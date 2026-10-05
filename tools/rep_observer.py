# -*- coding: utf-8 -*-
"""专家REP被动观察器(B路线, rep_format_notes.md): ReplayDnD拖放播放 +
ReadProcessMemory旁路逐帧记录双方(态势,动作ID) → 专家distill。
第一阶段: 启动一个专用游戏实例(带ReplayDnD), WM_DROPFILES喂rep,
验证: ①拖放能启动回放 ②旁路地址表在回放模式下可读 ③场景轨迹正常。
本探针只验证管线, 不落distill。"""
import ctypes
import ctypes.wintypes as wt
import os
import struct
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

GAME = r"D:\touhou\hisoutensoku2026-06-15\th123_train"
EXE = os.path.join(GAME, "th123.exe")
REP_DIR = r"D:\temp\expert_reps"

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
SCENE_ADDR = 0x8A0044
BATTLE_MGR_P = 0x8985E4


def find_window(pid):
    result = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, lparam):
        wpid = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and u32.IsWindowVisible(hwnd):
            result.append(hwnd)
        return True
    u32.EnumWindows(cb, 0)
    return result[0] if result else None


def drop_file(hwnd, path):
    # WM_DROPFILES: 申请全局内存放DROPFILES结构+路径串
    bytes_path = (path.encode("gbk") + b"\0\0")     # ANSI版消息用gbk
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    h = k32.GlobalAlloc(0x2002, 20 + len(bytes_path))   # GMEM_MOVEABLE|ZEROINIT
    p = k32.GlobalLock(h)
    df = struct.pack("<IIii", 20, 0, 0, 0)          # pFiles=20, pt=0, fNC=0
    df += struct.pack("<I", 0)                       # fWide=0 (ANSI)
    ctypes.memmove(p, df, 20)
    ctypes.memmove(p + 20, bytes_path, len(bytes_path))
    k32.GlobalUnlock(h)
    u32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                 ctypes.c_void_p, ctypes.c_void_p]
    u32.PostMessageW(hwnd, 0x0233, h, None)          # WM_DROPFILES
    return True


def read_mem(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                             buf, n, ctypes.byref(got)) and got.value == n:
        return buf.raw
    return None


def main():
    rep = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        REP_DIR, sorted(os.listdir(REP_DIR))[0])
    print("启动游戏实例(ReplayDnD观察)...")
    proc = subprocess.Popen([EXE], cwd=GAME,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    time.sleep(6)
    hwnd = find_window(proc.pid)
    if not hwnd:
        print("[失败] 未找到游戏窗口")
        proc.terminate()
        return 1
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
                        False, proc.pid)
    # 观察基线场景
    base = read_mem(h, SCENE_ADDR, 1)
    print("窗口=%x pid=%d 初始场景=%s" % (hwnd, proc.pid,
                                          base.hex() if base else "?"))
    print("拖放:", os.path.basename(rep)[:60])
    drop_file(hwnd, rep)
    # 150秒观察场景轨迹与战斗管理器可读性(回放有载入等待, scene 0→2→5)
    t0 = time.time()
    last = None
    frames_seen = 0
    while time.time() - t0 < 150:
        s = read_mem(h, SCENE_ADDR, 1)
        if s:
            v = s[0]
            if v != last:
                print("  scene→%d (t=%.0fs)" % (v, time.time() - t0))
                last = v
            if v == 5:      # BATTLE
                frames_seen += 1
                # 战斗管理器指针链可读性抽查
                rl = read_mem(h, BATTLE_MGR_P, 4)
                if rl and frames_seen % 50 == 1:
                    bm = struct.unpack("<I", rl)[0]
                    ok = 0x10000 < bm < 0x80000000
                    print("    battleMgr=%08x 合法=%s" % (bm, ok))
        time.sleep(0.1)
    k32.CloseHandle(ctypes.c_void_p(h))
    proc.terminate()
    print("战斗期采样数:", frames_seen)
    return 0 if frames_seen > 100 else 1


if __name__ == "__main__":
    sys.exit(main())
