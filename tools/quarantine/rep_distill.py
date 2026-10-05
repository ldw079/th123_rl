# -*- coding: utf-8 -*-
"""专家distill提取器v5: 直接使用兄弟工程(D:\\temp\\soku_arch)的完整已验证实现。
兄弟工程rep_drive.py已实现4/4比分一致——直接import其TrainerClient/rep_file/input_codec。
我们的职责仅: 包装为distill格式(11列)并落盘。
"""
import os
import sys
import time
import json
import argparse
import ctypes
import struct

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BRO = r"D:\temp\soku_arch"   # 兄弟工程根
sys.path.insert(0, ROOT)
sys.path.insert(0, BRO)
sys.stdout.reconfigure(encoding="utf-8")

from soku_arch.trainer_client import (
    TrainerClient, GameEnded, TrainerError,
    OPCODE_START_GAME_VS_PLAYER, NEUTRAL)
from soku_arch.rep_file import parse_rep_file
from soku_arch.input_codec import BattleInput, battle_to_trainer
from soku_arch import win_probe

STORE = r"D:\temp\th123_models"
GAME = os.path.join(BRO, "game_extract")
EXE = os.path.join(GAME, "th123.exe")
ID_CHAR = {0: "reimu", 1: "marisa", 9: "suika"}


