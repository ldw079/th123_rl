# -*- coding: utf-8 -*-
"""R61u(C1): 统一宏执行器 + 分支门系统 — train_tm/side_driver双拷贝终结.

架构(combo改进方案§2.3):
  当前: train_tm._run_episode和side_driver.frame_input各有一份
  宏队列推进逻辑(受击中止/R34中断/灵力门/confirm门/sc步) —
  这是本项目最大的双拷贝漂移源(macros/side_driver的前车之鉴).

  本模块: 把队列推进抽为**单一实现**, 两方共同引用.
  同时新增**分支门语法**(branch) — 从二值截断(confirm/cconfirm)
  升级为多路路由(hit/blocked/whiff/opp_jump/delay_then).

宏脚本步骤类型(向后兼容):
  (keys_tuple, frame_count)   — 按键步(既有)
  ("confirm", 0)              — 命中门(既有: d_deal>0→续, 否则4帧截断)
  ("cconfirm", 0)             — 接触门(既有: d_deal>0或被防→续)
  ("sc:ID", 0)                — 符卡步(既有, 状态机)
  ("branch", {cond: steps})   — **分支门(C1)**: 按游戏状态路由
  ("link", (max_wait, steps)) — **目押门(C3)**: 等untech→0最速出招
  ("pos_gate", {...})         — **位置门(CE-3.4)**: confirm后续段按坐标路由

目押(C3, combo改进方案§2.4):
  连段步进器读对手untech(每帧可见), 下一击条件改为"对手hitstun
  结束后≤2帧内"而非固定第N帧. link=(max_wait, steps) = 等待
  untech→0后最速出招, 超时max_wait落空截断. 近/远A分辨(Part1
  的fvariant)在此必需 — 步进器按fvariant查帧表(MOVE_STARTUP
  已有基础).

分支条件:
  "hit"        — 上一攻击命中(d_deal > 0) → 取该分支的步骤
  "blocked"    — 被防(d_deal == 0且对手在防御态) → 取该分支
  "whiff"      — 空挥(默认None=截断, 同confirm超时)
  "delay_then" — 放帧: (N, steps) = 门通过后延迟N帧再续(拍子择)
  "opp_jump"   — 对手空中(airBorne) → 该分支

位置门(CE-3.4, capability_extension_plan v3):
  评估时机=confirm门通过后的续段首帧 — 路由参考量 =
  对手距近角距离 − dx_opp_hit外推(CE-3位移表; 仅作路由参考
  不入特征, 保守). 外推后 < threshold(默认120px, R23贴角口径)
  → corner分支(版边收尾), 否则 → mid分支(弹墙推板收尾).
  corner未定义时回落mid(不因缺分支而截断已确认的连段).
  **状态声明(审计2026-10-16 P2)**: 语法+模板+16测试就绪, 当前
  宏库**无消费宏**(pos_gate步零使用) — 生效时点=宏库升版批次
  (连段A·自适应等经R23尾部契约追加, 与CH-3/JZ-4同批); 无运行时
  开关, 未消费前零行为影响.

目押(C3):
  ("link", (max_wait, steps)) — 等对手untech→0后最速出;
  超时max_wait帧未到0 → 截断. 观察窗计数器用gate_frames.

ender菜单(C5, combo改进方案§2.5):
  ("ender", [macro_indices]) — 起手confirm通过后清空队列+设置
  ender掩码(策略在下一决策点从菜单中自主选择终结技).
  架构: 复用B2事件掩码机制(train_tm._frame_event_mask).
"""
from __future__ import annotations

import numpy as np

# 分支条件评估需要的状态键
# 从零#2(执行器P2): 守卫ID集单源化 — 原此处是第三副本(frame_events/
# opp_model各一份), 漂移风险; 158=空防(非硬直边沿)不入集的语义见
# frame_events._GUARD_STUN_IDS注释(R61d A3裁决)。
from frame_events import _GUARD_STUN_IDS as GUARD_STUN_IDS  # noqa: E402
# BH-4.2(bug档): untech动作门 — link门等待期=真受击硬直(残留读数不空等)
from feat_builder import eff_untech  # noqa: E402
# 受击态族(从零#2执行器细部): 50-98受击/倒地 + 100被投 + 143/145压溃
# — hit判定的状态证据(持续~20帧, 天然结算窗)
HITSTUN_IDS = frozenset(range(50, 99)) | {100, 143, 145}


