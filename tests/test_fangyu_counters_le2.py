# -*- coding: utf-8 -*-
"""LE-2第二步行为测试: fangyu警戒表深解析 — 结构/覆盖/出处/抽样语义。"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

PASS, FAIL = [], []
GT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'data', 'guide_tables',
    'fangyu_counters.json')


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    check('表档存在', os.path.exists(GT))
    d = json.load(io.open(GT, encoding='utf8'))
    chars = d['characters']
    check('11角色全覆盖', len(chars) == 11, str(len(chars)))

    # 每角色必有破防/空防不可(章节索引里全有)
    for cn, rec in chars.items():
        check('%s有guard_crush' % cn, len(rec.get('guard_crush', [])) >= 1)
        check('%s有air_unblockable' % cn,
              len(rec.get('air_unblockable', [])) >= 1)

    # 警戒招覆盖: 除帕秋莉(用必杀技相性节, 如实缺省)外≥8
    # (咲夜章实测9条 — 章节本就短, 阈值按实测下界-1)
    for cn, rec in chars.items():
        n = len(rec.get('warning_moves', []))
        if rec.get('char_key') == 'patchouli':
            check('patchouli警戒0如实(节缺)', n == 0)
        else:
            # P1-12(从零#5): 阈值 8→6 — 原 8 是在"叙述句被当条目"的旧数据上标定的
            # (咲夜 9 条里 2 条是句子); 滤后 7 条全是合法招名
            # (3A/6A/DB/J6A/J2A/2B/JC), 保留"该节被解析出内容"的原意;
            # 标签串写≥6 而判据曾是 8 —— 一并修正。
            check('%s警戒≥6(%d)' % (cn, n), n >= 6)

    # 抽样语义: marisa的警戒表含6C/遠A类已知条目
    mar = chars['雾雨魔理沙']['warning_moves']
    names = [m['name'] for m in mar]
    check('marisa含6C条目', any('6C' in n for n in names))
    check('marisa含遠A条目', any('A' in n for n in names))

    # 出处可审计: 行锚点在档
    for cn, rec in chars.items():
        if 'warning_moves' in rec and rec['warning_moves']:
            check('%s行锚点' % cn,
                  len(rec.get('_warning_lines', [])) == 2)

    # 建议非空率(伪条目防线): ≥40% — "列名式"写法(招名后直接下一
    # 招名)的建议天然为空, 条目本身仍是有效警戒(计数先验不受影响)
    for cn, rec in chars.items():
        ms = rec.get('warning_moves', [])
        if ms:
            with_adv = sum(1 for m in ms if m.get('advice'))
            check('%s建议非空率' % cn, with_adv / len(ms) >= 0.4,
                  '%d/%d' % (with_adv, len(ms)))

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
