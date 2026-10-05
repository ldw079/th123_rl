# -*- coding: utf-8 -*-
"""vJoy 虚拟手柄输入后端(多开方向, 用户授权路线)。

背景: 本游戏失焦时挂起键盘消息处理(5通道实测全灭), 但手柄走 DirectInput
设备轮询, 失焦实例可能仍读取——本模块就是那条通道。

接口与 inject.Keyboard 对齐: apply(vk列表)/release_all(),
train_rl.py 里 kb = VJoyKeyboard() 即可无缝替换键盘通道。

键位依据(游戏内 Joystick 配置, 用户截图 + config123 profile):
  游戏 A(打击)=按钮1  B(射击)=按钮2  C(必杀)=按钮3  D(冲刺)=按钮4
  切换符卡(A+B)=R1  使用符卡(B+C)=R2
  方向: X/Y 轴(实测发现, 见 %TEMP%\\pad_discover 输出)
"""

import ctypes
import os

vj = ctypes.WinDLL(r"C:\Program Files\vJoy\x64\vJoyInterface.dll")
vj.vJoyEnabled.restype = ctypes.c_bool
vj.GetVJDStatus.argtypes = [ctypes.c_uint]
vj.GetVJDStatus.restype = ctypes.c_int
vj.AcquireVJD.argtypes = [ctypes.c_uint]
vj.AcquireVJD.restype = ctypes.c_bool
vj.RelinquishVJD.argtypes = [ctypes.c_uint]
vj.SetBtn.argtypes = [ctypes.c_bool, ctypes.c_uint, ctypes.c_uint]
vj.SetBtn.restype = ctypes.c_bool
vj.SetAxis.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_int]
vj.SetAxis.restype = ctypes.c_bool
vj.GetVJDAxisExist.argtypes = [ctypes.c_uint, ctypes.c_int]
vj.GetVJDAxisExist.restype = ctypes.c_bool
vj.GetVJDButtonNumber.argtypes = [ctypes.c_uint]
vj.GetVJDButtonNumber.restype = ctypes.c_int
vj.SetDiscPov.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_int]
vj.SetDiscPov.restype = ctypes.c_bool

# vJoy 轴 ID (HID usage)
AXIS_X = 0x30
AXIS_Y = 0x31

AX_MIN, AX_MID, AX_MAX = 0x0001, 0x4000, 0x7FFF   # vJoy 逻辑值域

# 游戏 VK(与 config.KEYMAP 一致) → vJoy 按钮号
# 依据: 游戏内 Joystick 配置截图 (A=1 B=2 C=3 D=4, R1=切卡 R2=符卡)
VK_TO_BTN = {
    0x4A: 1,   # J → 游戏 A(打击)      = 按钮1
    0x4B: 2,   # K → 游戏 B(射击)      = 按钮2
    0x4C: 3,   # L → 游戏 C(必杀)      = 按钮3
    0x4F: 4,   # O → 游戏 D(冲刺/飞行) = 按钮4
    0x55: 6,   # U → 符卡(B+C)         = R2(按钮6, 待实测校准)
}
# 方向 VK → 轴偏移
_DIR_AXIS = {
    0x41: (AXIS_X, AX_MIN),   # A(左)
    0x44: (AXIS_X, AX_MAX),   # D(右)
    0x57: (AXIS_Y, AX_MIN),   # W(上)
    0x53: (AXIS_Y, AX_MAX),   # S(下)
}


class VJoyKeyboard:
    """inject.Keyboard 同款接口: apply(VK列表) 差分按下/抬起, VK 经映射表转手柄。"""

    def __init__(self, dev_id=1):
        self.dev = dev_id
        self.held = set()
        if not vj.vJoyEnabled():
            raise RuntimeError("vJoy 驱动未启用")
        st = vj.GetVJDStatus(dev_id)
        # VJD_STAT_OWN=0 FREE=1 BUSY=2 MISS=3 UNKN=4
        if st in (2, 3, 4):
            raise RuntimeError("vJoy 设备 %d 不可用(status=%d)" % (dev_id, st))
        for _ in range(3):
            if vj.AcquireVJD(dev_id):
                break
        else:
            raise RuntimeError("vJoy AcquireVJD(%d) 失败" % dev_id)
        self._axes = {}
        self._btns = set()
        self.release_all()

    # ---- 底层 ----
    def _axis(self, axis, val):
        self._axes[axis] = val
        vj.SetAxis(val, self.dev, axis)

    def _btn(self, n, down):
        if down:
            self._btns.add(n)
        else:
            self._btns.discard(n)
        vj.SetBtn(down, self.dev, n)

    # ---- Keyboard 兼容接口 ----
    def apply(self, wanted):
        wanted = set(wanted)
        for vk in self.held - wanted:
            self._up(vk)
        for vk in wanted - self.held:
            self._down(vk)
        self.held = wanted

    def _down(self, vk):
        if vk in VK_TO_BTN:
            self._btn(VK_TO_BTN[vk], True)
        elif vk in _DIR_AXIS:
            axis, val = _DIR_AXIS[vk]
            # 反方向松开(同轴互斥)
            for other, (ax, v) in _DIR_AXIS.items():
                if ax == axis and v != val:
                    self._axis(ax, AX_MID)
            self._axis(axis, val)

    def _up(self, vk):
        if vk in VK_TO_BTN:
            self._btn(VK_TO_BTN[vk], False)
        elif vk in _DIR_AXIS:
            axis, _ = _DIR_AXIS[vk]
            self._axis(axis, AX_MID)

    def release_all(self):
        for n in list(self._btns):
            self._btn(n, False)
        for axis in list(self._axes):
            self._axis(axis, AX_MID)
        vj.SetAxis(AX_MID, self.dev, AXIS_X)
        vj.SetAxis(AX_MID, self.dev, AXIS_Y)
        self.held.clear()

    def close(self):
        self.release_all()
        vj.RelinquishVJD(self.dev)


if __name__ == "__main__":
    print("[自检] vJoyEnabled:", vj.vJoyEnabled())
    pad = VJoyKeyboard(1)
    print("[自检] acquired, 按钮%d个 轴存在X/Y:" % vj.GetVJDButtonNumber(1),
          vj.GetVJDAxisExist(1, AXIS_X), vj.GetVJDAxisExist(1, AXIS_Y))
    ok = pad._btn(1, True)
    print("[自检] 按钮1 按下 ret:", ok)
    pad._btn(1, False)
    ok = pad._axis(AXIS_X, AX_MAX)
    import time; time.sleep(0.2)
    pad.close()
    print("[自检] 完成")
