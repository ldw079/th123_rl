# -*- coding: utf-8 -*-
"""对手建模模块 v2(时空条件化读层): 全局统计 → 情境×行为×事件×动态。

v1批评(用户2026-09-21): 只有全局聚合, 无时空位置条件 — 回答不了
"他在哪/什么情境下会做什么"。v2四层:
  A 情境习惯矩阵: 9情境(距离3×场地位置3)×8行为 EMA分布 — 策略读当前情境行
  B 空间占据: 对手x轴6段驻留(他喜欢站哪)
  C 交互事件读: 被防后行为/对空反应/受压防御/起身行为(择层情报)
  D 时间动态: EMA半衰30s + 习惯漂移(对手在适应) + 样本充足度

P0-L修复(第十六轮审查): ①原ctx_id只产出{0,1,3,4,6,7}共6个可达情境
(位置维只有角/非角2档, 9行里3行恒死); ②原bands用cur_ctx%6折叠,
恒零2维+混叠2维且与"空间占据"语义无关。现把对手绝对position.x
传入(P1恒为左方, 场地三段=对手压我角/中场/退己角), 9情境与6段
占据均真实可达。

数据边界(纪律): 全部来自合法传感器量(动作ID/位置/速度/公开资源),
严禁读取对手输入指令。"""

import math

from action_tables import CHAR_ACTION_TABLES

STAGE_W = 1240.0   # 场地宽(世界坐标), 与feat_builder核心标量归一分母一致

# 行为8类(由对手动作ID+运动特征归桶)
A_GUARD, A_ATTACK, A_JUMP, A_ADVANCE, A_RETREAT, A_DASH, A_BULLET, A_IDLE = range(8)

# R4纪律→R28解除: 以下区间来自SokuLib引擎枚举(docs/soku_action_ids.md,
# 用户2026-10-02提供) — 权威, 非估。A系300-332(含连段320s/66A/4A);
# B/C系400-432=弹幕射击; 必杀500-593; 符卡600-619/650-669/690-698。
_ATTACK_ACT_LO, _ATTACK_ACT_HI = 300, 598
_BULLET_ACT_LO, _BULLET_ACT_HI = 400, 433
_SC_ACT_LO, _SC_ACT_HI = 600, 699

_HALF_LIFE_S = 30.0
_LAMBDA = math.log(2.0) / _HALF_LIFE_S          # EMA衰减系数(每秒)

# ---- 防御动作ID集(权威: 解包movepattern XML, 2026-10-02) ----
# 来源: 美化包_sokuExtractedFiles/data/character/<char>/<char>.xml,
# 三角色一致(生成表见docs/action_ids_<char>.md, tools/action_id_extractor.py):
#   150-153=立防姿态(guardUpper) 154-157=蹲防(guardUnder) 158=空防(guardAir)
#   159-166=防御受击(guardB*, 萃香命名guardUpperB同义) 167=空防系
# 勘误(hitlab旧表 vs XML): "立防姿态=5"实为后退走(walkBack, 按住后方向
# 未被攻击时的动画); "蹲防=8"实为跳跃; 110-115实为受击空中/倒地(112-114)。
# R20首版误采{5,8}已被本表替换 — 5留在"后退"(位移差分)桶, 与防御可分。
GUARD_STANCE_IDS = frozenset(range(150, 159))
GUARD_RECOIL_IDS = frozenset(range(159, 168))
GUARD_ALL_IDS = GUARD_STANCE_IDS | GUARD_RECOIL_IDS


def _decay(vals, dt_s):
    k = math.exp(-_LAMBDA * dt_s)
    return [v * k for v in vals]


def classify(act, guard_ids=None, dx_delta=None, vx=0.0, air=False,
             char=None):
    """单帧对手行为归桶(8类)。dx_delta=本拍dx变化(负=逼近)。
    R16§3: 补air参数 — 原classify无任何分支返回A_JUMP,
    情境:跳/机动性特征结构性恒零(侧向量死区门禁抓出)。
    R20: guard_ids默认GUARD_ALL_IDS(XML权威150-167)。
    R21: char=对手角色名时查action_tables精确分攻击/射击桶
    (原估区间把冲刺200-227误入攻击、射击800-860从未命中)。"""
    if guard_ids is None:
        guard_ids = GUARD_ALL_IDS
    a = act or 0
    if a in guard_ids:
        return A_GUARD
    # R28: SokuLib枚举精确区间(替代XML图像桶启发式 — 桶把marisa的
    # j8A=309误判非攻击; 枚举下300-332=A系/400-432=B/C弹/500+=必杀SC)
    if _SC_ACT_LO <= a < _SC_ACT_HI:
        return A_ATTACK                      # 符卡使用=攻击性行为
    if char is not None:
        _t = CHAR_ACTION_TABLES.get(char)
        if _t is not None:
            if a in _t["shot"]:
                return A_BULLET
            if a in _t["attack"]:
                return A_ATTACK
    if _BULLET_ACT_LO <= a < _BULLET_ACT_HI:
        return A_BULLET
    if _ATTACK_ACT_LO <= a < _ATTACK_ACT_HI:
        return A_ATTACK
    if air:
        return A_JUMP
    if abs(vx or 0.0) > 6.0:      # 估: 冲刺≈8~15世界/帧, 6为下限(hitlab标定待做)
        return A_DASH
    if dx_delta is not None:      # 估: 1世界/帧阈值(hitlab标定待做)
        if dx_delta < -1.0:
            return A_ADVANCE
        if dx_delta > 1.0:
            return A_RETREAT
    return A_IDLE


