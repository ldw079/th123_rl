# -*- coding: utf-8 -*-
"""共享单侧推理驱动 + 胜者记录环境 — outer_loop(评估)与train_tm(自对弈学习半环)
共用。从outer_loop.py v1原样抽取(2026-09-22), 逻辑与训练侧同构。

依赖train_tm(CHAR_LIBS/keys_to_input) — 因此train_tm侧必须**懒加载**本模块
(方法内import), 避免循环导入。
注: sc符卡宏已接入(掩码门控+sc:状态机, R16起 — 旧注释"掩死"作废);
镜像规则: mirror = 朝向<0(P1/P2通用)。
"""
import os
import sys

# R61u(C1): 统一宏执行器(与train_tm共同调用 — 双拷贝终结)
import macro_executor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from feat_builder import FeatureBuilder  # noqa: E402
from opp_model import GUARD_ALL_IDS  # noqa: E402 (R34中断判定 — 第九轮审计P0-2: 原遗漏导入, 对手攻击+我方硬直时NameError炸局)
from ppo import PPOTrainer  # noqa: E402
from soku_client2 import GameEnded  # noqa: E402
from tm_env import TMEnv  # noqa: E402
from train_tm import (CHAR_LIBS, keys_to_input, _parse_sc_targets)  # noqa: E402


class EvalEnv(TMEnv):
    """记录GameEnded胜者的TMEnv(父类step吞掉该信息)。"""
    last_match = None

    def _spawn(self, first=False):
        super()._spawn(first)
        _self = self
        _orig = self.inst.recv_frame

        def _rec(timeout=2.0):
            try:
                return _orig(timeout)
            except GameEnded as e:
                _self.last_match = (e.winner, e.ls, e.rs)
                raise
        self.inst.recv_frame = _rec


