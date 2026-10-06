# -*- coding: utf-8 -*-
"""TM训练环境: 封装SokuTrainerInstance为多环自对弈环境。
- VS_PLAYER双控(P1/P2都由我们驱动) / VS_COM(单控+真实对手)
- 对局结束自动续局(多环)
- SPEED变速(渲染保留下建议2-4)
- 每帧锁步: step()返回该输入作用后的完整状态包
公平性: 状态包只含物理量; 输入只写己方决策。"""
import ctypes
import glob
import os
import struct
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 本目录相对化(第六轮审计沙箱密闭性): 硬编码绝对根会让变异沙箱的
# import 解析回真实根, 变异测试全部失效
from soku_client2 import (SokuTrainerInstance, GameEnded, ProtocolError,
                          OPCODE_VS_PLAYER_START_GAME, OPCODE_VS_COM_START_GAME)  # noqa

# R46(第十四轮§3-1阻塞项): 全20角色 — 原只有三现役, 新角色在env构造处
# KeyError 5次×90s重试后退出(生成→加载→建模链条通了, 唯独没人跑过端到端)
CHAR = {"reimu": 0, "marisa": 1, "suika": 9,
        "sakuya": 2, "patchouli": 4, "yuyuko": 7,
        "reisen": 10, "komachi": 12, "tenshi": 14,
        "alice": 3, "youmu": 5, "remilia": 6, "yukari": 8,
        "aya": 11, "iku": 13, "sanae": 15, "cirno": 16,
        "meiling": 17, "utsuho": 18, "suwako": 19}

k32 = ctypes.windll.kernel32
k32.CreateMutexW.restype = ctypes.c_void_p   # R17(F18): 同CreateMutexW —
k32.OpenProcess.restype = ctypes.c_void_p    # 默认c_int会截断64位HANDLE
BATTLE_MGR_P = 0x8985E4
INPUT_TBL = 0x898680

# ---- R16: 游戏boot窗口跨进程互斥 ----
# 实测(探针v4-v9): 两游戏同时在boot段 → 后启动者永久卡在loader init
# (mod不连, 120s超时死循环); 错峰20s则全部正常。13:55旧批能跑纯靠
# trainer模型加载耗时不等形成的自然错峰。所有游戏生成走_spawn →
# 在此用命名互斥体把boot串行化, 后到者等待而非卡死游戏。
k32.CreateMutexW.restype = ctypes.c_void_p
_BOOT_MUTEX_NAME = "Local\\th123_train_game_boot"
_BOOT_TAIL_GRACE_S = 15.0    # 连接后继续持锁的余量: 实测排他窗延伸到
                             # accept之后(开局序列title→battle期间), accept+5s
                             # 放锁会让下一个游戏撞进尾段秒死(marisa 5连败根因);
                             # 错峰20s的探针全连 → 尾段<14.5s, 取15s
_BOOT_ACCEPT_TIMEOUT_S = 90.0  # 持锁期间的accept上限(空闲boot≈6~12s;
                               # 其他trainer更新期的重载下可超35s — 实测
                               # marisa被35s误杀; 90s兼顾锁占用与慢boot)


class _BootLock:
    """RAII跨进程boot互斥。锁等待超时=抛异常(绝不降级无锁启动 —
    实测无锁并发boot会让后到游戏秒死并级联)。"""

    def __init__(self, timeout_s=60.0):
        self.h = k32.CreateMutexW(None, False, _BOOT_MUTEX_NAME)
        if not self.h:
            # R19(审查2026-10-02): 原版静默return=降级无锁启动, 与类文档
            # "绝不降级"矛盾 — 无锁并发boot会让后到游戏秒死并级联
            raise RuntimeError("CreateMutexW失败(0x%X) — 拒绝无锁boot"
                               % k32.GetLastError())
        self.ok = False
        r = k32.WaitForSingleObject(ctypes.c_void_p(self.h),
                                    int(timeout_s * 1000))
        # 0=取得 0x80=被弃(前任崩溃, 视为取得)
        if r in (0, 0x80):
            self.ok = True
        else:
            err = k32.GetLastError()
            self.release()
            raise RuntimeError(
                "boot锁等待超时(r=%d, err=%d) — 拒绝无锁启动, 外层重试" % (r, err))

    def release(self):
        if self.h:
            if self.ok:
                k32.ReleaseMutex(ctypes.c_void_p(self.h))
            k32.CloseHandle(ctypes.c_void_p(self.h))
            self.h = None
            self.ok = False


