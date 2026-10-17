import struct
# -*- coding: utf-8 -*-
"""TM通道训练器: PinkySmile SokuAITrainer 协议 + 现有PPO/宏库。

**本文件遵循 METHODOLOGY.md(宪法文档)** — 奖励尺度定律/掩码规范/
宏保真三律/持久化清单/自检体系见彼处, 改参前先对照。

架构:
- 环境: TMEnv(独立游戏进程, TCP锁步, 按局重启) — 默认自对弈(VS_PLAYER双控:
  P1=本策略, P2=池快照SideDriver只读加载; --opp指定对手池, 2026-09-23主线)
- 观测: 虚拟视觉战场网格(包对象渲染, conv主干) + 包侧特征260维核心
- 动作: 宏ID(角色宏库) → 键名序列 → 输入包位图
 - 奖励: HP差(伤害-承伤) + KO(终局段入账) + 墙区罚 + 空挥(W_WHIFF标定) + 擦弹/防/避微奖励
- confirm/cconfirm门: 包HP精确判定(v1简化: 命中继续/落空截断)
- 符卡宏: v1掩掉(卡状态机待v2接包手牌)
- 多环: 局结束自动重启, 每局一个episode → PPO更新

用法: python train_tm.py --char reimu --port 20800 --episodes 100 --tps 60
"""
import argparse
import os
import glob
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
# R17(§3.5): 删除死导入 from perception import frame_features —
# 视觉早已改为_render_frame虚拟渲染, 全文件无使用(v3迁移残留)
from feat_builder import FeatureBuilder, eff_untech
from opp_model import GUARD_ALL_IDS   # R20: hitlab实测防御ID集(5/8/151/158)
from reach_maps import resolve_reach, resolve_startup, REACH_MARGIN
from tm_env import TMEnv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DIR = os.path.dirname(os.path.abspath(__file__))
# 模型/蒸馏数据迁至D盘(C盘曾爆满致训练中断 — stdout_rl.txt 1.4GB事件).
# 首次运行自动迁移旧文件; 代码仍在原处.
# 可迁移化: 路径经kit_config(config.json > 环境变量 > 本机默认)
from kit_config import STORE_DIR
try:
    os.makedirs(STORE_DIR, exist_ok=True)
except OSError:
    STORE_DIR = DIR  # D盘不可用时回退到代码目录(P3-3a修复)
for _f in os.listdir(DIR):
    # P3-3c/d修复: 加macro_counts_前缀, 加model_ppo.(无下划线)孤儿
    if _f.startswith(("model_ppo_", "model_ppo.", "model_bc", "distill_data_",
                      "macro_counts_")) and \
       (_f.endswith(".npz") or _f.endswith(".npy")):
        _src = os.path.join(DIR, _f)
        _dst = os.path.join(STORE_DIR, _f)
        if not os.path.exists(_dst):
            import shutil
            try:
                shutil.copy2(_src, _dst)  # copy2不删原件(P3-3b: 不做"唯一副本移动")
            except (OSError, shutil.Error):
                pass

# ---- 角色宏库装载 ----
CHAR_LIBS = {}


def _load_char_libs():
    import macros as m_reimu
    import macros.marisa as m_marisa
    import macros.suika as m_suika
    # P1-1修复: 距离掩码用全攻击集(近战+弹幕+必杀+连段+压制+空中体术)
    # 原版只用了MELEE(5)+BULLET(8), 漏了COMBO/STRING/SKILL/AIR/DA等15+宏
    def _attack_set(melee, bullet, skill, combo, string, air):
        return melee | bullet | skill | combo | string | air | {"DA"}

    CHAR_LIBS["reimu"] = {
        "id": 0, "macros": m_reimu.MACROS, "names": [m[0] for m in m_reimu.MACROS],
        "sc": m_reimu.SC_MACROS, "air": m_reimu.AIR_MACROS,
        "melee": m_reimu.MELEE_MACROS, "bullet": m_reimu.BULLET_MACROS,
        "skill": m_reimu.SKILL_MACROS, "combo": m_reimu.COMBO_MACROS,
        "string": m_reimu.STRING_MACROS,
        "sc_cost": m_reimu.SC_COST,
        "attack": _attack_set(m_reimu.MELEE_MACROS, m_reimu.BULLET_MACROS,
                              m_reimu.SKILL_MACROS, m_reimu.COMBO_MACROS,
                              m_reimu.STRING_MACROS, m_reimu.AIR_MACROS),
        # JZ-3.2: 投技宏集(无敌窗内掩蔽; 灵梦无指令投)
        "throw": {"择·投"},
    }
    CHAR_LIBS["marisa"] = {
        "id": 1, "macros": m_marisa.MACROS_MARISA,
        "names": m_marisa.MACRO_NAMES_MARISA,
        "sc": m_marisa.SC_MACROS_MARISA, "air": m_marisa.AIR_MACROS_MARISA,
        "melee": m_marisa.MELEE_MACROS_MARISA, "bullet": m_marisa.BULLET_MACROS_MARISA,
        "skill": m_marisa.SKILL_MACROS_MARISA, "combo": m_marisa.COMBO_MACROS_MARISA,
        "string": m_marisa.STRING_MACROS_MARISA,
        "sc_cost": m_marisa.SC_COST_MARISA,
        "attack": _attack_set(m_marisa.MELEE_MACROS_MARISA, m_marisa.BULLET_MACROS_MARISA,
                              m_marisa.SKILL_MACROS_MARISA, m_marisa.COMBO_MACROS_MARISA,
                              m_marisa.STRING_MACROS_MARISA, m_marisa.AIR_MACROS_MARISA),
        "throw": {"择·投"},        # JZ-3.2(黑白无指令投)
    }
    CHAR_LIBS["suika"] = {
        "id": 9, "macros": m_suika.MACROS_SUIKA,
        "names": m_suika.MACRO_NAMES_SUIKA,
        "sc": m_suika.SC_MACROS_SUIKA, "air": m_suika.AIR_MACROS_SUIKA,
        "melee": m_suika.MELEE_MACROS_SUIKA, "bullet": m_suika.BULLET_MACROS_SUIKA,
        "skill": m_suika.SKILL_MACROS_SUIKA, "combo": m_suika.COMBO_MACROS_SUIKA,
        "string": m_suika.STRING_MACROS_SUIKA,
        "sc_cost": m_suika.SC_COST_SUIKA,
        "attack": _attack_set(m_suika.MELEE_MACROS_SUIKA, m_suika.BULLET_MACROS_SUIKA,
                              m_suika.SKILL_MACROS_SUIKA, m_suika.COMBO_MACROS_SUIKA,
                              m_suika.STRING_MACROS_SUIKA, m_suika.AIR_MACROS_SUIKA),
        "throw": {"择·投", "623B"},   # JZ-3.2(萃鬼=指令投, suika.py:57)
    }
    # R44(2026-10-04): 六新角色 — tools/gen_newchar_libs.py生成的同构骨架库
    # (66宏: 通用体术+指令技+确认连段+原子宏+系统/角色符卡)。
    # 角色特化连段/换技宏待hitlab/Trialmode标定后末位追加。
    _NEW_SPECS = [
        ('sakuya', 2), ('patchouli', 4), ('yuyuko', 7),
        ('reisen', 10), ('komachi', 12), ('tenshi', 14),
        # R45: 剩余11角色 — 全20角色注册
        ('alice', 3), ('youmu', 5), ('remilia', 6), ('yukari', 8),
        ('aya', 11), ('iku', 13), ('sanae', 15), ('cirno', 16),
        ('meiling', 17), ('utsuho', 18), ('suwako', 19),
    ]
    for _nc, _nid in _NEW_SPECS:
        _m = __import__('macros.%s' % _nc, fromlist=['*'])
        _U = _nc.upper()
        CHAR_LIBS[_nc] = {
            "id": _nid, "macros": getattr(_m, 'MACROS_%s' % _U),
            "names": getattr(_m, 'MACRO_NAMES_%s' % _U),
            "sc": getattr(_m, '%s_SC_NAMES' % _U),
            "air": getattr(_m, '%s_AIR_MACROS' % _U),
            "melee": getattr(_m, '%s_MELEE_MACROS' % _U),
            "bullet": getattr(_m, '%s_BULLET_MACROS' % _U),
            "skill": getattr(_m, '%s_SKILL_MACROS' % _U),
            "combo": getattr(_m, '%s_COMBO_MACROS' % _U),
            "string": getattr(_m, '%s_STRING_MACROS' % _U),
            "sc_cost": getattr(_m, 'SC_COST_%s' % _U),
            "attack": _attack_set(
                getattr(_m, '%s_MELEE_MACROS' % _U),
                getattr(_m, '%s_BULLET_MACROS' % _U),
                getattr(_m, '%s_SKILL_MACROS' % _U),
                getattr(_m, '%s_COMBO_MACROS' % _U),
                getattr(_m, '%s_STRING_MACROS' % _U),
                getattr(_m, '%s_AIR_MACROS' % _U)),
            # JZ-3.2: 骨架库统一含择·投; 指令投(如有)待hitlab标定后补
            "throw": {"择·投"},
        }


_load_char_libs()


def _parse_sc_targets(macros_list):
    """宏名→目标卡ID(从脚本sc:ID步解析; -1=不旋转用当前)"""
    out = {}
    for name, script in macros_list:
        for ks, _ in script:
            if isinstance(ks, str) and ks.startswith("sc:"):
                out[name] = int(ks[3:])
    return out

# ---- 奖励权重(v2验证区回迁 2026-09-22: 伤害0.02/胜负1.2时结果信号仅占2%) ----
R_DMG = 0.004         # 每点伤害(v2等效/330区)
R_TAKEN = -0.005      # 每点承伤(略高: 防莽)
R_KO_ROUND = 10.0     # 回合胜(结果主导, v2 KO15区; 惨胜变亏: ×(0.3+血量))
R_KO_LOSE = -10.0     # 回合负
# R35: R_WALL/R_CORNER_ADV/SPIRIT_KEEP已由势函数POT_W覆盖(死常量删除)
# v2微奖励回迁(正向定律: 只用加成)
R_GRAZE = 0.40        # 擦弹穿弹(近失弹逼近窗内零承伤)
GRAZE_FULL_CAP = 20.0 # 全额段上限(此降为低费率 — 用户2026-09-29: 高手
                      # 作战大量擦弹, 硬顶=悬崖: 打满后零边际激励, 惩罚的
                      # 恰是擦弹大师; 两级费率防"躲弹不赢"退化而非封顶)
GRAZE_LOW_RATE = 0.01 # 超额段费率。实测(2026-09-29两级0.10版): 真实
                      # 擦弹需求2250~4041帧/局(旧cap12掩盖了6~35倍),
                      # 0.10费率下擦弹收入+419碾压KO±20 → "KO-0.1但总回报
                      # +417"的躲弹退化已发生。0.01: 方向性保留(每帧都算
                      # 数,无悬崖), 经济学回胜负主导(最坏≈+60<伤害±100)
# R61(用户2026-10-05裁定"d+鼓励快速胜利"): 0.01线性低段在超长局下复活收割
# (suika实测: 拖满10408帧收+122 — 拉长比赛本身成了收割手段)。低段费率按
# 局内已用帧数线性衰减至0 → 低段总收入硬上界=GRAZE_LOW_RATE×GRAZE_SAT_F/2
# ≈30, 无论拖多久; 正常局(≤6000帧)前中期擦弹收入几乎不受影响。
GRAZE_SAT_F = 6000.0   # 衰减饱和帧(≈1.6回合的常规 match 时长)
# R61: 快胜奖金 — 回合胜时按剩余时间比例加成(速胜+6 → 顶满时长胜+0),
# 与d互补: d杀"拖时间收入", 此项让"果断终结"有额外经济价值。
R_FASTWIN = 6.0        # 快胜奖金满额(回合)
ROUND_FRAMES = 3720.0  # 回合时长(60s×62fps教义)


def graze_low_rate(f):
    """R61-d: 低段擦弹费率(按局内已用帧数f线性衰减)。"""
    return GRAZE_LOW_RATE * max(0.0, 1.0 - f / GRAZE_SAT_F)


def fastwin_bonus(round_elapsed, d=1):
    """R61: 快胜奖金 = R_FASTWIN × 剩余时间比例(顶满时长胜=0)。"""
    return R_FASTWIN * max(0.0, 1.0 - round_elapsed / ROUND_FRAMES) * d


def ko_round_reward(my_hp, opp_hp, win):
    """R61b(用户2026-10-05"KO时双方血量差计入"): 回合结算按血量差分档。
    win: R_KO_ROUND×(0.3+margin), margin=(my−opp)/10000∈[0,1] —
         KO胜时opp≈0 ≡ 原"惨胜变亏"系数(数值连续); 顶时胜区分
         碾压(高margin)与擦分险胜(低margin)。
    lose: R_KO_LOSE×(0.5+0.5×opp_margin) — 惜败(对手残血)半罚,
         被碾压(对手满血)全罚(原恒-10不分惨烈, 是奖励经济学缺口)。
    值域: win∈[3,13], lose∈[-10,-5](败必负, 不与胜负经济学冲突)。"""
    if win:
        margin = min(1.0, max(0.0, (my_hp - opp_hp) / 10000.0))
        return R_KO_ROUND * (0.3 + margin)
    om = min(1.0, max(0.0, (opp_hp - my_hp) / 10000.0))
    return R_KO_LOSE * (0.5 + 0.5 * om)
# R39(第十轮P3-8): R_GUARD/R_GUARD_PREP防御帧奖励通道与_guard_decay_tracker
# 已删(R35势函数化后成死代码, 日志恒零误导调参); 格挡正反馈由势函数承担
# (格挡→HP不掉→势不降), BC锚引导选防。GUARD_PREP_MACROS保留(R34中断用)。
GUARD_PREP_MACROS = ("立防", "蹲防")  # 真格挡宏(不含空防/后跳/结界)
# R49: 帧级事件系统(L3时序墙) — R52: 用原名导入(代码中直接引用frame_events.*)
import frame_events
from frame_events import FrameEventDetector, pick_reaction, reaction_mask
from frame_events import E_NONE as _FE_NONE
# R61u(C1): 统一宏执行器(双拷贝终结 — train_tm与side_driver共同调用)
import macro_executor
_FRAME_EV_NAMES = {v: k for k, v in frame_events.__dict__.items()
                   if k.startswith('E_') and isinstance(v, int)}

# R43方案A(池刷新制度): 本角色每POOL_SNAPSHOT_EVERY局快照入池(只写自己
# 目录, 跨训练器零竞争), 滚动保留POOL_KEEP个; 对手路径在**轮换时动态解析**
# (原启动时冻结 — 10-03批次28h全程打10-02旧对手的根因)。
# D3'(R65)按实测吞吐重标定推导(原值为云6-12×吞吐时代设定, 撤云后验证):
#   实测 ~5min/局/actor ≈ 12局/h/角色 → POOL_SNAPSHOT_EVERY=50聚合局
#   ≈ 4.2h/池快照; POOL_K=3 → 对手可选窗 ≈ 12.6h; 对手周期(D3'后27位×5局
#   =135局/轮 ≈ 11h/轮)主角色位每轮命中1-2个快照代 — 快照分辨率≈轮换
#   分辨率(不浪费也不欠采样); league静态位(seed)标签永不变, min_games=5
#   在fleet聚合stats下约1轮命中即过中性期。结论: 三常量在本地吞吐下
#   数值维持, 推导入册(METHODOLOGY 2.66) — 重标定的交付物是推导本身,
#   下次吞吐变化(如actor扩容)按此式重算。
POOL_SNAPSHOT_EVERY = 50
POOL_KEEP = 6
POOL_K = 3   # R43: 池深(原main()局部变量 — _resolve_pool模块级引用需要提升)
# R43方案B(COM难度阶梯, 课程学习): 近COM_CLIMB_N局胜率≥COM_CLIMB_WR升一级,
# 近COM_FALL_N局<COM_FALL_WR降一级, 夹[0,3]。回火以熵监控替代(宪法2.29裁定)。
COM_CLIMB_N = 20
COM_CLIMB_WR = 0.5
COM_FALL_N = 40
COM_FALL_WR = 0.2
# 立防/蹲防/空防/后跳/斜后跳/后冲/结界类宏, 在压力下(对手<300或弹<220)
# 零承伤执行 → 有收入。无压力撤退不付(防挂机), 角落撤退另有R_WALL对冲。
R_EVADE = 0.20        # 规避让弹道(R17: 0.08→0.20; 归因干净: 需80px
                      # 真实位移脱弹, 攻击宏蹭不到)
W_WHIFF = 0.06        # 空挥基罚(×_whiff_cost倍率; P2-1清理: 死常量
                      # R_PARRY/WHIFF_B/C/SKILL从未接线, 已删)


