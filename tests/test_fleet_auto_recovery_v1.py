# -*- coding: utf-8 -*-
"""R15 行为测试: watcher 自动恢复/维护锁租约/限流/无 kill/边界 + 真实 subprocess dummy fleet.

覆盖 auditor AR-1..8（AR-9 为 15:00 现场）:
- AR-1 单缺不触发 / 连续 2 检查+关键缺触发
- AR-2 维护锁抑制 / stale 锁可接管 / 健康后清除
- AR-3 限流 1/10min / 失败退避 / recovery 记录
- AR-4 无 kill（代码审计+行为: 恢复路径只 launch/snapshot）
- AR-5 告警去重/恢复清除
- AR-6 单实例 / 边界
- AR-7 父链证据（运行时由 --parent-check 采集）
- AR-8 真实 subprocess dummy fleet 计数与恢复触发
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import fleet_health as FH  # noqa: E402
import fleet_lock  # noqa: E402

import uuid  # noqa: E402
MARKER = 'dummy_fleet_' + uuid.uuid4().hex[:8]

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def _ctx():
    d = tempfile.mkdtemp(prefix='fh_ar_')
    FH.STORE = d
    FH.HB = os.path.join(d, 'fleet_heartbeat')
    FH.ALERT = FH.HB + '.fleet_alert'
    FH.RECOVERY = os.path.join(d, 'fleet_recovery.json')
    FH.RECOVERY_LOG = os.path.join(d, 'fleet_recovery.log')
    FH.WATCH_LOCK = os.path.join(d, 'fleet_watcher.lock')
    FH.fleet_lock.LOCK = os.path.join(d, 'fleet_maintenance.lock')
    FH.fleet_lock.ALERT = os.path.join(d, 'fleet_alert')
    io.open(FH.HB, 'w').write(str(time.time()))
    return d


def _good():
    return {'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 2, 'games': 4}


def _critical():
    return {'sup': 0, 'learners': 0, 'actors': 0, 'ctl': 2, 'games': 1}


def _single_missing():
    return {'sup': 1, 'learners': 2, 'actors': 3, 'ctl': 2, 'games': 4}


def test_AR1_trigger():
    _ctx()
    calls = []
    launch = lambda: (calls.append(1), True)[1]
    st = {}
    FH.loop_tick(st, now=1000.0, snap_fn=_critical, launch_fn=launch, proc_fn=lambda: [])
    FH.loop_tick(st, now=1120.0, snap_fn=_critical, launch_fn=launch, proc_fn=lambda: [])
    check('AR-1: 关键缺员连续2检查→触发', len(calls) == 1, str(calls))
    _ctx()
    calls2 = []
    launch2 = lambda: (calls2.append(1), True)[1]
    st2 = {}
    FH.loop_tick(st2, now=1000.0, snap_fn=_single_missing, launch_fn=launch2)
    ok, d, acts = FH.loop_tick(st2, now=1300.0, snap_fn=_single_missing,
                               launch_fn=launch2)
    check('AR-1: 单 learner 缺不触发(alert_only)',
          calls2 == [] and 'alert_only' in acts, str(acts))
    _ctx()
    calls3 = []
    st3 = {}
    FH.loop_tick(st3, now=1000.0, snap_fn=_critical,
                 launch_fn=lambda: (calls3.append(1), True)[1],
                 auto_recover=False)
    ok3, d3, acts3 = FH.loop_tick(st3, now=1130.0, snap_fn=_critical,
                                   launch_fn=lambda: (calls3.append(1),
                                                      True)[1],
                                   auto_recover=False)
    check('AR-1: --auto-recover 未开→不恢复', calls3 == [] and
          'recover_skipped_no_flag' in acts3, str(acts3))


def test_AR2_lock():
    _ctx()
    calls = []
    launch = lambda: (calls.append(1), True)[1]
    st = {}
    FH.fleet_lock.acquire('ukemi-window', 'window', pid=99999)
    FH.loop_tick(st, now=1000.0, snap_fn=_critical, launch_fn=launch, proc_fn=lambda: [])
    ok, d, acts = FH.loop_tick(st, now=1200.0, snap_fn=_critical,
                               launch_fn=launch, proc_fn=lambda: [])
    check('AR-2: 有效锁→抑制恢复(maintenance)',
          calls == [] and 'maintenance' in acts, str(acts))
    # stale 锁(过期) → 可接管
    _ctx()
    FH.fleet_lock.acquire('old-window', 'stale', ttl=-1, pid=99999)
    calls2 = []
    launch2 = lambda: (calls2.append(1), True)[1]
    st2 = {}
    FH.loop_tick(st2, now=2000.0, snap_fn=_critical, launch_fn=launch2, proc_fn=lambda: [])
    ok, d, acts = FH.loop_tick(st2, now=2130.0, snap_fn=_critical,
                               launch_fn=launch2, proc_fn=lambda: [])
    check('AR-2: stale 锁→告警+可接管恢复',
          len(calls2) == 1 and 'stale_lock_takeover' in acts, str(acts))


def test_AR3_rate_backoff():
    _ctx()
    FH._save_recovery({'last_ts': 1000.0})
    calls = []
    launch = lambda: (calls.append(1), True)[1]
    st = {'critical_since': 1300.0}
    ok, d, acts = FH.loop_tick(st, now=1420.0, snap_fn=_critical,
                               launch_fn=launch, proc_fn=lambda: [])
    check('AR-3: 10min 限流', calls == [] and 'rate_limited' in acts,
          str(acts))
    _ctx()
    FH._save_recovery({'last_ts': 0.0, 'fail_window_start': 100.0,
                       'fail_count': 3})
    st2 = {'critical_since': 900.0}
    ok, d, acts = FH.loop_tick(st2, now=1100.0, snap_fn=_critical,
                               launch_fn=lambda: False, proc_fn=lambda: [])
    check('AR-3: 失败退避(仅告警)', 'backoff' in acts, str(acts))


def test_AR4_no_kill():
    src = io.open(os.path.join(ROOT, 'tools', 'fleet_health.py'),
                  encoding='utf-8').read()
    check('AR-4: 无 Stop-Process(禁 shell kill)', 'Stop-Process' not in src)
    check('AR-4: 无 kill-by-name(/IM)',
          "'/IM'" not in src and '"IM"' not in src)
    check('AR-4: 孤儿清理仅按 /PID', "'/PID'" in src)
    _ctx()
    calls = []
    st = {}
    FH.loop_tick(st, now=1000.0, snap_fn=_critical,
                 launch_fn=lambda: (calls.append(1), True)[1],
                 proc_fn=lambda: [])
    ok, d, acts = FH.loop_tick(st, now=1130.0, snap_fn=_critical,
                               launch_fn=lambda: (calls.append(1), True)[1],
                               proc_fn=lambda: [])
    rec = json.load(io.open(FH.RECOVERY, encoding='utf-8'))
    check('AR-4: 恢复记录仅 launch/snapshot(无 kill)',
          'kill' not in json.dumps(rec).lower() and len(calls) == 1)


def test_machine_alert_not_cleared():
    _ctx()
    ma = FH.HB + '.machine_alert'
    io.open(ma, 'w').write('cpu')
    st = {}
    FH.loop_tick(st, now=1000.0, snap_fn=_single_missing,
                 launch_fn=lambda: True)
    FH.loop_tick(st, now=1200.0, snap_fn=_good, launch_fn=lambda: True)
    check('alert 命名: 恢复只清 fleet_alert, 不动 machine_alert',
          os.path.exists(ma) and not os.path.exists(FH.ALERT))


def test_AR5_alert_dedupe():
    _ctx()
    st = {}
    FH.loop_tick(st, now=1000.0, snap_fn=_single_missing,
                 launch_fn=lambda: True)
    a1 = io.open(FH.ALERT, encoding='utf-8').read()
    FH.loop_tick(st, now=1100.0, snap_fn=_single_missing,
                 launch_fn=lambda: True)
    a2 = io.open(FH.ALERT, encoding='utf-8').read()
    check('AR-5: 相同 bad 集合告警去重(内容不变)', a1 == a2)
    ok, d, acts = FH.loop_tick(st, now=1200.0, snap_fn=_good,
                               launch_fn=lambda: True)
    check('AR-5: 恢复后 alert 清除', not os.path.exists(FH.ALERT))


def test_AR6_single_instance():
    _ctx()
    ok, cur = FH.try_single_instance()
    check('AR-6: 首次单实例获取', ok)
    # 伪造另一个存活 pid (父进程) 占锁
    import json as _j
    with open(FH.WATCH_LOCK, 'w') as f:
        _j.dump({'pid': os.getppid(), 'ts': time.time()}, f)
    ok2, cur2 = FH.try_single_instance()
    check('AR-6: 另一存活 watcher→拒绝双启', (not ok2) and cur2 is not None)


def _spawn_dummy(role):
    return subprocess.Popen(
        [sys.executable, '-c', 'import time; time.sleep(120)',
         MARKER, role])


def test_AR8_real_dummy_fleet():
    _ctx()
    # 清理历史 dummy(marker 前缀匹配, PID 方式)
    try:
        out = FH._ps_json("Get-CimInstance Win32_Process | ? {$_.Name -eq 'python.exe' -and $_.CommandLine -match 'dummy_fleet_marker'} | % {$_.ProcessId}")
        for pid_s in out.split():
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', pid_s.strip()], capture_output=True)
            except Exception:
                pass
    except Exception:
        pass
    procs = {
        'sup': [_spawn_dummy('fleet_supervisor.py --actors 3')],
        'learners': [_spawn_dummy('learner_hub.py --char reimu')
                     for _ in range(3)],
        'actors': [_spawn_dummy('actor_worker.py --char reimu --actor 0')
                   for _ in range(3)]}
    try:
        time.sleep(1.0)
        snap = FH.snapshot(MARKER)
        snap['games'] = 4
        check('AR-8: 真实 dummy 进程计数(sup/learners/actors)',
              int(snap.get('sup', 0)) >= 1
              and int(snap.get('learners', 0)) >= 3
              and int(snap.get('actors', 0)) >= 3, str(snap))
        ok, d = FH.check(snap=snap)
        check('AR-8: dummy fleet 全在位→PASS', ok, str(d['bad']))
        # 杀 1 个 learner → 单缺只告警
        procs['learners'][0].kill()
        procs['learners'][0].wait(timeout=10)
        time.sleep(0.5)
        snap2 = FH.snapshot(MARKER)
        snap2['games'] = 4
        calls = []
        st = {}
        FH.loop_tick(st, now=1000.0, snap_fn=lambda: snap2,
                     launch_fn=lambda: (calls.append(1), True)[1])
        ok3, d3, acts3 = FH.loop_tick(st, now=1200.0,
                                      snap_fn=lambda: snap2,
                                      launch_fn=lambda: (calls.append(1),
                                                         True)[1])
        check('AR-8: 真实杀1 learner→不触发恢复',
              calls == [] and 'alert_only' in acts3, str(acts3))
        # 杀 sup → 关键缺 → 连续2次触发(WMI launch 用假函数)
        procs['sup'][0].kill()
        procs['sup'][0].wait(timeout=10)
        time.sleep(0.5)
        snap3 = FH.snapshot(MARKER)
        snap3['games'] = 4
        calls2 = []
        st2 = {}
        FH.loop_tick(st2, now=2000.0, snap_fn=lambda: snap3,
                     launch_fn=lambda: (calls2.append(1), True)[1],
                     proc_fn=lambda: [])
        ok4, d4, acts4 = FH.loop_tick(st2, now=2130.0,
                                      snap_fn=lambda: snap3,
                                      launch_fn=lambda: (calls2.append(1),
                                                         True)[1],
                                      proc_fn=lambda: [])
        check('AR-8: 真实杀 sup→关键缺→触发恢复',
              len(calls2) == 1 and 'recovered' in acts4, str(acts4))
    finally:
        for grp in procs.values():
            for p in grp:
                try:
                    p.kill()
                except OSError:
                    pass



def test_AR2_additions():
    _ctx()
    # stale 锁→fleet_alert 通知
    FH.fleet_lock.acquire('old', 'stale', ttl=-1, pid=99999)
    FH.fleet_lock.status()
    check('AR-2: stale 锁写 fleet_alert',
          os.path.exists(FH.fleet_lock.ALERT))
    # TTL 字段
    _ctx()
    ok, code, lk = FH.fleet_lock.acquire('win', 'ttl', ttl=7200)
    check('AR-2: 窗可显式 ttl(7200)', ok and
          abs(float(lk['expires']) - float(lk['created']) - 7200) < 2)
    # owner 校验释放
    ok2, code2 = FH.fleet_lock.release(owner='wrong')
    check('AR-2: 释放 owner 不匹配→拒绝', (not ok2) and code2 == 'owner_mismatch')
    ok3, code3 = FH.fleet_lock.release(owner='win')
    check('AR-2: owner 匹配→释放', ok3 and code3 == 'released')
    # CAS 并发: 两个线程抢锁, 恰好一个成功
    import threading
    res = []

    def _try(i):
        r = FH.fleet_lock.acquire('t%d' % i, 'cas', pid=1000 + i)
        res.append(r[0])
    ts = [threading.Thread(target=_try, args=(i,)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    check('AR-2: CAS 并发仅一个成功', sum(1 for x in res if x) == 1,
          str(res))


def test_AR6_kill_incomplete_abort():
    """AR-6: 未全杀掉孤儿→不得 launch 整队, 写 alert+记录."""
    _ctx()
    old = {'sup': 0, 'learners': 2, 'actors': 2, 'ctl': 1, 'games': 2}
    procs = [{'pid': 111, 'ppid': 999999, 'name': 'python.exe',
              'cmd': 'x learner_hub'},
             {'pid': 222, 'ppid': 999999, 'name': 'python.exe',
              'cmd': 'x actor_worker'}]
    orig_pl = FH.proc_list
    orig_alive = FH._pid_alive
    FH.proc_list = lambda marker=None: procs
    FH._pid_alive = lambda pid: int(pid) in (111, 222)
    calls = []
    try:
        def _kill(pid):
            return int(pid) == 111          # 222 杀失败
        r = FH.recover_ar6(old, snap_fn=lambda: old,
                           launch_fn=lambda: (calls.append(1), True)[1],
                           kill_fn=_kill, marker='dummy')
        check('AR-6: 未全杀→abort_kill_incomplete',
              r.get('code') == 'abort_kill_incomplete', str(r.get('code')))
        check('AR-6: 未全杀→不 launch', calls == [])
        check('AR-6: 未全杀→写 fleet_alert',
              os.path.exists(FH.ALERT))
        check('AR-6: 记录未杀 PID',
              r.get('unkilled') == [222], str(r.get('unkilled')))
    finally:
        FH.proc_list = orig_pl
        FH._pid_alive = orig_alive


def test_AR6_orphan_recovery():
    """真实 dummy: 仅 sup 死/子进程活 → 孤儿 PID 清理+整队+control 不动."""
    import subprocess as sp
    d = _ctx()
    marker = 'ar6dummy_' + uuid.uuid4().hex[:8]
    launcher = sp.Popen(
        [sys.executable, '-c',
         'import subprocess,sys,time;'
         'sp=subprocess; m=sys.argv[1];'
         'ps=[sp.Popen([sys.executable,"-c","import time;time.sleep(120)",'
         'm,"fleet_supervisor"]) ]'
         '+ [sp.Popen([sys.executable,"-c","import time;time.sleep(120)",'
         'm,"learner_hub"]) for _ in range(3)]'
         '+ [sp.Popen([sys.executable,"-c","import time;time.sleep(120)",'
         'm,"actor_worker"]) for _ in range(3)]'
         '+ [sp.Popen([sys.executable,"-c","import time;time.sleep(120)",'
         'm,"th123_rl_control"]) ]'
         '', marker])
    launcher_pid = launcher.pid
    launcher.wait(timeout=10)
    launcher = None
    import gc
    gc.collect()
    time.sleep(2)
    try:
        plist = [p for p in FH.proc_list(marker)
                 if int(p['pid']) != int(launcher_pid)]
        check('AR-6: dummy 进程就绪', len(plist) >= 8, 'n=%d' % len(plist))
        sup = [p for p in plist
               if 'fleet_supervisor' in str(p['cmd'])][0]
        old_main = [int(p['pid']) for p in plist
                    if FH._is_main_child(p)]
        ctl = [p for p in plist if 'th123_rl_control' in str(p['cmd'])]
        check('AR-6: control 进程在', len(ctl) == 1)
        # 验证 control 不是合法孤儿
        check('AR-6: control 不被当孤儿', not FH._valid_orphan(ctl[0], set()))
        os.kill(int(sup['pid']), 9)
        time.sleep(1)
        old_pids = [int(p['pid']) for p in FH.proc_list(marker)
                    if FH._is_main_child(p)
                    and int(p['pid']) != int(launcher_pid)]
        launched = []

        def _launch():
            for role, n in (('fleet_supervisor', 1), ('learner_hub', 3),
                            ('actor_worker', 3)):
                for _ in range(n):
                    launched.append(sp.Popen(
                        [sys.executable, '-c',
                         'import time;time.sleep(60)', marker, role]))
            return True

        def _snap():
            pl = FH.proc_list(marker)
            return {'sup': sum(1 for p in pl if 'fleet_supervisor'
                               in str(p['cmd'])),
                    'learners': sum(1 for p in pl if
                                    'learner_hub' in str(p['cmd'])),
                    'actors': sum(1 for p in pl if
                                  'actor_worker' in str(p['cmd'])),
                    'ctl': 1, 'games': 4}

        r = FH.recover_ar6(_snap(), snap_fn=_snap, launch_fn=_launch,
                           now=time.time(), marker=marker)
        check('AR-6: 恢复码=recovered_ar6', r.get('code') == 'recovered_ar6',
              str(r.get('code')))
        remaining = [p for p in FH.proc_list(marker)
                     if FH._is_main_child(p)
                     and int(p['pid']) != int(launcher_pid)]
        check('AR-6: 旧孤儿已清理(无重复 main 子进程)',
              len(remaining) == 6, 'n=%d' % len(remaining))
        check('AR-6: launch 被调用一次', len(launched) == 7)
        s2 = _snap()
        check('AR-6: 恢复后无重复 fleet(3/3)',
              s2['learners'] == 3 and s2['actors'] == 3, str(s2))
        check('AR-6: control 未动', FH._pid_alive(int(ctl[0]['pid'])))
        check('AR-6: 维护锁已释放',
              not FH.fleet_lock.status().get('active'))
        rec = FH._load_recovery().get('last') or {}
        check('AR-6: recovery 记录旧孤儿 PID',
              len(rec.get('old_orphans') or []) >= 5,
              str(rec.get('old_orphans')))
    finally:
        for p in FH.proc_list(marker):
            try:
                sp.run(['taskkill', '/F', '/T', '/PID', str(p['pid'])],
                       capture_output=True)
            except Exception:
                pass
        if launcher is not None:
            launcher.kill()


def main():
    test_AR1_trigger()
    test_AR2_lock()
    test_AR3_rate_backoff()
    test_AR4_no_kill()
    test_AR5_alert_dedupe()
    test_machine_alert_not_cleared()
    test_AR6_single_instance()
    test_AR8_real_dummy_fleet()
    test_AR2_additions()
    test_AR6_kill_incomplete_abort()
    test_AR6_orphan_recovery()
    print('\n==== fleet_auto_recovery AR: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
