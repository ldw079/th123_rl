# -*- coding: utf-8 -*-
"""BC神谕数据对齐器(R38, 第九轮审计P0-5)。

问题: 状态流(mod实时回放, 开局含~65帧导入+每回合切换~90帧)与输入流
(rep文件解析)时间轴天然错位 — 实测互相关最优滞后+70~+240帧且**局内
漂移**(非全局常数)。原bc_build按原始下标配对frames[i]↔inputs[i] →
每行特征取自标签输入之前1~4秒的状态(系统性错标+未来信息泄漏)。

方法: 输入方向信号H(0x04/0x08位) ↔ 己方逐帧位移Δx 的滑窗互相关,
按回合段(HP回升边界)分段估计窗口滞后, 窗心线性插值成逐帧lag映射,
重排输入流使frames[i]↔u16[i]同拍。事后复检: 对齐后各窗|lag|须≤容差,
不过容差的窗口判无效(对应帧不产BC行)。

门禁哲学(R12测量纪律): 对齐是测量 — 无事后复检的对齐=不可信观测。
"""
import numpy as np

WIN = 1200          # 互相关窗宽(帧, ~19秒)
STEP = 600          # 窗步(50%重叠)
SCAN = 350          # 滞后扫描半径(帧)
PEAK_MIN = 0.06     # 峰值相关下限(低于=窗口不可靠)
POST_TOL = 24       # 对齐后复检容差(帧)


def h_signal(u16):
    """输入水平方向信号: 0x04=-1(左) / 0x08=+1(右) / 0=中性。"""
    return np.where((u16 & 0x04) != 0, -1.0,
                    np.where((u16 & 0x08) != 0, 1.0, 0.0)).astype(np.float64)


def round_bounds(frames):
    """回合边界: 任一方HP回升>500的帧索引(回合切换重置血条)。"""
    hp = np.array([f[0]['hp'] for f in frames], dtype=np.float32)
    return [i for i in range(1, len(hp)) if hp[i] > hp[i - 1] + 500]


def _corr_at(h, dx, s, k, w):
    """corr(h[s:s+w], dx[s+k:s+k+w]) — 不足样本返回nan。"""
    a = h[s:s + w]
    b = dx[s + k:s + k + w] if k >= 0 else None
    if k < 0:
        a = h[s - k:s + w - k]
        b = dx[s:s + w]
    n = min(len(a), len(b))
    if n < 300:
        return np.nan
    a = a[:n] - a[:n].mean()
    b = b[:n] - b[:n].mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-9 else np.nan


def window_lags(h, dx, lo, hi, win=WIN, step=STEP, scan=SCAN):
    """[lo,hi)段内滑窗估计滞后。返回[(center, lag, corr), ...](仅可靠窗)。"""
    out = []
    for s in range(lo, max(lo + 1, hi - win + 1), step):
        best, bestk = -2.0, None
        for k in range(-scan, scan + 1):
            if s + k < 0 or s + k + win > len(dx) or s + win > len(h):
                continue
            c = _corr_at(h, dx, s, k, win)
            if c == c and c > best:
                best, bestk = c, k
        if bestk is not None and best >= PEAK_MIN:
            out.append((s + win // 2, bestk, best))
    return out


def estimate_lag_map(frames, u16):
    """逐帧滞后映射与有效性。

    返回 (lag_map, valid): lag_map[j]=状态帧j对应输入下标的偏移
    (u16_true[j] = u16[j - lag_map[j]]); valid[j]=该帧对齐可信。
    按回合段独立估计(段内窗心线性插值, 段缘钳位到最近窗) — 滞后在
    回合边界是跳变(+90/次), 全局插值会把跳变抹成数百帧渐变。
    """
    n = len(frames)
    h = h_signal(u16[:n]) if len(u16) >= n else np.pad(
        h_signal(u16), (0, n - len(u16)))
    x = np.array([f[0]['position.x'] for f in frames], dtype=np.float64)
    dx = np.diff(x, prepend=x[0])

    segs = []
    b = 0
    for e in round_bounds(frames):
        if e - b > WIN // 2:
            segs.append((b, e))
        b = e
    if n - b > 0:
        segs.append((b, n))

    lag_map = np.zeros(n, dtype=np.float64)
    valid = np.zeros(n, dtype=bool)
    for lo, hi in segs:
        wins = window_lags(h, dx, lo, hi)
        if not wins:
            continue    # 整段无可靠窗(静止/杂讯) → 保持无效
        cs = np.array([w[0] for w in wins], dtype=np.float64)
        ks = np.array([w[1] for w in wins], dtype=np.float64)
        seg = np.arange(lo, hi)
        # np.interp段外自动钳到端点值(段缘常量外推)
        lag_map[lo:hi] = np.interp(seg, cs, ks)
        valid[lo:hi] = True
    lag_map = np.clip(np.rint(lag_map), -SCAN, SCAN).astype(np.int64)
    return lag_map, valid


def realign(u16, lag_map, valid):
    """按lag映射重排输入流: u16_al[j] = u16[j - lag[j]](越界=0中性)。"""
    n = len(lag_map)
    src = np.arange(n) - lag_map
    ok = valid & (src >= 0) & (src < len(u16))
    out = np.zeros(n, dtype=np.uint16)
    out[ok] = u16[src[ok]]
    return out


def post_validate(frames, u16_al, valid, win=WIN, step=STEP * 2):
    """对齐后复检: 可靠窗的残余滞后须≤POST_TOL, 否则该窗帧判无效。

    返回(有效掩码, 通过窗数, 总窗数)。"""
    n = len(frames)
    h = h_signal(u16_al)
    x = np.array([f[0]['position.x'] for f in frames], dtype=np.float64)
    dx = np.diff(x, prepend=x[0])
    v = valid.copy()
    n_ok = n_tot = 0
    for s in range(0, max(1, n - win + 1), step):
        w_lo, w_hi = s, min(s + win, n)
        if w_hi - w_lo < 300:
            continue
        n_tot += 1
        best, bestk = -2.0, 0
        for k in range(-POST_TOL * 2, POST_TOL * 2 + 1):
            if s + k < 0 or s + k + win > len(dx):
                continue
            c = _corr_at(h, dx, s, k, win)
            if c == c and c > best:
                best, bestk = c, k
        if abs(bestk) <= POST_TOL and best >= PEAK_MIN:
            n_ok += 1
        else:
            v[w_lo:w_hi] = False
    return v, n_ok, n_tot