def drive_rep(rep_path, port, tps=None, log=print):
    """用兄弟工程方案驱动一局rep → (distill行, actL, actR, char_pair, sync_ok)"""
    rep = parse_rep_file(rep_path)
    c1 = ID_CHAR.get(rep.char_x)
    c2 = ID_CHAR.get(rep.char_y)
    if c1 is None or c2 is None:
        log("[跳过] 角色%d/%d不在宏库" % (rep.char_x, rep.char_y))
        return None

    log("[rep] %s(%d) vs %s(%d) 帧%d 种子%d"
        % (c1, rep.char_x, c2, rep.char_y, rep.n_frames, rep.seed))

    env = {"SOKUAI_PORT": str(port), "SOKUAI_SEED": str(rep.seed)}
    cli = TrainerClient(port, EXE, GAME, launch=True, env=env)
    rows, acts_l, acts_r = [], [], []
    hands_l, hands_r = set(), set()
    try:
        cli.handshake()
        if tps:
            try:
                cli.set_speed(tps)
            except Exception:
                pass
        hwnd = win_probe.find_window(cli.proc.pid)
        if hwnd:
            win_probe.force_foreground(hwnd)
        h = win_probe.open_for_write(cli.proc.pid)
        # 输入表(驱动必需)
        if h:
            if win_probe.read_bytes(h, win_probe.TBL_ADDR, 8) != struct.pack(
                    "<II", win_probe.MGR_ADDR, win_probe.MGR_ADDR):
                win_probe.write_bytes(
                    h, win_probe.TBL_ADDR,
                    struct.pack("<II", win_probe.MGR_ADDR,
                               win_probe.MGR_ADDR))
        cli.wait_for_ready(max_wait=40.0)
        # 种子hook(mod内每帧强写SOKUAI_SEED)
        def _hook():
            pass  # v4 mod自己读SOKUAI_SEED强写, 无需Python干预

        first = cli.start_game(
            rep.char_x, rep.char_y,
            left_deck=list(rep.deck_x), right_deck=list(rep.deck_y),
            left_palette=rep.pal_x, right_palette=rep.pal_y,
            opcode=OPCODE_START_GAME_VS_PLAYER, hook=_hook)

        def _collect(st):
            L, R = st["left"], st["right"]
            for i in range(5):
                if L["hand"][i*2] not in (0xFF, 0):
                    hands_l.add(int(L["hand"][i*2]))
                if R["hand"][i*2] not in (0xFF, 0):
                    hands_r.add(int(R["hand"][i*2]))
            acts_l.append(L["action"])
            acts_r.append(R["action"])
            dx = abs(R["position.x"] - L["position.x"])
            rows.append([
                dx, L["spirit"] / 1000.0,
                1.0 if dx < 130 else 0.0,
                -1.0, L["frameCount"],
                R["position.y"] - L["position.y"],
                1.0 if R["airBorne"] else 0.0,
                0.0,   # bullet_near(后续可接)
                1.0 if L["position.x"] < R["position.x"] else 0.0,
                9.9,
                1.0 if (R["position.x"] < 120
                        or R["position.x"] > 1120) else 0.0,
            ])

        _collect(first)
        timeouts = 0
        for f, a, b in rep.frames():
            if cli.proc and cli.proc.poll() is not None:
                log("  [退出] 帧%d exit=%d" % (f, cli.proc.returncode))
                break
            li, _n1 = battle_to_trainer(BattleInput(a))
            ri, _n2 = battle_to_trainer(BattleInput(b))
            try:
                cli.send_inputs(li.as_dict(), ri.as_dict())
                kind, payload = cli.poll(timeout=3.0)
                if kind == "fault":
                    log("  [崩溃] 帧%d fault=%s" % (f, payload))
                    break
                if kind == "ended":
                    log("  [终局] 帧%d winner=%s" % (f, payload))
                    break
                if kind == "error":
                    if payload in (12, 17):
                        continue
                    raise TrainerError("err=%d" % payload)
                _collect(payload)
            except TimeoutError:
                timeouts += 1
                if timeouts > 30:
                    log("  [超时] 帧%d" % f)
                    break
                continue
        if h:
            win_probe.k32.CloseHandle(ctypes.c_void_p(h))
    except Exception as e:
        log("  [异常] %s: %s" % (type(e).__name__, str(e)[:80]))
    finally:
        cli.close()

    deck_l = {c for c in rep.deck_x if c}
    deck_r = {c for c in rep.deck_y if c}
    sync_l = hands_l <= deck_l | {0} if hands_l else True
    sync_r = hands_r <= deck_r | {0} if hands_r else True
    log("  完成: %d行 手牌同步L=%s R=%s" % (len(rows), sync_l, sync_r))
    return rows, acts_l, acts_r, (c1, c2), sync_l and sync_r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rep", help="rep路径(或目录)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--port", type=int, default=20970)
    a = ap.parse_args()

    if os.path.isdir(a.rep):
        paths = []
        for fn in sorted(os.listdir(a.rep)):
            if not fn.endswith(".rep"):
                continue
            b = open(os.path.join(a.rep, fn), "rb").read(70)
            if b[14] in ID_CHAR and b[63] in ID_CHAR:
                paths.append(os.path.join(a.rep, fn))
            if len(paths) >= a.max:
                break
        print("双侧在宏库: %d个" % len(paths))
    else:
        paths = [a.rep]

    out = a.out or os.path.join(STORE, "distill_expert_v5.npz")
    Xs, ALs, ARs, metas = [], [], [], []
    for i, p in enumerate(paths):
        print("[%d/%d]" % (i + 1, len(paths)),
              os.path.basename(p)[:55])
        try:
            result = drive_rep(p, a.port + (i % 5))
        except Exception as e:
            print("  失败:", type(e).__name__, str(e)[:80])
            continue
        if result is None:
            continue
        rows, al, ar, cp, sync = result
        if rows and sync:
            Xs.append(np.array(rows, dtype=np.float32))
            ALs.append(np.array(al, dtype=np.int32))
            ARs.append(np.array(ar, dtype=np.int32))
            metas.append({"file": os.path.basename(p),
                          "chars": list(cp), "rows": len(rows)})
        time.sleep(2)

    if not Xs:
        print("无有效数据")
        return 1
    X = np.concatenate(Xs)
    tmp = out + ".tmp.npz"
    np.savez(tmp, X=X, Y=np.full(len(X), -1, dtype=np.int64),
             act_L=np.concatenate(ALs), act_R=np.concatenate(ARs),
             meta=np.array(json.dumps(metas, ensure_ascii=False)))
    os.replace(tmp, out)
    print("总行%d → %s" % (len(X), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
