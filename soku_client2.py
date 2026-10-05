# -*- coding: utf-8 -*-
"""SokuAITrainer(TrainingMod) TCP客户端 — PinkySmile原版协议。
帧格式与GameInstance.py一致(CharacterState=105B; R39: 修订2.2记录的
101→105修复从未落地, 现补上)。
用法: python soku_client2.py [端口]"""
import ctypes
import os
import select
import socket
import struct
import subprocess
import sys
import tempfile
import time

OPCODE_HELLO = 0
OPCODE_GOODBYE = 1
OPCODE_SPEED = 2
OPCODE_DISPLAY = 3
OPCODE_SOUND = 4
OPCODE_VS_PLAYER_START_GAME = 5
OPCODE_FAULT = 6
OPCODE_ERROR = 7
OPCODE_GAME_FRAME = 8
OPCODE_GAME_INPUTS = 9
OPCODE_GAME_CANCEL = 10
OPCODE_GAME_ENDED = 11
OPCODE_OK = 12
OPCODE_SET_HEALTH = 13
OPCODE_SET_POSITION = 14
OPCODE_SET_WEATHER = 15
OPCODE_RESTRICT_MOVES = 16
OPCODE_VS_COM_START_GAME = 17

CHAR_REIMU = 0
CHAR_MARISA = 1
CHAR_SUIKA = 9

GAME_DIR = r"D:\touhou\hisoutensoku2026-06-15\th123_train"
EXE = GAME_DIR + r"\th123.exe"

CS_FIELDS = [
    "direction", "position.x", "position.y",
    "action", "sequence", "pose", "poseFrame",
    "frameCount", "comboDamage", "comboLimit",
    "airBorne", "timeStop", "hitStop",
    "hp", "airDashCount", "spirit", "maxSpirit",
    "untech", "healingCharm", "confusion", "swordOfRapture",
    "score",
    "hand",            # 10字节: 5×(id,cost)
    "cardGauge",
    "skills",          # 15字节
    "fanLevel", "rodsLevel", "booksLevel", "dollLevel", "dropLevel",
    "dropInvulTimeLeft", "superArmorHp", "imageID",
    "csd",             # 20字节 角色特异数据
    "objectCount",
]
CS_FMT = "<b2fHHHHIHH?HHHBHHHHHHB10sH15sBBBBBHHH20sB"
CS_SIZE = struct.calcsize(CS_FMT)          # 实测为准(手算易错)
FRAME_HEAD = 1 + CS_SIZE * 2 + 4           # op + 两角色 + 天气4字节(char+char+u16)


class GameEnded(Exception):
    def __init__(self, winner, ls, rs):
        super().__init__("winner=%s %d-%d" % (winner, ls, rs))
        self.winner = winner
        self.ls = ls    # 左方回合胜数(外环战报用, 2026-09-22补)
        self.rs = rs


class ProtocolError(RuntimeError):
    """结构化协议错误(从零审查D8): 上层按.code分支, 不再子串匹配文案 —
    改文案=静默改行为的事故源。code=-1为未知op。"""
    def __init__(self, code, op=None):
        super().__init__("协议错误 err=%d" % code if code >= 0
                         else "未知op=%d" % op)
        self.code = code
        self.op = op