def evaluate_branch(branch_dict, left, right, d_deal, d_take):
    """评估分支门 → 返回应执行的步骤列表(或None=截断).

    branch_dict: {"hit": [...], "blocked": [...], "whiff": None, ...}
    left/right: 当前帧玩家状态dict
    d_deal: 自上次检查以来造成的伤害量
    d_take: 自上次检查以来承受的伤害量

    R61-aa(从零#2): hit判定 = 瞬时d_deal OR 对手受击态。原纯d_deal>0
    在confirm消费了命中帧后, branch所在帧读0 → 命中后误判whiff截断
    (R5"结算窗"教训未继承到新门; 受击态50-98持续~20帧=状态式结算窗)。
    """
    opp_a = right.get("action", 0)
    if d_deal > 0 or opp_a in HITSTUN_IDS:
        return branch_dict.get("hit")
    if opp_a in GUARD_STUN_IDS:
        return branch_dict.get("blocked")
    if right.get("airBorne", False):
        return branch_dict.get("opp_jump")
    # 默认: whiff (None=截断)
    return branch_dict.get("whiff")


def evaluate_position_gate(payload, left, right):
    """CE-3.4: 位置路由门 — confirm通过后的续段按对手坐标路由.

    payload: {"corner": steps|None, "mid": steps|None,
              "dx_opp_hint": float, "threshold": float}
    路由参考量 = 距近角距离 − dx_opp_hint(命中桶推板外推, CE-3
    位移表; 保守: 仅作路由参考不入特征). 外推后<threshold → corner,
    否则 → mid. corner键缺省时回落mid(已确认的连段不因缺分支截断);
    corner显式None=截断(与branch whiff语义一致).
    """
    rx = right.get("position.x", 640.0)
    _dist = min(rx, 1280.0 - rx)
    _hint = float(payload.get("dx_opp_hint", 0.0))
    _thr = float(payload.get("threshold", 120.0))
    if _dist - _hint < _thr:
        if "corner" in payload:
            return payload.get("corner")
        return payload.get("mid")
    return payload.get("mid")