class SideDriver:
    """单侧推理驱动(outer_loop评估与train_tm自对弈对手共用)。
    R16对齐: 符卡状态机从train_tm逐字移植(sc宏不再掩死 — 实测掩死让
    评估玩家弱到连Easy COM都输, 战报系统性低估); 采样温度跟随模型meta
    的退火温度(评估=训练行为策略)。"""

    def __init__(self, char, side, com_difficulty=None):
        lib = CHAR_LIBS[char]
        self.char = char
        self.side = side
        self.macros = lib["macros"]
        self.n_macros = len(self.macros)
        self.sc_names = lib["sc"]
        self.names = [m[0] for m in self.macros]
        self.base_mask = np.array(
            [m[0] not in self.sc_names for m in self.macros], dtype=bool)
        # R16: 符卡状态机(与train_tm同源)
        self.sc_cost_table = lib["sc_cost"]
        self.sc_targets = _parse_sc_targets(self.macros)
        self._sc_name_idx = {m[0]: i for i, m in enumerate(self.macros)}
        self._sc_run = None         # 状态机运行态
        self._sc_tgt = None         # 当前sc步目标
        self._sc_next_input = {}    # 下一帧要发的键(SW/SC)
        self._skill_levels = [0, 0, 0, 0]  # R17②: 技能等级(默认Lv1)
        _btn = {"A", "B", "C"}
        self.dir_attack = np.array([
            any((("right" in ks) or ("left" in ks)) and (_btn & set(ks))
                for ks, _ in m[1] if not isinstance(ks, str))
            for m in self.macros], dtype=bool)
        self.melee_idx = np.array(
            [n in lib["attack"] for n in self.names], dtype=bool)
        self.bullet_idx = np.array(
            [n in lib["bullet"] for n in self.names], dtype=bool)
        # R60(F-9): 类级330门近战子集(melee∪combo∪string; 技能/弹幕放行,
        # 射程由R24逐宏reach门精管) — 与train_tm同源
        _near = (lib.get("melee", set()) | lib.get("combo", set())
                 | lib.get("string", set()))
        self.near_idx = np.array([n in _near for n in self.names],
                                 dtype=bool)
        # R23: 位置特化连段门控(与train_tm同源)
        self.corner_combo_idx = np.array(["版边" in n for n in self.names],
                                         dtype=bool)
        # R39(第十轮§4-8): 空连门精确名(同train_tm — 子串误伤跳入链)
        self.air_combo_idx = np.array([n == "空连A" for n in self.names],
                                      dtype=bool)
        # R24: 射程(与train_tm同源) + 侧向量布局
        # [宏N][上宏N][core][gap_x N][gap_y N][untech N](R25/R30)
        # R28: 门控仅限攻击集(受身等utility宏不门)
        from reach_maps import (resolve_reach, resolve_startup,
                                REACH_MARGIN)
        self.macro_reach, self.macro_reach_v = resolve_reach(
            lib["macros"], char)
        _atk_idx = np.array([n in lib["attack"] for n in self.names],
                            dtype=bool)
        self.reach_mask_idx = (self.macro_reach > 0) & _atk_idx
        self.reach_v_mask_idx = (self.macro_reach_v > 0) & _atk_idx
        self.macro_startup = resolve_startup(lib["macros"], char)
        self.startup_mask_idx = self.macro_startup > 0
        self._reach_margin = REACH_MARGIN
        self.n_side = 5 * self.n_macros + FeatureBuilder.CORE_DIMS
        self.ppo = PPOTrainer(n_side=self.n_side, n_out=self.n_macros)
        self.feat_builder = FeatureBuilder(self.n_macros)
        self.feat_builder._char_name = char   # R19: 技能等级查表(原恒0)
        self.opp_char_id = None   # R19: 对手角色注入(池序0/1/2, 由外部wire)
        self._opp_vx_ema_f = 0.0  # R19: 对手速度逐帧EMA(时基同train_tm,
        self._opp_x_prev_f = None  # 原逐决策差分≈10×大, 干扰冲刺判定)
        self.decisions = 0     # 全match累计(reset_match不清)
        self.reset_match()

    def load(self, pi_path):
        self.ppo.load(pi_path, pi_path.replace(".npz", "") + "_v.npz"
                      if pi_path.endswith(".npz") else pi_path + "_v")

    def reset_match(self):
        self.feat_hist = []
        self.macro_queue = []
        self.last_macro = 0
        self.last_macro2 = 0
        self._dir_frames = 0
        self._last_dir = 1
        self._last_inp = {}      # P2-7同款: 门步保持上一拍输入(第六轮审计§4)
        self.gate_frames = 0
        self.hp_opp_prev = 10000
        self.hp_own_prev = 10000
        self._opp_x_prev_f = None   # R19: 逐帧EMA基准
        self._opp_vx_ema_f = 0.0
        self.feat_builder.reset_match()
        self._sc_reset()   # R16: 符卡状态机随局复位(训练同款)

    def _push_frame(self, own, opp, objs):
        """R19(审查2026-10-02): 逐帧压栈(5帧) — 与train_tm._push_frame同构。
        原版只在决策拍压1帧且返回3张原始帧(无差分) — P2/eval的conv输入
        全部落在训练分布之外。"""
        img = self._render_frame(own, opp, objs)
        self.feat_hist.append(img.ravel())
        if len(self.feat_hist) > 5:
            self.feat_hist.pop(0)

    def _visual_feat(self):
        """运动感知栈[当前帧, Δ1, Δ2] — 与train_tm._visual_feat逐字同构。"""
        if len(self.feat_hist) < 3:
            return None
        f0, f1, f2 = self.feat_hist[-3], self.feat_hist[-2], self.feat_hist[-1]
        d1 = np.clip(f2.astype(np.int16) - f1.astype(np.int16),
                     0, 255).astype(np.uint8)
        d2 = np.clip(f1.astype(np.int16) - f0.astype(np.int16),
                     0, 255).astype(np.uint8)
        return np.concatenate([f2, d1, d2])

    # ---- 视觉(与train_tm._render_frame逐字同步) ----
    def _render_frame(self, own, opp, objs):
        img = np.zeros((60, 80), dtype=np.uint8)
        cx = int(np.clip(own["position.x"] / 16.0, 0, 79))
        cy = int(np.clip((600.0 - own["position.y"]) / 16.0, 0, 59))
        img[cy, cx] = 255
        ox = int(np.clip(opp["position.x"] / 16.0, 0, 79))
        oy = int(np.clip((600.0 - opp["position.y"]) / 16.0, 0, 59))
        img[oy, ox] = 180
        for o in objs[:48]:
            bx = int(np.clip(o[1] / 16.0, 0, 79))
            by = int(np.clip((600.0 - o[2]) / 16.0, 0, 59))
            v = 96 + (o[6] & 0x3F)
            if img[by, bx] < 90:
                img[by, bx] = v
        return img

    def _side_feat(self, own, opp, weather, bullets):
        core = self.feat_builder.build(own, opp, weather, bullets)
        core[33] = min(self._dir_frames, 62) / 62.0
        # R19: 对手角色注入 — R61t(F5): 前12走段11, 后8走扩展区
        _oid = getattr(self, 'opp_char_id', None)
        if _oid is not None:
            if _oid <= 19:
                assert _oid in (0, 1, 2) or 11 <= _oid <= 19, \
                    "对手池序非法槽位: %r" % _oid
                core[227 + _oid] = 1.0
            else:
                # 扩展区(core[308+i], R61t F5)
                core[308 + (_oid - 20)] = 1.0
        s = np.zeros(self.n_side, dtype=np.float32)
        s[self.last_macro] = 1.0
        s[self.n_macros + self.last_macro2] = 1.0
        s[2 * self.n_macros:2 * self.n_macros
          + self.feat_builder.CORE_DIMS] = core
        # R24/R25: 射程差特征块(二维, 与train_tm同构)
        _adx = abs(opp["position.x"] - own["position.x"])
        _ady = abs(opp["position.y"] - own["position.y"])
        _b0 = 2 * self.n_macros + self.feat_builder.CORE_DIMS
        s[_b0:_b0 + self.n_macros] = \
            np.clip((_adx - self.macro_reach) / 200.0, -1, 1) \
            * self.reach_mask_idx
        s[_b0 + self.n_macros:_b0 + 2 * self.n_macros] = \
            np.clip((_ady - self.macro_reach_v) / 200.0, -1, 1) \
            * self.reach_v_mask_idx
        # R30: untech差值块(与train_tm同构)
        _opp_ut = opp.get("untech", 0) or 0
        s[_b0 + 2 * self.n_macros:] = \
            np.clip((_opp_ut - self.macro_startup) / 50.0, -1, 1) \
            * self.startup_mask_idx
        return s

    def decide(self, own, opp, weather, objs, bullets):
        """队列空时决策+入队(与训练决策点同构; 无探索偏置; sc门控在位)。
        R19(审查2026-10-02): 视觉=差分栈(同train_tm._visual_feat)、
        对手vx=逐帧EMA — 原版3张原始帧+逐决策差分, P2输入分布外。"""
        feat = self._visual_feat()
        if feat is None:
            return
        self.feat_builder.update_opp(10 / 62, own, opp, weather,
                                     opp_vx=self._opp_vx_ema_f)
        side = self._side_feat(own, opp, weather, bullets)
        mask = self.base_mask.copy() | self._sc_usable_mask(own)
        back_turned = ((1 if own["direction"] > 0 else -1) > 0) != \
                      (opp["position.x"] > own["position.x"])
        dx_abs = abs(opp["position.x"] - own["position.x"])
        if back_turned:
            mask = mask & ~self.dir_attack
        if dx_abs > 330:
            # R60(F-9): 只禁近战子集(与train_tm同源; 原全攻击集 → 330外
            # 弹幕/技能全禁=远程立回不可学)
            mask = mask & ~self.near_idx
        elif dx_abs < 150:
            mask = mask & ~self.bullet_idx
        # R23: 位置特化连段门控(与train_tm同源)
        _ox = opp["position.x"]
        if not (_ox < 120 or _ox > 1120):
            mask = mask & ~self.corner_combo_idx
        if not opp["airBorne"]:
            mask = mask & ~self.air_combo_idx
        # R24/R25: 射程门控(二维, 与train_tm同源)
        if self.reach_mask_idx.any():
            _out = self.reach_mask_idx & (
                dx_abs > self.macro_reach + self._reach_margin)
            if _out.any():
                mask = mask & ~_out
        _ady = abs(opp["position.y"] - own["position.y"])
        if self.reach_v_mask_idx.any():
            _outv = self.reach_v_mask_idx & (
                _ady > self.macro_reach_v + self._reach_margin)
            if _outv.any():
                mask = mask & ~_outv
        if not mask.any():
            mask = self.base_mask
        mid = self.ppo.sample(feat, side, mask=mask,
                              temp=getattr(self.ppo, "_temp", 1.0))
        # R16: 温度跟随模型meta退火值(评估=训练行为策略; 原1.0冷静采样
        # 与训练玩家行为分布不一致, 战报低估)
        self.decisions += 1
        self.last_macro2 = self.last_macro
        self.last_macro = mid
        # 第六轮审计§4修复: 门步(confirm/cconfirm)必须入队 — 原版直接跳过,
        # 使门后步骤无条件执行(开环对赌在对手侧复活)且门观察窗代码不可达。
        # R16: sc:步也入队(状态机已移植, 在frame_input执行; 原v1跳过使
        # sc宏解锁后仍无脚本可执行)。
        # R17②: 等级条件宏(与train_tm同源)
        from level_macros import adjust_script
        _script = adjust_script(self.macros[mid][1], self._skill_levels)
        for ks, fr in _script:
            self.macro_queue.append(
                (ks if isinstance(ks, str) else tuple(ks), fr))

    def _parse_hand(self, own):
        """TM包手牌10字节 → (ids, 选中id, 数量). 与train_tm同源。"""
        hb = own.get("hand", b'\xff' * 10)
        ids = [hb[i * 2] for i in range(5) if hb[i * 2] != 0xFF]
        sel = hb[0] if hb[0] != 0xFF else None
        return ids, sel, len(ids)

    def _sc_cost(self, cid):
        """用一张卡的耗费(技能卡1xx只耗1, 其余查角色表)。"""
        if 100 <= cid < 200:
            return 1
        return self.sc_cost_table.get(cid, 1)

    def _sc_usable_mask(self, own):
        """决策门控: 目标卡在手 且 手牌数≥耗费(与train_tm同源;
        替换R14简化版 — 简化版不看目标/耗费, 高估可用性)。"""
        m = np.zeros(self.n_macros, dtype=bool)
        ids, sel, size = self._parse_hand(own)
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

    def _sc_step(self, own):
        """符卡状态机(每逻辑帧, 包手牌反馈闭环) — 与train_tm逐字同源。
        返回(pop, abort, hold_input). 时序依据v2实测: SW按2帧换选,
        SC按3帧生效。"""
        ids, sel, size = self._parse_hand(own)
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

    def frame_input(self, own, opp, weather, objs, bullets):
        """每逻辑帧: 更新队列状态, 返回本帧输入dict。
        R16修复: 此def行曾被意外顶格 → 降为模块级函数, SideDriver.frame_input
        AttributeError → 每局即崩重建(旧进程未重import故未暴露, 新启动即现)。"""
        d_deal = max(0, self.hp_opp_prev - opp["hp"])
        d_take = max(0, self.hp_own_prev - own["hp"])
        self.hp_opp_prev, self.hp_own_prev = opp["hp"], own["hp"]
        d_now = 1 if own["direction"] > 0 else -1
        if d_now != self._last_dir:
            self._dir_frames = 0
            self._last_dir = d_now
        else:
            self._dir_frames += 1
        # R19: 逐帧视觉栈+对手速度EMA — 与train_tm同拍同构
        self._push_frame(own, opp, objs)
        if self._opp_x_prev_f is not None:
            self._opp_vx_ema_f = (0.9 * self._opp_vx_ema_f
                                  + 0.1 * (opp["position.x"]
                                           - self._opp_x_prev_f))
        self._opp_x_prev_f = opp["position.x"]
        frozen = (own["hitStop"] > 0) or (own["timeStop"] > 0)
        # R61u(C1): 统一宏执行器 — 原~60行内联推进已抽至
        # macro_executor.py(与train_tm共同调用, 双拷贝终结)
        if self.macro_queue and not frozen:
            if (isinstance(self.macro_queue[0][0], str)
                    and self.macro_queue[0][0].startswith("sc:")
                    and self._sc_tgt is None):
                self._sc_tgt = int(self.macro_queue[0][0][3:])
            self.macro_queue, self.gate_frames, _, _inp = (
                macro_executor.advance_queue(
                    self.macro_queue, self.gate_frames,
                    own, opp, d_deal, d_take,
                    frozen, own["spirit"],
                    abs(opp["position.x"] - own["position.x"]),
                    None,
                    set(), GUARD_ALL_IDS,
                    self._sc_step, self._sc_reset))
            if _inp is not None:
                self._sc_next_input = _inp
        if not self.macro_queue:
            self.decide(own, opp, weather, objs, bullets)
        if self.macro_queue:
            keys = self.macro_queue[0][0]
            if isinstance(keys, str) and keys.startswith("sc:"):
                # R16: 符卡步输入来自状态机(SW换选/SC使用)
                return dict(self._sc_next_input)
            if isinstance(keys, str):
                # P2-7同款: 门步保持上一拍输入(原版松键=与训练侧语义不一致,
                # 第六轮审计§4: "同构"由代码保证而非注释)
                return dict(self._last_inp)
            self._last_inp = keys_to_input(keys, self._last_dir < 0)
            return dict(self._last_inp)
        return {}
