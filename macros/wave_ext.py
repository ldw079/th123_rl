# -*- coding: utf-8 -*-
"""CH-3/JZ-4(2026-10-14晚): 宏库扩展波 — 蓄力版/系统卡/DD变体/HJC取消.

数据源(零手写序列, 全部从既有基础宏派生):
- 蓄力阈值: macros/charge_table.json(萃香32F实测, 三主力外推36F显式标注)
- 系统卡编号: card_tables.py SYSTEM_CARDS(0-indexed, sc:2/3/4/12/14已查证)
- HJC取消: 基础射击宏脚本 + 尾接 高跳/空冲/空翔后 既有脚本
落库纪律: 尾部追加(索引稳定=ppo零初始化迁移直接适用); 基础宏缺失自动跳过。
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, 'charge_table.json'), encoding='utf8') as _f:
    CHARGE_TABLE = json.load(_f)

# JZ-4.4: 系统卡(sc:N=SYSTEM_CARDS 0-indexed编号, 2026-10-14查证)
SYSTEM_CARDS_NEW = [
    ("卡·怀表",   [("sc:2", 0),  ((), 12)]),   # ストップウォッチ: 时停
    ("卡·白楼剑", [("sc:3", 0),  ((), 12)]),   # 白楼剣: 射击系打断
    ("卡·人偶",   [("sc:4", 0),  ((), 12)]),   # 身代わり人形=灵反: 防反28F(含暗转15F)
    ("卡·铜钱",   [("sc:12", 0), ((), 12)]),   # 宵越しの銭: 防御态灵力回复
    ("卡·绯想剑", [("sc:14", 0), ((), 12)]),   # 緋想の剣: 发动预报中的天气
]

# JZ-4.3: DD变体(结界2/4同型镜像; 空结界=起跳后D窗)
DD_VARIANTS = [
    ("结界6", [(("right",), 2), (("right", "D"), 2),
               (("right",), 1), (("right", "D"), 8)]),        # 6DD 可延长
    ("结界1", [(("down", "left"), 2), (("down", "left", "D"), 2),
               (("down", "left"), 1), (("down", "left", "D"), 8)]),
    ("空结界4", [(("up",), 10), (("left",), 3), ((), 1),
                 (("left", "D"), 8)]),
    ("空结界6", [(("up",), 10), (("right",), 3), ((), 1),
                 (("right", "D"), 8)]),
]

# JZ-4.2: HJC取消三件(射击→大跳/射击→空冲/空射→空翔后)
HJC_PAIRS = (('5B', '高跳'), ('5B', '空冲'), ('jC', '空翔后'))


def charge_of(base_macros, base_name, hold=36):
    """基础宏→蓄力版: 末步(按键步)延长到hold帧, 预压步原样保留。"""
    d = dict(base_macros)
    script = [tuple(s) for s in d[base_name]]
    keys, _fl = script[-1]
    script[-1] = (keys, hold)
    return (base_name + '蓄', script)


def hjc_of(base_macros, shot, tail):
    """射击宏全脚本 + 1帧取消窗 + 尾接宏脚本(高跳/空冲/空翔后)。"""
    d = dict(base_macros)
    s = [tuple(x) for x in d[shot]]
    t = [tuple(x) for x in d[tail]]
    return ('%s·%s取消' % (shot, tail), s + [((), 1)] + t)


def wave_extensions(base_macros, char):
    """该角色扩展宏列表(基础宏缺失项自动跳过, 不猜)。"""
    dm = dict(base_macros)
    out = []
    for m in CHARGE_TABLE['chars'][char]['moves']:
        # 表用大写J(JB/J2B), 库用小写(jB/j2B) — 双候选匹配
        base = m['base']
        cand = base if base in dm else base.replace('J', 'j')
        if cand in dm:
            out.append(charge_of(dm, cand, m['threshold_frames']))
    out.extend(SYSTEM_CARDS_NEW)
    out.extend(DD_VARIANTS)
    for shot, tail in HJC_PAIRS:
        if shot in dm and tail in dm:
            out.append(hjc_of(dm, shot, tail))
    return out


def wave_registrations(ext_list):
    """扩展宏按类别注册名集: (弹幕类, 符卡类, 位移类)。"""
    bullets = set()
    scs = set()
    dashes = set()
    for n, _s in ext_list:
        if n.endswith('蓄'):
            bullets.add(n)
        elif n.startswith('卡·'):
            scs.add(n)
        else:                       # 结界*/空结界*/*取消 = 位移类
            dashes.add(n)
    return bullets, scs, dashes
