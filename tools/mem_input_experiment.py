# -*- coding: utf-8 -*-
"""B-2'行动通道实验(用户裁定2026-10-13: 内存写入, 暂绕键盘/vJoy).

原理: KeymapManager(每玩家一个, INPUT_TBL=0x898680两指针)有replay机制:
  +0x38 KeyInput input   ← 设备轮询每帧覆写(纯写有竞态)
  +0x60 u16 inKeys       ← replay/netplay输入源
  +0x64 bool readInKeys  ← true时游戏读inKeys(纯数据, 零代码钩子)
BattleKeys位域(bit0起): up,down,left,right,A,B,C,dash(D),AandB(SC),
BandC(SW),pause,select — 与rep输入流同款(已实证1.0000对齐)。

实验全程RPM自验证(scene/action/x客观读数), 无需看屏幕:
  P1 结构发现+基线 → P2 inKeys通道反应测试 → 菜单驱动(P1)找战斗
  → 战斗内P2动作验证 → 状态复原。
"""
from __future__ import annotations

import ctypes
import os
import struct
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf8', write_through=True)
k32 = ctypes.windll.kernel32

INPUT_TBL = 0x898680
SCENE = 0x8A0044
BM_P = 0x8985E4
OFF_INPUT, OFF_INKEYS, OFF_READIN = 0x38, 0x60, 0x64

BIT = {'up': 0, 'down': 1, 'left': 2, 'right': 3, 'A': 4, 'B': 5,
       'C': 6, 'D': 7, 'SC': 8, 'SW': 9, 'pause': 10, 'select': 11}


def keys_u16(d):
    v = 0
    for k, on in d.items():
        if on and k in BIT:
            v |= 1 << BIT[k]
    return v


def find_game():
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name='th123.exe'\" | "
         "Where-Object {$_.CommandLine -notlike '*th123_train*'} | "
         "Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True).stdout.strip()
    return int(out.split()[0]) if out else None


class Game:
    def __init__(self, pid):
        self.pid = pid
        self.h = k32.OpenProcess(0x10 | 0x20 | 0x8 | 0x400, False, pid)

    def rd(self, a, n):
        b = ctypes.create_string_buffer(n)
        g = ctypes.c_size_t()
        ok = k32.ReadProcessMemory(ctypes.c_void_p(self.h),
                                   ctypes.c_void_p(a), b, n,
                                   ctypes.byref(g))
        return b.raw[:n] if ok and g.value == n else None

    def wr(self, a, data):
        b = ctypes.create_string_buffer(data)
        g = ctypes.c_size_t()
        return bool(k32.WriteProcessMemory(ctypes.c_void_p(self.h),
                                           ctypes.c_void_p(a), b,
                                           len(data), ctypes.byref(g))
                    and g.value == len(data))

    def u32(self, a):
        return struct.unpack('<I', self.rd(a, 4))[0]

    # ---- 业务读数 ----
    def scene(self):
        return self.rd(SCENE, 1)[0]

    def battle_snap(self):
        """(scene, actL, actR, xL, xR, hpL, hpR) — 无战斗时None字段。"""
        bm = self.u32(BM_P)
        if not 0x10000 < bm < 0x80000000:
            return (self.scene(), None, None, None, None, None, None)
        out = [self.scene()]
        for cm_off, act, hp, x in ((0x0C, 316, 388, 236), (0x10, 316, 388, 236)):
            cm = self.u32(bm + cm_off)
            w = self.rd(cm, 0x800) if 0x10000 < cm < 0x80000000 else None
            if not w:
                out.extend([None, None, None])
                continue
            out.extend([struct.unpack_from('<H', w, act)[0],
                        struct.unpack_from('<h', w, hp)[0],
                        round(struct.unpack_from('<f', w, x)[0])])
        return tuple(out)

    def keymgrs(self):
        raw = self.rd(INPUT_TBL, 8)
        p1, p2 = struct.unpack('<II', raw)
        return p1, p2

    def km_state(self, p):
        w = self.rd(p, 0x68)
        if not w:
            return None
        ki = struct.unpack_from('<10i', w, OFF_INPUT)
        return {'input_h': ki[0], 'input_v': ki[1],
                'btns': tuple(bool(x) for x in ki[2:8]),
                'inKeys': struct.unpack_from('<H', w, OFF_INKEYS)[0],
                'readIn': w[OFF_READIN]}


def phase1(g):
    print('==== P1 结构发现+基线 ====', flush=True)
    p1, p2 = g.keymgrs()
    print('KeymapMgr: P1=0x%X P2=0x%X' % (p1, p2), flush=True)
    for tag, p in (('P1', p1), ('P2', p2)):
        st = g.km_state(p)
        print(' %s: %s' % (tag, st), flush=True)
        assert st, '结构读取失败'
    print(' scene=%s battle=%s' % (g.scene(), g.battle_snap()[:3]),
          flush=True)
    return p1, p2


def phase2(g, p1, p2):
    """P2 inKeys通道: 置readInKeys+写inKeys('down'), 观察input字段反应。"""
    print('==== P2 inKeys通道测试(12s) ====', flush=True)
    orig_in = g.rd(p2, 2)
    orig_rd = g.rd(p2 + OFF_READIN, 1)
    moved = False
    seen = set()
    try:
        # 审计2026-10-13 P2: 异常时readInKeys=1残留=真人输入被夺权
        g.wr(p2 + OFF_READIN, b'\x01')
        t0 = time.time()
        while time.time() - t0 < 12:
            el = time.time() - t0
            # 3s脉冲制: down按下1.2s → 停1.2s → A按下1.2s → ...
            seq = [{'down': True}, {}, {'A': True}, {}]
            d = seq[int(el // 1.2) % 4]
            g.wr(p2 + OFF_INKEYS, struct.pack('<H', keys_u16(d)))
            st = g.km_state(p2)
            seen.add((st['input_v'], st['input_h'], st['btns'][0]))
            time.sleep(1 / 240)
    finally:
        g.wr(p2 + OFF_INKEYS, orig_in)
        g.wr(p2 + OFF_READIN, orig_rd)
    print(' P2 input字段观察值集合:', sorted(seen)[:8], flush=True)
    moved = len(seen) > 1
    print(' 判定: input字段%s ← readInKeys路径%s' % (
        '有跟随!' if moved else '无变化', '生效' if moved else '未生效(或input不被inKeys回填)'), flush=True)
    return moved


def main():
    pid = find_game()
    if not pid:
        print('无原版游戏进程', flush=True)
        return 1
    g = Game(pid)
    print('[exp] PID=%d' % pid, flush=True)
    p1, p2 = phase1(g)
    phase2(g, p1, p2)
    print('[exp] 完成(状态已复原)', flush=True)
    return 0


if __name__ == '__main__':
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
