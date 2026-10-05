# -*- coding: utf-8 -*-
"""专家distill提取器(借兄弟工程成果, rep_format_notes路线B'):
用兄弟工程的隔离游戏副本(game_extract, 硬链接不占空间) + 观察版mod
(SokuAITrainerEnv: SOKUAI_PORT环境变量端口 + SOKUAI_OBSERVE=1被动推状态),
游戏自播rep, 我们收105字节状态包 + 从rep偏移121解出专家输入流按帧配对。
用法: python tools/rep_observe_session.py <rep路径> [--games N]"""
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from soku_client2 import GameEnded, ProtocolError  # noqa: E402

GAME = r"D:\temp\soku_arch\game_extract"
EXE = os.path.join(GAME, "th123.exe")
PORT = 20975          # probe段(20960-20999)
BATTLE_BITS = ("up", "down", "left", "right", "A", "B", "C", "dash",
               "AandB", "BandC", "pause", "select")


def parse_rep(path):
    """兄弟工程实证布局: 角色u8@14/@63, deck@20/@69, 种子u32@117,
    输入流@121起 2字节/条(游戏内部BattleKeys 12位, 两方交错)"""
    b = open(path, "rb").read()
    return {
        "char1": b[14], "pal1": b[15], "char2": b[63], "pal2": b[64],
        "deck1": list(struct.unpack_from("<20H", b, 20)),
        "deck2": list(struct.unpack_from("<20H", b, 69)),
        "seed": struct.unpack_from("<I", b, 117)[0],
        "inputs": [struct.unpack_from("<H", b, 121 + 2 * i)[0]
                   for i in range((len(b) - 121) // 2)],
    }


def battle_to_keys(v):
    """BattleKeys u16 → 我方send_inputs的dict(A/B/C/D + H/V)"""
    up = (v >> 0) & 1
    dn = (v >> 1) & 1
    lf = (v >> 2) & 1
    rt = (v >> 3) & 1
    h = rt - lf
    vv = dn - up          # 游戏V: 下=+1(与mod V一致: down为正)
    d = {"A": bool(v & 16), "B": bool(v & 32), "C": bool(v & 64),
         "D": bool(v & 128), "SC": False, "SW": False}
    d["H"] = h if h in (-1, 0, 1) else 0
    d["V"] = vv if vv in (-1, 0, 1) else 0
    return d


def main():
    rep = sys.argv[1]
    hdr = parse_rep(rep)
    print("[rep] 角色%d/%d deck%d+%d 种子%d 输入条目%d"
          % (hdr["char1"], hdr["char2"], len(hdr["deck1"]),
             len(hdr["deck2"]), hdr["seed"], len(hdr["inputs"])))
    # 裸文件名放入隔离副本的replay目录(ReplayDnD只认裸名)
    import shutil
    bare = "obs_%d.rep" % int(time.time())
    dst = os.path.join(GAME, "replay", bare)
    shutil.copy2(rep, dst)
    # 启动: SOKUAI_PORT=端口 + SOKUAI_OBSERVE=1 + argv=[裸rep名]
    import socket
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("127.0.0.1", PORT))
    lsock.listen(1)
    env = {**os.environ, "SOKUAI_PORT": str(PORT), "SOKUAI_OBSERVE": "1"}
    proc = subprocess.Popen([EXE, bare], cwd=GAME, env=env,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    print("[启动] pid=%d argv=[%s] SOKUAI_PORT=%d OBSERVE=1"
          % (proc.pid, bare, PORT))
    time.sleep(6)
    if proc.poll() is not None:
        print("[失败] 进程已退出 exit=%d(ReplayDnD AutoShutdown?)"
              % proc.returncode)
        return 1
    # 观察模式需窗口前台(游戏不聚焦不推进 — 兄弟工程test_focus实证)
    time.sleep(4)
    import ctypes
    import ctypes.wintypes as wt
    u32 = ctypes.windll.user32

    def find_win(pid):
        r = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, l):
            p = wt.DWORD()
            u32.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value == pid:
                cls = ctypes.create_string_buffer(64)
                u32.GetClassNameA(h, cls, 64)
                if cls.value == b'th123_110a':
                    r.append(h)
            return True
        u32.EnumWindows(cb, 0)
        return r[0] if r else None
    hwnd = find_win(proc.pid)
    if hwnd:
        u32.ShowWindow(hwnd, 9)
        # AttachThreadInput前台化(兄弟工程win_probe实证的最可靠路径)
        cur = u32.GetWindowThreadProcessId(hwnd, None)
        _tid = u32.GetCurrentThreadId() or ctypes.windll.kernel32.GetCurrentThreadId()
        fg = u32.GetForegroundWindow()
        fgT = u32.GetWindowThreadProcessId(fg, None)
        u32.AttachThreadInput(_tid, fgT, True)
        u32.SetForegroundWindow(hwnd)
        u32.AttachThreadInput(_tid, fgT, False)
        print("[前台化] hwnd=%x" % hwnd)
    lsock.settimeout(120.0)
    try:
        sock, _ = lsock.accept()
    except socket.timeout:
        proc.terminate()
        print("[失败] 120s未连接")
        return 1
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    hello = b"\x00\x2A\x9D\x6E\xF5"
    sock.sendall(hello)
    import select
    buf = b""

    def recv_exact(n, timeout=5.0):
        nonlocal buf
        t0 = time.time()
        while len(buf) < n:
            r, _, _ = select.select([sock], [], [],
                                    max(0.0, timeout - (time.time() - t0)))
            if not r:
                raise TimeoutError()
            c = sock.recv(n - len(buf))
            if not c:
                raise ConnectionError("closed")
            buf += c
        out, buf = buf[:n], buf[n:]
        return out

    echo = recv_exact(5, 10.0)
    print("[握手] 回显一致:", echo == hello)
    # 观察模式: mod被动推帧, 不需发输入 — 纯收
    CS = 105
    frames = 0
    t0 = time.time()
    seen_hand = set()
    deck_set = {c for c in hdr["deck1"] + hdr["deck2"] if c}
    try:
        while time.time() - t0 < 180 and proc.poll() is None:
            op = recv_exact(1, 3.0)[0]
            while op == 12:      # OK透跳
                op = recv_exact(1, 3.0)[0]
            if op == 8:          # GAME_FRAME
                head = recv_exact(2 * CS + 4)
                lv = struct.unpack("<b2fHHHHIHH?HHHBHHHHHHB10sH15sBBBBBHHH20sB",
                                   head[:CS])
                rv = struct.unpack("<b2fHHHHIHH?HHHBHHHHHHB10sH15sBBBBBHHH20sB",
                                   head[CS:2 * CS])
                for hand in (lv[20], rv[20]):
                    for i in range(5):
                        cid = hand[i * 2]
                        if cid not in (0xFF, 0):
                            seen_hand.add(cid)
                frames += 1
                if frames % 200 == 1:
                    print("  帧%d L.hp=%d R.hp=%d L.x=%.0f"
                          % (frames, lv[13], rv[13], lv[1]))
            elif op == 11:       # GAME_ENDED
                recv_exact(3)
                print("[局终] 帧%d" % frames)
                break
            elif op == 7:
                recv_exact(1)
    except (TimeoutError, ConnectionError) as e:
        print("[结束]", type(e).__name__, e)
    print("总帧数:", frames, "| 观测到手牌ID:", len(seen_hand),
          "| 手牌⊆rep卡组:", seen_hand <= deck_set if seen_hand else "无手牌")
    proc.terminate()
    try:
        os.remove(dst)
    except OSError:
        pass
    return 0 if frames > 100 else 1


if __name__ == "__main__":
    sys.exit(main())