class OpponentModel:
    """时空条件化对手读层。决策拍update(); features()取特征。
    R17(用户2026-10-01): 27→75维 — 基础27 + 动作历史5×8=40
    + 资源条件化(灵满4+灵空4)=8。(R18勘误: 旧稿"55维/8×3"为误记)"""

    N_CTX = 9
    N_ACT = 8
    N_BANDS = 6
    HIST_N = 5       # 动作历史深度
    N_FEATS = 27 + 40 + 8  # 基础27 + 历史40(5步×8类) + 资源条件8

    FEAT_NAMES = (
        ["情境:防", "情境:攻", "情境:跳", "情境:进", "情境:退", "情境:冲",
         "情境:射", "情境:怠"]
        + ["占据%d" % i for i in range(6)]
        + ["被防反击", "被防跳避", "对空反应", "受压防御", "起身攻击", "起身跳"]
        + ["跳频", "囤牌", "充能", "低灵", "射击"]
        + ["漂移", "样本量"]
        + ["历史%d_%d" % (step, cls) for step in range(HIST_N)
           for cls in range(8)]
        + ["灵满:%s" % n for n in ("防", "攻", "射", "机")]
        + ["灵空:%s" % n for n in ("防", "攻", "射", "机")]
    )

    def __init__(self):
        self.t = 0.0
        # A 情境矩阵: 9×8 EMA计数
        self.ctx = [[0.0] * self.N_ACT for _ in range(self.N_CTX)]
        self.ctx_total = [0.0] * self.N_CTX
        self.cur_ctx = 4   # 最近情境(中距×中场)
        # B 空间占据: 归一化舞台0~1分6段
        self.bands = [0.0] * self.N_BANDS
        # C 事件跟踪
        self._post_guard = [0.0] * 4     # 被防后: 攻/跳/退/其他
        self._post_guard_tot = 0.0
        self._guard_left_t = None        # 对手何时离开防御态
        self._in_guard = False
        self.aa_atk = 0.0                # 我滞空时: 对手攻击EMA
        self.aa_tot = 0.0                # 我滞空时: 总EMA
        self.press_guard = 0.0           # 贴身时: 防御EMA
        self.press_tot = 0.0             # 贴身时: 总EMA
        self._wakeup = [0.0] * 3         # 起身后: 攻/跳/防
        self._wakeup_tot = 0.0
        self._down_since = None          # 对手倒地中(受击/吹飞态)
        # D 全局/动态
        self.jump_events = 0.0           # 起跳事件EMA计数
        self._prev_air = False
        self.cards_avg = 0.0             # 手牌EMA
        self.gauge_acc = 0.0             # 充能增量EMA(速率代理)
        self.low_spirit = 0.0            # 低灵帧EMA
        self.frames_tot = 0.0
        self.bullet = 0.0                # 射击帧EMA
        self._prev_dx = None
        self._prev_gauge = None
        self._recent = [0.0] * self.N_ACT   # 近15s分布(漂移检测用)
        self._older = [0.0] * self.N_ACT
        self._older_t = 0.0
        self._enough = 0.0
        # R17①: 动作历史(最近HIST_N步的类别, 滚动队列)
        self._hist = [A_IDLE] * self.HIST_N
        # R17②: 资源条件化行为分布(灵满/灵空 各4类: 防攻射机)
        self._res_full = [0.0] * 4   # 灵力>=500时的: 防攻射机 EMA
        self._res_full_tot = 0.0
        self._res_low = [0.0] * 4    # 灵力<500时的: 防攻射机 EMA
        self._res_low_tot = 0.0

    # ---------- 情境编码 ----------
    @staticmethod
    def ctx_id(dx, opp_x):
        """P0-L: 位置3档改为场地绝对三段(P1恒左方: 左段=对手压我角,
        右段=对手退己角), 与距离3档组合后9情境全部可达。"""
        d = 0 if dx < 130 else (1 if dx < 420 else 2)
        z = 0 if opp_x < STAGE_W / 3 else (1 if opp_x < STAGE_W * 2 / 3 else 2)
        return d * 3 + z

    # ---------- 每决策拍 ----------
    def update(self, dt_s, opp_air, opp_act, dx, opp_vx, opp_spirit,
               opp_cards_n, opp_gauge, opp_x, guard_ids,
               own_air, opp_down, char=None):
        """dt_s: 本拍游戏秒; own_air: 我方滞空(对空反应检测);
        opp_down: 对手在受击/倒地态(起身行为检测);
        opp_x: 对手绝对position.x(P0-L: 9情境+6段占据都由它构成);
        char: 对手角色名(R21: 查action_tables精确分攻击/射击桶)。"""
        self.t += dt_s
        w = dt_s
        dx_delta = (dx - self._prev_dx) if (dx is not None
                                            and self._prev_dx is not None) else None
        # A: 情境+行为归桶
        if dx is not None and opp_x is not None:
            self.cur_ctx = self.ctx_id(dx, opp_x)
        b = classify(opp_act, guard_ids, dx_delta, opp_vx, air=bool(opp_air),
                     char=char)
        self.ctx[self.cur_ctx][b] += w
        self.ctx_total[self.cur_ctx] += w
        # R17①: 动作历史滚动
        self._hist.pop(0)
        self._hist.append(b)
        # R17②: 资源条件化(灵力>=500 vs <500 时对手行为不同)
        _res_group = (0 if b == A_GUARD else
                      1 if b == A_ATTACK else
                      2 if b == A_BULLET else 3)  # 3=机动(跳/冲/进/退/怠)
        if opp_spirit is not None and opp_spirit >= 500:
            self._res_full[_res_group] += w
            self._res_full_tot += w
        else:
            self._res_low[_res_group] += w
            self._res_low_tot += w
        # D: 全局(P1-4c修复: recent有独立衰减, older存历史累积, drift才能感知变化)
        self._recent[b] += w
        self._recent = _decay(self._recent, dt_s)  # 近窗独立半衰30s
        self._older[b] += w
        if self.t - self._older_t > 15.0:   # 每15s把older做一次快照归一
            tot = max(1e-6, sum(self._older))
            self._older = [v / tot * 30.0 for v in self._older]  # 归一到30s等效
            self._older_t = self.t
        # B: 空间占据(P0-L: 按对手绝对x分6段真实统计驻留, 替代
        # cur_ctx%6折叠 — 那一版恒零2维+混叠2维且名不副实)
        if opp_x is not None:
            bi = min(self.N_BANDS - 1, max(0, int(opp_x * self.N_BANDS / STAGE_W)))
            self.bands[bi] += w
        # 跳跃事件
        if opp_air and not self._prev_air:
            self.jump_events += 1.0
        self._prev_air = bool(opp_air)
        # 起跳衰减
        self.jump_events *= math.exp(-_LAMBDA * dt_s)
        # C: 被防后行为(离开防御后的首个非防御类)
        act = opp_act or 0
        if act in guard_ids:
            self._in_guard = True
        elif self._in_guard:
            self._in_guard = False
            if b == A_ATTACK:
                self._post_guard[0] += 1.0
            elif b in (A_JUMP, A_ADVANCE):
                self._post_guard[1] += 1.0
            elif b in (A_RETREAT, A_DASH):
                self._post_guard[2] += 1.0
            else:
                self._post_guard[3] += 1.0
        # C: 对空反应(我滞空时对手攻击)
        if own_air:
            self.aa_tot += w
            if b == A_ATTACK:
                self.aa_atk += w
        # C: 受压防御(贴身时对手防御)
        if dx is not None and dx < 130:
            self.press_tot += w
            if b == A_GUARD:
                self.press_guard += w
        # C: 起身行为(倒地结束后的首类)
        if opp_down:
            self._down_since = self.t
        elif self._down_since is not None:
            if self.t - self._down_since < 1.0:   # 1s内起身
                if b == A_ATTACK:
                    self._wakeup[0] += 1.0
                elif b in (A_JUMP, A_ADVANCE, A_DASH):
                    self._wakeup[1] += 1.0
                elif b == A_GUARD:
                    self._wakeup[2] += 1.0
                self._wakeup_tot += 1.0
            self._down_since = None
        # D: 全局量EMA
        if opp_cards_n is not None:
            self.cards_avg += (opp_cards_n - self.cards_avg) * min(1.0, w * 0.5)
        if opp_gauge is not None and self._prev_gauge is not None:
            dg = opp_gauge - self._prev_gauge
            if dg > 0:
                self.gauge_acc += dg * 0.1
        self._prev_gauge = opp_gauge
        self.gauge_acc *= math.exp(-_LAMBDA * dt_s)
        if opp_spirit is not None and opp_spirit < 300:   # 估: 低灵阈值(hitlab标定待做)
            self.low_spirit += w
        if b == A_BULLET:
            self.bullet += w
        self.frames_tot += w
        self._enough = min(1.0, self.frames_tot / 45.0)
        # 全局EMA衰减(半衰)
        k = math.exp(-_LAMBDA * dt_s)
        self.low_spirit *= k
        self.bullet *= k
        self.aa_atk *= k
        self.aa_tot *= k
        self.press_guard *= k
        self.press_tot *= k
        for i in range(4):
            self._post_guard[i] *= k
        for i in range(3):
            self._wakeup[i] *= k
        self._wakeup_tot *= k
        for i in range(6):
            self.bands[i] *= k
        for i in range(self.N_CTX):
            self.ctx_total[i] *= k
            for j in range(self.N_ACT):
                self.ctx[i][j] *= k
        self._prev_dx = dx

    # ---------- 特征 ----------
    @staticmethod
    def _rate(a, b):
        return min(1.0, a / b) if b > 1e-6 else 0.0

    def features(self):
        # A: 当前情境行为分布
        row = self.ctx[self.cur_ctx]
        tot = self.ctx_total[self.cur_ctx]
        ctx8 = [self._rate(v, tot) for v in row] if tot > 1e-6 else [0.0] * 8
        # B: 空间占据(情境占比归一)
        bt = sum(self.bands)
        bands6 = [self._rate(v, bt) for v in self.bands] if bt > 1e-6 else [0.125] * 6
        # C: 事件率
        pgt = sum(self._post_guard)
        ev6 = [
            self._rate(self._post_guard[0], pgt),          # 被防后反击
            self._rate(self._post_guard[1], pgt),          # 被防后跳/进
            self._rate(self.aa_atk, self.aa_tot),          # 对空反应
            self._rate(self.press_guard, self.press_tot),  # 受压防御
            self._rate(self._wakeup[0], self._wakeup_tot), # 起身攻击
            self._rate(self._wakeup[1], self._wakeup_tot), # 起身跳/突
        ]
        # D: 全局
        g5 = [
            min(1.0, self.jump_events / 8.0),
            min(1.0, self.cards_avg / 5.0),
            min(1.0, self.gauge_acc / 1500.0),
            self._rate(self.low_spirit, max(1e-6, self.frames_tot * 0.3)),
            self._rate(self.bullet, max(1e-6, self.frames_tot * 0.3)),
        ]
        # D: 漂移(近15s vs 累计的分布差)
        rs = sum(self._recent) or 1e-6
        os_ = sum(self._older) or 1e-6
        drift = 0.0
        for a, b in zip(self._recent, self._older):
            drift += abs(a / rs - b / os_)
        drift = min(1.0, drift / 2.0)
        base27 = ctx8 + bands6 + ev6 + g5 + [drift, self._enough]
        # R17①: 动作历史(最近HIST_N步, 每步8类one-hot)
        hist_feats = []
        for cls in self._hist:
            row8 = [0.0] * 8
            row8[cls] = 1.0
            hist_feats.extend(row8)
        # R17②: 资源条件化(灵满4 + 灵空4)
        res_full4 = [self._rate(v, self._res_full_tot)
                     for v in self._res_full]
        res_low4 = [self._rate(v, self._res_low_tot)
                    for v in self._res_low]
        return base27 + hist_feats + res_full4 + res_low4

    def summary(self):
        f = self.features()
        row = f[0:8]
        names8 = ("防御", "攻击", "跳跃", "逼近", "后撤", "冲刺", "射击", "其他")
        top = sorted(zip(names8, row), key=lambda kv: -kv[1])[:3]
        s = "情境倾向[" + "/".join("%s%.0f%%" % (n, v * 100) for n, v in top if v > 0.05) + "]"
        ev = []
        if f[8 + 0] > 0.4:
            ev.append("被防爱反击")
        if f[8 + 2] > 0.4:
            ev.append("对空积极")
        if f[8 + 3] > 0.6:
            ev.append("贴身爱防")
        if f[8 + 4] > 0.5:
            ev.append("起身抢招")
        if f[20 + 5] > 0.5:
            ev.append("习惯漂移中")
        return "对手画像: %s %s" % (s, " ".join(ev))
