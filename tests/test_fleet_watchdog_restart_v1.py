# -*- coding: utf-8 -*-
"""P0 回归: supervisor 停滞看门狗 kill 后必须 spawn（真实进程行为测试）.

事故: 2026-10-25 marisa learner 日志停滞, 看门狗"精确重启"只 kill 未 spawn
→ learner 消失 78min（R17-12）。本测试钉死: restart_stalled 后 learners/actors
必须被**新进程**替换且进程存活（不得只删）。
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import fleet_supervisor as FS  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def _sleep_proc(sec=30):
    return subprocess.Popen([sys.executable, '-c',
                             'import time; time.sleep(%d)' % sec])


class _FakeProc:
    def __init__(self, pid):
        self.pid = pid
        self.returncode = None

    def poll(self):
        return None


def test_stall_learner_respawn():
    old = _sleep_proc()
    learners = {'marisa': old}
    actors = {}
    restarts = {}
    last = {}
    orig_kill = FS._kill_tree
    orig_spawn = FS._spawn_learner_proc
    try:
        FS._kill_tree = lambda pid: None
        FS._spawn_learner_proc = lambda ch: _sleep_proc()
        p2 = FS.restart_stalled('learner', 'marisa', actors, learners, [],
                                360, restarts, last)
        check('learner: 被替换为新进程',
              learners.get('marisa') is p2 and p2 is not None)
        check('learner: 新进程存活(非只删)', p2 is not None
              and p2.poll() is None)
        check('learner: 重启计数', restarts.get(('learner', 'marisa')) == 1)
    finally:
        FS._kill_tree = orig_kill
        FS._spawn_learner_proc = orig_spawn
        for p in (old, p2 if 'p2' in dir() else None):
            if p is not None:
                try:
                    p.kill()
                except OSError:
                    pass


def test_stall_actor_respawn():
    old = _FakeProc(424242)
    actors = {('reimu', 0): old}
    learners = {}
    restarts = {}
    last = {}
    orig_kill = FS._kill_tree
    orig_spawn = FS._spawn_actor
    newp = _FakeProc(434343)
    try:
        FS._kill_tree = lambda pid: None
        FS._spawn_actor = lambda ch, aid, port, opp, tps: newp
        p2 = FS.restart_stalled('actor', ('reimu', 0), actors, learners, [],
                                360, restarts, last)
        check('actor: 被替换为新进程', actors.get(('reimu', 0)) is newp)
        check('actor: 重启计数', restarts.get(('reimu', 0)) == 1)
    finally:
        FS._kill_tree = orig_kill
        FS._spawn_actor = orig_spawn


def test_stall_detection_real_log():
    logp = r'D:\temp\learner_zzstalltest.log'
    try:
        with open(logp, 'w') as f:
            f.write('x')
        os.utime(logp, (time.time() - 400, time.time() - 400))
        fake = type('P', (), {'poll': lambda self: None})()
        res = FS.watchdog_stalled({}, {'zzstalltest': fake})
        check('看门狗: 检测到 learner 日志停滞',
              any(k == 'learner' and v == 'zzstalltest' for k, v, _a in res),
              str(res))
    finally:
        try:
            os.remove(logp)
        except OSError:
            pass


def test_spawn_failure_not_crash():
    learners = {'ghost': _FakeProc(1)}
    orig_kill = FS._kill_tree
    orig_spawn = FS._spawn_learner_proc
    try:
        FS._kill_tree = lambda pid: None

        def _boom(ch):
            raise RuntimeError('spawn fail')
        FS._spawn_learner_proc = _boom
        r = FS.restart_stalled('learner', 'ghost', {}, learners, [], 360,
                               {}, {})
        check('spawn 失败: 返回 None 不抛(监督器存活)', r is None)
    finally:
        FS._kill_tree = orig_kill
        FS._spawn_learner_proc = orig_spawn


def main():
    test_stall_learner_respawn()
    test_stall_actor_respawn()
    test_stall_detection_real_log()
    test_spawn_failure_not_crash()
    print('\n==== supervisor_watchdog: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