def mixed_behavior_p(p_pi, mid, probe_legal=None, vg_on=False,
                     vg_best=None):
    """P1-5(从零#4): 行为策略的混合边际概率 — stored_logp用真分布。

    行为构成: 12%均匀探针(legal非空时) + 88%π(·|mask,bias)采样,
    之后30%价值引导重选(argmaxV确定覆盖, 探针选择亦可被覆盖):
      P(a) = 0.7·(0.12·U(a) + 0.88·π(a)) + 0.3·1{a=vg_best}
    (VG未触发/W1v缺席时无0.3项; legal空时无0.12项)。
    p_pi: π(mid)标量(调用方经_pi_forward(mask,bias)取得)。
    """
    p = float(p_pi)
    if probe_legal:
        p = 0.88 * p + (0.12 / len(probe_legal)
                        if mid in probe_legal else 0.0)
    if vg_on:
        p = 0.7 * p + (0.3 if mid == vg_best else 0.0)
    return max(p, 1e-10)
LOW_SPIRIT_PEN = 300.0  # 灵力不足阈值(满1000): 低于此值起手攻击宏且空挥
                      # → 罚×2(用户2026-09-29: "明知没灵还出招"与"打空了"
                      # 是两种过错; 直打suika灵力枯竭22B×23%红线)
# R62(用户2026-10-06"把胜负和回报挂钩"): 败回合微收入追扣率。
# 诊断实证: 回报-胜率相关性-0.52~-0.68(三角色齐报) — 拖时间擦弹的
# 微收入(+21~49/局)碾压结果信号(KO摆动±5~13/回合), 输局反而高回报。
# 修法: 微收入(擦弹+规避)在回合结算时与胜负挂钩 — 胜回合全额保留
# (消耗战取胜是合法赢法), 败回合追扣70%。算术: 输局2回合≈KO-15
# -0.7×35=-39.5 vs 赢局≈+16+35=+51 → 符号翻转, 结果信号重新主导。
MICRO_TAX_LOSS = 0.7


def micro_tax(micro_bank, round_won):
    """R62: 回合末微收入追扣(胜负挂钩). 胜=0(全额保留), 败=MICRO_TAX_LOSS×bank."""
    return 0.0 if round_won else MICRO_TAX_LOSS * micro_bank

# ==== R35 势函数奖励塑形(差距#5, Ng et al. 1999) ====
# 数学保证: 势函数塑形不改变最优策略 — 可刷分通道从根源消灭。
# 原理: r_shaped = γΦ(s') - Φ(s) + r_event
#   势函数Φ(s)只依赖状态(HP/灵力/位置/对手状态), 不依赖动作
#   → 停在某状态不能持续获得正奖励(势是差分, 不是持续流)
#   → "站防刷防御分"/"擦弹刷graze分"类exploit结构性不可能
# 权重从现有通道值映射(保持学习信号量级不变):
POT_W = {
    # A1-2(未决方案§A1-2, 10-12): 原opp_hp=+0.004 vs own_hp=-0.005 — 自保
    # 价值>伤害价值, 防御数学占优=被动性是奖励结构的正确解(F6全顶时/E1互证)。
    # 对称化±0.005(值域同量级, KO±10主通道不动); A/B: 24h对照F6 quick,
    # 顶时判负率<20%为目标, 净分下滑则回滚改走A1-4(反康对称项)。
    'opp_hp': 0.005,      # 对手HP降=正(映射R_DMG)
    'own_hp': -0.005,     # 我方HP降=负(映射R_TAKEN)
    'own_spirit': 0.0004, # 灵力高=好(映射SPIRIT_KEEP方向)
    'opp_corner': 0.003,  # 对手被角=好(映射R_CORNER_ADV)
    'own_corner': -0.003, # 我方被角=坏(映射R_WALL)
    # CE-7(2026-10-15用户批准立项, 部署排A1-2验收后):
    # 推板进度势 — 角项二值→距角连续(k_c使版中→贴角全程势差
    # ≈二值跳变的2-3倍); 势函数差分→推板每步有梯度(telescoping保持)
    'corner_progress': 0.0144,  # 对手距近角距离归一(0=贴角 1=版中)
    'card_gauge': 0.001,  # 卡牌充能=好(长期资源)
    # R61z(用户裁定"加进攻积极性奖励"): 距离势差 — 越近势越高,
    # 后退/跳跃逃跑→势降→负奖励; 前进→势升→正奖励.
    # 势函数telescoping保证不可刷分(往返净=0, 不同于事件奖励).
    # 权重0.15: 300px撤退≈0.45势损 ≈ 90点承伤(适度威慑);
    # 100px前进≈0.15势得 ≈ 30点伤害(温和激励).
    'engage': 0.15,
}
GAMMA_POT = 0.999   # R61c(B5): 势函数γ(Ng式r'=γΦ(s')−Φ(s); 原γ=1)
# R61z: 空中被动惩罚 — 空中>30帧且非攻击/非受击态 → 微负/帧
# (跳跃逃逸的"零惩罚盲区"修复; 攻击中/受击中空中不罚)
R_AIR_PASSIVE = 0.003
AIR_PASSIVE_GRACE = 30   # 宽限帧数(跳跃弧线的合法滞空)


def air_passive_exempt(left):
    """BH-4.2(bug档): 空中被动豁免 = 攻击中(300-599)或**真受击**
    (eff_untech>0)。原内联条件用原始untech — 自由飞翔(214)带残留
    读数被错误豁免, 反逃逸惩罚被削弱(R61z盲区); 抽出成可测函数。"""
    return ((300 <= left.get("action", 0) < 600)
            or eff_untech(left) > 0)


def state_potential(left, right, card_gauge_val=None):
    """势函数Φ(s): 状态质量度量 — 只看状态, 不看动作。
    R35: 从现有奖励通道的权重映射而来, 保持量级一致。
    可刷分不可能: 停在某状态→Φ不变→差分=0→零奖励。
    R61c(B5): card_gauge_val — 晴岚哨兵的冻结值覆盖(晴岚期卡牌被
    遮蔽, gauge读数不可信=伪势跳±2.0, 从零审计P2); None=用真值。"""
    p = 0.0
    p += POT_W['opp_hp'] * (10000 - right["hp"])
    p += POT_W['own_hp'] * (10000 - left["hp"])
    p += POT_W['own_spirit'] * left["spirit"]
    # 位置势: 离墙越远越好(telescoping, 版边自动最低)
    _ox = right["position.x"]
    _mx = left["position.x"]
    if (_ox < 120 or _ox > 1120) and 120 <= _mx <= 1120:
        p += POT_W['opp_corner']
    if _mx < 120 or _mx > 1120:
        p += POT_W['own_corner']
    # CE-7 推板进度势(连续角项) — **默认关**(部署排A1-2 A/B验收后);
    # 开启: 环境变量 TH123_CE7_POT=1; 立项已批(2026-10-15)但时点纪律是红线
    if os.environ.get('TH123_CE7_POT', '0') == '1':
        # 对手距近角越近→势越高(推板每步有梯度); own侧对称
        # 版中(0.64)→贴角(0.12)全程势差 = k_c×0.52 ≈ 0.0075
        # ≈ 二值跳变0.003的2.5倍(方案标定2-3倍; 测试钉住)
        _opp_to_corner = min(_ox, 1280.0 - _ox) / 1000.0   # 0=贴角 1=版中
        _own_to_corner = min(_mx, 1280.0 - _mx) / 1000.0
        p += POT_W['corner_progress'] * (1.0 - _opp_to_corner)   # 推对手向角
        p -= POT_W['corner_progress'] * (1.0 - _own_to_corner)   # 自己别被关角
    _cg = (left.get("cardGauge", 0) if card_gauge_val is None
           else card_gauge_val)
    p += POT_W['card_gauge'] * min(_cg, 2000)
    # R61z: 距离势差 — 距对手越近势越高(600px内线性递减).
    # 势函数差分性质: 后退→Φ降→负奖励; 前进→Φ升→正奖励;
    # 往返(退→进)→净差=0(telescoping, 不可刷分).
    _adx = abs(right["position.x"] - left["position.x"])
    p += POT_W['engage'] * max(0.0, (600.0 - _adx) / 100.0)
    return p

KEY_TO_BIT = {
    "up": ("V", 1), "down": ("V", -1),
    "left": ("H", -1), "right": ("H", 1),
    "A": ("A", True), "B": ("B", True), "C": ("C", True), "D": ("D", True),
}


def keys_to_input(keys, mirror=False):
    """宏键名元组 → TM输入dict。mirror=朝向镜像(**只翻水平轴**)。

    R63(P0-1, 2026-10-07架构审查): 原 `axis in ("H","V")` 把上下也翻了 —
    H/V极性见 soku_client2.KEYMAP/send_inputs: V是**屏幕上下**(up=+1),
    镜像是左右翻转, 上下语义不变。原版后果: `_last_dir<0` 时 j8A→j2A、
    高跳(down,(),up)退化成普通跳, 而轨迹/distill/bc_targets 记的仍是
    策略原本选的那一招 → 约一半决策的信用分配被污染(执行A、记录A、
    实际发生A的纵向镜像), 对手侧同款。

    判据(库内第三条独立证据): bc_match.keys_to_input 只翻H, 其docstring
    记录"原连V一起翻→换边段空中宏标签静默丢失/错配"=**同型bug已修在
    bc_match、漏在train_tm**; tools/branch_demo.py:200-202 同样只翻H。
    配对测试: test_mirror_axis_r63.py。
    """
    inp = {}
    for k in keys:
        if k in KEY_TO_BIT:
            axis, val = KEY_TO_BIT[k]
            if axis == "H" and mirror:
                val = -val
            inp[axis] = val
    return inp


def mir_keys(keys, mirror):
    if not mirror:
        return keys
    out = []
    for k in keys:
        if k == "left":
            out.append("right")
        elif k == "right":
            out.append("left")
        else:
            out.append(k)
    return tuple(out)


def _pool_snapshot_ok(path, n_macros):
    """fleet首跑缺陷③(2026-10-26木桩根因): 池快照维度守卫 —
    陈旧快照(宏数不符)装入当前SideDriver=近死对手(整局输出100),
    对局数据静默污染。拒载而非装坏(与learner宽度断言同哲学)。"""
    import numpy as _np
    try:
        d = _np.load(path)
        ok = int(d['W2'].shape[1]) == int(n_macros)
        d.close()
        return ok
    except Exception:
        return False


