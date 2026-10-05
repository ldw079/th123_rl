# -*- coding: utf-8 -*-
"""游戏注入测试 v2: 用"变化像素质心的位移"判定角色是否真的移动了。

只看画面变化量没有意义(待机动画、天气特效都会变)。
方法: 先测无输入 2.5 秒的基线漂移, 再分别按住 → / ← 各 2.5 秒;
角色若真的走动, 下半屏变化像素的质心会沿按键方向明显漂移(几百像素级)。

用法:
  <python> test_game_inject.py                # 默认 SendInput 虚拟键码
  <python> test_game_inject.py --mode scan    # 扫描码模式
  <python> test_game_inject.py --mode journal # 日志回放模式(等价 AHK SendPlay)
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import ctypes
from ctypes import wintypes

import config
import inject
import loop  # 复用 wait_foreground
from capture import ScreenCapturer, find_windows, get_client_rect, user32
from perception import save_bmp


def _post_key(hwnd, vk, up):
    """直接向游戏窗口投递 WM_KEYDOWN/WM_KEYUP(窗口消息路径, 不走输入队列)。"""
    sc = user32.MapVirtualKeyW(vk, 0)
    lp = (sc << 16) | (0xC0000000 if up else 0)
    user32.PostMessageW(hwnd, 0x0101 if up else 0x0100, vk, lp)


def centroid(prev, cur, w, h, y0, y1, stride=2, thresh=24):
    """区域内变化像素的 x 质心(用于判定角色位移方向)。"""
    sx = sy = n = 0
    for yy in range(y0, y1, stride):
        base = yy * w * 4
        i = base
        for xx in range(0, w, stride):
            d = abs(prev[i] - cur[i]) + abs(prev[i + 1] - cur[i + 1]) + abs(prev[i + 2] - cur[i + 2])
            if d > thresh:
                sx += xx
                sy += yy
                n += 1
            i += 4 * stride
    return n, (sx / n if n else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="vk", choices=["vk", "scan", "keybd_scan", "keybd_vk", "journal", "postmsg"])
    args = ap.parse_args()
    if args.mode == "scan":
        inject._send = inject._send_scan
        sender = "SendInput 扫描码"
    elif args.mode == "keybd_scan":
        inject._send = inject._send_keybd_scan
        sender = "keybd_event 扫描码(神AI 同款)"
    elif args.mode == "keybd_vk":
        inject._send = inject._send_keybd_vk
        sender = "keybd_event 虚拟键码"
    elif args.mode == "journal":
        inject._send = inject._send_journal
        sender = "journal playback(等价 AHK SendPlay)"
    elif args.mode == "postmsg":
        sender = "PostMessage WM_KEYDOWN(窗口消息)"
    else:
        sender = "SendInput 虚拟键码"

    win = None
    for sub in config.TITLE_CANDIDATES:
        wins = find_windows(sub)
        if wins:
            win = wins[0]
            break
    if win is None:
        print("[错误] 找不到游戏窗口")
        sys.exit(1)
    hwnd, title = win
    print("[窗口]", title)
    if not loop.wait_foreground(hwnd, seconds=8.0):
        print("[错误] 游戏窗口不在前台, 请点击游戏窗口后重试")
        sys.exit(1)

    x, y, w, h = get_client_rect(hwnd)
    cap = ScreenCapturer(x, y, w, h)
    band = (int(h * 0.55), int(h * 0.9))   # 角色所在的下半屏
    print("[注入通道]", sender)
    print("[测试区] 客户区 %dx%d, 下半屏 y=%d..%d" % (w, h, band[0], band[1]))

    # 基线: 无输入 2.5 秒的画面漂移(待机动画/天气特效)
    a = cap.grab()
    time.sleep(2.5)
    b = cap.grab()
    nb, cxb = centroid(a, b, w, h, *band)
    print("[基线] 无输入 2.5s: 变化像素=%d 质心x=%.0f" % (nb, cxb))

    # 按住 → 2.5 秒
    a = b
    if args.mode == "postmsg":
        _post_key(hwnd, config.KEYMAP["right"], False)
    else:
        inject.press(config.KEYMAP["right"])
    time.sleep(2.5)
    if args.mode == "postmsg":
        _post_key(hwnd, config.KEYMAP["right"], True)
    else:
        inject.release(config.KEYMAP["right"])
    time.sleep(0.2)
    b = cap.grab()
    n1, cx1 = centroid(a, b, w, h, *band)
    save_bmp(b, w, h, os.path.join(config.FRAME_DIR, "test_right_%s.bmp" % args.mode))
    print("[→ 2.5s] 变化像素=%d 质心x=%.0f (相对基线漂移 %+.0f px)" % (n1, cx1, cx1 - cxb))

    # 按住 ← 2.5 秒
    a = b
    if args.mode == "postmsg":
        _post_key(hwnd, config.KEYMAP["left"], False)
    else:
        inject.press(config.KEYMAP["left"])
    time.sleep(2.5)
    if args.mode == "postmsg":
        _post_key(hwnd, config.KEYMAP["left"], True)
    else:
        inject.release(config.KEYMAP["left"])
    time.sleep(0.2)
    b = cap.grab()
    n2, cx2 = centroid(a, b, w, h, *band)
    save_bmp(b, w, h, os.path.join(config.FRAME_DIR, "test_left_%s.bmp" % args.mode))
    print("[← 2.5s] 变化像素=%d 质心x=%.0f (相对基线漂移 %+.0f px)" % (n2, cx2, cx2 - cxb))
    cap.close()

    moved = (cx1 - cxb) > 40 and (cx2 - cxb) < -40
    print("[结论]", "通过: 角色随按键左右移动, 该注入通道有效" if moved else
          "未通过: 该注入通道似乎被游戏忽略(或角色已到版边/画面不响应方向键)")


if __name__ == "__main__":
    main()
