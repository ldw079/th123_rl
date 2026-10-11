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
# P1-E(从零#2): 角色引擎ID原为手抄表 — 17项中11项错位(tenshi=11实为
# aya/youmu=13实为iku/...), 9个SC费用取自别的角色表。修: 从tm_env.CHAR
# 单源导入(游戏内选人用的真值, 与card_tables技能名交叉验证一致)。
from tm_env import CHAR as ENGINE_ID  # noqa: E402
CID = ENGINE_ID
# 首攻击token→action_id(reach查表用)
TOK2ACT = {
    '5a': 300, 'f5a': 301, '6a': 302, '2a': 303, '3a': 304,
    'j5a': 306, 'j6a': 307, 'j2a': 308, 'j8a': 309,
    '5b': 400, '6b': 401, '2b': 402, '5c': 410, '6c': 411, '2c': 412,
    'j5b': 404, 'j2b': 406, 'j5c': 414, 'j2c': 416,
    '66': 305, 'da': 305, '66a': 305, '66b': 305, '66c': 305,
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
        m = mv.lower().split('/')[0].replace('/', '')
        m = re.sub(r'^d(?=[a-z2-9])', '', m)
        for prefix in ('hj', 'j', 'f', ''):
            body = m[len(prefix):] if m.startswith(prefix) else None
            if body and body in TOK2ACT:
                return body
            # 66a类(冲刺攻击) → 底座66
            if body and body[-1] in 'abc' and body[:-1] in TOK2ACT:
                return body[:-1]
        if re.match(r'^[1-9]+[bc]$', m):
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
            moves = '_'.join(s.get('move') or 'x' for s in c['steps'])
            macro, bad = combo_to_macro(c['steps'], 'TM·%s' % moves)
            if macro:
                ok.append((c, macro))
        ok.sort(key=lambda x: -(x[0]['min_damage'] or 0))
        picked = ok[:max_per]
        if not picked:
            print('%s: 0条可转换' % ch)
            continue

        fpath = os.path.join(ROOT, 'macros', '%s.py' % ch)
        src = open(fpath, encoding='utf-8').read()
        m = re.search(r'(MACROS_[A-Z_]+)\s*=', src)
        var = m.group(1)
        # P1-E(从零#2): 既有宏名集合(去重校验用 — 原[:18]截断产生
        # remilia/komachi各一对重名, 名字索引静默解析到第一个)
        existing_names = set(re.findall(r"\(['\"]([^'\"]+)['\"],\s*\[", src))
        # SC耗费: 引用的卡ID从card_tables查cost(P1-E: CID走tm_env真值)
        eid = CID.get(ch)
        ct = CHAR_CARD_TABLES.get(eid, [])
        cost_map = {int(i): int(c) if str(c).isdigit() else 1
                    for i, _n, c in ct}
        sc_needed = set()
        for c, (name, script) in picked:
            for k, f in script:
                if isinstance(k, str) and k.startswith('sc:'):
                    sc_needed.add(int(k[3:]))

        # 写宏追加+COMBO更新+SC耗费补缺
        used_names = set(existing_names)
        final_names = []
        with open(fpath, 'a', encoding='utf-8') as f:
            f.write('\n# ==== R61j(C6): Trialmode连段完整集成 ====\n')
            for c, (name, script) in picked:
                # 全长名(不截断); 撞名加#N后缀
                if name in used_names:
                    _k = 2
                    while '%s#%d' % (name, _k) in used_names:
                        _k += 1
                    name = '%s#%d' % (name, _k)
                used_names.add(name)
                final_names.append((c, name))
                steps = []
                for k, fr in script:
                    if isinstance(k, str):
                        steps.append('(%r, 0)' % k)
                    else:
                        steps.append('(%r, %d)' % (tuple(k), fr))
                # 从零#2(产品面P2): 生成即过_norm_presteps规范化
                # (R46死招类第三次复发 — 追加在规范化重绑定之后=裸脚本)
                f.write('%s.append((%r, _norm_presteps([%s])))\n'
                        % (var, name, ', '.join(steps)))
            f.write('%s_COMBO_MACROS |= {%s}\n'
                    % (ch.upper(),
                       ', '.join(repr(n) for _c, n in final_names)))
            # 同步更新MACRO_NAMES/N_MACROS(names在上方预计算, 不随append走)
            f.write('# R61j: TM宏追加后同步names(含去重后缀)\n')
            f.write('MACRO_NAMES_%s = [m[0] for m in %s]\n'
                    % (ch.upper(), var))
            f.write('N_MACROS_%s = len(%s)\n' % (ch.upper(), var))
            # SC耗费补缺(仅引用了但表里没有的; P1-E: cost查真值CID表)
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
        # 射程: 首攻击token→action_id(用去重后的最终名; 值须为元组)
        reach_pairs = []
        for c, name in final_names:
            tok = first_attack_token(c['steps'])
            if tok:
                reach_pairs.append((name, (TOK2ACT[tok],)))
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
