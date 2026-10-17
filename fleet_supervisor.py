# -*- coding: utf-8 -*-
"""R56(fleet P1): fleet_supervisor — 车队监督器。

职责(scenario_b §3.5):
- actor/learner死亡重启(30s冷却+存活衰减+退出码语义)
- league分配器(每角色保底2-3 actor, 余量按league权重)
- 错峰boot(20s间隔)
- 停机卫生(Ctrl-C先停actor再join learner最后save)

用法: python fleet_supervisor.py [--actors 8]
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time

# 子进程用新进程组启动, 这样可发CTRL_BREAK_EVENT优雅停机(learner存档后再退)
CG = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
# R14(CPU红线<=75%, 用户明令): 全树低优先级(子进程继承), 用户态应用先行
PRIORITY = 0x4000  # BELOW_NORMAL_PRIORITY_CLASS
CPU_RED_LINE = 75.0
CPU_WINDOW = 6        # 滚动窗口: 近6次采样(3min)均值>红线才降容
# R75(2026-10-12全灭事故): 降容曾=del actor且无任何恢复路径 — 三actor
# 全灭后车队空转55min(learner无数据, A/B断流, 日志却显示"恢复走重启")。
# 降容语义改为**可恢复暂停**: 均值<回入场线持续满窗 → 恢复最早暂停的
# actor(一次一个); 滞后带[REENTER, RED_LINE]防抖动。
CPU_REENTER = 65.0
SUSPEND_MIN_S = 180.0


class CpuWatchdog:
    """R75: CPU红线降容/恢复策略(纯逻辑, tests/test_fleet_watchdog_r74钉死).

    - sample(cpu, now) → ('kill'|'resume'|None, avg): kill=应暂停一个
      actor(选哪个由调用方定, 通常最新), resume=可恢复一个; 两个判定都
      要求窗口满, 且降容判定后窗口重置(防连环杀/防抖);
    - suspend(key, now)/pop_resumable(now): 暂停簿记, 恢复取最早且
      已满SUSPEND_MIN_S的;
    - 全灭告警由调用方按 not actors and watchdog.suspended_at 触发。
    """

    def __init__(self, red_line=CPU_RED_LINE, reenter=CPU_REENTER,
                 window=CPU_WINDOW, min_suspend_s=SUSPEND_MIN_S):
        self.red_line = red_line
        self.reenter = reenter
        self.window = window
        self.min_suspend_s = min_suspend_s
        self.win = []
        self.suspended_at = {}
        self.avg = None

    def sample(self, cpu, now=0.0):
        """喂一次CPU采样(心跳节奏), 返回(决策, 均值)。

        P2修(从零#4, 震荡实测446次降容/恢复): ①cpu<0=查询失败哨兵
        (日志实证"均值-1%"入窗) — 拒收不入窗, 防假均值错误触发恢复;
        ②恢复须**连续两个满窗**低于回入场线(原单窗即恢复, 突发负载
        下快闪: 恢复→下一窗又降容的震荡环)。
        """
        self.avg = None
        if cpu is None or cpu < 0:
            return None, None
        self.win.append(cpu)
        if len(self.win) > self.window:
            self.win.pop(0)
        if len(self.win) < self.window:
            return None, None
        self.avg = sum(self.win) / len(self.win)
        if self.avg > self.red_line:
            self.win = []   # 降容判定后窗口重置: 新均值再判(防连环杀)
            self._calm = 0
            return 'kill', self.avg
        if self.avg < self.reenter:
            # 连续样本计数: 稳足2×窗宽(=连续两满窗均值都在场下)才恢复
            self._calm = getattr(self, '_calm', 0) + 1
            if self._calm >= 2 * self.window:
                self._calm = 0
                return 'resume', self.avg
            return None, self.avg
        self._calm = 0
        return None, self.avg

    def suspend(self, key, now):
        self.suspended_at[key] = now

    def pop_resumable(self, now):
        """返回最早且暂停已满min_suspend_s的key(无则None), 并移出簿记。"""
        for k in sorted(self.suspended_at, key=lambda x: self.suspended_at[x]):
            if now - self.suspended_at[k] >= self.min_suspend_s:
                del self.suspended_at[k]
                return k
        return None


_LOGICAL_CORES = os.cpu_count() or 1


def _wd_proc_rows(ps_out=None):
    """(pid, ppid, 累计CPU秒) 三元组 — 只取 python.exe / th123.exe。

    ps_out 仅供测试注入(免真实 PowerShell; 传 JSON 文本)。
    返回 None = 采样失败(看门狗哨兵, 不可当 0 用)。
    """
    if ps_out is None:
        try:
            out = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR "
                 "Name='th123.exe'\" | Select-Object ProcessId,"
                 "ParentProcessId,KernelModeTime,UserModeTime | "
                 "ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=25)
        except Exception:
            return None
        ps_out = out.stdout
    txt = (ps_out or '').strip()
    if not txt:
        return []
    try:
        data = json.loads(txt)
    except ValueError:
        return None
    if isinstance(data, dict):      # ConvertTo-Json 单元素返回对象而非数组
        data = [data]
    rows = []
    for d in data:
        if not isinstance(d, dict):
            continue
        try:
            # Win32_Process 的 KernelModeTime/UserModeTime 单位=100ns
            cpu = (float(d.get('KernelModeTime') or 0)
                   + float(d.get('UserModeTime') or 0)) / 1e7
            rows.append((int(d['ProcessId']), int(d['ParentProcessId']), cpu))
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def family_cpu_seconds(root_pid=None, ps_out=None):
    """训练族(本监督器进程树)累计CPU秒 — R14 的正确分子。

    P0-3(从零#5)口径修: 原 cpu_load_pct 取**整机**处理器利用率。实测整机
    100% 时 fleet 全家(3 learner+3 actor+监督器+3游戏)仅 ≈17% —— 旁路负载
    (ZCode会话/变异sweep/BC重建)被算成"训练负载", 看门狗据此杀 actor;
    而恢复线在旁路不退时永不满足 → 10-14 的"降容↔恢复"震荡(32min/8次)
    的真因。树口径还顺带把**对照臂**(另一 worktree/独立树)排除在外。
    """
    rows = _wd_proc_rows(ps_out)
    if rows is None:
        return None
    root = os.getpid() if root_pid is None else root_pid
    cpu_by_pid = {r[0]: r[2] for r in rows}
    kids = {}
    for pid, ppid, _c in rows:
        kids.setdefault(ppid, []).append(pid)
    seen, stack, total = set(), [root], 0.0
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        total += cpu_by_pid.get(p, 0.0)
        stack.extend(kids.get(p, ()))
    return total


_WD_CPU_LAST = {'ts': None, 'cpu': None, 'pct': None}


def cpu_load_pct(now=None, ps_out=None, cores=None, root_pid=None):
    """训练族CPU占用率(%) = Δ族累计CPU / (Δ墙钟 × 逻辑核数) × 100。

    首次调用返回 None(无 Δt), 采样失败返回 None(哨兵, CpuWatchdog
    拒收 — 见 sample() 的 cpu is None/负值语义)。
    root_pid/ps_out/cores 仅测试注入(生产一律默认: 本监督器进程树)。
    """
    now = time.time() if now is None else now
    cur = family_cpu_seconds(root_pid=root_pid, ps_out=ps_out)
    if cur is None:
        return None
    prev_ts, prev_cpu = _WD_CPU_LAST['ts'], _WD_CPU_LAST['cpu']
    _WD_CPU_LAST['ts'], _WD_CPU_LAST['cpu'] = now, cur
    if prev_ts is None or now <= prev_ts:
        return None
    pct = (cur - prev_cpu) / ((now - prev_ts) * (cores or _LOGICAL_CORES)) * 100.0
    pct = max(0.0, min(100.0, pct))   # 进程退出致 Δ<0 / 越界都不得入窗
    _WD_CPU_LAST['pct'] = pct
    return pct

HERE = os.path.dirname(os.path.abspath(__file__))
# 首跑缺陷(2026-10-06点火): 本机解释器safe-path模式(sys.path[0]=
# python312.zip而非脚本目录) — actor_worker/learner_hub均有此自救,
# 唯supervisor缺(从未真实跑过的集成缝)。局部import portmap即炸。
sys.path.insert(0, HERE)
PY = sys.executable
# P1-D(从零#2): STORE原未定义 — 监督循环首个league周期(3600s)引用
# 即NameError杀死监督器(全部子进程成孤儿)。统一模块级定义。
STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
LOCK = os.path.join(STORE, 'fleet.lock')
SUPERVISION_LOG = os.path.join(STORE, 'fleet_supervision.log')
# C1-1(未决方案§C): 墙钟心跳 — 把'深夜无日志全灭'从推断变为账目
HEARTBEAT = os.path.join(STORE, 'fleet_heartbeat')
HEARTBEAT_EVERY = 3   # 每3个监督循环(30s)写一次


def write_heartbeat(alert=None):
    """P0(从零#4): alert≠None时同步写异常标记文件(耗尽减员等事故),
    恢复调用(alert=None)清除 — 主时间戳格式不变(offline-gap读数兼容)。"""
    try:
        tmp = HEARTBEAT + '.tmp'
        with open(tmp, 'w') as f:
            f.write(str(time.time()))
        os.replace(tmp, HEARTBEAT)
        ap = HEARTBEAT + '.alert'
        if alert:
            with open(ap, 'w') as f:
                f.write('%s %s' % (time.strftime('%m-%d %H:%M:%S'), alert))
        elif os.path.exists(ap):
            os.remove(ap)
    except OSError:
        pass


# P0-3存活自检(从零#5): 心跳主文件内容格式**不变**(离线gap读数依赖
# float(...)), 看门狗存活证据走独立 sidecar。消费方: tools/status_dashboard.py
WD_STATUS = HEARTBEAT + '.wd'


def write_watchdog_status(pct, now=None):
    """写看门狗存活+读数 sidecar(`<ts> <pct|->`)。

    动机(从零#5 P0-3): 看门狗曾是"制度写着、代码不执行"两天无人察觉。
    每次采样都留痕(含 pct=None 的失败采样) — 文件停更即证据。
    """
    now = time.time() if now is None else now
    try:
        tmp = WD_STATUS + '.tmp'
        with open(tmp, 'w', encoding='utf8') as f:
            f.write('%.3f %s\n' % (now, '-' if pct is None else '%.2f' % pct))
        os.replace(tmp, WD_STATUS)
    except OSError:
        pass


def report_offline_gap():
    """启动时读上次心跳 → 间隙>90s=离线时段(睡眠/关机/灭队), 入账。"""
    try:
        last = float(open(HEARTBEAT).read().strip())
    except (OSError, ValueError):
        return
    gap = time.time() - last
    if gap > 90:
        log('离线时段报告: 上次心跳 %s → 本次启动, 间隔 %.1fh '
            '(主机睡眠/关机或灭队 — C1-1记账)'
            % (time.strftime('%m-%d %H:%M:%S', time.localtime(last)),
               gap / 3600.0))

CHARS = ('reimu', 'marisa', 'suika')   # 主角色(有learner); D3'(R65): --focus可配
# D3'(R65): league对手周期 — 主角色块×LEAGUE_FOCUS_WEIGHT + 全量league角色
# + COM(份额推导见league.league20_opps docstring)。
LEAGUE_FOCUS_WEIGHT = 3
STAGGER_S = 20
MAX_RESTARTS = 20
# P1-7(从零#5): 重启预算**按窗口衰减** — 原 restarts 终身累计
# (20 次崩溃即永久减员, 与"偶发崩溃是常态"相悖)。窗口内无重启
# 则计数折半, 连续两个窗口无重启清零。
RESTART_DECAY_S = 1800.0


def restart_budget(restarts, last_restart, now=None, window=RESTART_DECAY_S):
    """重启预算按窗口衰减 → 新计数dict(**不改入参**)。

    P1-7(从零#5): 原 restarts 终身累计 — 20 次崩溃即永久减员, 且重启预算
    是最容易被"偶发崩溃堆积"误伤的机制。语义:
      · 该 key 上次重启距今 ≤ window  → 计数保持;
      · > window(窗口内无重启)        → 折半(连续两窗无重启自然清零);
      · 未重启过(last=0)              → 保持(0 恒为 0)。
    """
    now = time.time() if now is None else now
    out = {}
    for k, n in restarts.items():
        last = last_restart.get(k, 0.0)
        out[k] = (int(n) // 2) if (n and last and now - last > window) else int(n)
    return out
COOLDOWN_S = 30
LEAGUE_INTERVAL = 3600  # league重分配周期(秒)
# R63(P1-5): actor局预算 — supervisor的actor是**长期生产者**, 原不传
# --episodes 而 actor_worker 默认1000局, 跑满即 exit 0 → 被下面判为
# "正常完成"永久移出车队 → 车队静默排空到零actor(learner永远空转)。
# 传一个实质无界的预算 + 语义修正(见监督循环)双保险。
ACTOR_EPISODES = 1000000


def log(msg):
    """监督日志 — P1-8(从零#5): 写盘失败**不得**掀翻监督器。

    原实现 open(append) 裸抛: 盘满/被占用/杀软占用 → 异常穿出主循环 →
    `finally` 只删锁, 不走 _clean_shutdown → learner/actor/游戏全成孤儿
    (监督日志 16:51 有"孤儿回收 PID=19136"前例)。
    """
    line = '[%s] %s' % (time.strftime('%m-%d %H:%M:%S'), msg)
    print(line, flush=True)
    try:
        with open(SUPERVISION_LOG, 'a', encoding='utf8') as f:
            f.write(line + '\n')
    except OSError as _e:
        print('[log] 监督日志写失败(%r) — 仅控制台' % (_e,), flush=True)


def league_alloc(n_actors, chars=CHARS, stats=None):
    """分配actor到主角色(有learner的角色位)。和恒=n_actors。

    D3'(R65)泛化: 原硬编码3角色(n//3), 现 n//len(chars) 均分+余量按
    league权重(本角色胜率低=更需练习位)。3角色3actor时与原行为逐位相等
    (回归锚); chars数>actor数时base=0由余量轮转兜底(每角色至少有机会)。
    """
    n = len(chars)
    alloc = {ch: n_actors // n for ch in chars}
    rem = n_actors - sum(alloc.values())
    order = list(chars)
    if rem > 0 and stats:
        # league权重: 本角色胜率越低 → 越需要actor(练习位)
        weights = []
        for ch in chars:
            w_total = 0
            n_total = 0
            for label, (w, l) in stats.items():
                if label.startswith(ch + '@'):
                    w_total += w
                    n_total += w + l
            wr = w_total / max(n_total, 1)
            weights.append((ch, (1 - wr) ** 1.5))
        weights.sort(key=lambda x: -x[1])
        order = [ch for ch, _ in weights]
    for i in range(rem):
        alloc[order[i % len(order)]] += 1
    return alloc


def aggregate_stats(fleet_dir):
    """R57(2.6): 聚合各actor scratch/stats.json → league_alloc可用的
    {label: [wins, losses]}(label=char@对手)。读不到/损坏返回None
    (league退化为均分, 不崩 — 第十八轮2.6的降级语义)。"""
    import glob
    import json as _json
    stats = {}
    try:
        for p in glob.glob(os.path.join(
                fleet_dir, 'scratch_actor*', 'stats.json')):
            try:
                with open(p, encoding='utf8') as f:
                    d = _json.load(f)
                for lab, wl in (d.get('opp_stats') or {}).items():
                    w0, l0 = stats.get(lab, (0, 0))
                    stats[lab] = (w0 + int(wl[0]), l0 + int(wl[1]))
            except (OSError, ValueError, IndexError, TypeError):
                continue
    except OSError:
        return None
    return stats or None


def _kill_tree(pid):
    """R63(P1-5): 连同**子进程**一起终结(Windows)。

    原实现只 `os.kill(pid,9)` 杀 worker, 而 worker 用 subprocess.Popen
    直接拉起 th123.exe(soku_client2.py:115, 无job object) → 游戏成孤儿,
    **继续占住监听端口**; portmap 随后把同一端口发给重启后的 actor,
    形成"旧游戏还在听/新actor连上旧游戏"的风险(portmap.py:3-5 明确把
    静默双绑列为已知风险)。taskkill /T 杀整棵树可一次解决。
    失败时退回单进程 kill(不改变原有语义)。
    """
    if os.name == 'nt':
        try:
            r = subprocess.run(['taskkill', '/F', '/T', '/PID', str(int(pid))],
                               capture_output=True, text=True, timeout=20)
            if r.returncode == 0:
                return True
        except Exception:
            pass
    try:
        os.kill(int(pid), 9)
        return True
    except OSError:
        return False


def reap_orphans():
    """R61f(F3/D5): 启动时回收孤儿 — 上次supervisor被强杀时其子进程
    (actor_worker/learner_hub)可能残留(占游戏实例+learner双写者由
    R61e单实例锁兜底)。按WMI ParentProcessId判定: 父进程已死=孤儿。
    R63(P1-5): 改整树终结(taskkill /T) — 否则游戏子进程残留占端口。"""
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" "
         "| Where-Object { $_.CommandLine -match "
         "'actor_worker|learner_hub|exploiter' } "
         "| ForEach-Object { '{0}|{1}' -f $_.ProcessId, $_.ParentProcessId }"],
        capture_output=True, text=True, timeout=30)
    live = {os.getpid()}   # P1-D belt-and-braces: 本进程入存活集 —
    workers = []           # 即便reap被误置于boot后, 车队之父(本进程)也算活
    for line in (out.stdout or '').strip().splitlines():
        try:
            pid_s, ppid_s = line.strip().split('|')
            pid, ppid = int(pid_s), int(ppid_s)
        except ValueError:
            continue
        live.add(pid)
        workers.append((pid, ppid))
    n = 0
    for pid, ppid in workers:
        if pid == os.getpid() or ppid in live:
            continue          # 自己/父仍在(受管或属本会话) — 不碰
        if _kill_tree(pid):
            n += 1
            log('孤儿回收: PID=%d(父%d已死, 含游戏子树)' % (pid, ppid))
    return n


def _spawn_actor(ch, aid, port, opp_specs, tps=480):
    """启动一个actor(boot与重启共用同一构造 — 防双拷贝漂移)。

    D3'(R65): opp_specs=league20_opps产物(20角色对手周期), 显式--opp
    下发(与actor_worker独立运行时的默认构建同源)。
    """
    from portmap import fleet_port
    cmd = [PY, '-X', 'utf8', '-u', 'actor_worker.py',
           '--char', ch, '--actor', str(aid),
           '--port', str(port),
           '--tps', str(tps),
           '--episodes', str(ACTOR_EPISODES)]
    for spec in opp_specs:
        cmd += ['--opp', spec]
    # P2(审计#3): 原日志fd内联在Popen里永不关(重启风暴泄漏句柄)
    try:
        _lf = open(r'D:\temp\actor_%s_%d.log' % (ch, aid),
                   'a', encoding='utf8')
    except OSError as _e:
        # P1-8(从零#5): 日志档打不开不该等于**该 actor 起不来** —
        # 回落 DEVNULL 继续拉人(原异常穿出主循环=整队孤儿)。
        print('[spawn] actor日志打开失败(%r) — 回落DEVNULL' % (_e,),
              flush=True)
        _lf = subprocess.DEVNULL
    p = subprocess.Popen(
        cmd, cwd=HERE, creationflags=CG | PRIORITY,
        stdout=_lf, stderr=subprocess.STDOUT)
    if _lf is not subprocess.DEVNULL:
        _lf.close()   # 子进程已继承句柄, 父侧关闭不影响子进程写
    return p


def _clean_shutdown(actors, learners):
    """停机卫生(D5从零#2收尾; C1-2窗口尾共用): 先actor(CTRL_BREAK→
    优雅退出, 释放游戏/episode写盘), 再learner(存档后退出) — 原两批
    同时发信号, actor慢退出期间learner已可能重发布/竞争。"""
    for p in list(actors.values()):
        try:
            p.send_signal(signal.CTRL_BREAK_EVENT)
        except OSError:
            pass
    for p in list(actors.values()):
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _kill_tree(p.pid)
    for p in list(learners.values()):
        try:
            p.send_signal(signal.CTRL_BREAK_EVENT)
        except OSError:
            pass
    for p in list(learners.values()):
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _kill_tree(p.pid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--actors', type=int, default=8)
    ap.add_argument('--focus', default=','.join(CHARS),
                    help='主角色位(有learner, 逗号分隔; 默认%s)'
                         % ','.join(CHARS))
    ap.add_argument('--hours', default=None,
                    help='运营窗口 START-END 如 9:00-23:00(C1-2: 窗口尾干净收队)')
    ap.add_argument('--tps', type=int, default=480,
                    help='actor游戏tps(R14红线降载: 360≈75%%功耗)')
    ap.add_argument('--league-weight', type=int, default=LEAGUE_FOCUS_WEIGHT,
                    help='对手周期中主角色块倍率(D3\')')
    args = ap.parse_args()
    n_actors = args.actors
    chars = tuple(c.strip() for c in args.focus.split(',') if c.strip())

    # D3'(R65): 20角色league对手周期(单源构建器, actor_worker默认同源)
    from league import league20_opps
    opp_specs = league20_opps(None, focus=chars, weight=args.league_weight)
    log('league对手周期: %d位(主角色块×%d+league%d+COM) %s...'
        % (len(opp_specs), args.league_weight,
           len(opp_specs) - len(chars) * args.league_weight - 1,
           '+'.join(opp_specs[:6])))

    actors = {}   # (char, actor_id) -> proc
    learners = {}  # char -> proc

    # 单实例锁
    if os.path.exists(LOCK):
        try:
            old = open(LOCK).read().strip()
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, int(old))
            if h:
                k32.CloseHandle(h)
                # R67b(2026-10-12 PID复用防御, 与learner锁同款): OpenProcess
                # 对任何占用该PID的进程都成功 — 被灭supervisor的PID被无关
                # 进程回收 → 误判双开退出(实证: 10-12 10:42只打出周期行即
                # 消失, 剩剥削者孤儿)。命令行校验: 真supervisor才拒双开。
                import subprocess as _sp
                _cmd = _sp.run(
                    ['powershell', '-NoProfile', '-Command',
                     "(Get-CimInstance Win32_Process -Filter "
                     "'ProcessId=%d').CommandLine" % int(old)],
                    capture_output=True, text=True, timeout=20)
                if 'fleet_supervisor' in (_cmd.stdout or ''):
                    print("已有fleet_supervisor在跑(PID=%s) — 拒绝双开" % old)
                    sys.exit(1)
                print("锁PID%s已被无关进程复用 — 清锁续启" % old)
        except (ValueError, OSError):
            pass
        os.remove(LOCK)
    fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)

    # P1-D(从零#2): 孤儿回收必须**先于boot** — 原放在boot之后, WMI匹配
    # 不到supervisor自身(命令行是fleet_supervisor不在存活集) → 新拉起的
    # actor/learner的父(=本进程)被判死 → 启动后杀光自己的车队。
    # 前置后: 回收时本进程尚无子进程, 只清上次强杀的残留。
    try:
        _orphans = reap_orphans()
        if _orphans:
            log('启动前回收孤儿%d个' % _orphans)
    except Exception as e:
        log('孤儿回收异常(%s) — 继续boot(锁与单实例锁兜底)' % e)

    try:
        # league分配
        alloc = league_alloc(n_actors, chars)
        log('league分配: %s (共%d actor)' % (alloc, sum(alloc.values())))

        # 启动learner(每角色一个, 先启动)
        for ch in chars:
            cmd = [PY, '-X', 'utf8', '-u', 'learner_hub.py',
                   '--char', ch]
            p = subprocess.Popen(cmd, cwd=HERE, creationflags=CG | PRIORITY,
                                 stdout=open(
                                     r'D:\temp\learner_%s.log' % ch,
                                     'a', encoding='utf8'),
                                 stderr=subprocess.STDOUT)
            learners[ch] = p
            log('启动 learner_%s PID=%d' % (ch, p.pid))
            time.sleep(5)

        # 错峰启动actor
        from portmap import fleet_port
        actor_id = 0
        for ch, count in alloc.items():
            for i in range(count):
                port = fleet_port(actor_id)
                p = _spawn_actor(ch, actor_id, port, opp_specs,
                                args.tps)
                actors[(ch, actor_id)] = p
                log('启动 actor_%s_%d PID=%d port=%d' % (
                    ch, actor_id, p.pid, port))
                actor_id += 1
                time.sleep(STAGGER_S)

        log('全部启动 — 监督模式')

        # 监督循环
        restarts = {k: 0 for k in list(actors) + [
            ('learner', ch) for ch in chars]}
        _last_restart = {}   # P1-7: key→上次重启时刻(衰减窗口用)
        last_league = time.time()
        report_offline_gap()
        _hb = 0
        _wd = CpuWatchdog()
        _last_alarm = 0.0
        # C1-2(用户裁定①窗口制): 窗口尾干净收队 — 任务计划程序负责窗口头
        win_end = None
        if args.hours:
            try:
                _h, _m = args.hours.split('-')[1].split(':')
                win_end = (int(_h) * 60 + int(_m)) * 60
            except (ValueError, IndexError):
                log('窗口参数无法解析(%r) — 忽略' % args.hours)
        _exhausted = set()   # P0(从零#4): 重启耗尽减员账(告警重播源)
        while actors or learners:
            time.sleep(10)
            if win_end is not None:
                _now = time.localtime()
                _now_s = _now.tm_hour * 3600 + _now.tm_min * 60 + _now.tm_sec
                if _now_s >= win_end:
                    log('运营窗口尾(%s) — 干净收队(learner存档→actor退出)'
                        % args.hours)
                    _clean_shutdown(actors, learners)
                    break
            _hb += 1
            # P1-7(从零#5): alert 文本一次算好, 循环内所有心跳调用都带上 —
            # 原重启路径的无参 write_heartbeat() 会把减员告警**自己清掉**,
            # 且该文件当时**无任何读者**(写而不读=假账)。
            _alert_txt = ('restart_exhausted:%s'
                          % ','.join(sorted(map(str, _exhausted)))
                          ) if _exhausted else None
            if _hb % HEARTBEAT_EVERY == 0:
                write_heartbeat(alert=_alert_txt)
            # P0: 耗尽减员节流重播(每18循环≈3min) — 静默事故不再
            if _exhausted and _hb % 18 == 0:
                log('!!ALERT!! 车队减员在案: %s (需人工介入)'
                    % sorted(map(str, _exhausted)))
            # P0-3修(从零#5): CPU看门狗移出_exhausted守卫 — 原版把
            # _wd.sample圈在耗尽分支内, 正常运行时CPU策略从不执行
            # (红线R14两日死代码). 现每心跳(30s)采样一次.
            if _hb % HEARTBEAT_EVERY == 0:
                _cpu = cpu_load_pct()          # 训练族口径(见 family_cpu_seconds)
                write_watchdog_status(_cpu)    # 存活证据(消费方=status_dashboard)
                # R75: 策略在CpuWatchdog(纯逻辑), 进程管理在此。
                # 降容=可恢复暂停(非移除) — 全灭事故修正。
                _dec, _avg = _wd.sample(_cpu, time.time())
                if _dec == 'kill' and actors:
                    _k = sorted(actors)[-1]
                    log('CPU红线降容: 均值%.0f%% — 暂停 %s (均值<%d%%'
                        '满窗后恢复)' % (_avg, str(_k), CPU_REENTER))
                    _kill_tree(actors[_k].pid)
                    del actors[_k]
                    _wd.suspend(_k, time.time())
                elif _dec == 'resume' and _wd.suspended_at:
                    _k = _wd.pop_resumable(time.time())
                    if _k is not None:
                        ch, aid = _k
                        p2 = _spawn_actor(ch, aid, fleet_port(aid),
                                          opp_specs, args.tps)
                        actors[_k] = p2
                        log('CPU恢复(均值%.0f%%) — 重启 %s PID=%d'
                            % (_avg, str(_k), p2.pid))
                # 全灭告警: 10min周期(一次性首报+周期状态 — 今日事故
                # 形态下必须显眼, 不能只靠人翻日志发现空转)
                if not actors and _wd.suspended_at and \
                        time.time() - _last_alarm > 600:
                    _last_alarm = time.time()
                    log('[告警] 车队actor全灭(降容) — 均值%.0f%% '
                        '恢复线%d%% 暂停中:%s' % (
                            _wd.avg if _wd.avg is not None else -1,
                            CPU_REENTER,
                            sorted(_wd.suspended_at)))
            # R57(2.6): league周期重算 — 聚合actor stats重定余量分配
            # (只影响未来重启的actor, 运行中的actor不中断)
            if time.time() - last_league > LEAGUE_INTERVAL:
                last_league = time.time()
                st = aggregate_stats(os.path.join(STORE, 'fleet'))
                try:
                    from league import league_report
                    log('league重算: %s' % (league_report(st) if st
                                            else '无stats → 维持现分配'))
                except ImportError:
                    log('league重算: stats=%s' % (st is not None,))
            # actor检查
            for key in list(actors):
                p = actors[key]
                if p.poll() is None:
                    continue
                if p.returncode in (0, 130):
                    # R63(P1-5): actor跑满预算/被中断 = 仍是**生产者退出**,
                    # 必须重启而不是移出车队(原语义"不重启"→车队静默排空;
                    # 配合ACTOR_EPISODES实质无界, 此路径近乎不可达, 但语义
                    # 必须正确: 车队排空后 while actors or learners 会
                    # 永久空转且看起来健康)。
                    log('%s 正常完成(code=%d) — 视为生产者退出, 重启' % (
                        key, p.returncode))
                ch, aid = key
                rk = restarts.get(key, 0)
                # P1-7: 窗口内无重启 → 预算折半(偶发崩溃不再终身记账)
                _dec = restart_budget({key: rk}, _last_restart)[key]
                if _dec != rk:
                    rk = restarts[key] = _dec
                if rk >= MAX_RESTARTS:
                    # P0(从零#4, bug_restart_exhaust_silent): 耗尽=事故
                    # 不是静默减员 — 原仅del无告警, marisa缺员1.6h无人
                    # 察觉。ALERT级+心跳异常标记+主循环节流重播。
                    log('!!ALERT!! %s 重启耗尽(%d次) — 车队永久减员, '
                        '需人工介入(查该actor日志定位根因)' % (
                            str(key), rk))
                    _exhausted.add(key)
                    write_heartbeat(
                        alert='restart_exhausted:%s' % str(key))
                    del actors[key]
                    continue
                log('%s 退出(code=%s) — %ds后重启' % (
                    str(key), p.returncode, COOLDOWN_S))
                # P2(审计#3): 重启风暴时N×30s阻塞主循环>心跳窗(90s)
                # → 假离线账 — 冷却期照写心跳
                write_heartbeat(alert=_alert_txt)
                time.sleep(COOLDOWN_S)
                p2 = _spawn_actor(ch, aid, fleet_port(aid), opp_specs,
                                 args.tps)
                actors[key] = p2
                restarts[key] = rk + 1
                _last_restart[key] = time.time()   # P1-7: 衰减窗口起点
                log('%s 已重启 PID=%d' % (str(key), p2.pid))

            # learner检查
            for ch in list(learners):
                p = learners[ch]
                if p.poll() is None:
                    continue
                # R60(F-2): 重启上限(原无上限无条件拉起 — 疯狂循环风险)
                rk = restarts.get(('learner', ch), 0)
                if rk >= MAX_RESTARTS:
                    log('learner_%s 重启耗尽(%d次) — 放弃' % (ch, rk))
                    del learners[ch]
                    continue
                log('learner_%s 退出(code=%s) — 重启' % (ch, p.returncode))
                cmd = [PY, '-X', 'utf8', '-u', 'learner_hub.py',
                       '--char', ch]
                p2 = subprocess.Popen(
                    cmd, cwd=HERE, creationflags=CG | PRIORITY,
                    stdout=open(
                        r'D:\temp\learner_%s.log' % ch,
                        'a', encoding='utf8'),
                    stderr=subprocess.STDOUT)
                learners[ch] = p2
                restarts[('learner', ch)] = rk + 1
                _last_restart[('learner', ch)] = time.time()

        log('全部结束')

    except KeyboardInterrupt:
        log('中断 — 先停actor等待退出, 再停learner')
        _clean_shutdown(actors, learners)

    except Exception as _fatal:
        # P1-8(从零#5): 任何未预期异常都必须**先收队再抛** — 原只删锁,
        # learner/actor/游戏全成孤儿(监督日志有"孤儿回收 PID=19136"前例)。
        log('!!监督器异常退出(%r) — 先干净收队再抛(防整队孤儿)' % (_fatal,))
        try:
            _clean_shutdown(actors, learners)
        except Exception as _e2:
            log('收队期间异常(%r) — 继续抛出原错' % (_e2,))
        raise

    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


if __name__ == '__main__':
    main()
