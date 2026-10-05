# -*- coding: utf-8 -*-
"""标准决策树(灵梦·依据CHM攻略r1/r3/r2a) + 模型树对比自检工具。

用法:
  standard_tree.py standard    # 打印标准树(态势节点→攻略教义→标准动作)
  standard_tree.py audit       # 读distill_data.npz, 蒸馏模型树并与标准树逐节点对比,
                               # 输出偏离矩阵(缺陷清单: 节点×标准动作×模型实际×频率)
标准树的特征维度与训练态势向量一致(距离带/高度/角区/弹幕/灵力), 保证两树可比。
依据:
  r3/39-44 Wiki距离论(远:布置弹幕渐近; 中:空弹>66>打击; 近:择时抢帧;
    地对空:基本不利靠DC/升龙; 空对空:弹幕压制或44摸奖; 空对地:性能微妙需观察)
  r3/34-37 大佬立回(TR后手控灵/食欲封魔针+抄地走路/河豚教科书/勇者猛攻紧缚)
  r3/48-155 压制篇(版边无缝压制链/打防/压起身)
  r2a 移动篇(44性能优秀/大跳上升GRAZE)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 本目录相对化(第六轮审计沙箱密闭性): 硬编码绝对根会让变异沙箱的
# import 解析回真实根, 变异测试全部失效

# ===== 标准树: (态势节点描述, 判定条件(基于distill特征), 标准动作集(攻略教义), 依据章节) =====
# distill_X 特征(11列): [dx, spirit, close, macro_id, game_frame,
#                        dy高度差, opp_air敌空中, bullet_near弹近, we_left我左, tti, opp_corner敌在角]
# 判定条件接整行 r(10列), 与态势向量同源
STANDARD_TREE = [
    ("远距离(dx>450)", lambda r: r[0] > 450,
     [("5B", "弹幕布置渐进接近(r3/39: 布置弹幕制作有利状况)"),
      ("236B", "高相杀强度弹幕压制(UU以外用妖怪, r3/39)"),
      ("前进", "渐近(不直冲: 灵梦移速慢不适合直接冲, r3/38)"),
      ("高跳", "上升GRAZE抢占中空(r2a: 大跳上升段GRAZE)")],
     "r3/39"),
    ("中距离(250<dx<450)", lambda r: 250 < r[0] <= 450,
     [("jB", "空中弹幕射击>66>打击的中距基本形(r3/40)"),
      ("j6A", "空压突进(66>JA前端能打到则换J2A, r3/40)"),
      ("DA", "突进技间隙抓(r2a: 灵梦DA 10F最快档)"),
      ("5B", "地面弹幕牵制")],
     "r3/40"),
    ("近距离(130<dx<250)", lambda r: 130 < r[0] <= 250,
     [("5A", "范围长的物理打击择时使用(r3/41: 把握时机很重要)"),
      ("2A", "下段体术(贴身择)"),
      ("蹲防", "对手出招时防御(抢帧知识是关键, r3/41)"),
      ("连段A", "命中确认后整套AAAA-6A-623B(hit-confirm)"),
      ("压制A", "被防也续磨的防反连段(cconfirm后近距正解, r3/94)")],
     "r3/41+94"),
    ("贴身(dx<130)+灵力足", lambda r: r[0] <= 130 and r[1] > 0.3,
     [("连段A", "AAAA-6A-623B(命中后伤害最大化)"),
      ("连段C", "AAA-2B-623B(低灵力收尾)"),
      ("压制A", "2A-6A-2B-DA(最强伪压, r3/94)"),
      ("蹲防", "对手先手时防御(灵梦近距被抢则不利, r3/41)")],
     "r3/41+48"),
    ("贴身+灵力枯竭", lambda r: r[0] <= 130 and r[1] <= 0.3,
     [("后退", "拉开回灵(无灵力=无法攻击与防御, g2/6)"),
      ("立防", "撑过灵力真空期")],
     "g2/6"),
    ("对手在空中+自己在地面", lambda r: r[6] > 0.5,
     [("2B", "地面斜上射击对空(用户指正2026-09-08: 灵梦优秀对空, 此前漏列)"),
      ("空连A", "版边对空JA-J6A-JC juggle(攻略#22, 空中追打主力)"),
      ("6B", "对空射击(r3/42: 性能收益差但可用)"),
      ("623B", "升龙拼判定(能拼赢则用, r3/42)"),
      ("高跳", "升空抢上盘对空轨迹(空对空弹幕压制, r3/42)")],
     "r3/42+#22+用户"),
    ("对手在版边", lambda r: r[10] > 0.5 and r[6] < 0.5,
     [("版边连A", "版边AAA-B-C-JB-JA-AAAA民工(攻略#11, 角上伤害最大化)"),
      ("压制A", "伪压磨防钉角(r3/94, cconfirm被防续磨)"),
      ("连段A", "版中同款民工(角上安定)"),
      ("蹲防", "被先手时防御兜底")],
     "#11+r3/94"),
    ("弹幕近身(<220)", lambda r: r[7] > 0.5,
     [("前冲", "GRAZE位移穿弹(g1/17)"),
      ("后冲", "后方DASH发动帧带GRAZE(g2/19)"),
      ("高跳", "上升段GRAZE回避射击主力(r2a)"),
      ("立防", "无把握时防御兜底")],
     "g1/17+g2/19"),
    ("来袭弹TTI<0.3s", lambda r: r[9] < 0.3,
     [("后冲", "短窗位移离开弹道"),
      ("高跳", "垂直脱离弹道平面"),
      ("立防", "来不及动的兜底(吃磨耗)")],
     "擦弹教义"),
]

# hitlab定案(2026-09-23): 2A判定框只及蹲姿高度(站姿/空中零接触) —
# 树特征无蹲姿列, 2A在此节点按"对手蹲姿时"的条件推荐解读
# ===== 魔理沙标准树(依据: 水杨酸黑白自编攻略23.09.09 + 则wiki黑白;
# 帧数据见macros_marisa.py头注释。态势分段与灵梦树同构保持可比,
# 动作集按黑白机体教义: 弹幕立回+扫把机动+绿升对空) =====
STANDARD_TREE_MARISA = [
    ("远距离(dx>450)", lambda r: r[0] > 450,
     [("6C", "主力弹幕远压(黑白攻略: 6C为弹幕主力, 接B_6C恐怖连)"),
      ("5B", "激光直线牵制(发生快·无限射程)"),
      ("214C", "星炮C远程压制(214星炮)"),
      ("前进", "渐近(弹幕角色不直冲, 与灵梦同则g1/39)")],
     "黑白攻略+g1/39"),
    ("中距离(250<dx<450)", lambda r: 250 < r[0] <= 450,
     [("jB", "空中弹幕射击中距基本形"),
      ("j2B", "空对地弹幕(连段B收尾J2B同款)"),
      ("DA", "突进技间隙抓(DA→236B连段起手)"),
      ("236B", "扫把飞行突进(黑白机动特色)")],
     "黑白攻略"),
    ("近距离(130<dx<250)", lambda r: 130 < r[0] <= 250,
     [("5A", "发生11F近距主力(帧数据: 被康1-15F)"),
      ("2A", "发生10F下段择(被康1-13F)"),
      ("蹲防", "对手出招时防御"),
      ("连段A", "命中确认AAAA→623C绿升(hit-confirm)"),
      ("压制A", "AAA→B板中被防续磨(cconfirm)")],
     "黑白攻略帧数据"),
    ("贴身(dx<130)+灵力足", lambda r: r[0] <= 130 and r[1] > 0.3,
     [("连段A", "AAAA→623C绿升(主力连, 伤害最大化)"),
      ("连段B", "AAA→B→6C→J2B(中灵力收尾)"),
      ("B6C连", "B→6C→浮空追打(恐怖连段)"),
      ("蹲防", "对手先手时防御(贴身被抢则不利)")],
     "黑白攻略: 主力连段三条"),
    ("贴身+灵力枯竭", lambda r: r[0] <= 130 and r[1] <= 0.3,
     [("后退", "拉开回灵(无灵力=无法攻击与防御, g2/6)"),
      ("立防", "撑过灵力真空期")],
     "g2/6"),
    ("对手在空中+自己在地面", lambda r: r[6] > 0.5,
     [("623C", "绿升龙拼判定(黑白对空主力)"),
      ("5B", "激光对空牵制(直线速射)"),
      ("2B", "斜上射击对空"),
      ("高跳", "升空抢上盘(空对空弹幕压制)")],
     "黑白攻略: 升龙C"),
    ("对手在版边", lambda r: r[10] > 0.5 and r[6] < 0.5,
     [("压制A", "AAA→B板中磨防钉角"),
      ("压制B", "J6A→C→236B压制链(6B→6C→追打)"),
      ("连段A", "版中同款民工(角上安定)"),
      ("蹲防", "被先手时防御兜底")],
     "黑白攻略: 压制链"),
    ("弹幕近身(<220)", lambda r: r[7] > 0.5,
     [("前冲", "GRAZE位移穿弹(g1/17)"),
      ("后冲", "后方DASH发动帧带GRAZE(g2/19)"),
      ("高跳", "上升段GRAZE回避射击主力(r2a)"),
      ("立防", "无把握时防御兜底")],
     "g1/17+g2/19"),
    ("来袭弹TTI<0.3s", lambda r: r[9] < 0.3,
     [("后冲", "短窗位移离开弹道"),
      ("高跳", "垂直脱离弹道平面"),
      ("立防", "来不及动的兜底(吃磨耗)")],
     "擦弹教义"),
]

# ===== 萃香标准树(依据: 酔人瘾子-西瓜1.10攻略 水杨酸+679L补充;
# 帧数据见macros_suika.py头注释。机体教义: 重机·快 jab·投技混合·DC超大弹) =====
STANDARD_TREE_SUIKA = [
    ("远距离(dx>450)", lambda r: r[0] > 450,
     [("6C", "DC超大弹远压(西瓜攻略: 核心技, 可蓄力)"),
      ("5B", "射击牵制(发生17F)"),
      ("5C", "烟弹布置(22F+30F爆炸·区域控制)"),
      ("前进", "渐近(重机不急, 与灵梦同则g1/39)")],
     "西瓜攻略+g1/39"),
    ("中距离(250<dx<450)", lambda r: 250 < r[0] <= 450,
     [("DA", "突进长判定(发生15F持续30F·DA→DC连段起手)"),
      ("jB", "空中射击中距牵制"),
      ("6B", "SMASH弹(发生18F·吹飞制造)"),
      ("236B", "火拳突进(妖鬼-密-)")],
     "西瓜攻略帧数据"),
    ("近距离(130<dx<250)", lambda r: 130 < r[0] <= 250,
     [("5A", "发生9F全角色最快档·抢帧主力(全体26F)"),
      ("2A", "发生10F下段择(出手速度优秀)"),
      ("蹲防", "对手出招时防御"),
      ("连段A", "命中确认AAAA→623萃鬼投(hit-confirm)"),
      ("压制A", "2A→6A→2B→DA被防续磨(cconfirm)")],
     "西瓜攻略: A系极快"),
    ("贴身(dx<130)+灵力足", lambda r: r[0] <= 130 and r[1] > 0.3,
     [("连段A", "AAAA→623萃鬼投(主力连·投技收尾不可防)"),
      ("连段B", "AAA→6B→22B地火(中灵力收尾)"),
      ("623B", "萃鬼投·指令投(对手蹲防时破龟择)"),
      ("蹲防", "对手先手时防御(重机被抢不利更大)")],
     "西瓜攻略: 主力连+投技混合"),
    ("贴身+灵力枯竭", lambda r: r[0] <= 130 and r[1] <= 0.3,
     [("后退", "拉开回灵(无灵力=无法攻击与防御, g2/6)"),
      ("立防", "撑过灵力真空期")],
     "g2/6"),
    ("对手在空中+自己在地面", lambda r: r[6] > 0.5,
     [("3A", "对空Rift(发生25F·攻略标注对空·全体62F慢需预判)"),
      ("jA", "升空抢判定(发生9F持续20F长判定)"),
      ("5B", "射击对空牵制"),
      ("高跳", "升空抢上盘(AAAA超大判定空对空)")],
     "西瓜攻略: 3A对空"),
    ("对手在版边", lambda r: r[10] > 0.5 and r[6] < 0.5,
     [("压制A", "2A→6A→2B→DA磨防钉角"),
      ("连段A", "版边AAAA→萃鬼投(角上伤害最大化)"),
      ("623B", "投技破龟(版边蹲防死守的正解)"),
      ("蹲防", "被先手时防御兜底")],
     "西瓜攻略: 版边投压"),
    ("弹幕近身(<220)", lambda r: r[7] > 0.5,
     [("前冲", "GRAZE位移穿弹(g1/17)"),
      ("后冲", "后方DASH发动帧带GRAZE(g2/19)"),
      ("高跳", "上升段GRAZE回避射击主力(r2a)"),
      ("立防", "无把握时防御兜底")],
     "g1/17+g2/19"),
    ("来袭弹TTI<0.3s", lambda r: r[9] < 0.3,
     [("后冲", "短窗位移离开弹道"),
      ("高跳", "垂直脱离弹道平面"),
      ("立防", "来不及动的兜底(吃磨耗)")],
     "擦弹教义"),
]

TREES = {"reimu": STANDARD_TREE,
         "marisa": STANDARD_TREE_MARISA,
         "suika": STANDARD_TREE_SUIKA}


def print_standard(char="reimu"):
    tree = TREES[char]
    print("=" * 70)
    print("%s标准决策树(依据攻略)" % {"reimu": "灵梦", "marisa": "魔理沙",
                                    "suika": "萃香"}[char])
    print("=" * 70)
    for name, cond, actions, src in tree:
        print("\n[%s]  (依据: %s)" % (name, src))
        for act, why in actions:
            print("  → %-8s %s" % (act, why))


def audit(char, suffix=""):
    """蒸馏模型实际行为, 逐节点对比标准树, 输出偏离矩阵。
    R16修复: 原mname三元的先len(None)后判None → reimu审计恒崩(rc=1,
    外环日志AUDIT_FAILED); 且MACRO_NAMES从未import → 兜底路径NameError。"""
    from macros import MACRO_NAMES   # reimu兜底表(本模块原漏import)
    NAMES = {"reimu": None, "marisa": __import__("macros_marisa").MACRO_NAMES_MARISA,
             "suika": __import__("macros_suika").MACRO_NAMES_SUIKA}
    tree = TREES[char]
    try:
        data = np.load(r"D:\temp\th123_models\distill_data_%s%s.npz" % (char, suffix))
        X, Y = data["X"], data["Y"].astype(int)
    except Exception as e:
        print("蒸馏数据不可读:", e)
        return
    if X.shape[1] < 11:
        print("旧格式蒸馏数据(维度 %d), 需新批训练收集11列格式" % X.shape[1])
        return
    use = X[:, 0] >= 0
    X, Y = X[use], Y[use]
    print("蒸馏样本: %d 条" % len(X))
    print("\n" + "=" * 70)
    print("自检: %s标准树 vs 模型实际(偏离矩阵)" % char)
    print("=" * 70)
    defects = []
    for name, cond, actions, src in tree:
        mask = np.array([cond(r) for r in X])
        n = int(mask.sum())
        if n < 10:
            continue
        sub_Y = Y[mask]
        counts = {}
        for m in sub_Y:
            _names = NAMES.get(char)
            if _names and 0 <= int(m) < len(_names):
                mname = _names[int(m)]
            elif 0 <= int(m) < len(MACRO_NAMES):
                mname = MACRO_NAMES[int(m)]
            else:
                mname = "?%d" % int(m)
            counts[mname] = counts.get(mname, 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
        std_set = {a for a, _ in actions}
        # 偏离: 模型在此节点高频选的动作 ∉ 标准动作集
        offlist = [(m, c) for m, c in top if m not in std_set]
        coverage = sum(c for m, c in counts.items() if m in std_set) / n
        print("\n[%s] 样本%d | 标准覆盖率 %.0f%%" % (name, n, coverage * 100))
        print("  标准: %s" % " ".join(a for a, _ in actions))
        print("  实际TOP: %s" % " ".join("%s%d" % kv for kv in top))
        if offlist:
            for m, c in offlist[:3]:
                defects.append((name, m, c, c / n))
            print("  ⚠ 偏离: %s" % " ".join("%s×%d(%.0f%%)" % (m, c, 100.0 * c / n)
                                            for m, c in offlist[:3]))
        else:
            print("  ✓ 与标准一致")
    if defects:
        print("\n" + "=" * 70)
        print("缺陷清单(按偏离频率排序)")
        print("=" * 70)
        for name, m, c, frac in sorted(defects, key=lambda d: -d[3])[:10]:
            print("  [%s] 非标动作 %s 占 %.0f%% (%d次)" % (name, m, frac * 100, c))
        # R17阈值红线(用户2026-09-29反思): 偏离矩阵曾只是"日志里的数字",
        # 无阈值无消费者 — 木桩/塌缩时代照常输出矩阵、无人被触发。
        # ≥20%的节点必须以红线形式可见(外环audit子进程输出直接携带)。
        hot = [(n, m, f) for n, m, c, f in defects if f >= 0.20]
        if hot:
            print("\n>>> [策略树红线] %d个节点非标率≥20%%: %s <<<"
                  % (len(hot), "; ".join("%s×%s%.0f%%" % (n, m, f * 100)
                                         for n, m, f in hot[:5])))
    else:
        print("\n✓ 全部节点与标准一致")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "standard"
    ch = sys.argv[2] if len(sys.argv) > 2 else "reimu"
    if cmd == "standard":
        print_standard(ch)
    elif cmd == "audit":
        audit(ch)
    else:
        print(__doc__)
