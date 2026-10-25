# -*- coding: utf-8 -*-
"""R15 辅助静态门禁: 窗口脚本禁止用 Start-Process 启动常驻 fleet.

背景: 2026-10-26 00:43 主臂全灭 — 工具后台作业 Start-Process 起的 fleet 被 harness
回合清理树杀。本测试只做**辅助静态扫描**；行为证据见
tests/test_fleet_detach_health_v1.py（WMI detached + 父杀存活）。
"""
import glob
import io
import os
import re
import sys

TMP = r'D:\temp'
FLEET_KEY = re.compile(
    r'fleet_supervisor|train_start|train_batch_launch|learner_hub|'
    r'actor_worker', re.I)
LAUNCH = re.compile(r'(^|\s)Start-Process(\s|$)', re.I)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def scan():
    bad = []
    for p in glob.glob(os.path.join(TMP, '*.ps1')):
        try:
            L = io.open(p, encoding='utf-8', errors='replace').read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(L):
            st = line.strip()
            if st.startswith('#'):
                continue
            if LAUNCH.search(st) and FLEET_KEY.search(st):
                bad.append('%s:%d %s' % (os.path.basename(p), i + 1,
                                         st[:100]))
            # 跨行 continuation: Start-Process 行 + 下 3 行含 fleet 关键字
            if LAUNCH.search(st):
                window = ' '.join(x.strip() for x in L[i:i + 4])
                if FLEET_KEY.search(window) and 'pyenv' in window:
                    bad.append('%s:%d %s' % (os.path.basename(p), i + 1,
                                             window[:100]))
    return bad


def test_scripts_no_start_process_fleet():
    if not os.path.isdir(TMP):
        check('窗口脚本扫描: D:\\temp 不存在(跳过)', True)
        return
    bad = scan()
    check('窗口脚本: 无 Start-Process 启动 fleet', not bad,
          '; '.join(bad[:3]) if bad else 'ok')


def main():
    test_scripts_no_start_process_fleet()
    print('\n==== window_launch_policy: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
