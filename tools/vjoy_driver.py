# -*- coding: utf-8 -*-
"""B-2(顶端标尺v2§B-2): vJoy虚拟手柄驱动 — 模型行动通道.

ctypes直调vJoyInterface.dll(免pyvjoy依赖, 方案裁定优先后者)。
键位映射(方案§B-2): H=axisX V=axisY, A/B/C/D=btn1-4, SC=btn5,
SW=btn6 — 用户游戏内把P2键位绑到vJoy设备(那步人工, 兼容探针)。

公平: 行动不经延迟垫片(观察侧5帧已垫) — 人类"看到→反应"同构。
"""
from __future__ import annotations

import ctypes
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf8')

DLL_PATHS = [
    r'C:\Program Files\vJoy\x64\vJoyInterface.dll',
    r'D:\vJoy\x64\vJoyInterface.dll',
    r'D:\vjoy\x64\vJoyInterface.dll',
]
# HID usage ID
HID_X, HID_Y = 0x30, 0x31
# 原生手柄绑定(.pf实测: profile2p.pf手柄块 a=btn1..d=btn4,
# changeCard=btn5, spellcard=btn6) — 协议'SC'=符卡use→btn6, 'SW'=切卡→btn5
BTN_MAP = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'SW': 5, 'SC': 6}


class VJoyDevice:
    """单vJoy设备(rID默认1)。未acquire/驱动缺失时响亮报错。"""

    def __init__(self, rid=1, dll_path=None):
        path = dll_path or next((p for p in DLL_PATHS
                                 if os.path.exists(p)), None)
        if not path:
            raise RuntimeError('vJoyInterface.dll未找到(搜索%s)' % DLL_PATHS)
        self.dll = d = ctypes.CDLL(path)
        self.rid = rid
        self._axis_min = self._axis_max = None
        # 原型声明(无声明时ctypes默认猜32位int — 实测GetNumberExistingVJD
        # 当场access violation, 原型必须显式)
        u = ctypes.c_uint
        d.vJoyEnabled.restype = ctypes.c_bool
        d.GetVJDStatus.argtypes = [u]
        d.GetVJDStatus.restype = ctypes.c_int
        d.GetNumberExistingVJD.argtypes = []
        d.GetNumberExistingVJD.restype = ctypes.c_int
        d.AcquireVJD.argtypes = [u]
        d.AcquireVJD.restype = ctypes.c_bool
        d.GetVJDAxisMin.argtypes = [u, u, ctypes.POINTER(ctypes.c_long)]
        d.GetVJDAxisMin.restype = ctypes.c_bool
        d.GetVJDAxisMax.argtypes = [u, u, ctypes.POINTER(ctypes.c_long)]
        d.GetVJDAxisMax.restype = ctypes.c_bool
        d.SetAxis.argtypes = [ctypes.c_long, u, u]
        d.SetAxis.restype = ctypes.c_bool
        d.SetBtn.argtypes = [ctypes.c_bool, u, u]
        d.SetBtn.restype = ctypes.c_bool
        d.RelinquishVJD.argtypes = [u]

    def probe(self):
        """驱动级探测: vJoyEnabled/设备存在/acquire/轴范围。"""
        d = self.dll
        if not d.vJoyEnabled():
            return False, '驱动未启用'
        st = d.GetVJDStatus(self.rid)
        if st == 3:   # VJD_STAT_MISS(0=OWN/1=FREE/2=BUSY)
            return False, '设备%d不存在(MISS)' % self.rid
        n = d.GetNumberExistingVJD()
        if self.rid > n:
            return False, '设备%d不存在(共%d个)' % (self.rid, n)
        if not d.AcquireVJD(self.rid):
            return False, 'acquire失败'
        lo = ctypes.c_long()
        hi = ctypes.c_long()
        if d.GetVJDAxisMin(self.rid, HID_X, ctypes.byref(lo)):
            self._axis_min = lo.value
        if d.GetVJDAxisMax(self.rid, HID_X, ctypes.byref(hi)):
            self._axis_max = hi.value
        if self._axis_min is None:
            self._axis_min, self._axis_max = -16000, 16000   # vJoy默认
        # 写探针: 中位+清键
        self._set_axis(0, 0)
        self._set_axis(1, 0)
        for b in BTN_MAP.values():
            if not d.SetBtn(False, self.rid, b):
                return False, 'SetBtn失败(btn%d)' % b
        if not d.UpdateVJD(self.rid):   # 旧版接口无此导出时容错
            pass
        return True, '设备%d acquire OK, 轴[%d,%d], 写入OK' % (
            self.rid, self._axis_min, self._axis_max)

    def _set_axis(self, usage, frac):
        """frac∈[-1,1] → 轴值(三段:H=-1左/+1右, V=-1上/+1下)。"""
        v = int((self._axis_min + self._axis_max) / 2
                + frac * (self._axis_max - self._axis_min) / 2)
        self.dll.SetAxis(v, self.rid, usage)

    def write_frame(self, inp):
        """协议输入dict(与soku_client2.send_inputs同键) → vJoy状态。

        H: -1=左 +1=右; V: -1=上 +1=下(soku协议: V=-1是上)。
        游戏手柄Y轴: 上=-1(负值), 下=+1 — 与协议V直接同号。
        """
        h = int(inp.get('H', 0) or 0)
        v = int(inp.get('V', 0) or 0)
        self._set_axis(HID_X, h)
        self._set_axis(HID_Y, v)
        for key, btn in BTN_MAP.items():
            self.dll.SetBtn(bool(inp.get(key)), self.rid, btn)
        return True

    def neutral(self):
        self.write_frame({})

    def release(self):
        try:
            self.neutral()
            self.dll.RelinquishVJD(self.rid)
        except Exception:
            pass


def probe():
    """系统级兼容探针(方案§B-2): 设备acquire+读写+正弦摆动2秒。

    通过后仍需游戏内人工确认P2绑定可见(那步才算B-2a裁定点)。
    """
    dev = VJoyDevice()
    ok, msg = dev.probe()
    print('[vjoy] %s' % msg)
    if not ok:
        return 1
    print('[vjoy] 正弦摆动axisX 2秒(可开"设置→游戏控制器"观察十字)')
    t0 = time.time()
    import math
    while time.time() - t0 < 2.0:
        frac = math.sin((time.time() - t0) * 6.0)
        dev._set_axis(HID_X, frac)
        time.sleep(1 / 60)
    dev.neutral()
    dev.release()
    print('[vjoy] 探针完成 — 下一步: 游戏内P2键位绑定vJoy设备(人工)')
    return 0


if __name__ == '__main__':
    _rc = probe()
    # vJoy DLL在解释器teardown时卸载段错误(实测) — 跳过析构直接退出
    sys.stdout.flush()
    os._exit(_rc)
