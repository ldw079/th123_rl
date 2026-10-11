# -*- coding: utf-8 -*-
"""R44: 六新角色宏库生成器(咲夜/帕秋莉/幽幽子/铃仙/小町/天子)。

产物: macros/{char}.py — 结构与三现役库同构:
- 通用体术/移动/防御/系统卡(引擎级一致, 照搬现役模板)
- 指令技 236/623/22/214 × B/C(输入公式化, mod层直收)
- 空中体术 jA/j6A/j8A/j2A/jB/jC
- hit-confirm 连段(通用A链+确认门)
- 原子宏四件套(R35同款, 通用A链可移植)
- 符卡宏: SC id/耗费 取card_tables(解包CSV, 测量级)
- 压制/空连通用版

角色特化(专属连段/换技/精确帧)留待hitlab/Trialmode标定 — 本版
目标是"完整可跑"的动作空间, 与三现役库的共同骨架逐位同构。

用法: python tools/gen_newchar_libs.py
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')
from card_tables import CHAR_CARD_TABLES  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 角色注册: (模块名, 引擎id, XML目录名, 中文名)
NEW_CHARS = [
    ('sakuya', 2, 'sakuya', '咲夜'),
    ('patchouli', 4, 'patchouli', '帕秋莉'),
    ('yuyuko', 7, 'yuyuko', '幽幽子'),
    ('reisen', 10, 'udonge', '铃仙'),
    ('komachi', 12, 'komachi', '小町'),
    ('tenshi', 14, 'tenshi', '天子'),
    # R45(2026-10-04): 剩余11角色 — 至此全20角色宏库齐备
    ('alice', 3, 'alice', '爱丽丝'),
    ('youmu', 5, 'youmu', '妖梦'),
    ('remilia', 6, 'remilia', '蕾米莉亚'),
    ('yukari', 8, 'yukari', '八云紫'),
    ('aya', 11, 'aya', '射命丸文'),
    ('iku', 13, 'iku', '永江衣玖'),
    ('sanae', 15, 'sanae', '东风谷早苗'),
    ('cirno', 16, 'chirno', '琪露诺'),
    ('meiling', 17, 'meirin', '红美铃'),
    ('utsuho', 18, 'utsuho', '灵乌路空'),
    ('suwako', 19, 'suwako', '洩矢诹访子'),
]

# ---- 通用宏模板(与macros.py逐位同构; 仅角色注释差异) ----
UNIVERSAL = '''# -*- coding: utf-8 -*-
"""{cn}({en})宏库 — tools/gen_newchar_libs.py 生成(R44, 2026-10-04)。

