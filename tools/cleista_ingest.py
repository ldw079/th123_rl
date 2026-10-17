# -*- coding: utf-8 -*-
"""cleista帧数据入档(JZ-2数据源升级, 用户2026-10-14裁定权威源):
用户手工提取的txt(反爬期) → data/guide_tables/cleista/{char}.json
(source=cleista逐条标注; 文件名互换如实记录; 后续站直连时同格式续入)。

格式: 招式 | 发生帧 | 持续帧 | 硬直差[防御/命中/破防三轨] | 伤害 | 备注
marisa数据暂缺(反爬未取得) — 不编造, 占位null。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf8')

# 用户提取件: 文件名与内容互换(萃香数据.txt实为灵梦) — 按内容角色入档
# P0-2(从零#5): 用户家目录输入档用 expanduser(不钉用户名), TH123_CLEISTA_SRC 可覆盖
_HOME = os.path.expanduser('~')
_OVR = os.environ.get('TH123_CLEISTA_SRC', '')
SOURCES = [
    (os.path.join(_OVR or os.path.join(_HOME, 'Downloads'), '萃香数据.txt'), 'reimu'),
    (os.path.join(_OVR or os.path.join(_HOME, 'Downloads'), '灵梦数据.txt'), 'suika'),
]

SEC_RE = re.compile(r'^[一二三四]、(.+)$')
ROW_RE = re.compile(
    r'^(?P<move>.+?)\s*\|\s*(?P<startup>[\d+f\s+]*\d+f?|—)\s*\|\s*'
    r'(?P<total>\d+f|—)\s*\|\s*(?P<adv>.+?)\s*\|\s*(?P<adv2>.*?)\s*\|\s*'
    r'(?P<adv3>.*?)\s*\|\s*(?P<dmg>[\d—]+)\s*\|\s*(?P<note>.*)$')


def parse_num(s):
    s = s.strip()
    if not s or s == '—':
        return None
    m = re.match(r'^(\d+)f$', s)
    if m:
        return int(m.group(1))
    m = re.match(r'^([+-]?\d+)$', s)
    if m:
        return int(m.group(1))
    # 复合发生(符卡 "13+28f")
    m = re.match(r'^(\d+)\+(\d+)f$', s)
    if m:
        return [int(m.group(1)), int(m.group(2))]
    return None


def parse_txt(path):
    rows = []
    section = '普通技'
    for line in open(path, encoding='utf8'):
        line = line.strip()
        if not line or line.startswith('=') or line.startswith('---') \
                or line.startswith('来源') or line.startswith('导出') \
                or line.startswith('字段说明') or line.startswith('说明') \
                or line.startswith('东方非想天则') or line == '完':
            m = SEC_RE.match(line)
            if m:
                section = m.group(1)
            continue
        m = SEC_RE.match(line)
        if m:
            section = m.group(1)
            continue
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 5:
            continue
        move = parts[0]
        startup = parse_num(parts[1])
        total = parse_num(parts[2])
        # 硬直差轨: 单列或三列(防御/命中/破防)
        adv_parts = parts[3:-2]
        adv = None
        if adv_parts:
            adv = [parse_num(p) for p in adv_parts]
            if len(adv) == 1:
                adv = adv[0]
        dmg = parse_num(parts[-2])
        note = parts[-1]
        rows.append({'move': move, 'section': section,
                     'startup': startup, 'total': total,
                     'advantage': adv, 'damage': dmg, 'note': note or None})
    return rows


def main():
    out_dir = os.path.join(ROOT, 'data', 'guide_tables', 'cleista')
    os.makedirs(out_dir, exist_ok=True)
    for path, char in SOURCES:
        rows = parse_txt(path)
        # 蓄力行抽取(charge[...]记法)
        charged = [r for r in rows if '[' in r['move']]
        out = {
            'source': 'https://soku.cleista.cc/framedata(%s) — 用户手工'
                      '提取(反爬期), 文件名互换已按内容纠正, 2026-10-14' % char,
            'authority': '用户2026-10-14裁定权威源(游戏内部数据派生), '
                         'CHM降为交叉验证源',
            'fields': 'startup=发生帧; total=持续(全体); advantage=硬直差'
                      '(单值或[防御,命中,破防]三轨); note含逐帧属性窗',
            'rows': rows,
            'charged_rows': len(charged),
        }
        dst = os.path.join(out_dir, '%s.json' % char)
        with open(dst, 'w', encoding='utf8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print('%s: %d行(蓄力%d) → %s' % (char, len(rows), len(charged), dst))


if __name__ == '__main__':
    main()
