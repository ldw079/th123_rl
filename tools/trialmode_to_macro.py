# -*- coding: utf-8 -*-
"""Trialmode expected记法 → 宏脚本转换器(R31)。
记法→键序列映射(小键盘方向→方向键名; 招式名→按键+预置)。
输出: 可直接追加到macros*.py的(name, script)元组列表。
用法: python tools/trialmode_to_macro.py [char] [--dry-run]"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')
from tools.trialmode_parse import parse_expected, load_pack  # noqa: E402

# 小键盘→方向键(相对角色朝向, 我们的宏用right=前)
DIR_MAP = {
    '1': ('down', 'left'), '2': ('down',), '3': ('down', 'right'),
    '4': ('left',), '5': (), '6': ('right',),
    '7': ('up', 'left'), '8': ('up',), '9': ('up', 'right'),
}

# 招式记法→(方向帧, 按键) — 预置帧从hitlab标定(6帧阈值5)
MOVE_SCRIPT = {
    # A系
    '5a': [(("A",), 8)],
    '2a': [(("down",), 6), (("down", "A"), 10)],
    '6a': [(("right",), 6), (("right", "A"), 12)],
    '3a': [(("down",), 6), (("down", "right"), 2), (("down", "right", "A"), 14)],
    '4a': [(("left",), 6), (("left", "A"), 10)],
    'j5a': [(("up",), 6), (("up",), 2), (("A",), 10)],
    'j6a': [(("up",), 6), (("right",), 2), (("right",), 4), (("right", "A"), 12)],
    'j2a': [(("up",), 6), (("down",), 2), (("down",), 4), (("down", "A"), 12)],
    'j8a': [(("up",), 6), (("up",), 2), (("up", "A"), 12)],
    # B/C系(弹幕)
    '5b': [(("B",), 10)],
    '2b': [(("down",), 6), (("down", "B"), 10)],
    '6b': [(("right",), 6), (("right", "B"), 10)],
    '5c': [(("C",), 12)],
    '2c': [(("down",), 6), (("down", "C"), 12)],
    '6c': [(("right",), 6), (("right", "C"), 12)],
    'j5b': [(("up",), 6), (("up",), 2), (("B",), 14)],
    'j2b': [(("up",), 6), (("down",), 2), (("down", "B"), 14)],
    'j5c': [(("up",), 6), (("up",), 2), (("C",), 14)],
    'j2c': [(("up",), 6), (("down",), 2), (("down", "C"), 14)],
    # 冲刺
    '66': [(("right", "D"), 8)],
    '44': [(("left", "D"), 8)],
    'hj8': [(("down",), 4), (("up",), 8)],
    'hj9': [(("down",), 4), (("up", "right"), 8)],
    # 纯方向步(移动/高跳指示)
    '6': [(("right",), 6)],
    '4': [(("left",), 6)],
    '8': [(("up",), 6)],
    '2': [(("down",), 6)],
    'd6': [(("right", "D"), 6)],
    'd4': [(("left", "D"), 6)],
    # f前缀远距离版(与近版同输入, 距离自动替换)
    'f5a': [(("A",), 10)],
    'f2a': [(("down",), 6), (("down", "A"), 10)],
}


def move_keys(token):
    """记法令牌→键步列表; None=无法转换。"""
    raw = token.lower()
    # scN → "sc:N" 步(符卡状态机)
    m_sc = re.match(r'^(?:j)?sc(\d+)$', raw)
    if m_sc:
        return [("sc:%s" % m_sc.group(1), 0)]
    # dskillNb/c → 必杀技N(装配相关, 转为对应236/623/214指令)
    m_sk = re.match(r'^d?(?:j)?skill(\d)([bc])$', raw)
    if m_sk:
        n, btn = int(m_sk.group(1)), m_sk.group(2).upper()
        dirs = {1: '236', 2: '623', 3: '214', 4: '214', 5: '22'}.get(n, '236')
        seq = {'236': ['down', 'down+right', 'right'],
               '623': ['right', 'down', 'down+right'],
               '214': ['left', 'down', 'left'],
               '22': ['down', 'down']}[dirs]
        steps = []
        for d in seq:
            steps.append((tuple(d.split('+')), 3))
        last = tuple(sorted(set(seq[-1].split('+')) | {btn}))
        steps.append((last, 10))
        return steps
    m = raw.replace('/', '')
    m = re.sub(r'^d(?=[a-z2-9])', '', m)   # d前缀=冲刺取消(暂不模拟)
    # 逐级匹配: 精确→前缀剥离
    for prefix in ('hj', 'j', ''):
        body = m[len(prefix):] if m.startswith(prefix) else None
        if body and body in MOVE_SCRIPT:
            return list(MOVE_SCRIPT[body])
    # 5aa系(连段后续段=再按A)
    if re.match(r'^5a{2,5}$', m):
        n_a = len(m) - 1
        return [(("A",), 6)] * n_a
    # 必杀指令
    skill = re.match(r'^([2236]+)([bc])$', m)
    if skill:
        dirs_str, btn = skill.group(1), skill.group(2).upper()
        seq = {'236': ['down', 'down+right', 'right'],
               '623': ['right', 'down', 'down+right'],
               '214': ['left', 'down', 'left'],
               '22': ['down', 'down']}.get(dirs_str)
        if seq is None:
            return None
        steps = []
        for d in seq:
            steps.append((tuple(d.split('+')), 3))
        last = tuple(sorted(set(seq[-1].split('+')) | {btn}))
        steps.append((last, 10))
        return steps
    return None


def combo_to_macro(steps, name):
    """Trialmode步骤列表 → (name, script)宏元组。
    R39(第十轮§4-2): confirm门原插在首token后 — TM连段首token是走路/
    蹲置/跳(4帧内无伤害) → 门几乎必然截断, 6个宏成近乎死槽。改为插在
    **首个攻击步**(含A/B/C的步)前: 前置移动步直接放行, 首个攻击命中才续。
    各步间按帧偏移差插入等待帧。"""
    script = []
    prev_frame = None
    gated = False
    for s in steps:
        mv = s.get('move')
        if not mv:
            continue
        ks = move_keys(mv)
        if ks is None:
            return None, mv    # 含不可转换招
        fr = s.get('frame')
        if fr is not None and prev_frame is not None:
            gap = fr - prev_frame
            if gap > 2:
                script.append(((), min(gap, 30)))
        is_attack = any(any(b in kt for b in ("A", "B", "C"))
                        for kt, _f in ks)
        if is_attack and not gated:
            # R39: 完整发招(前置蹲/走+攻击键自然时长) → 松键 → confirm门
            # (对齐手写"2A确认"形状: 门在攻击键**之后**观测d_deal;
            # 原版把门放在ks[0]后=攻击键按下前, 4帧无伤害必然截断)
            *pre, (last_keys, last_f) = ks
            script.extend(pre)
            script.append((last_keys, min(last_f, 10)))
            script.append(((), 2))
            script.append(("confirm", 0))
            gated = True
        else:
            script.extend(ks)
        prev_frame = fr
    return (name, script), None


def main():
    """输出可直接追加的宏定义(Python代码片段)。"""
    chars = ['reimu', 'marisa', 'suika']
    max_per = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    PACKS = {
        'reimu': ['白天子-灵梦连段包，直接解压里面的东西即可.zip'],
        'marisa': ['marisa_小朔士.zip'],
        'suika': ['[Finished]Suika_xianxiang 现象.zip'],
    }
    for ch in chars:
        combos = []
        for pk in PACKS[ch]:
            combos.extend(load_pack(pk))

        def _diff(steps):
            exact = sum(1 for s in steps if s.get('exact'))
            n = len(steps)
            has_sc = any('sc' in (s['move'] or '') for s in steps)
            return exact * 2 + (n > 8) * 2 + (n > 11) * 2 + has_sc * 1

        ok_list = []
        for c in combos:
            if _diff(c['steps']) > 5 or len(c['steps']) > 8:
                continue
            moves = '_'.join(s['move'] for s in c['steps'])[:18]
            macro, _bad = combo_to_macro(c['steps'], 'TM·%s' % moves)
            if macro:
                ok_list.append((c, macro))
        ok_list.sort(key=lambda x: -x[0]['min_damage'])
        print('# ==== %s: 追加%d条(安全/中等, 末位) ====' % (ch, max_per))
        for c, (name, script) in ok_list[:max_per]:
            steps_repr = []
            for k, f in script:
                if isinstance(k, str):
                    steps_repr.append('("%s", 0)' % k)
                else:
                    steps_repr.append('((%s), %d)'
                                      % (', '.join('"%s"' % x for x in k), f))
            print('    ("%s",\n     [%s]),\n'
                  '    # Trialmode %d伤 %d段' % (name, ',\n      '.join(steps_repr),
                                                 c['min_damage'],
                                                 len(c['steps'])))


if __name__ == '__main__':
    main()
