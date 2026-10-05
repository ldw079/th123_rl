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
GUARD_STUN_IDS = frozenset(range(150, 167)) - {158}


def evaluate_branch(branch_dict, left, right, d_deal, d_take):
    """评估分支门 → 返回应执行的步骤列表(或None=截断).

    branch_dict: {"hit": [...], "blocked": [...], "whiff": None, ...}
    left/right: 当前帧玩家状态dict
    d_deal: 自上次检查以来造成的伤害量
    d_take: 自上次检查以来承受的伤害量
    """
    if d_deal > 0:
        return branch_dict.get("hit")
    opp_a = right.get("action", 0)
    if opp_a in GUARD_STUN_IDS:
        return branch_dict.get("blocked")
    if right.get("airBorne", False):
        return branch_dict.get("opp_jump")
    # 默认: whiff (None=截断)
    return branch_dict.get("whiff")


def advance_queue(macro_queue, gate_frames, left, right, d_deal, d_take,
                  frozen, spirit, dx, dec_name, GUARD_PREP_SET,
                  GUARD_ALL_IDS, sc_step_fn, sc_reset_fn):
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

        # 灵力门
        if macro_queue:
            _nk = macro_queue[0][0]
            if (not isinstance(_nk, str)
                    and any(b in _nk for b in ("A", "B", "C"))
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
                    branch_dict, left, right, d_deal, d_take)
                if result is None:
                    # 截断(whiff默认)
                    macro_queue = []
                    gate_frames = 0
                    dec_name = None
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
                max_wait, steps = fl
                gate_frames += 1
                opp_untech = right.get("untech", 0) or 0
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
                if d_deal > 0:
                    macro_queue.pop(0)
                    gate_frames = 0
                elif gate_frames >= 4:
                    near = abs(right.get("position.x", 0)
                               - left.get("position.x", 0)) < 300
                    if keys.startswith("cconfirm") and near:
                        macro_queue.pop(0)
                    else:
                        macro_queue = []
                        dec_name = None
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
