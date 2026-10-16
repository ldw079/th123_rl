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

# 键→位映射。V极性约定(P1-G从零#2文档化): up=V:-1 / down=V:+1 —
# 与train_tm.keys_to_input及macro_executor按键步**同极性**(同名表
# 反义的复制陷阱: 各自内部都对, 改任一处必须三处同步)。
KEY_TO_BIT = {
    "right": ("H", 1), "left": ("H", -1),
    "up": ("V", -1), "down": ("V", 1),
    "A": ("A", True), "B": ("B", True), "C": ("C", True), "D": ("D", True),
}

# 低决策含量宏(降采样) — 审计后修订(2026-10-14): 立防/蹲防移出
# (格挡=高决策含量且高风险; 实测TR语料降采样前格挡族≈18%决策点,
# 原与待机同组砍到15% → 防御先验结构性缺失, 对应人测"拉防极弱")
LOW_INFO = {'待机', '前进', '后退'}

SC_PRESS_F = 3   # R61g: 规范SC按压时长(专家实测卡键按压2-6帧, 3为模板)


def keys_to_input(keys, mirror=False):
    """P1-G(从零#2): mirror只翻H轴 — 原连V(up/down)一起翻, 而专家流
    (BattleInput)从不翻V → 换边段的空中宏(up/down攻击)标签静默
    丢失/错配。格斗游戏镜像是左右翻转, 上下方向语义不变。"""
    inp = {}
    for k in keys:
        if k in KEY_TO_BIT:
            axis, val = KEY_TO_BIT[k]
            if axis == "H" and mirror:
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
    """v3(2026-10-14 A1-3③): 决策点扫描匹配器 — 掩码位+变长截断.

    v2根因(弹幕漏标): 逐帧精确相等 → 专家弹幕(3-8帧变长按压/带方向
    漂移/衔接连打)对"纯B键10帧"模板得分必然低于阈值 → 弹幕决策点
    整体丢弃(不产BC行)。实测TR语料B键按压率6-30%而弹幕标签仅1-2%。

    v3两条放宽(**其余与v2同严**):
    1. 掩码位比较 — 步骤仅含按钮(如5B的('B',)10帧)时H/V双wild
       (漂移弹幕可匹配); 交叉轴wild(含方向键步的另一轴); 未指定的
       按钮仍必False(5B不匹配B+C同按); 方向键步的指定轴必match。
    2. 变长截断匹配 — 每宏试L∈[3..min(全长,24)]∪{全长}, 取
       (得分, 更长)最优 — 5帧干净B按压以5B@L=5满分命中。

    mode='v2'保留旧路径(前后对比探针/回滚开关)。
    """

    # BH-4.1连段保持: 连段语境内抑制的中性移动标签(松键/微走位节奏)
    NEUTRAL_MOVE_NAMES = frozenset(('待机', '前进', '后退'))

    def __init__(self, macros, threshold=0.85, mode='v3',
                 attack_names=None):
        self.tl_facing = {}
        self.cons_facing = {}
        self.threshold = threshold
        self.macros = macros
        self.mode = mode
        # BH-4.1: 攻击/连段类宏索引集(连段语境重排用; None=语境功能关)
        self.attack_idx = (frozenset(i for i, (nm, _s) in enumerate(macros)
                                     if nm in attack_names)
                           if attack_names is not None else None)
        self._fams = {}     # 裁定一(类甲): 同前缀族(门后窥视用; 按朝向分套 P1-6)

    # ---- 裁定一(2026-10-14用户裁定): confirm门族门后窥视 ----
    LOOK_K = 24        # 门后窥视窗口
    LOOK_T = 0.75      # 延续匹配阈值(宽于主阈值: 时序受confirm等待影响)
    LEAD_SKIP = 12     # 门后前导中性容忍(TM·2a连门后()×9等待)

    @staticmethod
    def _enc_step(ks, fr, mirror):
        """单个键步→[(值,掩码)]×fr帧(continuation/constraints共用)."""
        inp = keys_to_input(tuple(ks), mirror)
        bits = inp_bits(inp)
        has_dir = any(k in ('right', 'left', 'up', 'down') for k in ks)
        has_btn = any(k in ('A', 'B', 'C', 'D') for k in ks)
        v = [bits[0] + 1, bits[1] + 1,
             int(bits[2]), int(bits[3]), int(bits[4]),
             int(bits[5]), int(bits[6]), int(bits[7])]
        if has_dir:
            m = [1 if ('right' in ks or 'left' in ks) else 0,
                 1 if ('up' in ks or 'down' in ks) else 0,
                 1, 1, 1, 1, 1, 1]
        elif has_btn:
            m = [0, 0, 1, 1, 1, 1, 1, 1]
        else:
            m = [1, 1, 1, 1, 1, 1, 1, 1]
        return [(tuple(v), tuple(m))] * int(fr)

    def _script_continuation(self, script, mirror):
        """门后延续约束: 首个门(confirm/cconfirm/branch)之后的输入帧
        (≤32帧, 遇下一个门步截断)。无门步→None(基础宏)。
        branch门(2026-10-14线A): 延续=hit路由(专家流命中路线的输入
        证据; blocked/opp_jump路由输入不同, lookahead按实际输入归属)。"""
        import numpy as np
        seen_gate = False
        frames = []
        for ks, fr in script:
            if isinstance(ks, str):
                if ks.startswith(('confirm', 'cconfirm')):
                    if seen_gate:
                        break           # 第二个门: 截断
                    seen_gate = True
                    continue
                if ks == 'branch':
                    if seen_gate:
                        break
                    seen_gate = True
                    if isinstance(fr, dict) and fr.get('hit'):
                        for hk, hf in fr['hit']:
                            if isinstance(hk, str):
                                break
                            frames.extend(self._enc_step(hk, hf, mirror))
                            if len(frames) >= 32:
                                frames = frames[:32]
                                break
                    continue
                if ks.startswith('sc:'):
                    if not seen_gate:
                        continue
                    v = (1, 1, 0, 0, 0, 0, 1, 0)
                    m = (1, 1, 1, 1, 1, 1, 1, 1)
                    frames.extend([(v, m)] * int(SC_PRESS_F))
                    continue
                break
            if not seen_gate:
                continue
            frames.extend(self._enc_step(ks, fr, mirror))
            if len(frames) >= 32:
                frames = frames[:32]
                break
        if not seen_gate or not frames:
            return None
        return (np.array([f[0] for f in frames], dtype=np.int8),
                np.array([f[1] for f in frames], dtype=bool))

    def families(self, mirror=False):
        """同前缀族表(裁定一·类甲门后窥视用) — **按朝向分套缓存**。

        P1-6(从零#4): 原版continuation硬编码mirror=False且单套缓存 —
        左朝向段(facings<0用mirror=True约束)查到的是右朝向延续,
        带方向门后延续系统性错标(正确镜像方向无法确认/错误方向反而
        确认)。现按mirror缓存两套, continuation用同mirror生成
        (与walk的tl_facing/cons_facing同拍)。

        同前缀族(裁定一类甲): 主变体约束互为前缀(含全等)的宏族
        +各自门后延续约束。

        覆盖两种构型: 全等前缀(连段A/B/C=[A4,()2]×4)与包含前缀
        (5A=[A10] ⊂ 5A确认前缀[A10,()2]; 2A⊂2A确认)。
        返回 {成员idx: (族成员idx列表, {idx: (cont_val,cont_mask)|None})};
        基础宏(无门步)延续=None — 门未确认时的回落标签。
        """
        if mirror in self._fams:
            return self._fams[mirror]
        cons = self.constraints(False)
        prim = {}
        for idx, variants in enumerate(cons):
            if variants is None:
                continue
            prim[idx] = (variants[0][0], variants[0][1])
        # 前缀包含归族(双向): A⊆B或B⊆A皆同族 — 覆盖全等前缀
        # (连段A/B/C)与包含前缀(5A⊂5A确认)及无门同形竞争者
        # (原子·地面链的A串⊂连段族前缀竞赛)
        def _pref(i, j):
            vi, mi_ = prim[i]
            vj, mj = prim[j]
            if len(vi) > len(vj):
                vi, vj = vj, vi
                mi_, mj = mj, mi_
            return (vj[:len(vi)] == vi).all() and (mj[:len(mi_)] == mi_).all()
        fams = []                     # [set(idx)]
        for i in sorted(prim, key=lambda k: len(prim[k][0])):
            joined = False
            for f in fams:
                if any(_pref(i, j) for j in f):
                    f.add(i)
                    joined = True
                    break
            if not joined:
                fams.append({i})
        fam = {}
        for members in fams:
            if len(members) < 2:
                continue
            conts = {}
            for mi in members:
                conts[mi] = self._script_continuation(
                    self.macros[mi][1], mirror)
            if not any(c is not None for c in conts.values()):
                continue   # 纯同形族(空防/后跳等): 无门可窥, 不注册
            # 每成员延续的锚=自身前缀长度(非赢家匹配长度)
            info = {mi: (conts[mi], len(prim[mi][0])) for mi in members}
            for mi in members:
                fam[mi] = (sorted(members), info)
        self._fams[mirror] = fam
        return fam

    def timelines(self, mirror):
        if mirror not in self.tl_facing:
            self.tl_facing[mirror] = macro_timelines(self.macros, mirror)
        return self.tl_facing[mirror]

    # ---- v3: 掩码约束构建与向量化匹配 ----
    @staticmethod
    def _enc_bits(b8):
        """8元组bits → int8[8]: (H+1, V+1, A,B,C,D,SC,SW)."""
        return (b8[0] + 1, b8[1] + 1,
                int(b8[2]), int(b8[3]), int(b8[4]), int(b8[5]),
                int(b8[6]), int(b8[7]))

    def constraints(self, mirror):
        """每宏 → (req_val int8[L,8], req_mask bool[L,8], generic_head int).

        掩码规则(只放宽漂移场景):
        - 帧掩码1=必match/0=wild; 按钮步(无方向键)的帧 → H/V双wild;
          含方向键步的帧 → 指定轴约束, 交叉轴wild; 空键步=全约束真中性。
        generic_head(P1修复, 审计2026-10-14): 含特色步(按钮/SC)的宏,
        其无按钮前导帧数 — 匹配侧禁止仅凭通用头部段claim(否则
        压起身·延迟用()×8前缀骗过待机、起身穿用right×10吃掉前进);
        纯通用宏(前进/待机/立防等)head=0不受限。
        dist(P1续): 每帧是否特色(按钮/SC)。混合宏的截断L必须落在
        特色帧上或等于全长 — 否则原子·收尾@L=16(落中性帧)凭rd前缀
        +中性尾巴吃掉前冲; 5B@L=5(落B帧)合法保留。
        """
        import numpy as np
        if mirror in self.cons_facing:
            return self.cons_facing[mirror]
        out = []
        # 重走一遍脚本展开, 同macro_timelines逻辑但产出约束帧
        for name, script in self.macros:
            frames = []
            dist = []
            ok = True
            has_distinctive = False
            generic_head = 0
            head_done = False
            for ks, fr in script:
                if isinstance(ks, str):
                    if ks.startswith('sc:'):
                        # SC规范按压帧: SC位必True, 其余位必False(同v2)
                        # 值域=编码空间(H+1/V+1, 中性=1)
                        v = (1, 1, 0, 0, 0, 0, 1, 0)
                        m = (1, 1, 1, 1, 1, 1, 1, 1)
                        frames.extend([(v, m)] * int(SC_PRESS_F))
                        dist.extend([True] * int(SC_PRESS_F))
                        has_distinctive = True
                        head_done = True
                        continue
                    elif ks.startswith(('confirm', 'cconfirm',
                                        'link', 'ender')):
                        # 门步: 到此为止(前缀可离线展开, 门后不可) — 同v2
                        # (link/ender: 分支门方案线A同族门步)
                        break
                    elif ks == 'branch':
                        # 分支门启用(2026-10-14线A): 门后为路由dict,
                        # 匹配语义=前缀+hit路延续(裁定一门后窥视同构)
                        break
                    else:
                        ok = False
                        break
                inp = keys_to_input(tuple(ks), mirror)
                bits = inp_bits(inp)
                has_dir = any(k in ('right', 'left', 'up', 'down')
                              for k in ks)
                has_btn = any(k in ('A', 'B', 'C', 'D')
                              for k in ks)
                if has_btn:
                    has_distinctive = True
                    head_done = True
                elif not head_done:
                    generic_head += int(fr)
                v = [bits[0] + 1, bits[1] + 1,
                     int(bits[2]), int(bits[3]), int(bits[4]),
                     int(bits[5]), int(bits[6]), int(bits[7])]
                if has_dir:
                    # P0修复(审计2026-10-14): 掩码约定1=必match/0=wild —
                    # 指定轴=1(约束), 交叉轴=0(wild)。原版极性反转:
                    # 指定轴给了wild → 前进/后退不可分、后跳双轴全wild
                    # 成万能吞噬器(动态实测: 待机→跳跃/左右移→后跳)。
                    m = [1 if ('right' in ks or 'left' in ks) else 0,
                         1 if ('up' in ks or 'down' in ks) else 0,
                         1, 1, 1, 1, 1, 1]
                elif has_btn:
                    # 纯按钮步: H/V双wild(漂移弹幕), 按钮位全必match
                    m = [0, 0, 1, 1, 1, 1, 1, 1]
                else:
                    # 空键步(显式中性): H=0/V=0必match — 否则待机会
                    # 以"最长宏"吞掉立防/后退/前进等全部地面方向保持
                    m = [1, 1, 1, 1, 1, 1, 1, 1]
                frames.extend([(tuple(v), tuple(m))] * int(fr))
                dist.extend([has_btn] * int(fr))
            if not ok or not frames:
                out.append(None)
                continue
            req_val = np.array([f[0] for f in frames], dtype=np.int8)
            req_mask = np.array([f[1] for f in frames], dtype=bool)
            dist_arr = np.array(dist, dtype=bool)
            head = generic_head if has_distinctive else 0
            variants = [(req_val, req_mask, head,
                         bool(has_distinctive), dist_arr)]
            if head > 0:
                # P1升级(审计2026-10-14续②): 可选预压前缀 — 专家常
                # 同帧按压(方向+B同时, 无6帧预压), 完整时间线对同帧
                # 输入只有~0.63分被拒, 纯按钮宏(轴wild)以1.00错吞
                # (2B同帧→5B)。跳过预压段变体: 从特色步起匹配; 预压
                # 真存在时完整版凭更长自然胜出, 同帧时变体接管。
                variants.append((req_val[head:], req_mask[head:], 0,
                                 True, dist_arr[head:]))
            out.append(variants)
        self.cons_facing[mirror] = out
        return out

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

    def walk(self, expert_u16, facings, intro_frames=60, combo_ctx=None):
        """产出 (帧号, 宏idx, 置信度)。mode='v2'走旧逐帧精确路径.

        BH-4.1: combo_ctx=逐帧bool(对手真受击∧近距, 调用方从游戏状态
        计算) — 连段语境下攻击/连段类宏(attack_idx)启用按钮帧评分
        (见_match_all_dp), 压碎片被标成移动/待机的份额(H1病灶)。"""
        if self.mode == 'v2':
            return self._walk_v2(expert_u16, facings, intro_frames)
        import numpy as np
        frames = np.array([self._enc_bits(expert_bits(u))
                           for u in expert_u16], dtype=np.int8)
        if len(frames) == 0:
            return []
        # 决策点(输入变化帧) + 朝向分组
        change = np.any(frames[1:] != frames[:-1], axis=1)
        dp_all = np.concatenate([[0], np.where(change)[0] + 1])
        dp_all = dp_all[dp_all >= intro_frames]
        out = []
        for mirror in (False, True):
            dp = dp_all[[i for i, f in enumerate(dp_all)
                         if (facings[f] < 0 if f < len(facings)
                             else False) == mirror]]
            if not len(dp):
                continue
            ctx = None
            if combo_ctx is not None and self.attack_idx is not None:
                _c = np.asarray(combo_ctx, dtype=bool)
                ctx = _c[dp] if len(_c) >= (int(dp.max()) + 1
                                            if len(dp) else 1) else None
            idxs, scores, lens = self._match_all_dp(frames, dp, mirror,
                                                    combo_dp=ctx)
            for f, idx, s, L in zip(dp.tolist(), idxs.tolist(),
                                    scores.tolist(), lens.tolist()):
                if idx >= 0 and s >= self.threshold and L >= 3:
                    out.append((f, idx, float(s), int(L), mirror))
        # 顺序贪心消费(等价v2语义): 命中后跳过宏长度内的后续决策点
        out.sort(key=lambda h: h[0])
        consumed = []
        next_free = 0
        # BH-4.1连段保持: 语境帧级数组(消费段用)
        _cfull = (np.asarray(combo_ctx, dtype=bool)
                  if combo_ctx is not None and self.attack_idx is not None
                  else None)
        # P1-6续修: 族表按**每个命中的朝向**取套 — 原:families(循环尾
        # 残留mirror)对纯右朝向输入错取True套(旧单套缓存时代此泄漏
        # 不可见, 分套后暴露, 首版P1-6修法自身引入, 本行为定版)
        _fams = {False: self.families(False), True: self.families(True)}
        for f, idx, s, L, m in out:
            fam = _fams[m]
            if f < next_free:
                continue
            # BH-4.1连段保持: 连段语境内的中性移动标签抑制 — 对手真
            # 受击近距时, 松键/微走位是连段节奏不是决策, 不教锚"等待/
            # 走位"(待机×622/前进×329/后退×104为H1实测大头); 不消费,
            # 让后续攻击按压的标签接管
            if (_cfull is not None and f < len(_cfull) and _cfull[f]
                    and self.macros[idx][0]
                    in self.NEUTRAL_MOVE_NAMES):
                continue
            next_free = f + L
            if idx in fam:
                idx2, extra = self._lookahead(frames, f, L, fam[idx])
                if idx2 is None:
                    continue          # 门未确认且无基础宏 — 丢弃(裁定一)
                idx = idx2
                next_free = f + L + extra   # 延续帧由确认宏消费(防二次标注)
            consumed.append((f, idx, s))
        return consumed

    def _lookahead(self, frames, hit_f, hit_L, fam_entry):
        """裁定一(类甲)门后窥视: 前缀命中后按门后实际输入重归属.

        每成员延续从**自身前缀末端**锚定(hit_f+成员前缀长), 而非
        赢家匹配长度末端 — 连段B延续与原子·地面链的A串部分重叠,
        各自对齐才能正确评分。
        返回(重归属宏idx, 消费延伸长度); 门未确认→(基础宏,0)或
        (None,0)。确认判据: 延续匹配须覆盖到首个按钮帧。
        """
        import numpy as np
        members, info = fam_entry
        n = len(frames)
        best = (None, -1.0, 0, 0)     # (idx, score, L, anchor)
        for mi, (cont, plen) in info.items():
            if cont is None:
                continue              # 基础宏: 不参与延续评分
            cv, cm = cont
            btn_pos = None
            for i in range(len(cv)):
                if any(cm[i][k] and cv[i][k] for k in range(2, 8)):
                    btn_pos = i
                    break
            if btn_pos is None:
                continue              # 延续无按钮帧: 无法确认
            L_min = btn_pos + 1
            anchor = hit_f + plen     # 该成员自身前缀末端
            for off in range(0, self.LEAD_SKIP + 1):
                st = anchor + off
                for L in range(max(3, L_min),
                               min(len(cv), self.LOOK_K) + 1):
                    if st + L > n:
                        break
                    win = frames[st:st + L]
                    sat = ((win == cv[:L]) | ~cm[:L]).all(axis=1)
                    sc = float(sat.mean())
                    if sc > best[1] + 1e-9 or (abs(sc - best[1]) < 1e-9
                                               and L > best[2]):
                        best = (mi, sc, L, anchor + off)
                if best[1] >= self.LOOK_T:
                    break              # 已过阈值, 不再放宽偏移
        if best[1] >= self.LOOK_T:
            # 消费延伸到该成员前缀+匹配延续(不早于赢家已消费长度)
            return best[0], max(0, best[3] + best[2] - (hit_f + hit_L))
        # 门未确认: 回落基础宏(如2A族的裸2A); 无基础宏→丢弃
        for mi, (cont, _plen) in info.items():
            if cont is None:
                return mi, 0
        return None, 0

    @staticmethod
    def _cand_lens(L_full):
        ls = list(range(3, min(L_full, 24) + 1))
        if L_full > 24:
            ls.append(L_full)
        return ls

    def _match_all_dp(self, frames, dp, mirror, combo_dp=None):
        """全部决策点向量化: 每点最优(宏idx, 得分, 长度).

        平局裁决(P1修复, 审计2026-10-14): 得分 → 长度 → 约束密度。
        长度优先(完整更长的时间线=更多确认帧, 如空防@18应胜后跳@12);
        密度仅破剩余平局。另: 含特色步的宏禁用通用头部段claim
        (generic_head), 否则中性/方向前缀宏系统性夺标。

        BH-4.1(连段语境): combo_dp为真的决策点上, 攻击/连段类宏
        (attack_idx)额外计**按钮帧评分** s_btn = 宏要求按钮按下的帧
        上6按钮列全对的比例(微走位帧不计 — 连段中走位是噪声, 按钮
        序列才是意图, H1碎片化标注的病灶修法)。s_eff=max(s, s_btn)
        参与排序与walk的阈值裁决; 非攻击宏与语境外决策点逐位不变。
        """

        import numpy as np
        n = len(frames)
        res_idx = np.full(len(dp), -1, dtype=np.int64)
        res_s = np.zeros(len(dp), dtype=np.float64)
        res_spec = np.zeros(len(dp), dtype=np.float64)
        res_L = np.zeros(len(dp), dtype=np.int64)
        res_vr = np.zeros(len(dp), dtype=np.int64)
        ar = np.arange
        has_ctx = combo_dp is not None and self.attack_idx is not None
        for idx, variants in enumerate(self.constraints(mirror)):
            if variants is None:
                continue
            _atk = has_ctx and idx in self.attack_idx
            for vr, (req_val, req_mask, head, mixed, dist) \
                    in enumerate(variants):
                for L in self._cand_lens(len(req_val)):
                    if L <= head:
                        continue    # 通用前缀claim禁止(P1)
                    if mixed and L < len(req_val) and not dist[L - 1]:
                        continue    # 混合宏截断须落在特色帧(防尾部通用帧)
                    ok = dp + L <= n
                    dpo = dp[ok]
                    if not len(dpo):
                        break
                    win = frames[dpo[:, None] + ar(L)]      # (m,L,8)
                    sat = ((win == req_val[:L])
                           | ~req_mask[:L]).all(axis=2)
                    s = sat.mean(axis=1)
                    if _atk and combo_dp[ok].any():
                        # BH-4.1: 按钮帧评分(仅语境位为真的决策点取max)
                        btn_req = (req_val[:L, 2:8] == 1).any(axis=1)
                        nb = int(btn_req.sum())
                        if nb >= 2:
                            satb = ((win[:, :, 2:8] == req_val[:L, 2:8])
                                    | ~req_mask[:L, 2:8]).all(axis=2)
                            s_btn = ((satb & btn_req).sum(axis=1)
                                     / float(nb))
                            s = np.where(combo_dp[ok], np.maximum(s, s_btn),
                                         s)
                        # 近平局翻转: 语境内攻击类+0.04(战胜0.9x的
                        # 移动模板 — 走位碎片在连段中是噪声不是意图)
                        s = np.where(combo_dp[ok],
                                     np.minimum(s + 0.04, 1.0), s)
                    spec = float(req_mask[:L].sum()) / L    # 约束密度
                    cur = res_s[ok]
                    cur_L = res_L[ok]
                    cur_sp = res_spec[ok]
                    cur_vr = res_vr[ok]
                    upd = (s > cur + 1e-9) | \
                          ((np.abs(s - cur) < 1e-9) & (L > cur_L)) | \
                          ((np.abs(s - cur) < 1e-9) & (L == cur_L)
                           & (spec > cur_sp + 1e-9)) | \
                          ((np.abs(s - cur) < 1e-9) & (L == cur_L)
                           & (np.abs(spec - cur_sp) < 1e-9)
                           & (vr < cur_vr))
                    iok = np.where(ok)[0][upd]
                    res_idx[iok] = idx
                    res_s[iok] = s[upd]
                    res_L[iok] = L
                    res_spec[iok] = spec
                    res_vr[iok] = vr
        return res_idx, res_s, res_L

    def _walk_v2(self, expert_u16, facings, intro_frames=60):
        """v2旧路径(逐帧精确+定长) — 前后对比/回滚用."""
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