class TMTrainer:
    def __init__(self, char, port, tps=60, episodes=100, ep_timeout=300,
                 slot=None, render=False, opp=None, suffix="", com_difficulty=1):
        import random as _rnd
        from ppo import PPOTrainer
        self.char = char
        self.slot = slot
        self.render = render
        self.suffix = suffix
        self._deck_rng = _rnd.Random(hash(char) & 0xFFFF)  # R47: deck采样
        self._deck_arch_stats = {}   # C(L1): 对手流派战绩桶
        self._opp_deck_arch = None   # C: 当前局对手卡组原型
        self._opp_skill_stats = {}   # C-L2: 对手逐技能卡战绩桶
        self._opp_skillset = ()      # C-L2: 当前局对手技能卡签名
        self._opp_sc_stats = {}      # C-L3: 对手逐SC卡战绩桶
        self._opp_sys_stats = {}     # C-L3: 对手逐系统卡战绩桶
        self._opp_deck_scids = ()    # C-L3: 当前局对手SC id集
        self._opp_deck_sysids = ()   # C-L3: 当前局对手系统卡id集
        self._ep_count = 0                                  # R47: 课程进度
        self._ret_win_hist = []                             # R47: 回报-胜率仪表
        self.com_difficulty = com_difficulty
        # R61e(B6): 起读持久化难度 — 有存档则覆盖启动参数(重启不再回
        # Easy反复爬梯); --com-difficulty仅作无存档时的起点
        # 从零#2(fleet P2): 路径入属性(actor模式按actor隔离 — 原共享
        # 文件多写者=同角色多actor的阶梯状态互踩)
        self._com_diff_path = os.path.join(
            STORE_DIR, "com_difficulty_%s%s.json" % (char, suffix))
        try:
            import json as _json
            _cd = self._com_diff_path
            if os.path.exists(_cd):
                _d = _json.load(open(_cd, encoding="utf8"))["difficulty"]
                if 0 <= int(_d) <= 3:
                    self.com_difficulty = int(_d)
                    print("[COM阶梯] 续档难度%d(%s)" % (
                        self.com_difficulty,
                        ("Easy", "Normal", "Hard", "Lunatic")[
                            self.com_difficulty]))
        except (OSError, ValueError, KeyError):
            pass
        # R14: 对手角色ID(用于one-hot)
        self._opp_char_id = None     # 模型文件后缀(实验分支隔离, 防双训练器写同档)
        lib = CHAR_LIBS[char]
        self.macros = lib["macros"]
        self.n_macros = len(self.macros)
        self.sc_names = lib["sc"]
        # 基础掩码: 非符卡宏(符卡宏由每决策的可用性门控动态放开)
        self.base_mask = np.array(
            [m[0] not in self.sc_names for m in self.macros], dtype=bool)
        # 符卡目标/耗费表(v2 Phase C制度移植, TM包手牌数据驱动)
        self.sc_targets = _parse_sc_targets(self.macros)
        self.sc_cost_table = dict(lib["sc_cost"])
        self._sc_name_idx = {m[0]: i for i, m in enumerate(self.macros)}
        self._sc_run = None         # 状态机运行态
        self._sc_tgt = None         # 当前sc步目标
        self._sc_next_input = {}    # 下一帧要发的键(SW/SC)
        # 方向性攻击宏(方向键+攻击键同帧的步): 背向期间禁放 —
        # 冲刺/跳过顶时自动转向有延迟, 背向出6系/指令必杀=无效攻击(用户指正)
        _btn = {"A", "B", "C"}
        self.dir_attack = np.array([
            any((("right" in ks) or ("left" in ks)) and (_btn & set(ks))
                for ks, _ in m[1] if not isinstance(ks, str))
            for m in self.macros], dtype=bool)
        # 距离掩码宏集(P1-1修复: 全攻击集含连段/压制/必杀/空中体术, 不只MELEE/BULLET)
        names = [m[0] for m in self.macros]
        attack_set = lib["attack"]
        self.melee_idx = np.array([n in attack_set for n in names], dtype=bool)
        self.bullet_idx = np.array([n in lib["bullet"] for n in names], dtype=bool)
        # R60(F-9): 类级330门用的**近战子集** — 原用melee_idx(=全攻击集,
        # P1-1改的) → dx>330时连弹幕/远程技能一起禁采样, 远程立回结构性
        # 不可学(19轮全员漏网, 注释"弹幕不受影响"与行为矛盾)。
        # 近战=melee∪combo∪string(天然贴身类); 技能/弹幕放行 —
        # 技能射程由R24逐宏reach门精确限距, 类级栅栏只管天然近战。
        _near = (lib.get("melee", set()) | lib.get("combo", set())
                 | lib.get("string", set()))
        self.near_idx = np.array([n in _near for n in names], dtype=bool)
        # JZ-3.2(2026-10-14): 投技宏索引+对手投技无敌窗跟踪
        # (掩码层实现: 无敌窗内禁采样投技, 零奖励改动)
        self.throw_idx = np.array(
            [n in lib.get("throw", set()) for n in names], dtype=bool)
        from frame_events import ThrowInvulnTracker
        self._throw_invuln_trk = ThrowInvulnTracker()
        # R23(2026-10-02): 位置特化连段情境门控 — 架构文档§2.1声称
        # "版边连A敌在角才可用/空连A敌空中才可用", 实际从未实现(中场可采
        # 样版边连=confirm门只能止损, 决策已浪费)
        self.corner_combo_idx = np.array(["版边" in n for n in names],
                                         dtype=bool)
        # R39(第十轮§4-8): 空连门改精确名 — 子串匹配误伤萃香TM·空连终结/
        # TM·对空连与三库原子·空链(均为跳入链, 设计目标是打**地面**目标),
        # 被限制到罕见的对手浮空情形。只有真正需要对手浮空的空连A受限。
        self.air_combo_names = {"空连A"}
        self.air_combo_idx = np.array(
            [n in self.air_combo_names for n in names], dtype=bool)
        # R24: 宏射程(XML hitbox权威+SokuLib引擎枚举映射) — 掩码栅栏+
        # 射程差特征双通道, 模型"理解"范围而非仅硬写入
        # R25: 二维化(用户提醒: 判定二维勿忘纵向) — 横/纵各一数组
        # R28: 门控仅限攻击集宏 — 受身/起身穿等防御utility宏
        # 解析出射程也不许被距离门拦(自抓: 受身曾被dx门误禁)
        self.macro_reach, self.macro_reach_v = resolve_reach(
            lib["macros"], char)
        self.reach_mask_idx = self.macro_reach > 0
        self.reach_v_mask_idx = self.macro_reach_v > 0
        _atk_idx = np.array([n in lib["attack"] for n in names],
                            dtype=bool)
        self.reach_mask_idx &= _atk_idx
        self.reach_v_mask_idx &= _atk_idx
        # R30: 发生帧(untech差值特征用) — "出这招赶得上对手恢复吗"
        self.macro_startup = resolve_startup(lib["macros"], char)
        self.startup_mask_idx = self.macro_startup > 0

        # R24/R25/R30: 侧向量布局[宏N][上宏N][core][gap_x N][gap_y N]
        # [untech_margin N] — 射程块=空间范围理解, untech块=时序范围理解
        self.n_side = 5 * self.n_macros + FeatureBuilder.CORE_DIMS
        self.ppo = PPOTrainer(n_side=self.n_side, n_out=self.n_macros)
        # v2全量特征构建器(威胁网格+未来占据+卡牌+对手建模+势函数)
        self.feat_builder = FeatureBuilder(self.n_macros)
        self.feat_builder._char_name = char   # R17①: 技能等级查表用
        # v2新宏配额探索
        self.macro_counts_path = os.path.join(
            STORE_DIR, "macro_counts_%s.npy" % char)
        if os.path.exists(self.macro_counts_path):
            self.macro_counts = np.load(self.macro_counts_path).astype(np.int64)
            if len(self.macro_counts) < self.n_macros:
                self.macro_counts = np.concatenate([
                    self.macro_counts,
                    np.zeros(self.n_macros - len(self.macro_counts),
                             dtype=np.int64)])
        else:
            self.macro_counts = np.full(self.n_macros, 150, dtype=np.int64)
            for i, m in enumerate(self.macros):
                if m[0] in self.sc_names:
                    self.macro_counts[i] = 0
        # (R38第九轮审计P2-7: expert_ids属性全仓无消费者 — 已删)
        self.pi_path = os.path.join(STORE_DIR, "model_ppo_%s%s.npz" % (char, suffix))
        self.v_path = os.path.join(STORE_DIR, "model_ppo_%s%s_v.npz" % (char, suffix))
        self.macro_counts_path = os.path.join(
            STORE_DIR, "macro_counts_%s%s.npy" % (char, suffix))
        # 注: 上方208行的无后缀路径仅作加载源(实验分支继承主线宏计数),
        # 保存走本后缀路径(双训练器互斥纪律)
        if os.path.exists(self.pi_path):
            self.ppo.load(self.pi_path, self.v_path)
            print("[模型] 加载 %s" % self.pi_path)
        else:
            self.ppo.init_fresh(self.n_side)
            print("[模型] 全新初始化")
        import copy
        self._ppo_act = copy.deepcopy(self.ppo)   # 采样快照(异步更新流水线)
        self._upd_thread = None
        # R56(fleet): actor模式logP记录钩子 — 生产路径恒None(零行为变化);
        # fleet actor注入闭包后, 每决策点记录行为策略logP(a)(红线①的
        # 采样侧)。见 actor_worker.py / docs/scenario_b_fleet_design §3.1。
        self._fleet_logp_rec = None

        # 外环训练半环(2026-09-22): opp=[(char, model_path),...]轮换对手池快照
        # (VS_PLAYER双控: P1=本学习器, P2=只读SideDriver快照, §6.0纪律:
        #  对手只读加载防强弱漂移; 双方皆己方=合法自对弈, R1不变)
        self.opp_cycle = list(opp) if opp else None
        self._opp_i = 0
        self._opp_stats = {}      # label → [wins, losses]
        self._pool_rot = {}       # R43: 角色→池轮转指针(动态解析用)
        # E阶段1(系列方案§3.1): series_len=0=legacy(逐位现行), >0=系列赛
        # 轮换由SeriesManager发令(归因隔离: A/B期间保持legacy)
        self._series_mgr = None
        self._com_hist = []       # R43方案B: COM对局胜负序列(1胜0负)
        if self.opp_cycle:
            from side_driver import SideDriver
            _c0, _m0 = self.opp_cycle[0]
            if _c0 == "COM":
                # R61e(F3): COM作首位原SideDriver("COM")KeyError启动崩
                # (从零审计P2) — 镜像_rotate_opp的COM分支: opp=None=
                # VS_COM模式, 对手角色=己方镜像(R21)
                self.opp = None
                self._opp_char_id = None
                self.feat_builder._opp_char = self.char
                self._cur_opp_model = None
            else:
                self.opp = SideDriver(_c0, "R")
                self._wire_opp_ids(_c0)
                if _m0 is None:
                    _m0 = self._resolve_pool(_c0)
                # 池守卫拒载兜底(2026-10-15晨事故): 宏数换代期池快照全被
                # _pool_snapshot_ok滤光 → _m0=None → 原版对手驱动**未加载
                # 就上场**(空权重Wc1=None, 每局AttributeError崩溃循环,
                # 18:04池快照70宏 vs 88/93/91代码宏数)。未加载的驱动
                # 永不入局: 回退生产模型(恒为现行代际)。
                if _m0 is None:
                    _m0 = os.path.join(STORE_DIR, 'model_ppo_%s.npz' % _c0)
                    if os.path.exists(_m0):
                        print('[对手池] %s池快照全被维度守卫拒载 — '
                              '回退生产模型(换代期正常, 池将随对局刷新)'
                              % _c0)
                    else:
                        raise RuntimeError(
                            '%s无可用对手模型(池拒载+生产档缺失)' % _c0)
                self._cur_opp_model = _m0
                self.opp.load(_m0)
        else:
            self.opp = None
            self._cur_opp_model = None
        self.tps = tps
        self.episodes = episodes
        self.ep_timeout = ep_timeout
        self._load_bc_bank()
        self.env = self._make_env(port)

        # 视觉捕获(按PID找训练实例窗口)
        self._setup_capture()

        # 状态
        self.feat_hist = []
        self.last_macro = 0
        self.last_macro2 = 0
        self._last_dir = 0       # 当前朝向(±1) — 逐帧镜像用
        self._dir_frames = 0     # 距上次转向的帧数(转向延迟感知)

    def near_gate(self, mask, dx_abs):
        """R60(F-9)距离门: 330外只禁近战子集(弹幕/技能放行),
        150内禁弹幕。抽出为方法供行为测试钉住
        (变异面: near→melee=全攻击集 → 远程立回不可学)。"""
        if dx_abs > 330:
            mask = mask & ~self.near_idx
        elif dx_abs < 150:
            mask = mask & ~self.bullet_idx
        return mask

    def _setup_capture(self):
        """虚拟视觉(2026-09-22重审): 屏幕捕获废弃 — TM包含全部弹幕对象
        的精确坐标, 渲染成3×60×80网格喂同一卷积主干。
        收益: 无遮挡/无DXGI/无窗口管理/解锁高tps无头。"""
        pass

    def _render_frame(self, left, right, objs):
        """包→80×60战场网格(uint8): 自255 对手180 弹幕按类型96/128。
        世界: x 0..1280, y 地面0向上为正(hud_sensor同源实测)。"""
        img = np.zeros((60, 80), dtype=np.uint8)
        cx = int(np.clip(left["position.x"] / 16.0, 0, 79))
        cy = int(np.clip((600.0 - left["position.y"]) / 16.0, 0, 59))
        img[cy, cx] = 255
        ox = int(np.clip(right["position.x"] / 16.0, 0, 79))
        oy = int(np.clip((600.0 - right["position.y"]) / 16.0, 0, 59))
        img[oy, ox] = 180
        for o in objs[:48]:
            bx = int(np.clip(o[1] / 16.0, 0, 79))
            by = int(np.clip((600.0 - o[2]) / 16.0, 0, 59))
            # imageID低位区分弹种灰度, 弹幕保留可辨识梯度
            v = 96 + (o[6] & 0x3F)
            if img[by, bx] < 90:      # 不覆盖角色标记
                img[by, bx] = v
        return img

    def _push_frame(self, left, right, objs):
        """逐帧追加(连续帧), 保留5帧用于构造运动感知栈.
        决策时取最近3帧, 构造[当前帧, 当前-1差分, 当前-2差分].
        差分通道直接编码实体运动速度和方向 — conv无需自行学习."""
        img = self._render_frame(left, right, objs)
        self.feat_hist.append(img.ravel())
        if len(self.feat_hist) > 5:
            self.feat_hist.pop(0)

    def _visual_feat(self, left, right, objs):
        """运动感知栈: [当前帧, Δ1, Δ2] 3通道×60×80=14400维.
        Δ1 = 当前帧 - 前一帧 (实体运动速度)
        Δ2 = 前一帧 - 前前帧 (运动加速度/方向变化)
        模型尺寸与旧3帧栈完全兼容(conv输入仍3通道)."""
        if len(self.feat_hist) < 3:
            return None
        f0, f1, f2 = self.feat_hist[-3], self.feat_hist[-2], self.feat_hist[-1]
        d1 = np.clip(f2.astype(np.int16) - f1.astype(np.int16),
                     0, 255).astype(np.uint8)
        d2 = np.clip(f1.astype(np.int16) - f0.astype(np.int16),
                     0, 255).astype(np.uint8)
        return np.concatenate([f2, d1, d2])

    def _sc_cost(self, cid):
        """用一张卡的耗费(技能卡1xx只耗1, 其余查角色表)"""
        if 100 <= cid < 200:
            return 1
        return self.sc_cost_table.get(cid, 1)

    @staticmethod
    def _parse_hand(left):
        """TM包手牌10字节 → (ids列表, 选中id, 数量). 0xFF=空位, hand[0]=选中."""
        hb = left["hand"]
        ids = [hb[i * 2] for i in range(5) if hb[i * 2] != 0xFF]
        sel = hb[0] if hb[0] != 0xFF else None
        return ids, sel, len(ids)

    def _sc_usable_mask(self, left):
        """决策门控: 目标卡在手 且 手牌数≥耗费(与v2 pmask同源)."""
        m = np.zeros(self.n_macros, dtype=bool)
        ids, sel, size = self._parse_hand(left)
        if not ids:
            return m
        for name, tgt in self.sc_targets.items():
            idx = self._sc_name_idx.get(name)
            if idx is None:
                continue
            use = tgt if tgt >= 0 else sel
            if use is not None and use in ids and size >= self._sc_cost(use):
                m[idx] = True
        return m

    def _sc_reset(self):
        self._sc_run = None
        self._sc_tgt = None
        self._sc_next_input = {}

    def _sc_step(self, left):
        """TM版符卡状态机(每逻辑帧, 包手牌驱动).
        返回(pop, abort, hold_input). 时序依据v2实测: SW按2帧换选, SC按3帧生效."""
        ids, sel, size = self._parse_hand(left)
        if self._sc_run is None:
            if not ids:
                return False, True, {}
            use = self._sc_tgt if self._sc_tgt >= 0 else sel
            if use is None or use not in ids or size < self._sc_cost(use):
                return False, True, {}
            self._sc_run = {"phase": "chk", "tries": 0, "hold": 0}
        if not ids:
            return False, True, {}
        run = self._sc_run
        ph = run["phase"]
        if ph == "chk":
            if self._sc_tgt < 0 or sel == self._sc_tgt:
                run["phase"], run["hold"] = "i_down", 0
                run["size_i"] = size
                return False, False, {}
            if run["tries"] >= size + 1:
                return False, True, {}
            run["phase"], run["hold"] = "u_down", 0
            return False, False, {}
        if ph == "u_down":
            run["hold"] += 1
            if run["hold"] >= 2:
                run["phase"], run["hold"] = "u_gap", 0
            return False, False, {"SW": True}
        if ph == "u_gap":
            run["hold"] += 1
            if run["hold"] >= 2:
                run["phase"], run["hold"] = "chk", 0
                run["tries"] += 1
            return False, False, {}
        if ph == "i_down":
            run["hold"] += 1
            if run["hold"] >= 3:
                run["phase"], run["hold"] = "ver", 0
            return False, False, {"SC": True}
        # ver: 留3帧结算, 手牌数下降=已消费
        run["hold"] += 1
        if run["hold"] >= 3:
            if size < run.get("size_i", 99):
                return True, False, {}
            run["iretry"] = run.get("iretry", 0) + 1
            if run["iretry"] > 1:
                return False, True, {}
            run["phase"], run["hold"] = "i_down", 0
        return False, False, {}

    def _build_side(self, left, right, weather, bullets):
        """v2全量侧特征(260维核心 + 2N宏one-hot): 威胁网格+未来占据+
        卡牌感知+对手建模+势函数+速度资源 — feat_builder.py驱动"""
        core = self.feat_builder.build(left, right, weather, bullets)
        # R14: 对手角色one-hot — R17: 段10对手建模27→75, 段11起点179→227
        # R60(F-8): 越界守卫改为合法槽校验(0/1/2+11-19; 3-10=技能特征块
        # 严禁one-hot[R19契约], 20/21=fvariant位, 22-27=扩展区[R61t])
        opp_id = getattr(self, '_opp_char_id', None)
        if opp_id is not None:
            if opp_id <= 19:
                # 前12角色: 段11合法槽(0-2+11-19)
                assert opp_id in (0, 1, 2) or 11 <= opp_id <= 19, \
                    "对手池序非法槽位: %r" % opp_id
                core[227 + opp_id] = 1.0
            else:
                # 后8角色: 扩展区(core[308+i], R61t F5)
                core[self._EXT_OPP_OFF + (opp_id - 20)] = 1.0
        # P0-2修复: turn_recency写入正确的core[33](feat_builder预留位)
        core[33] = min(self._dir_frames, 62) / 62.0   # 62fps教义: 1秒=62帧
        # 拼宏one-hot
        s = np.zeros(self.n_side, dtype=np.float32)
        s[:2 * self.n_macros] = 0.0
        s[self.last_macro] = 1.0
        s[self.n_macros + self.last_macro2] = 1.0
        s[2 * self.n_macros:2 * self.n_macros
          + self.feat_builder.CORE_DIMS] = core
        # R24/R25: 射程差特征块(二维) — clip((adx-reach_x_i)/200)与
        # clip((ady-reach_y_i)/200), 未解析宏=0。每个宏的logit可读自己
        # 的gap(经W_side近对角映射), 空挥惩罚提供梯度教它读。
        _adx = abs(right["position.x"] - left["position.x"])
        _ady = abs(right["position.y"] - left["position.y"])
        _b0 = 2 * self.n_macros + self.feat_builder.CORE_DIMS
        s[_b0:_b0 + self.n_macros] = \
            np.clip((_adx - self.macro_reach) / 200.0, -1, 1) \
            * self.reach_mask_idx
        s[_b0 + self.n_macros:_b0 + 2 * self.n_macros] = \
            np.clip((_ady - self.macro_reach_v) / 200.0, -1, 1) \
            * self.reach_v_mask_idx
        # R30: untech差值块 — (opp_untech - startup_i)/50, 正=来得及
        # (对手还在硬直), 负=来不及(目押窗口外)。模型借连段中优势梯度
        # 学读此特征=目押/放帧的感知基础。
        # BH-4.2: untech过动作门(残留读数污染目押判据)
        _opp_ut = eff_untech(right)
        s[_b0 + 2 * self.n_macros:] = \
            np.clip((_opp_ut - self.macro_startup) / 50.0, -1, 1) \
            * self.startup_mask_idx
        return s

    def _load_bc_bank(self):
        """神谕专家BC库: bc_io单源(trio mmap优先/npz回退, 2026-10-14
        用户裁定mmap方案 — 全量驻磁盘零采样损失)。
        S-6: I列(shard组id)并行加载 — 有则采样走连续窗口。"""
        from bc_io import find_bank, load_bank_seq
        kind, base = find_bank(self.char, self.suffix, store=STORE_DIR)
        if kind is not None:
            X, S, Y, I = load_bank_seq(self.char, self.suffix,
                                       store=STORE_DIR)
            self._bc_X, self._bc_S, self._bc_Y, self._bc_I = X, S, Y, I
            # R37(审查2026-10-02): 宽度守卫 — BC库停留旧布局时
            # 静默载入会导致update时广播爆炸(已烧一次前向)。
            assert S.shape[1] == self.n_side, \
                ("BC库宽度%d≠n_side%d — BC库与当前宏库/CORE_DIMS"
                 "不一致, 需重跑repad脚本" % (S.shape[1], self.n_side))
            # R39(第十轮P3-10): X宽校验 — 旧视觉布局(≠14400)的BC文件
            # 会"健康"载入后在每次update里_trunk reshape崩、被worker
            # except吞掉 → 零学习且无可见错误
            from ppo import CONV_H, CONV_W
            assert X.shape[1] == 3 * CONV_H * CONV_W, \
                ("BC库X宽%d≠视觉栈%d — 旧视觉布局, 需重建BC库"
                 % (X.shape[1], 3 * CONV_H * CONV_W))
            print("[BC] 专家库 %s(%s): %d行 (S宽%d✓)" % (
                os.path.basename(base), kind, len(Y), S.shape[1]))
            return
        self._bc_X = None
        self._bc_I = None
        print("[BC] 无专家库(神谕数据未提取或角色无对局) — 纯PPO模式")

    def _sample_bc(self, k=64):
        """marisa数据少(3.5K vs 9K+) → k加倍补偿."""
        if self.char == 'marisa':
            k = min(k * 2, 128)
        """每次更新混入k行专家数据(BC-extra: adv=0纯模仿梯度)。
        v2数据(2026-09-26): 决策点扫描+前缀匹配, 22372行, 技术动作39-50%。
        S-6: 有I列 → 同shard连续窗口(宁短勿跨 — 跨shard的连续是假
        序列; GRU锚与决策序列的时序结构从此进BC-extra)。
        LE-1b: env TH123_LE1B_RATIO>0时, 注入行从情境库热度加权
        选取(≤20%批占比上限, A/B专项; 默认0=关, 零行为影响)。"""
        X = getattr(self, '_bc_X', None)
        if X is None or len(X) == 0:
            return None
        # LE-1b: 高价值情境注入行
        _inj = None
        if os.environ.get('TH123_LE1B_RATIO', '0') != '0':
            try:
                _le1b_dir = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), 'tools')
                if _le1b_dir not in sys.path:
                    sys.path.insert(0, _le1b_dir)
                from le1b_inject import inject_count, inject_indices
                n_inj = inject_count(k)
                if n_inj > 0:
                    rng = getattr(self, '_bc_rng', None)
                    if rng is None:
                        rng = np.random.default_rng(4321)
                        self._bc_rng = rng
                    _inj = inject_indices(self.char, n_inj, rng)
            except Exception as _le:
                if not getattr(self, '_le1b_err_seen', False):
                    self._le1b_err_seen = True
                    print('[LE-1b] 注入异常(%r) — 回落纯窗口采样' % _le)
        I = getattr(self, '_bc_I', None)
        if I is not None:
            from bc_io import sample_seq_window
            rng = getattr(self, '_bc_rng', None)
            if rng is None:
                rng = np.random.default_rng(4321)
                self._bc_rng = rng
            _k_win = k - (len(_inj) if _inj is not None else 0)
            widx = sample_seq_window(I, min(_k_win, len(X)), rng)
            if widx is not None:
                if _inj is not None:
                    widx = np.concatenate([widx, _inj])
                return (X[widx], self._bc_S[widx], self._bc_Y[widx])
        idx = np.random.randint(0, len(X), size=min(k, len(X)))
        if _inj is not None:
            idx[:len(_inj)] = _inj
        return (X[idx], self._bc_S[idx], self._bc_Y[idx])

    def _make_env(self, port, lane=None):
        """按模式建环境: 对手模式=EvalEnv(VS_PLAYER+胜者记录), 否则VS_COM。
        2026-09-27: 混合池(含COM) — opp=None时切VS_COM。
        R19(审查-2026-10-02): lane=(lo,hi)显式车道。
        R47(可行性天花板2): deck采样 — 每次建env按课程比例采样P1侧卡组
        (技能+SC入池→激活等级特征/SC门控/等级条件宏)。"""
        from side_driver import EvalEnv
        from deck_sampler import sample_deck, curriculum_ratio
        # C: 对抗性卡组池(L1流派+L2必杀系别)
        from deck_sampler import sample_deck_weighted, skillset_key
        _ep = getattr(self, '_ep_count', 0)
        _ratio = curriculum_ratio(_ep)
        _my_deck = sample_deck(CHAR_LIBS[self.char]['id'],
                               self._deck_rng, _ratio)
        # C(用户"只做DCB"+L2必杀系别+L3 SC/系统卡细化): 对手卡组按
        # 流派败率+逐卡败率加权 — 弱流派/弱必杀/弱SC/弱系统卡自动高频
        if self.opp:
            _opp_deck, self._opp_deck_arch = sample_deck_weighted(
                CHAR_LIBS[self.opp.char]['id'],
                self._deck_rng,
                getattr(self, '_deck_arch_stats', None),
                skill_stats=getattr(self, '_opp_skill_stats', None),
                sc_stats=getattr(self, '_opp_sc_stats', None),
                sys_stats=getattr(self, '_opp_sys_stats', None))
            self._opp_skillset = skillset_key(_opp_deck)
            self._opp_deck_scids = tuple(sorted(
                {c for c in _opp_deck if c >= 200}))
            self._opp_deck_sysids = tuple(sorted(
                {c for c in _opp_deck if c < 100}))
        else:
            _opp_deck, self._opp_deck_arch = None, None
            self._opp_skillset = ()
            self._opp_deck_scids = ()
            self._opp_deck_sysids = ()
        if self.opp_cycle and self.opp is not None:
            env = EvalEnv(port, char_left=self.char,
                          char_right=self.opp.char, vs_com=False,
                          tps=self.tps, render=self.render, lane=lane,
                          deck_left=_my_deck, deck_right=_opp_deck)
        else:
            env = EvalEnv(port, char_left=self.char,
                          char_right=self.char, vs_com=True,
                          tps=self.tps, render=self.render,
                          com_difficulty=getattr(self, 'com_difficulty',
                                                 None), lane=lane,
                          deck_left=_my_deck, deck_right=_opp_deck)
        env.deck_left = _my_deck   # 双保险(续局/重建路径消费)
        env.deck_right = _opp_deck
        return env

    # R47(P0-3): 20角色池序映射 — 段11的[o..o+2]原3宽装不下。
    # 方案: 池序按训练实例实际对手池大小动态分配(3现役场景=原行为,
    # 扩容后按池内角色数)。段11的[o..o+N]契约由feat_builder按
    # _opp_pool_size扩展(o+3..o+N与技能等级块重叠部分暂置零 — 技能
    # 等级在230..233, one-hot在227..229, 扩展到227..246需feat_builder
    # 段宽调整, 这是CORE_DIMS变更需模型迁移, 留待GPU化一并做)。
    # R51(§C4修复): 新角色池序从11起 — 原3-10与段11技能特征块
    # [o+3..o+10]冲突(one-hot覆写技能等级/可用性)。
    # R60(F-8)修正版: R19注入契约(3-10=技能特征块, 严禁one-hot)与20角色
    # 唯一性在26维段11内**不可兼得**(合法槽{0,1,2}∪{11..19}=12个)。
    # 从零审计F-8的原修法(0-19)会覆写技能特征 — 采纳其实质(消灭溢出/
    # 复用), 摒弃其越界: 9个新角色入11-19唯一位; 其余8个(yukari/aya/
    # iku/sanae/cirno/meiling/utsuho/suwako)暂不注入(无池快照未参战,
    # 缺席优于碰撞) — 20角色全量one-hot待CORE_DIMS 316扩维(改进方案
    # §1.2既有规划)后补位。
    # R61t(F5): 20角色全唯一映射 — 前12走段11合法槽, 后8走扩展区
    # (CORE_DIMS 308→316, 尾部追加=零内部布局变化)
    _CHAR_POOL_IDX = {"reimu": 0, "marisa": 1, "suika": 2,
                      "sakuya": 11, "patchouli": 12, "yuyuko": 13,
                      "reisen": 14, "komachi": 15, "tenshi": 16,
                      "alice": 17, "youmu": 18, "remilia": 19,
                      # 扩展区(写core[308+i], F5新增)
                      "yukari": 20, "aya": 21, "iku": 22, "sanae": 23,
                      "cirno": 24, "meiling": 25, "utsuho": 26,
                      "suwako": 27}
    _EXT_OPP_OFF = 308   # R61t(F5): 扩展one-hot起始(core尾部)

    def _wire_opp_ids(self, opp_char):
        """R19/R47: 对手角色id接线(20角色全唯一映射).
        前12角色走段11合法槽(0/1/2+11-19); 后8角色走扩展区
        (core[308+i], R61t F5新增 — 尾部追加=现有布局零变化).
        R21: feat_builder._opp_char接角色名(opp_model查表用)。"""
        self._opp_char_id = self._CHAR_POOL_IDX.get(opp_char)
        self.feat_builder._opp_char = opp_char
        # P2修(审计2026-10-16): JZ-1冷却char_id双侧注入(帕秋莉专属覆盖)
        self.feat_builder._jz1_ids = (
            CHAR_LIBS[self.char]['id'],
            CHAR_LIBS[opp_char]['id'] if opp_char in CHAR_LIBS else 0)
        # K5(裁定五并入S-2): 池外位 — R61t扩展one-hot虽全覆盖20角色,
        # 但池外槽位训练中从未激活(权重冷); 紧凑位聚合"陌生对手"信号
        self.feat_builder.opp_outside_pool = (
            0.0 if opp_char in ('reimu', 'marisa', 'suika') else 1.0)
        if self.opp is not None:
            self.opp.opp_char_id = self._CHAR_POOL_IDX.get(self.char)
            self.opp.feat_builder._opp_char = self.char
            # P2修: 对手侧镜像(其feat_builder的my=对手机体, opp=我)
            self.opp.feat_builder._jz1_ids = (
                CHAR_LIBS[opp_char]['id'] if opp_char in CHAR_LIBS else 0,
                CHAR_LIBS[self.char]['id'])
            self.opp.feat_builder.opp_outside_pool = (
                0.0 if self.char in ('reimu', 'marisa', 'suika') else 1.0)

    def _resolve_pool(self, ch):
        """R43方案A: 角色对手的池路径动态解析。
        R48: League加权 — 原纯轮转指针改为胜率加权选择(强敌更多采样,
        已碾压对手降权; fictitious play标准形式, 可行性报告天花板5)。
        从零#2(fleet P2): 池根路径可注入(self._pool_root) — 原恒读生产
        POOL_DIR, fleet learner的池快照写FLEET_DIR/pool但actor读不到
        =league对手冻结在生产快照。actor模式注入fleet池根。"""
        from outer_loop import OpponentPool as _OP, POOL_DIR as _PD
        _root = getattr(self, '_pool_root', None) or _PD
        cands = _OP(root=_root).latest(ch, k=POOL_K)
        # 维度守卫: 滤掉陈旧宏数快照(fleet池混入旧试验残留的木桩根因)
        _n = len(CHAR_LIBS[ch]['macros'])
        cands = [c for c in cands if _pool_snapshot_ok(c, _n)]
        if not cands:
            return None
        # R48: League胜率加权(替代R43纯轮转)
        from league import pick_weighted
        pairs = [(ch, p) for p in cands]
        _c, _m = pick_weighted(pairs, self._opp_stats, self._deck_rng)
        if _m is not None:
            return _m
        # 兜底: 纯轮转(league模块异常时不阻塞)
        ri = self._pool_rot.get(ch, 0)
        self._pool_rot[ch] = ri + 1
        return cands[ri % len(cands)]

    def _snapshot_pool(self):
        """R43方案A: 本角色快照入池(先join更新线程, 保证盘上是最新完整
        保存; 先v后pi=配对提交标记, 同outer_loop约定)。只写自己角色目录
        (跨训练器零竞争), 滚动保留POOL_KEEP个。
        D4(2026-10-06): 写根可注入(self._pool_write_root) — 剥削者把
        exploit_前缀快照写进主策略的读池, 形成针对性对抗压力。"""
        _t = getattr(self, "_upd_thread", None)
        if _t is not None:
            _t.join()
            self._upd_thread = None
        import shutil as _sh
        from outer_loop import POOL_DIR
        _root = getattr(self, '_pool_write_root', None) or POOL_DIR
        ts = time.strftime("%Y%m%d_%H%M%S")
        if getattr(self, '_is_exploiter', False):
            ts = 'exploit_' + ts   # D4: 剥削者快照标记(stats可区分)
        d = os.path.join(_root, self.char)
        os.makedirs(d, exist_ok=True)
        _sh.copy2(self.v_path, os.path.join(d, ts + "_v.npz"))
        _sh.copy2(self.pi_path, os.path.join(d, ts + ".npz"))
        snaps = sorted(f for f in os.listdir(d)
                       if f.endswith(".npz") and not f.endswith("_v.npz")
                       # D4: 剥削者与主策略共享池目录 — 滚动保留按
                       # 前缀分流(exploit_只由剥削者清理, 互不误删)
                       and f.startswith("exploit_")
                       == bool(getattr(self, '_is_exploiter', False)))
        for f in snaps[:-POOL_KEEP]:
            for _f in (f, f[:-4] + "_v.npz"):
                try:
                    os.remove(os.path.join(d, _f))
                except OSError:
                    pass
        print("[pool] 快照 %s@%s 入池(滚动保留%d)" % (
            self.char, ts, POOL_KEEP))

    def _com_ladder(self):
        """R43方案B: COM难度阶梯 — 近COM_CLIMB_N局胜率≥50%升一级,
        近COM_FALL_N局<20%降一级(清空窗口重新积累)。难度变化在下一次
        环境重建时生效(_make_env按self.com_difficulty传递)。
        R61e(B6): 难度持久化(com_difficulty_{char}{suffix}.json原子写)
        — 原仅内存态, 重启回Easy反复爬梯(诊断多次标注"重启后COM读数
        不可比"的根因)。"难度爬升必回火1.8"旧制=2.31裁定熵监控替代。"""
        h = self._com_hist
        _names = ("Easy", "Normal", "Hard", "Lunatic")
        _old_d = self.com_difficulty
        if (len(h) >= COM_CLIMB_N
                and sum(h[-COM_CLIMB_N:]) / COM_CLIMB_N >= COM_CLIMB_WR
                and self.com_difficulty < 3):
            self.com_difficulty += 1
            self._com_hist = []
            print("[COM阶梯] 近%d局胜率%.0f%% ≥%.0f%% → 升至难度%d(%s)"
                  % (COM_CLIMB_N, 100.0 * COM_CLIMB_WR, 100.0 * COM_CLIMB_WR,
                     self.com_difficulty, _names[self.com_difficulty]))
        elif (len(h) >= COM_FALL_N
              and sum(h[-COM_FALL_N:]) / COM_FALL_N < COM_FALL_WR
              and self.com_difficulty > 0):
            self.com_difficulty -= 1
            self._com_hist = []
            print("[COM阶梯] 近%d局胜率%.0f%% <%.0f%% → 降至难度%d(%s)"
                  % (COM_FALL_N, COM_FALL_WR * 100, 100.0 * COM_FALL_WR,
                     self.com_difficulty, _names[self.com_difficulty]))
        if self.com_difficulty != _old_d:
            import json as _json
            _p = getattr(self, '_com_diff_path', None) or os.path.join(
                STORE_DIR,
                "com_difficulty_%s%s.json" % (self.char, self.suffix))
            _t = _p + ".tmp"
            with open(_t, "w", encoding="utf8") as _f:
                _f.write(_json.dumps(
                    {"difficulty": int(self.com_difficulty),
                     "ts": time.strftime("%Y%m%d_%H%M%S")}))
            os.replace(_t, _p)

    def _opp_label(self):
        c, _m = self.opp_cycle[self._opp_i]
        if c == "COM":
            return "COM"
        m = self._cur_opp_model or _m
        if m is None:
            return c
        return "%s@%s" % (c, os.path.splitext(os.path.basename(m))[0])

    def _settle_match(self):
        """局结束结算胜率(env.last_match → 统计)。"""
        lm = getattr(self.env, "last_match", None)
        if not lm:
            return
        self.env.last_match = None
        _w, ls, rs = lm
        self._last_match_win = ls > rs   # E阶段1: 系列计分源
        lab = self._opp_label() if self.opp_cycle else "COM"
        st = self._opp_stats.setdefault(lab, [0, 0])
        if ls > rs:
            st[0] += 1
        elif rs > ls:
            st[1] += 1
        # C(用户"只做DCB"): 对手卡组流派战绩归桶 —
        # 对抗性卡组池的输入(败率高的流派下一批被加权采样)
        _arch = getattr(self, '_opp_deck_arch', None)
        if _arch is not None:
            ds = self._deck_arch_stats.setdefault(_arch, [0, 0])
            if ls > rs:
                ds[0] += 1
            elif rs > ls:
                ds[1] += 1
            dn = ds[0] + ds[1]
            if dn % 10 == 0:
                print("[流派战绩] vs %s流: %dW-%dL (%.0f%%)"
                      % (_arch, ds[0], ds[1], 100.0 * ds[0] / dn))
        # C-L2(必杀系别层): 对手装备的每个技能卡各记一票 —
        # 逐卡败率驱动下批skill/mixed卡组的技能选择加权
        _sset = getattr(self, '_opp_skillset', None)
        if _sset:
            for sid in _sset:
                ss = self._opp_skill_stats.setdefault(sid, [0, 0])
                if ls > rs:
                    ss[0] += 1
                elif rs > ls:
                    ss[1] += 1
        # C-L3(SC/系统卡细化, 用户2026-10-07): 对手卡组内逐SC/逐系统卡
        # 各记一票 — 弱SC/弱系统卡在sc/mixed与填充位被加权
        _arch = _arch or getattr(self, '_opp_deck_arch', None)
        if _arch is not None and _arch != 'system':
            _deck_sc = getattr(self, '_opp_deck_scids', None)
            if _deck_sc:
                for cid in _deck_sc:
                    cs = self._opp_sc_stats.setdefault(cid, [0, 0])
                    if ls > rs:
                        cs[0] += 1
                    elif rs > ls:
                        cs[1] += 1
            _deck_sys = getattr(self, '_opp_deck_sysids', None)
            if _deck_sys:
                for cid in _deck_sys:
                    ys = self._opp_sys_stats.setdefault(cid, [0, 0])
                    if ls > rs:
                        ys[0] += 1
                    elif rs > ls:
                        ys[1] += 1
        n = st[0] + st[1]
        if lab == "COM" and self.opp_cycle:
            self._com_hist.append(1 if ls > rs else 0)
            self._com_ladder()
        # R47(可行性天花板6): 回报-胜率相关性仪表 — suika曾输COM局
        # 赚+11.7(擦弹盖过KO), 相关性跌破0.3即报警(奖励经济学失衡)
        self._ret_win_hist.append((ls > rs, getattr(self, '_last_ret',
                                                    0.0)))
        if len(self._ret_win_hist) >= 50:
            wins = np.array([w for w, _ in self._ret_win_hist[-50:]])
            rets = np.array([r for _, r in self._ret_win_hist[-50:]])
            if rets.std() > 1e-6:
                corr = float(np.corrcoef(wins, rets)[0, 1])
                if corr < 0.3:
                    print("[警报] 回报-胜率相关性%.2f < 0.3 — 奖励经济学"
                          "失衡(微收入碾压结果信号)!" % corr)
                elif (st[0] + st[1]) % 50 == 0:
                    print("[仪表] 回报-胜率相关性%.2f(50局窗口)" % corr)
        if n % 5 == 0 or n <= 3:
            print("[matchup] vs %s: %dW-%dL (%.0f%%)"
                  % (lab, st[0], st[1], 100.0 * st[0] / n))

    def _remake_env(self):
        """R39(第十轮P2-4): _rotate_opp的环境重建原丢lane参数 — 异常重建后
        base_port是rebuild车道**中段口**, 无lane时tm_env行走(p,p+9)越入
        相邻slot的12宽车道(僵尸口探测使其成为响亮失败, 代价=丢局churn)。
        主车道base=车道起点, 保持原生无lane行为。
        从零#2(fleet P2): fleet段口同样入lane — 原只认train_rebuild段,
        fleet actor的重建(rebuild_port补丁返回车道内ep偏移口)拿不到lane
        →行走(p,p+9)越入相邻actor车道。actor_worker已补丁rebuild_lane
        返回fleet车道, 此处放行fleet段即可。
        _next_port死代码已删(TMEnv:176恒定义base_port)。"""
        from portmap import SEGMENTS, rebuild_lane
        p = self.env.base_port
        lo, hi = SEGMENTS["train_rebuild"]
        flo, fhi = SEGMENTS["fleet"]
        lane = (rebuild_lane(self.slot)
                if (lo <= p <= hi or flo <= p <= fhi) else None)
        return self._make_env(p, lane=lane)

    def _rotate_opp(self, ep):
        """每5局轮换对手池下一条(跨角色需重建环境)。
        2026-09-27: "COM"条目=切VS_COM模式(游戏COM驱动P2, 无SideDriver)。
        E阶段1(系列方案§3.1): 系列模式下轮换发令人=SeriesManager —
        系列内(未到8胜未满15场)抑制轮换(同对手连打, 画像跨场携带)。"""
        if not self.opp_cycle or len(self.opp_cycle) < 2:
            return
        if self._series_mgr is not None:
            if self._series_mgr.in_series:
                return          # 系列内: 同对手继续
            # 系列刚结束/新系列: 正常轮换下一条(下方逻辑照走)
        if (ep + 1) % 5:
            return
        old = self._opp_label()
        self._opp_i = (self._opp_i + 1) % len(self.opp_cycle)
        c, m = self.opp_cycle[self._opp_i]
        if c == "COM":
            # COM模式: 重建环境为VS_COM, 对手=None(COM自走)
            # R16关键修复: opp必须先置None — _make_env按"opp是否为None"
            # 选VS_COM/VS_PLAYER分支。原顺序(先建env后置None)误建VS_PLAYER
            # +无输入P2=打木桩: 09-27以来全部"vs COM"训练局都是假COM
            # (实测: 训练内"COM"4-1 vs 真COM评估0-3的矛盾根源)
            self.opp = None
            # R19(审查2026-10-02): 池序0/1/2 — 原suika=9写core[236]覆盖
            # 段11技能可用性块; 且初始对手从未注入。契约: 只允许[o..o+2]
            self._opp_char_id = None
            # R21: COM=己方角色镜像 → 对手模型查同名角色表
            self.feat_builder._opp_char = self.char
            try:
                self.env.close()
            except Exception:
                pass
            self.env = self._remake_env()
            print("[opp] 轮换 %s → COM(VS_COM模式)" % old)
        else:
            # R43方案A: 池路径动态解析 — 原启动时冻结, 新快照永不可见
            if m is None:
                m = self._resolve_pool(c)
                if m is None:
                    print("[opp] 池无%s快照 — 跳过该轮换" % c)
                    return
            self._cur_opp_model = m
            if self.opp is None or c != self.opp.char:
                try:
                    self.env.close()
                except Exception:
                    pass
                from side_driver import SideDriver
                self.opp = SideDriver(c, "R")
                self.env = self._remake_env()
            self._wire_opp_ids(c)
            self.opp.load(m)
            print("[opp] 轮换 %s → %s" % (old, self._opp_label()))

    def train(self):
        ep = 0
        _consec_fail = 0   # R19: 连续无决策局计数(重建失败后每局都抛
                           # → 循环自然结束且exit 0, 监督器误判"正常完成")
        while ep < self.episodes:
            try:
                _ok = self._run_episode()
                _consec_fail = 0 if _ok else _consec_fail + 1
                self._ep_count += 1   # R47: deck课程进度
                self._settle_match()
                # E阶段1: 场结束喂系列管理器(计分; legacy跳过)
                if self._series_mgr is not None:
                    self._series_mgr.on_match_end(
                        self._last_match_win if hasattr(
                            self, '_last_match_win') else False)
                self._rotate_opp(ep)
                # R43方案A: 每50局本角色快照入池(对手动态解析自动可见)
                if self.opp_cycle and (ep + 1) % POOL_SNAPSHOT_EVERY == 0:
                    self._snapshot_pool()
                if (ep + 1) % 10 == 0:
                    self.audit_tree()   # 定期基准树诊断(每10局)
                    # R58-S1(改进方案2.2): 采纳仪表 — 零计数宏与原子宏最低
                    # 计数进[ep]周期行(排查结论: 原子宏0%是体检时的过期
                    # 发现, R50配额扩展后1013~6775; 真实零采纳=部分SC卡宏)
                    _zero = [self.macros[i][0]
                             for i in range(self.n_macros)
                             if self.macro_counts[i] == 0]
                    _atm = [int(self.macro_counts[i])
                            for i in range(self.n_macros)
                            if self.macros[i][0].startswith('原子')]
                    print("[宏采纳] 零计数%d(%s) 原子min%d" % (
                        len(_zero), ','.join(_zero[:6]) or '-',
                        min(_atm) if _atm else -1))
                # R17(D3D根因修复后移除): 原R16"每局回收env制造窗口"
                # 是降级绕行 — SokuDirectXOptimizations已修复多实例boot,
                # env跨局存活走_restart_same_process自动续局(快+省boot)
            except TypeError as e:
                import traceback
                print("[ep] TypeError: %s" % e)
                traceback.print_exc()
                print("--- 重建环境 ---")
                try:
                    self.env.close()
                except Exception:
                    pass
                import time as _t
                from portmap import rebuild_port, rebuild_lane
                _t.sleep(1.0)
                self.env = self._make_env(rebuild_port(self.slot, ep),
                                          lane=rebuild_lane(self.slot))
                # R39(第十轮P2-5): 原不递增 — 持续TypeError零学习烧完全部
                # 局数且exit 0 → 监督器记"正常完成"不重启(R19盲区的回归)
                _consec_fail += 1
            except Exception as e:
                # 诊断升级(2026-10-15晨): 首次异常打完整栈(原仅一行消息
                # — AttributeError None.T排查数轮无栈可看); 后续静默防刷屏
                _consec_fail2 = getattr(self, '_ep_exc_logged', False)
                if not _consec_fail2:
                    import traceback
                    traceback.print_exc()
                    self._ep_exc_logged = True
                print("[ep] 异常: %s: %s — 重建环境" % (type(e).__name__, e))
                try:
                    self.env.close()
                except Exception:
                    pass
                import time as _t
                from portmap import rebuild_port, rebuild_lane
                # 重建本身也要保护(游戏启动失败曾穿透杀死训练器 — 实测suika死因)
                for _rb in range(5):
                    _t.sleep(1.0)
                    try:
                        self.env = self._make_env(rebuild_port(self.slot, ep),
                                                  lane=rebuild_lane(self.slot))
                        break
                    except Exception as e2:
                        print("[ep] 重建失败#%d: %s" % (_rb, e2))
                        try:
                            self.env.close()
                        except Exception:
                            pass
                else:
                    print("[ep] 重建5次耗尽 — 继续重试下一局")
                _consec_fail += 1
            if _consec_fail >= 5:
                # R19(审查2026-10-02): 原版此处每局抛异常→循环自然耗尽
                # → exit 0 → 监督器记"正常完成"永不重启。改显式退出码1。
                print("[train] 连续%d局无有效对局 — 环境系统性故障, 退出(码1)"
                      % _consec_fail)
                try:
                    self.env.close()
                except Exception:
                    pass
                raise SystemExit(1)
            ep += 1
        self.env.close()

    def _run_episode(self):
        """一局(match) = episode。锁步: 每env.step一逻辑帧。
        返回bool=本局是否有决策(R19: train()连续失败检测的数据源)。"""
        frozen = False   # R52: 帧级事件需此值, 首帧前初始化(防爆)
        self._setup_capture()   # 按局重启换PID → 重建捕获
        macro_queue = []       # [(keys, frames_left)]
        feats, sides, acts, rews, masks_hist, bc_targets = [], [], [], [], [], []
        ep_logps = []       # R60(F-11): 采样时行为策略logP(a)(本地路径;
                            # fleet actor走_fleet_logp_rec闭包, 此表留空)
        opp_acts = []          # R17④: 每决策拍对手动作类(action//128) —
                               # 下一拍作辅助预测标签(末拍-1)
        # R16: 奖励槽在决策点append(0.0), 区间奖励经rews[-1]+=记给上一动作
        # E阶段1: 系列模式下画像仅系列首场重置(跨场携带对手画像=适应基础);
        # legacy(无series_mgr)逐位不变
        if self._series_mgr is None or self._series_mgr.should_reset_profiles():
            self.feat_builder.reset_match()   # 对手模型/弹速缓存/擦弹计数重置
            # S-4阶段1(2026-10-15): GRU隐状态随局reset(系列内跨场=阶段2)
            self._gru_h = None
        self._guard_frames_ep = 0         # R33: 防御递减计数(每局重置)
        self._cur_bullets = []
        distill_rows = []      # [dx, spirit, close, macro_id, game_frame,
                               #  dy, opp_air, bullet_near, we_left, tti, opp_corner]
        prev_near_d = None     # 上一帧最近弹距(TTI估计用)
        seg_rew = 0.0
        hp_l_prev, hp_r_prev = 10000, 10000
        score_l_prev, score_r_prev = 0, 0   # 回合胜场(包字段, KO奖励接线用)
        round_f0 = 0                         # R61: 本回合起始帧(快胜奖金计时)
        micro_bank = 0.0                     # R62: 本回合微收入累计(胜负挂钩用)
        self._seiran_gauge = None            # R61c(B5): 晴岚gauge冻结值
        self._last_gauge = 0                 # R61c: 进入晴岚前的真实gauge
        self._frame_event_mask = None        # R61l(B2): 事件反应掩码
        self._ender_mask = None              # R61w(C5): ender菜单掩码
        self._in_frame_reaction = False      # R61l: 事件反应模式标记
        self._frame_ev_count = 0            # R61l: 帧级事件触发计数
        self.frame_event_count = 0          # R61l: 日志计数
        self._air_passive_f = 0             # R61z: 空中被动帧计数
        gate_frames = 0        # confirm门观察窗状态(hitstop晚结算容忍)
        # P2-1修复: 空挥判定状态(决策→决策窗口内的伤害/对手防御)
        dec_name, dec_dmg, dec_guarded = None, 0.0, False
        dec_spirit = None   # R17: 起手时灵力(空挥加重判据)
        # BH-1(行为健康方案v4): 行为计数器(每局新建; actor的submit钩子
        # 在episode落盘后flush旁车json — 不动episode npz契约)
        from behavior_health import BehaviorCounter as _BHC
        self.bh = _BHC(self.char)
        # CE-0.1: 帧日志抽样(TH123_FRAME_LOG=1开启, 默认关)
        # — BH-1表6-8数据源, ~250-400KB/抽样局
        # R151: 计数改**时间基准**(距该角色上次抽样>INTERVAL秒) —
        # 原进程内局计数在fleet重启后清零, 每次重启都要重攒50局,
        # 反复重启把抽样吃掉(实测仅1份). 时间基准对重启鲁棒.
        from behavior_health import (frame_log_enabled as _fle,
                                     frame_log_interval as _fliv,
                                     FL_FIELDS)
        self._bh_ep_n = getattr(self, '_bh_ep_n', 0) + 1
        _fl_on = False
        if _fle():
            # P1-5(从零#5): 按**角色子目录**隔离 — 原落盘在共享 frame_logs/,
            # 修剪用 glob('fl_*.pkl') 只留500 → 三角色互删对方日志(实测
            # 目录 23 文件三色交错, .last_<char> 门闸也共用一把)
            _mark = os.path.join(STORE_DIR, 'frame_logs', self.char,
                                 '.last_%s' % self.char)
            try:
                _last = os.path.getmtime(_mark)
            except OSError:
                _last = 0.0
            if time.time() - _last > _fliv():
                _fl_on = True
                os.makedirs(os.path.dirname(_mark), exist_ok=True)
                io_open = open(_mark, 'w')
                io_open.close()
        self._fl_frames = [] if _fl_on else None
        self._fl_decisions = [] if _fl_on else None
        # P1-4b修复(真): 对手水平速度=包位置逐帧差分EMA(包无vx字段,
        # archive版的R["vx"]来自抓屏管线, 本通道须自差分)
        opp_x_prev, opp_vx_ema = None, 0.0
        frames = 0
        # R17仪表: 每局奖励成分(决策依据 — 此前盲调, P0-K教训)
        # R39(P3-8): guard/wall/spirit通道R35已删, 死键移除(恒零=读死表)
        rew_mix = {"dmg": 0.0, "taken": 0.0, "ko": 0.0, "graze": 0.0,
                   "evade": 0.0, "whiff": 0.0, "micro_tax": 0.0}
        # R63(P1-1): micro_tax键入表(原只get到不初始化) — 败回合微收追扣
        # 原来**不在**mix里, 于是打印的"总和"既漏了扣分项、又把不参与
        # 目标函数的dmg/taken算进去 → 调参依据与实际回报不同源。
        graze_frames = 0     # R17: 擦弹帧计数(测真实擦弹需求量)
        t0 = time.time()
        self.feat_hist = []    # 跨局栈污染修复(5帧用于差分)(上局尾帧不进新局首决策)
        # R39(第十轮P2-7): 上局sc状态机残留带入新局 — 新sc:步不重解析目标
        # (仅None时设置), 可在开局乱按SW/SC误烧卡; last_macro同复位
        # (side_driver.reset_match同款语义, 消除首决策one-hot史污染)
        self._sc_reset()
        self.last_macro, self.last_macro2 = 0, 0
        # R49: 帧级事件检测器(每局重置)
        self._frame_detector = FrameEventDetector()
        if not hasattr(self, 'frame_event_count'):
            self.frame_event_count = 0
        # 外环训练半环: 对手侧状态(P2只读驱动, 上帧状态算本帧输入=与P1同拍)
        self._opp_inp = {}
        if self.opp is not None:
            if self._series_mgr is None                     or self._series_mgr.should_reset_profiles():
                self.opp.reset_match()
        # P0-6修复: 采样前刷新快照(原在_submit_update入口, 行为策略滞后1-2拍)
        # R60(F-1): 原刷新被_upd_thread门控 — actor模式替换了_submit_update
        # 不再有更新线程 → 门永不开 → _ppo_act冻结在启动权重(快照死链,
        # meta谎报snap_ver)。fleet钩子在位时(actor)同样每局刷新。
        import copy as _copy
        _t = getattr(self, "_upd_thread", None)
        if _t is not None:
            _t.join()
            self._upd_thread = None
            self._ppo_act = _copy.deepcopy(self.ppo)
        elif getattr(self, "_fleet_logp_rec", None) is not None:
            self._ppo_act = _copy.deepcopy(self.ppo)

        while time.time() - t0 < self.ep_timeout:
            # ---- 当前输入(宏队列头; sc步由状态机供键; 门步保持上一拍键) ----
            if macro_queue:
                keys, fl = macro_queue[0]
                if isinstance(keys, str) and keys.startswith("sc:"):
                    inp = dict(self._sc_next_input)
                elif isinstance(keys, str):
                    # P2-7修复: 确认门保持上一拍输入(原版keys_to_input("confirm")={})
                    inp = dict(inp) if isinstance(inp, dict) else {}
                else:
                    inp = keys_to_input(keys, self._last_dir < 0)
            else:
                inp = {}

            r = self.env.step(inp, self._opp_inp)
            if r is None:
                break    # 局终止(env已重启) — episode边界
            left, right, weather, objs = r
            frames += 1

            # CE-0.1(BH-1): 抽样局逐帧记录(12字段/侧+objs前20个原始元组)
            if self._fl_frames is not None:
                self._fl_frames.append((
                    tuple(left.get(_fk, 0) for _fk in FL_FIELDS),
                    tuple(right.get(_fk, 0) for _fk in FL_FIELDS),
                    tuple(tuple(o[:17]) for o in objs[:20]),
                    int(left.get('frameCount', 0) or 0)))


            # ---- 对手侧驱动(P2快照模型; VS_COM模式下_opp_inp恒空不干扰COM) ----
            if self.opp is not None:
                _ob = self.opp.feat_builder.track_bullets(objs)
                self._opp_inp = self.opp.frame_input(right, left, weather,
                                                     objs, _ob)

            # ---- 朝向跟踪(转向延迟感知) ----
            d_now = 1 if left["direction"] > 0 else -1
            if d_now != self._last_dir:
                self._dir_frames = 0
                self._last_dir = d_now
            else:
                self._dir_frames += 1
            back_turned = (d_now > 0) != (right["position.x"] > left["position.x"])

            # ---- R49: 帧级事件检测与反应(L3时序墙) ----
            # R51(§F3修复): 反应动作为**守式模式** — 不入训练轨迹。
            # R52: frozen须在此前定义(原在宏队列推进段=帧级事件之后,
            # UnboundLocalError炸局)
            frozen = (left["hitStop"] > 0) or (left["timeStop"] > 0)
            _fev, _fwin = self._frame_detector.detect(left, right, frozen)
            # JZ-3.2: 投技无敌窗逐帧跟踪(与事件检测器同拍)
            self._throw_invuln_trk.feed(right, frozen)
            if _fev != _FE_NONE and macro_queue:
                # R61l(B2): 事件→策略条件化 — 原pick_reaction固定权重
                # 随机选择, 改为清空队列+设置反应掩码, 让策略在下一
                # 决策点从事件约束的选项中**自主选择**(学习化, 入轨迹
                # →获信用/担责). 策略学会"被防时做什么"而非规则随机.
                _rmask = frame_events.reaction_mask(
                    _fev, left, right,
                    CHAR_LIBS[self.char]['names'],
                    self.base_mask)
                if _rmask is not None:
                    macro_queue = []
                    gate_frames = 0
                    dec_name = None   # 从零#2(执行器P2): 清队不清名=
                    # 误记空挥(下决策窗把被打断的宏记作空挥扣分)
                    self._sc_reset()
                    self._frame_event_mask = _rmask
                    self._in_frame_reaction = True
                    # J(未决方案§J裁定): _fwin显式消费入日志 — 反应采B2
                    # 即时掩码语义, 延迟执行路线被取代; 事件窗作元数据可见
                    print("[帧级事件] %s→策略决策(掩码%d,窗%d) (第%d次)" % (
                        _FRAME_EV_NAMES.get(_fev, _fev),
                        int(_rmask.sum()),
                        int(_fwin),
                        self._frame_ev_count))
                    self._frame_ev_count = (getattr(
                        self, '_frame_ev_count', 0) + 1)
                    self.frame_event_count += 1
                    if self.frame_event_count % 20 == 1:
                        print("[帧级事件] %s→策略决策 (第%d次)"
                              % (frame_events.EV_NAMES.get(_fev, '?'),
                                 self.frame_event_count))
                # R61l(B2): 反应模式在决策完成后自动清除(见决策点)

                        # ---- 逐帧视觉栈(架构审查C: 连续帧=运动感知) ----
            self._push_frame(left, right, objs)

            # ---- 对手速度差分(P1-4b真接线的数据源) ----
            if opp_x_prev is not None:
                opp_vx_ema = 0.9 * opp_vx_ema + 0.1 * (right["position.x"] - opp_x_prev)
            opp_x_prev = right["position.x"]

            # ---- 弹速追踪(v2威胁/未来占据数据源) ----
            # R19(审查2026-10-02): 原在奖励段之后更新 → check_graze用的
            # 是上一帧弹表(决策拍本来就滞后, 帧内不该再滞后一帧)
            # own=left: R16§0.1生产计数(未匹配率+零速入盒频率)
            self._cur_bullets = self.feat_builder.track_bullets(objs, own=left)

            # ---- 奖励(帧级) ----
            # R35: 势函数塑形(差距#5) — 核心变化:
            #   旧: 动作奖励(选立防+0.06/帧) → 可刷(站防刷分)
            #   新: 状态势差(HP/灵力/位置的差分) → 不可刷(停着=差分0)
            # 事件奖励(KO/擦弹/空挥)保留 — 它们是离散事件, 不适合势函数
            # R61c(B5, 主规划B5): ①γ因子 — 理论式r'=γΦ(s')−Φ(s), 原γ=1
            #   纯telescoping虽也策略不变, 但γ<1给"驻高势态"微负漂移
            #   (与fleet episode_core旧骨架的0.999对齐, 消双实现漂移);
            # ②晴岚哨兵 — 晴岚(11)期卡牌遮蔽, gauge读数不可信(伪势跳
            #   ±2.0, 从零审计P2): 进入时冻结前值(入晴岚无跳变/期间
            #   恒定/退出回真值)
            _cg = left.get("cardGauge", 0)
            _seiran = (weather.get("active") == 11
                       or weather.get("displayed") == 11)
            if _seiran:
                if self._seiran_gauge is None:
                    self._seiran_gauge = self._last_gauge
                _cg = self._seiran_gauge
            else:
                self._seiran_gauge = None
            self._last_gauge = left.get("cardGauge", 0)
            _pot = state_potential(left, right, card_gauge_val=_cg)
            seg_rew += (GAMMA_POT * _pot - self._prev_pot
                        if hasattr(self, '_prev_pot') else 0.0)
            self._prev_pot = _pot
            d_deal = max(0, hp_r_prev - right["hp"])
            d_take = max(0, hp_l_prev - left["hp"])
            # S-1接线(2026-10-14): 宏执行中的punish证据逐帧入账
            # (对手攻击态=300-598; blocked=我方入GUARD_STUN族)
            self.feat_builder.punish.frame(
                d_take, 300 <= right.get("action", 0) <= 598,
                d_deal, 150 <= left.get("action", 0) <= 166
                and left.get("action", 0) != 158)
            hp_l_prev, hp_r_prev = left["hp"], right["hp"]
            dx_guard = right["position.x"] - left["position.x"]
            # P2-1修复: 空挥窗口累计(伤害入账 + 对手是否在防)
            dec_dmg += d_deal
            # R17③修正: 传对手untech(超长连段判定—收招帧不断链)
            # BH-4.2: 过动作门(对手自由行动时残留untech不再维持链)
            self.feat_builder.update_combo_chain(d_deal,
                                                 eff_untech(right))
            # R20: 对手在防=实测ID集(原110-115恒不命中 → 被防的压制
            # 被误判空挥扣分)
            if right["action"] in GUARD_ALL_IDS:
                dec_guarded = True
            # R35: 伤害/承伤/墙/灵力/位置已由势函数差分覆盖(见_pot)
            # 事件奖励(KO/擦弹/空挥)保留 — 离散事件不适合势函数
            # 回合胜负(惨胜变亏: ×(0.3+自身血量/10000) — v2 KO加权)
            d_sl = left["score"] - score_l_prev
            d_sr = right["score"] - score_r_prev
            score_l_prev, score_r_prev = left["score"], right["score"]
            if d_sl > 0:
                # R61: 快胜奖金(用户裁定"鼓励快速胜利") — 剩余时间比例,
                # 速决回合最高+6/回合, 拖满时长胜+0
                # R61b: KO胜按双方血量差分档(原只看自身血量)
                _fw = fastwin_bonus(frames - round_f0, d_sl)
                _ko = ko_round_reward(left["hp"], right["hp"],
                                      True) * d_sl + _fw
                _tax = micro_tax(micro_bank, True)
                seg_rew += _ko - _tax
                rew_mix["ko"] += _ko
                rew_mix["micro_tax"] = rew_mix.get("micro_tax", 0.0) - _tax
            if d_sr > 0:
                # R61b: 败局按血量差分档(原恒-10: 惜败与被碾压同罚)
                _ko = ko_round_reward(left["hp"], right["hp"],
                                      False) * d_sr
                # R62(用户2026-10-06"把胜负和回报挂钩"): 败回合微收入
                # 追扣 — 拖时间擦弹不再碾压结果信号(相关性-0.5~-0.68)
                _tax = micro_tax(micro_bank, False)
                seg_rew += _ko - _tax
                rew_mix["ko"] += _ko
                rew_mix["micro_tax"] = rew_mix.get("micro_tax", 0.0) - _tax
            if d_sl > 0 or d_sr > 0:
                round_f0 = frames   # R61: 回合边界(快胜计时重置)
                micro_bank = 0.0    # R62: 微收入银行随回合重置
            # R35: 保留伤害/承伤在rew_mix中用于诊断(但不再加到seg_rew
            # — 势函数已覆盖: HP变化自动反映在_pot差分中)
            rew_mix["dmg"] += d_deal * R_DMG
            rew_mix["taken"] += d_take * R_TAKEN
            # (R17 per-round切片已撤回 — 用户2026-09-30: 技能卡跨round
            #  升级使round间有战略依赖, 应保持整场match轨迹+提升γ视界)

            # ---- v2微奖励回迁(正向定律) ----
            # 擦弹: 弹幕近身+零承伤
            # R17两级费率(用户2026-09-29: 高手作战大量擦弹, 硬顶惩罚擦弹
            # 大师): 全额到GRAZE_FULL_CAP, 之后低费率 — 无悬崖,
            # 密集擦弹持续有收入, 但超额段费率碾压不了胜负经济学
            # R61-d(用户2026-10-05): 低段费率随局内已用帧衰减(graze_low_rate)
            # — 0.01恒定线性段在10408帧局收+122, 拖时间成了收割手段;
            # 衰减后低段硬上界≈30, 正常局前中期收入不变。
            if self.feat_builder.check_graze(left, self._cur_bullets, d_take):
                _g_rate = (R_GRAZE if rew_mix["graze"] < GRAZE_FULL_CAP
                           else graze_low_rate(frames))
                seg_rew += _g_rate
                rew_mix["graze"] += _g_rate
                micro_bank += _g_rate   # R62: 入银行(回合末胜负结算)
                graze_frames += 1
            # 规避: TTI触发+位移脱离+零承伤(归因干净: 攻击宏蹭不到 —
            # 要求80px真实位移脱弹; R17 0.08→0.20 对冲"穿弹出招"吸引子)
            # R35: 保留为事件奖励(擦弹/规避是瞬时事件, 不适合势函数)
            if self.feat_builder.check_evasion(left, d_take):
                seg_rew += R_EVADE
                rew_mix["evade"] += R_EVADE
                micro_bank += R_EVADE   # R62: 入银行(回合末胜负结算)
            # R35: 防御奖励已由势函数覆盖 — 格挡→HP不掉→势不降→等效正奖励
            # 旧L1/L2逐帧奖励是刷分根源(站防每帧+0.06=每秒+3.72), 已移除。
            # 防御的BC锚(expert_rec推荐立防)保留 — 引导但不直接付费。

            # R61z: 空中被动惩罚 — 空中>宽限帧且非攻击/非受击态
            # (跳跃逃逸的"零惩罚盲区"修复: 空中挂机不再免费)
            # BH-4.2: 豁免抽为air_passive_exempt(过动作门 — 飞翔逃逸
            # 的残留untech不再错误豁免反逃逸惩罚)
            if (left.get("airBorne", False)
                    and not air_passive_exempt(left)):
                self._air_passive_f += 1
                if self._air_passive_f > AIR_PASSIVE_GRACE:
                    seg_rew -= R_AIR_PASSIVE
                    rew_mix["air_passive"] = rew_mix.get(
                        "air_passive", 0.0) - R_AIR_PASSIVE
            else:
                self._air_passive_f = 0

            # ---- TTI估计: 最近弹距的接近速度 ----
            near_d = None
            for o in objs[:24]:
                od = abs(o[1] - left["position.x"])
                if near_d is None or od < near_d:
                    near_d = od
            tti = 9.9
            if near_d is not None and prev_near_d is not None and near_d < 400:
                closing = prev_near_d - near_d
                if closing > 2:
                    tti = max(0.0, near_d / closing / 62.0)   # 帧→秒: /62
            prev_near_d = near_d

            # ---- 宏队列推进(R61u C1: 统一执行器) ----
            frozen = (left["hitStop"] > 0) or (left["timeStop"] > 0)
            # R61u(C1): 内联队列推进(原~70行)已抽至macro_executor.py
            # — train_tm与side_driver共同调用(双拷贝终结)
            if macro_queue and not frozen:
                # 符卡目标步初始化(sc:步状态机需要)
                if isinstance(macro_queue[0][0], str) \
                        and macro_queue[0][0].startswith("sc:") \
                        and self._sc_tgt is None:
                    self._sc_tgt = int(macro_queue[0][0][3:])
                _prev_q = macro_queue
                macro_queue, gate_frames, dec_name, _cur_inp = (
                    macro_executor.advance_queue(
                        macro_queue, gate_frames,
                        left, right, d_deal, d_take,
                        frozen, left["spirit"], dx_guard, dec_name,
                        GUARD_PREP_MACROS, GUARD_ALL_IDS,
                        self._sc_step, self._sc_reset))
                if _cur_inp is not None:
                    if (isinstance(_cur_inp, tuple)
                            and _cur_inp[0] == "ender"):
                        # R61w(C5, P1-A从零#2接线): ender菜单信号 — 原
                        # 元组落入_sc_next_input→后续SC帧dict()崩溃且
                        # 菜单掩码从未实施。修: 转成ender掩码(下一决策
                        # 点策略从菜单中选终结技, 复用B2事件掩码机制)。
                        _m = np.zeros(self.n_macros, dtype=bool)
                        for _ei in _cur_inp[1]:
                            if 0 <= _ei < self.n_macros:
                                _m[_ei] = True
                        self._ender_mask = _m if _m.any() else None
                        _cur_inp = None
                    else:
                        # 审计从零#3推迟项(sc步首帧镜像泄漏): 执行器按键步
                        # 输出不镜像, 存入_sc_next_input后sc步首帧原样泄出
                        # — 背向时方向反一帧。存入时按当前朝向镜像
                        # (sc本体SW/SC无方向位, 不受影响)。
                        if isinstance(_cur_inp, dict) and _cur_inp.get("H"):
                            _cur_inp = dict(_cur_inp)
                            if self._last_dir < 0:
                                _cur_inp["H"] = -_cur_inp["H"]
                        self._sc_next_input = _cur_inp

            # ---- 决策点(队列空) ----
            # R61l(B2): 事件反应期间产生**策略条件化决策点** —
            # 策略从事件约束掩码中自主选择(入轨迹→获信用/担责)
            # (R51旧版: 反应期间不产生决策=守式不入轨迹 — 已废,
            #  B2让反应决策成为真实训练数据)
            _ev_mask = getattr(self, '_frame_event_mask', None)
            _end_mask = getattr(self, '_ender_mask', None)
            if not macro_queue:
                # 虚拟视觉(包渲染, 内部维护3帧栈)
                vf = self._visual_feat(left, right, objs)  # 栈由_push_frame维护
                if vf is not None:
                    feat = vf
                    # 更新对手模型(决策拍, 间隔≈10逻辑帧; 62fps教义换算)
                    self.feat_builder.update_opp(10 / 62, left, right, weather,
                                                 opp_vx=opp_vx_ema)
                    side = self._build_side(left, right, weather,
                                            self._cur_bullets)
                    # 决策掩码: 基础 + 符卡动态门控(目标在手且够耗费)
                    # + 背向禁方向攻 + 远距禁近战/贴身禁弹幕
                    mask = self.base_mask | self._sc_usable_mask(left)
                    # R61l(B2): 事件反应掩码交集(策略从事件约束中选)
                    if _ev_mask is not None:
                        mask = mask & _ev_mask
                    # R61w(C5): ender菜单掩码交集(起手命中→策略从
                    # 终结技菜单中选 — 分层连段的二次决策快路径)
                    if _end_mask is not None:
                        mask = mask & _end_mask
                    dx_abs = abs(right["position.x"] - left["position.x"])
                    if back_turned:
                        mask = mask & ~self.dir_attack
                    # R60(F-9): 距离门抽出为near_gate(行为测试钉住
                    # "330外弹幕放行" — 变异面: 换melee_idx=全攻击集)
                    mask = self.near_gate(mask, dx_abs)
                    # R23: 位置特化连段门控 — 版边连须对手贴角,
                    # 空连须对手浮空(口径同段9贴角: x<120 或 >1120)
                    _ox = right["position.x"]
                    if not (_ox < 120 or _ox > 1120):
                        mask = mask & ~self.corner_combo_idx
                    if not right["airBorne"]:
                        mask = mask & ~self.air_combo_idx
                    # R24: 射程门控 — 已解析体术宏超出reach+余量禁采样
                    # (弹幕/技能/未解析宏不受影响, 类级330门仍是外栅栏)
                    if self.reach_mask_idx.any():
                        _out = self.reach_mask_idx & (
                            dx_abs > self.macro_reach + REACH_MARGIN)
                        if _out.any():
                            mask = mask & ~_out
                    # R25: 纵向门控(判定二维) — |dy|超纵向射程禁采样
                    # (对空3A系纵向大/下段2A系纵向小, 高度错配=空挥)
                    _ady = abs(right["position.y"] - left["position.y"])
                    if self.reach_v_mask_idx.any():
                        _outv = self.reach_v_mask_idx & (
                            _ady > self.macro_reach_v + REACH_MARGIN)
                        if _outv.any():
                            mask = mask & ~_outv
                    # JZ-3.2: 对手投技无敌窗(起身10F/防硬直+10F/起跳1F/
                    # 受身)内禁采样投技宏 — 掩码层, 窗外策略自由
                    if self.throw_idx.any() and self._throw_invuln_trk.invuln > 0:
                        mask = mask & ~self.throw_idx
                    if not mask.any():
                        # 兜底: 全禁时优先保约束语义(ender菜单/事件反应
                        # 比回退基础掩码更忠实于触发源), 都无约束才回退
                        mask = (_end_mask if _end_mask is not None
                                and _end_mask.any() else
                                _ev_mask if _ev_mask is not None
                                and _ev_mask.any() else self.base_mask)
                    # v2配额探索: 新宏(计数<150)12%探针覆盖 + 乐观先验
                    # R50(体检A4): 原子宏配额延长 — 零初始化迁移的logit
                    # 需要梯度才能>0, 但150次配额跑完后策略层不选零logit宏
                    # → 鸡生蛋. 修: 原子宏(核心投资)配额上限150→1000
                    newbie_legal = [i for i in range(self.n_macros)
                                    if mask[i]
                                    and self.macro_counts[i] < (
                                        1000 if self.macros[i][0].startswith('原子')
                                        else 150)]
                    nbias = None
                    _pred = None   # S-3: 策略意图top-1(探针/引导路径无)
                    _probe_fired = False
                    _vg_on = False
                    _vg_best = None
                    if newbie_legal and self._ppo_act.rng.random() < 0.12:
                        mid = int(self._ppo_act.rng.choice(newbie_legal))
                        _probe_fired = True
                    else:
                        if newbie_legal:
                            nbias = np.zeros(self.n_macros, dtype=np.float32)
                            for i in newbie_legal:
                                nbias[i] = 2.0 * (1.0 - self.macro_counts[i] / 150.0)
                        # R17③连段组合子: 连段中(连续伤害>0)→攻击宏加成
                        # 模型在连段命中状态偏好继续攻击而非重置
                        _cc = getattr(self.feat_builder, '_combo_chain', 0)
                        if _cc > 0:
                            if nbias is None:
                                nbias = np.zeros(self.n_macros, dtype=np.float32)
                            _combo_bias = min(1.5, _cc * 0.1)  # 连段越长加成越大
                            for i in range(self.n_macros):
                                if self.macros[i][0] in CHAR_LIBS[self.char].get("combo", set()) | \
                                        CHAR_LIBS[self.char].get("melee", set()):
                                    nbias[i] += _combo_bias
                        # S-4阶段1: GRU逐步(输入=当前side切片87维),
                        # repr16入采样(W_gru零=位等价, 阶段2解冻起效)
                        from opp_gru import gru_slice as _gru_slice
                        self._gru_h = self._ppo_act.opp_gru.step(
                            _gru_slice(side, self.n_macros),
                            getattr(self, '_gru_h', None))
                        _gru_repr = self._ppo_act.opp_gru.repr16(self._gru_h)
                        mid, _pred = self._ppo_act.sample(
                            feat, side, mask=mask, bias=nbias,
                            return_pred=True, gru_repr=_gru_repr)
                    # R35(差距#3-L1): 价值引导宏选择 — critic评估Top-5
                    # 相当于一步前瞻搜索(depth=1), 零新参数
                    # (第九轮审计P0-3: 原`_V,=...[1:]`解包3元组的[1:]=2元组
                    #  → ValueError被except吞 → 特性从未执行过; 且_base_v
                    #  算出未用。修复: 取[1], _base_v作切换阈值 — 候选须
                    #  优于基准值才顶替采样宏, 保探索不被critic劫持)
                    if (mid is not None and hasattr(self._ppo_act, 'W1v')
                            and self._ppo_act.W1v is not None
                            and self._ppo_act.rng.random() < 0.3):
                        try:
                            _Xn = self._ppo_act._trunk_fwd_chunked(
                                feat.reshape(1, -1))
                            _V = self._ppo_act._v_forward(
                                _Xn, side.reshape(1, -1))[1]
                            _base_v = float(_V[0, 0]) if _V.ndim == 2 \
                                else float(_V[0])
                            # 用side vector中宏one-hot的value做快速评估:
                            # 把side的宏one-hot改为候选宏, 比较critic输出
                            _cands = np.where(mask)[0]
                            if len(_cands) > 1:
                                _cands = _cands[
                                    np.argsort(-np.asarray(nbias)[_cands])[:5]] \
                                    if nbias is not None else _cands[:5]
                                _best, _best_v = mid, _base_v
                                _s_try = side.copy()
                                for _c in _cands:
                                    _s_try[:self.n_macros] = 0.0
                                    _s_try[_c] = 1.0
                                    _Vc = self._ppo_act._v_forward(
                                        _Xn, _s_try.reshape(1, -1))[1]
                                    _vc = float(_Vc[0, 0]) if _Vc.ndim == 2 \
                                        else float(_Vc[0])
                                    if _vc > _best_v:
                                        _best, _best_v = _c, _vc
                                mid = int(_best)
                                # P1-5: VG成分入混合边际(30%确定重选)
                                _vg_on = True
                                _vg_best = _best
                        except Exception:
                            pass    # 价值引导失败不阻塞采样
                    self.macro_counts[mid] += 1
                    # R61l(B2): 事件反应决策完成 — 清除掩码+守卫
                    if _ev_mask is not None:
                        self._frame_event_mask = None
                        self._in_frame_reaction = False
                    # R61w(C5): ender菜单单次有效 — 决策完成即消费
                    if _end_mask is not None:
                        self._ender_mask = None
                    # R56(fleet): actor模式logP记录(在mid最终确定后)
                    # R60(F-11): stored_logp入update=真重要性比。
                    # P1-5(从零#4): 探针(12%均匀)/VG重选(30%)路径的行为
                    # 概率=混合边际(mixed_behavior_p) — 原记纯π系有偏
                    # (~40%决策), 红线①"actor记真实logP"债清偿。
                    _mix_p = None
                    if newbie_legal or _vg_on:
                        P_rec = self._ppo_act._pi_forward(
                            feat.reshape(1, -1), side.reshape(1, -1),
                            temp=self._ppo_act._temp,
                            mask=mask.reshape(1, -1) if mask is not None
                            else None, bias=nbias)[2][0]
                        _mix_p = mixed_behavior_p(
                            P_rec[mid], mid,
                            probe_legal=newbie_legal if newbie_legal else None,
                            vg_on=_vg_on, vg_best=_vg_best)
                    if self._fleet_logp_rec is not None:
                        self._fleet_logp_rec(mid, feat, side, mask, nbias,
                                             mix_p=_mix_p)
                    elif _mix_p is not None:
                        ep_logps.append(float(np.log(_mix_p)))
                    else:
                        P_rec = self._ppo_act._pi_forward(
                            feat.reshape(1, -1), side.reshape(1, -1),
                            temp=self._ppo_act._temp,
                            mask=mask.reshape(1, -1) if mask is not None
                            else None, bias=nbias)[2][0]
                        ep_logps.append(float(np.log(max(P_rec[mid],
                                                         1e-10))))
                    feats.append(feat.astype(np.uint8))
                    sides.append(side)
                    acts.append(mid)
                    opp_acts.append(min(int(right["action"]) // 128, 7))
                    masks_hist.append(mask)      # 更新用同掩码(PPO比率干净)
                    # R47(可行性天花板3): _expert_rec手写弱启发式已删 —
                    # 永久"平均人类风格"梯度拉力与超人方向冲突; oracle BC
                    # (真实专家数据)保留但允许退火归零(BC_W_MIN=0)。
                    # P2-1修复: 空挥结算 — 上一决策的攻击宏完整执行且零伤害、
                    # 对手全程未防御 → W_WHIFF×倍率(移动宏倍率0不判;
                    # 受击中止/SC中止已在清队处豁免)
                    if dec_name is not None and dec_dmg == 0.0 and not dec_guarded:
                        wc = self._whiff_cost(dec_name)
                        if wc > 0:
                            # 灵力感知加重: 起手时灵力不足仍选攻击宏 → ×2
                            _mult = 2.0 if (dec_spirit is not None
                                            and dec_spirit < LOW_SPIRIT_PEN) else 1.0
                            seg_rew -= W_WHIFF * wc * _mult
                            rew_mix["whiff"] -= W_WHIFF * wc * _mult
                    # R14-P0J: 本区间奖励记给上一个动作(a_{k-1})
                    if rews:
                        rews[-1] += seg_rew
                    rews.append(0.0)   # 新动作a_k的奖励槽(R16补回:
                    #  P0-J修复时误删append → rews恒空 → 每次更新触发
                    #  "ep_lens≠R长度"断言, 全部更新丢失)
                    seg_rew = 0.0
                    # BH-1: 决策点记账(在dec_name被替换前 — prev结算口径)
                    # 对手名源=feat_builder._opp_char(trainer自身无此属性,
                    # 首版取self._opp_char恒None→表5全是'?' — 上线即自检
                    # 抓出的第二处接线错)
                    from my_punish_tracker import classify as _bh_clsfy
                    _bh_cur_name = self.macros[mid][0]
                    self.bh.note_decision(
                        dec_name,
                        (_bh_clsfy(dec_name, CHAR_LIBS[self.char])
                         if dec_name else None),
                        dec_dmg, dec_guarded, _bh_cur_name,
                        _bh_clsfy(_bh_cur_name, CHAR_LIBS[self.char]),
                        getattr(self.feat_builder, '_opp_char', None))
                    if self._fl_decisions is not None:
                        self._fl_decisions.append((frames, int(mid)))
                    dec_name = self.macros[mid][0]
                    dec_dmg, dec_guarded = 0.0, False
                    dec_spirit = left["spirit"]   # R17: 起手灵力(空挥加重判据)
                    # S-2接线(2026-10-14): 决策落子 — 上宏结算/新宏开始/
                    # 类别序列/预测回写(S-1/S-3/S-5源, 维330-339)
                    from my_punish_tracker import classify as _clsfy
                    _dcls = _clsfy(dec_name, CHAR_LIBS[self.char])
                    if getattr(self, '_punish_active', False):
                        self.feat_builder.punish.end()
                    self._punish_active = True
                    # P1-1修(审计2026-10-16): 补name=宏名 — CE-1宏层
                    # 画像此前生产路径恒空(测试走name=路径全绿)
                    self.feat_builder.punish.begin(_dcls, name=dec_name)
                    self.feat_builder.note_decision(
                        ('JUMP', 'MELEE', 'BULLET', 'SKILL',
                         'GUARD_PREP', 'OTHER').index(_dcls))
                    if _pred is not None:
                        self.feat_builder.set_last_pred(*_pred)
                    # R47: _expert_rec已删(可行性天花板3: 永久人类风格
                    # 拉力与超人冲突) — BC目标=自身动作(纯自模仿, 无外部锚)
                    bc_targets.append(mid)
                    # 基准树诊断数据(标准树11列+S-7B风格2列: pc1/pc2 —
                    # 消费方按下标取0-10, 尾部追加向后兼容)
                    dx = abs(right["position.x"] - left["position.x"])
                    distill_rows.append([
                        dx, left["spirit"] / 1000.0, 1.0 if dx < 130 else 0.0,
                        mid, left["frameCount"],
                        right["position.y"] - left["position.y"],
                        1.0 if right["airBorne"] else 0.0,
                        1.0 if (near_d is not None and near_d < 220) else 0.0,
                        1.0 if left["position.x"] < right["position.x"] else 0.0,
                        tti,
                        1.0 if (right["position.x"] < 120
                                or right["position.x"] > 1120) else 0.0,
                        float(side[2 * self.n_macros + 340]),
                        float(side[2 * self.n_macros + 341]),
                    ])
                    self.last_macro2 = self.last_macro
                    self.last_macro = mid
                    # 入队新宏(镜像在执行时逐帧按当前朝向计算 — 转向延迟安全)
                    # R17②等级条件宏: 技能升级后取消帧减(等级越高窗口越早开)
                    from level_macros import adjust_script
                    script = adjust_script(self.macros[mid][1],
                                           self.feat_builder._skill_levels)
                    # P0-B(从零#2): 入队走macro_executor.enqueue_script单源
                    # — 原内联(ks,0)丢字符串步载荷(branch/link/ender)
                    macro_executor.enqueue_script(macro_queue, script)

        # CE-0.1: 抽样局帧日志落盘(原子; 滚动保留最近500局 ~200MB上限)
        if self._fl_frames is not None and self._fl_frames:
            try:
                import pickle as _pkl
                _fld = os.path.join(STORE_DIR, 'frame_logs', self.char)
                os.makedirs(_fld, exist_ok=True)
                _fnp = os.path.join(
                    _fld, 'fl_%s_%s_%05d.pkl' % (
                        self.char, time.strftime('%Y%m%d_%H%M%S'),
                        self._bh_ep_n))
                with open(_fnp + '.tmp', 'wb') as _fh:
                    _pkl.dump({'char': self.char,
                               'opp_char': getattr(
                                   self.feat_builder, '_opp_char', None),
                               'fields': FL_FIELDS,
                               'frames': self._fl_frames,
                               'decisions': self._fl_decisions or []},
                              _fh, protocol=4)
                os.replace(_fnp + '.tmp', _fnp)
                # 修剪只作用于本角色子目录(跨角色互删已由目录隔离根治)
                _old = sorted(glob.glob(os.path.join(_fld, 'fl_*.pkl')),
                              key=os.path.getmtime)
                for _p in _old[:-500]:
                    try:
                        os.remove(_p)
                    except OSError:
                        pass
            except Exception as _fle_err:
                print('[BH-1] 帧日志落盘异常(%r) — 不影响训练' % _fle_err)
        # ---- episode结束 → 异步PPO更新(与下一局采集重叠) ----
        if feats:
            # 修(2026-09-21): 终局段奖励入账 — 原尾段seg_rew从未append,
            # 决胜回合KO(±10)静默丢失, 结果信号只剩前两回合
            if rews:
                rews[-1] += seg_rew
                # P1(§7.2): rews[0]是占位0, 丢弃使rews[i]对应acts[i]
            # R17仪表: 奖励成分(episode作用域 — 调参依据)
            # R63(P1-1)修: 原来打印的"总和"= sum(rew_mix.values()), 其中
            # dmg/taken **从不加进seg_rew**(HP由势函数差分覆盖, 见上),
            # 而真正扣分的micro_tax不在mix里 → 打印的总和既含幻影项、
            # 又漏扣分项, 与真实回报不同源(用户按此行调奖励经济学=
            # 读错量纲)。现: ①幻影项标注"(诊断,不入回报)"; ②总和只累计
            # 真实入账通道, 并打印该局实际回报以便自查。
            _real_sum = (rew_mix["ko"] + rew_mix["graze"] + rew_mix["evade"]
                         + rew_mix["whiff"] + rew_mix.get("air_passive", 0.0)
                         + rew_mix.get("micro_tax", 0.0))
            print("[奖励成分] 诊断(不入回报): 伤害+%.1f 承伤%.1f | "
                  "入账: KO%+.1f 擦弹+%.1f(%d帧) 规避+%.1f 空挥%.1f "
                  "空中被动%.1f 微收追扣%.1f 小计%+.1f 回报%+.1f"
                  % (rew_mix["dmg"], rew_mix["taken"], rew_mix["ko"],
                     rew_mix["graze"], graze_frames, rew_mix["evade"],
                     rew_mix["whiff"], rew_mix.get("air_passive", 0.0),
                     rew_mix.get("micro_tax", 0.0), _real_sum,
                     float(np.sum(rews)) if rews else 0.0))
            # R17环境健全性断言(用户2026-09-29反思): 策略树审计只照模型
            # 不照环境 — 木桩时代(09-27~09-28)审计全程照常出矩阵、无人
            # 察觉对手零输出。此断言当天即可抓住假COM。
            _opp_dmg = rew_mix["taken"] / R_TAKEN   # 两者皆负→正HP数
            if _opp_dmg < 500.0:
                print("[警报] 对手整局输出仅%.0f — 疑似木桩/对手驱动断连!"
                      % _opp_dmg)
        # R15: 已删
            # P1-3修复: 超时截断(非终局)用非终止标记, PPO用V(s_end) bootstrap
            # R39(第十轮P2-6): 协议错/断连/90s无帧结束的局原也走terminal=True
            # → GAE尾部按零价值自举 → 异常结束局尾部动作获系统性负偏优势
            # (崩溃史下非平凡比例数据被污染)。判定: 比分未到2局=对局未完=截断
            truncated = (time.time() - t0 >= self.ep_timeout
                         or (score_l_prev + score_r_prev) < 2)
            self._prev_pot = state_potential(left, right)  # R35: 下局初始势
            self._submit_update(feats, acts, rews, sides, distill_rows, frames,
                                masks_hist, bc_targets,
                                truncated=truncated, opp_acts=opp_acts,
                                logps=ep_logps)
            # 宏计数持久化
            # D13修复(从零审查): 全项目最后一个裸写产物 → 原子写
            _mc_tmp = self.macro_counts_path + ".tmp.npy"
            np.save(_mc_tmp, self.macro_counts)
            os.replace(_mc_tmp, self.macro_counts_path)
            return True
        print("[ep] 帧%d 无决策(视觉未就绪)" % frames)
        return False

    def _whiff_cost(self, name):
        """空挥成本倍率(v2标定, 62fps版): 体术/连段/压制2.5 · 必杀120F/62 ·
        C系62F/62 · B系45F/62 · 其余攻击1.0 · 非攻击宏0(移动/防御/受身不判)。"""
        L = CHAR_LIBS[self.char]
        if name not in L["attack"]:
            return 0.0
        if (name in L["melee"] or name in L["combo"]
                or name in L["string"]):
            return 2.5
        if name in L["skill"]:
            return 120.0 / 62.0
        if name in ("5C", "6C"):
            return 62.0 / 62.0
        if name in ("5B", "6B", "2B", "jB"):
            return 45.0 / 62.0
        return 1.0

    # R47(可行性天花板3): _expert_rec方法已删 — 手写距离→宏查表构成
    # 永久"平均人类风格"梯度拉力(BC_W_MIN=0.05时bcw=5%的梯度永不消失),
    # 与超人目标(彻底离开人类先验)方向冲突。oracle BC(真实专家数据)
    # 保留, 且BC_W_MIN已改0允许锚退火归零。

    def _submit_update(self, feats, acts, rews, sides, distill_rows, frames,
                       masks_hist=None, bc_targets=None, truncated=False,
                       opp_acts=None, logps=None):
        # R60(F-10): 喂活回报-胜率看门狗 — 原self._last_ret从未赋值,
        # corrcoef读全0永不报警(该表专为"擦弹收入碾压KO"退化建, 从零
        # 审计F-10抓出)。同步记局回报(无异步滞后, _settle_match即读)。
        self._last_ret = float(np.sum(rews)) if len(rews) else 0.0
        """异步更新流水线(2026-09-22, 基准: 700~1500决策update 19~84s ≈ 墙钟一半):
        - 采样用冻结快照_ppo_act(行为策略=快照, PPO比率语义干净);
        - 更新在后台线程跑live权重, 与下一局play重叠(GIL: numpy矩阵乘释放GIL);
        - 上一局更新未完时先join(同时至多一个更新在飞), 完成后刷新快照。
        opp_acts: 每决策拍对手动作类 → 标签=下一拍值(末拍-1, 不计损失)。
        logps: R60(F-11)采样时行为策略logP → stored_logp(真重要性比)。"""
        import copy
        import threading
        if getattr(self, "_upd_thread", None) is not None:
            self._upd_thread.join()
            self._upd_thread = None
            self._ppo_act = copy.deepcopy(self.ppo)

        M = np.stack(masks_hist) if masks_hist else None
        B = np.array(bc_targets, dtype=np.int64) if bc_targets else None
        # P1-2修复: bc_mask用逐拍掩码(原版全1, 被mask的宏也被BC拉引)
        BM = M.astype(np.float32) if (M is not None and B is not None) else (
            np.ones(self.n_macros, dtype=np.float32) if B is not None else None)
        # P1-3修复: 超时截断标记
        EP_TERMS = [not truncated]
        # R17④: 下一拍对手动作类(末拍无后续→-1)
        OPP_NEXT = (np.array(opp_acts[1:] + [-1], dtype=np.int64)
                    if opp_acts else None)

        # 自审攒批: 单局小批(300-800决策)梯度方差大 → 攒ACCUM_EP局合批更新。
        # ppo.update原生支持多局(ep_lens列表+逐局GAE截断)。
        ACCUM_EP = 1   # 回退: 3局合批太慢, 1局更快
        pend = getattr(self, '_pend_ep', None)
        if pend is None:
            pend = self._pend_ep = []
        pend.append((np.stack(feats), np.array(acts),
                     np.array(rews, dtype=np.float32), np.stack(sides),
                     M, B, BM, EP_TERMS, frames, OPP_NEXT,
                     np.array(logps, dtype=np.float32) if logps else None))
        # 基准树数据落盘(增量合并, 旁路无需等更新)
        self._save_distill(distill_rows)
        # 视觉供帧健康: 本局特征帧间方差
        fa = np.stack(feats).astype(np.float32)
        v = float(np.abs(np.diff(fa, axis=0)).mean()) if len(fa) > 1 else 0.0
        print("[ep] 视差%.3f (攒批%d/%d)" % (v, len(pend), ACCUM_EP))
        if v < 0.02:
            print("[警告] 特征真冻结(视差%.4f) — 供帧管线疑似断流!" % v)
        # R16§0.1: 生产环境弹匹配频率(每局报告一次, 回答"伪威胁机制
        # 在生产里多常见" — 离线分片的16.6%因跳帧不可作数)
        um_r, zb_pf, um_fr = self.feat_builder.unmatched_stats()
        if um_fr > 0:
            print("[弹匹配] 帧%d 未匹配率%.1f%% 零速入盒%.2f颗/帧"
                  % (um_fr, um_r * 100.0, zb_pf))
        if len(pend) < ACCUM_EP:
            return
        feats = np.concatenate([e[0] for e in pend])
        acts = np.concatenate([e[1] for e in pend])
        rews = np.concatenate([e[2] for e in pend])
        sides = np.concatenate([e[3] for e in pend])
        M = np.concatenate([e[4] for e in pend]) if pend[0][4] is not None else None
        B = np.concatenate([e[5] for e in pend]) if pend[0][5] is not None else None
        BM = np.concatenate([e[6] for e in pend]) if pend[0][6] is not None else None
        EP_TERMS = [t for e in pend for t in e[7]]
        frames = sum(e[8] for e in pend)
        OPP_NEXT = (np.concatenate([e[9] for e in pend])
                    if pend[0][9] is not None else None)
        LOGPS = (np.concatenate([e[10] for e in pend])
                 if pend[0][10] is not None else None)
        ep_lens = [len(e[1]) for e in pend]
        self._pend_ep = []

        def work():
            try:
                stats = self.ppo.update(
                    feats, acts, rews, sides, ep_lens, masks=M,
                    bc_targets=B, bc_mask=BM, ep_terms=EP_TERMS, temp=self.ppo._temp,
                    bc_extra=self._sample_bc(), opp_next=OPP_NEXT,
                    stored_logp=LOGPS)
                self.ppo.save(self.pi_path, self.v_path)
                # 第八轮§4: 增|KL|/优势幅度/价值损失 — 区分"收敛"与"停摆"
                _aux = ""
                if stats.get("aux_loss") is not None:
                    _aux = " 预aux%.3f/命中%.0f%%" % (
                        stats["aux_loss"], (stats.get("aux_acc") or 0) * 100)
                print("[ep] 帧%d 决策%d 回报%.2f 熵%.2f |KL|%.4f 优势%.3f "
                      "值损%.4f%s %s" % (
                          frames, len(feats), stats["return"], stats["entropy"],
                          stats.get("kl_abs", abs(stats["kl"])),
                          stats.get("adv_abs", -1),
                          stats.get("value_loss", -1),
                          _aux,
                          "早停" if stats["kl_stopped"] else ""))
            except Exception as e:
                import traceback
                traceback.print_exc()
                print("[ep] 更新异常: %s: %s" % (type(e).__name__, e))

        self._upd_thread = threading.Thread(target=work, daemon=True)
        self._upd_thread.start()
        # 基准树数据落盘(增量合并, 旁路无需等更新)
        # 重复_save_distill已删(第十轮P1)
        # 视觉供帧健康: 本局特征帧间方差
        fa = np.stack(feats).astype(np.float32)
        v = float(np.abs(np.diff(fa, axis=0)).mean()) if len(fa) > 1 else 0.0
        # 第八轮§4: 旧阈值0.5在正常局(实测~0.30)100%触发=零信息。
        # 正常局也有视差数值 → 并入[ep]行; 仅真冻结(<0.02, 供帧断流)才告警。
        print("[ep] 视差%.3f" % v)
        if v < 0.02:
            print("[警告] 特征真冻结(视差%.4f) — 供帧管线疑似断流!" % v)

    def _save_distill(self, rows):
        # R56(fleet F4): 逻辑原文抽出至episode_core.save_distill_rows
        # (fleet learner合并蒸馏数据共用同一份代码 — 防双拷贝漂移;
        # 本委托路径=生产回归测试)
        from episode_core import save_distill_rows
        save_distill_rows(STORE_DIR, self.char, self.suffix, rows)

    def audit_tree(self):
        """基准树诊断(standard_tree移植): 态势节点×模型实际 偏离矩阵。
        2026-09-22: 三角色各自教义树(魔理沙/萃香不再用灵梦树打折近似)。"""
        from standard_tree import TREES
        path = os.path.join(STORE_DIR,
                            "distill_data_%s%s.npz" % (self.char, self.suffix))
        # P3-4修复(补全): 与_save_distill同径(原读DIR=冻结旧档, audit输出陈数据)
        if not os.path.exists(path):
            print("[audit] 无蒸馏数据")
            return
        d = np.load(path)
        X, Y = d["X"], d["Y"].astype(int)
        names = [m[0] for m in self.macros]
        print("\n[audit %s] 蒸馏样本%d — 基准树偏离:" % (self.char, len(X)))
        defects = []
        for name, cond, actions, src in TREES[self.char]:
            mask = np.array([cond(r) for r in X])
            n = int(mask.sum())
            if n < 20:
                continue
            sub = Y[mask]
            counts = {}
            for m in sub:
                nm = names[int(m)] if 0 <= int(m) < len(names) else "?"
                counts[nm] = counts.get(nm, 0) + 1
            top = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
            std_set = {a for a, _ in actions}
            cov = sum(c for m, c in counts.items() if m in std_set) / n
            off = [(m, c) for m, c in top if m not in std_set]
            print("  [%s] n=%d 标准覆盖%.0f%% 实际: %s" % (
                name, n, cov * 100,
                " ".join("%s×%d" % kv for kv in top[:4])))
            for m, c in off[:3]:
                defects.append((name, m, c / n))
        if defects:
            for name, m, frac in sorted(defects, key=lambda x: -x[2])[:6]:
                print("  ⚠ [%s] 非标动作 %s 占%.0f%%" % (name, m, frac * 100))
        else:
            print("  ✓ 与标准一致")


def build_opp_cycle(specs, pool_root=None, strict=True):
    """--opp规格列表 → 轮换对手cycle。R56(fleet): 从main()原文抽出 —
    fleet actor用同一函数构造对手池(防双拷贝漂移)。
    specs: ["reimu", "COM", ...]或["reimu:path.npz"]; 返回[(char, path|None)]
    或specs为空时None。轮换时None→动态解析池快照(R43)。
    D3'(R65): pool_root可注入 — 原恒查生产POOL_DIR, 而fleet actor运行时
    _resolve_pool读注入的fleet池根=启动校验与运行时解析**查的不是同一个
    池**(现3角色靠生产池恰好有trio快照侥幸通过)。fleet须传fleet池根。
    strict=False时池空角色跳过该周期位(league角色种未种齐不炸actor;
    运行时再度变空由_rotate_opp的安全跳过兜底), strict=True保留原
    SystemExit语义(单实例模式误配置响亮失败)。"""
    if not specs:
        return None
    from outer_loop import OpponentPool
    pool = OpponentPool(pool_root) if pool_root else OpponentPool()
    # R22(用户2026-10-02): 池深k=3 — 原latest(1)只有对手当前版,
    # 无历史对抗(策略循环+旧技能遗忘风险); 镜像对局由--opp含己方
    # 角色实现(run_parallel已配)。快照按新近度交错排列, 每个轮换
    # 周期覆盖全部对手一遍。R43: POOL_K提升为模块常量。
    _per = []
    for spec in specs:
        ch, _, pth = spec.partition(":")
        if ch == "COM":
            _per.append([("COM", None)])   # VS_COM模式(COM驱动P2)
            continue
        if not pth:
            cands = pool.latest(ch, k=POOL_K)
            if not cands:
                if strict:
                    raise SystemExit(
                        "对手池无 %s 快照 — 先跑 outer_loop.py snapshot" % ch)
                # D3'(R65): 非严格模式跳过该位(league角色未种/被清,
                # actor降级到剩余周期位, 不炸启动)
                print("[opp] 池无%s快照 — 周期跳过该位" % ch)
                continue
            # R43: 条目存None — 轮换时动态解析(新快照自动入局);
            # 此处仅校验池非空并留启动信息
            _per.append([(ch, None)])
        else:
            _per.append([(ch, pth)])
    from itertools import zip_longest
    opp = []
    for _tier in zip_longest(*_per):
        opp.extend(_e for _e in _tier if _e is not None)
    print("=== 对手池(轮换, k=%d, R43动态解析): %s ===" % (
        POOL_K,
        ["COM" if c == "COM" else
         ("%s@%s" % (c, os.path.splitext(os.path.basename(m))[0])
          if m else "%s@池动态" % c)
         for c, m in opp]))
    return opp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="reimu", choices=list(CHAR_LIBS))
    ap.add_argument("--port", type=int, default=20800)
    ap.add_argument("--tps", type=int, default=60,
                    help="每秒逻辑帧(60=原速, 120=2倍; 视觉观测建议60)")
    ap.add_argument("--episodes", type=int, default=100)
    ap.add_argument("--ep-timeout", type=float, default=300.0)
    ap.add_argument("--slot", type=int, default=None,
                    help="窗口槽位0/1/2 — 多实例并排(观看用, 虚拟视觉不依赖)")
    ap.add_argument("--render", action="store_true",
                    help="保留游戏渲染(默认关 — 无头省CPU, 虚拟视觉不需要屏幕)")
    ap.add_argument("--opp", action="append", default=None,
                    help="外环训练半环: 对手池条目 char[:model_path], 可多次"
                         "(VS_PLAYER自对弈; 缺路径=pool最新快照); 缺省VS_COM")
    ap.add_argument("--suffix", default="",
                    help="模型/产物文件后缀(实验分支隔离, 防双训练器写同档)")
    ap.add_argument("--com-difficulty", type=int, default=1,
                    help="COM难度: 0=Easy 1=Normal 2=Hard 3=Lunatic "
                         "(实测地址0x008998A4)")
    args = ap.parse_args()

    # R56(fleet F4): 对手池构造抽出为build_opp_cycle(fleet actor共用)
    opp = build_opp_cycle(args.opp)

    print("=== TM训练: %s 端口%d tps%d 渲染%s ===" % (
        args.char, args.port, args.tps, "开" if args.render else "关"))
    # 第八轮审查§3: 启动期构造失败(如游戏120s未连接)曾让训练器直接退出且
    # 无重试(train()里的重建保护不覆盖__init__) — 构造也纳入同规格重试。
    tr = None
    last_init_err = None
    for _attempt in range(5):
        try:
            tr = TMTrainer(args.char, args.port, tps=args.tps,
                           episodes=args.episodes, ep_timeout=args.ep_timeout,
                           slot=args.slot, render=args.render, opp=opp,
                           suffix=args.suffix,
                                           com_difficulty=args.com_difficulty)
            break
        except KeyboardInterrupt:
            raise
        except Exception as e:
            last_init_err = e
            # 退避90s: 周期器评估局造成的资源挤兑下, 快速重试会再拉游戏放大拥塞
            print("[init] 第%d次构造失败: %s — 90s后重试(防拥塞放大)" % (_attempt + 1, e))
            time.sleep(90)
    if tr is None:
        raise SystemExit("TMTrainer 构造 5 次均失败: %s" % last_init_err)
    try:
        tr.train()
    except KeyboardInterrupt:
        print("中断 — 等待后台更新完成后保存模型")
        # R39(第十轮P2-3): 原直接save未join更新线程 — 后台可能正在
        # (a)经Adam改权重→主线序列化撕裂混合权重; (b)写同一路径tmp→
        # 交叉损坏npz+双os.replace。join后再save(worker成功路径已save过,
        # 此处兜worker异常未save的情况; join后无并发写者, 幂等安全)
        _t = getattr(tr, "_upd_thread", None)
        if _t is not None:
            _t.join()
            tr._upd_thread = None
        tr.ppo.save(tr.pi_path, tr.v_path)
        tr.env.close()
        # R19(审查2026-10-02): 原版return=exit 0, 监督器把人为停止
        # 记成"正常完成"。130=SIGINT惯例, run_parallel不重启。
        raise SystemExit(130)


if __name__ == "__main__":
    main()