# ---- R16: 对局窗口标志(系统态受损规避) ----
# 实测(探针v15-v19): 本机自14:45起, 有对局运行时新spawn的游戏会在0.5s内
# 自退(码1, 窗口未建); 历史会话无此性质(每段0-3次重建)。mod集/config/
# DLL/渲染/速度全排除 → 判定为系统会话态受损, 重启系统可清。
# 规避(语义: "忙"标志从spawn起立、贯穿boot+开局+对局、close时清):
# 所有spawn等"其他trainer全在更新阶段"才动 → boot/开局/对局整段跨进程
# 串行, PPO更新(~2.5min, 无标志)仍并发。系统恢复后等待自然缩短。
_MATCH_FLAG = os.path.join(tempfile.gettempdir(),
                          "th123_match_%d.flag" % os.getpid())
# 健康标记: 争用状态下强闯spawn成功 → 系统支持"对局中spawn" → 30分钟内
# 后续spawn跳过等待(全吞吐)。失败则删标记 → 串行保命模式。
_HEALTHY_MARKER = os.path.join(tempfile.gettempdir(),
                               "th123_spawn_healthy.marker")
_HEALTHY_TTL_S = 86400.0  # 24h(D3D根因已修复: SokuDirectXOptimizations
                          # 解决了多实例boot, 标记基本不会失效. 保留24h而非
                          # 永久是为了万一系统真出问题时能自动降级)


def _healthy():
    try:
        return time.time() - os.path.getmtime(_HEALTHY_MARKER) < _HEALTHY_TTL_S
    except OSError:
        return False


def _mark_healthy(on):
    try:
        if on:
            open(_HEALTHY_MARKER, "w").close()
        elif os.path.exists(_HEALTHY_MARKER):
            os.remove(_HEALTHY_MARKER)
    except OSError:
        pass


def _set_match_flag(on):
    try:
        if on:
            open(_MATCH_FLAG, "w").close()
        elif os.path.exists(_MATCH_FLAG):
            os.remove(_MATCH_FLAG)
    except OSError:
        pass


_MATCH_STALE_S = 30.0     # 心跳新鲜度: _watch每拍touch, 超30s视为不再活跃


def _touch_match_flag():
    """心跳: _watch线程每拍调用(局活着=标志常新)。"""
    try:
        os.utime(_MATCH_FLAG, None)
    except OSError:
        _set_match_flag(True)   # 被外部清掉则重建(局仍在)


def _live_other_matches():
    """其他trainer的活跃对局数 — mtime新鲜度判活(对PID复用免疫, R16审计
    第2/3条: 原OpenProcess判活会被复用PID骗过; 崩溃残留>60s顺手回收)。"""
    n = 0
    now = time.time()
    for fp in glob.glob(os.path.join(tempfile.gettempdir(),
                                     "th123_match_*.flag")):
        if fp == _MATCH_FLAG:
            continue
        try:
            age = now - os.path.getmtime(fp)
        except OSError:
            continue
        if age > 60.0:
            try:
                os.remove(fp)   # 死残留自愈(崩溃/重启遗留)
            except OSError:
                pass
            continue
        if age < _MATCH_STALE_S:
            n += 1
    return n


