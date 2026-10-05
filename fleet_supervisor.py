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

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
LOCK = os.path.join(os.environ.get('TH123_STORE',
                                  r'D:\temp\th123_models'), 'fleet.lock')
SUPERVISION_LOG = os.path.join(
    os.environ.get('TH123_STORE', r'D:\temp\th123_models'),
    'fleet_supervision.log')

CHARS = ('reimu', 'marisa', 'suika')
STAGGER_S = 20
MAX_RESTARTS = 20
COOLDOWN_S = 30
LEAGUE_INTERVAL = 3600  # league重分配周期(秒)


def log(msg):
    line = '[%s] %s' % (time.strftime('%m-%d %H:%M:%S'), msg)
    print(line, flush=True)
    with open(SUPERVISION_LOG, 'a', encoding='utf8') as f:
        f.write(line + '\n')


def league_alloc(n_actors, stats=None):
    """分配actor到角色。和恒=n_actors; n≥6时每角色保底2, 余量按
    league权重(胜率低=更需练习的对手位); n<6时均分+余量轮转。"""
    alloc = {ch: n_actors // 3 for ch in CHARS}
    rem = n_actors - sum(alloc.values())
    order = list(CHARS)
    if rem > 0 and stats:
        # league权重: 本角色胜率越低 → 越需要actor(练习位)
        weights = []
        for ch in CHARS:
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


def reap_orphans():
    """R61f(F3/D5): 启动时回收孤儿 — 上次supervisor被强杀时其子进程
    (actor_worker/learner_hub)可能残留(占游戏实例+learner双写者由
    R61e单实例锁兜底)。按WMI ParentProcessId判定: 父进程已死=孤儿。"""
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" "
         "| Where-Object { $_.CommandLine -match 'actor_worker|learner_hub' } "
         "| ForEach-Object { '{0}|{1}' -f $_.ProcessId, $_.ParentProcessId }"],
        capture_output=True, text=True, timeout=30)
    live = set()
    workers = []
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
        try:
            os.kill(pid, 9)
            n += 1
            log('孤儿回收: PID=%d(父%d已死)' % (pid, ppid))
        except OSError:
            pass
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--actors', type=int, default=8)
    args = ap.parse_args()
    n_actors = args.actors

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
                print("已有fleet_supervisor在跑(PID=%s) — 拒绝双开" % old)
                sys.exit(1)
        except (ValueError, OSError):
            pass
        os.remove(LOCK)
    fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)

    try:
        # league分配
        alloc = league_alloc(n_actors)
        log('league分配: %s (共%d actor)' % (alloc, sum(alloc.values())))

        # 启动learner(每角色一个, 先启动)
        for ch in CHARS:
            cmd = [PY, '-X', 'utf8', '-u', 'learner_hub.py',
                   '--char', ch]
            p = subprocess.Popen(cmd, cwd=HERE, creationflags=CG,
                                 stdout=open(
                                     r'D:\temp\learner_%s.log' % ch,
                                     'a', encoding='utf8'),
                                 stderr=subprocess.STDOUT)
            learners[ch] = p
            log('启动 learner_%s PID=%d' % (ch, p.pid))
            time.sleep(5)

        # 错峰启动actor
        actor_id = 0
        for ch, count in alloc.items():
            for i in range(count):
                from portmap import fleet_port
                port = fleet_port(actor_id)
                cmd = [PY, '-X', 'utf8', '-u', 'actor_worker.py',
                       '--char', ch, '--actor', str(actor_id),
                       '--port', str(port)]
                p = subprocess.Popen(
                    cmd, cwd=HERE, creationflags=CG,
                    stdout=open(
                        r'D:\temp\actor_%s_%d.log' % (ch, actor_id),
                        'a', encoding='utf8'),
                    stderr=subprocess.STDOUT)
                actors[(ch, actor_id)] = p
                log('启动 actor_%s_%d PID=%d port=%d' % (
                    ch, actor_id, p.pid, port))
                actor_id += 1
                time.sleep(STAGGER_S)

        # R61f: 上次强杀残留的孤儿回收(在boot前 — 释放游戏实例/端口)
        _orphans = reap_orphans()
        if _orphans:
            log('启动前回收孤儿%d个' % _orphans)
        log('全部启动 — 监督模式')

        # 监督循环
        restarts = {k: 0 for k in list(actors) + [
            ('learner', ch) for ch in CHARS]}
        last_league = time.time()
        while actors or learners:
            time.sleep(10)
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
                    log('%s 正常完成(code=%d) — 不重启' % (key, p.returncode))
                    del actors[key]
                    continue
                ch, aid = key
                rk = restarts.get(key, 0)
                if rk >= MAX_RESTARTS:
                    log('%s 重启耗尽 — 放弃' % str(key))
                    del actors[key]
                    continue
                log('%s 退出(code=%s) — %ds后重启' % (
                    str(key), p.returncode, COOLDOWN_S))
                time.sleep(COOLDOWN_S)
                from portmap import fleet_port
                port = fleet_port(aid)
                cmd = [PY, '-X', 'utf8', '-u', 'actor_worker.py',
                       '--char', ch, '--actor', str(aid),
                       '--port', str(port)]
                p2 = subprocess.Popen(
                    cmd, cwd=HERE, creationflags=CG,
                    stdout=open(
                        r'D:\temp\actor_%s_%d.log' % (ch, aid),
                        'a', encoding='utf8'),
                    stderr=subprocess.STDOUT)
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
                    cmd, cwd=HERE, creationflags=CG,
                    stdout=open(
                        r'D:\temp\learner_%s.log' % ch,
                        'a', encoding='utf8'),
                    stderr=subprocess.STDOUT)
                learners[ch] = p2
                restarts[('learner', ch)] = rk + 1

        log('全部结束')

    except KeyboardInterrupt:
        # 停机卫生: 先actor(CTRL_BREAK→优雅退出), 等待, 再learner(存档), 强杀兜底
        log('中断 — 先停actor再停learner')
        for p in list(actors.values()) + list(learners.values()):
            try:
                p.send_signal(signal.CTRL_BREAK_EVENT)
            except OSError:
                pass
        for p in list(actors.values()) + list(learners.values()):
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


if __name__ == '__main__':
    main()
