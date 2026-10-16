# -*- coding: utf-8 -*-
"""BH-4.3行为测试: 对位连段成立性先验表 — 结构完整性/角色名合法/
宏名真实存在于各主力库/出处可审计/未确认项显式登记(空表优于错表)。"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from train_tm import CHAR_LIBS

PASS, FAIL = [], []
GT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'data', 'guide_tables',
    'matchup_combo_prior.json')


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    check('表档存在', os.path.exists(GT))
    d = json.load(io.open(GT, encoding='utf-8'))

    # 出处可审计
    check('攻略引文在档', '浮空连' in d['provenance']['guide_quote'])
    check('攻略档引用在案', 'behavioral_health' in
          d['provenance']['guide_doc'])

    # 昵称解码完备: 引文里每个昵称要么解码要么进unverified
    nk = set(d['provenance']['nicknames_decoded'])
    un = set(d['provenance']['unverified'])
    check('UU/早苗/YM/⑨已解码',
          {'UU', '早苗', 'YM', '⑨'} <= nk)
    check('19显式未确认', '19' in un)
    check('高个子显式未确认', '高个子限定推板' in un)

    # 角色名合法(在20角色库内)
    all_chars = set(CHAR_LIBS.keys())
    for sname, s in d['restriction_sets'].items():
        for c in s['chars']:
            check('%s角色名合法:%s' % (sname, c), c in all_chars)

    # 宏名真实存在于对应主力库
    for sname, s in d['restriction_sets'].items():
        for ch, macros in s.get('macros', {}).items():
            names = set(CHAR_LIBS[ch]['names'])
            for m in macros:
                check('%s宏存在于%s:%s' % (sname, ch, m), m in names)

    # 模式合法 + 消费设计在档(接线排BH-4.4)
    check('模式合法', all(s['mode'] in ('downweight', 'documented_only')
                          for s in d['restriction_sets'].values()))
    check('消费设计在档', 'BH-4.4' in d.get('consumer_design', ''))

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
