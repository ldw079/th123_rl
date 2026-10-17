# -*- coding: utf-8 -*-
"""LE-2表提取·第二步: fangyu警戒表深解析(文本级, 无动作ID映射).

从fangyu_index.json的行锚点读正文, 逐角色提取:
  warning_moves: [{name, advice}] — 警戒招(招名行+建议段落)
  guard_crush:   一击破防属性攻击条目
  air_unblockable: 空防不可攻击条目
  weather:       需要注意的天气条目
消费(LE-2特征段, 迁移窗): 类别计数先验(n_warning/guard_crush/air) —
不做逐招ID映射(R4: 文本→ID错映射风险, 计数级无需).
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = (os.environ.get('TH123_FANGYU_SRC')
       or os.path.join(os.path.dirname(ROOT), '_extracted', 'fangyu.txt'))
IDX = os.path.join(ROOT, 'data', 'guide_tables', 'fangyu_index.json')
OUT = os.path.join(ROOT, 'data', 'guide_tables', 'fangyu_counters.json')

SEC_WARNING = ('需要警戒的通常技', '需要警戒的通常技/必杀/SC',
               '需要警戒的必杀/SC')
SEC_GC = '一击破防属性攻击'
SEC_AIR = '空防不可攻击'
SEC_WX = '需要注意的天气'

# 招名行启发式(R151b收紧): 满足其一 — ①含拉丁字母/数字(6C/JA/214
# 记法); ②片假名占假名比>50%(日文技能名ウィッチレイライン类).
# 首版纯"短行无标点"在天子/空/早苗章误吸大量建议短行(建议非空率34/79)
import unicodedata as _ud

_NAME_BAD = re.compile(r'[。．，,；;：:（）()↑←→↓/·…—]{3,}')


_SENTENCE_HINTS = ('了', '开始', '所以', '因为', '但是', '虽然', '之后',
                   '的话', '使用率', '而且', '基本', '很难', '容易', '时候',
                   '可以', '这个', '那个', '还有')


def _looks_like_sentence(s):
    """P1修(bug_2026-10-17): 含叙述词的中文句不是招名 — has_latin
    对'原236的使用率开始上升'类建议句误判(数字触发拉丁判定)."""
    return any(w in s for w in _SENTENCE_HINTS)


def is_move_name(ln):
    """警戒节的严格招名(拉丁/片假名记法) — 见上注释."""
    s = ln.strip()
    if not s or len(s) > 24:
        return False
    if s.endswith(('。', '，', '、', '：', '；', '？', '！')):
        return False
    if s in ('特征', '技能', '备注', '发生时间', '无敌时间', '伤害', '花费'):
        return False
    if _NAME_BAD.search(s):
        return False
    if _looks_like_sentence(s):
        return False
    has_latin = any(c.isascii() and c.isalnum() for c in s)
    if has_latin:
        return True
    kana = [c for c in s if '\u30a0' <= c <= '\u30ff']   # 片假名
    hira = [c for c in s if '\u3040' <= c <= '\u309f']   # 平假名
    if kana and len(kana) >= max(2, 0.5 * (len(kana) + len(hira))):
        return True
    return False


def is_list_item(ln):
    """列表节(破防/空防不可/天气)的宽松条目名 — 枚举节里中文短行
    也是条目(如'雾雨萝卜'), P1修: 长度放宽60(单行多招枚举由
    parse_list_section拆分), 补节标题过滤+叙述句排除."""
    s = ln.strip()
    if not s or len(s) > 60:
        return False
    if s.endswith(('。', '？', '！')):
        return False
    if s in (SEC_GC, SEC_AIR, SEC_WX, '特征'):
        return False
    if _looks_like_sentence(s):
        return False
    return not _NAME_BAD.search(s)


def parse_list_section(body):
    """一击破防/空防不可/天气: 逐条(宽松条目名is_list_item).

    P1修(bug审计2026-10-17): 枚举节大量单行多招式("中段：H6A、蓄力花剪、
    …" / "A連、遠A、6A、2A、DA、DB、…") — 长度上限放宽到60且按顿号
    拆分逐招计数(计数先验的口径=招数, 非行数)."""
    items = []
    cur = None

    def _flush(name, note):
        # 顿号拆分: "H6A、蓄力花剪" → 两条
        parts = [p.strip() for p in name.split('、') if p.strip()]
        for p in parts:
            items.append({'name': p[:24], 'note': note[:120]})

    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        if is_list_item(s):
            if cur:
                _flush(cur['name'], cur['note'])
            cur = {'name': s, 'note': ''}
        elif cur is not None:
            cur['note'] = (cur['note'] + ' ' + s).strip()
    if cur:
        _flush(cur['name'], cur['note'])
    return items


def parse_warning(body):
    """警戒招: 招名行 + 后续建议段落(至下一招名)."""
    moves = []
    cur = None
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        if is_move_name(s):
            if cur:
                moves.append(cur)
            cur = {'name': s, 'advice': ''}
        elif cur is not None:
            cur['advice'] = (cur['advice'] + ' ' + s).strip()[:300]
    if cur:
        moves.append(cur)
    return moves


def main():
    lines = io.open(SRC, encoding='utf8', errors='replace').read().splitlines()
    idx = json.load(io.open(IDX, encoding='utf8'))
    out = {'source': 'fangyu.txt正文深解析(锚点自fangyu_index.json) — '
                     'LE-2第二步; 文本级无动作ID映射(R4), 消费=类别计数先验',
           'characters': {}}
    for cn, ent in idx['chapters'].items():
        secs = ent['sections']
        rec = {'char_key': ent['char_key']}
        for ws in SEC_WARNING:
            if ws in secs:
                a, b = secs[ws]
                _body = '\n'.join(lines[a:b - 1])
                rec['warning_moves'] = [
                    m for m in parse_warning(_body)
                    if m['name'] != ws]      # 首条常=节标题伪条目
                rec['_warning_lines'] = [a, b]
                break
        for key, sec in (('guard_crush', SEC_GC),
                         ('air_unblockable', SEC_AIR),
                         ('weather', SEC_WX)):
            if sec in secs:
                a, b = secs[sec]
                rec[key] = parse_list_section('\n'.join(lines[a:b - 1]))
        out['characters'][cn] = rec
    io.open(OUT, 'w', encoding='utf8').write(
        json.dumps(out, ensure_ascii=False, indent=1))
    for cn, rec in out['characters'].items():
        print('%-8s 警戒%2d 破防%2d 空防不可%2d 天气%d' % (
            rec.get('char_key') or cn[:4],
            len(rec.get('warning_moves', [])),
            len(rec.get('guard_crush', [])),
            len(rec.get('air_unblockable', [])),
            len(rec.get('weather', []))))
    print('→ %s' % OUT)


if __name__ == '__main__':
    main()
