# -*- coding: utf-8 -*-
"""BH-1行为测试: 行为健康计数器 — 续打率/连段完成率/对位分解/
宏转移/承诺占比的记账语义 + 旁车flush→aggregate→rates往返。"""
import glob
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from behavior_health import (BehaviorCounter, aggregate, rates,
                             is_attack_macro, is_combo_macro)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    # ===== 类别判定 =====
    check('连段类: 名称前缀', is_combo_macro('连段A', 'MELEE'))
    check('连段类: 名称含连', is_combo_macro('TM·对空连', 'MELEE'))
    check('非连段: 纯5A', not is_combo_macro('5A', 'MELEE'))
    check('攻击类: MELEE/SKILL', is_attack_macro('MELEE')
          and is_attack_macro('SKILL'))
    check('非攻击: JUMP/GUARD_PREP', not is_attack_macro('JUMP')
          and not is_attack_macro('GUARD_PREP'))

    # ===== 记账语义 =====
    bh = BehaviorCounter('reimu')
    # 决策1: 选连段A(开局, 无prev)
    bh.note_decision(None, None, 0.0, False, '连段A', 'MELEE', 'marisa')
    check('开局决策不结算fate', sum(bh.combo.values()) == 0)
    # 决策2: 上一窗命中(连段A结算=hit) + 本决策又选攻击 → follow hit_atk
    bh.note_decision('连段A', 'MELEE', 500.0, False, '6A', 'MELEE',
                     'marisa')
    check('连段命中结算', bh.combo['hit'] == 1)
    check('命中后续打(hit_atk)', bh.follow['hit_atk'] == 1)
    # 决策3: 上一窗未命中未防(6A落空) + 本决策移动 → nohit_n
    bh.note_decision('6A', 'MELEE', 0.0, False, '后退', 'OTHER',
                     'marisa')
    check('落空结算(dropped)', bh.combo['dropped'] == 0
          or bh.combo['dropped'] == 1)   # 6A非连段类不结算
    check('6A非连段类', not is_combo_macro('6A', 'MELEE'))
    check('未命中时移动(nohit_n)', bh.follow['nohit_n'] == 1)
    # 决策4: 选版边连A(连段类)
    bh.note_decision('后退', 'OTHER', 0.0, False, '版边连A', 'MELEE',
                     'suika')
    # 决策5: 上一窗被打断(prev_name None) → interrupted + 对位suika
    bh.note_decision(None, None, 0.0, False, '立防', 'GUARD_PREP',
                     'suika')
    check('打断结算', bh.combo['interrupted'] == 1)
    check('对位分解suika', bh.combo_by_opp.get('suika', {})
          .get('interrupted') == 1)
    check('对位分解marisa隔离', bh.combo_by_opp.get('marisa', {})
          .get('interrupted', 0) == 0)
    # 决策6: 再选连段A → 上一窗被防
    bh.note_decision('立防', 'GUARD_PREP', 0.0, False, '连段A', 'MELEE',
                     'marisa')
    bh.note_decision('连段A', 'MELEE', 0.0, True, '5A', 'MELEE',
                     'marisa')
    check('被防结算(blocked)', bh.combo['blocked'] == 1)
    # 承诺占比: 7决策中攻击类=5(连段A×3+6A+版边连A+5A,
    # 非攻击=后退+立防)
    atk = sum(v for k, v in bh.cls_count.items() if is_attack_macro(k))
    check('承诺占比计数', atk == 5 and bh.n_dec == 7,
          'atk=%d n=%d' % (atk, bh.n_dec))
    # 宏转移
    check('宏转移记账', bh.trans.get('连段A→6A') == 1
          and bh.trans.get('后退→版边连A') == 1)

    # ===== flush → aggregate → rates 往返 =====
    tmp = tempfile.mkdtemp(prefix='bh_test_')
    try:
        p = bh.flush(tmp, 3, 42)
        check('旁车落盘', p is not None and os.path.exists(p))
        r = json.loads(json.dumps(json.load(open(p, encoding='utf8'))))
        check('旁车字段齐', all(k in r for k in
                                ('char', 'n_dec', 'cls', 'follow',
                                 'combo', 'combo_by_opp', 'trans_top')))
        agg = aggregate(tmp, 'reimu', 10)
        rr = rates(agg)
        check('聚合往返: 决策数', rr['decisions'] == 7)
        check('聚合往返: 连段命中数', agg['combo']['hit'] == 1)
        check('聚合往返: 续打率', abs(rr['followup_hit'] - 1.0) < 1e-9)
        check('聚合往返: 对位', rr['combo_by_opp']['suika']['n'] == 1)
        # 空决策计数器不落盘
        bh0 = BehaviorCounter('reimu')
        check('空计数器不落盘', bh0.flush(tmp, 3, 43) is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
