# -*- coding: utf-8 -*-
"""vJoy激活+完整链路测试: 喂非中性轴 → 游戏检测手柄活跃 → 手柄路径激活 →
SokuAI mod输入通道工作 → 自动开局到战斗收帧。"""
import ctypes
import sys
import threading
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from soku_client import SokuInstance, CHAR_REIMU  # noqa: E402

VJOY_DLL = r"C:\Program Files\vJoy\x64\vJoyInterface.dll"
HID_X = 0x30
HID_Y = 0x31

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class VJoy:
    def __init__(self, dev=1):
        self.dll = ctypes.CDLL(VJOY_DLL)
        self.dev = dev
        self.dll.vJoyEnabled.restype = ctypes.c_int
        self.dll.GetVJDStatus.argtypes = [ctypes.c_uint]
        self.dll.AcquireVJD.argtypes = [ctypes.c_uint]
        self.dll.AcquireVJD.restype = ctypes.c_int
        self.dll.SetAxis.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_long]
        self.dll.SetAxis.restype = ctypes.c_int
        self.dll.RelinquishVJD.argtypes = [ctypes.c_uint]

    def status(self):
        return self.dll.GetVJDStatus(self.dev)

    def feed(self, x, y):
        self.dll.SetAxis(x, self.dev, x if False else x)  # noqa — 见下
        return None


def main():
    # 简化: 直接用feeder式的ctypes调用
    dll = ctypes.CDLL(VJOY_DLL)
    dll.vJoyEnabled.restype = ctypes.c_int
    dll.GetVJDStatus.argtypes = [ctypes.c_uint]
    dll.AcquireVJD.argtypes = [ctypes.c_uint]
    dll.AcquireVJD.restype = ctypes.c_int
    dll.SetAxis.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_long]
    dll.SetAxis.restype = ctypes.c_int

    print("vJoyEnabled=%s" % bool(dll.vJoyEnabled()))
    st = dll.GetVJDStatus(1)
    print("设备1状态=%s (1=free 2=owned 3=busy)" % st)
    r = dll.AcquireVJD(1)
    print("Acquire=%s" % r)
    # 持续振荡喂值: 游戏的"手柄活跃"检测需要变化量(InputFreedom补丁的存在即证据)
    stop_feed = threading.Event()

    def feeder():
        i = 0
        while not stop_feed.is_set():
            x = 0x3000 + (0x800 if i % 2 == 0 else -0x800)
            dll.SetAxis(HID_X, 1, x)
            dll.SetAxis(HID_Y, 1, 0x3800 + (0x600 if i % 2 == 0 else -0x600))
            i += 1
            stop_feed.wait(0.05)

    threading.Thread(target=feeder, daemon=True).start()
    print("振荡喂值中")

    # 完整链路
    inst = SokuInstance(20762)
    pid = inst.proc.pid
    print("游戏PID=%d" % pid)

    res = {}

    def _s():
        try:
            inst.start_game(CHAR_REIMU, CHAR_REIMU)
            res["ok"] = 1
        except Exception as e:
            res["err"] = str(e)

    threading.Thread(target=_s, daemon=True).start()

    k32 = ctypes.windll.kernel32
    SCENE = 0x8A0044

    def rd(a):
        b = ctypes.create_string_buffer(1)
        g = ctypes.c_size_t()
        if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(a), b, 1,
                                     ctypes.byref(g)):
            return None
        return b.raw[0]

    h = k32.OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0400, False, pid)
    t0 = time.time()
    kicked = 0
    last = None
    while time.time() - t0 < 60 and not res.get("ok"):
        s = rd(SCENE)
        if s != last:
            print("[%4.1fs] scene=%s" % (time.time() - t0, s))
            last = s
        if s == 2 and time.time() - t0 > 2 and kicked < 5:
            k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(SCENE),
                                   b"\x03", 1, None)
            kicked += 1
            time.sleep(0.8)
        time.sleep(0.2)
    print("开局: %s" % res)
    if not res.get("ok"):
        inst.close()
        return

    # 选人自动驾驶推进监视
    t1 = time.time()
    last = None
    frames = 0
    hold = False
    while time.time() - t1 < 45:
        s = rd(SCENE)
        if s != last:
            print("  [%4.1fs] scene=%s" % (time.time() - t1, s))
            last = s
        try:
            left, right, weather, objs = inst.recv_frame(timeout=30.0 if frames == 0 else 2.0)
        except Exception as e:
            if frames == 0 and time.time() - t1 > 31:
                print("无首帧: %s" % e)
                break
            continue
        frames += 1
        if frames % 60 == 0:
            hold = not hold
        inst.send_inputs({"H": 1 if hold else -1}, {"H": -1 if hold else 1})
        if frames % 120 == 0:
            print("  帧%d: L.hp=%s relx=%.0f obj=%d"
                  % (frames, left["hp"], left["rel_x"], len(objs)))
    print("总帧数=%d" % frames)
    inst.close()
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main()
