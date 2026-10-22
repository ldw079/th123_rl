# -*- coding: utf-8 -*-
"""宏动作层: 策略输出"招式宏"而非裸按键。

背景: 方向+按键的组合有独立招式表现(6B≠5B), 必杀技需要指令序列(236+B 等)——
帧级独立采样探索永远发现不了指令序列。宏层把动作空间坍缩到招式选择。

每个宏 = 脚本化的按键序列(每步持续若干控制帧), 执行期间不采样新动作。
"""

# (名称, [(按键名列表, 持续控制帧数), ...])
MACROS = [
    ("待机",  [((), 6)]),
    ("前进",  [(("right",), 6)]),
    ("后退",  [(("left",), 6)]),
    ("跳跃",  [(("up",), 12)]),
    ("后跳",  [(("up", "left"), 12)]),
    ("前冲",  [(("right", "D"), 8)]),
    ("后冲",  [(("left", "D"), 8)]),                  # 后方DASH, 发动帧带GRAZE
    ("空冲",  [(("up",), 10), (("right",), 3), ((), 1), (("right",), 6)]),  # 跳后66空中冲刺(不能延长,按住D会变飞翔)
    ("高跳",  [(("down",), 3), ((), 1), (("up",), 12)]),   # 2↷8大跳, 上升段带GRAZE(回避射击主力)
    ("斜上冲", [(("down",), 3), ((), 1), (("up", "right"), 12)]),  # 2↷9斜向大跳: 朝右上缝隙穿弹
    ("斜后跳", [(("down",), 3), ((), 1), (("up", "left"), 12)]),   # 2↷7斜后大跳: 朝左上缝隙穿弹
    ("立防",  [(("left",), 12)]),                     # 站立防御(中/上段)
    ("蹲防",  [(("down", "left"), 12)]),              # 下段防御
    ("空防",  [(("up", "left"), 10), (("left",), 8)]),  # 后跳起跳后按住后 = 空中防御
    ("5A",   [(("A",), 10)]),
    # 5A确认(用户2026-09-29: "5A命中后自动接后续连段"): 单发5A+confirm门
    # → 命中才放6A→623B取消尾段(与连段A尾段同源), 落空/被防截断=安全5A
    ("5A确认", [(("A",), 10), ((), 2), ("confirm", 0),
               (("right",), 6), (("right", "A"), 10), ((), 3),
               (("right",), 3), (("down",), 3), (("down", "right"), 6),
               (("down", "right", "B"), 10)]),   # 5A→确认→6A→623B
    ("2A确认", [(("down",), 6), (("down", "A"), 10), ((), 2), ("confirm", 0),
               (("down", "B"), 10), ((), 3),
               (("right",), 3), (("down",), 3), (("down", "right"), 6),
               (("down", "right", "B"), 10)]),   # 2A→确认→2B→623B
    # 2026-09-22 hitlab修复(灵梦实测): 方向+攻击同帧按下时, 攻击键边沿落在
    # 姿态转换帧上会被吞(实测l_act=6纯蹲无攻击) — 方向必须预置≥5帧再按键(hitlab标定阈值5, 库内取6)
    ("2A",   [(("down",), 6), (("down", "A"), 10)]),
    ("6A",   [(("right",), 6), (("right", "A"), 10)]),
    ("5B",   [(("B",), 10)]),
    ("6B",   [(("right",), 6), (("right", "B"), 10)]),
    ("2B",   [(("down",), 6), (("down", "B"), 10)]),
    ("jB",   [(("up",), 6), (("up",), 2), (("B",), 14)]),
    ("5C",   [(("C",), 12)]),
    ("6C",   [(("right",), 6), (("right", "C"), 12)]),
    ("236B", [(("down",), 3), (("down", "right"), 3), (("right", "B"), 10)]),
    ("236C", [(("down",), 3), (("down", "right"), 3), (("right", "C"), 12)]),
    ("623B", [(("right",), 3), (("down",), 3), (("down", "right", "B"), 10)]),
    ("22C",  [(("down",), 3), (("down",), 3), (("down", "C"), 12)]),  # hitlab修复(阈值5标定): 松键后down+C同帧=吞键, 改持续按住
    ("214B", [(("left",), 3), (("down", "left"), 3), (("left", "B"), 10)]),
    # ---- 受攻侧工具箱(攻略 g2/39-44, 角落死循环对策) ----
    ("受身",  [(("left",), 4), (("left", "A"), 8)]),      # 吹飞追击时间结束: 方向+任意键, 15F完全无敌
    ("起身穿", [(("right",), 4), (("right", "A"), 14)]),   # 倒地中按紧6+键: 移动起身, 占位消失可穿人逃离
    ("结界2", [(("down",), 2), (("down", "D"), 2), (("down",), 1), (("down", "D"), 8)]),  # 2DD 防御硬直中, 角落脱压终极手段
    ("结界4", [(("left",), 2), (("left", "D"), 2), (("left",), 1), (("left", "D"), 8)]),  # 4DD 完全无敌后撤(碎1珠全回灵)
    ("DA",   [(("right", "D"), 6), (("right", "A"), 10)]),   # 突进技: 冲刺中6A(灵梦10F, 全角色最快档 g1/85)
    ("飞翔",  [(("up",), 10), (("right", "D"), 16)]),        # 地面起跳接飞翔: 空中GRAZE主力(g2/17)
    # ---- 空中擦弹补全(攻略: 空中GRAZE主力是飞翔; 空中66/44为空中冲刺) ----
    ("空翔前", [(("right", "D"), 16)]),        # 空中直接飞翔前进(地面按下=前冲, 策略按自身高度选用)
    ("空翔后", [(("left", "D"), 16)]),         # 空中飞翔后撤
    ("空冲后", [(("left",), 3), ((), 1), (("left",), 6)]),   # 空中44后冲(左向空中冲刺)
    # ---- 空压武器包(灵梦攻略r3: 空压三段 JA→J6A/J8A→JC 是角色核心立回) ----
    ("jA",   [(("up",), 6), (("A",), 10)]),             # 空中中性体术
    ("j6A",  [(("up",), 6), (("right",), 2), (("right", "A"), 12)]),     # 空中前踢: 空压主力/推板核心
    ("j8A",  [(("up",), 6), (("up",), 2), (("up", "A"), 12)]),        # 空中上段: 空对空
    ("j2A",  [(("up",), 6), (("down",), 2), (("down", "A"), 12)]),      # 空中下段: 空压收尾/压起身打逆
    ("j2B",  [(("up", "B"), 14)]),                      # 低空J2B: 封位/压起身(jB同款低空出法)
    ("jC",   [(("up",), 6), (("up",), 2), (("C",), 14)]),                      # 低空JC: 空压三段收尾/无缝推板
    # ---- 民工连(攻略r1新手篇路线; hit-confirm版: "confirm"步=确认门,
    #      起手命中(对手掉血)才放后半段, 被防/落空立刻截断交还决策权 — 修开环对赌) ----
    ("连段A", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("right", "A"), 10), ((), 3), (("right",), 3), (("down",), 3), (("down", "right"), 6), (("down", "right", "B"), 10)]),   # A→确认→AAA→6A→623B,   # AAAA→确认→6A-623B
    ("连段B", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("right", "D"), 6), (("right", "A"), 10), ((), 3), (("right",), 3), (("down",), 3), (("down", "right"), 6), (("down", "right", "B"), 10)]),   # A→确认→AAA→DA→623B,   # AAAA→确认→DA-623B
    ("连段C", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("down", "B"), 10), ((), 3), (("right",), 3), (("down",), 3), (("down", "right"), 6), (("down", "right", "B"), 10)]),   # A→确认→AA→2B→623B,   # AAA→确认→2B-623B
    # ---- 压制链(攻略r3; cconfirm接触确认门: 命中或被防都继续 — 防反连段本职,
    #      对手蹲防时继续磨防钉人, 纯落空才截断 — 修: 旧confirm门把它阉割成hit-only) ----
    ("压制A", [(("down",), 6), (("down", "A"), 8), ((), 3), ("cconfirm", 0),
              (("right", "A"), 10), ((), 3),
              (("down", "B"), 10), ((), 3), (("right", "D"), 6), (("right", "A"), 9)]),
    ("压制B", [(("up",), 6), (("right", "A"), 12), ("cconfirm", 0), (("C",), 12), ((), 2),
              (("down",), 3), (("down", "right"), 3), (("right", "B"), 10)]),
    # ---- 空连/版边路由(位置特化, 攻略r1: #22版边对空JA-J6A-JC, #11版边AAA-B-C-JB-JA-AAAA) ----
    ("空连A", [(("up",), 6), (("A",), 10), ("cconfirm", 0),      # 对手空中: jA起手接触确认
              (("up",), 2), (("right", "A"), 10), ((), 2),       # j6A 追打
              (("up",), 2), (("C",), 12)]),                      # jC 收尾
    ("版边连A", [(("A",), 4), ((), 2), ("confirm", 0), (("A",), 4), ((), 2), (("A",), 6), ((), 3), (("B",), 10), ((), 3), (("C",), 12), ((), 3), (("up",), 6), (("B",), 12), ((), 2), (("up",), 2), (("A",), 10), ((), 2), (("A",), 4)]),  # A→确认→AA→B-C-jB-jA-A,                                     # A收(版边安定)
    # ---- 符卡系统(Phase C, 2026-09-07 全链实测): "sc:ID"步=转U选中目标卡→按I用卡。
    # 消费语义: 系统卡/符卡 耗费数张手牌(选中卡起连吞), 技能卡只耗自身1张。
    # 手牌不足/无目标卡/旋转一整圈未命中 → 整宏作废交还决策权(执行器处理)。----
    ("卡·鬼神玉", [("sc:210", 0), ((), 18)]),   # 宝具「陰陽鬼神玉」费4: 大伤害终结
    ("卡·妙珠",   [("sc:200", 0), ((), 14)]),   # 灵符「夢想妙珠」费2: 弹幕符卡
    ("卡·灵击札", [("sc:0", 0), ((), 12)]),     # 「霊撃札」费1: 无敌防反脱连段
    ("卡·药水",   [("sc:1", 0), ((), 10)]),     # 「マジックポーション」费1: 灵力回满
    ("卡·当前",   [("sc:-1", 0), ((), 10)]),    # 不旋转直接用当前选中卡(技能卡装载等)
    # ---- R31 Trialmode连段包导入(2026-10-02, tools/trialmode_to_macro.py
    # 生成; 末位追加契约 — 新宏必须追加在列表末尾) ----
    ("TM·2a连",
     [(("down",), 6), (("down", "A"), 10), ((), 2), ("confirm", 0),
      ((), 9),
      (("down",), 6), (("down", "B"), 10),
      (("C",), 12), ((), 22),
      (("down",), 4), (("up", "right"), 8),
      (("right",), 6), (("right", "A"), 12)]),
    # Trialmode: 2a→2b→5c→hj9→j6a(灵梦包, 帧偏移精确)
    # R39(第十轮§4-2): confirm门移到首个攻击键之后(原在蹲置后=4帧无伤害必截断)
    ("TM·4a连",
     [(("left",), 6), (("left", "A"), 10), ((), 2), ("confirm", 0),
      (("left",), 6), (("left", "A"), 10),
      (("right",), 3), (("down",), 3), (("down", "right"), 3),
      (("B", "down", "right"), 10)]),
    # Trialmode: 4a→4a→d623b(灵梦背向连段) R39: 门后移同上
    # ---- R35 原子化(差距#1): Trialmode帧偏移 ----
    ("原子·确认5A",
     [(("A",), 6), ((), 2), ("confirm", 0)]),
    ("原子·地面链",
     [(("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 6),
      ((), 3), (("B",), 10)]),
    ("原子·空链",
     [(("down",), 4), (("up",), 8),
      (("A",), 8), ((), 11),
      (("down",), 2), (("down",), 4), (("down", "A"), 10)]),
    ("原子·收尾",
     [(("right", "D"), 8), ((), 8),
      (("down",), 2), (("down",), 4), (("down", "A"), 10)]),
]

MACRO_NAMES = [m[0] for m in MACROS]
N_MACROS = len(MACROS)

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



_RAW = list(MACROS)
MACROS = [(n, _norm_presteps(sc)) for n, sc in _RAW]
# D13配套: 精确受影响集合导出(重播种工具消费, 替代宽口径)
NORMALIZED_AFFECTED = {n for (n, s0), (_, s1) in zip(_RAW, MACROS)
                       if s0 != s1}

# 分支门启用·线A(2026-10-14, plans/branch_gate_activation): 12门宏
# confirm二值→branch四路 — 同名同前缀(训练面/BC前缀兼容零变化);
# 路由步骤经_norm_presteps规范化(执行器直插队列不走主管线)
from macros_branch import upgrade_branches   # noqa: E402
MACROS = upgrade_branches(MACROS, norm=_norm_presteps)


MELEE_MACROS = {"5A", "2A", "6A", "623B", "空连A", "5A确认", "2A确认"}  # 近身判定类(远距空放受罚; 空连另需敌空中)
BULLET_MACROS = {"5B", "6B", "2B", "5C", "6C", "jB", "236B", "236C"}   # 弹幕类(贴身空放受罚: 无近身判定)
SKILL_MACROS = {"236B", "236C", "623B", "22C", "214B"}   # 指令必杀
DASH_MACROS = {"前冲", "后冲", "空冲", "高跳", "斜上冲", "斜后跳", "结界2", "结界4",
               "飞翔", "空翔前", "空翔后", "空冲后", "DA"}   # 全方向×全高度GRAZE位移(攻略g1/17,g2/19,21)
GUARD_MACROS = {"立防", "蹲防", "空防"}          # 防御姿态(按住后方向)
AIR_MACROS = {"jA", "j6A", "j8A", "j2A", "j2B", "jC"}          # 空压武器包(攻略r3空压三段)
COMBO_MACROS = {"连段A", "连段B", "连段C", "版边连A", "TM·2a连", "TM·4a连", "原子·确认5A", "原子·地面链", "原子·空链", "原子·收尾"}          # 民工连(命中后整套输出; 版边连另需敌在角)
STRING_MACROS = {"压制A", "压制B"}                             # 压制链(推板/伪压, 接触确认)
SC_MACROS = {"卡·鬼神玉", "卡·妙珠", "卡·灵击札", "卡·药水", "卡·当前"}   # 符卡使用类

ATTACK_MACROS_ALL = (MELEE_MACROS | BULLET_MACROS | SKILL_MACROS
                     | AIR_MACROS | COMBO_MACROS | STRING_MACROS)   # 全部攻击类(贴身滞留罚豁免用)

# 符卡消费表(实测矩阵 2026-09-07): 系统卡/符卡=耗费数张, 技能卡(1xx)=只耗1张
# R39(第十轮§4-6): 补204/206/207/214(原缺→默认费1高估可用性, 游戏内使用
# 失败→重试作废) — 耗费值取card_tables(解包CSV), 与既有6项全部吻合
SC_COST = {0: 1, 1: 1, 200: 2, 201: 5, 204: 2, 206: 4, 207: 3,
           208: 1, 209: 2, 210: 4, 214: 3, 219: 5,
           # JZ-4系统卡(2026-10-14晚): 2怀表/3白楼剑/4人偶/12铜钱/
           # 14绯想剑 — 系统卡均耗1张(card_tables口径)
           2: 1, 3: 1, 4: 1, 12: 1, 14: 1}


def sc_consumption(card_id):
    """用一张卡的手牌消耗数(技能卡只耗自身, 其余=费)。"""
    if 100 <= card_id < 200:
        return 1
    return SC_COST.get(card_id, 1)


# SC宏名 → 目标卡ID(从脚本"sc:ID"步自动解析; -1=不旋转用当前选中)
SC_TARGET = {}
for _n, _scr in MACROS:
    for _ks, _fr in _scr:
        if isinstance(_ks, str) and _ks.startswith("sc:"):
            SC_TARGET[_n] = int(_ks[3:])


def sc_tick(sc_run, tgt, cs, kb, keymap):
    """"sc:ID"步单控制帧状态机(Phase C): 转U至目标卡→按I用卡→校验消费。
    每控制帧调用一次; 返回 (sc_run, pop, abort):
      pop=当前步完成可弹出(宏继续放后续后摇步); abort=作废整宏(手牌不足/
      无目标卡/旋转一整圈未命中/I按下后未消费(重试1次仍败, 如药水在灵力
      已满时的冗余使用) — 交还决策权)。
    首帧传 sc_run=None(按 tgt+cs 初始化, 门控失败直接 abort)。
    时序实测依据: U按2帧即换选中, I按3帧生效; 换卡后2帧读数已刷新。"""
    if sc_run is None:
        if not cs or not cs["hand_ids"]:
            return None, False, True
        use_id = tgt if tgt >= 0 else cs["sel_id"]
        if use_id is None or use_id not in cs["hand_ids"] \
                or cs["size"] < sc_consumption(use_id):
            return None, False, True
        return {"tgt": tgt, "phase": "chk", "tries": 0, "hold": 0}, False, False
    if not cs or not cs["hand_ids"]:
        return None, False, True
    ph = sc_run["phase"]
    if ph == "chk":
        if sc_run["tgt"] < 0 or cs["sel_id"] == sc_run["tgt"]:
            sc_run["phase"], sc_run["hold"] = "i_down", 0
            sc_run["size_i"] = cs["size"]       # 按I时的手牌数(消费校验基线)
        elif sc_run["tries"] >= (cs["size"] or 0) + 1:
            return None, False, True      # 转了一整圈没找到 → 作废
        else:
            sc_run["phase"], sc_run["hold"] = "u_down", 0
    elif ph == "u_down":
        kb.apply([keymap["SCSW"]])
        sc_run["hold"] += 1
        if sc_run["hold"] >= 2:
            kb.apply([])
            sc_run["phase"], sc_run["hold"] = "u_gap", 0
    elif ph == "u_gap":
        kb.apply([])
        sc_run["hold"] += 1
        if sc_run["hold"] >= 2:
            sc_run["phase"], sc_run["hold"] = "chk", 0
            sc_run["tries"] += 1
    elif ph == "i_down":
        kb.apply([keymap["SC"]])
        sc_run["hold"] += 1
        if sc_run["hold"] >= 3:
            kb.apply([])
            sc_run["phase"], sc_run["hold"] = "ver", 0
    elif ph == "ver":
        kb.apply([])
        sc_run["hold"] += 1
        if sc_run["hold"] >= 3:            # 留3帧给游戏结算消费
            if (cs["size"] or 0) < sc_run.get("size_i", 99):
                return None, True, False   # 已消费 → 弹步
            sc_run["iretry"] = sc_run.get("iretry", 0) + 1
            if sc_run["iretry"] > 1:
                return None, False, True   # 重按一次仍未消费 → 作废
            sc_run["phase"], sc_run["hold"] = "i_down", 0   # 瞬态未中: 重按I
    return sc_run, False, False


def whiff_cost(name):
    """空放惩罚的成本倍率, 按灵力回复停止时间标定(攻略outline_14, 62fps换算):
    B系45F→0.73 / C系62F→1.0 / 必杀120F→1.94(锁灵~2秒, 重罚) / 体术不耗灵→1.0
    体术系例外(2026-09-08用户指正"体术代替位移"): 连段空挥旧罚-0.06但宏内
    前移薅到接近塑形分≈+0.05~0.1 → 净收益为正=奖励黑客。倍率提2.5把
    空挥净收益翻负, 位移宏保留干净的接近收入(教义: 移动接近, 到位才打)。"""
    if name in MELEE_MACROS or name in COMBO_MACROS or name in STRING_MACROS:
        return 2.5
    if name in SKILL_MACROS:
        f = 120.0
    elif name in ("5C", "6C"):
        f = 62.0
    elif name in ("5B", "6B", "2B", "jB"):
        f = 45.0
    else:
        return 1.0
    return f / 62.0   # 62fps教义: 帧转秒 /62


def macro_script(idx):
    """返回宏的执行脚本: [(按键名元组, 持续帧), ...]"""
    return MACROS[idx][1]

# ==== R61n(C4): 表里择+压起身套件 ====
MACROS.append(('择·中段', [(('right', 'D'), 6), ((), 2), (('right',), 6), (('right', 'A'), 10)]))
MACROS.append(('择·下段', [(('right', 'D'), 6), ((), 2), (('right',), 6), (('down',), 6), (('down', 'A'), 10)]))
MACROS.append(('择·投', [(('right', 'D'), 6), ((), 2), (('right',), 6), (('A', 'D'), 6)]))
MACROS.append(('压起身·即', [(('down', 'A'), 12), ((), 4), (('A',), 8)]))
MACROS.append(('压起身·延迟', [((), 8), (('A',), 10), ((), 2), (('down', 'A'), 10)]))
MACROS.append(('压起身·空', [(('up',), 6), (('down',), 6), (('down', 'A'), 12)]))
MACROS.append(('压起身·穿', [(('left', 'D'), 6), ((), 4), (('left',), 8)]))
MELEE_MACROS |= {'择·中段', '择·下段', '择·投', '压起身·即', '压起身·延迟', '压起身·空', '压起身·穿'}
COMBO_MACROS |= {'择·中段', '择·下段', '择·投', '压起身·即', '压起身·延迟', '压起身·空', '压起身·穿'}
MACRO_NAMES = [m[0] for m in MACROS]
# R61n: 追加宏的规范化(预置帧≥5 — hitlab标定阈值)
MACROS[-7:] = [(n, _norm_presteps(sc)) for n, sc in MACROS[-7:]]
# CH-3/JZ-4扩展波(2026-10-14晚): 蓄力/系统卡/DD变体/HJC取消 —
# **真末位追加**(择/压起身之后 — R23契约; 首版插在upgrade后致择/压起身
# 被顶移+18索引, 模型迁移错挂+BC标签错位, 深夜修复)
from macros.wave_ext import wave_extensions, wave_registrations  # noqa: E402
_WAVE = wave_extensions(MACROS, 'reimu')
MACROS = MACROS + _WAVE
# CH-3/JZ-4扩展波集合注册(2026-10-14晚)
_WB, _WS, _WD = wave_registrations(_WAVE)
BULLET_MACROS |= _WB
SC_MACROS |= _WS
DASH_MACROS |= _WD

MACRO_NAMES = [m[0] for m in MACROS]
N_MACROS = len(MACROS)

# task-29: 实机无此招/宏不可用 → 掩码禁用(不删 id, 保模型兼容)
DISABLED_MACROS = {'214B'}
