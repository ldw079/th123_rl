# -*- coding: utf-8 -*-
"""最小感知层: 区域像素差异检测 + BMP 帧保存。

M0 只做一件事: 证明"画面上发生的事能被程序看到"。
HP 条区域变化 → 输出命中事件; 后续 M1 再扩展成完整状态提取(位置/灵槽/天气/弹幕)。
"""

import struct


def frame_features(frame, w, h, fw=80, fh=60):
    """把 BGRA 帧转成灰度小图(默认 80x60, 弹幕3~4px可辨), conv主干输入。
    区域均值下采样: 跳采会随机丢弹(弹幕落在采样缝里就不可见)。
    按实际字节数推回真实宽高(窗口尺寸漂移时传入的w/h可能失真)。"""
    import numpy as np
    real_h = len(frame) // 4 // w
    if real_h < 1 or len(frame) != 4 * w * real_h:   # w也失真: 尝试宽高互换布局
        real_h = h
        w = len(frame) // 4 // h
    h = real_h
    img = np.frombuffer(frame, dtype=np.uint8).reshape(h, w, 4)
    gray = (img[:, :, 0].astype(np.uint16) * 29
            + img[:, :, 1].astype(np.uint16) * 150
            + img[:, :, 2].astype(np.uint16) * 77) >> 8
    bh, bw = max(1, h // fh), max(1, w // fw)
    g2 = gray[:fh * bh, :fw * bw].reshape(fh, bh, fw, bw).mean(axis=(1, 3))
    return g2.astype(np.uint8).ravel()


# ---- HP 条自动检测(2026-09-02 实测本整合包 HUD) ----
# 顶部两条大黄色横条: 左=P1, 右=P2; 条内红色段=刚损失的血。
# 坐标按客户区比例给出, 与窗口缩放无关(2x 缩放下自动适配)。
HP_BAR_Y = (0.070, 0.110)
HP_BAR_LEFT_X = (0.013, 0.344)
HP_BAR_RIGHT_X = (0.363, 0.794)


def _hp_yellow(b, g, r):
    """黄条判定(色调相对判据): 天气特效会整体压暗/偏色画面, 绝对阈值会被
    误判成掉血; 用通道比例(R、G 明显高于 B)可扛亮度型色调污染。"""
    return (r > 90) & (g > 80) & (r > 1.25 * b) & (g > 1.1 * b) & (r - b > 40)


def _hp_red(b, g, r):
    return (r > 110) & (r > 1.6 * g) & (r > 1.6 * b) & (g < 110)


def hp_counts(frame, w, h):
    """统计两条 HP 条的黄色/红色像素数, 返回 (左黄, 右黄, 左红, 右红)。"""
    try:
        import numpy as np
        img = np.frombuffer(frame, dtype=np.uint8).reshape(h, w, 4)
        y0, y1 = int(h * HP_BAR_Y[0]), int(h * HP_BAR_Y[1])
        lx0, lx1 = int(w * HP_BAR_LEFT_X[0]), int(w * HP_BAR_LEFT_X[1])
        rx0, rx1 = int(w * HP_BAR_RIGHT_X[0]), int(w * HP_BAR_RIGHT_X[1])
        strip = img[y0:y1]          # 先切片再算掩码, 避免整帧布尔运算

        def count(reg):
            b, g, r = reg[:, :, 0].astype(np.int16), reg[:, :, 1].astype(np.int16), reg[:, :, 2].astype(np.int16)
            # 色调相对判据: 天气特效整体压暗/偏色时, 绝对阈值会把血条误判成掉血
            yel = (r > 90) & (g > 80) & (r > 1.25 * b) & (g > 1.1 * b) & (r - b > 40)
            red = (r > 110) & (r > 1.6 * g) & (r > 1.6 * b) & (g < 110)
            return int(yel.sum()), int(red.sum())

        ly, lr = count(strip[:, lx0:lx1])
        ry, rr = count(strip[:, rx0:rx1])
        return ly, ry, lr, rr
    except ImportError:
        return _hp_counts_py(frame, w, h)


def _hp_counts_py(frame, w, h, stride=3):
    """无 numpy 时的纯 Python 兜底(抽样)。"""
    y0, y1 = int(h * HP_BAR_Y[0]), int(h * HP_BAR_Y[1])
    res = [0, 0, 0, 0]
    rects = ((int(w * HP_BAR_LEFT_X[0]), int(w * HP_BAR_LEFT_X[1]), 0, 2),
             (int(w * HP_BAR_RIGHT_X[0]), int(w * HP_BAR_RIGHT_X[1]), 1, 3))
    for yy in range(y0, y1, stride):
        base = yy * w * 4
        for (x0, x1, oy, orr) in rects:
            for xx in range(x0, x1, stride):
                i = base + xx * 4
                b, g, r = frame[i], frame[i + 1], frame[i + 2]
                if _hp_yellow(b, g, r):
                    res[oy] += 1
                elif _hp_red(b, g, r):
                    res[orr] += 1
    return tuple(res)


def changed_blobs(prev, frame, w, h, gh=24, gw=32, thresh=100):
    """帧差 + 网格聚类: 返回下半屏的变化块, 按面积降序 [(cx, cy, 格数), ...]。

    角色(含待机动画)、弹幕、天气特效都会产生变化; 角色块通常面积大且靠近地面。
    """
    import numpy as np
    a = np.frombuffer(prev, dtype=np.uint8).reshape(h, w, 4).astype(np.int16)
    b = np.frombuffer(frame, dtype=np.uint8).reshape(h, w, 4).astype(np.int16)
    diff = np.abs(a[:, :, :3] - b[:, :, :3]).sum(axis=2) > 60
    y0, y1 = int(h * 0.45), int(h * 0.92)   # 带宽些: 相机拉近时角色会升高
    d = diff[y0:y1]
    ch, cw = d.shape[0] // gh, d.shape[1] // gw
    if ch < 1 or cw < 1:
        return []
    d = d[:gh * ch, :gw * cw].reshape(gh, ch, gw, cw).sum(axis=(1, 3))
    mask = d > thresh
    seen = set()
    comps = []
    for i in range(gh):
        for j in range(gw):
            if mask[i, j] and (i, j) not in seen:
                stack = [(i, j)]
                seen.add((i, j))
                cells = []
                while stack:
                    ci, cj = stack.pop()
                    cells.append((ci, cj))
                    for ni, nj in ((ci + 1, cj), (ci - 1, cj), (ci, cj + 1), (ci, cj - 1)):
                        if 0 <= ni < gh and 0 <= nj < gw and mask[ni, nj] and (ni, nj) not in seen:
                            seen.add((ni, nj))
                            stack.append((ni, nj))
                if len(cells) >= 2:
                    cx = sum(cj for _, cj in cells) / len(cells) * cw + cw / 2
                    cy = y0 + (sum(ci for ci, _ in cells) / len(cells) * ch + ch / 2)
                    comps.append((cx, cy, len(cells)))
    comps.sort(key=lambda c: -c[2])
    return [c for c in comps if c[2] >= 3][:6]


class _Track:
    __slots__ = ("x", "y", "size", "first_seen", "last_seen", "xmin", "xmax")

    def __init__(self, x, y, size, now):
        self.x, self.y, self.size = x, y, size
        self.first_seen = self.last_seen = now
        self.xmin = self.xmax = x


class DualTracker:
    """双角色追踪(通用版: 双方都会移动, 如 VS COM)。

    连续性双目标跟踪: 变化块按大小降序认领最近的未认领轨迹(位置 EMA);
    own/opp 是两条固定轨迹的引用, 纯靠连续性跟随(角色交叉换位不丢身份)。
    回合开始时(角色回到左右出生点)由训练循环调用 reset() 重新锚定:
    最大的两条轨迹中左侧=己方, 右侧=对手。
    贴身: 两轨迹距离 < 60, 或任一丢失且存在大块(两角色重叠)。
    """

    GATE = 120.0
    TIMEOUT = 1.0
    MERGED_SIZE = 12     # 无 own/opp 轨迹时, 大于该格数的块 → 视为重叠

    def __init__(self, min_opp_x=0.0):   # min_opp_x 仅为兼容旧签名, 已不使用
        self.tracks = []
        self.own = None
        self.opp = None

    def reset(self):
        """回合开始时锚定: 最大两条轨迹, 左=己 右=敌。"""
        self.tracks.sort(key=lambda t: -t.size)
        big = [t for t in self.tracks if t.size >= 4][:2]
        if len(big) == 2:
            self.own, self.opp = sorted(big, key=lambda t: t.x)
        elif len(big) == 1:
            self.own, self.opp = big[0], None
        else:
            self.own = self.opp = None

    def hard_reset(self):
        """清空全部轨迹并解除锚定(进入静默期时调用: 静默期角色会瞬移,
        且静默期时钟冻结使轨迹超时失效, 旧轨迹只会污染重新锚定)。"""
        self.tracks = []
        self.own = None
        self.opp = None

    def update(self, blobs, now):
        claimed = set()
        for (cx, cy, sz) in blobs:                    # 已按大小降序
            best = None
            for t in self.tracks:
                if id(t) in claimed:
                    continue
                d = abs(t.x - cx)
                if d < self.GATE and (best is None or d < abs(best.x - cx)):
                    best = t
            if best is not None:
                best.x = best.x * 0.5 + cx * 0.5
                best.y = best.y * 0.5 + cy * 0.5
                best.size = sz
                best.last_seen = now
                best.xmin = min(best.xmin, cx)
                best.xmax = max(best.xmax, cx)
                claimed.add(id(best))
            else:
                self.tracks.append(_Track(cx, cy, sz, now))
        self.tracks = [t for t in self.tracks if now - t.last_seen < self.TIMEOUT]
        self.tracks.sort(key=lambda t: -t.size)
        del self.tracks[6:]
        if self.own is not None and self.own not in self.tracks:
            self.own = None
        if self.opp is not None and self.opp not in self.tracks:
            self.opp = None
        # 未锚定且存在稳定轨迹 → 惰性锚定:
        # own=最大者; opp=与 own 水平距离 >150px 的最大者(防止把角色旁的
        # 噪声块锚成对手, 造成"幻影贴身"常开惩罚)。找不到分离轨迹则暂不锚 opp。
        # (60fps 下木桩待机块在 3-4 格边缘抖动, 阈值放宽避免轨迹反复夭折)
        if self.own is None and self.opp is None:
            stable = [t for t in self.tracks
                      if t.size >= 3 and now - t.first_seen > 0.6]
            if stable:
                self.own = max(stable, key=lambda t: t.size)
                far = [t for t in stable if abs(t.x - self.own.x) > 150]
                if far:
                    self.opp = max(far, key=lambda t: t.size)

        own_x = self.own.x if self.own is not None else None
        opp_x = self.opp.x if self.opp is not None else None
        # 贴身只在双轨迹都在且距离 <60 时判定; 单侧丢失时不判(防幻影惩罚)
        if own_x is not None and opp_x is not None:
            close = abs(own_x - opp_x) < 60
        else:
            close = False
        return own_x, opp_x, close


# ---- 灵力珠(实测标定, 比例坐标; 每侧5颗, 锯齿排列, 满珠约320蓝像素) ----
SPIRIT_ORBS = {
    "left":  [(0.248, 0.283), (0.290, 0.325), (0.332, 0.368), (0.375, 0.410), (0.417, 0.452)],
    "right": [(0.548, 0.583), (0.590, 0.625), (0.632, 0.668), (0.675, 0.710), (0.717, 0.752)],
}
SPIRIT_Y = (0.915, 0.980)
SPIRIT_LIT_PX = 60      # 珠内蓝像素 > 该值视为亮


def spirit_level(frame, w, h, side="left"):
    """读灵力: 返回 (亮珠数/5, 每珠是否亮的列表)。"""
    import numpy as np
    img = np.frombuffer(frame, dtype=np.uint8).reshape(h, w, 4).astype(np.int16)
    y0, y1 = int(h * SPIRIT_Y[0]), int(h * SPIRIT_Y[1])
    band = img[y0:y1]
    b, g, r = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    blue = (b > 120) & (b - r > 40) & (b - g > 20)
    lit = []
    for (fx0, fx1) in SPIRIT_ORBS[side]:
        x0, x1 = int(w * fx0), int(w * fx1)
        lit.append(bool(blue[:, x0:x1].sum() > SPIRIT_LIT_PX))
    return sum(lit) / 5.0, lit


def frame_activity(prev, cur, w, h):
    """游戏区(去掉顶部HUD与底部灵力带)的帧间变化像素数 — 战斗激活门控用。
    防御: 帧缓冲尺寸漂移(窗口客户区抖动)时按实际字节推回宽高或跳过
    (本指标仅日志参考, 跳过无损)。"""
    import numpy as np
    need = w * h * 4
    if len(prev) != need or len(cur) != need:
        px = len(cur) // 4
        if px <= 0 or px != len(prev) // 4:
            return 0
        h2 = px // w if px % w == 0 else 0
        if h2 <= 0:
            return 0
        w, h = w, h2
    a = np.frombuffer(prev, dtype=np.uint8).reshape(h, w, 4).astype(np.int16)
    b = np.frombuffer(cur, dtype=np.uint8).reshape(h, w, 4).astype(np.int16)
    y0, y1 = int(h * 0.15), int(h * 0.90)
    d = np.abs(a[y0:y1, :, :3] - b[y0:y1, :, :3]).sum(axis=2) > 60
    return int(d.sum())


def region_diff(prev, cur, img_w, img_h, x0, y0, rw, rh, stride=1, thresh=24):
    """统计区域内相邻两帧的变化像素数与总差异。

    prev/cur: BGRA bytes; 区域会被裁剪到图像范围内。
    返回 (changed_pixels, total_diff)。
    """
    if prev is None or cur is None or rw <= 0 or rh <= 0:
        return 0, 0
    x1 = min(x0 + rw, img_w)
    y1 = min(y0 + rh, img_h)
    x0 = max(0, x0)
    y0 = max(0, y0)
    if x1 <= x0 or y1 <= y0:
        return 0, 0
    changed = total = 0
    for yy in range(y0, y1, stride):
        base = (yy * img_w + x0) * 4
        end = (yy * img_w + x1) * 4
        i = base
        while i < end:
            d = abs(prev[i] - cur[i]) + abs(prev[i + 1] - cur[i + 1]) + abs(prev[i + 2] - cur[i + 2])
            if d > thresh:
                changed += 1
            total += d
            i += 4 * stride
    return changed, total


def save_bmp(buf, w, h, path):
    """把 BGRA 帧保存为 32 位 BMP(可用画图打开, 用于标定坐标)。"""
    row_size = w * 4
    data = bytearray()
    for y in range(h - 1, -1, -1):          # BMP 行序自下而上
        data += buf[y * row_size:(y + 1) * row_size]
    file_size = 54 + len(data)
    header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 32, 0, len(data), 0, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(header)
        f.write(info)
        f.write(bytes(data))
