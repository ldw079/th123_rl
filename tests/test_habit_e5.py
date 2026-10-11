# -*- coding: utf-8 -*-
"""R61r(E5)行为测试: 坏习惯检测与惩罚演示."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from habit_detector import (detect_habits, habit_report,
                            punishment_macros, HABITS)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def _rate(seq, key):
    """直接取某习惯的检测率(不经过阈值过滤)。"""
    return HABITS[key]['detect'](seq)


def main():
    # 1. 五种习惯定义完整
    check('五种习惯', len(HABITS) == 5,
          str(sorted(HABITS.keys())))

    # 2. 合成数据: 80%起身蹲防
    seq = []
    for i in range(200):
        if i % 50 < 20:
            seq.append((i, 97, 1000))        # 倒地
        elif i % 50 < 22:
            seq.append((i, 2, 1000))          # 蹲姿(起身)
        elif i % 50 < 30:
            seq.append((i, 154, 1000))        # 蹲防
        else:
            seq.append((i, 0, 1000))          # 待机
    habits = detect_habits(seq)
    check('检测到蹲防习惯', len(habits) >= 1,
          str([(h[1]['label'], '%.0f%%' % (h[2] * 100))
               for h in habits]))

    # 3. 合成数据: 无明显习惯(均匀分布)
    seq_ok = [(i, (i * 7) % 50, 1000) for i in range(200)]
    habits_ok = detect_habits(seq_ok)
    check('均匀行为无习惯', len(habits_ok) <= 1,
          str([(h[1]['label'], '%.0f%%' % (h[2] * 100))
               for h in habits_ok]))

    # 4. 空灵力出招
    seq_empty = []
    for i in range(100):
        if i % 10 < 3:
            seq_empty.append((i, 300 + i % 10, 50))   # 攻击+低灵力
        else:
            seq_empty.append((i, 0, 1000))
    habits_empty = detect_habits(seq_empty)
    check('检测到空灵力', any(k == 'empty_spirit_attack'
                             for k, _, _ in habits_empty),
          str([(h[1]['label'], '%.0f%%' % (h[2] * 100))
               for h in habits_empty]))

    # 5. 报告生成
    report = habit_report(habits)
    check('报告含标题', '坏习惯检测报告' in report)
    check('报告含改正建议', any('改正建议' in line
                                 for line in report.split('\n')))

    # 6. 无习惯时报告
    report_none = habit_report([])
    check('无习惯报告', '未检测到' in report_none)

    # 7. 惩罚宏映射
    from train_tm import CHAR_LIBS
    lib = CHAR_LIBS['reimu']
    macros = punishment_macros(lib, 'wakeup_crouch_guard')
    check('蹲防惩罚宏', len(macros) >= 1,
          str(macros))

    # 8. 未知习惯→空列表
    check('未知习惯空', punishment_macros(lib, 'unknown') == [])

    # 9. 从零#2 P1-F: 起身直入防御硬直态必须入样本(原act<50漏防)
    seq_g = []
    for i in range(100):
        if i % 25 < 10:
            seq_g.append((i, 97, 1000))          # 倒地
        elif i % 25 < 20:
            seq_g.append((i, 152, 1000))         # 起身→立防(硬直态)
        else:
            seq_g.append((i, 0, 1000))
    rate_g = _rate(seq_g, 'wakeup_stand_guard')
    check('起身立防可测(硬直态入样)', rate_g >= 0.7,
          'rate=%.2f' % rate_g)

    # 10. 从零#2 P1-F: 受压后跳检测(需4元组对手位; 3元组退化0)
    seq_p = [(i, 8 if 10 <= i % 40 < 18 else 0, 1000,
              400 if i % 40 < 10 else 0) for i in range(200)]
    rate_p = _rate(seq_p, 'pressure_backjump')
    check('受压后跳可测(对手位)', rate_p >= 0.5, 'rate=%.2f' % rate_p)
    seq_p3 = [(i, a, s) for i, a, s, _o in seq_p]
    rate_p3 = _rate(seq_p3, 'pressure_backjump')
    check('3元组退化不误报', rate_p3 == 0.0, 'rate=%.2f' % rate_p3)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
