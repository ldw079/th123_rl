# -*- coding: utf-8 -*-
"""F(未决问题方案§F) 配对测试: throughput_report 三件解析.

覆盖:
  1. actor局/小时: 连续段切分(ep回落=重启) + 跨午夜回绕(+24h)
  2. learner批耗时分布(median/p90/max)
  3. 占空比: 监督日志间隙>600s=停机
"""
import os
import sys
import tempfile

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.stdout.reconfigure(encoding='utf8')

from tools import throughput_report as tr

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAIL: %s" % label
    PASS += 1
    print("[PASS] %s" % label)


def main():
    tmp = tempfile.mkdtemp(prefix="tp_test_")

    # 1. actor速率: 段切分+跨午夜
    a = os.path.join(tmp, 'actor_test_0.log')
    lines = [
        '[actor0] 23:50:00 ep0 100决策 v1 帧1 → a.npz',
        '[actor0] 23:55:00 ep5 100决策 v1 帧1 → a.npz',      # 5局/5min=60/h
        '[actor0] 00:05:00 ep15 100决策 v1 帧1 → a.npz',     # 跨午夜+15局/15min
        '[actor0] 00:10:00 ep3 100决策 v1 帧1 → a.npz',      # ep回落=重启段
    ]
    open(a, 'w', encoding='utf8').write('\n'.join(lines) + '\n')
    rates = tr.actor_rates([a])
    rs = rates['actor_test_0.log']
    # 段2仅1个采样点(00:10 ep3) → 不足2点不入速率表; 有效段=段1
    ok(len(rs) == 1, '有效段=1(重启后单点段被滤)')
    # 段1: 23:50:00→00:05:00(+24h回绕)=15min, ep0→15 → 60局/h
    ok(abs(rs[0][0] - 60.0) < 1e-6 and rs[0][1] == 15,
       '段1=60局/h(跨午夜回绕正确)')

    # 2. 批耗时分布
    l = os.path.join(tmp, 'learner_test.log')
    open(l, 'w', encoding='utf8').write('\n'.join(
        '[learner] test 批1局/100决策 %.1fs v%d |KL|0.1 熵1.5 值损5 陈旧1'
        % (10.0 + i, i) for i in range(10)) + '\n')
    tr.LEARNER_LOG = os.path.join(tmp, 'learner_%s.log')
    bd = tr.batch_durations(('test',))
    d = bd['test']
    ok(d['n'] == 10 and d['median'] == 15.0 and d['max'] == 19.0,
       '批耗时分布 n/median/max')

    # 3. 占空比: 间隙>600s计停机
    s = os.path.join(tmp, 'fleet_supervision.log')
    import datetime
    now = datetime.datetime.now()

    def ts(dt):
        return dt.strftime('[%m-%d %H:%M:%S]')
    sup = [
        ts(now - datetime.timedelta(hours=2)),
        ts(now - datetime.timedelta(hours=1, minutes=55)),  # 在线5min
        ts(now - datetime.timedelta(minutes=20)),           # 间隙95min>70min=停机
        ts(now - datetime.timedelta(minutes=15)),           # 在线5min
    ]
    open(s, 'w', encoding='utf8').write('\n'.join(sup) + '\n')
    tr.SUP_LOG = s
    tr.STORE = tmp   # 隔离真心跳(无档→尾部按停机)
    dc = tr.duty_cycle(6)
    ok(abs(dc['online_h'] - 25 / 60.0) < 0.01
       and abs(dc['downtime_h'] - 95 / 60.0) < 0.01,
       '占空比: 在线25min(10+尾部15min<GAP_DEAD按活)停机95min(>70min间隙)')

    # 审计#3 P1-3: 路径常量不得含控制字符(D:<TAB>emp字节笔误让fleet
    # 合计恒0 — getmtime恒OSError)。可编程扫源码字节。
    _src = open(os.path.join(os.path.dirname(__file__), '..',
                             'tools', 'throughput_report.py'),
                'rb').read()
    _ctrl = [i for i in range(len(_src))
             if _src[i] < 0x20 and _src[i] not in (0x0A, 0x0D)]
    ok(not _ctrl, '源码无控制字符(TAB路径字节笔误防复发): %d处'
       % len(_ctrl))

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    print("==== %d PASS / 0 FAIL ====" % PASS)


if __name__ == "__main__":
    main()
