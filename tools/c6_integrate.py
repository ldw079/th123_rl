# -*- coding: utf-8 -*-
"""R61j(C6完整集成): TM连段→宏库+类别集+SC耗费+射程一步到位。

上轮(R61i)试追加被门禁R39拦截的三类缺口的同步修复:
1. 宏追加: repr(tuple)格式(单键步尾逗号)
2. COMBO集: TM名加入COMBO_MACROS
3. SC耗费: 引用的卡ID从card_tables补入SC_COST表
4. 射程: 首攻击token→action_id→CHAR_MACRO_MOVES(reach_maps.py)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

from trialmode_parse import PACKS, load_pack  # noqa: E402
from trialmode_to_macro import combo_to_macro  # noqa: E402
from card_tables import CHAR_CARD_TABLES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEW_CHARS = ['yukari', 'komachi', 'meiling', 'sanae', 'youmu', 'yuyuko',
             'tenshi', 'suwako', 'alice', 'cirno', 'aya', 'remilia',
             'utsuho', 'sakuya', 'iku', 'patchouli', 'reisen']
# 角色引擎ID(engine_id → char name)
CID = {'reimu': 0, 'marisa': 1, 'suika': 9, 'sakuya': 2, 'alice': 3,
       'patchouli': 4, 'yuyuko': 7, 'reisen': 10, 'komachi': 12,
       'tenshi': 11, 'youmu': 13, 'remilia': 14, 'yukari': 15,
       'aya': 16, 'iku': 17, 'sanae': 18, 'cirno': 5, 'meiling': 6,
       'utsuho': 19, 'suwako': 8}
# 首攻击token→action_id(reach查表用)
TOK2ACT = {
    '5a': 300, 'f5a': 301, '6a': 302, '2a': 303, '3a': 304,
    'j5a': 306, 'j6a': 307, 'j2a': 308, 'j8a': 309,
    '5b': 400, '6b': 401, '2b': 402, '5c': 410, '6c': 411, '2c': 412,
    'j5b': 404, 'j2b': 406, 'j5c': 414, 'j2c': 416,
    '66': 305, 'da': 305,
}


def _diff(steps):
    exact = sum(1 for s in steps if s.get('exact'))
    n = len(steps)
    has_sc = any('sc' in (s.get('move') or '')
                 for s in steps if isinstance(s, dict))
    return exact * 2 + (n > 8) * 2 + (n > 11) * 2 + has_sc * 1


def first_attack_token(steps):
    """首个含A/B/C的token名(小写)。"""
    for s in steps:
        mv = s.get('move', '')
        if not mv:
            continue
        m = mv.lower().replace('/', '')
        m = re.sub(r'^d(?=[a-z2-9])', '', m)
        for prefix in ('hj', 'j', 'f', ''):
            body = m[len(prefix):] if m.startswith(prefix) else None
            if body and body in TOK2ACT:
                return body
        if re.match(r'^[2236]+[bc]$', m):
            return '5b'   # 必杀起手近似按B射程
    return None


def main():
    max_per = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    grand = 0
    reach_additions = {}    # char → [(tm_name, act_id)]

    for ch in NEW_CHARS:
        packs = PACKS.get(ch, [])
        if not packs:
            print('%s: 无数据' % ch)
            continue
        combos = []
        for pk in packs:
            combos.extend(load_pack(pk))
        ok = []
        for c in combos:
            if _diff(c['steps']) > 5 or len(c['steps']) > 8:
                continue
            # 必须含至少一个攻击步(纯移动如"4"不是连段)
            if first_attack_token(c['steps']) is None:
                continue
            moves = '_'.join(s['move'] for s in c['steps'])[:18]
            macro, bad = combo_to_macro(c['steps'], 'TM·%s' % moves)
            if macro:
                ok.append((c, macro))
        ok.sort(key=lambda x: -(x[0]['min_damage'] or 0))
        picked = ok[:max_per]
        if not picked:
            print('%s: 0条可转换' % ch)
            continue

        fpath = os.path.join(ROOT, 'macros_%s.py' % ch)
        src = open(fpath, encoding='utf8').read()
        m = re.search(r'(MACROS_[A-Z_]+)\s*=', src)
        var = m.group(1)
        # SC耗费: 引用的卡ID从card_tables查cost
        eid = CID.get(ch)
        ct = CHAR_CARD_TABLES.get(eid, [])
        cost_map = {int(i): int(c) if str(c).isdigit() else 1
                    for i, _n, c in ct}
        sc_needed = set()
        for c, (name, script) in picked:
            for k, f in script:
                if isinstance(k, str) and k.startswith('sc:'):
                    sc_needed.add(int(k[3:]))
        # 射程: 首攻击token→action_id(值须为元组 — reach_maps的
        # mids迭代消费)
        reach_pairs = []
        for c, (name, script) in picked:
            tok = first_attack_token(c['steps'])
            if tok:
                reach_pairs.append((name, (TOK2ACT[tok],)))

        # 写宏追加+COMBO更新+SC耗费补缺
        with open(fpath, 'a', encoding='utf8') as f:
            f.write('\n# ==== R61j(C6): Trialmode连段完整集成 ====\n')
            for c, (name, script) in picked:
                steps = []
                for k, fr in script:
                    if isinstance(k, str):
                        steps.append('(%r, 0)' % k)
                    else:
                        steps.append('(%r, %d)' % (tuple(k), fr))
                f.write('%s.append((%r, [%s]))\n'
                        % (var, name, ', '.join(steps)))
            f.write('%s_COMBO_MACROS |= {%s}\n'
                    % (ch.upper(),
                       ', '.join(repr(c[1][0]) for c in picked)))
            # 同步更新MACRO_NAMES(names在第98行预计算, 不随append走)
            f.write('# R61j: TM宏追加后同步names\n')
            f.write('MACRO_NAMES_%s = [m[0] for m in %s]\n'
                    % (ch.upper(), var))
            # SC耗费补缺(仅引用了但表里没有的)
            existing = re.search(
                r'SC_COST_\w+ = \{([^}]*)\}', src)
            existing_ids = set()
            if existing:
                existing_ids = {int(x) for x
                                in re.findall(r'(\d+):', existing.group(1))}
            missing = sc_needed - existing_ids
            if missing:
                f.write('# R61j: TM宏引用的SC卡耗费补入\n')
                for cid in sorted(missing):
                    cost = cost_map.get(cid, 1)
                    f.write('SC_COST_%s[%d] = %d\n'
                            % (ch.upper(), cid, cost))
        reach_additions[ch] = reach_pairs
        grand += len(picked)
        sc_str = ('SC补:%s' % sorted(missing)) if missing else 'SC全有'
        print('%s: +%d条 %s 射程%d条 → %s'
              % (ch, len(picked), sc_str, len(reach_pairs),
                 os.path.basename(fpath)))

    # 更新reach_maps.py的CHAR_MACRO_MOVES
    rm_path = os.path.join(ROOT, 'reach_maps.py')
    rm = open(rm_path, encoding='utf8').read()
    for ch, pairs in reach_additions.items():
        if not pairs:
            continue
        entries = ', '.join('%r: %r' % (n, a) for n, a in pairs)
        # 在角色的dict(_COMMON)后追加
        old = "'%s': dict(_COMMON)" % ch
        if old in rm:
            new = "'%s': dict(_COMMON, **{%s})" % (ch, entries)
            rm = rm.replace(old, new, 1)
            print('  reach_maps: %s +%d条' % (ch, len(pairs)))
        else:
            print('  !! reach_maps: %s的条目未找到' % ch)
    with open(rm_path, 'w', encoding='utf8') as f:
        f.write(rm)

    print('--- 总追加: %d条 ---' % grand)


if __name__ == '__main__':
    main()