class SokuTrainerInstance:
    def __init__(self, port, launch=True, exe=EXE, game_dir=GAME_DIR,
                 accept_timeout=120.0):
        self.port = port
        # R17(僵尸口探针 — connection failed根因的保险网): SO_REUSEADDR对
        # 已被监听的口会静默双绑, 游戏连接被旧监听吃掉→"未连接"。bind前
        # 先connect探测: 拒绝=空闲可绑; 成功=有活监听(泄漏)→响亮报错。
        _probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _probe.settimeout(0.3)
        if _probe.connect_ex(("127.0.0.1", port)) == 0:
            _probe.close()
            raise RuntimeError(
                "端口%d已被监听(泄漏的僵尸lsock?) — 拒绝双绑" % port)
        _probe.close()
        self.lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind(("127.0.0.1", port))
        self.lsock.listen(1)
        self.proc = None
        if launch:
            # R17: 禁止游戏进程崩溃弹窗(pure virtual function call等)
            # SetErrorMode被子进程继承 — 游戏静默死亡→训练器检测→自动重启
            # SEM_NOGPFAULTERRORBOX=0x2 | SEM_FAILCRITICALERRORS=0x1
            _prev_mode = ctypes.windll.kernel32.SetErrorMode(0x0002)
            # R16: 游戏stdout落盘(按口截断, 每次boot约7KB — loader日志是
            # 连接故障的一手证据; 原DEVNULL让"游戏卡在哪一步"永远不可见)
            _boot_log = os.path.join(
                tempfile.gettempdir(), "th123_boot_%d.log" % port)
            _blf = open(_boot_log, "wb")
            # R17: 不抢焦点 — SW_SHOWNOACTIVATE(4): 窗口显示但不激活
            # 用户2026-09-30: 多实例并发时每次boot都抢走当前窗口焦点
            _si = subprocess.STARTUPINFO()
            _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            _si.wShowWindow = 4   # SW_SHOWNOACTIVATE
            self.proc = subprocess.Popen(
                [exe, str(port)], cwd=game_dir,
                stdin=subprocess.DEVNULL,
                stdout=_blf,
                stderr=subprocess.DEVNULL,   # 1.5GB磁盘事故修复: mod的printf已灭+不再落盘
                startupinfo=_si)
            _blf.close()
        # 第六轮审计§7b: accept无超时=游戏连接前崩溃则永久静默挂起
        self.lsock.settimeout(accept_timeout)
        try:
            self.sock, _ = self.lsock.accept()
        except socket.timeout:
            # BUGREPORT§6-3: 失败路径自收尾(原来只terminate了proc, lsock漏)
            try:
                self.lsock.close()
            except OSError:
                pass
            # R16排查: 游戏退出码是死因的一手证据(mod的UnhandledExFilter用
            # 异常码调ExitProcess, 不留WER事件; None=还活着=慢boot/挂起,
            # 由本方terminate终止 — 与自退区分报告)
            _code = None
            _slow = False
            if self.proc:
                _code = self.proc.poll()
                if _code is None:
                    _slow = True   # 35/90s仍存活: 慢boot(他trainer更新期
                    #               磁盘/CPU重载下boot可超35s) 或 真挂起
                    self.proc.terminate()
                    try:
                        _code = self.proc.wait(5)
                    except Exception:
                        _code = "still-alive"
            raise RuntimeError("游戏实例%.0fs内未连接 %s 游戏退出码=%r"
                               % (accept_timeout,
                                  "(慢boot被终止)" if _slow else "(自行退出)",
                                  _code))
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # R17(F7): 发送超时 — 原阻塞socket的sendall在mod不排空时永久阻塞
        # (与recv不同, send无select守卫)。30s: 正常帧间隔<10ms, 病理才触顶。
        self.sock.settimeout(30.0)
        hello = b"\x00\x2A\x9D\x6E\xF5"
        try:
            self._send(hello)
            echo = self._recv_exact(len(hello), 15.0)
        except (OSError, TimeoutError) as e:
            # R17(F10): 握手失败路径原无清理(sock/lsock泄漏, proc不终止)
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
            try:
                self.lsock.close()
            except OSError:
                pass
            self.lsock = None
            if self.proc:
                self.proc.terminate()
            raise RuntimeError("握手失败(%s): %s" % (type(e).__name__, e))
        if echo != hello:
            # R19(审查2026-10-02): 原版无清理直接raise — 与超时分支同类
            # 缺陷只修了一半; lsock继续LISTENING侵蚀端口车道+游戏进程泄漏
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
            try:
                self.lsock.close()
            except OSError:
                pass
            self.lsock = None
            if self.proc:
                self.proc.terminate()
            raise RuntimeError("握手失败: %s" % (echo and echo.hex()))

    def _send(self, d):
        self.sock.sendall(d)

    def close(self):
        """D10幂等 + 半构造安全(BUGREPORT_soku_client2_close §6):
        本方法曾被误缩进进CrashInfo(上游D1'缺陷, 训练日志'no attribute close'
        即此) — 已搬回。accept超时/握手失败时实例没有self.sock却有lsock+proc,
        恰是最需要收尾的状态: 逐属性getattr兜底, 修后置None保幂等。
        R17(F9): terminate后wait(5)回收子进程并取退出码(死因的一手证据)。"""
        try:
            if getattr(self, "sock", None) is not None:
                self._send(bytes([OPCODE_GOODBYE]))
        except OSError:
            pass
        for _name in ("sock", "lsock"):
            _s = getattr(self, _name, None)
            if _s is not None:
                try:
                    _s.close()
                except OSError:
                    pass
                setattr(self, _name, None)
        _p = getattr(self, "proc", None)
        if _p is not None:
            try:
                _p.terminate()
            except OSError:
                pass
            # R19(审查2026-10-02): 原版wait(5)包在except:pass里 — 存活
            # 超5s的游戏既不kill也不报告(退出码证据被吞)。补kill兜底。
            try:
                _code = _p.wait(5)
                if _code not in (0, None) and _code != 1:
                    # 1=本方terminate的常见码; 其他码=游戏自退(异常码)
                    print("[close] 游戏退出码=%r" % _code)
            except Exception:
                try:
                    _p.kill()
                    print("[close] 游戏5s未退 — kill(退出码=%r)" % _p.wait(5))
                except Exception as e:
                    print("[close] 游戏无法回收: %r" % e)

    def _recv_exact(self, n, timeout=30.0):
        """D2修复(从零审查): deadline制 — 首字节后的剩余字节共享同一预算,
        原版首字节后变无限阻塞, mod中途崩溃=训练永久静默挂起(看门狗无法抢占)。
        R19(审查2026-10-02): timeout默认None是"无deadline"后门 — 不带
        参调用点(:262/:273帧体读取等)退回无限阻塞。默认30s(与socket级
        settimeout一致), 需要阻塞语义的调用点显式传None。"""
        buf = b""
        deadline = None
        if timeout is not None:
            deadline = time.time() + timeout
        while len(buf) < n:
            if deadline is not None:
                remain = deadline - time.time()
                if remain <= 0:
                    raise TimeoutError()
                r, _, _ = select.select([self.sock], [], [], remain)
                if not r:
                    raise TimeoutError()
            c = self.sock.recv(n - len(buf))
            if not c:
                raise ConnectionError("连接关闭(半包途中)")
            buf += c
        return buf

    def start_vs_com(self, left_char=CHAR_REIMU, right_char=CHAR_REIMU,
                     deck=None, stage=0, music=0):
        """VS COM开局 — 含wait_for_ready状态机(err=12→CANCEL→排干重试)"""
        deck = deck if deck is not None else list(range(1, 21))
        pkt = struct.pack(
            "<BBBI20sB32sI20sB32s",
            OPCODE_VS_COM_START_GAME, stage, music,
            left_char, bytes(deck), 0, b"RL-LEFT".ljust(32, b"\0"),
            right_char, bytes(deck), 0, b"RL-RIGHT".ljust(32, b"\0"))
        assert len(pkt) == 117, len(pkt)
        for attempt in range(20):
            self._send(pkt)
            try:
                op = self._recv_exact(1, 20.0)[0]
            except TimeoutError:
                # demo战斗锁步卡死网络线程 — CANCEL唤醒后重试
                print("  尝试#%d: 无应答(demo锁步?) → CANCEL唤醒" % (attempt + 1))
                try:
                    self._send(bytes([OPCODE_GAME_CANCEL]))
                    self._recv_exact(1, 3.0)
                except (TimeoutError, ConnectionError):
                    pass
                continue
            if op == OPCODE_OK:
                print("  开局OK(第%d次)" % (attempt + 1))
                return op
            if op != OPCODE_ERROR:
                raise RuntimeError("开局异常op=%d" % op)
            err = self._recv_exact(1)[0]
            print("  尝试#%d: err=%d" % (attempt + 1, err))
            if err != 12:
                raise RuntimeError("开局被拒 err=%d" % err)
            # wait_for_ready式: CANCEL → 视应答决定
            self._send(bytes([OPCODE_GAME_CANCEL]))
            try:
                op2 = self._recv_exact(1, 10.0)[0]
            except TimeoutError:
                continue
            if op2 == OPCODE_ERROR:
                e2 = self._recv_exact(1)[0]
                print("    cancel→err=%d" % e2)
                if e2 != 17:
                    raise RuntimeError("cancel后err=%d" % e2)
                continue
            # 帧应答 → 排干
            try:
                for _ in range(120):
                    self.send_inputs(
                        {"A": False, "B": False, "C": False, "D": False,
                         "SC": False, "SW": False, "H": 0, "V": 0}, {})
                    self.recv_frame(timeout=1.0)
            except (TimeoutError, GameEnded, ConnectionError, RuntimeError):
                continue
        raise RuntimeError("开局重试耗尽")

    def set_speed(self, tps):
        self._send(struct.pack("<BI", OPCODE_SPEED, tps))
        self._recv_exact(1, 5.0)

    def send_inputs(self, left, right):
        def pack(i):
            v = 0
            v |= bool(i.get("A")) << 0
            v |= bool(i.get("B")) << 1
            v |= bool(i.get("C")) << 2
            v |= bool(i.get("D")) << 3
            v |= bool(i.get("SC")) << 4
            v |= bool(i.get("SW")) << 5
            v |= (i.get("H", 0) & 3) << 6
            v |= (i.get("V", 0) & 3) << 8
            return v
        self._send(struct.pack("<BHH", OPCODE_GAME_INPUTS,
                               pack(left), pack(right)))

    def recv_frame(self, timeout=2.0):
        r, _, _ = select.select([self.sock], [], [], timeout)
        if not r:
            raise TimeoutError()
        # R17(F6): 帧体/OK跳过/对象块读取原无deadline — D2只覆盖了帧首
        # 字节; 对端发半包后停住则永久阻塞(实测4s仍挂)。统一2s预算。
        op = self._recv_exact(1, 2.0)[0]
        # 控制包(SET_POSITION/HEALTH等)的OK应答会混入帧流 — 透明跳过。
        # (2026-09-22 hitlab教训: 不跳过则上层把op=12当协议错误重开对局,
        #  摆位/回血全部被重置回出生点)
        # R19(审查2026-10-02): 加8次迭代上限 — 对端持续发OK(每轮2s)时
        # 原版永不返回, step()的90s预算只在调用间检查, 看门狗无法抢占
        _ok_n = 0
        while op == OPCODE_OK:
            _ok_n += 1
            if _ok_n > 8:
                raise ProtocolError(-1, op)   # OK洪流按错位处理
            op = self._recv_exact(1, 2.0)[0]
        if op == OPCODE_GAME_FRAME:
            head = self._recv_exact(FRAME_HEAD - 1, 2.0)
            lv = struct.unpack(CS_FMT, head[0:CS_SIZE])
            rv = struct.unpack(CS_FMT, head[CS_SIZE:CS_SIZE * 2])
            wdisp, wact, wt = struct.unpack(
                "<bbH", head[CS_SIZE * 2:CS_SIZE * 2 + 4])
            left = dict(zip(CS_FIELDS, lv))
            right = dict(zip(CS_FIELDS, rv))
            # 发送端序列化 obj1+obj2 两个列表 — 计数取两侧之和
            n = left["objectCount"] + right["objectCount"]
            objs = []
            if n:
                raw = self._recv_exact(17 * n, 5.0)
                for i in range(n):
                    objs.append(struct.unpack("<b2f4H", raw[i*17:(i+1)*17]))
            return left, right, {"displayed": wdisp, "active": wact,
                                 "timer": wt}, objs
        if op == OPCODE_GAME_ENDED:
            w, ls, rs = self._recv_exact(3, 2.0)
            raise GameEnded(w, ls, rs)
        if op == OPCODE_ERROR:
            err = self._recv_exact(1, 2.0)[0]
            raise ProtocolError(err)
        if op == OPCODE_FAULT:
            addr, code = struct.unpack("<II", self._recv_exact(8, 2.0))
            # D7(从零审查): 崩溃必须响亮 — CrashInfo非RuntimeError子类,
            # 穿透tm_env的噪声容忍层直达训练器顶层, 带可排障的地址/码
            raise CrashInfo(addr, code)
        # R19(审查2026-10-02): 未知op=帧流错位(半帧残留被当opcode) —
        # 立即废socket, 防_start_first/续局把残留字节继续当opcode消耗、
        # 白烧重试次数; 上层按异常走进程重建(换socket=唯一可靠重同步)
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = None
        raise ProtocolError(-1, op)