def _wait_match_free(timeout_s=600.0):
    """等其余trainer全进更新阶段(无忙标志)。上限600s=3个trainer连续
    忙段的最坏排队(boot15s+对局~90s各×2); 实测90s会硬闯被杀。"""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if _live_other_matches() == 0:
            return True
        time.sleep(1.0)
    print("[env] 等待无对局窗口超时(%.0fs) — 硬闯尝试(外层重试兜底)"
          % timeout_s)
    return False


class TMEnv:
    def __init__(self, port, char_left="reimu", char_right="reimu",
                 vs_com=False, tps=None, deck=None, launch=True, render=False,
                 com_difficulty=None, lane=None, deck_left=None,
                 deck_right=None):
        self.base_port = port
        self.port = port
        # R19(审查2026-10-02): 车道锚定 — 原 base+(x+1)%10 的行走假设
        # base=车道起点; 当base是rebuild_port的中段口时(12宽车道), 行走
        # 侵入相邻slot车道/eval段(审查枚举: slot0实际可达20850-20870,
        # slot3越界至20906)。lane=(lo,hi)显式给出车道, 行走环回其中。
        # 默认10宽车道(训练主端口20800/20810/20820、eval 20900、exp 20940)。
        if lane is not None:
            self._lane_lo, self._lane_hi = lane
        else:
            self._lane_lo, self._lane_hi = port, port + 9
        assert self._lane_lo <= port <= self._lane_hi, \
            "port不在车道内: %d lane=%s" % (port, lane)
        self.char_left = CHAR[char_left]
        self.char_right = CHAR[char_right]
        self.vs_com = vs_com
        # R47(可行性报告天花板2): deck采样 — 原恒系统卡1-20(技能卡/SC
        # 永不入手→整套技能子系统死跑)。现由外部传入或自动采样。
        # 从零#2(fleet P2): deck_left/right入构造参数 — _start_first在
        # __init__内即发包, 构造后才赋值=首局恒系统卡(R53只修了续局,
        # ~15-20%局无技能/SC)。
        self.deck = deck if deck is not None else list(range(1, 21))
        self.deck_left = deck_left     # R47: P1侧独立deck(可异于P2)
        self.deck_right = deck_right
        self.tps = tps
        self.render = render
        self.com_difficulty = com_difficulty
        self.games = 0
        self.inst = None
        self.h = None
        self._monitor_stop = None
        self._spawn(first=True)

    def _spawn(self, first=False):
        """全新游戏进程+连接(按局重启 — 规避mod协议跨局残包, 参照其PY reconnect)
        R19: first=True用base本身(原版首次spawn即+1, base每10次才用一次);
        重启在车道内环回(不再依赖base与行走同源)。"""
        if self.inst:
            try:
                self.inst.close()
            except OSError:
                pass
        if self._monitor_stop:
            self._monitor_stop.set()
        if self.h:
            k32.CloseHandle(ctypes.c_void_p(self.h))
            self.h = None   # R17(F12): 置None防异常路径二次CloseHandle
                              # 复用句柄值(对齐close()的D10纪律)
        if not first:
            _w = self._lane_hi - self._lane_lo + 1
            self.port = self._lane_lo + (self.port - self._lane_lo + 1) % _w
        self.inst = None
        _set_match_flag(False)          # 清自己上一环境的残留标志
        # R16自适应: 健康标记新鲜 → 直接spawn(系统支持对局中spawn, 全吞吐);
        # 否则等其余trainer全进更新阶段。注意语义: 等到窗口后spawn成功
        # ≠系统健康(窗口spawn本就该活); 只有超时硬闯成功才证明健康。
        _contended = _live_other_matches() > 0
        _forced = False
        if _contended and not _healthy():
            _forced = not _wait_match_free()
        _set_match_flag(True)           # R16: 即刻宣布"忙"(boot+开局+对局整段)
        try:
            _bl = _BootLock(timeout_s=60.0)   # R16: boot窗口串行化(锁超时=异常, 不降级)
            try:
                # 持锁期accept(90s): 空闲boot 6~12s; 重载下可超35s(实测)
                self.inst = SokuTrainerInstance(
                    self.port, accept_timeout=_BOOT_ACCEPT_TIMEOUT_S)
                time.sleep(_BOOT_TAIL_GRACE_S)
            finally:
                _bl.release()
        except Exception:
            if _forced:
                _mark_healthy(False)    # 硬闯失败 → 系统仍受损(仅硬闯才证伪)
            _set_match_flag(False)      # R19: boot失败清忙标志(防幽灵卡闸门)
            raise
        # R19(审查2026-10-02): 语义=粘性健康 — 任何成功spawn都刷新全局
        # 健康标记(防TTL过期回降级); 只有硬闯失败才证伪(原两支同函数,
        # 合并并注明语义)
        _mark_healthy(True)
        self.pid = self.inst.proc.pid
        self.h = k32.OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0400, False,
                                 self.pid)
        self._tbl_filled = False
        self._first_frame = True
        self._monitor_stop = threading.Event()
        threading.Thread(target=self._watch, daemon=True).start()
        # 变速在开局前发送且不读应答(OK应答与帧流交错会造成读串 — 实测ep3秒死);
        # 杂音OK由首帧容错循环吃掉
        if self.tps:
            self.inst.sock.sendall(struct.pack("<BI", 2, self.tps))
        # 关渲染(DISPLAY=3, bool false): PinkySmile默认路径, 省GPU/CPU;
        # 虚拟视觉后屏幕纯装饰 — render=True可保留观看
        if not self.render:
            self.inst.sock.sendall(struct.pack("<BB", 3, 0))
        # 注意: 不发OPCODE_SOUND(4) — mod未实现该opcode,
        # 发送会破坏协议流导致后续所有通信错乱(实测).
        # COM难度设置(必须在_start_first之前: 游戏开局时读取0x008998A4
        # 并初始化AI参数, 局中改无效 — 实测验证)
        # R17(R2纪律补全): 原版裸写+吞异常 — 失败被当成功, com_eval外部
        # 标尺读数不可信。现写后读回校验, 失败大声打印。
        com_diff = getattr(self, 'com_difficulty', None)
        if com_diff is not None and self.vs_com and self.h:
            ok = False
            try:
                # R18字节预检(R2三道齐): 先读当前值, 非0..3合法难度域
                # → 地址假设错误, 拒绝写入(防错结构盲写)
                pb = ctypes.create_string_buffer(1)
                pn = ctypes.c_size_t()
                pre_ok = (k32.ReadProcessMemory(
                    ctypes.c_void_p(self.h), ctypes.c_void_p(0x008998A4),
                    pb, 1, ctypes.byref(pn)) and pn.value == 1
                    and pb.raw[0] <= 3)
                if not pre_ok:
                    print("[env] COM难度预检失败(现值0x%02X非0..3) — 拒写!"
                          % pb.raw[0])
                else:
                    ok = bool(k32.WriteProcessMemory(
                        ctypes.c_void_p(self.h), ctypes.c_void_p(0x008998A4),
                        bytes([com_diff & 0xFF]), 1, None))
                    rb = ctypes.create_string_buffer(1)
                    n = ctypes.c_size_t()
                    if ok and k32.ReadProcessMemory(
                            ctypes.c_void_p(self.h),
                            ctypes.c_void_p(0x008998A4),
                            rb, 1, ctypes.byref(n)) and n.value == 1:
                        ok = rb.raw[0] == (com_diff & 0xFF)
                    else:
                        ok = False
            except Exception as e:
                print("[env] COM难度写入异常: %r" % e)
                ok = False
            if not ok:
                print("[env] COM难度写入校验失败(期望%d) — 本局难度不可信!"
                      % com_diff)
        # R17(泄漏修复 — connection failed根因): _start_first失败时实例
        # 已绑定监听, 原版直接抛出 → lsock泄漏。外环每次新建EvalEnv端口
        # 轮换重置 → SO_REUSEADDR对泄漏口静默双绑 → 游戏连接被僵尸监听
        # 吃掉 → "未连接(自行退出)码0"。任何后续失败都必须收掉inst。
        # R19(审查2026-10-02): 还须收掉R16的监视线程+进程句柄+忙标志 —
        # 原版只收inst, 线程继续触碰th123_match_<pid>.flag保持新鲜,
        # 其它训练器的并发闸门被幽灵"对局中"卡600s后硬闯。
        try:
            self._start_first()
        except Exception:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
            if self._monitor_stop:
                self._monitor_stop.set()
            if self.h:
                k32.CloseHandle(ctypes.c_void_p(self.h))
                self.h = None
            _set_match_flag(False)
            raise

    def _start_first(self):
        """纯净开局: 单START等应答, err12(尚未到可开局场景)静默重试。
        不发填充输入(会触发选人自动驾驶搅乱场景机 — 实测)。
        R47: P1/P2各自独立deck — deck_left/deck_right为None时退回self.deck"""
        op = OPCODE_VS_COM_START_GAME if self.vs_com else OPCODE_VS_PLAYER_START_GAME
        dl = self.deck_left if self.deck_left else self.deck
        dr = self.deck_right if self.deck_right else self.deck
        pkt = struct.pack(
            "<BBBI20sB32sI20sB32s",
            op, 0, 0,
            self.char_left, bytes(dl), 0, b"RL-L".ljust(32, b"\0"),
            self.char_right, bytes(dr), 0, b"RL-R".ljust(32, b"\0"))
        for attempt in range(60):
            # D6(从零审查): 双排干 — SPEED/DISPLAY的OK若晚到会把
            # 下一次START的判定骗成"成功"(games虚增+真拒绝永不知晓)
            self._drain()
            time.sleep(0.03)
            self._drain()
            self.inst._send(pkt)
            try:
                r = self.inst._recv_exact(1, 2.0)[0]
            except TimeoutError:
                continue
            if r == 12:  # OPCODE_OK
                self.games += 1
                _set_match_flag(True)   # R16: 对局开始 → 通知全场spawn等待
                return
            if r == 7:
                try:
                    err = self.inst._recv_exact(1, 1.0)[0]
                except TimeoutError:
                    continue
                if err == 12:      # STILL_PLAYING — 场景未就绪, 静默重试
                    time.sleep(0.2)
                    continue
                raise RuntimeError("开局err=%d" % err)
            time.sleep(0.2)
        raise RuntimeError("开局重试耗尽")

    def _drain(self):
        """非阻塞排空接收缓冲(旧帧残留会读串协议)。
        D1(R17回归修复): 对端FIN后recv返回b''且不再抛异常 —
        原版丢弃返回值⇒紧循环单核100%永久挂死(看门狗无法抢占socket调用)。
        判b''即break + 有界迭代双保险。"""
        s = self.inst.sock
        s.setblocking(False)
        try:
            for _ in range(64):            # 有界: 64×64KB=4MB残留足矣
                d = s.recv(65536)
                if not d:                  # EOF/FIN — 对端已关, 停止
                    break
        except (BlockingIOError, ConnectionResetError):
            pass
        finally:
            s.setblocking(True)
            s.settimeout(30.0)   # R17: setblocking(True)等效settimeout(None),
            #                      会清掉F7的发送超时 — 此处复位

    def _watch(self):
        """战斗期回填输入表 + 场景轨迹日志。
        D3修复(从零审查, R2红线): 仅scene==5(BATTLE)才允许解析指针链并写入;
        写前读回原值预检; 写后校验返回值与字节数; 任一失败不置_tbl_filled
        (原版无门禁+不校验, 在标题/选人期可能把垃圾值写进全局输入表并整局锁定)。"""
        last = None
        while not self._monitor_stop.is_set():
            _touch_match_flag()   # R16心跳: 判活只看新鲜度(防PID复用+残留)
            try:
                import ctypes as _c
                b = _c.create_string_buffer(1)
                g = _c.c_size_t()
                if k32.ReadProcessMemory(_c.c_void_p(self.h),
                                         _c.c_void_p(0x8A0044), b, 1,
                                         _c.byref(g)):
                    s = b.raw[0]
                    if s != last:
                        print("  [env] scene %s→%s" % (last, s))
                        last = s
            except Exception:
                pass
            if not self._tbl_filled and last == 5:
                rl = ctypes.create_string_buffer(4)
                g = ctypes.c_size_t()
                got = None
                if k32.ReadProcessMemory(ctypes.c_void_p(self.h),
                                         ctypes.c_void_p(BATTLE_MGR_P), rl, 4,
                                         ctypes.byref(g)) and g.value == 4:
                    bm = struct.unpack("<I", rl.raw)[0]
                    if 0x10000 < bm < 0x80000000:
                        for ofs in (0x0C, 0x10):
                            if k32.ReadProcessMemory(ctypes.c_void_p(self.h), ctypes.c_void_p(bm + ofs), rl, 4, ctypes.byref(g)) and g.value == 4:
                                cm = struct.unpack("<I", rl.raw)[0]
                                if 0x10000 < cm < 0x80000000 and \
                                   k32.ReadProcessMemory(ctypes.c_void_p(self.h), ctypes.c_void_p(cm + 0x750), rl, 4, ctypes.byref(g)) and g.value == 4:
                                    kmgr = struct.unpack("<I", rl.raw)[0]
                                    km = ctypes.create_string_buffer(4)
                                    if 0x10000 < kmgr < 0x80000000 and \
                                       k32.ReadProcessMemory(ctypes.c_void_p(self.h), ctypes.c_void_p(kmgr), km, 4, ctypes.byref(g)) and g.value == 4:
                                        v = struct.unpack("<I", km.raw)[0]
                                        if 0x10000 < v < 0x80000000:
                                            got = v
                                            break
                if got:
                    # 字节预检: 读回输入表现值, 非合法指针形态则拒绝写入
                    # R19(审查2026-10-02): 原版只校验读回字节数, 注释声称的
                    # "合法指针形态"从未检查 — 现值须为0或指针形态(0x10000
                    # ..0x7FFFFFFF)才写(非此=地址假设错误, 拒绝盲写)
                    old = ctypes.create_string_buffer(8)
                    if not (k32.ReadProcessMemory(
                            ctypes.c_void_p(self.h),
                            ctypes.c_void_p(INPUT_TBL), old, 8,
                            ctypes.byref(g)) and g.value == 8):
                        self._tbl_filled = False
                    else:
                        _ov = struct.unpack("<II", old.raw)
                        if not all(v == 0 or 0x10000 < v < 0x80000000
                                   for v in _ov):
                            print("  [env] 输入表现值非法(%08X/%08X) — 拒写"
                                  % _ov)
                            self._tbl_filled = False
                        else:
                            w = k32.WriteProcessMemory(
                                ctypes.c_void_p(self.h),
                                ctypes.c_void_p(INPUT_TBL),
                                struct.pack("<II", got, got), 8,
                                ctypes.byref(g))
                            if w and g.value == 8:
                                self._tbl_filled = True
                            else:
                                print("  [env] 输入表写入失败(w=%s n=%s) — 不锁定, 下轮重试"
                                      % (bool(w), g.value))
            self._monitor_stop.wait(0.2)

    def step(self, left_in=None, right_in=None):
        """发一帧输入, 返回(left, right, weather, objects)。
        首帧前容忍加载期协议杂音; 对局结束 → 同进程续局(快),
        协议异常 → 进程重启兜底。返回None=局边界。"""
        t0 = time.time()
        while time.time() - t0 < 90:
            self.inst.send_inputs(left_in or {}, right_in or {})
            try:
                r = self.inst.recv_frame(timeout=2.0)
            except GameEnded:
                self._restart_same_process()
                return None
            except ProtocolError as e:
                if self._first_frame and e.code == 17:
                    time.sleep(0.005)  # 加载期NOT_IN_GAME限频(灭洪泛)
                    continue       # §9.2: 继续喂不重启
                # D7(从零审查): 首帧期也只容忍err=17 — 其余协议错
                # 打印后走重启(原版全吞, 掩盖崩溃根因)
                if self._first_frame:
                    print("  [env] 首帧期协议错 code=%d op=%s → 重启"
                          % (e.code, e.op))
                    self.games += 1
                    self._spawn()
                    return None
                # D8(从零审查): 稳态err=17=短暂离开BATTLE, 继续喂(§9.2),
                # 不再白白重启一局; 其余错误码才重启
                if e.code == 17:
                    time.sleep(0.005)
                    continue
                print("  [env] 局终止: 协议错code=%d → 同进程续局" % e.code)
                self._restart_same_process()
                return None
            except TimeoutError:
                if self._first_frame:
                    continue       # 等首帧 — 继续喂
                print("  [env] 局终止: 超时 → 进程重启")
                self.games += 1
                self._spawn()
                return None
            except ConnectionError:
                print("  [env] 连接断 → 进程重启")
                self.games += 1
                self._spawn()
                return None
            self._first_frame = False
            return r
        print("  [env] 90s无帧 → 进程重启")
        self.games += 1
        self._spawn()
        return None

    def _restart_same_process(self):
        """同进程续局 — mod修复版(2026-09-23): startGame等场景稳定+重置键管理器。
        若仍失败自动fallback进程重启。
        R53(§S1): 续局包改用双deck源(原恒self.deck=系统卡 — 同进程续局
        是主路径, 导致R47卡组激活~90%失效)。"""
        op = OPCODE_VS_COM_START_GAME if self.vs_com else OPCODE_VS_PLAYER_START_GAME
        dl = self.deck_left if self.deck_left else self.deck
        dr = self.deck_right if self.deck_right else self.deck
        pkt = struct.pack(
            "<BBBI20sB32sI20sB32s",
            op, 0, 0,
            self.char_left, bytes(dl), 0, b"RL-L".ljust(32, b"\0"),
            self.char_right, bytes(dr), 0, b"RL-R".ljust(32, b"\0"))
        for attempt in range(30):
            self._drain()
            self.inst._send(pkt)
            try:
                r = self.inst._recv_exact(1, 2.0)[0]
            except TimeoutError:
                time.sleep(0.2)
                continue
            if r == 12:  # OK — mod等到了场景稳定
                self.games += 1
                self._first_frame = True
                self._tbl_filled = False
                return
            if r == 7:
                try:
                    err = self.inst._recv_exact(1, 1.0)[0]
                except TimeoutError:
                    continue
                if err in (0, 10, 12, 17):
                    time.sleep(0.5)   # 场景过渡中 — 给清理时间
                    continue
                break
            time.sleep(0.3)
        # fallback
        self.games += 1
        self._spawn()

    def close(self):
        # D10(从零审查): 幂等 + 置None — 原版二次CloseHandle可能误关
        # 被复用的句柄值(外环finally与训练器异常处理都会各调一次)
        _set_match_flag(False)   # R16: 本环境对局结束
        if self._monitor_stop:
            self._monitor_stop.set()
        if getattr(self, "inst", None):
            try:
                self.inst.close()
            except (OSError, AttributeError):
                pass
            self.inst = None
        if getattr(self, "h", None):
            k32.CloseHandle(ctypes.c_void_p(self.h))
            self.h = None
