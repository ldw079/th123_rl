# -*- coding: utf-8 -*-
"""REP(非想天则录像)格式解析与结构探测。
目标: 从D:/temp/expert_reps的1521个rep中解析出逐帧双方输入,
供TM通道回放(喂给VS_PLAYER收全量状态包)。
第一阶段: 结构探测 — 版本头/帧数据布局/长度自洽性。"""
import os
import struct
import sys
import collections

sys.stdout.reconfigure(encoding="utf-8")
REP_DIR = r"D:\temp\expert_reps"


def probe(path):
    d = open(path, "rb").read()
    info = {"size": len(d), "head_hex": d[:32].hex()}
    # 非想天则rep头部(社区资料): 起始魔数+版本+卡组等; 帧数据为
    # 定长记录。先统计可整除性找帧宽候选。
    n = len(d)
    divs = [w for w in range(2, 13) if n % w == 0]
    info["div_candidates"] = divs
    # 常见布局: 4字节头 + N×(2×2字节输入)。试 (n-4)/4 整数?
    for skip in (0, 4, 8, 12, 16, 20, 24, 0x20, 0x28):
        body = n - skip
        if body > 0 and body % 4 == 0:
            frames = body // 4
            # 抽样验证: 输入16位, 高位(H/V在6-9位)很少全1
            ok = 0
            tot = 0
            for i in range(min(frames, 500)):
                a, b = struct.unpack_from("<HH", d, skip + i * 4)
                for v in (a, b):
                    tot += 1
                    if v >> 10 == 0:   # 位10-15应为0(仅0-9位有效)
                        ok += 1
            if tot and ok / tot > 0.95:
                info["frame_layout"] = {
                    "skip": skip, "frames": frames, "valid_ratio": ok / tot}
                break
    return info


def main():
    files = sorted(os.listdir(REP_DIR))[:40]
    layouts = collections.Counter()
    for f in files:
        p = os.path.join(REP_DIR, f)
        info = probe(p)
        fl = info.get("frame_layout")
        key = (fl["skip"], fl["frames"]) if fl else None
        layouts[(key, tuple(info["div_candidates"][:3]))] += 1
        if len(layouts) < 6:
            print("%s\n  size=%d head=%s divs=%s layout=%s"
                  % (f[:60], info["size"], info["head_hex"][:40],
                     info["div_candidates"][:6],
                     ("skip=%d frames=%d ok=%.2f"
                      % (fl["skip"], fl["frames"], fl["valid_ratio"]))
                     if fl else "未识别"))
    print("\n布局分布:", layouts.most_common(5))
    return 0


if __name__ == "__main__":
    sys.exit(main())
