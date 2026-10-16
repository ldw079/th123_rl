# -*- coding: utf-8 -*-
"""JZ-2: 射击相杀(抵消)规则+强度矩阵生成 → bullet_clash.json

规则文本: system.txt outline_100-103 (line 1493-1552), SF数据大全。
矩阵: 各角色CHM技表两种版式 —
  A) 统一版式(黑白/红白系): [技能名称|HIT数|相杀(强度,回数)|擦弹耐久|备考]
  B) 转置版式(西瓜系): 每招一块, 属性做行(伤害/Rate/.../受身不能/削灵/...
     天气玉/强度/击中效果/...), 本脚本取"强度"行值。
覆盖度: 逐角色统计(有表/无表/CHM未解出), 未覆盖显式登记不编造。
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# clash_all 索引 → (角色键, CHM名) — 与批解压日志一致(2026-10-14);
# 空格文件名CHM经无空格中转复解(2026-10-14晚, remilia/patchouli/alice/
# reimu3·4/reisen 6卷补齐)
IDX2CHAR = {
    3: 'suika', 4: 'yukari', 5: 'yuyuko', 6: 'remilia', 7: 'youmu',
    8: 'patchouli', 9: 'alice', 10: 'sakuya', 12: 'marisa',
    13: 'reimu', 14: 'reimu', 15: 'reimu', 16: 'reimu',
    17: 'reimu', 18: 'reimu',
    19: 'sanae', 20: 'cirno', 21: 'meiling', 22: 'utsuho', 23: 'suwako',
    24: 'reisen', 25: 'aya', 26: 'komachi', 27: 'iku', 28: 'tenshi',
}
DECOMPILE_FAILED = ['marisa自编版(11, 水杨酸 — 非权威, 不采用)']

RULES = {
    'source': 'system.txt outline_100-103 (lines 1493-1552), SF数据大全, 2026-10-14提取',
    'strength_levels': ['S', 'A', 'B', 'C'],
    'strength_rule': '强度高者可瞬间将强度低者的抵消判定减到0(与绯想天不同); '
                     '强度相同时双方抵消判定同时减少',
    'principles': {
        'A_强度原则': {'line': 1504, 'text': '强度高者瞬间清零低者; 同级同时减1, '
                     '抵消判定归0时攻击判定同时消失'},
        'B_倒数原则': {'line': 1509, 'text': '同级时每个射击技每F只被减1次抵消判定, '
                     'N次判定至少存在N F; 高速多判定弹(帕秋莉C夏日红)可贯穿同级'},
        'C_覆盖原则': {'line': 1519, 'text': '自身强度≥对方时, 抵消发生1F内可减少'
                     '自身判定内任意个单个射击技的抵消判定 — 判定大者在弹幕战占优'},
        'D_残留原则': {'line': 1521, 'text': '被抵消的射击技至少残留1F攻击判定, '
                     '站在抵消判定边缘不安全'},
    },
    'pierce': {'name': '贯穿', 'line': 1500,
               'text': '不带抵消判定的射击技相遇不产生抵消现象, 如幽幽子的C射击'},
    'proxy_strike': {'name': '代打击判定(身代判定)', 'line': 1528,
                     'text': '带被攻击判定和体力的招式(爱丽丝人偶/妖梦半灵)按体力'
                     '抵消攻击; 至少挡1HIT; 不受修正影响; 对激光类无效; '
                     '乱舞SC/投技命中代打后无后续演出'},
    'reflection': {'name': '射击反射', 'line': 1544,
                   'text': '妖梦反射下界斬/衣玖羽衣は風の如く可反射部分射击; '
                   '垂直镜面折回; 对贯穿/激光/设置/爆炸/SC多数无效'},
    'laser_note': {'line': 1513, 'text': '激光抵消判定与HIT数脱钩: 魔理沙6C 10HIT'
                  '只有2次抵消判定, 连灵梦C射都无法穿透'},
}


def cells_of(tr_html):
    cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr_html, re.S | re.I)
    return [re.sub(r'<[^>]+>', '', c).replace('&nbsp;', ' ').strip()
            for c in cells]


def page_text(path):
    raw = open(path, 'rb').read()
    for enc in ('gb18030', 'utf-8'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode('gb18030', 'replace')


def page_title(t):
    h = re.search(r'<h\d[^>]*>(.*?)</h\d>', t, re.S | re.I)
    return re.sub(r'<[^>]+>', '', h.group(1)).strip() if h else ''


def parse_unified(rows):
    """版式A: 返回rows列表或None(不匹配)."""
    if not rows:
        return None
    head = ' '.join(cells_of(rows[0]))
    if '技能名称' not in head or ('相杀' not in head and '相殺' not in head):
        return None
    out = []
    for r in rows[2:]:                      # 跳过表头+强度/回数子表头
        cs = cells_of(r)
        if not cs:
            continue
        if cs[0].startswith('技能名称') or '攻击' in cs[0:2] and '分类' in ' '.join(cs[0:3]):
            break                           # 合体表的第二张表开始了
        if len(cs) < 4:
            continue
        out.append({'move': ' '.join(cs[0].split()), 'hit': cs[1],
                    'strength': cs[2], 'times': cs[3],
                    'graze': cs[4] if len(cs) > 4 else '',
                    'note': ' '.join(' '.join(cs[5:]).split()) or None})
    return out or None


CLASH_VAL = re.compile(r'^(S|A|B|C)$')
LEVEL_VAL = re.compile(r'^(小|中|大|特大)$')


def classify_transposed(rows):
    """转置版式: 按强度值域分流 — S/A/B/C=相杀强度(弹幕表),
    小/中/大/特大=攻击等级(体术表, 语义不同另存). 返回(clash, levels)."""
    clash, levels = [], []
    cur_move = None
    for i, r in enumerate(rows):
        cs = cells_of(r)
        if not cs:
            continue
        if cs[0].strip() == '指令' and len(cs) > 1 and cs[1].strip():
            cur_move = cs[1].strip()
            continue
        if '强度' in cs and cur_move:
            try:
                k = cs.index('强度')
            except ValueError:
                k = next(j for j, c in enumerate(cs) if '强度' in c)
            val = None
            for j in range(i + 1, min(i + 3, len(rows))):   # 值行紧跟标签行
                vs = cells_of(rows[j])
                if len(vs) > k and vs[k].strip():
                    val = ' '.join(vs[k].split())
                    break
            if val is None:
                cur_move = None
                continue
            if cur_move in ('名称', '技能名称', '指令'):    # 图例页示例行
                cur_move = None
                continue
            if CLASH_VAL.match(val):
                clash.append({'move': cur_move, 'strength': val})
            elif all(LEVEL_VAL.match(v) for v in val.split()):
                levels.append({'move': cur_move, 'attack_level': val})
            cur_move = None
    return clash, levels


def main():
    chars = {}
    coverage = {}
    for idx, key in sorted(IDX2CHAR.items()):
        d = r'D:/temp/clash_all/%02d' % idx
        pages = sorted(glob.glob(d + '/*/outline_*.htm'),
                       key=lambda p: int(re.search(r'(\d+)', os.path.basename(p)).group(1)))
        unified, transposed, strike_lv = [], [], []
        for p in pages:
            t = page_text(p)
            if '<td' not in t:
                continue
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.S | re.I)
            u = parse_unified(rows)
            if u:
                unified.append({'page': os.path.basename(p).replace('.htm', ''),
                                'title': page_title(t), 'rows': u})
                continue
            cl, lv = classify_transposed(rows)
            if cl or lv:
                meta = {'page': os.path.basename(p).replace('.htm', ''),
                        'title': page_title(t)}
                if cl:
                    transposed.append(dict(meta, rows=cl))
                if lv:
                    strike_lv.append(dict(meta, rows=lv))
        if unified or transposed or strike_lv:
            slot = chars.setdefault(key, {'unified_tables': [],
                                          'transposed_tables': [],
                                          'strike_level_tables': []})
            slot['unified_tables'] += unified
            slot['transposed_tables'] += transposed
            slot['strike_level_tables'] += strike_lv
            coverage[key] = 'unified=%d弹幕转置=%d体术等级=%d' % (
                len(slot['unified_tables']), len(slot['transposed_tables']),
                len(slot['strike_level_tables']))
        else:
            coverage.setdefault(key, '无表')

    n_rows = lambda key: sum(len(t['rows']) for t in chars.get(key, {}).get(
        'unified_tables', [])) + sum(len(t['rows']) for t in chars.get(key, {}).get(
        'transposed_tables', [])) + sum(len(t['rows']) for t in chars.get(key, {}).get(
        'strike_level_tables', []))
    out = {
        'source': '规则=system.txt outline_100-103; 矩阵=各角色CHM技表(2026-10-14'
                  'hh.exe解压), tools/jz2_bullet_clash.py解析',
        'rules': RULES,
        'semantics_note': 'strength=S/A/B/C为相杀强度(仅射击技); '
                          'strike_level_tables里的attack_level=小/中/大/特大为'
                          '攻击等级(体术表"强度"行, 与相杀同词不同义)',
        'chars': chars,
        'coverage': coverage,
        'decompile_failed': DECOMPILE_FAILED,
        'coverage_note': 'CHM未解出角色与无表角色均显式登记; 强度值只转录不推算',
    }
    dst = os.path.join(ROOT, 'data', 'guide_tables', 'bullet_clash.json')
    with open(dst, 'w', encoding='utf8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('== 生成 %s ==' % dst)
    for key in sorted(set(IDX2CHAR.values())):
        print('%-9s %-16s 总行数=%d' % (key, coverage.get(key, '?'), n_rows(key)))
    print('CHM未解出:', ', '.join(DECOMPILE_FAILED))


if __name__ == '__main__':
    main()
