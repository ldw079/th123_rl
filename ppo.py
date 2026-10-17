# -*- coding: utf-8 -*-
"""PPO 训练器(宏动作版): 类别策略(softmax over 招式宏) + 价值网络(GAE) + 侧输入。

相对按键版的关键变化:
- 策略输出 = 宏 ID 的类别分布(softmax)——必杀指令(236+B 等)一键可达,
  探索空间从 2^9 帧级组合坍缩到 N_MACROS 个招式选项;
- 侧输入 = 最近 2 个宏 ID(one-hot) + 灵力;
- 温度退火作用于 logits(softmax 温度), 熵为类别熵。
"""

import numpy as np

from macros import N_MACROS


# ==== 卷积工具(im2col, 纯 numpy 无框架) ====
# 布局: 输入 14400 = 3帧×60行×80列 → (N,3,60,80), 时间帧当通道
# 三层主干(架构审查: 16/32/32→32/64/64, 空间特征容量×2):
CONV1_F, CONV2_F, CONV3_F = 32, 64, 64
CONV_H, CONV_W = 60, 80
# 形状链: 3×60×80 → conv1 → 32×58×78 → pool → 32×29×39
#        → conv2 → 64×27×37 → 裁64×36 → pool → 64×13×18
#        → conv3 → 64×11×16 → 裁10×16 → pool → 64×5×8 = 2560
TRUNK_FLAT = CONV3_F * 5 * 8       # 2560


def _im2col(X, KH, KW):
    """X:(N,C,H,W) → (N*OH*OW, C*KH*KW), stride=1。"""
    N, C, H, W = X.shape
    OH, OW = H - KH + 1, W - KW + 1
    s = X.strides
    v = np.lib.stride_tricks.as_strided(
        X, (N, C, OH, OW, KH, KW), (s[0], s[1], s[2], s[3], s[2], s[3]))
    return np.ascontiguousarray(
        v.transpose(0, 2, 3, 1, 4, 5)).reshape(N * OH * OW, C * KH * KW)


def _col2im(dcols, N, C, H, W, KH, KW):
    """im2col 逆(仅卷积内层用): (N*OH*OW, C*KH*KW) → (N,C,H,W), 重叠位置累加。"""
    OH, OW = H - KH + 1, W - KW + 1
    dp = dcols.reshape(N, OH, OW, C, KH, KW).transpose(0, 3, 1, 2, 4, 5)
    dX = np.zeros((N, C, H, W), dtype=dcols.dtype)
    for kh in range(KH):
        for kw in range(KW):
            dX[:, :, kh:kh + OH, kw:kw + OW] += dp[:, :, :, :, kh, kw]
    return dX


