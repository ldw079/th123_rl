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


def cpu_load_pct():
    try:
        out = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             '(Get-CimInstance Win32_Processor | '
             'Measure-Object -Property LoadPercentage -Average)'
             '.Average'],
            capture_output=True, text=True, timeout=20)
        return float(out.stdout.strip())
    except Exception:
        return None

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


def write_heartbeat():
    try:
        tmp = HEARTBEAT + '.tmp'
        with open(tmp, 'w') as f:
            f.write(str(time.time()))
        os.replace(tmp, HEARTBEAT)
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
COOLDOWN_S = 30
LEAGUE_INTERVAL = 3600  # league重分配周期(秒)
# R63(P1-5): actor局预算 — supervisor的actor是**长期生产者**, 原不传
# --episodes 而 actor_worker 默认1000局, 跑满即 exit 0 → 被下面判为
# "正常完成"永久移出车队 → 车队静默排空到零actor(learner永远空转)。
# 传一个实质无界的预算 + 语义修正(见监督循环)双保险。
ACTOR_EPISODES = 1000000


def log(msg):
    line = '[%s] %s' % (time.strftime('%m-%d %H:%M:%S'), msg)
    print(line, flush=True)
    with open(SUPERVISION_LOG, 'a', encoding='utf8') as f:
        f.write(line + '\n')


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
         "| Where-Object { $_.CommandLine -match 'actor_worker|learner_hub' } "
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
    p = subprocess.Popen(
        cmd, cwd=HERE, creationflags=CG | PRIORITY,
        stdout=open(r'D:\temp\actor_%s_%d.log' % (ch, aid),
                    'a', encoding='utf8'),
        stderr=subprocess.STDOUT)
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
        last_league = time.time()
        report_offline_gap()
        _hb = 0
        _cpu_win = []
        # C1-2(用户裁定①窗口制): 窗口尾干净收队 — 任务计划程序负责窗口头
        win_end = None
        if args.hours:
            try:
                _h, _m = args.hours.split('-')[1].split(':')
                win_end = (int(_h) * 60 + int(_m)) * 60
            except (ValueError, IndexError):
                log('窗口参数无法解析(%r) — 忽略' % args.hours)
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
            if _hb % HEARTBEAT_EVERY == 0:
                write_heartbeat()
                _cpu = cpu_load_pct()
                if _cpu is not None:
                    # R68b: 滚动均值判降容 — 原连续strike+双低复位在
                    # 震荡负载下永不触发(实测14:16-14:22连续82-99%仅到
                    # strike2即被复位)。近CPU_WINDOW次采样均值>红线即降,
                    # 单次深蹲只稀释均值不复位 — 红线的忠实执行。
                    _cpu_win.append(_cpu)
                    if len(_cpu_win) > CPU_WINDOW:
                        _cpu_win.pop(0)
                    _avg = sum(_cpu_win) / len(_cpu_win)
                    if _avg > CPU_RED_LINE and len(_cpu_win) >= CPU_WINDOW                             and actors:
                        _k = sorted(actors)[-1]
                        log('CPU红线降容: 均值%.0f%%(近%d采样) — 停 %s '
                            '(杀最新actor, 恢复走重启)'
                            % (_avg, len(_cpu_win), str(_k)))
                        _kill_tree(actors[_k].pid)
                        del actors[_k]
                        _cpu_win = []
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
                if rk >= MAX_RESTARTS:
                    log('%s 重启耗尽 — 放弃' % str(key))
                    del actors[key]
                    continue
                log('%s 退出(code=%s) — %ds后重启' % (
                    str(key), p.returncode, COOLDOWN_S))
                time.sleep(COOLDOWN_S)
                p2 = _spawn_actor(ch, aid, fleet_port(aid), opp_specs,
                                 args.tps)
                actors[key] = p2
                restarts[key] = rk + 1
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

        log('全部结束')

    except KeyboardInterrupt:
        log('中断 — 先停actor等待退出, 再停learner')
        _clean_shutdown(actors, learners)

    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


if __name__ == '__main__':
    main()
