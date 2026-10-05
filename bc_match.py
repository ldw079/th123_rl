# -*- coding: utf-8 -*-
"""专家输入流 ↔ 宏库匹配器 v2: 第九轮审查§3重建 + R61g(B1)SC词汇。

三条根因修复:
1. 字符串步宏→前缀匹配: confirm/cconfirm门步之前的部分可离线展开,
   门后依赖游戏状态(hit/block/whiff)不可离线判定 → 只匹配前缀。
2. 贪心→决策点扫描: 只在输入变化帧(新按键/方向改变)处尝试起匹配,
   "按住右60帧"不再产生10个前进标签。
3. 降采样推广到四个低决策含量宏: 待机/前进/后退/立防。

R61g(B1, 主规划): sc:步从"结构性排除"改为**SC按键词汇**:
- 专家流(BattleInput)的AandB组合键经battle_to_trainer映射为SC位
  (input_codec:197) — 卡牌使用在输入流里是真实可观测的按键事件;
- expert_bits扩为8元组(+SC/SW位), macro_timelines把sc:步展开为
  规范SC按压时间线(3帧) — 所有SC宏共享同一按键形态(哪个卡由手牌
  状态决定, 不在按键流里), bc_build按对齐帧的手牌差分解析具体卡。
"""
from __future__ import annotations

import sys

sys.path.insert(0, r'D:\temp\soku_arch')
from soku_arch.input_codec import BattleInput, battle_to_trainer

KEY_TO_BIT = {
    "right": ("H", 1), "left": ("H", -1),
    "up": ("V", -1), "down": ("V", 1),
    "A": ("A", True), "B": ("B", True), "C": ("C", True), "D": ("D", True),
}

LOW_INFO = {'待机', '前进', '后退', '立防', '蹲防'}   # 低决策含量宏(降采样)

SC_PRESS_F = 3   # R61g: 规范SC按压时长(专家实测卡键按压2-6帧, 3为模板)


def keys_to_input(keys, mirror=False):
    inp = {}
    for k in keys:
        if k in KEY_TO_BIT:
            axis, val = KEY_TO_BIT[k]
            if axis in ("H", "V") and mirror:
                val = -val
            inp[axis] = val
    return inp


def inp_bits(inp):
    # R61g: 8元组(含SC/SW — 卡牌按键词汇)
    return (inp.get("H", 0), inp.get("V", 0),
            bool(inp.get("A")), bool(inp.get("B")),
            bool(inp.get("C")), bool(inp.get("D")),
            bool(inp.get("SC")), bool(inp.get("SW")))


def sc_press_bits():
    """R61g: sc:步的规范按键时间线(纯SC位×3帧)。"""
    base = (0, 0, False, False, False, False, True, False)
    return [base] * SC_PRESS_F


def expert_bits(u16):
    t, _ = battle_to_trainer(BattleInput(int(u16)))
    return inp_bits(t.as_dict())


def macro_timelines(macros, mirror):
    """每个宏展开为(前缀帧列表, 前缀长度, 名称, 是否完整可匹配)。
    含confirm/cconfirm的宏: 只展开门前步骤。
    R61g: sc:步展开为SC按压时间线(所有SC宏共享; 具体卡由bc_build
    按手牌差分后解析) — sc:步不再中断可匹配性。
    返回 [(prefix_bits|None, full_frames|None, name)]。"""
    out = []
    for name, script in macros:
        prefix = []
        full = []
        prefix_ok = True
        full_ok = True
        for ks, fr in script:
            if isinstance(ks, str):
                if ks.startswith("sc:"):
                    # R61g: SC按压(朝向无关 — 纯SC位)
                    frames = sc_press_bits()
                elif ks.startswith(("confirm", "cconfirm")):
                    # confirm/cconfirm: 前缀到此为止, 之后的不可离线展开
                    full_ok = False
                    break
                else:
                    prefix_ok = full_ok = False
                    break
                full.extend(frames)
                if full_ok:
                    prefix.extend(frames)
                continue
            inp = keys_to_input(tuple(ks), mirror)
            frames = [inp_bits(inp)] * int(fr)
            full.extend(frames)
            if full_ok:
                prefix.extend(frames)
        out.append((prefix if prefix_ok and prefix else None,
                    full if full_ok and full else None,
                    name))
    return out


class StreamMatcher:
    """v2: 决策点扫描匹配器。"""

    def __init__(self, macros, threshold=0.85):
        self.tl_facing = {}
        self.threshold = threshold
        self.macros = macros

    def timelines(self, mirror):
        if mirror not in self.tl_facing:
            self.tl_facing[mirror] = macro_timelines(self.macros, mirror)
        return self.tl_facing[mirror]

    def _best_at(self, frames, start, mirror):
        """在start处找最佳匹配: 优先完整宏(长且具体), 退而求前缀。"""
        best = (None, -1.0, 0, 'none')   # (idx, score, length, kind)
        for idx, (prefix, full, name) in enumerate(self.timelines(mirror)):
            for tl, kind in ((full, 'full'), (prefix, 'prefix')):
                if not tl or len(tl) < 3:
                    continue
                if start + len(tl) > len(frames):
                    continue
                hit = sum(1 for i in range(len(tl))
                          if frames[start + i] == tl[i])
                s = hit / len(tl)
                # 同分取更长(更具体的宏)
                if s > best[1] + 1e-9 or (abs(s - best[1]) < 1e-9
                                          and len(tl) > best[2]):
                    best = (idx, s, len(tl), kind)
        return best

    def _decision_points(self, frames):
        """输入变化帧(新决策): bits与前一帧不同的位置。"""
        if not frames:
            return []
        pts = [0]
        for i in range(1, len(frames)):
            if frames[i] != frames[i - 1]:
                pts.append(i)
        return pts

    def walk(self, expert_u16, facings, intro_frames=60):
        """产出 (帧号, 宏idx, 置信度)。"""
        frames = [expert_bits(u) for u in expert_u16]
        dp_set = set(self._decision_points(frames))
        out = []
        f = intro_frames
        n = len(frames)
        while f < n:
            # 跳到下一个决策点(输入变化帧)
            while f < n and f not in dp_set:
                f += 1
            if f >= n:
                break
            mirror = facings[f] < 0 if f < len(facings) else False
            idx, s, length, kind = self._best_at(frames, f, mirror)
            if idx is not None and s >= self.threshold and length >= 3:
                out.append((f, idx, s))
                f += length   # 跳过整个宏(到下一个决策点)
            else:
                f += 1        # 不匹配: 前进1(下个循环跳到决策点)
        return out