def advance_queue(macro_queue, gate_frames, left, right, d_deal, d_take,
                  frozen, spirit, dx, dec_name, GUARD_PREP_SET,
                  GUARD_ALL_IDS, sc_step_fn, sc_reset_fn, hit_mem=None):
    """统一宏队列推进 — train_tm和side_driver共同调用.

    参数:
      macro_queue: [(keys, frames_left), ...] 当前队列
      gate_frames: int 观察窗计数器
      left/right: 当前帧玩家状态
      d_deal/d_take: 自上次帧以来的伤害量
      frozen: bool hitstop/timestop
      spirit: float 当前灵力
      dx: float 位置差
      dec_name: str/None 当前决策的宏名(空挥判定用)
      GUARD_PREP_SET: set 防御预备宏名
      GUARD_ALL_IDS: set 防御动作ID集
      sc_step_fn: callable 符卡状态机(返回pop, abort, hold)
      sc_reset_fn: callable 符卡状态重置

    返回: (macro_queue, gate_frames, dec_name, current_input)
      current_input: dict 本帧要发的键(None=不发)
    """
    # task-58: 命中/伤害记忆窗(env TH123_EXEC_HITMEM>0 时由调用方提供)
    # 背景(2026-10-25 P1): 命中帧与 hitStop 同帧, 主循环 frozen 帧跳过本函数
    # → 该帧 d_deal 永久丢失; confirm 4F 窗永远读不到 → 首段命中即截断.
    # hit_mem = 最近 N 帧 d_deal (含 frozen 帧), None=旧行为逐位等价.
    _dd = (float(d_deal) if hit_mem is None
           else max(float(d_deal), float(hit_mem)))
    # 受击中止
    if macro_queue and not frozen:
        if d_take > 80:
            macro_queue = []
            gate_frames = 0
            dec_name = None
            sc_reset_fn()
            return macro_queue, gate_frames, dec_name, None

        # R34中断: 对手攻击 + 我方硬直/移动 + 近距
        my_a = left.get("action", 0)
        opp_a = right.get("action", 0)
        if (300 <= opp_a < 600 and my_a < 100
                and my_a not in GUARD_ALL_IDS
                and abs(dx) < 300
                and dec_name not in GUARD_PREP_SET):
            macro_queue = []
            gate_frames = 0
            dec_name = None
            sc_reset_fn()
            return macro_queue, gate_frames, dec_name, None

        # 灵力门 — 裁定四A(2026-10-14用户裁定): 触发键从A/B/C收窄为
        # B/C — 近战A不耗灵力, 低灵时连带禁近战=残血没收最后手段
        # (人测被动性放大器, 审计从零#3推迟项); 清队语义保留(交还决策权)
        if macro_queue:
            _nk = macro_queue[0][0]
            if (not isinstance(_nk, str)
                    and any(b in _nk for b in ("B", "C"))
                    and spirit < 100):
                macro_queue = []
                gate_frames = 0
                dec_name = None
                sc_reset_fn()
                return macro_queue, gate_frames, dec_name, None

        # 推进
        if macro_queue:
            keys, fl = macro_queue[0]
            if isinstance(keys, str) and keys.startswith("sc:"):
                pop, abort, hold = sc_step_fn(left)
                if pop:
                    macro_queue.pop(0)
                    sc_reset_fn()
                elif abort:
                    macro_queue = []
                    dec_name = None
                    sc_reset_fn()
                return macro_queue, gate_frames, dec_name, hold

            elif isinstance(keys, str) and keys == "branch":
                # R61u(C1): 分支门 — 按游戏状态路由
                macro_queue.pop(0)
                branch_dict = fl  # fl stores the branch dict
                result = evaluate_branch(
                    branch_dict, left, right, _dd, d_take)
                if result is None:
                    # 截断(whiff默认)
                    # P1-4(从零#4): **保留dec_name** — 交还决策权的正常
                    # 截断仍要结算空挥(12个branch宏+confirm族的落空路径
                    # 原被清名豁免, W_WHIFF经济学对门宏失效)。受击中止/
                    # R34中断/SC中止才是豁免语义(那些路径继续清名)。
                    macro_queue = []
                    gate_frames = 0
                    sc_reset_fn()
                    return macro_queue, gate_frames, dec_name, None
                # delay_then: 门通过后延迟N帧
                if (isinstance(result, tuple)
                        and len(result) == 2
                        and isinstance(result[0], int)):
                    delay, steps = result
                    macro_queue = ([((), delay)] + list(steps)
                                   + macro_queue)
                else:
                    macro_queue = list(result) + macro_queue
                return macro_queue, gate_frames, dec_name, None

            elif isinstance(keys, str) and keys == "link":
                # R61v(C3): 目押门 — 等对手untech→0最速出招
                # fl = (max_wait, steps); gate_frames作为观察窗
                # BH-4.2: untech过动作门 — 自由行动的残留读数不再
                # 让link空等(等待期=真受击硬直)
                max_wait, steps = fl
                gate_frames += 1
                opp_untech = eff_untech(right)
                if opp_untech <= 0:
                    # 对手恢复完毕 → 最速出招
                    macro_queue.pop(0)
                    gate_frames = 0
                    macro_queue = list(steps) + macro_queue
                elif gate_frames >= max_wait:
                    # 超时 → 落空截断(对手已恢复但我们没跟上)
                    macro_queue = []
                    gate_frames = 0
                    dec_name = None
                    sc_reset_fn()
                return macro_queue, gate_frames, dec_name, None

            elif isinstance(keys, str) and keys == "pos_gate":
                # CE-3.4: 位置路由门 — 评估时机=confirm通过后的
                # 续段首帧(本步即续段首步). 截断保留dec_name
                # (P1-4语义: 正常截断仍结算; 受击/R34/SC才是豁免)
                macro_queue.pop(0)
                result = evaluate_position_gate(fl, left, right)
                if result is None:
                    macro_queue = []
                    gate_frames = 0
                    sc_reset_fn()
                    return macro_queue, gate_frames, dec_name, None
                macro_queue = list(result) + macro_queue
                return macro_queue, gate_frames, dec_name, None

            elif isinstance(keys, str) and keys == "ender":
                # R61w(C5): ender菜单 — 起手通过后策略选终结技
                # 清空队列+返回ender信号(调用方设掩码→策略在下一
                # 决策点从菜单中自主选择 — 复用B2事件掩码机制)
                macro_queue = []
                gate_frames = 0
                sc_reset_fn()
                # fl = list of valid ender macro indices
                # 调用方检查返回的inp == ("ender", indices)
                return macro_queue, gate_frames, dec_name, (
                    "ender", fl)

            elif isinstance(keys, str):
                # confirm/cconfirm 门(既有语义)
                gate_frames += 1
                if _dd > 0:
                    macro_queue.pop(0)
                    gate_frames = 0
                elif gate_frames >= 4:
                    near = abs(right.get("position.x", 0)
                               - left.get("position.x", 0)) < 300
                    if keys.startswith("cconfirm") and near:
                        macro_queue.pop(0)
                    else:
                        # P1-4(从零#4): confirm超时截断保留dec_name供
                        # 空挥结算(原清名=confirm族落空免费)
                        macro_queue = []
                    gate_frames = 0
                return macro_queue, gate_frames, dec_name, None

            else:
                # 按键步
                gate_frames = 0
                fl -= 1
                if fl <= 0:
                    macro_queue.pop(0)
                else:
                    macro_queue[0] = (keys, fl)
                # 构建输入
                inp = {}
                for k in keys:
                    if k == "right":
                        inp["H"] = 1
                    elif k == "left":
                        inp["H"] = -1
                    elif k == "up":
                        inp["V"] = -1
                    elif k == "down":
                        inp["V"] = 1
                    elif k in ("A", "B", "C", "D"):
                        inp[k] = True
                return macro_queue, gate_frames, dec_name, inp

    # 队列空或冻结
    return macro_queue, gate_frames, dec_name, None


