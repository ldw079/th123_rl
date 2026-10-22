# -*- coding: utf-8 -*-
"""魔理沙(雾雨魔理沙/黑白)宏库 — 从攻略CHM帧数据提取(2026-09-21)。

攻略来源: 水杨酸黑白自编攻略23.09.09 + 则wiki黑白
帧数据要点:
  5A: 发生11f 持续5f 硬直-2f 破防+30f 被康1-15f
  2A: 发生10f 持续4f 硬直+1f 破防+33f 下段 被康1-13f
  6A: 发生15f 持续15f Smash 破防+12f 被康1-29f(贴身打防中+23确反)
  3A: 发生16f Rift 破防+21f 下段 被康1-18f
  623B/C: 升龙(623C绿升/623B蓝球)
  236B/C: 扫把飞行
  22B/C: 火炬(22C台火)
  214B/C: 星炮(214C星炮)
  B_6C: 恐怖连段(B→6C→追打)
主力连段: AAAA→623C升龙 / AAA→B→6C→J2B / DA→236B
"""

# 键序: (名称, [(按键名元组, 持续控制帧), ...])
# 与灵梦宏库同构, 确认门/SC步等由train_rl执行器处理
MACROS_MARISA = [
    # ---- 移动/防御(与灵梦共享物理, 无需改动) ----
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
    # ---- 魔理沙体术(帧数据标定; 2026-09-22 hitlab修复: 方向预置6帧[阀值5标定, 灵梦实测外推], 同帧按=吞键) ----
    ("5A",   [(("A",), 10)]),                            # 发生11f 近距主力
    # 5A确认(用户2026-09-29): 单发5A+confirm → 命中放623C取消, 落空截断=安全5A
    ("5A确认", [(("A",), 10), ((), 2), ("confirm", 0),
               (("right",), 3), (("down",), 3),
               (("down", "right", "C"), 10)]),   # 5A→确认→623C绿升
    ("2A确认", [(("down",), 6), (("down", "A"), 10), ((), 2), ("confirm", 0),
               (("down", "B"), 10), ((), 3),
               (("right",), 3), (("down",), 3),
               (("down", "right", "C"), 10)]),   # 2A→确认→2B→623C
    ("2A",   [(("down",), 6), (("down", "A"), 10)]),     # 发生10f 下段
    ("6A",   [(("right",), 6), (("right", "A"), 14)]),   # 发生15f Smash 可SC取消
    ("3A",   [(("down",), 6), (("down", "right"), 2), (("down", "right", "A"), 12)]),  # 发生16f 下段Rift
    ("5B",   [(("B",), 10)]),                            # 激光
    ("6B",   [(("right",), 6), (("right", "B"), 10)]),   # 弹
    ("2B",   [(("down",), 6), (("down", "B"), 10)]),     # 弹(蓄力0.1*5灵)
    ("5C",   [(("C",), 12)]),
    ("6C",   [(("right",), 6), (("right", "C"), 12)]),   # 主力弹幕(接B_6C连)
    ("2C",   [(("down",), 6), (("down", "C"), 12)]),
    ("jB",   [(("up",), 6), (("up",), 2), (("B",), 14)]),
    ("j2B",  [(("up",), 6), (("down",), 2), (("down", "B"), 14)]),               # 空对地弹幕
    ("jC",   [(("up",), 6), (("up",), 2), (("C",), 14)]),
    # ---- 魔理沙必杀(指令技) ----
    ("236B", [(("down",), 3), (("down", "right"), 3), (("right", "B"), 10)]),  # 扫把
    ("236C", [(("down",), 3), (("down", "right"), 3), (("right", "C"), 12)]),  # 扫把C
    ("623B", [(("right",), 3), (("down",), 3), (("down", "right", "B"), 10)]), # 升龙B(蓝球)
    ("623C", [(("right",), 3), (("down",), 3), (("down", "right", "C"), 10)]), # 升龙C(绿升)
    ("22B",  [(("down",), 3), (("down",), 3), (("down", "B"), 12)]),                  # hitlab修复: 原松键后同帧=吞键
    ("22C",  [(("down",), 3), (("down",), 3), (("down", "C"), 12)]),                  # hitlab修复: 同上
    ("214B", [(("down",), 3), (("down", "left"), 3), (("left", "B"), 10)]),    # 星炮B
    ("214C", [(("down",), 3), (("down", "left"), 3), (("left", "C"), 12)]),    # 星炮C(214星炮)
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
    # ---- 魔理沙空压 ----
    ("jA",   [(("up",), 6), (("A",), 10)]),
    ("j6A",  [(("up",), 6), (("right",), 2), (("right", "A"), 12)]),
    ("j8A",  [(("up",), 6), (("up",), 2), (("up", "A"), 12)]),
    ("j2A",  [(("up",), 6), (("down",), 2), (("down", "A"), 12)]),
    # ---- 魔理沙民工连(攻略: AAAA→623C主力 / AAA→B→6C→J2B / DA→236B) ----
    ("连段A", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("right",), 3), (("down",), 3), (("down", "right", "C"), 10)]),  # A→确认→AAA→623C,   # AAAA→623C绿升
    ("连段B", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("B",), 10), ((), 3), (("right", "C"), 12), ((), 3), (("up",), 8), (("down", "B"), 14)]),  # A→确认→AA→B→6C→J2B
    # R39(第十轮§4-3): 尾步原("up","down","B")同轴后写覆盖=实际2B;
    # 改B6C连同款(先up跳8帧再down+B)=真J2B
    ("连段C", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("right", "B"), 10), ((), 3), (("right",), 3), (("down",), 3), (("down", "right", "C"), 10)]),  # A→确认→AA→6B→623C,   # AAA→6B→623C
    # ---- 魔理沙压制链(攻略: AAA→B板中/6B→6C→追打) ----
    ("压制A", [(("down",), 6), (("down", "A"), 8), ((), 3), ("cconfirm", 0),
              (("right", "A"), 10), ((), 3),
              (("down", "B"), 10), ((), 3), (("right", "D"), 6), (("right", "A"), 9)]),
    ("压制B", [(("up",), 6), (("right", "A"), 12), ("cconfirm", 0), (("C",), 12), ((), 2),
              (("down",), 3), (("down", "right"), 3), (("right", "B"), 10)]),
    # ---- B_6C恐怖连段(攻略: B→6C→浮空追打) ----
    ("B6C连", [(("B",), 10), ((), 3),
               ("confirm", 0),
               (("right", "C"), 12), ((), 3),
               (("up",), 8), (("down", "B"), 14)]),   # B→6C→J2B追打
    # ---- 符卡 ----
    ("卡·星星",   [("sc:200", 0), ((), 14)]),   # 恋符「マスタースパーク」费3
    ("卡·钻头",   [("sc:202", 0), ((), 12)]),   # 魔砲「ファイナルスパーク」费5
    ("卡·星炮SC", [("sc:214", 0), ((), 18)]),   # 魔廃「ディープエコロジカルボム」费4
    ("卡·邪恋",   [("sc:219", 0), ((), 14)]),   # 邪恋「実りやすいマスタースパーク」费5
    ("卡·药水",   [("sc:1", 0), ((), 10)]),
    ("卡·灵击",   [("sc:0", 0), ((), 12)]),
    ("卡·当前",   [("sc:-1", 0), ((), 10)]),
    # ---- R31 Trialmode导入(末位追加契约) ----
    ("TM·6a终结",
     [(("right",), 6), (("right",), 6), (("right", "A"), 10), ((), 2),
      ("confirm", 0), ("sc:219", 0)]),
    # Trialmode 6177伤 3段: 6→6a→sc219(SC终结连)
    # R39(第十轮§4-2): confirm门移到6A攻击键之后(原在走路后=4帧无伤害必截断)
    ("TM·必杀SC连",
     [(("right",), 6), (("right",), 3), (("down",), 3),
      (("down", "right"), 3),
      (("C", "down", "right"), 10), ((), 2), ("confirm", 0),
      ((), 17), ("sc:219", 0)]),
    # Trialmode 5022伤 3段: 6→623c→sc219(中难度含SC) R39: 门后移同上
    # ---- R34 连段原子化试点(架构差距#1/#2: 决策频率+开环执行) ----
    # 原子间模型决策(看untech margin/位置/资源选继续或停):
    # 比TM连段更细粒度, 每原子3-20帧, 决策频率从~10帧提升到~5帧。
    # 帧数来源: Trialmode #10(3100伤) expected帧偏移。
    ("原子·确认5A",
     [(("A",), 6), ((), 2), ("confirm", 0)]),
    # 起手原子: 6帧5A+确认门(命中才继续,落空自动截断)
    ("原子·地面链",
     [(("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6),
      ((), 3), (("B",), 10), ((), 3),
      (("down",), 3), (("down", "right"), 3), (("right", "C"), 10)]),
    # 地面链原子: 5AA→5AAA→5B→236C(帧偏移15/15/17/12)
    ("原子·空链",
     [(("down",), 4), (("up", "right"), 8),
      (("A",), 8), ((), 11),
      (("down",), 2), (("down",), 4), (("down", "A"), 10), ((), 4),
      (("down", "C"), 10)]),
    # 空链原子: hjc9→j5A→j2A→j2C(帧偏移42/5/16/24)
    ("原子·收尾",
     [(("right", "D"), 8), ((), 8),
      (("down",), 2), (("down",), 4), (("down", "A"), 10)]),
    # 收尾原子: j66→j2A(帧偏移35/9) — 空中冲刺追击终结
]

MACRO_NAMES_MARISA = [m[0] for m in MACROS_MARISA]
N_MACROS_MARISA = len(MACROS_MARISA)

# 集合(与灵梦同构的分类, 供pmask/whiff_cost用)

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



_RAW = list(MACROS_MARISA)
MACROS_MARISA = [(n, _norm_presteps(sc)) for n, sc in _RAW]
# D13配套: 精确受影响集合导出(重播种工具消费, 替代宽口径)
NORMALIZED_AFFECTED = {n for (n, s0), (_, s1) in zip(_RAW, MACROS_MARISA)
                      if s0 != s1}

MELEE_MACROS_MARISA = {"5A", "2A", "6A", "3A", "623B", "623C", "B6C连", "5A确认", "2A确认"}
BULLET_MACROS_MARISA = {"5B", "6B", "2B", "5C", "6C", "2C", "jB", "j2B", "jC", "236B", "236C"}
SKILL_MACROS_MARISA = {"236B", "236C", "623B", "623C", "22B", "22C", "214B", "214C"}
DASH_MACROS_MARISA = {"前冲", "后冲", "空冲", "高跳", "斜上冲", "斜后跳", "结界2", "结界4",
                      "飞翔", "空翔前", "空翔后", "空冲后", "DA"}
GUARD_MACROS_MARISA = {"立防", "蹲防", "空防"}
AIR_MACROS_MARISA = {"jA", "j6A", "j8A", "j2A", "j2B", "jC"}
COMBO_MACROS_MARISA = {"连段A", "连段B", "连段C", "B6C连", "TM·6a终结", "TM·必杀SC连", "原子·确认5A", "原子·地面链", "原子·空链", "原子·收尾"}
STRING_MACROS_MARISA = {"压制A", "压制B"}
SC_MACROS_MARISA = {"卡·星星", "卡·钻头", "卡·星炮SC", "卡·邪恋", "卡·药水", "卡·灵击", "卡·当前"}

# 符卡消费表(从card_tables: 魔理沙卡费)
SC_COST_MARISA = {0: 1, 1: 1, 200: 3, 202: 5, 203: 5, 204: 4, 205: 2, 206: 3,
                  207: 5, 208: 1, 209: 3, 211: 2, 212: 3, 214: 4, 215: 2, 219: 5,
           # JZ-4系统卡(2026-10-14晚)
           2: 1, 3: 1, 4: 1, 12: 1, 14: 1}

# ==== R61n(C4): 表里择+压起身套件 ====
MACROS_MARISA.append(('择·中段', [(('right', 'D'), 6), ((), 2), (('right',), 6), (('right', 'A'), 10)]))
MACROS_MARISA.append(('择·下段', [(('right', 'D'), 6), ((), 2), (('right',), 6), (('down',), 6), (('down', 'A'), 10)]))
MACROS_MARISA.append(('择·投', [(('right', 'D'), 6), ((), 2), (('right',), 6), (('A', 'D'), 6)]))
MACROS_MARISA.append(('压起身·即', [(('down', 'A'), 12), ((), 4), (('A',), 8)]))
MACROS_MARISA.append(('压起身·延迟', [((), 8), (('A',), 10), ((), 2), (('down', 'A'), 10)]))
MACROS_MARISA.append(('压起身·空', [(('up',), 6), (('down',), 6), (('down', 'A'), 12)]))
MACROS_MARISA.append(('压起身·穿', [(('left', 'D'), 6), ((), 4), (('left',), 8)]))
MELEE_MACROS_MARISA |= {'择·中段', '择·下段', '择·投', '压起身·即', '压起身·延迟', '压起身·空', '压起身·穿'}
COMBO_MACROS_MARISA |= {'择·中段', '择·下段', '择·投', '压起身·即', '压起身·延迟', '压起身·空', '压起身·穿'}
MACRO_NAMES_MARISA = [m[0] for m in MACROS_MARISA]
# R61n: 追加宏的规范化(预置帧≥5 — hitlab标定阈值)
MACROS_MARISA[-7:] = [(n, _norm_presteps(sc)) for n, sc in MACROS_MARISA[-7:]]
MACRO_NAMES_MARISA = [m[0] for m in MACROS_MARISA]
N_MACROS_MARISA = len(MACROS_MARISA)
# CH-3/JZ-4扩展波(2026-10-14晚): 蓄力/系统卡/DD变体/HJC取消 —
# 尾部追加+基础宏派生(wave_ext), 索引稳定=ppo零初始化迁移适用
from macros.wave_ext import wave_extensions, wave_registrations
_WAVE = wave_extensions(MACROS_MARISA, 'marisa')
MACROS_MARISA.extend(_WAVE)
_B, _S, _D = wave_registrations(_WAVE)
BULLET_MACROS_MARISA |= _B
SC_MACROS_MARISA |= _S
DASH_MACROS_MARISA |= _D
MACROS_MARISA[-len(_WAVE):] = [(n, _norm_presteps(sc)) for n, sc in MACROS_MARISA[-len(_WAVE):]]
MACRO_NAMES_MARISA = [m[0] for m in MACROS_MARISA]
N_MACROS_MARISA = len(MACROS_MARISA)
