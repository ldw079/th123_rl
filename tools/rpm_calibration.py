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

    def __init__(self, pid, win=0x800):
        super().__init__(daemon=True)
        self.h = k32.OpenProcess(0x10 | 0x20 | 0x8 | 0x400, False, pid)
        self.win = win
        self.samples = []       # [(t, scene, cmL_bytes, cmR_bytes, bm_bytes)]
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
            if wL and wR and bmw:
                self.samples.append((time.time(), scene[0], wL, wR, bmw))
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
                              payload['left'], payload['right']))
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
    """离线解: 每字段在窗口内找逐帧相等的偏移。

    对齐v2: 已确认的hp偏移(388=0x184, 与tm_env既知一致)作锚 —
    内存hp序列与真值hp序列做**互相关**解最优(帧0样本号k, 每帧样本
    步进rate), 再按该映射逐字段匹配。字段判据: 只在**值变化帧**上
    匹配(常零区歧义消除), ≥90%变化帧相等。
    """
    res = {'_meta': {'truth_frames': len(truth), 'rpm_samples': len(samples),
                     'win': win}}
    if not truth or not samples:
        return res
    n = len(truth)
    hp_off = 388   # 已双重确认(本轮+tm_env既知0x184)
    truth_hp = [l.get('hp') for _fc, l, _r in truth]
    mem_hp = []
    for _t, _sc, wL, _wR, _bm in samples:
        mem_hp.append(struct.unpack_from('<h', wL, hp_off)[0])

    # 互相关对齐: 找(k, rate)最大化|hp相等数| — rate网格按实测
    # 样本/帧比自适应中心±40%(首轮硬编码1.7-2.2在tps=120下全miss)
    import numpy as _np
    center = len(samples) / max(n, 1)
    best = (0, center, -1)
    for rate in [center * (0.6 + 0.04 * i) for i in range(21)]:
        for k in range(0, max(len(samples) - int(n * rate), 1)):
            eq = 0
            for i in range(0, n, 5):
                j = int(k + i * rate)
                if j >= len(samples):
                    break
                if mem_hp[j] == truth_hp[i]:
                    eq += 1
            if eq > best[2]:
                best = (k, rate, eq)
    print('  [对齐] k=%d rate=%.3f hp锚命中%d/%d' % (
        best[0], best[1], best[2], len(range(0, n, 5))))
    k, rate, _ = best
    res['_meta']['align'] = {'k': k, 'rate': round(rate, 2)}

    # 两阶段精对齐(v3): ①窗口内扫**单调u32计数器**候选(frameCount),
    # 用"以它建帧同步后hp@388一致率"作评分选定; ②用选定计数器做
    # 精确帧同步(j_of), 其余字段在该样本上匹配 — hp跟踪式(恒值段
    # 多解)对快变字段(action/pose/position)对不齐的修复
    def _mono_candidates(winL):
        cands = []
        for off in range(0, win - 4, 4):
            prev = None
            mono = True
            for _t, _sc, w, _r, _b in samples[::20]:
                v = struct.unpack_from('<I', w, off)[0]
                if prev is not None and not (0 <= v - prev <= 40):
                    mono = False
                    break
                prev = v
            if mono and prev and prev > 100:
                cands.append(off)
        return cands

    truth_fc = [fc for fc, _l, _r in truth]
    fc_off = None
    best_hp_eq = 0
    for off in _mono_candidates(win):
        j_c = [None] * n
        for i in range(n):
            j0 = int(k + i * rate)
            for dj in range(0, 9):
                for j in (j0 + dj, j0 - dj):
                    if 0 <= j < len(samples):
                        _, _sc, w, _r, _b = samples[j]
                        if struct.unpack_from('<I', w, off)[0] == truth_fc[i]:
                            j_c[i] = j
                            break
                if j_c[i] is not None:
                    break
        eqs = sum(1 for i in range(n)
                  if j_c[i] is not None
                  and mem_hp[j_c[i]] == truth_hp[i])
        if eqs > best_hp_eq and eqs > 0.5 * n:
            best_hp_eq = eqs
            fc_off = off
            j_of = j_c
    if fc_off is not None:
        res['_meta']['frameCount_offset'] = fc_off
        print('  [对齐] frameCount偏移=%d hp一致%d/%d' % (
            fc_off, best_hp_eq, n))
    else:
        # 回退hp跟踪式
        j_of = [None] * n
    if fc_off is None:
        for i in range(n):
            if truth_hp[i] is None:
                continue
            j0 = int(k + i * rate)
            # 变化帧用宽窗(±25): hp锚相等式跟踪在值变化瞬间天然失配,
            # 首个新值样本=变化点
            _w = 25 if (i and truth_hp[i] != truth_hp[i - 1]) else 8
            for dj in range(0, _w):
                for j in (j0 + dj, j0 - dj):
                    if 0 <= j < len(samples) and mem_hp[j] == truth_hp[i]:
                        j_of[i] = j
                        break
                if j_of[i] is not None:
                    break
    _tracked = sum(1 for x in j_of if x is not None)
    print('  [对齐] hp跟踪命中 %d/%d' % (_tracked, n))
    res['_meta']['tracked'] = _tracked

    def aligned(i):
        j = j_of[i]
        if j is None:
            j = int(k + i * rate)
        return samples[min(j, len(samples) - 1)]

    fields = {
        'hp': ('left', 'hp', '<h'),
        'action': ('left', 'action', '<H'),
        'sequence': ('left', 'sequence', '<H'),
        'poseFrame': ('left', 'poseFrame', '<H'),
        'position.x': ('left', 'position.x', '<f'),
        'position.y': ('left', 'position.y', '<f'),
        'spirit': ('left', 'spirit', '<H'),
        'score': ('left', 'score', '<B'),
        'frameCount': ('left', 'frameCount', '<I'),
    }
    for name, (side, key, fmt) in fields.items():
        series = []
        for _fc, l, r in truth:
            series.append((l if side == 'left' else r).get(key))
        # 变化帧索引(真值侧值改变处) — 消除常值区歧义
        chg = [i for i in range(1, n)
               if series[i] is not None and series[i] != series[i - 1]]
        if name == 'hp':
            use = [i for i in range(n) if j_of[i] is not None]
        else:
            use = [i for i in chg if j_of[i] is not None]                 if len([i for i in chg if j_of[i] is not None]) >= 8                 else [i for i in range(n) if j_of[i] is not None]
        found = []
        for off in range(0, win - struct.calcsize(fmt) + 1):
            eq = 0
            tot = 0
            for i in use[:300]:
                v = series[i]
                j = j_of[i]
                if j is None:
                    continue
                _, _sc, wL, _wR, _bm = samples[j]
                tot += 1
                if struct.unpack_from(fmt, wL, off)[0] == v:
                    eq += 1
            if tot >= 8 and eq / tot >= 0.9:
                found.append((off, eq, tot))
        res[name] = found[:5]
        print('  %-12s %s (变化帧%d)' % (
            name, found[:3] if found else '未命中', len(chg)))
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