def make_branch_step(branch_dict):
    """构造分支门步骤元组."""
    return ("branch", branch_dict)


def enqueue_script(queue, script):
    """脚本入队(单源) — P0-B(从零#2): 字符串步必须保留载荷fr
    (branch字典/link元组/ender列表都存在fr位), 键步转tuple。
    train_tm与side_driver共同调用(原train_tm侧(ks,0)丢载荷=
    训练/评估最大偏斜源)。"""
    for ks, fr in script:
        if isinstance(ks, str):
            queue.append((ks, fr))
        else:
            queue.append((tuple(ks), fr))
    return queue


# ---- 预制分支宏模板(供宏库追加用) ----

def mixup_branch_variants(char, macro_names):
    """为角色生成表里择分支宏(快/慢两版, 同一起手).

    返回: [(宏名, 脚本), ...] — 起手confirm通过后分支路由.
    """
    starter = [(("right", "D"), 6), ((), 2), (("A",), 8), ((), 2)]
    fast = [(("A",), 6)]          # 最速
    mid = [((), 3), (("A",), 6)]  # 3帧延迟
    slow = [((), 6), (("A",), 6)]  # 6帧延迟
    return [
        ("拍子·快", starter + [("confirm", 0)] + fast),
        ("拍子·中", starter + [("confirm", 0)] + mid),
        ("拍子·慢", starter + [("confirm", 0)] + slow),
    ]


def oki_branch(char):
    """压起身分支宏: 按对手起身行为路由.

    hit→追击, blocked→二择, whiff→截断, opp_jump→对空.
    """
    setup = [(("down", "A"), 12)]     # meaty 2A
    on_hit = [((), 2), (("A",), 8)]   # 命中→5A追击
    on_block = [((), 4), (("down", "A"), 10)]  # 被防→2A二择
    on_jump = [(("up",), 6), (("down",), 4), (("down", "A"), 12)]  # 对空
    return ("压起身·分支", setup + [
        make_branch_step({
            "hit": on_hit,
            "blocked": on_block,
            "opp_jump": on_jump,
            "whiff": None,   # 空挥→截断
        })
    ])


def make_link_step(max_wait, steps):
    """构造目押门步骤(C3): 等untech→0后最速出.

    max_wait: 最长等待帧数(超时截断)
    steps: untech→0后要执行的步骤列表
    """
    return ("link", (max_wait, list(steps)))


def just_frame_link(char, starter_steps, follow_up, max_wait=20):
    """目押连段宏(C3): 起手→link等恢复→最速追击.

    攻略核心: "目押=对手恢复瞬间命中=最大连段窗口"
    实现: 起手confirm通过→link门等untech→0→最速出追击
    max_wait=20帧(约0.32秒) — 超过说明对手已脱连.
    """
    return starter_steps + [
        ("confirm", 0),
        make_link_step(max_wait, follow_up),
    ]


