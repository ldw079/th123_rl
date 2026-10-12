# -*- coding: utf-8 -*-
"""H(未决问题方案§H) 配对测试: learning_curve 解析+平台期检测.

覆盖:
  1. 批行解析(ver/KL/熵/值损/aux, 含无aux旧行式)
  2. 系列曲线/被动曲线行解析
  3. tail_slope: 平坦序列斜率≈0 / 上升序列斜率>0 / 样本不足→None
  4. analyze_char: verdict判定(平台/上升)
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.stdout.reconfigure(encoding='utf8')

from tools.learning_curve import analyze_char, tail_slope

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAIL: %s" % label
    PASS += 1
    print("[PASS] %s" % label)


def main():
    tmp = tempfile.mkdtemp(prefix="lc_test_")
    log = os.path.join(tmp, 'learner_test.log')
    lines = []
    # 旧式批行(无aux) + 新式(含aux)
    lines.append('[learner] test 批4局/2741决策 505.3s v100 |KL|0.0883 熵2.01 值损22.59 陈旧2')
    lines.append('[learner] test 批4局/2389决策 17.7s v101 |KL|0.1493 熵1.89 值损9.38 陈旧2 aux命中47%')
    lines.append('[learner] test 系列曲线 b1:aux64%(n379) W1-0(100%) b2:aux81%(n847) W0-0(-) b3:aux-(n0) W0-0(-) b4-5:aux68%(n1940) W2-0(100%)')
    lines.append('[learner] test 被动曲线 远弹50%(n40) 逼近75% 开局攻38%')
    with open(log, 'w', encoding='utf8') as f:
        f.write('\n'.join(lines) + '\n')

    d = analyze_char(log, tail=500)
    ok(d['n_batches'] == 2 and d['updates'] == 2, '批行解析2条跨v2')
    ok(d['aux_last'] == 47.0, 'aux末值47(旧行None不入序列)')
    ok(d['series_lines'] == 1 and d['series_b1_last'] == 64.0
       and d['series_b45_last'] == 68.0, '系列曲线行解析(b1/b4-5)')
    ok(d['passive_lines'] == 1 and d['far_bullet_last'] == 50.0
       and d['opening_attack_last'] == 38.0, '被动曲线行解析')

    # tail_slope: 平坦 vs 上升 vs 样本不足
    flat = [(i, 50.0) for i in range(100)]
    ok(abs(tail_slope(flat, 50)) < 1e-9, '平坦序列斜率≈0')
    rise = [(i, 40.0 + 0.1 * i) for i in range(100)]
    ok(abs(tail_slope(rise, 50) - 0.1) < 1e-6, '上升序列斜率=0.1')
    ok(tail_slope([(1, 1.0), (2, 2.0)]) is None, '样本不足→None')
    ok(tail_slope([(i, None) for i in range(50)]) is None, '全None→None')

    # verdict: 平台(斜率近零) vs 上升
    log2 = os.path.join(tmp, 'learner_rise.log')
    with open(log2, 'w', encoding='utf8') as f:
        f.write('\n'.join(
            '[learner] t 批1局/100决策 1.0s v%d |KL|0.1 熵1.5 值损5 陈旧1 aux命中%.1f%%'
            % (1000 + i, 40.0 + 0.2 * i) for i in range(60)) + '\n')
    d2 = analyze_char(log2, tail=50)
    ok(d2['plateau_verdict'] is not None
       and d2['plateau_verdict'].startswith('上升'),
       'verdict=上升(斜率0.2pp/点)')
    with open(log, 'a', encoding='utf8') as f:
        f.write('\n'.join(
            '[learner] test 批1局/100决策 1.0s v%d |KL|0.1 熵2.0 值损5 陈旧1 aux命中50.0%%'
            % (200 + i) for i in range(60)) + '\n')
    d3 = analyze_char(log, tail=50)
    ok(d3['plateau_verdict'] is not None
       and d3['plateau_verdict'].startswith('平台'),
       'verdict=平台(50%恒定)')

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    print("==== %d PASS / 0 FAIL ====" % PASS)


if __name__ == "__main__":
    main()