class CrashInfo(Exception):
    """OPCODE_FAULT载荷"""
    def __init__(self, addr, code):
        super().__init__("游戏崩溃 @0x%X code=0x%X" % (addr, code))
        self.addr = addr
        self.code = code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    port = 20770
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    print("启动TM实例(端口%d)..." % port)
    inst = SokuTrainerInstance(port)
    pid = inst.proc.pid
    print("握手OK PID=%s" % pid)

    # 场景踢线程: TM的verify要求sceneId==TITLE(2), 而logo钩子跳到了SELECT(3)
    import ctypes
    import threading
    k32 = ctypes.windll.kernel32
    SCENE = 0x8A0044
    h = k32.OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0400, False, pid)
    stop_kick = threading.Event()
    kick_enabled = threading.Event()
    kick_enabled.set()   # 只在开局前允许踢SELECT→TITLE

    def kicker():
        last = None
        tbl_filled = False
        while not stop_kick.is_set():
            b = ctypes.create_string_buffer(1)
            g = ctypes.c_size_t()
            if k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(SCENE),
                                     b, 1, ctypes.byref(g)):
                s = b.raw[0]
                if s != last:
                    print("  [kick] scene=%s" % s)
                    last = s
                if s == 5 and not tbl_filled:
                    # 战斗期: bm链解析真实keymapManager → 回填0x898680输入表
                    rl = ctypes.create_string_buffer(4)
                    if k32.ReadProcessMemory(ctypes.c_void_p(h),
                                             ctypes.c_void_p(0x8985E4), rl, 4,
                                             ctypes.byref(g)) and g.value == 4:
                        bm = struct.unpack("<I", rl.raw)[0]
                        if 0x10000 < bm < 0x80000000:
                            km = ctypes.create_string_buffer(4)
                            ok2 = False
                            for ofs in (0x0C, 0x10):
                                if k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(bm + ofs), rl, 4, ctypes.byref(g)) and g.value == 4:
                                    cm = struct.unpack("<I", rl.raw)[0]
                                    if 0x10000 < cm < 0x80000000 and k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(cm + 0x750), rl, 4, ctypes.byref(g)) and g.value == 4:
                                        kmgr = struct.unpack("<I", rl.raw)[0]
                                        if 0x10000 < kmgr < 0x80000000 and k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(kmgr), km, 4, ctypes.byref(g)) and g.value == 4:
                                            v = struct.unpack("<I", km.raw)[0]
                                            if 0x10000 < v < 0x80000000:
                                                k32.WriteProcessMemory(
                                                    ctypes.c_void_p(h),
                                                    ctypes.c_void_p(0x898680),
                                                    struct.pack("<II", v, v), 8, None)
                                                ok2 = True
                                                break
                            if ok2:
                                print("  [kick] 已回填输入表0x898680")
                                tbl_filled = True
            stop_kick.wait(0.3)

    threading.Thread(target=kicker, daemon=True).start()

    # 开局前一次性把SELECT(3)踢回TITLE(2) — verify的硬性前置
    for _ in range(30):
        b = ctypes.create_string_buffer(1)
        g = ctypes.c_size_t()
        if k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(SCENE),
                                 b, 1, ctypes.byref(g)) and b.raw[0] == 2:
            break
        if b.raw and b.raw[0] == 3:
            k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(SCENE),
                                   b"\x02", 1, None)
        time.sleep(0.2)

    print("VS_COM开局: 灵梦 vs 灵梦(COM)...")
    inst.start_vs_com(CHAR_REIMU, CHAR_REIMU)
    # 注意: 不停kicker — 它还要在战斗开始(scene=5)时回填输入表
    print("收帧(首帧60s)...")
    t0 = time.time()
    frames = 0
    hold = False
    while time.time() - t0 < 30.0:
        try:
            left, right, weather, objs = inst.recv_frame(
                timeout=60.0 if frames == 0 else 2.0)
        except GameEnded as ge:
            print("对局结束: %s @帧%d" % (ge, frames))
            break
        except TimeoutError:
            print("超时@帧%d" % frames)
            break
        frames += 1
        if frames % 60 == 0:
            hold = not hold
        inst.send_inputs({"H": 1 if hold else -1}, {})
        if frames % 120 == 0:
            print("帧%d: L.hp=%s L.x=%.0f R.hp=%s obj=%d 天气=%s"
                  % (frames, left["hp"], left["position.x"], right["hp"],
                     len(objs), weather["active"]))
    print("共%d帧 (%.1f帧/秒)" % (frames, frames / max(0.1, time.time() - t0)))
    stop_kick.set()
    inst.close()
