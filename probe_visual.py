# -*- coding: utf-8 -*-
"""视觉供帧健康探针: 对运行中的训练槽位窗口连抓12帧,
报告帧间差异(全零=画面冻结, 视觉主干收不到梯度)。只读。"""
import sys
import time

import numpy as np

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from perception import frame_features  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main(slot=0):
    from capture import DxcamCapturer
    x = slot * 656
    cap = DxcamCapturer(x, 30, 640, 510, scale=2)
    feats = []
    t0 = time.time()
    while time.time() - t0 < 6.0:
        f = cap.grab()
        if f:
            feats.append(frame_features(f, cap.w, cap.h, 80, 60))
        time.sleep(0.4)
    try:
        cap._cam.stop()
    except Exception:
        pass
    print("抓到 %d 帧" % len(feats))
    if len(feats) < 4:
        return
    arr = np.stack(feats).astype(np.float32)
    # 相邻帧差
    diffs = [float(np.abs(arr[i] - arr[i - 1]).mean()) for i in range(1, len(arr))]
    print("相邻帧平均绝对差: %s" % ["%.2f" % d for d in diffs])
    print("帧内方差(首帧): %.2f  时间方差(像素维度): %.2f"
          % (float(arr[0].var()), float(arr.var(axis=0).mean())))
    if max(diffs) < 0.5:
        print("!! 画面疑似冻结 — 视觉主干无有效输入")
    else:
        print("OK 画面在变化 — 视觉通道健康")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
