# -*- coding: utf-8 -*-
"""JZ-2: 全员打击技发生帧表生成 (zonghe.txt outline_80-92 → startup_frames.json)

来源: 00-综合攻略20200409.chm outline_80-92 (菜菜整理, 数据自wiki百科,
      1.10版本口径), gb18030全文提取件逐行解析 — 每条目带行号出处。
纪律: 只转录不推算; 攻略未给的角色显式 null; 多段招/特殊形态保留括注。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(os.path.dirname(ROOT), '_extracted', 'zonghe.txt')

# 攻略称谓 → 项目角色键(macros/文件名同源)
NAME2KEY = {
    '霊夢': 'reimu', '灵梦': 'reimu',
    '魔理沙': 'marisa',
    '咲夜': 'sakuya',
    '妖夢': 'youmu', '妖梦': 'youmu',
    '爱丽丝': 'alice', 'アリス': 'alice',
    '帕秋莉': 'patchouli', 'パチェ': 'patchouli',
    '雷米莉亚': 'remilia',
    '幽々子': 'yuyuko',
    '鈴仙': 'reisen', '铃仙': 'reisen',
    '萃香': 'suika',
    '文': 'aya',
    '紫': 'yukari',
    '小町': 'komachi', '町': 'komachi',
    '衣玖': 'iku',
    '天子': 'tenshi',
    '早苗': 'sanae',
    '⑨': 'cirno', 'チルノ': 'cirno',
    '美鈴': 'meiling',
    '空': 'utsuho',
    '諏訪子': 'suwako', '诹访子': 'suwako',
}
ALL_KEYS = ['reimu', 'marisa', 'sakuya', 'youmu', 'alice', 'patchouli',
            'remilia', 'yuyuko', 'reisen', 'suika', 'aya', 'yukari',
            'komachi', 'iku', 'tenshi', 'sanae', 'cirno', 'meiling',
            'utsuho', 'suwako']

# 段落名 → (招式键, 招式名)
SECTIONS = {
    80: ('near_a', '近A/4A'), 81: ('far_a', '远A'), 82: ('low_a', '2A'),
    83: ('f6a', '6A'), 84: ('f3a', '3A'), 85: ('da', 'DA'),
    86: ('db', 'DB'), 87: ('dc', 'DC'), 88: ('ja', 'JA'),
    89: ('j6a', 'J6A'), 90: ('j8a', 'J8A'), 91: ('j2a', 'J2A'),
}


def parse_name(tok):
    """'紫(中心)' → ('yukari', '中心'); 未闭合括号也按括注截断; None=无法归键."""
    tok = tok.strip().rstrip('、').strip()
    m = re.match(r'^(.+?)[（(](.*?)[）)]?$', tok)
    base, note = (m.group(1).strip(), m.group(2).strip()) if m else (tok, '')
    key = NAME2KEY.get(base)
    return key, note


def main():
    lines = open(SRC, encoding='utf8').read().splitlines()
    # 定位正文段(行号=索引+1): 第二次出现的 outline 段头在1331行起
    heads = [(i + 1, l) for i, l in enumerate(lines)
             if l.startswith('##### outline_')]
    body_heads = [(ln, int(re.search(r'(\d+)', l).group(1)))
                  for ln, l in heads if ln > 1000]

    moves = {}
    coverage_notes = []
    for idx, (ln, oid) in enumerate(body_heads):
        if oid not in SECTIONS:
            continue
        key, disp = SECTIONS[oid]
        end = body_heads[idx + 1][0] - 1 if idx + 1 < len(body_heads) else len(lines)
        entries = []          # [{char, frames, note, line}]
        per_char = {}         # key → 已见(多段合并)
        section_note = ''
        for n in range(ln + 1, end + 1):
            text = lines[n - 1].strip()
            if not text:
                continue
            m = re.match(r'^(\d+)F?\s*[：:\s](.*)$', text)
            if m and m.group(2).strip():
                frames = int(m.group(1))
                for tok in m.group(2).split('、'):
                    if not tok.strip():
                        continue
                    ck, note = parse_name(tok)
                    if ck is None:
                        coverage_notes.append('line %d: 无法归键 "%s" (%s)'
                                              % (n, tok, disp))
                        continue
                    entries.append({'char': ck, 'frames': frames,
                                    'note': note or None, 'line': n})
                continue
            if text.startswith('注：'):
                section_note = text
        # 覆盖统计: 主形态(无note或非第二段)缺失者显式null
        have = {e['char'] for e in entries}
        for ck in ALL_KEYS:
            if ck not in have:
                entries.append({'char': ck, 'frames': None,
                                'note': '攻略未给出', 'line': None})
        moves[key] = {'display': disp,
                      'source': 'zonghe.txt outline_%d (line %d起)' % (oid, ln),
                      'entries': sorted(entries, key=lambda e: ALL_KEYS.index(e['char'])),
                      'section_note': section_note or None}

    # 羽衣(身代わり人形反击卡) outline_92: 数字列被折行, 单独解析
    hagoromo = {'display': '羽衣(身代わり人形反击)', 'unit': 'F',
                'includes': '攻略口径含暗转15F',
                'source': 'zonghe.txt outline_92 (line 1480起)',
                'columns': ['startup', 'active', 'total'],
                'rows': []}
    ln92 = next(ln for ln, oid in body_heads if oid == 92)
    ln93 = next(ln for ln, oid in body_heads if oid == 93)
    nums_buf, cur_char = [], None
    for n in range(ln92 + 1, ln93):
        text = lines[n - 1].strip()
        m = re.match(r'^(.+?)\s+(\d+)\s+(\d+)$', text)
        if m and parse_name(m.group(1))[0]:
            cur_char = parse_name(m.group(1))
            nums_buf = [int(m.group(2)), int(m.group(3))]
            continue
        if re.match(r'^\d+$', text) and cur_char and len(nums_buf) == 2:
            hagoromo['rows'].append({'char': cur_char[0],
                                     'startup': nums_buf[0],
                                     'active': nums_buf[1],
                                     'total': int(text), 'line': n})
            cur_char, nums_buf = None, []
            continue
        # 折行形态B: "名 28" 已入buf, 本行 "持続 全体" 两数字
        if re.match(r'^\d+\s+\d+$', text) and cur_char and len(nums_buf) == 1:
            a, b = text.split()
            hagoromo['rows'].append({'char': cur_char[0],
                                     'startup': nums_buf[0],
                                     'active': int(a),
                                     'total': int(b), 'line': n})
            cur_char, nums_buf = None, []
            continue
        if re.match(r'^(.+?)\s+(\d+)$', text) and parse_name(
                re.match(r'^(.+?)\s+(\d+)$', text).group(1))[0] and not nums_buf:
            mt = re.match(r'^(.+?)\s+(\d+)$', text)
            cur_char = parse_name(mt.group(1))
            nums_buf = [int(mt.group(2))]
            continue
        if re.match(r'^\d+$', text) and cur_char and len(nums_buf) == 1:
            nums_buf.append(int(text))
            continue
        if re.match(r'^\d+$', text) and cur_char and len(nums_buf) == 2:
            hagoromo['rows'].append({'char': cur_char[0],
                                     'startup': nums_buf[0],
                                     'active': nums_buf[1],
                                     'total': int(text), 'line': n})
            cur_char, nums_buf = None, []

    out = {
        'source': '00-综合攻略20200409.chm outline_80-91 (菜菜·全人物A系帧数表'
                  '对比1.10, 数据来自wiki百科), zonghe.txt全文提取件, 2026-10-14生成',
        'script': 'tools/jz2_startup_frames.py (逐行解析, 每条目带行号)',
        'columns': 'frames=发生(攻击判定出现)帧; note保留攻略括注(多段/特殊形态/L态)',
        'version_note': '1.10版本口径; 攻略作者声明"有的是自己排的有的是wiki排过的'
                        '然后一一检查的"',
        'moves': moves,
        'hagoromo_counter_card': hagoromo,
        'known_estimates': [
            {'char': 'suwako', 'move': 'DA',
             'note': '攻略注: 青蛙(suwako)的DA未给出准确发生数据, 作者估10-11F间'
                     ' — 估测不作为数据入表, 该位为null', 'line': 1398}
        ],
    }
    dst = os.path.join(ROOT, 'data', 'guide_tables', 'startup_frames.json')
    with open(dst, 'w', encoding='utf8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # 覆盖审计输出
    print('== 生成 %s ==' % dst)
    for key, mv in moves.items():
        missing = [e['char'] for e in mv['entries'] if e['frames'] is None]
        n_e = sum(1 for e in mv['entries'] if e['frames'] is not None)
        print('%-7s %-8s %2d条 无数据: %s' %
              (key, mv['display'], n_e, ','.join(missing) or '-'))
    print('羽衣: %d/20行' % len(hagoromo['rows']))
    for cnote in coverage_notes:
        print('!! ', cnote)


if __name__ == '__main__':
    main()
