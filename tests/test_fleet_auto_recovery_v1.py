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

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def _ctx():
    d = tempfile.mkdtemp(prefix='fh_ar_')
    FH.STORE = d
    FH.HB = os.path.join(d, 'fleet_heartbeat')
    FH.ALERT = FH.HB + '.machine_alert'
    FH.RECOVERY = os.path.join(d, 'fleet_recovery.json')
    FH.RECOVERY_LOG = os.path.join(d, 'fleet_recovery.log')
    FH.WATCH_LOCK = os.path.join(d, 'fleet_watcher.lock')
    FH.fleet_lock.LOCK = os.path.join(d, 'fleet_maintenance.lock')
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
    FH.loop_tick(st, now=1000.0, snap_fn=_critical, launch_fn=launch)
    FH.loop_tick(st, now=1120.0, snap_fn=_critical, launch_fn=launch)
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


def test_AR2_lock():
    _ctx()
    calls = []
    launch = lambda: (calls.append(1), True)[1]
    st = {}
    FH.fleet_lock.acquire('ukemi-window', 'window', pid=99999)
    FH.loop_tick(st, now=1000.0, snap_fn=_critical, launch_fn=launch)
    ok, d, acts = FH.loop_tick(st, now=1200.0, snap_fn=_critical,
                               launch_fn=launch)
    check('AR-2: 有效锁→抑制恢复(maintenance)',
          calls == [] and 'maintenance' in acts, str(acts))
    # stale 锁(过期) → 可接管
    _ctx()
    FH.fleet_lock.acquire('old-window', 'stale', ttl=-1, pid=99999)
    calls2 = []
    launch2 = lambda: (calls2.append(1), True)[1]
    st2 = {}
    FH.loop_tick(st2, now=2000.0, snap_fn=_critical, launch_fn=launch2)
    ok, d, acts = FH.loop_tick(st2, now=2130.0, snap_fn=_critical,
                               launch_fn=launch2)
    check('AR-2: stale 锁→告警+可接管恢复',
          len(calls2) == 1 and 'stale_lock_takeover' in acts, str(acts))


def test_AR3_rate_backoff():
    _ctx()
    FH._save_recovery({'last_ts': 1000.0})
    calls = []
    launch = lambda: (calls.append(1), True)[1]
    st = {'critical_since': 1300.0}
    ok, d, acts = FH.loop_tick(st, now=1420.0, snap_fn=_critical,
                               launch_fn=launch)
    check('AR-3: 10min 限流', calls == [] and 'rate_limited' in acts,
          str(acts))
    _ctx()
    FH._save_recovery({'last_ts': 0.0, 'fail_window_start': 100.0,
                       'fail_count': 3})
    st2 = {'critical_since': 900.0}
    ok, d, acts = FH.loop_tick(st2, now=1100.0, snap_fn=_critical,
                               launch_fn=lambda: False)
    check('AR-3: 失败退避(仅告警)', 'backoff' in acts, str(acts))


def test_AR4_no_kill():
    src = io.open(os.path.join(ROOT, 'tools', 'fleet_health.py'),
                  encoding='utf-8').read()
    check('AR-4: watcher 源码无 taskkill/Stop-Process',
          'taskkill' not in src and 'Stop-Process' not in src)
    _ctx()
    calls = []
    st = {}
    FH.loop_tick(st, now=1000.0, snap_fn=_critical,
                 launch_fn=lambda: (calls.append(1), True)[1])
    ok, d, acts = FH.loop_tick(st, now=1130.0, snap_fn=_critical,
                               launch_fn=lambda: (calls.append(1), True)[1])
    rec = json.load(io.open(FH.RECOVERY, encoding='utf-8'))
    check('AR-4: 恢复记录仅 launch/snapshot(无 kill)',
          'kill' not in json.dumps(rec).lower() and len(calls) == 1)


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
         'dummy_fleet_marker', role])


def test_AR8_real_dummy_fleet():
    _ctx()
    procs = {'sup': [_spawn_dummy('fleet_supervisor')],
             'learners': [_spawn_dummy('learner_hub') for _ in range(3)],
             'actors': [_spawn_dummy('actor_worker') for _ in range(3)]}
    try:
        time.sleep(1.0)
        snap = FH.snapshot('dummy_fleet_marker')
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
        snap2 = FH.snapshot('dummy_fleet_marker')
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
        snap3 = FH.snapshot('dummy_fleet_marker')
        snap3['games'] = 4
        calls2 = []
        st2 = {}
        FH.loop_tick(st2, now=2000.0, snap_fn=lambda: snap3,
                     launch_fn=lambda: (calls2.append(1), True)[1])
        ok4, d4, acts4 = FH.loop_tick(st2, now=2130.0,
                                      snap_fn=lambda: snap3,
                                      launch_fn=lambda: (calls2.append(1),
                                                         True)[1])
        check('AR-8: 真实杀 sup→关键缺→触发恢复',
              len(calls2) == 1 and 'recovered' in acts4, str(acts4))
    finally:
        for grp in procs.values():
            for p in grp:
                try:
                    p.kill()
                except OSError:
                    pass


def main():
    test_AR1_trigger()
    test_AR2_lock()
    test_AR3_rate_backoff()
    test_AR4_no_kill()
    test_AR5_alert_dedupe()
    test_AR6_single_instance()
    test_AR8_real_dummy_fleet()
    print('\n==== fleet_auto_recovery AR: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