# 目押预制: 5A→link→2A (基础目押确认连)
def just_frame_5a_2a(char='reimu'):
    """5A命中→等恢复→最速2A(目押基础)."""
    starter = [(("A",), 8)]
    follow = [(("down",), 5), (("down", "A"), 8)]
    return ("目押·5A2A", just_frame_link(char, starter, follow))


# 目押预制: 2A→link→5A (下段→中段目押)
def just_frame_2a_5a(char='reimu'):
    """2A命中→等恢复→最速5A(下中目押)."""
    starter = [(("down",), 5), (("down", "A"), 8)]
    follow = [(("A",), 8)]
    return ("目押·2A5A", just_frame_link(char, starter, follow))


# ===== C5: ender菜单系统 =====

def make_ender_step(ender_indices):
    """构造ender菜单步骤: 起手通过后策略从列表中选终结技.

    ender_indices: list[int] — 可选ender宏的索引列表
    (在宏库中的位置; 策略在下一决策点从这些宏中自主选择)
    """
    return ("ender", list(ender_indices))


def starter_ender_pair(starter_name, starter_steps, ender_names,
                        char_lib):
    """生成起手+ender菜单宏对.

    starter: 正常宏(confirm通过后→ender菜单)
    enders: 终结技宏(由策略选择, 不直接入策略动作空间—菜单驱动)
    返回: (starter_macro, [ender_macros]) — enders可从主宏库中
    选择已有宏(如连段A的终结步), 或创建新ender专宏.
    """
    names = char_lib['names']
    ender_idx = [names.index(n) for n in ender_names
                 if n in names]
    if not ender_idx:
        return None, []
    starter = (starter_name, starter_steps + [
        ("confirm", 0),
        make_ender_step(ender_idx)])
    enders = [(n, char_lib['macros'][i][1])
              for i, n in [(names.index(n), n)
                           for n in ender_names if n in names]]
    return starter, enders


def build_ender_menu(char_lib, starter_macros, ender_names):
    """为角色构建完整ender菜单系统.

    starter_macros: [(名称, 脚本), ...] — 起手宏定义
    ender_names: [str, ...] — 可用作ender的宏名列表
    返回: [(starter_name, script_with_ender), ...]
    """
    out = []
    for name, script in starter_macros:
        s, _ = starter_ender_pair(name, script, ender_names,
                                  char_lib)
        if s is not None:
            out.append(s)
    return out


# ===== CE-3.4: 位置路由门 =====

# R23贴角口径(train_tm二值角项/宏门共用; 1280=场地宽)
POS_GATE_THRESHOLD = 120.0


def make_pos_gate_step(corner_steps, mid_steps, dx_opp_hint=0.0,
                       threshold=POS_GATE_THRESHOLD):
    """构造位置路由门步骤(CE-3.4).

    corner_steps/mid_steps: 续段步骤列表(None=该路截断)
    dx_opp_hint: 命中桶推板外推(CE-3位移表dx_opp_hit; 0=不外推)
    threshold: 贴角判定px(默认120, R23口径)
    """
    return ("pos_gate", {
        "corner": (list(corner_steps)
                   if corner_steps is not None else None),
        "mid": (list(mid_steps) if mid_steps is not None else None),
        "dx_opp_hint": float(dx_opp_hint),
        "threshold": float(threshold),
    })


def adaptive_combo(starter_steps, corner_ender, mid_ender,
                   dx_opp_hint=0.0, threshold=POS_GATE_THRESHOLD):
    """位置自适应连段宏模板(CE-3.4).

    版中起手→confirm→贴角走版边收尾/否则走弹墙推板收尾 —
    攻略C5"同一命中确认因屏幕坐标不同有三套后续"在宏内表达.
    **宏库升版时经R23契约尾部追加**(与CH-3/JZ-4同批; 现库
    连段A/B/C与版边连A不动 — 合并式改造会移位既有索引).
    dx_opp_hint从CE-3位移表宏末攻击步取命中桶值(低置信记0).
    """
    return list(starter_steps) + [
        ("confirm", 0),
        make_pos_gate_step(corner_ender, mid_ender,
                           dx_opp_hint, threshold),
    ]
