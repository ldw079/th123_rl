# -*- coding: utf-8 -*-
"""确定性自检: 同一rep驱动两次, 比较状态流哈希。
如果两次一致=系统确定性(偏差来自系统性输入转换损失, 非随机);
如果不一致=存在非确定源(TCP时序/帧节拍), 需进一步排查。
"""
import hashlib
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from tools.rep_distill import (
    SyncClient, GameEnded, parse_rep, battle_to_trainer)

REP_DIR = r"D:\temp\expert_reps"
PORT = 20977


def drive_and_hash(rep_path, port, max_frames=3000):
    """驱动前N帧, 返回状态流的SHA256"""
    hdr = parse_rep(rep_path)
    inputs = hdr["inputs"]
    cli = SyncClient(port)
    cli.launch(tps=None)
    hasher = hashlib.sha256()
    n = 0
    try:
        first = cli.start_game_sync(
            hdr["char_x"], hdr["char_y"],
            hdr["deck_x"], hdr["deck_y"],
            hdr["pal_x"], hdr["pal_y"],
            hdr["seed"])
        # 首帧入哈希
        left, right = first[0], first[1]
        hasher.update(("%d,%d,%d,%d,%d,%d" % (
            left["hp"], right["hp"],
            int(left["position.x"] * 10), int(right["position.x"] * 10),
            left["action"], right["action"])).encode())
        n = 1
        t0 = time.time()
        while n < max_frames and n < len(inputs) // 2 \
                and time.time() - t0 < max_frames / 30.0:
            inp_l = battle_to_trainer(inputs[n * 2]) \
                if n * 2 + 1 < len(inputs) else {}
            inp_r = battle_to_trainer(inputs[n * 2 + 1]) \
                if n * 2 + 1 < len(inputs) else {}
            try:
                r = cli.step(inp_l, inp_r)
            except GameEnded:
                break
            left, right = r[0], r[1]
            hasher.update(("%d,%d,%d,%d,%d,%d" % (
                left["hp"], right["hp"],
                int(left["position.x"] * 10),
                int(right["position.x"] * 10),
                left["action"], right["action"])).encode())
            n += 1
    finally:
        cli.close()
    return hasher.hexdigest()[:16], n


def main():
    # 选一个双侧rep
    for f in sorted(os.listdir(REP_DIR)):
        if not f.endswith(".rep"):
            continue
        b = open(os.path.join(REP_DIR, f), "rb").read(70)
        if b[14] in (0, 1, 9) and b[63] in (0, 1, 9):
            rep = os.path.join(REP_DIR, f)
            break
    print("确定性自检: %s" % f[:60])
    print("驱动前3000帧×2次, 比较状态流哈希\n")

    h1, n1 = drive_and_hash(rep, PORT)
    print("第1次: %d帧 hash=%s" % (n1, h1))
    time.sleep(3)

    h2, n2 = drive_and_hash(rep, PORT + 1)
    print("第2次: %d帧 hash=%s" % (n2, h2))

    print("\n=== 结论 ===")
    if h1 == h2:
        print("✓ 确定性: 两次状态流完全一致")
        print("  → 与原录像的偏差是系统性的(输入转换损失), 非随机")
        print("  → 可通过量化偏差分布来标注数据置信度")
    else:
        print("✗ 非确定: 两次状态流不同")
        print("  → 存在非确定源(TCP时序/种子未完全生效/其他)")
        print("  → 需进一步排查")
    return 0


if __name__ == "__main__":
    sys.exit(main())
