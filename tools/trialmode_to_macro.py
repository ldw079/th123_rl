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
    '4b': [(("left",), 6), (("left", "B"), 10)],
    '4c': [(("left",), 6), (("left", "C"), 12)],
    '1a': [(("down", "left"), 6), (("down", "left", "A"), 12)],
    '5': [((), 6)],          # 中立微步(择一记法"5/x"首项)
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
    # 从零#2(产品面P2): hj全方向族(原只有8/9 — hj7等60+次被拒)
    'hj7': [(("down",), 4), (("up", "left"), 8)],
    'hj6': [(("down",), 4), (("up", "right"), 8)],
    'hj4': [(("down",), 4), (("up", "left"), 8)],
    'hj2': [(("down",), 4), (("down",), 8)],
    # 纯方向步(移动/高跳指示) — 小键盘全方向(原缺1/3/7/9)
    '6': [(("right",), 6)],
    '4': [(("left",), 6)],
    '8': [(("up",), 6)],
    '2': [(("down",), 6)],
    '1': [(("down", "left"), 6)],
    '3': [(("down", "right"), 6)],
    '7': [(("up", "left"), 6)],
    '9': [(("up", "right"), 6)],
    'd6': [(("right", "D"), 6)],
    'd4': [(("left", "D"), 6)],
    # 冲刺攻击(66a/b/c = DA系 — 原171+次被拒)
    '66a': [(("right", "D"), 8), ((), 2), (("A",), 10)],
    '66b': [(("right", "D"), 8), ((), 2), (("B",), 10)],
    '66c': [(("right", "D"), 8), ((), 2), (("C",), 12)],
    # 空中冲刺(j{dir}d族 — 空中D+方向=飞行, 输入同地面冲刺)
    'j2d': [(("down", "D"), 6)],
    'j3d': [(("down", "right", "D"), 6)],
    'j6d': [(("right", "D"), 6)],
    'j9d': [(("up", "right", "D"), 6)],
    'j7d': [(("up", "left", "D"), 6)],
    'j4d': [(("left", "D"), 6)],
    'j1d': [(("down", "left", "D"), 6)],
    'j8d': [(("up", "D"), 6)],
    # f前缀远距离版(与近版同输入, 距离自动替换)
    'f5a': [(("A",), 10)],
    'f2a': [(("down",), 6), (("down", "A"), 10)],
}


def move_keys(token):
    """记法令牌→键步列表; None=无法转换。
    从零#2(产品面P2)三修:
    (a) 精确匹配必须先于前缀剥离 — 原循环先剥'j'再查表, j5a/j6a/
        j2a/j8a/j5b/j2b/j5c/j2c全部退化为地面版(占全token约30%,
        空中连段整体错键), d6/d4被d-strip抢走退化成走路;
    (b) 择一记法"x/y"取首项(原replace('/','')拼成乱码必拒);
    (c) 运动记法字符类[2236]不含1/4 → 214系(d214b/a1236b等)
        全拒 — 放宽到[1-9]按尾姿映射。
    """
    raw = token.lower().split('/')[0]     # 择一记法取首项
    # 从零#2: 罕见前缀族归一化(l=面向左变体/ud=取消/hjd9=高跳dash/
    # j6d2=空中dash复合 — 各数十次, 归一到基础记法近似)
    raw = re.sub(r'^ud(?=[1-9])', '', raw)
    raw = re.sub(r'^l(?=[1-9hjs])', '', raw)
    raw = re.sub(r'^u(?=sc)', '', raw)           # usc202 → sc202
    raw = re.sub(r'^[su](?=[1-9])', '', raw)     # s/u取消前缀(护住sc:)
    if raw.startswith('hjd') and ('hj' + raw[3:]) in MOVE_SCRIPT:
        raw = 'hj' + raw[3:]
    raw = re.sub(r'^(j[1-9]d)[1-9]$', r'\1', raw)
    # scN → "sc:N" 步(符卡状态机)
    m_sc = re.match(r'^(?:j)?sc(\d+)$', raw)
    if m_sc:
        return [("sc:%s" % m_sc.group(1), 0)]
    # dskillNb/c → 必杀技N(装配相关, 转为对应236/623/214指令)
    m_sk = re.match(r'^d?(?:j)?skill(\d)([bc])$', raw) \
        or re.match(r'^(?:[adj]{0,2})[1-9]?skill([1-9])([bc])$', raw)
    if m_sk:
        n, btn = int(m_sk.group(1)), m_sk.group(2).upper()
        dirs = {1: '236', 2: '623', 3: '214', 4: '214', 5: '22'}.get(n, '236')
        seq = {'236': ['down', 'down+right', 'right'],
               '623': ['right', 'down', 'down+right'],
               '214': ['down', 'down+left', 'left'],
               '22': ['down', 'down']}[dirs]
        steps = []
        for d in seq:
            steps.append((tuple(d.split('+')), 3))
        last = tuple(sorted(set(seq[-1].split('+')) | {btn}))
        steps.append((last, 10))
        return steps
    m = raw.replace('/', '')
    # 精确匹配优先(死路径修复(a)) — j5a/hj8/d6等全条目复活
    if m in MOVE_SCRIPT:
        return list(MOVE_SCRIPT[m])
    m = re.sub(r'^d(?=[a-z2-9])', '', m)   # d前缀=冲刺取消(精确条目之后)
    # 逐级匹配: 精确→前缀剥离
    for prefix in ('hj', 'j', ''):
        body = m[len(prefix):] if m.startswith(prefix) else None
        if body and body in MOVE_SCRIPT:
            return list(MOVE_SCRIPT[body])
    # 5aa系(连段后续段=再按A; 含空中j5aa — 剥j后匹配)
    _body5 = m[1:] if m.startswith('j') else m
    if re.match(r'^5a{2,5}$', _body5):
        n_a = len(_body5) - 1
        return [(("A",), 6)] * n_a
    # 必杀指令 — 从零#2(c): [1-9]全数字+按尾姿映射(214系复活);
    # 容许复合前缀(a=取消/j=空中/d=冲刺: a1236b/ja1236b族)
    skill = re.match(r'^(?:[adj]{0,2})([1-9]{2,8})([bc])$', m)
    if skill:
        dirs_str, btn = skill.group(1), skill.group(2).upper()
        seq = _motion_seq(dirs_str)
        if seq is None:
            return None
        steps = []
        for d in seq:
            steps.append((tuple(d.split('+')), 3))
        last = tuple(sorted(set(seq[-1].split('+')) | {btn}))
        steps.append((last, 10))
        return steps
    return None


def _motion_seq(dirs_str):
    """运动记法→姿态序列(从零#2: 未知长运动按尾姿近似映射)。"""
    known = {'236': ['down', 'down+right', 'right'],
             '623': ['right', 'down', 'down+right'],
             '214': ['down', 'down+left', 'left'],
             '421': ['down', 'down+left', 'left'],
             '22': ['down', 'down']}
    if dirs_str in known:
        return known[dirs_str]
    tail = dirs_str[-3:] if len(dirs_str) >= 3 else dirs_str
    if tail in known:
        return known[tail]
    # 尾姿近似: 末位定终点(6=前, 4/1=后, 2=下)
    last_d = dirs_str[-1]
    if last_d in ('6', '3'):
        return known['236']
    if last_d in ('4', '1', '7'):
        return known['214']
    if last_d == '2':
        return known['22']
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
