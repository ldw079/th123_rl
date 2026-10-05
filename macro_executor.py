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
  ("branch", {cond: steps})   — **分支门(新)**: 按游戏状态路由

分支条件:
  "hit"        — 上一攻击命中(d_deal > 0) → 取该分支的步骤
  "blocked"    — 被防(d_deal == 0且对手在防御态) → 取该分支
  "whiff"      — 空挥(默认None=截断, 同confirm超时)
  "delay_then" — 放帧: (N, steps) = 门通过后延迟N帧再续(拍子择)
  "opp_jump"   — 对手空中(airBorne) → 该分支
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
