# -*- coding: utf-8 -*-
"""萃香(伊吹萃香/西瓜)宏库 — 帧数据从CHM攻略gb18030解码提取(2026-09-21)。

攻略来源: 酔人瘾子-西瓜1.10攻略(水杨酸+679L补充)
关键帧数据:
  A/4A:  发生9F 持续4F 全体26F 硬直-2 发生极快
  2A:    发生10F 持续3F 全体29F 硬直-4 出手速度优秀
  6A(三段): 发生17F 持续6F 全体52F 硬直-14 SMASH
  3A:    发生25F 持续10F 全体62F 硬直-9 RIFT
  DA:    发生15F 持续30F 全体一段后追加
  B/JB:  发生17F(通常)/32F(蓄力) 射击 持续30F
  6B:    发生18F 持续31F 全体45F SMASH(弹)
  C:     发生22F 爆炸30F后 追击烟弹
  DC:    萃香核心技(超大弹/可蓄力)
主力连段: AAAA→623萃鬼投 / AAA→6B→22B / DA→DC
特点: AAAA超大判定 / 623投技 / DC超大弹 / Missing Power变大
"""

MACROS_SUIKA = [
    # ---- 移动/防御(通用物理) ----
    ("待机",  [((), 6)]),
    ("前进",  [(("right",), 6)]),
    ("后退",  [(("left",), 6)]),
    ("跳跃",  [(("up",), 12)]),
    ("后跳",  [(("up", "left"), 12)]),
    ("前冲",  [(("right", "D"), 8)]),
    ("后冲",  [(("left", "D"), 8)]),
    ("空冲",  [(("up",), 10), (("right",), 3), ((), 1), (("right",), 6)]),
    ("高跳",  [(("down",), 3), ((), 1), (("up",), 12)]),
    ("斜上冲", [(("down",), 3), ((), 1), (("up", "right"), 12)]),
    ("斜后跳", [(("down",), 3), ((), 1), (("up", "left"), 12)]),
    ("立防",  [(("left",), 12)]),
    ("蹲防",  [(("down", "left"), 12)]),
    ("空防",  [(("up", "left"), 10), (("left",), 8)]),
    # ---- 萃香体术(帧数据标定) ----
    ("5A",   [(("A",), 8)]),                     # 发生9F 全体26F 发生极快
    # 5A确认(用户2026-09-29): 单发5A+confirm → 命中放623B萃鬼投, 落空截断
    ("5A确认", [(("A",), 8), ((), 2), ("confirm", 0),
               (("right",), 3), (("down",), 3),
               (("down", "right", "B"), 10)]),   # 5A→确认→623B萃鬼投
    # 2026-09-22 hitlab修复(灵梦实测标定外推): 方向预置6帧, 同帧按=吞键
    ("2A",   [(("down",), 6), (("down", "A"), 10)]),       # 发生9F 全体28F 下段(JZ-2b: 站9f修正, 旧注释10F)
    ("6A",   [(("right",), 6), (("right", "A"), 14)]),     # hitlab修复: 6系同帧同理
    ("3A",   [(("down",), 6), (("down", "right"), 2), (("down", "right", "A"), 14)]),  # 发生19F 全体54F 对空(JZ-2b: 站19f修正, 旧注释25F=CHM错值)
    ("5B",   [(("B",), 10)]),                     # 发生15F 全体42F 射击(JZ-2b: 站15f修正, 旧注释17F)
    ("6B",   [(("right",), 6), (("right", "B"), 10)]),     # hitlab修复: 发生18F SMASH弹
    ("2B",   [(("down",), 6), (("down", "B"), 10)]),
    ("5C",   [(("C",), 12)]),                     # 弹体22F放出/主判定52F爆炸(JZ-2b: 站startup=52f记爆炸, 语义双值)
    ("6C",   [(("right",), 6), (("right", "C"), 12)]),     # hitlab修复: DC系列(核心技)
    ("2C",   [(("down",), 6), (("down", "C"), 12)]),
    ("jB",   [(("up",), 6), (("up",), 2), (("B",), 14)]),               # 空中JB 发生14F
    ("j2B",  [(("up",), 6), (("down",), 2), (("down", "B"), 14)]),
    ("jC",   [(("up",), 6), (("up",), 2), (("C",), 14)]),
    # ---- 萃香必杀 ----
    ("236B", [(("down",), 3), (("down", "right"), 3), (("right", "B"), 10)]),  # 妖鬼-密-(火拳)
    ("236C", [(("down",), 3), (("down", "right"), 3), (("right", "C"), 12)]),
    ("623B", [(("right",), 3), (("down",), 3), (("down", "right", "B"), 10)]), # 萃鬼(投技)
    ("623C", [(("right",), 3), (("down",), 3), (("down", "right", "C"), 10)]),
    ("22B",  [(("down",), 3), (("down",), 3), (("down", "B"), 12)]),                  # hitlab修复: 原松键后同帧=吞键
    ("22C",  [(("down",), 3), (("down",), 3), (("down", "C"), 12)]),                  # hitlab修复: 同上
    ("214B", [(("left",), 3), (("down", "left"), 3), (("left", "B"), 10)]),    # 踏鞴(风箱)
    ("214C", [(("left",), 3), (("down", "left"), 3), (("left", "C"), 12)]),
    # ---- 受攻侧 ----
    ("受身",  [(("left",), 4), (("left", "A"), 8)]),
    ("起身穿", [(("right",), 4), (("right", "A"), 14)]),
    ("结界2", [(("down",), 2), (("down", "D"), 2), (("down",), 1), (("down", "D"), 8)]),
    ("结界4", [(("left",), 2), (("left", "D"), 2), (("left",), 1), (("left", "D"), 8)]),
    ("DA",   [(("right", "D"), 6), (("right", "A"), 12)]),  # DA发生15F持续30F
    ("飞翔",  [(("up",), 10), (("right", "D"), 16)]),
    ("空翔前", [(("right", "D"), 16)]),
    ("空翔后", [(("left", "D"), 16)]),
    ("空冲后", [(("left",), 3), ((), 1), (("left",), 6)]),
    # ---- 空压 ----
    ("jA",   [(("up",), 6), (("A",), 8)]),      # 发生9F持续20F(长判定)
    ("j6A",  [(("up",), 6), (("right",), 2), (("right", "A"), 12)]),  # 发生12F SMASH
    ("j8A",  [(("up",), 6), (("up",), 2), (("up", "A"), 12)]),
    ("j2A",  [(("up",), 6), (("down",), 2), (("down", "A"), 12)]),
    # ---- 萃香民工连(AAAA→623萃鬼投为核心) ----
    ("连段A", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("right",), 3), (("down",), 3), (("down", "right", "B"), 10)]),  # A→确认→AAA→623B萃鬼投,   # AAAA→623B萃鬼投
    ("连段B", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("right", "B"), 10), ((), 3), (("down",), 3), ((), 1), (("down", "B"), 12)]),  # A→确认→AA→6B→22B地火,   # AAA→6B→22B地火
    ("连段C", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("right", "A"), 10), ((), 3), (("up",), 8), (("down", "B"), 14)]),  # A→确认→AA→6A→J2B追打,   # AAA→6A→J2B追打
    # ---- 萃香压制链 ----
    ("压制A", [(("down",), 6), (("down", "A"), 8), ((), 3), ("cconfirm", 0),
              (("right", "A"), 10), ((), 3),
              (("down", "B"), 10), ((), 3), (("right", "D"), 6), (("right", "A"), 9)]),
    ("压制B", [(("up",), 6), (("right", "A"), 12), ("cconfirm", 0), (("C",), 12), ((), 2),
              (("down",), 3), (("down", "right"), 3), (("right", "B"), 10)]),
    # ---- 符卡(从card_tables萃香卡表) ----
    ("卡·投掷",   [("sc:200", 0), ((), 14)]),   # 萃符「戸隠山投げ」费2
    ("卡·鬼缚",   [("sc:201", 0), ((), 14)]),   # 酔神「鬼縛りの術」费2
    ("卡·力量",   [("sc:202", 0), ((), 14)]),   # 鬼符「ミッシングパワー」费2
    ("卡·紫力",   [("sc:205", 0), ((), 18)]),   # 鬼神「ミッシングパープルパワー」费4
    ("卡·大杀",   [("sc:208", 0), ((), 18)]),   # 鬼符「大江山悉皆殺し」费5
    ("卡·三歩",   [("sc:212", 0), ((), 14)]),   # 四天王奥義「三歩壊廃」费3
    ("卡·药水",   [("sc:1", 0), ((), 10)]),
    ("卡·灵击",   [("sc:0", 0), ((), 12)]),
    ("卡·当前",   [("sc:-1", 0), ((), 10)]),
    # R23(2026-10-02): 2A确认 — 下段命中转2B(结构同reimu/marisa模板;
    # 帧数取自萃香自家2A/2B已验证宏)。补齐下段起手确认缺口。
    # 契约: 新宏必须追加在列表末尾(零初始化迁移/宏计数/BC标签都按
    # "旧索引不变, 新宏占末位"对齐 — 中插会使全部下游错位)。
    ("2A确认", [(("down",), 6), (("down", "A"), 10), ((), 2), ("confirm", 0),
               (("down",), 6), (("down", "B"), 10), ((), 3)]),
    # ---- R31 Trialmode导入(末位追加契约) ----
    ("TM·空连终结",
     [(("right",), 6), (("down",), 4), (("up", "right"), 8),
      (("A",), 8), ((), 2), ("confirm", 0),
      ((), 11),
      (("right",), 6), (("right", "A"), 12), ((), 6),
      (("right",), 6), (("right", "B"), 10),
      (("right",), 6), (("right", "C"), 12), ((), 15), ("sc:200", 0)]),
    # Trialmode 3100伤 7段: 6→hj9→j5a→j6a→j6b→j6c→sc200
    # R39(第十轮§4-2): confirm门移到j5A攻击键之后(原在走路后=必截断)
    ("TM·对空连",
     [(("up",), 6), (("down",), 6), (("down", "A"), 10), ((), 2),
      ("confirm", 0),
      ((), 26),
      (("right",), 6), (("right", "C"), 12),
      (("right", "D"), 8),
      (("right",), 6), (("right", "C"), 12), ((), 11),
      (("right", "D"), 8),
      (("right",), 6), (("right", "A"), 12)]),
    # Trialmode 3000伤 7段: 8→j2a→j6c→j66→j6c→j66→j6a(萃香空连)
    # R39: 门后移到j2A之后同上
    # ---- R35 原子化(差距#1): Trialmode帧偏移 ----
    ("原子·确认5A",
     [(("A",), 8), ((), 2), ("confirm", 0)]),
    ("原子·地面链",
     [(("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6),
      ((), 3), (("right",), 6), (("right", "B"), 10)]),
    ("原子·空链",
     [(("down",), 4), (("up", "right"), 8),
      (("A",), 8), ((), 11),
      (("down",), 2), (("down",), 4), (("down", "A"), 10)]),
    ("原子·收尾",
     [(("right", "D"), 8), ((), 8),
      (("down",), 2), (("down",), 4), (("down", "A"), 10)]),
]

MACRO_NAMES_SUIKA = [m[0] for m in MACROS_SUIKA]
N_MACROS_SUIKA = len(MACROS_SUIKA)


# ---- 2026-09-22 hitlab死招事故的运行时规范化(门禁C11联动) ----
# 实证: 方向+攻击键同帧按下且该方向未预置≥5帧时, 攻击键被姿态转换吞掉
# (纯蹲无攻击, docs/hitlab_tables.md)。加载时自动为违例步补6帧方向预置(阈值5,余量1)。
_BTN = {"A", "B", "C"}
_DIR = {"down", "right", "left", "up"}


def _eff_dirs(keys):
    """同轴双键取最后生效键(D14修复: keys_to_input同轴后者覆盖前者 —
    原sorted(need)在('up','down','B')类步上把预置方向写反)"""
    last = {}
    for k in keys:
        if k in ("left", "right"):
            last["H"] = k
        elif k in ("down", "up"):
            last["V"] = k
    return set(last.values())


def _norm_presteps(script):
    """D15修复(从零审查): 紧邻连续帧数模型 — 原established集合永不重置,
    回答的是"脚本更早处出现过该方向吗", 而物理失效模式是姿态转换帧,
    关键是"紧邻的前若干帧有没有按住该方向"。门步/空步/异向步都打断累计。
    对每个攻击步, 其生效方向的紧邻连续保持帧<5则补6帧预置。"""
    out = []
    run = {}
    for ks, fr in script:
        if isinstance(ks, str):
            out.append((ks, fr))
            run = {}
            continue
        keys = set(ks)
        ed = _eff_dirs(ks)
        atk = bool(keys & _BTN)
        if atk:
            # 插入步必须携带攻击步的**全部**生效方向 — 只补缺的方向会
            # 松开已按住的方向(如3A: 只补right则down键松开=退出蹲姿,
            # 攻击又变死招; 从零审查紧邻模型的正确判定)
            if any(run.get(d, 0) < 5 for d in ed):
                ins = tuple(sorted(
                    ed, key=lambda k: ("down", "left", "right", "up").index(k)))
                out.append((ins, 6))
                for d in ed:
                    run[d] = 6
        out.append((ks, fr))
        if atk:
            run = {d: fr for d in ed}
        else:
            run = {d: run.get(d, 0) + fr for d in ed}
    return out



_RAW = list(MACROS_SUIKA)
MACROS_SUIKA = [(n, _norm_presteps(sc)) for n, sc in _RAW]
# D13配套: 精确受影响集合导出(重播种工具消费, 替代宽口径)
NORMALIZED_AFFECTED = {n for (n, s0), (_, s1) in zip(_RAW, MACROS_SUIKA)
                      if s0 != s1}

MELEE_MACROS_SUIKA = {"5A", "2A", "6A", "3A", "623B", "623C", "5A确认", "2A确认"}
BULLET_MACROS_SUIKA = {"5B", "6B", "2B", "5C", "6C", "2C", "jB", "j2B", "jC", "236B", "236C"}
SKILL_MACROS_SUIKA = {"236B", "236C", "623B", "623C", "22B", "22C", "214B", "214C"}
DASH_MACROS_SUIKA = {"前冲", "后冲", "空冲", "高跳", "斜上冲", "斜后跳", "结界2", "结界4",
                     "飞翔", "空翔前", "空翔后", "空冲后", "DA"}
GUARD_MACROS_SUIKA = {"立防", "蹲防", "空防"}
AIR_MACROS_SUIKA = {"jA", "j6A", "j8A", "j2A", "j2B", "jC"}
COMBO_MACROS_SUIKA = {"连段A", "连段B", "连段C", "TM·空连终结", "TM·对空连", "原子·确认5A", "原子·地面链", "原子·空链", "原子·收尾"}
STRING_MACROS_SUIKA = {"压制A", "压制B"}
SC_MACROS_SUIKA = {"卡·投掷", "卡·鬼缚", "卡·力量", "卡·紫力", "卡·大杀", "卡·三歩",
                   "卡·药水", "卡·灵击", "卡·当前"}

SC_COST_SUIKA = {0: 1, 1: 1, 200: 2, 201: 2, 202: 2, 203: 5, 204: 4, 205: 4,
                 206: 1, 207: 4, 208: 5, 212: 3,
           # JZ-4系统卡(2026-10-14晚)
           2: 1, 3: 1, 4: 1, 12: 1, 14: 1}

# ==== R61n(C4): 表里择+压起身套件 ====
MACROS_SUIKA.append(('择·中段', [(('right', 'D'), 6), ((), 2), (('right',), 6), (('right', 'A'), 12)]))
MACROS_SUIKA.append(('择·下段', [(('right', 'D'), 6), ((), 2), (('right',), 6), (('down',), 6), (('down', 'A'), 12)]))
MACROS_SUIKA.append(('择·投', [(('right', 'D'), 6), ((), 2), (('right',), 6), (('A', 'D'), 6)]))
MACROS_SUIKA.append(('压起身·即', [(('down', 'A'), 14), ((), 4), (('A',), 10)]))
MACROS_SUIKA.append(('压起身·延迟', [((), 10), (('A',), 12), ((), 2), (('down', 'A'), 12)]))
MACROS_SUIKA.append(('压起身·空', [(('up',), 6), (('down',), 6), (('down', 'A'), 14)]))
MACROS_SUIKA.append(('压起身·穿', [(('left', 'D'), 6), ((), 4), (('left',), 8)]))
MELEE_MACROS_SUIKA |= {'择·中段', '择·下段', '择·投', '压起身·即', '压起身·延迟', '压起身·空', '压起身·穿'}
COMBO_MACROS_SUIKA |= {'择·中段', '择·下段', '择·投', '压起身·即', '压起身·延迟', '压起身·空', '压起身·穿'}
MACRO_NAMES_SUIKA = [m[0] for m in MACROS_SUIKA]
# R61n: 追加宏的规范化(预置帧≥5 — hitlab标定阈值)
MACROS_SUIKA[-7:] = [(n, _norm_presteps(sc)) for n, sc in MACROS_SUIKA[-7:]]
MACRO_NAMES_SUIKA = [m[0] for m in MACROS_SUIKA]
N_MACROS_SUIKA = len(MACROS_SUIKA)
# CH-3/JZ-4扩展波(2026-10-14晚): 蓄力/系统卡/DD变体/HJC取消 —
# 尾部追加+基础宏派生(wave_ext), 索引稳定=ppo零初始化迁移适用
from macros.wave_ext import wave_extensions, wave_registrations
_WAVE = wave_extensions(MACROS_SUIKA, 'suika')
MACROS_SUIKA.extend(_WAVE)
_B, _S, _D = wave_registrations(_WAVE)
BULLET_MACROS_SUIKA |= _B
SC_MACROS_SUIKA |= _S
DASH_MACROS_SUIKA |= _D
MACROS_SUIKA[-len(_WAVE):] = [(n, _norm_presteps(sc)) for n, sc in MACROS_SUIKA[-len(_WAVE):]]
MACRO_NAMES_SUIKA = [m[0] for m in MACROS_SUIKA]
N_MACROS_SUIKA = len(MACROS_SUIKA)