def _maxpool2(X):
    """2×2最大池化 → (输出, argmax掩码0..3, k=行*2+列)。H,W 须为偶数。"""
    N, C, H, W = X.shape
    xr = X.reshape(N, C, H // 2, 2, W // 2, 2).transpose(0, 1, 2, 4, 3, 5)\
        .reshape(N, C, H // 2, W // 2, 4)
    am = xr.argmax(-1)
    return xr.max(-1), am


def _unpool2(d, am):
    """maxpool2 反向: 梯度散回 argmax 位置。"""
    N, C, OH, OW = d.shape
    dx = np.zeros((N, C, OH, OW, 4), dtype=d.dtype)
    n = np.arange(N)[:, None, None, None]
    c = np.arange(C)[None, :, None, None]
    oh = np.arange(OH)[None, None, :, None]
    ow = np.arange(OW)[None, None, None, :]
    dx[n, c, oh, ow, am] = d
    # k=行*2+列: 先拆成(行,列)相邻两维, 再转置到(行,块行,列,块列)
    return dx.reshape(N, C, OH, OW, 2, 2).transpose(0, 1, 2, 4, 3, 5).reshape(N, C, OH * 2, OW * 2)


class _Adam:
    GRAD_CLIP = 5.0   # 全局梯度范数裁剪(价值损失曾飙26: 离群 minibatch 的爆炸抑制)

    def __init__(self, params):
        self.params = params
        self.m = [np.zeros_like(p) for p in params]
        self.v = [np.zeros_like(p) for p in params]
        self.t = 0

    def step(self, grads, lr, maximize=False):
        assert len(grads) == len(self.params), \
            "Adam梯度数%d≠参数槽%d" % (len(grads), len(self.params))
        # P1(第十轮§7.3): NaN防护 — 一帧坏数据→dz NaN→Adam.v永久NaN
        for gi, g in enumerate(grads):
            if not np.all(np.isfinite(g)):
                print("[Adam] 梯度[%d]含NaN/Inf — 跳过本步(防永久污染)" % gi)
                return
        self.t += 1
        gn = float(np.sqrt(sum(float((g * g).sum()) for g in grads)))
        if gn > self.GRAD_CLIP:
            s = self.GRAD_CLIP / gn
            grads = [g * s for g in grads]
        b1a, b2a, eps = 0.9, 0.999, 1e-8
        sgn = 1.0 if maximize else -1.0
        for i, g in enumerate(grads):
            self.m[i] = b1a * self.m[i] + (1 - b1a) * g
            self.v[i] = b2a * self.v[i] + (1 - b2a) * g * g
            mh = self.m[i] / (1 - b1a ** self.t)
            vh = self.v[i] / (1 - b2a ** self.t)
            self.params[i] += sgn * lr * mh / (np.sqrt(vh) + eps)


def _cap_backward(dz, cap, zraw):
    """审计#3 P1-5②: 封顶反向 — dz_capped→dz_raw。逐行cap=zmax/8>1时,
    zmax所在列有额外项(torch autograd天然含; 原只补1/cap致conv主干/
    对手子网梯度大面积反号)。有限差分数值验证见tests/test_gpu_onestep
    (单步权重符号级对此项不够敏感, 曾漏网)。"""
    _r = np.flatnonzero(cap[:, 0] > 1.0)
    out = dz / cap
    if _r.size:
        _zs = zraw[_r]
        _m = np.argmax(np.abs(_zs), axis=1)
        _dot = np.einsum('ij,ij->i', dz[_r], _zs)
        _sgn = np.sign(_zs[np.arange(_r.size), _m])
        out[_r, _m] -= (_dot * _sgn / (8.0 * (cap[_r, 0] ** 2)))
    return out


def _softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


class PPOTrainer:
    GAMMA = 0.999       # 每决策步折扣(用户2026-09-30: 技能卡跨round升级→round间
                        # 有战略依赖. 0.999→有效视界≈1000决策≈整场match,
                        # 能"看到"round1用升级卡→round3必杀变强的长弧线)
    LAM = 0.95          # GAE λ
    CLIP = 0.2          # PPO 裁剪幅度
    EPOCHS = 1      # 回退: 3epoch太慢, 1epoch够用      # 自审: 小批防过拟合, 配合攒批          # 每批数据复用轮数
    MINIBATCH = 64
    PI_LR = 3e-4   # R11§2: 1e-3是在temp未修复时测的假低KL下调的, 实际30-200倍过冲   # 自审: |KL|低于目标6-60倍, 提速(早停兜底)
    VF_LR = 3e-3   # 自审: 值损130-1200(归一化尺度应O(1))
    BETA_ENT_0 = 0.02   # 熵系数退火起点
    BETA_ENT_MIN = 0.001
    ENT_DECAY = 0.97    # 每次更新衰减系数(0.94→0.97: EPISODES_PER_UPDATE=1后更新翻倍, 保持墙钟退火节奏)
    BC_W = 0.12         # BC 辅助初始权重(随退火衰减)
    BC_W_MIN = 0.0      # R47(可行性天花板3): 原0.05永不归零→永久人类风格拉力与超人目标冲突; 改0允许锚完全释放(oracle BC仍保留)
    TARGET_KL = 0.03    # 近端 KL 早停阈值
    HIDDEN = 128
    SIDE_H = 64         # 侧通路非线性头宽度: 连续特征(距离/高度/TTI/速度)的
                        # 平滑响应能力 — 线性W_side只表达单调, 带间跳变靠它消除
    N_OUT = N_MACROS    # 类别输出 = 宏数
    # P2修(从零#4): 308残留改CORE_DIMS派生(330→343→…每次扩维这里都
    # 落后一代 — 与"维度锚静态字面量跟不了活常量"同类, 注释自称
    # "须与实际布局一致"却硬编码)。feat_builder无反向依赖, 导入安全。
    from feat_builder import FeatureBuilder as _FBForNSide  # noqa: E402
    N_SIDE = 5 * N_MACROS + _FBForNSide.CORE_DIMS  # R35布局:
    #                            [宏N][上宏N][core][gap_x][gap_y][untech]
    #                            (train_tm/side_driver显式传n_side覆盖;
    #                             类默认值供_v_forward的S is None兜底)
    N_SIDE_TM = 2 * N_MACROS + 64  # TM通道v1: 双宏one-hot + 包侧核心64维
    # ---- R17对手建模四件套③④: 对手子网络 + 动作预测辅助损失 ----
    # 侧布局[宏N][上宏N][core], 对手建模段(feat_builder段10)在core内
    # 偏移152(段1..9宽度和: 16+16+2+14+4+6+36+36+22), 宽75(opp_model.N_FEATS)
    OPP_DIM = 75
    OPP_CORE_OFF = 152
    OPP_H1, OPP_H2 = 32, 16   # 子网络 75→32→16(ReLU), 16维紧凑对手表征
    AUX_W = 0.15              # 对手动作预测辅助损失权重(预测下一决策拍
                              # 对手动作类//128; 塑造trunk+子网络的对手注意力)
    AUX_H = 32                # 预测头隐层宽
    N_OPP_CLS = 8             # 预测目标类数

    def __init__(self, n_side=None, n_out=None):
        if n_side is not None:
            self.N_SIDE = n_side
        if n_out is not None:
            self.N_OUT = n_out
        self.rng = np.random.default_rng(0)
        self.Wc1 = self.bc1 = self.Wc2 = self.bc2 = None   # 卷积主干(策略/价值共享)
        self.W1 = self.b1 = self.W2 = self.b2 = None
        self.W_side = None
        self.Ws1 = self.bs1 = self.Ws2 = self.bs2 = None   # 侧通路非线性头(连续化)
        self.Wo1 = self.bo1 = self.Wo2 = self.bo2 = None   # R17③对手子网络
        self.W_opp = None                                  # 子网络→策略logits
        # S-4阶段1(2026-10-15): GRU序列记忆 — 推理侧集成, W_gru零初始化
        # →行为与无GRU逐位一致(旧档兼容); 阶段2(更新重放+解冻)另批
        from opp_gru import OppGRU as _OG
        self.opp_gru = _OG(seed=7)
        self.W_gru = None   # (N_OUT,16) — init_fresh建零, 旧档load后补零
        self.Wq1 = self.bq1 = self.Wq2 = self.bq2 = None   # R17④动作预测头
        self.W1v = self.b1v = self.W2v = self.b2v = None
        self._pi_adam = None
        self._vf_adam = None
        self._rstd = 1.0
        self._beta = self.BETA_ENT_0
        self._temp = 2.0     # softmax 温度(高温→趋近均匀分布, 探索)
        self._bcw = self.BC_W
        self._updates = 0
        self._adaptive_lr_scale = 1.0

    # ---- 加载/保存 ----
    def init_fresh(self, n_in):
        rng = np.random.default_rng(0)
        self.Wc1 = (rng.standard_normal((CONV1_F, 3 * 9)) / np.sqrt(3 * 9)).astype(np.float32)
        self.bc1 = np.zeros(CONV1_F, dtype=np.float32)
        self.Wc2 = (rng.standard_normal((CONV2_F, CONV1_F * 9)) / np.sqrt(CONV1_F * 9)).astype(np.float32)
        self.bc2 = np.zeros(CONV2_F, dtype=np.float32)
        self.Wc3 = (rng.standard_normal((CONV3_F, CONV2_F * 9)) / np.sqrt(CONV2_F * 9)).astype(np.float32)
        self.bc3 = np.zeros(CONV3_F, dtype=np.float32)
        self.W1 = (rng.standard_normal((TRUNK_FLAT, self.HIDDEN)) / np.sqrt(TRUNK_FLAT)).astype(np.float32)
        self.b1 = np.zeros(self.HIDDEN, dtype=np.float32)
        self.W2 = (rng.standard_normal((self.HIDDEN, self.N_OUT)) / np.sqrt(self.HIDDEN)).astype(np.float32)
        self.b2 = np.zeros(self.N_OUT, dtype=np.float32)
        self.W_side = np.zeros((self.N_SIDE, self.N_OUT), dtype=np.float32)
        rng2 = np.random.default_rng(3)
        self.Ws1 = (rng2.standard_normal((self.N_SIDE, self.SIDE_H)) / np.sqrt(self.N_SIDE)).astype(np.float32)
        self.bs1 = np.zeros(self.SIDE_H, dtype=np.float32)
        self.Ws2 = (rng2.standard_normal((self.SIDE_H, self.N_OUT)) * 0.01).astype(np.float32)
        self.bs2 = np.zeros(self.N_OUT, dtype=np.float32)
        # S-4: GRU表征→logits投影(零初始化=R17③W_opp同纪律)
        self.W_gru = np.zeros((16, self.N_OUT), dtype=np.float32)
        # R17③对手子网络: 侧向量对手建模切片75→32→16(ReLU);
        # W_opp零初始化 → 初始策略分布与无子网络时逐位一致
        rng4 = np.random.default_rng(5)
        self.Wo1 = (rng4.standard_normal((self.OPP_DIM, self.OPP_H1)) / np.sqrt(self.OPP_DIM)).astype(np.float32)
        self.bo1 = np.zeros(self.OPP_H1, dtype=np.float32)
        self.Wo2 = (rng4.standard_normal((self.OPP_H1, self.OPP_H2)) / np.sqrt(self.OPP_H1)).astype(np.float32)
        self.bo2 = np.zeros(self.OPP_H2, dtype=np.float32)
        self.W_opp = np.zeros((self.OPP_H2, self.N_OUT), dtype=np.float32)
        # R17④动作预测辅助头: [trunk 2560 | 对手表征16]→32→8类softmax
        _aq = TRUNK_FLAT + self.OPP_H2
        self.Wq1 = (rng4.standard_normal((_aq, self.AUX_H)) / np.sqrt(_aq)).astype(np.float32)
        self.bq1 = np.zeros(self.AUX_H, dtype=np.float32)
        self.Wq2 = (rng4.standard_normal((self.AUX_H, self.N_OPP_CLS)) * 0.01).astype(np.float32)
        self.bq2 = np.zeros(self.N_OPP_CLS, dtype=np.float32)
        self._init_value(TRUNK_FLAT)

    def load(self, pi_path, v_path):
        d = np.load(pi_path)
        if "Wc3" not in d:
            raise ValueError("旧模型无三层卷积主干")
        self.Wc1, self.bc1 = d["Wc1"], d["bc1"]
        self.Wc2, self.bc2 = d["Wc2"], d["bc2"]
        self.Wc3, self.bc3 = d["Wc3"], d["bc3"]
        self.W1, self.b1, self.W2, self.b2 = d["W1"], d["b1"], d["W2"], d["b2"]
        if self.W1.shape[0] != TRUNK_FLAT:
            raise ValueError("旧模型主干维度不符")
        self.W_side = d["W_side"] if "W_side" in d else \
            np.zeros((self.N_SIDE, self.N_OUT), dtype=np.float32)
        # ---- 宏库扩展兼容(零初始化迁移): 旧模型宏数/侧维小于当前宏库时,
        # 新宏 logit 与新侧槽位全部零初始化 — 旧策略分布逐位不变, 新宏从零学起。
        # 侧布局: [宏N][上宏N][85], 新槽位插在两段one-hot尾部, 其余行原序平移。
        oldn = self.W2.shape[1]
        old_side = self.W_side.shape[0]

        # R37(审查2026-10-02): 显式宏数守卫 — 旧模型宏数>当前库=缩容
        # (此前靠numpy广播报"negative dimensions"无法定位根因)
        if oldn > self.N_OUT:
            raise ValueError(
                "模型宏数%d > 当前宏库%d — 缩容不支持; "
                "检查是否旧进程用旧宏库覆盖了产物"
                % (oldn, self.N_OUT))

        def _map_row(i):
            if i < self.N_OUT:                      # 槽1: 上上宏
                return i if i < oldn else None
            if i < 2 * self.N_OUT:                  # 槽2: 上宏
                j = i - self.N_OUT
                return oldn + j if j < oldn else None
            # B修core增长错位(原`2*oldn+(i-2N)`纯恒等平移): 5N布局
            # [slot1 N][slot2 N][core][gap N][gap_v N][untech N],
            # 新core宽度=self.N_SIDE-5*self.N_OUT, 旧core=old_side-5*oldn.
            # 新core超出旧core→None(零初始化); 尾三块块内偏移对齐.
            _core_new = self.N_SIDE - 5 * self.N_OUT
            _core_old = old_side - 5 * oldn
            _c = i - 2 * self.N_OUT
            if _c < _core_new:
                return (2 * oldn + _c) if _c < _core_old else None
            _t = _c - _core_new
            _b, _k = divmod(_t, self.N_OUT)
            if _b < 3 and _k < oldn:
                return 2 * oldn + _core_old + _b * oldn + _k
            return None

        if oldn < self.N_OUT or old_side < self.N_SIDE:
            # R36(审查2026-10-02): _map_row正确性依赖的不变量 —
            # 旧侧向量必须至少含[双宏one-hot][core 308]才能正确映射;
            # 尾部块(射程/untech)允许存在(零填充到新宽度)。CORE_DIMS
            # 再变时此断言会在静默错位前拦截(偏移污染的同一形状)。
            _CORE_DIMS = 280  # B: 最低合法旧core(B前308/316均>此值;
            #                 #  纯断言旧侧非退化, 具体布局由_map_row处理)
            assert old_side >= 2 * oldn + _CORE_DIMS, \
                ("旧侧向量过短: old_side=%d < 2*%d+%d — "
                 "旧模型年代的CORE_DIMS与本代码不一致, "
                 "_map_row会静默错位" % (old_side, oldn, _CORE_DIMS))
            print("[迁移] 宏库扩展 %d→%d: 新宏零初始化, 旧策略保持" % (oldn, self.N_OUT))
            dmac = self.N_OUT - oldn
            self.b2 = np.concatenate([self.b2, np.zeros(dmac, dtype=np.float32)])
            self.W2 = np.concatenate(
                [self.W2, np.zeros((self.W2.shape[0], dmac), dtype=np.float32)], axis=1)
            Ws = np.zeros((self.N_SIDE, self.N_OUT), dtype=np.float32)
            for i in range(self.N_SIDE):
                j = _map_row(i)
                if j is not None and j < old_side:
                    Ws[i, :oldn] = self.W_side[j]
            self.W_side = Ws
        try:
            dv = np.load(v_path)
            W1v_o = dv["W1v"]
            # R37(bug修复): 旧代码条件 TRUNK_FLAT+old_side 漏了 OPP_H2(16)
            # → 3179≠3163 → 迁移不触发 → 维度不符 → critic被静默重随机。
            # 实际旧值文件含对手表征16列, 正确条件须+OPP_H2。
            _old_full = TRUNK_FLAT + old_side + self.OPP_H2
            _new_full = TRUNK_FLAT + self.N_SIDE + self.OPP_H2
            if old_side < self.N_SIDE and W1v_o.shape[0] == _old_full:
                # 价值网输入同映射迁移(侧槽位插入, 主干+对手表征行不动)
                Wv = np.zeros((_new_full, W1v_o.shape[1]),
                              dtype=np.float32)
                Wv[:TRUNK_FLAT] = W1v_o[:TRUNK_FLAT]
                for i in range(self.N_SIDE):
                    j = _map_row(i)
                    if j is not None and j < old_side:
                        Wv[TRUNK_FLAT + i] = W1v_o[TRUNK_FLAT + j]
                # 对手表征16列在侧向量块之后, 原序平移
                _old_opp_start = TRUNK_FLAT + old_side
                _new_opp_start = TRUNK_FLAT + self.N_SIDE
                _opp_rows = min(self.OPP_H2,
                                W1v_o.shape[0] - _old_opp_start)
                if _opp_rows > 0:
                    Wv[_new_opp_start:_new_opp_start + _opp_rows] = \
                        W1v_o[_old_opp_start:_old_opp_start + _opp_rows]
                W1v_o = Wv
            if W1v_o.shape[0] != _new_full:
                raise ValueError("value 维度不符(期望%d got %d)"
                                 % (_new_full, W1v_o.shape[0]))
            self.W1v, self.b1v = W1v_o, dv["b1v"]
            if "W3v" in dv:
                # 3层值头(新格式)
                self.W2v, self.b2v = dv["W2v"], dv["b2v"]
                self.W3v, self.b3v = dv["W3v"], dv["b3v"]
            else:
                # 2层→3层迁移: 恒等中间层保旧值函数逐位不变
                # H1 @ I + 0 = H1, 然后 H1 @ W3v + b3v = 旧输出
                self.W2v = np.eye(self.HIDDEN, dtype=np.float32)
                self.b2v = np.zeros(self.HIDDEN, dtype=np.float32)
                self.W3v = dv["W2v"].astype(np.float32)
                self.b3v = dv["b2v"].astype(np.float32)
                print("[迁移] 值头2层→3层: 恒等中间层, 旧值函数保持")
        except Exception as e:
            # R37: 响亮失败(不静默重随机 — 会制造"指标在续训但critic从零")
            raise ValueError(
                "价值文件加载失败(%s) — 检查模型/代码/宏库版本一致性" % e)
        # 退火状态恢复(持久化配套; 旧模型无 meta → 维持初始值)
        if "meta" in d:
            _m = d["meta"]
            self._temp, self._beta, self._bcw = float(_m[0]), float(_m[1]), float(_m[2])
            self._updates, self._rstd = int(_m[3]), float(_m[4])
            if len(_m) >= 6:
                self._adaptive_lr_scale = float(_m[5])  # R13: 新元素在末尾
        # 侧通路非线性头(连续化): 旧模型无此参数 → 零输出起步(旧策略逐位不变,
        # 新头从批26起学连续响应); 侧维迁移时同步映射 Ws1 行
        if "Ws1" in d:
            self.Ws1, self.bs1 = d["Ws1"], d["bs1"]
            self.Ws2, self.bs2 = d["Ws2"], d["bs2"]
            if self.Ws2.shape[1] < self.N_OUT or self.bs2.shape[0] < self.N_OUT:
                # 宏库扩展时侧头第二层同步扩列(新宏零列=旧logits逐位不变;
                # 漏扩会让 (1,N_MACROS)+(1,旧宏数) 广播崩溃 — 验证批首采样即爆)
                dm = self.N_OUT - min(self.Ws2.shape[1], self.bs2.shape[0])
                self.Ws2 = np.concatenate(
                    [self.Ws2, np.zeros((self.Ws2.shape[0], dm), dtype=np.float32)], axis=1)
                self.bs2 = np.concatenate([self.bs2, np.zeros(dm, dtype=np.float32)])
            if self.Ws1.shape[0] < self.N_SIDE:
                Hs = np.zeros((self.N_SIDE, self.SIDE_H), dtype=np.float32)
                for i in range(self.N_SIDE):
                    j = _map_row(i)
                    if j is not None and j < self.Ws1.shape[0]:
                        Hs[i] = self.Ws1[j]
                self.Ws1 = Hs
        else:
            rng3 = np.random.default_rng(4)
            self.Ws1 = (rng3.standard_normal((self.N_SIDE, self.SIDE_H)) / np.sqrt(self.N_SIDE)).astype(np.float32)
            self.bs1 = np.zeros(self.SIDE_H, dtype=np.float32)
            self.Ws2 = np.zeros((self.SIDE_H, self.N_OUT), dtype=np.float32)
            self.bs2 = np.zeros(self.N_OUT, dtype=np.float32)
            print("[迁移] 侧通路非线性头零初始化(连续化头, 旧策略保持)")
        # R17③④: 对手子网络+预测头(旧模型无 → 与init_fresh同种子随机化;
        # W_opp零初始化保旧策略逐位不变 — 子网络/预测头从零学起)
        if "Wo1" in d and d["Wo1"].shape == (self.OPP_DIM, self.OPP_H1):
            (self.Wo1, self.bo1, self.Wo2, self.bo2, self.W_opp) = (
                d["Wo1"], d["bo1"], d["Wo2"], d["bo2"], d["W_opp"])
            self.Wq1, self.bq1 = d["Wq1"], d["bq1"]
            self.Wq2, self.bq2 = d["Wq2"], d["bq2"]
        else:
            rng4 = np.random.default_rng(5)
            self.Wo1 = (rng4.standard_normal((self.OPP_DIM, self.OPP_H1)) / np.sqrt(self.OPP_DIM)).astype(np.float32)
            self.bo1 = np.zeros(self.OPP_H1, dtype=np.float32)
            self.Wo2 = (rng4.standard_normal((self.OPP_H1, self.OPP_H2)) / np.sqrt(self.OPP_H1)).astype(np.float32)
            self.bo2 = np.zeros(self.OPP_H2, dtype=np.float32)
            self.W_opp = np.zeros((self.OPP_H2, self.N_OUT), dtype=np.float32)
            _aq = TRUNK_FLAT + self.OPP_H2
            self.Wq1 = (rng4.standard_normal((_aq, self.AUX_H)) / np.sqrt(_aq)).astype(np.float32)
            self.bq1 = np.zeros(self.AUX_H, dtype=np.float32)
            self.Wq2 = (rng4.standard_normal((self.AUX_H, self.N_OPP_CLS)) * 0.01).astype(np.float32)
            self.bq2 = np.zeros(self.N_OPP_CLS, dtype=np.float32)
            print("[迁移] 对手子网络+预测头初始化(R17新架构, 从零学起)")
        # S-4阶段1(2026-10-15): GRU序列记忆 — 旧档无GRU键 → 容器保持
        # __init__随机初始化+W_gru零(行为位等价); 新档全量恢复
        if 'gruW_ih' in d:
            g = self.opp_gru
            g.W_ih, g.W_hh = d['gruW_ih'], d['gruW_hh']
            g.b_ih, g.b_hh = d['grub_ih'], d['grub_hh']
            g.W_proj = d['gruW_proj']
            self.W_gru = d['W_gru']
        else:
            if self.W_gru is None:
                self.W_gru = np.zeros((16, self.N_OUT), dtype=np.float32)
            print('[迁移] GRU序列记忆: 旧档 — 容器随机+W_gru零(位等价)')
        if self.W_opp.shape[1] != self.N_OUT:   # 宏库扩展同步扩列
            dm = self.N_OUT - self.W_opp.shape[1]
            self.W_opp = np.concatenate(
                [self.W_opp, np.zeros((self.OPP_H2, dm), dtype=np.float32)], axis=1)
        self._pi_adam = _Adam([self.W1, self.b1, self.W2, self.b2, self.W_side,
                               self.Ws1, self.bs1, self.Ws2, self.bs2,
                               self.Wo1, self.bo1, self.Wo2, self.bo2,
                               self.W_opp,
                               self.Wq1, self.bq1, self.Wq2, self.bq2,
                               self.Wc1, self.bc1, self.Wc2, self.bc2,
                               self.Wc3, self.bc3])
        # P0-A(第十轮): load路径曾漏W3v/b3v → _Adam 4槽被喂6梯度
        # → IndexError被train_tm吞掉 → 模型永不落盘(零学习根因)
        self._vf_adam = _Adam([self.W1v, self.b1v, self.W2v, self.b2v,
                               self.W3v, self.b3v])
        return self

    def _init_value(self, n_in):
        rng = np.random.default_rng(1)
        nv = n_in + self.N_SIDE + self.OPP_H2   # R17: 侧向量+对手表征16
        # 3层值头(自审: 2层值损130-1800, 归一化尺度应O(1)):
        # nv→HIDDEN→HIDDEN→1, 共享conv主干, 侧通路也进值头
        self.W1v = (rng.standard_normal((nv, self.HIDDEN)) / np.sqrt(nv)).astype(np.float32)
        self.b1v = np.zeros(self.HIDDEN, dtype=np.float32)
        self.W2v = (rng.standard_normal((self.HIDDEN, self.HIDDEN)) / np.sqrt(self.HIDDEN)).astype(np.float32)
        self.b2v = np.zeros(self.HIDDEN, dtype=np.float32)
        self.W3v = (rng.standard_normal(self.HIDDEN) / np.sqrt(self.HIDDEN)).astype(np.float32)
        self.b3v = np.zeros(1, dtype=np.float32)  # P1(§7.3): 保持0-d数组(标量形式params[i]+=不生效)
        self._pi_adam = _Adam([self.W1, self.b1, self.W2, self.b2, self.W_side,
                               self.Ws1, self.bs1, self.Ws2, self.bs2,
                               self.Wo1, self.bo1, self.Wo2, self.bo2,
                               self.W_opp,
                               self.Wq1, self.bq1, self.Wq2, self.bq2,
                               self.Wc1, self.bc1, self.Wc2, self.bc2,
                               self.Wc3, self.bc3])
        self._vf_adam = _Adam([self.W1v, self.b1v, self.W2v, self.b2v,
                               self.W3v, self.b3v])

    def save(self, pi_path, v_path):
        """P0-5修复: 原子写入(tmp+replace, 防止并发撕裂/进程被杀时半写损坏)
        R19(审查2026-10-02): 落盘前有限性校验 — NaN/Inf权重一旦落盘,
        下次加载即永久污染(特征NaN无拦截时代的最后防线)。"""
        import os as _os
        for _k in ("W1", "W2", "W_side", "Ws1", "Ws2", "Wo1", "Wo2",
                   "W_opp", "Wq1", "Wq2", "W1v", "W2v", "W3v",
                   "Wc1", "Wc2", "Wc3",
                   # R39(第十轮P3-9): 偏置向量原不在守卫内 — NaN偏置可穿
                   # 过"最后防线"毒化下次加载
                   "b1", "b2", "bs1", "bs2", "bo1", "bo2", "bq1", "bq2",
                   "b1v", "b2v", "b3v", "bc1", "bc2", "bc3"):
            _a = getattr(self, _k)
            if _a is None:
                continue
            if not np.all(np.isfinite(_a)):
                raise ValueError("save拒绝: %s含NaN/Inf — 查上游特征/梯度"
                                 % _k)
        _tp = pi_path + ".tmp"
        _tv = v_path + ".tmp"
        np.savez(_tp, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2, W_side=self.W_side,
                 Ws1=self.Ws1, bs1=self.bs1, Ws2=self.Ws2, bs2=self.bs2,
                 Wo1=self.Wo1, bo1=self.bo1, Wo2=self.Wo2, bo2=self.bo2,
                 W_opp=self.W_opp, Wq1=self.Wq1, bq1=self.bq1,
                 Wq2=self.Wq2, bq2=self.bq2,
                 Wc1=self.Wc1, bc1=self.bc1, Wc2=self.Wc2, bc2=self.bc2,
                 Wc3=self.Wc3, bc3=self.bc3,
                 gruW_ih=self.opp_gru.W_ih, gruW_hh=self.opp_gru.W_hh,
                 grub_ih=self.opp_gru.b_ih, grub_hh=self.opp_gru.b_hh,
                 gruW_proj=self.opp_gru.W_proj, W_gru=self.W_gru,
                 meta=np.array([self._temp, self._beta, self._bcw,
                                float(self._updates), self._rstd,
                                getattr(self, '_adaptive_lr_scale', 1.0)], dtype=np.float32))
        np.savez(_tv, W1v=self.W1v, b1v=self.b1v, W2v=self.W2v, b2v=self.b2v, W3v=self.W3v, b3v=self.b3v)
        _os.replace(_tp + ".npz" if not _tp.endswith(".npz") else _tp, pi_path)
        _os.replace(_tv + ".npz" if not _tv.endswith(".npz") else _tv, v_path)

    # ---- 卷积主干(策略/价值共享): 像素14400 → 特征1280 ----
    def _trunk_fwd_chunked(self, X, chunk=4096):
        """纯前向分块(2026-09-22 OOM修复): N>256的全量前向(logp_old/V/KL检查)
        im2col中间矩阵达数百MiB, 三进程并发+异步更新下OOM。
        分块限峰≈70MB; 语义与_trunk完全一致(无cache需求的前向专用)。"""
        flats = [self._trunk(X[i:i + chunk])[0] for i in range(0, X.shape[0], chunk)]
        return np.concatenate(flats, axis=0)

    def _trunk(self, X):
        """X:(N,14400) → (flat(N,1280), cache)。三层conv, 复杂弹幕感知。
        3×60×80 → c1 16×58×78 → p 16×29×39 → c2 32×27×37 → 裁26×36 → p 32×13×18
        → c3 32×11×16 → 裁10×16 → p 32×5×8"""
        N = X.shape[0]
        Xn = X.astype(np.float32).reshape(N, 3, CONV_H, CONV_W) / 255.0
        cols1 = _im2col(Xn, 3, 3)
        c1 = (cols1 @ self.Wc1.T + self.bc1).reshape(N, 58, 78, CONV1_F).transpose(0, 3, 1, 2)
        a1 = np.maximum(c1, 0)
        p1, am1 = _maxpool2(a1)                     # 16×29×39
        cols2 = _im2col(p1, 3, 3)
        c2 = (cols2 @ self.Wc2.T + self.bc2).reshape(N, 27, 37, CONV2_F).transpose(0, 3, 1, 2)
        a2 = np.maximum(c2, 0)[:, :, :26, :36]      # 裁奇数维(池化需偶数)
        p2, am2 = _maxpool2(a2)                     # 32×13×18
        cols3 = _im2col(p2, 3, 3)
        c3 = (cols3 @ self.Wc3.T + self.bc3).reshape(N, 11, 16, CONV3_F).transpose(0, 3, 1, 2)
        a3 = np.maximum(c3, 0)[:, :, :10, :]        # 裁奇数维
        p3, am3 = _maxpool2(a3)                     # 32×5×8
        return p3.reshape(N, TRUNK_FLAT), (cols1, c1, am1, cols2, c2, am2, cols3, c3, am3)

    def _trunk_bwd(self, cache, dflat):
        """dflat:(N,1280) → [dWc1,dbc1,dWc2,dbc2,dWc3,dbc3](策略+价值梯度先累加进 dflat)。"""
        cols1, c1, am1, cols2, c2, am2, cols3, c3, am3 = cache
        N = dflat.shape[0]
        dp3 = dflat.reshape(N, CONV3_F, 5, 8)
        da3c = _unpool2(dp3, am3)                   # (N,32,10,16)
        da3 = np.zeros((N, CONV3_F, 11, 16), dtype=dflat.dtype)
        da3[:, :, :10, :] = da3c                    # 被裁维梯度为0
        dc3 = (da3 * (c3 > 0)).transpose(0, 2, 3, 1).reshape(-1, CONV3_F)
        dWc3 = (cols3.T @ dc3).T
        dbc3 = dc3.sum(0)
        dcols3 = dc3 @ self.Wc3
        dp2 = _col2im(dcols3, N, CONV2_F, 13, 18, 3, 3)
        da2c = _unpool2(dp2, am2)                   # (N,32,26,36) 裁剪区
        da2 = np.zeros((N, CONV2_F, 27, 37), dtype=dflat.dtype)
        da2[:, :, :26, :36] = da2c                  # 被裁维梯度为0
        dc2 = (da2 * (c2 > 0)).transpose(0, 2, 3, 1).reshape(-1, CONV2_F)
        dWc2 = (cols2.T @ dc2).T
        dbc2 = dc2.sum(0)
        dcols2 = dc2 @ self.Wc2
        dp1 = _col2im(dcols2, N, CONV1_F, 29, 39, 3, 3)
        da1 = _unpool2(dp1, am1)
        dc1 = (da1 * (c1 > 0)).transpose(0, 2, 3, 1).reshape(-1, CONV1_F)
        dWc1 = (cols1.T @ dc1).T
        dbc1 = dc1.sum(0)
        return [dWc1, dbc1, dWc2, dbc2, dWc3, dbc3]

    # ---- 前向 ----
    def _opp_fwd(self, S):
        """R17③对手子网络: 侧向量对手建模切片(75)→32→16紧凑表征。
        返回(h1, h2); h2拼进策略logits/值头输入/预测头输入。"""
        o = 2 * self.N_OUT + self.OPP_CORE_OFF
        So = S[:, o:o + self.OPP_DIM]
        h1 = np.maximum(0, So @ self.Wo1 + self.bo1)
        return h1, np.maximum(0, h1 @ self.Wo2 + self.bo2)

    def _pi_forward(self, X, S=None, temp=1.0, mask=None, bias=None,
                    gru_repr=None):
        """bias: 采样侧乐观先验(新宏探索加成, 不进更新 — 行为层机制, 同强制探针先例)"""
        """返回 (主干特征, 隐层, 概率)。logit封顶: 防长期更新后权重膨胀→softmax饱和→熵死。
        N>256时用分块前向(峰值内存限流 — 异步更新三进程并发OOM修复)。"""
        if X.shape[0] > 256:
            Xn = self._trunk_fwd_chunked(X)
        else:
            Xn, _ = self._trunk(X)
        H = np.maximum(0, Xn @ self.W1 + self.b1)
        Z = H @ self.W2 + self.b2
        if S is not None:
            Z = Z + S @ self.W_side
            if self.Ws2 is not None:
                Z = Z + np.maximum(0, S @ self.Ws1 + self.bs1) @ self.Ws2 + self.bs2
            if self.W_opp is not None:
                Z = Z + self._opp_fwd(S)[1] @ self.W_opp
        if gru_repr is not None and self.W_gru is not None:
            # S-4: GRU序列表征(16,)→logits(零初始化=初始无影响)
            Z = Z + np.asarray(gru_repr, dtype=np.float32).reshape(1, -1)                 @ self.W_gru
        # 封顶最大logit差≤8(温度1.5下仍保分布响应); 保序只压幅度, 采样/更新同路径一致
        zmax = np.abs(Z).max(axis=1, keepdims=True)
        Z = Z / np.maximum(1.0, zmax / 8.0)
        if mask is not None:
            Z = Z + np.where(mask, 0.0, -1e9).astype(np.float32)
        if bias is not None:
            Z = Z + np.asarray(bias, dtype=np.float32).reshape(1, -1)
        return Xn, H, _softmax(Z / temp)

    def _pi_forward_c(self, X, S, temp=1.0, mask=None):
        """同上但附带主干反向缓存(训练用)。"""
        Xn, cache = self._trunk(X)
        H = np.maximum(0, Xn @ self.W1 + self.b1)
        Z = H @ self.W2 + self.b2 + S @ self.W_side
        Sh = None
        if self.Ws2 is not None:
            Sh = np.maximum(0, S @ self.Ws1 + self.bs1)
            Z = Z + Sh @ self.Ws2 + self.bs2
        Oh1 = Oh = None
        if self.W_opp is not None:
            Oh1, Oh = self._opp_fwd(S)
            Z = Z + Oh @ self.W_opp
        zmax = np.abs(Z).max(axis=1, keepdims=True)
        # R38(第九轮审计P2-2): cap随缓存返回 — 反向须补1/s缩放
        # (前向Z/s, 反向dZ_raw=dZ_cap/s; 原缺失使封顶激活行的梯度
        #  幅度系统性偏大)
        cap = np.maximum(1.0, zmax / 8.0)
        zraw = Z
        Z = Z / cap
        if mask is not None:
            Z = Z + np.where(mask, 0.0, -1e9).astype(np.float32)
        # 审计#3 P1-5②: zraw随返 — 封顶反向需要(原只回cap, 反向只能
        # 补1/cap, zmax行的dz项缺失 → 与torch autograd不等价)
        return Xn, H, _softmax(Z / temp), cache, Sh, Oh1, Oh, cap, zraw

    def _v_forward(self, Xn, S=None):
        """R17③: 值头输入=[trunk | 侧向量 | 对手表征16] — 对手建模同样
        进critic(读对对手=读不准价值)。"""
        if S is None:
            S = np.zeros((Xn.shape[0], self.N_SIDE), dtype=np.float32)
        Oh = self._opp_fwd(S)[1] if self.W_opp is not None else np.zeros(
            (Xn.shape[0], self.OPP_H2), dtype=np.float32)
        Xn = np.concatenate([Xn, S, Oh], axis=1)
        H1v = np.maximum(0, Xn @ self.W1v + self.b1v)
        H2v = np.maximum(0, H1v @ self.W2v + self.b2v)
        return H2v, H2v @ self.W3v + self.b3v, H1v

    def _pi_forward_batch(self, X, S=None, temp=1.0, mask=None, chunk=4096):
        """分块_pi_forward(修im2col内存爆炸: 1500样本×新conv≈3GB中间矩阵)。
        只用于无cache的前向(old-logp/KL/初始值) — minibatch内的带cache前向不受影响。"""
        N = X.shape[0]
        if N <= chunk:
            Xn, _, P = self._pi_forward(X, S, temp, mask=mask)
            return Xn, P
        Xns, Ps = [], []
        for i0 in range(0, N, chunk):
            xb = X[i0:i0 + chunk]
            sb = S[i0:i0 + chunk] if S is not None else None
            mb = mask[i0:i0 + chunk] if mask is not None else None
            Xn_b, _, P_b = self._pi_forward(xb, sb, temp, mask=mb)
            Xns.append(Xn_b)
            Ps.append(P_b)
        return np.concatenate(Xns), np.concatenate(Ps)

    def sample(self, feat, side=None, temp=None, mask=None, bias=None,
               return_pred=False, gru_repr=None):
        """采样动作。return_pred=True(S-3预测回流): 附带
        (top1宏idx, top1概率) — 策略可读"我要出什么(置信多少)",
        写入特征维5-6供反预期/变招接口。"""
        t = self._temp if temp is None else temp
        s = side.reshape(1, -1) if side is not None else None
        m = mask.reshape(1, -1) if mask is not None else None
        _, _, P = self._pi_forward(feat.reshape(1, -1), s, temp=t, mask=m,
                                   bias=bias, gru_repr=gru_repr)
        a = int(self.rng.choice(self.N_OUT, p=P[0]))
        if return_pred:
            top1 = int(np.argmax(P[0]))
            return a, (top1, float(P[0][top1]))
        return a

    # ---- 更新 ----
    def update(self, feats, acts, rewards, sides, ep_lens, ep_terms=None,
               ep_first=None, bc_targets=None, bc_mask=None, temp=1.0, masks=None,
               bc_extra=None, opp_next=None, stored_logp=None):
        """acts = 宏 ID 数组; bc_targets = 专家宏 ID; masks = (N,N_OUT)物理可达掩码
        (True=允许)。采样与更新同掩码 — logp_old 与行为策略一致, PPO 语义干净。
        bc_extra = (Xe, Se, Ye): 神谕专家行(npz), 混入批量做纯BC梯度(adv=0,
        ratio=1 → PPO项零贡献; 既有BC损失机制自动拉引)。
        opp_next = (N,)int64: R17④对手下一决策拍动作类(action//128)标签,
        -1=未知(BC-extra行/末决策) → 该行不计辅助损失。
        stored_logp = (N,)float: R60(F-11)采样时记录的行为策略logP(a)
        (含探针/bias/价值引导的实际行为分布) — 提供时episode行用它做
        logp_old(真重要性比), 未提供时按现状重算(兼容)。"""
        X = np.stack(feats).astype(np.float32)
        A = np.asarray(acts, dtype=np.int64)
        S = np.stack(sides).astype(np.float32)
        R = np.asarray(rewards, dtype=np.float32)
        B = np.asarray(bc_targets, dtype=np.int64) if bc_targets is not None else None
        M = np.asarray(masks, dtype=bool) if masks is not None else None
        Q = np.asarray(opp_next, dtype=np.int64) if opp_next is not None else None
        N = len(R)

        sd = float(R.std())
        if sd > 1e-6:
            self._rstd = 0.8 * self._rstd + 0.2 * sd
        R = R / (self._rstd + 1e-6)

        # 性能优化: trunk只算一次, value和logp共享
        Xn, _ = self._pi_forward_batch(X, S, temp, mask=M)
        _, V, _ = self._v_forward(Xn, S)
        V = V.ravel()
        Vf = None
        if ep_first is not None:
            fxs = [f for (f, _s) in ep_first if f is not None]
            fss = [s for (_f, s) in ep_first if s is not None]
            if fxs:
                Xf = np.stack(fxs).astype(np.float32)
                Sf = np.stack(fss).astype(np.float32)
                Xfn, _, _ = self._pi_forward(Xf, Sf, temp)
                # R60-N1(第二十轮): _v_forward返回3元组 — 原双解包
                # ValueError(潜伏: 生产无ep_first调用者, 从零审查N1)
                _, Vfull, _ = self._v_forward(Xfn, Sf)
                Vf = Vfull.ravel()

        # R14-P0J: 防奖励-动作错位的结构性断言
        assert sum(ep_lens) == len(R), \
            "ep_lens总和%d != R长度%d (奖励-动作错位!)" % (sum(ep_lens), len(R))
        adv = np.zeros(N, dtype=np.float32)
        start = 0
        for i, L in enumerate(ep_lens):
            end = start + L
            vseg = V[start:end]
            terminal = bool(ep_terms[i]) if ep_terms is not None else True
            if terminal:
                tail = 0.0
            elif Vf is not None and i + 1 < len(ep_lens):
                tail = Vf[i + 1]
            else:
                # P1-3设计决定(2026-09-21): 本通道每批=单局独立对局, 跨局
                # bootstrap会耦合无关MDP轨迹 → 截断尾用V(末决策态)自举,
                # 不传ep_first。连续流场景才需要下一局首态。
                tail = vseg[-1]
            vnext = np.append(vseg[1:], tail)
            delta = R[start:end] + self.GAMMA * vnext - vseg
            acc = 0.0
            for j in range(L - 1, -1, -1):
                acc = delta[j] + self.GAMMA * self.LAM * acc
                adv[start + j] = acc
            start = end
        ret = adv + V
        adv = (adv - adv.mean()) / (adv.std() + 1e-6)

        # R35(差距#4-B): 经验回放 — 高优势样本(|adv|>1σ)跨批重用20%
        # on-policy PPO 1epoch后丢弃=浪费; 重用好经验减30-50%所需局数
        # (第九轮审计P0-4修复: 原(a)`X[_hi][_cap:]`切片方向反 — 高优样本数
        #  ≤cap时池恒空, 特性从未生效; (b)回放行未拼mask → 前向广播爆炸被
        #  异步线程except吞掉 → 更新静默丢失; (c)logp_old取当前策略→ratio≡1。
        #  修复: 按|adv|降序取前cap; 池存mask与保存时logp_old → 回放行带
        #  真重要性ratio, PPO clip正常生效(小比例off-policy重用的标准语义))
        N0 = N    # 本批episode行数(入池只用新数据, 防回放行反复入池)
        _hi_idx = np.where(np.abs(adv) > 1.0)[0]
        _replay = getattr(self, '_replay_buf', None)
        _rp_n = 0
        if _replay is not None and len(_replay[0]) > 0:
            _rp_n = min(len(_replay[0]), max(1, N // 5))   # 20%混入
            _ridx = self.rng.choice(len(_replay[0]), size=_rp_n, replace=False)
            _rows = [_replay[k][_ridx] for k in range(8)]
            X = np.concatenate([X, _rows[0]])
            S = np.concatenate([S, _rows[1]])
            A = np.concatenate([A, _rows[2]])
            R = np.concatenate([R, _rows[3]])
            adv = np.concatenate([adv, _rows[4]])
            ret = np.concatenate([ret, _rows[5]])
            if M is None:
                M = np.ones((N0, self.N_OUT), dtype=bool)
            M = np.concatenate([M, _rows[6]])
            if B is not None:   # 回放行BC目标=自身动作(同episode行自模仿语义)
                B = np.concatenate([B, _rows[2]])
            if Q is not None:   # 回放行无下一拍对手标签 → -1跳过辅助损失
                Q = np.concatenate([Q, -np.ones(_rp_n, dtype=np.int64)])
            if bc_mask is not None and bc_mask.ndim == 2:
                # 回放行不吃BC梯度(旧经验不重复自模仿)
                bc_mask = np.concatenate(
                    [bc_mask, np.zeros((_rp_n, self.N_OUT), np.float32)])
            N = len(R)

        # BC-extra混入: 专家行追加到批量尾 — adv=0(无PPO梯度),
        # logp_old=当前策略(ratio=1), BC目标=专家宏. 既有BC损失自动生效.
        if bc_extra is not None:
            Xe, Se, Ye = bc_extra
            Xe = np.asarray(Xe, dtype=np.float32)
            Se = np.asarray(Se, dtype=np.float32)
            Ye = np.asarray(Ye, dtype=np.int64)
            Ne = len(Ye)
            _, Pe = self._pi_forward_batch(Xe, Se, temp)
            logp_e = np.log(np.clip(Pe[np.arange(Ne), Ye], 1e-8, 1.0))
            X = np.concatenate([X, Xe])
            S = np.concatenate([S, Se])
            A = np.concatenate([A, Ye])       # BC目标兼做A(logp行取值用)
            R = np.concatenate([R, np.zeros(Ne, dtype=np.float32)])
            adv = np.concatenate([adv, np.zeros(Ne, dtype=np.float32)])
            # P0-D: 专家行ret=当前V(自洽,不拉向0)
            _, Ve, _ = self._v_forward(
                self._trunk(Xe.reshape(-1, 3, CONV_H, CONV_W))[0], Se)
            ret = np.concatenate([ret, Ve.ravel()])
            onehot = None   # 在下方重建
            if B is not None:
                B = np.concatenate([B, Ye])
            else:
                # episode行无BC目标 → 用自身动作A(自模仿正则, 避免B=-1的
                # tgt[..., -1]错索引最后一个宏的bug)
                B = np.concatenate([A, Ye])
                if bc_mask is None:
                    bc_mask = np.ones((N + Ne, self.N_OUT), dtype=np.float32)
            if M is not None:
                M = np.concatenate([M, np.ones((Ne, self.N_OUT), dtype=bool)])
            else:
                M = np.ones((N + Ne, self.N_OUT), dtype=bool)  # 2-D修广播bug(不改变episode行为:
                # episode行原本无掩码=全放行, 现在也全放行)
            if bc_mask is not None and bc_mask.ndim == 2:
                bc_mask = np.concatenate([bc_mask,
                                          np.ones((Ne, self.N_OUT),
                                                  dtype=np.float32)])
            if Q is not None:   # R17④: 专家行无下一拍标签 → -1跳过辅助损失
                Q = np.concatenate([Q, -np.ones(Ne, dtype=np.int64)])
            N = N + Ne

        # 旧行为对数概率(固定, 与采样同掩码)
        _, P0 = self._pi_forward_batch(X, S, temp, mask=M)
        logp_old = np.log(np.clip(P0[np.arange(N), A], 1e-8, 1.0))
        # R60(F-11): 采样时记录的行为策略logp优先(探针/bias/价值引导
        # 的实际分布入ratio — 原按π(mask,temp)重算对~40%决策有偏)
        if stored_logp is not None:
            _sl = np.asarray(stored_logp, dtype=np.float32)
            assert len(_sl) == N0, (
                "stored_logp长度%d≠episode行数%d" % (len(_sl), N0))
            logp_old[:N0] = _sl
        if _rp_n:
            # 回放行: 用保存时策略的logp → ratio=π_new/π_save (真重要性)
            logp_old[N0:N0 + _rp_n] = _rows[7]
        if bc_extra is not None:
            logp_old[N - Ne:] = logp_e   # 专家行: 当前策略(经验证的ratio=1)
        # 保存高优势样本供下批回放(须在logp_old算好后 — 池存保存时策略logp;
        # 按|adv|降序取前cap, 原[_cap:]切片为P0-4(a)修复点)
        # R39(第十轮§2-2): 原`<_N0`条件使全批皆高优势(小偏斜批)时池永不
        # 刷新 — 拿掉(cap已限尺寸); R39(§2-1): masks=None的裸update()调用
        # 会对None下标 → 兜底存全放行mask
        if len(_hi_idx) > 0:
            _cap = min(500, len(_hi_idx))    # 回放池上限
            _ord = _hi_idx[np.argsort(-np.abs(adv[_hi_idx]))[:_cap]]
            _Mo = M[_ord] if M is not None else np.ones(
                (len(_ord), self.N_OUT), dtype=bool)
            self._replay_buf = (X[_ord], S[_ord], A[_ord], R[_ord],
                                adv[_ord], ret[_ord], _Mo, logp_old[_ord])
        # 注(R39·第十轮§2-3): 回放行的adv/ret沿用保存批的归一化统计
        # (旧rstd/均值) — 与新批量纲混用为已知取舍: ratio侧已正确(保存时
        # logp), 价值目标为陈旧尺度, 等效轻度AWR式行为正则而非纯PPO。
        onehot = np.zeros((N, self.N_OUT), dtype=np.float32)
        onehot[np.arange(N), A] = 1.0

        value_losses = []
        pi_losses = []
        aux_losses = []
        aux_hits = 0
        aux_n = 0
        kl = 0.0
        stopped = False
        for _ in range(self.EPOCHS):
            order = self.rng.permutation(N)
            for i0 in range(0, N, self.MINIBATCH):
                idx = order[i0:i0 + self.MINIBATCH]
                xb, ab1, sb = X[idx], onehot[idx], S[idx]
                advb, retb = adv[idx], ret[idx]
                mb = M[idx] if M is not None else None
                xbn, H, P, cache, Sh, Oh1, Oh, cap, zraw = self._pi_forward_c(
                    xb, sb, temp, mask=mb)
                logp = np.log(np.clip(P[np.arange(len(idx)), A[idx]], 1e-8, 1.0))
                diff = np.clip(logp - logp_old[idx], -20.0, 20.0)
                ratio = np.exp(diff)
                surr1 = ratio * advb
                surr2 = np.clip(ratio, 1 - self.CLIP, 1 + self.CLIP) * advb
                active = (surr1 <= surr2)
                # 从零#2(统计对齐): pi_loss仪表值(GPU版同键 — sum归约)
                pi_losses.append(float(-np.minimum(surr1, surr2).sum()))
                dz = (ab1 - P) * (advb * ratio * active)[:, None]
                # P0-1修复: 熵梯度符号 — code曾产出-dH/dz, 现修正为+dH/dz
                # dH/dz_i = -p_i*(log p_i + H), 取负号使maximize=True时最大化H
                ent_grad = -P * (np.log(np.clip(P, 1e-8, 1.0))
                                 + (-(np.log(np.clip(P, 1e-8, 1.0)) * P).sum(1, keepdims=True)))
                dz += self._beta * ent_grad
                if B is not None:
                    tgt = np.zeros((len(idx), self.N_OUT), dtype=np.float32)
                    tgt[np.arange(len(idx)), B[idx]] = 1.0
                    # P1-2修复: BC按当拍掩码; bc_mask可为(n_out,)或(N,n_out)
                    # 从零#2(等价探针发现): bc_mask=None+bc_targets给定
                    # 时原直接.ndim即AttributeError — None=全行吃BC
                    _bm = (bc_mask[idx] if bc_mask.ndim == 2
                           else bc_mask) if bc_mask is not None else 1.0
                    dz -= self._bcw * (P - tgt) * _bm
                # P1-2修复: dz按掩码归零(masked宏的logit不动)
                if mb is not None:
                    dz = dz * mb
                dz /= temp
                # R38(P2-2)+审计#3 P1-5②: 封顶反传完整版 — 逐行cap=
                # zmax/8时, zmax所在列有额外dz项(torch autograd天然含,
                # 原只补1/cap → conv主干/对手子网梯度大面积反号):
                # dz_raw[m] -= (dz_capped·z_raw)·sign(z_raw[m])/(8·cap²)
                dz = _cap_backward(dz, cap, zraw)

                dW2 = H.T @ dz
                db2 = dz.sum(0)
                dh = dz @ self.W2.T * (H > 0)
                dW1 = xbn.T @ dh
                db1 = dh.sum(0)
                dW_side = sb.T @ dz
                # 侧通路非线性头反向(连续化): dz → Ws2 → ReLU → Ws1
                if Sh is not None:
                    dWs2 = Sh.T @ dz
                    dbs2 = dz.sum(0)
                    dSh = dz @ self.Ws2.T * (Sh > 0)
                    dWs1 = sb.T @ dSh
                    dbs1 = dSh.sum(0)
                else:
                    dWs1 = np.zeros_like(self.Ws1)
                    dbs1 = np.zeros_like(self.bs1)
                    dWs2 = np.zeros_like(self.Ws2)
                    dbs2 = np.zeros_like(self.bs2)

                # R17④对手动作预测辅助损失: q=[trunk|对手表征16]→32→8类
                # (标签=下一拍对手动作类; 梯度经q_in回流trunk与对手子网络,
                # 迫使两路都编码"对手将要做什么")
                dWq1 = dbq1 = dWq2 = dbq2 = None
                dq_in = None
                if Q is not None and Oh is not None:
                    yb = Q[idx]
                    qv = yb >= 0
                    nq = int(qv.sum())
                    if nq > 0:
                        q_in = np.concatenate([xbn, Oh], axis=1)
                        Hq = np.maximum(0, q_in @ self.Wq1 + self.bq1)
                        Pq = _softmax(Hq @ self.Wq2 + self.bq2)
                        yclip = np.clip(yb, 0, self.N_OPP_CLS - 1)
                        aux_losses.append(float(
                            -(np.log(np.clip(Pq[np.arange(len(idx)), yclip],
                                            1e-8, 1.0)) * qv).sum() / nq))
                        aux_hits += int((Pq.argmax(1) == yclip)[qv].sum())
                        aux_n += nq
                        tgtq = np.zeros((len(idx), self.N_OPP_CLS),
                                        dtype=np.float32)
                        tgtq[np.arange(len(idx)), yclip] = 1.0
                        # 最小化方向×AUX_W, 按有效行数归一(与价值损失同尺度)
                        dq = (Pq - tgtq) * qv[:, None] * (self.AUX_W / nq)
                        dWq2 = Hq.T @ dq
                        dbq2 = dq.sum(0)
                        dHq = dq @ self.Wq2.T * (Hq > 0)
                        dWq1 = q_in.T @ dHq
                        dbq1 = dHq.sum(0)
                        dq_in = dHq @ self.Wq1.T

                vin = np.concatenate(
                    [xbn, sb, Oh if Oh is not None else
                     np.zeros((len(idx), self.OPP_H2), dtype=np.float32)], axis=1)
                H2v, Vv, H1v = self._v_forward(xbn, sb)
                Vv = Vv.ravel()
                value_losses.append(float(((Vv - retb) ** 2).mean()))
                dv = (Vv - retb) / len(idx)
                # 3层反向: dv → W3v → H2v → W2v → H1v → W1v
                dW3v = H2v.T @ dv
                db3v = dv.sum()
                dH2v = dv[:, None] * self.W3v[None, :] * (H2v > 0)
                dW2v = H1v.T @ dH2v
                db2v = dH2v.sum(0)
                dH1v = dH2v @ self.W2v.T * (H1v > 0)
                dW1v = vin.T @ dH1v
                db1v = dH1v.sum(0)
                # 审计#3 P1-5①: dvin必须用step**前**的W1v — 原版
                # vf_adam.step先执行, 下方dH1v@W1v.T混用已更新权重
                # (旧dH1v×新W1v, 与torch单步计算图不等价)
                dvin = dH1v @ self.W1v.T
                # 梯度全局范数裁剪(值头): 防大损失步的梯度爆炸
                _vg = [dW1v, db1v, dW2v, db2v, dW3v, db3v]
                _vn = np.sqrt(sum(float((g ** 2).sum()) for g in _vg))
                if _vn > 10.0:
                    _scale = 10.0 / _vn
                    _vg = [g * _scale for g in _vg]
                # P1-11(从零#5): 卷积主干反传必须用 **step 前** 的 W1v —
                # 原版在 vf_adam.step **之后** 用 self.W1v 反传价值路(第991行),
                # 即"旧 dH1v × 新 W1v", 与 torch 单步计算图不等价:
                # 审计实测 conv1/2/3 的梯度 cos=0.396/0.637/0.564(范数相同、方向不同),
                # 一步整步 W1 cos=0.785, value_loss numpy 20.36 vs GPU 15.67。
                # 注: 只影响 numpy 实现(ppo_gpu 走 autograd), 即单机 train_tm/剥削者。
                _W1v_pre = self.W1v.copy()
                self._vf_adam.step(_vg, self.VF_LR, maximize=False)

                # R17③对手子网络反向: 三路汇合(全部转上升约定 — _pi_adam
                # maximize=True): 策略路+ · 价值路−(下降) · 辅助路−(下降),
                # 过Oh的ReLU后回传两层
                if Oh is not None:
                    dOh = dz @ self.W_opp.T \
                        - dvin[:, TRUNK_FLAT + self.N_SIDE:]
                    if dq_in is not None:
                        dOh = dOh - dq_in[:, TRUNK_FLAT:]
                    dOh = dOh * (Oh > 0)
                    dWo2 = Oh1.T @ dOh
                    dbo2 = dOh.sum(0)
                    dOh1 = dOh @ self.Wo2.T * (Oh1 > 0)
                    _o_off = 2 * self.N_OUT + self.OPP_CORE_OFF
                    So = sb[:, _o_off:_o_off + self.OPP_DIM]
                    dWo1 = So.T @ dOh1
                    dbo1 = dOh1.sum(0)
                    dW_opp = Oh.T @ dz
                    if dWq1 is None:
                        dWq1 = np.zeros_like(self.Wq1)
                        dbq1 = np.zeros_like(self.bq1)
                        dWq2 = np.zeros_like(self.Wq2)
                        dbq2 = np.zeros_like(self.bq2)
                else:
                    dWo1 = np.zeros_like(self.Wo1)
                    dbo1 = np.zeros_like(self.bo1)
                    dWo2 = np.zeros_like(self.Wo2)
                    dbo2 = np.zeros_like(self.bo2)
                    dW_opp = np.zeros_like(self.W_opp)
                    dWq1 = np.zeros_like(self.Wq1)
                    dbq1 = np.zeros_like(self.bq1)
                    dWq2 = np.zeros_like(self.Wq2)
                    dbq2 = np.zeros_like(self.bq2)

                # 卷积主干: 策略+价值+辅助三路梯度累加后一次反传(共享主干)
                # (价值/辅助=下降, 策略=上升 → 减号; P0-B先例)
                dflat = dh @ self.W1.T - (dH1v @ _W1v_pre.T)[:, :TRUNK_FLAT]
                if dq_in is not None:
                    dflat = dflat - dq_in[:, :TRUNK_FLAT]
                conv_grads = self._trunk_bwd(cache, dflat)
                # 辅助头参数梯度: 上面按下降方向算, 并入上升优化器须取负
                _pg = [dW1, db1, dW2, db2, dW_side,
                       dWs1, dbs1, dWs2, dbs2,
                       dWo1, dbo1, dWo2, dbo2, dW_opp,
                       -dWq1, -dbq1, -dWq2, -dbq2] + conv_grads
                _pn = np.sqrt(sum(float((g ** 2).sum()) for g in _pg))
                if _pn > 10.0:
                    _pg = [g * (10.0 / _pn) for g in _pg]
                self._pi_adam.step(_pg, self.PI_LR * self._adaptive_lr_scale,
                                   maximize=True)

            # R11§2: KL自适应学习率(替代无效早停)
            # R18(P0, 审查2026-10-02): 复检必须与参考同掩码 — 原版无mask,
            # 被禁宏的-1e9质量回流产生≈-log(1-q)重归一化伪影(实测读0.31
            # 而真实移动0.015, 20×), 自适应LR被钉死在下限=有效LR×1/10
            _kidx = self.rng.choice(N, size=min(500, N), replace=False)
            _, Pn_s = self._pi_forward_batch(
                X[_kidx], S[_kidx] if S is not None else None, temp,
                mask=M[_kidx] if M is not None else None)
            logp_new_s = np.log(np.clip(Pn_s[np.arange(len(_kidx)), A[_kidx]], 1e-8, 1.0))
            kl = float(np.abs(logp_old[_kidx] - logp_new_s).mean())  # 不可相消
            # R50(体检A1): 原缩条件TARGET_KL*1.5=0.045/回升条件TARGET_KL/3=0.01
            # → KL常驻0.01-0.045死区 → LR钉底0.1(三家全钉, 有效LR=3e-5)。
            # 修: 回升条件从KL<TARGET/3改到KL<TARGET(0.03), 地板0.1→0.3
            # — 死区从[0.01,0.045]缩到[0.03,0.045](正常KL 0.03-0.08
            # 大部分落在回升区), 学习速度恢复名义的30%起步。
            if kl > self.TARGET_KL * 1.5:
                self._adaptive_lr_scale = max(0.3,
                    self._adaptive_lr_scale / 1.5)
                print("[KL-adapt] KL=%.4f > 1.5×目标 → LR缩至%.2f" % (
                    kl, self._adaptive_lr_scale))
            elif kl < self.TARGET_KL:
                self._adaptive_lr_scale = min(3.0,
                    self._adaptive_lr_scale * 1.2)
            if kl > self.TARGET_KL:
                stopped = True

        _fidx = self.rng.choice(N, size=min(500, N), replace=False)
        # R18(P0): 熵诊断同掩码 — 原版读的是"含被禁宏质量"的未掩码熵,
        # 与采样/更新所用的行为分布不一致(历轮熵读数均受此偏差)
        _, Pn_s = self._pi_forward_batch(
            X[_fidx], S[_fidx] if S is not None else None, temp,
            mask=M[_fidx] if M is not None else None)
        Pc = np.clip(Pn_s, 1e-8, 1.0)
        ent = float(-(Pc * np.log(Pc)).sum(1).mean())
        self._updates += 1
        self._beta = max(self.BETA_ENT_MIN, self._beta * self.ENT_DECAY)
        self._temp = max(0.5, self._temp * self.ENT_DECAY)  # 自审: 原下限1.0+初值1.0=退火死锁(熵3.0≈均匀), 放开到0.7让分布渐尖
        self._bcw = max(self.BC_W_MIN, self._bcw * self.ENT_DECAY)
        return {"return": float(ret.mean()), "entropy": ent, "kl": kl,
                "pi_loss": (float(np.mean(pi_losses))
                            if pi_losses else 0.0),
                "value_loss": float(np.mean(value_losses)) if value_losses else 0.0,
                "kl_stopped": stopped, "beta": self._beta, "temp": self._temp,
                "bcw": self._bcw,
                # R17④: 对手动作预测辅助(损失/命中率 — 命中率显著高于
                # 先验占比=模型真的在读对手; 12.5%=均匀基线)
                "aux_loss": (float(np.mean(aux_losses))
                             if aux_losses else None),
                "aux_acc": (aux_hits / aux_n if aux_n > 0 else None),
                # 第八轮§4: 学习健康度 — KL≈0既可能是收敛也可能是停摆,
                # 配优势幅度/价值损失才能区分
                "adv_abs": float(np.abs(adv).mean()), "kl_abs": abs(kl)}
