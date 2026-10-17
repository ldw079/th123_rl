# -*- coding: utf-8 -*-
"""LE-2表提取·第一步: fangyu攻略逐角色章节索引(结构+锚点).

源: %USERPROFILE%/Desktop/workplace/_extracted/fangyu.txt (CHM反编译全文,
4341行) — TOC(行1~447) + 正文("##### outline_N.htm [enc]"分节).

产出: data/guide_tables/fangyu_index.json
  chapters: 逐角色 {角色中文名, wiki锚行, 子节: {类别: 正文行号}}
  警戒类别(可结构化枚举的): 需要警戒的通常技/必杀/SC, 一击破防属性攻击,
  空防不可攻击, 各状况的对策, 防御和推版对策, 需要注意的天气, 凹升龙,
  铜钱, 刹那成立, 必杀技相性
深解析(逐招文本→动作ID映射)留下批(R4: 空表优于错表).
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf8')

SRC = r'%USERPROFILE%\Desktop\workplace\_extracted\fangyu.txt'
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'data', 'guide_tables', 'fangyu_index.json')

# 警戒子节类别(TOC Name精确匹配)
CATEGORIES = (
    '特征', '需要警戒的通常技', '需要警戒的通常技/必杀/SC',
    '需要警戒的必杀/SC', '一击破防属性攻击', '空防不可攻击',
    '必杀技相性', '各状况的对策', '防御和推版对策', '需要注意的天气',
    '凹升龙', '铜钱', '刹那成立',
)

CN2KEY = {  # 中文名→库键(20角色; 未映射=表外)
    '博丽灵梦': 'reimu', '博丽霊梦': 'reimu',  # 简繁变体
    '雾雨魔理沙': 'marisa', '十六夜咲夜': 'sakuya',
    '魂魄妖梦': 'youmu', '红美铃': 'meiling', '帕秋莉': 'patchouli',
    '爱丽丝': 'alice', '蕾米莉亚': 'remilia', '芙兰朵露': 'flandre?',
    '伊吹萃香': 'suika', '橙': 'ran?', '八云蓝': 'ran?', '八云紫': 'yukari',
    '射命丸文': 'aya', '莉格露': 'wriggle?', '米斯蒂娅': 'mystia?',
    '犬走椛': 'momiji?', '河城荷取': 'nitori?', '东风谷早苗': 'sanae',
    '比那名居天子': 'tenshi', '永江衣玖': 'iku', '琪露诺': 'cirno',
    '灵乌路空': 'utsuho', '泄矢诹访子': 'suwako', '铃仙': 'reisen',
    '蓬莱山辉夜': 'kaguya?', '藤原妹红': 'mokou?', '小町': 'komachi',
    '四季映姬': 'sikieiki?', '姬海棠羽立': 'hatate?',
}


def main():
    lines = io.open(SRC, encoding='utf8', errors='replace').read().splitlines()
    # 1) TOC解析: Local: outline_N → (Name栈) 映射
    toc = {}          # outline_N -> 角色中文名(最近的祖先角色名)
    cur_chars = []    # 嵌套角色名栈
    last_outline = None
    toc_order = []    # (outline_N, char_cn, section_name)
    cur_sec = None
    for ln in lines[:447]:
        m = re.match(r'\s*Name: (.+)', ln)
        if m:
            nm = m.group(1).strip()
            cur_sec = nm
            if nm in CN2KEY:
                cur_chars.append(nm)
            continue
        m = re.match(r'\s*Local: .*/(outline_\d+)\.htm', ln)
        if m and cur_chars:
            last_outline = m.group(1)
            toc[last_outline] = (cur_chars[-1], cur_sec)
            toc_order.append((last_outline, cur_chars[-1], cur_sec))
    # 2) 正文锚点: ##### outline_N 行号
    anchors = {}
    for i, ln in enumerate(lines):
        m = re.match(r'##### (outline_\d+)\.htm', ln)
        if m:
            anchors[m.group(1)] = i + 1   # 1-based
    # 3) 章节/类别组装
    chapters = {}
    for ol, char_cn, sec in toc_order:
        if sec not in CATEGORIES or ol not in anchors:
            continue
        key = CN2KEY.get(char_cn)
        ent = chapters.setdefault(char_cn, {
            'char_key': key if key and '?' not in key else None,
            'sections': {}})
        ent['sections'][sec] = anchors[ol]
    # 4) 章节正文抽样长度(锚点到下一个#####)
    ol_sorted = sorted(anchors.items(), key=lambda kv: kv[1])
    lens = {}
    for idx, (ol, ln_no) in enumerate(ol_sorted):
        end = ol_sorted[idx + 1][1] if idx + 1 < len(ol_sorted) \
            else len(lines) + 1
        lens[ol] = end - ln_no
    for ent in chapters.values():
        for sec, ln_no in list(ent['sections'].items()):
            ol = next((o for o, (c, s) in toc.items()
                       if s == sec and toc and anchors.get(o) == ln_no), None)
    # 简化: 直接给行区间(锚点+下一锚点)
    for ent in chapters.values():
        for sec, ln_no in list(ent['sections'].items()):
            nxt = min((a for a in anchors.values() if a > ln_no),
                      default=len(lines) + 1)
            ent['sections'][sec] = [ln_no, nxt]

    out = {
        'source': 'CHM攻略fangyu篇反编译全文(fangyu.txt, 4341行) '
                  'TOC+正文锚点索引 — LE-2表提取第一步(结构层)',
        'note': '深解析(逐招文本→动作ID/宏映射)留下批; R4空表优于错表',
        'n_chapters': len(chapters),
        'chapters': chapters,
    }
    io.open(OUT, 'w', encoding='utf8').write(
        json.dumps(out, ensure_ascii=False, indent=1))
    print('章节: %d' % len(chapters))
    for cn, ent in sorted(chapters.items()):
        cats = [c for c in CATEGORIES if c in ent['sections']]
        print('%-10s %-8s %2d类别' % (cn, ent['char_key'] or '?', len(cats)))
    print('→ %s' % OUT)


if __name__ == '__main__':
    main()
