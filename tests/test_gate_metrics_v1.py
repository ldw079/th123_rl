# -*- coding: utf-8 -*-
"""P1 行为测试: act_mask 指标语义/合法动作>0/选中合法; 防"全掩码"误判."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import game_gates as G  # noqa: E402
import numpy as np  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    G.reset_masked_stats()
    names = ['待机', '前进', '后退', '5A', '5B', '5C', 'jA', '空冲', '空翔前',
             '空翔后', '高跳', '6A', '2A', 'DA', '跳跃', '立防', '蹲防',
             '受身', '飞翔', '5B·高跳取消', '5B·空冲取消', 'jC·空翔后取消']
    mask = np.ones(len(names), dtype=bool)
    m = G.apply_state_gates(mask, names, {'action': 9, 'airBorne': False})
    check('mask 非空', bool(m.any()))
    check('allowed>0', int(np.count_nonzero(m)) > 0)
    check('选中在 allowed', G.choice_legal(int(np.argmax(m))))
    line = G.gate_metrics_line()
    check('新指标 gate_changed/allowed', 'gate_changed=' in line
          and 'allowed_avg=' in line, line)
    import re
    avg = re.search(r'allowed_avg=([0-9.]+)', line)
    check('allowed_avg>0', avg is not None and float(avg.group(1)) > 0)
    check('旧 masked_line 兼容', 'masked=' in G.masked_line())
    print('\n==== gate_metrics: %d PASS / %d FAIL ====' % (len(PASS),
                                                           len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
