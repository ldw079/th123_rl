# -*- coding: utf-8 -*-
r"""B-1(顶端标尺v2§B-1): RPM偏移链校准器 — mod流式真值 × 内存窗口对解.

原理: rl_game跑rep回放(SOKUAI_OBSERVE=1)时, mod逐帧发全量状态(真值);
同一进程同时用RPM按帧读**角色管理器周围内存窗口**。离线对齐后, 对每个
真值字段(spirit/hand/action/hp/position/frameCount...)在窗口内搜偏移:
内存值序列与真值序列逐帧相等的偏移=该字段偏移(誤差=0 硬判据)。

对齐: 真值帧自带frameCount(CS字段); RPM侧先解frameCount偏移(单调
计数器与真值序列吻合), 再按帧号对齐其余字段。

用法: python tools/rpm_calibration.py [--rep xxx.rep] [--win 0x800]
产物: tools/rpm_offsets.json(已验证偏移表+rpm_observer消费)
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')

from soku_arch.trainer_client import TrainerClient
from portmap import reserved_port

RL_GAME = r'D:\temp\rl_game'
RL_EXE = os.path.join(RL_GAME, 'th123.exe')
PORT = reserved_port('human_solo_oracle')   # 校准复用solo口(串行使用)
k32 = ctypes.windll.kernel32

SCENE = 0x8A0044
BATTLE_MGR_P = 0x8985E4
CM_L, CM_R = 0x0C, 0x10


def _read(h, addr, n):
    b = ctypes.create_string_buffer(n)
    g = ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                                 b, n, ctypes.byref(g)) or g.value != n:
        return None
    return b.raw


class RpmCapture(threading.Thread):
    """60-120Hz抓取两角色管理器win字节窗口+battle_mgr窗口+场景。"""

    GLOB_BASE = 0x89F000
    GLOB_WIN = 0x3000

    def __init__(self, pid, win=0x800):
        super().__init__(daemon=True)
        self.h = k32.OpenProcess(0x10 | 0x20 | 0x8 | 0x400, False, pid)
        self.win = win
        self.samples = []       # [(t, scene, cmL, cmR, bm, glob)]
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            bm_p = _read(self.h, BATTLE_MGR_P, 4)
            if not bm_p:
                time.sleep(0.01)
                continue
            bm = struct.unpack('<I', bm_p)[0]
            if not (0x10000 < bm < 0x80000000):
                time.sleep(0.01)
                continue
            scene = _read(self.h, SCENE, 1)
            cmLp = _read(self.h, bm + CM_L, 4)
            cmRp = _read(self.h, bm + CM_R, 4)
            if not (scene and cmLp and cmRp):
                time.sleep(0.005)
                continue
            cmL = struct.unpack('<I', cmLp)[0]
            cmR = struct.unpack('<I', cmRp)[0]
            wL = _read(self.h, cmL, self.win)
            wR = _read(self.h, cmR, self.win)
            bmw = _read(self.h, bm, self.win)
            glob = _read(self.h, self.GLOB_BASE, self.GLOB_WIN)
            if wL and wR and bmw and glob:
                self.samples.append((time.time(), scene[0], wL, wR, bmw,
                                     glob))
            time.sleep(1.0 / 120.0)


def run_calibration(rep_path, win=0x800, tps=60, max_frames=4000):
    staged = 'calib_%d.rep' % int(time.time())
    shutil.copy(rep_path, os.path.join(RL_GAME, staged))
    cli = TrainerClient(
        PORT, RL_EXE, RL_GAME, launch=True, accept_timeout=90,
        raw_argv=[staged],
        env={'SOKUAI_PORT': str(PORT), 'SOKUAI_OBSERVE': '1'})
    truth = []      # [(frameCount, left_dict, right_dict)]
    cap = None
    t0 = time.time()
    try:
        cli.handshake()
        cli.set_speed(tps)
        cap = RpmCapture(cli.proc.pid, win)
        cap.start()
        last = t0
        while time.time() - t0 < 300 and len(truth) < max_frames:
            if cli.proc and cli.proc.poll() is not None:
                break
            try:
                kind, payload = cli.poll(timeout=3.0)
            except TimeoutError:
                if truth and time.time() - last > 15:
                    break
                continue
            except Exception:
                break
            if kind in ('fault', 'ended'):
                break
            if kind == 'frame':
                last = time.time()
                truth.append((payload['left'].get('frameCount', -1),
                              payload['left'], payload['right'],
                              payload.get('weather') or {}))
    finally:
        if cap:
            cap.stop.set()
            cap.join(timeout=3)
        try:
            cli.close()
        except Exception:
            pass
        try:
            os.remove(os.path.join(RL_GAME, staged))
        except OSError:
            pass
    print('[calib] 真值帧 %d | RPM样本 %d' % (len(truth), len(cap.samples)))
    return truth, cap.samples if cap else []


def solve_offsets(truth, samples, win):
    """离线解v5(定版): hp锚互相关粗对齐(自适应率网格) → 各字段在
    ±2样本窗内全帧评估(此法实测action@316=96.1%/sequence=94.6%)。
    常值真值字段(score)只报候选不裁决(标注ambiguous)。
    """
    res = {'_meta': {'truth_frames': len(truth), 'rpm_samples':
                     len(samples), 'win': win}}
    if not truth or not samples:
        return res
    n = len(truth)
    hp_off = 388
    hp_t = [t[1].get('hp') for t in truth]
    mem_hp = [struct.unpack_from('<h', smp[2], hp_off)[0] for smp in samples]
    center = len(samples) / max(n, 1)
    best = (0, center, -1)
    for rate in [center * (0.6 + 0.04 * i) for i in range(21)]:
        for k in range(0, max(len(samples) - int(n * rate), 1)):
            eq = 0
            for i in range(0, n, 5):
                j = int(k + i * rate)
                if j < len(samples) and mem_hp[j] == hp_t[i]:
                    eq += 1
            if eq > best[2]:
                best = (k, rate, eq)
    k, rate, _ = best
    # 分块精化: 10块各搜±40样本局部shift(hp全等最多), 过(块号,shift)
    # 最小二乘拟合 → 抗漂移的精(k,rate)
    pts = []
    nb = 10
    for b in range(nb):
        i_lo = int(b * n / nb)
        i_hi = int((b + 1) * n / nb)
        best_b = (None, -1)
        for sh in range(-40, 41, 2):
            eq = 0
            for i in range(i_lo, i_hi, 4):
                j = int(k + i * rate) + sh
                if 0 <= j < len(samples) and mem_hp[j] == hp_t[i]:
                    eq += 1
            if eq > best_b[1]:
                best_b = ((i_lo, int(k + i_lo * rate) + sh), eq)
        if best_b[0] and best_b[1] > (i_hi - i_lo) / 4 * 0.5:
            pts.append(best_b[0])
    if len(pts) >= 3:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        rate = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) /             max(sum((x - mx) ** 2 for x in xs), 1e-9)
        k = my - rate * mx
    print('  [锚] hp互相关+分块精化 k=%.1f rate=%.4f(块%d)'
          % (k, rate, len(pts)))
    res['_meta']['anchor'] = {'k': k, 'rate': round(rate, 4)}

    def hits_for(getter, fmt, side_w, tolerance=2):
        fv = [getter(t) for t in truth]
        if len([v for v in fv if v is not None]) < 100:
            return []
        out = []
        for off in range(0, win - 16, 2):
            eq = 0
            tot = 0
            for i in range(0, n, 4):     # 抽稀1/4控成本
                v = fv[i]
                if v is None:
                    continue
                j0 = int(k + i * rate)
                ok = False
                for dj in range(-tolerance, tolerance + 1):
                    j = j0 + dj
                    if 0 <= j < len(samples):
                        w = samples[j][side_w]
                        if struct.unpack_from(fmt, w, off)[0] == v:
                            ok = True
                            break
                tot += 1
                eq += ok
            if tot and eq / tot >= 0.85:
                out.append((off, eq, tot))
        return out

    char_fields = {
        'hp': ('<h', lambda t: t[1].get('hp'), 2),
        'action': ('<H', lambda t: t[1].get('action'), 2),
        'sequence': ('<H', lambda t: t[1].get('sequence'), 2),
        'pose': ('<H', lambda t: t[1].get('pose'), 2),
        'poseFrame': ('<H', lambda t: t[1].get('poseFrame'), 2),
        'spirit': ('<H', lambda t: t[1].get('spirit'), 2),
        'position.x': ('<f', lambda t: t[1].get('position.x'), 2),
        'position.y': ('<f', lambda t: t[1].get('position.y'), 2),
        'action_r': ('<H', lambda t: t[2].get('action'), 3),
        'spirit_r': ('<H', lambda t: t[2].get('spirit'), 3),
        'hp_r': ('<h', lambda t: t[2].get('hp'), 3),
        'weather_displayed': ('<b', lambda t: (t[3] or {}).get('displayed'), 5),
        'weather_active': ('<b', lambda t: (t[3] or {}).get('active'), 5),
        'weather_timer': ('<H', lambda t: (t[3] or {}).get('timer'), 5),
    }
    for name, (fmt, getter, sw) in char_fields.items():
        hits = hits_for(getter, fmt, sw)
        res[name] = hits[:4]
        print('  %-18s %s' % (name, hits[:3] if hits else '未命中'))
    # hand 10字节块(±2窗)
    def _hand_bytes(t):
        h = t[1].get('hand')
        if isinstance(h, (bytes, bytearray)):
            return bytes(h)
        if h:
            try:
                return bytes(b for pair in h for b in
                             (int(pair[0]) & 0xFF, int(pair[1]) & 0xFF))
            except (TypeError, ValueError):
                return b''
        return b''
    fv = [_hand_bytes(t) for t in truth]
    out = []
    for off in range(0, win - 10):
        eq = 0
        tot = 0
        for i in range(0, n, 4):
            if len(fv[i]) != 10:
                continue
            j0 = int(k + i * rate)
            ok = False
            for dj in range(-2, 3):
                j = j0 + dj
                if 0 <= j < len(samples) and                         samples[j][2][off:off + 10] == fv[i]:
                    ok = True
                    break
            tot += 1
            eq += ok
        if tot >= 50 and eq / tot >= 0.85:
            out.append((off, eq, tot))
    res['hand'] = out[:4]
    print('  %-18s %s' % ('hand(10B)', out[:3] if out else '未命中'))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rep', default=None)
    ap.add_argument('--win', type=lambda x: int(x, 0), default=0x800)
    ap.add_argument('--tps', type=int, default=60)
    args = ap.parse_args()
    rep = args.rep
    if not rep:
        import glob
        cands = sorted(glob.glob(os.path.join(
            r'D:\temp\th123_models\human_reps', '*.rep')))
        rep = cands[-1] if cands else None
    if not rep or not os.path.exists(rep):
        raise SystemExit('无可用rep(用--rep指定)')
    truth, samples = run_calibration(rep, args.win, args.tps)
    res = solve_offsets(truth, samples, args.win)
    out = os.path.join(HERE, 'rpm_offsets.json')
    json.dump(res, open(out, 'w', encoding='utf8'), indent=1)
    print('[calib] 偏移表:', out)


if __name__ == '__main__':
    main()