骨架与三现役库同构(通用体术+指令技+确认连段+原子宏+符卡);
角色特化连段/换技待hitlab与Trialmode标定后末位追加
(末位追加契约: 新宏必须追加在列表末尾, 零初始化迁移兼容)。
SC耗费取card_tables(解包CSV测量级); 技能槽位映射留空(R4纪律:
空映射优于错映射, 待标定后补CHAR_SKILL_MAPS)。
"""
from macros import _eff_dirs, _norm_presteps  # noqa: F401 (复用规范化器)

MACROS_{UP} = [
    # ---- 基础 ----
    ("待机", [((), 10)]),
    ("前进", [(("right",), 10)]),
    ("后退", [(("left",), 10)]),
    ("前冲", [(("right",), 3), ((), 1), (("right",), 6)]),
    ("后冲", [(("left",), 3), ((), 1), (("left",), 6)]),
    ("高跳", [(("down",), 4), (("up",), 8)]),
    ("跳跃", [(("up",), 6)]),
    ("立防", [(("left",), 10)]),
    ("蹲防", [(("down", "left"), 10)]),
    ("空防", [(("left",), 8)]),
    ("后跳", [(("left",), 3), ((), 1), (("left",), 4), (("up",), 6)]),
    ("斜后跳", [(("left", "down"), 3), ((), 1), (("left",), 4), (("up", "left"), 6)]),
    # ---- 受攻侧工具箱 ----
    ("受身",  [(("left",), 4), (("left", "A"), 8)]),
    ("起身穿", [(("right",), 4), (("right", "A"), 14)]),
    ("结界2", [(("down",), 2), (("down", "D"), 2), (("down",), 1), (("down", "D"), 8)]),
    ("结界4", [(("left",), 2), (("left", "D"), 2), (("left",), 1), (("left", "D"), 8)]),
    ("DA",   [(("right", "D"), 6), (("right", "A"), 10)]),
    ("飞翔",  [(("up",), 10), (("right", "D"), 16)]),
    ("空翔前", [(("right", "D"), 16)]),
    ("空翔后", [(("left", "D"), 16)]),
    ("空冲后", [(("left",), 3), ((), 1), (("left",), 6)]),
    # ---- 地面体术 ----
    ("5A",   [(("A",), 10)]),
    ("2A",   [(("down",), 6), (("down", "A"), 10)]),
    ("6A",   [(("right",), 6), (("right", "A"), 10)]),
    ("3A",   [(("down", "right"), 6), (("down", "right", "A"), 10)]),
    ("4A",   [(("left",), 6), (("left", "A"), 10)]),
    ("5A确认", [(("A",), 10), ((), 2), ("confirm", 0)]),
    ("2A确认", [(("down",), 6), (("down", "A"), 10), ((), 2), ("confirm", 0)]),
    # ---- 地面射击 ----
    ("5B",   [(("B",), 10)]),
    ("6B",   [(("right",), 6), (("right", "B"), 10)]),
    ("2B",   [(("down",), 6), (("down", "B"), 10)]),
    ("5C",   [(("C",), 12)]),
    ("6C",   [(("right",), 6), (("right", "C"), 12)]),
    ("2C",   [(("down",), 6), (("down", "C"), 12)]),
    # ---- 空中体术/射击 ----
    ("jA",   [(("up",), 6), (("A",), 10)]),
    ("j6A",  [(("up",), 6), (("right",), 2), (("right", "A"), 12)]),
    ("j8A",  [(("up",), 6), (("up",), 2), (("up", "A"), 12)]),
    ("j2A",  [(("up",), 6), (("down",), 2), (("down", "A"), 12)]),
    ("jB",   [(("up",), 6), (("up",), 2), (("B",), 14)]),
    ("j2B",  [(("up", "B"), 14)]),
    ("jC",   [(("up",), 6), (("up",), 2), (("C",), 14)]),
    ("j6C",  [(("up",), 6), (("right",), 2), (("right", "C"), 14)]),
    # ---- 指令技(输入公式化, 引擎直收) ----
    ("236B", [(("down",), 3), (("down", "right"), 3), (("right", "B"), 10)]),
    ("236C", [(("down",), 3), (("down", "right"), 3), (("right", "C"), 12)]),
    ("623B", [(("right",), 3), (("down",), 3), (("down", "right", "B"), 10)]),
    ("623C", [(("right",), 3), (("down",), 3), (("down", "right", "C"), 10)]),
    ("22B",  [(("down",), 3), (("down",), 3), (("down", "B"), 12)]),
    ("22C",  [(("down",), 3), (("down",), 3), (("down", "C"), 12)]),
    ("214B", [(("left",), 3), (("down", "left"), 3), (("left", "B"), 10)]),
    ("214C", [(("left",), 3), (("down", "left"), 3), (("left", "C"), 12)]),
    # ---- hit-confirm连段(通用A链; 角色特化帧待hitlab) ----
    ("连段A", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("right", "A"), 10), ((), 3), (("right",), 3), (("down",), 3), (("down", "right"), 6), (("down", "right", "B"), 10)]),
    ("连段B", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("right", "D"), 6), (("right", "A"), 10), ((), 3), (("right",), 3), (("down",), 3), (("down", "right"), 6), (("down", "right", "B"), 10)]),
    # ---- 压制链(通用版) ----
    ("压制A", [(("down",), 6), (("down", "A"), 8), ((), 3), ("cconfirm", 0),
              (("right", "A"), 10), ((), 3),
              (("down", "B"), 10), ((), 3), (("right", "D"), 6), (("right", "A"), 9)]),
    ("压制B", [(("up",), 6), (("right", "A"), 12), ("cconfirm", 0), (("C",), 12), ((), 2),
              (("down",), 3), (("down", "right"), 3), (("right", "B"), 10)]),
    # ---- 空连(通用版) ----
    ("空连A", [(("up",), 6), (("A",), 10), ("cconfirm", 0),
              (("up",), 2), (("right", "A"), 10), ((), 2),
              (("up",), 2), (("C",), 12)]),
    # ---- 原子宏(R35同款, 通用A链可移植) ----
    ("原子·确认5A", [(("A",), 6), ((), 2), ("confirm", 0)]),
    ("原子·地面链", [(("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("B",), 10)]),
    ("原子·空链", [(("down",), 4), (("up",), 8), (("A",), 8), ((), 11), (("down",), 2), (("down",), 4), (("down", "A"), 10)]),
    ("原子·收尾", [(("right", "D"), 8), ((), 8), (("down",), 2), (("down",), 4), (("down", "A"), 10)]),
    # ---- 系统卡(全角色通用, 耗费实测) ----
    ("卡·灵击札", [("sc:0", 0), ((), 12)]),
    ("卡·药水",   [("sc:1", 0), ((), 10)]),
    ("卡·当前",   [("sc:-1", 0), ((), 10)]),
    # ---- 角色符卡(SC id/耗费取card_tables) ----
{SC_MACROS}
]

MACRO_NAMES_{UP} = [m[0] for m in MACROS_{UP}]
N_MACROS_{UP} = len(MACROS_{UP})
NORMALIZED_AFFECTED_{UP} = _norm_presteps(MACROS_{UP})

{UP}_MELEE_MACROS = {{"5A", "2A", "6A", "3A", "4A", "jA", "j6A", "j8A", "j2A", "DA", "623B", "623C", "5A确认", "2A确认"}}
{UP}_BULLET_MACROS = {{"5B", "6B", "2B", "5C", "6C", "jB", "j2B", "jC", "j6C", "2C"}}
# R46(§3-3修复): 指令必杀归SKILL(与手写库一致) — 原误入BULLET导致
# dx<150被贴身禁令掩掉(升龙/反转最需的距离) + 空挥按1.0×而非技能档
{UP}_SKILL_MACROS = {{"236B", "236C", "623B", "623C", "22B", "22C", "214B", "214C"}}
{UP}_AIR_MACROS = {{"jA", "j6A", "j8A", "j2A", "jB", "j2B", "jC", "j6C", "空翔前", "空翔后", "空冲后", "飞翔", "高跳"}}
{UP}_COMBO_MACROS = {{"连段A", "连段B", "空连A", "原子·确认5A", "原子·地面链", "原子·空链", "原子·收尾"}}
{UP}_STRING_MACROS = {{"压制A", "压制B"}}
{UP}_SC_NAMES = {{"卡·灵击札", "卡·药水", "卡·当前"{SC_EXTRA_NAMES}}}
{UP}_GUARD_PREP = ("立防", "蹲防")

SC_COST_{UP} = {SC_COST_DICT}

# 末位追加契约: 新宏必须追加在MACROS_{UP}列表末尾(零初始化迁移兼容)

# R46(第十四轮§3-2修复): hitlab规范化 — 正确形态是逐脚本重绑定
# (原`NORMALIZED_AFFECTED = _norm_presteps(MACROS)`把整表当单脚本传参,
# 14/66宏跑的原始脚本 = 当年实测的"方向预置不足→攻击被吞→死招")
_RAW_{UP} = list(MACROS_{UP})
MACROS_{UP} = [(n, _norm_presteps(sc)) for n, sc in _RAW_{UP}]
NORMALIZED_AFFECTED_{UP} = {{n for (n, s0), (_, s1) in
                            zip(_RAW_{UP}, MACROS_{UP}) if s0 != s1}}
'''

# 符卡挑选: 每角色取SC区(>=200)耗费最低2张+最高伤1张(以费2/费5为代表)
# 简化: 取id顺序前3张SC + 费5大招(如有)
SC_NAME_CN = {
    200: '符卡一', 201: '符卡二', 202: '符卡三', 203: '符卡四',
    204: '符卡五', 205: '符卡六', 206: '符卡七', 207: '符卡八',
    208: '符卡九', 209: '符卡十', 210: '终卡', 211: '终卡二',
    212: '终卡三', 213: '终卡四', 214: '终卡五', 215: '终卡六',
    216: '终卡七', 217: '终卡八', 218: '终卡九', 219: '究极卡',
}


def pick_scs(cards):
    """[(id, name, cost)] SC区 → 取费最低3张+费最高1张(去重)"""
    scs = [(int(i), n, int(c)) for i, n, c in cards if int(i) >= 200]
    if not scs:
        return []
    by_cost = sorted(scs, key=lambda t: (t[2], t[0]))
    picks = by_cost[:3]
    hi = max(scs, key=lambda t: (t[2], t[0]))
    if hi not in picks:
        picks.append(hi)
    return sorted(picks)


def main():
    for en, cid, xdir, cn in NEW_CHARS:
        cards = CHAR_CARD_TABLES[cid]
        scs = pick_scs(cards)
        sc_lines = []
        sc_extra = []
        cost_dict = {0: 1, 1: 1}
        for sid, name, cost in scs:
            nm = '卡·' + SC_NAME_CN.get(sid, 'SC%d' % sid)
            # 日文名含「」等字符, 注释里保留原文名
            sc_lines.append('    ("%s", [("sc:%d", 0), ((), 14)]),'
                            '   # %s 费%d' % (nm, sid, name, cost))
            sc_extra.append('"%s"' % nm)
            cost_dict[sid] = cost
        cost_str = '{' + ', '.join('%d: %d' % (k, v)
                                   for k, v in sorted(cost_dict.items())) + '}'
        body = UNIVERSAL.format(
            cn=cn, en=en, UP=en.upper(), XDIR=xdir,
            SC_MACROS='\n'.join(sc_lines),
            SC_EXTRA_NAMES=(', ' + ', '.join(sc_extra)) if sc_extra else '',
            SC_COST_DICT=cost_str)
        p = os.path.join(HERE, 'macros', '%s.py' % en)
        io.open(p, 'w', encoding='utf-8').write(body)
        n = body.count('    ("')  # 宏数粗计
        print('生成 %s: %s (符卡%d张, 耗费%s)' % (en, p, len(scs), cost_str))


if __name__ == '__main__':
    main()
