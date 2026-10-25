# -*- coding: utf-8 -*-
"""task-60: BC 补锚离线采集工具（R1 合规：隔离游戏 + 只写己方输入；
不读对手输入；仅离线数据）。生成 trio 兼容 X/S/Y 锚行 + manifest。

用法:
  python tools/bc_anchor_collect.py --chars reimu,marisa --seeds 2
产物:
  D:\\temp\\th123_anchor\\bc_anchor_<char>_<ts>.npz  (X,S,Y,src 字符串数组)
  D:\\temp\\th123_anchor\\manifest_<char>_<ts>.json
"""
import argparse
import hashlib
import io
import json
import os
import struct
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import macro_executor as ME  # noqa: E402
from feat_builder import FeatureBuilder, eff_untech  # noqa: E402
from reach_maps import resolve_reach, resolve_startup  # noqa: E402
from side_driver import EvalEnv  # noqa: E402
from train_tm import CHAR_LIBS, TMTrainer  # noqa: E402

NEUTRAL = {"A": False, "B": False, "C": False, "D": False,
           "SC": False, "SW": False, "H": 0, "V": 0}
GUARD_ALL_IDS = frozenset(range(150, 167))
GUARD_PREP_SET = set()
KNOCK = set(range(50, 79))
TARGET_KEYS = ('连段', '空连', '版边连', '压起身', '原子', '择·', 'B6C', 'TM·')
DEFAULT_OUT = r'D:\temp\th123_anchor'


def step(env, il, ir):
    try:
        return env.step(il or {}, ir or {})
    except Exception:
        return None


def sync(env, lx, rx, ry=0.0):
    ok = 0
    for i in range(300):
        if i % 40 == 0:
            try:
                env.inst._send(struct.pack("<BHH", 13, 10000, 10000))
                env.inst._send(struct.pack("<B4f", 14, lx, 0.0, rx, ry))
            except Exception:
                pass
        r = step(env, dict(NEUTRAL), dict(NEUTRAL))
        if r is None:
            return None
        if ry > 0:
            # 空中场景: 对手下落中 action!=0; 等左方 idle 即可
            if i >= 20 and r[0]['action'] == 0:
                return r
            continue
        if r[0]['action'] == 0 and r[1]['action'] == 0:
            ok += 1
            if ok >= 5:
                return r
        else:
            ok = 0
    return None


def finalize_rows(Xs, Ss, Ys, srcs, cap=400):
    """去重(X 哈希) + 每宏上限; 返回 (X,S,Y,src,per_macro)."""
    seen = set()
    outX, outS, outY, outSrc = [], [], [], []
    per = {}
    for X, S, Y, src in zip(Xs, Ss, Ys, srcs):
        h = hashlib.md5(np.asarray(X).tobytes()).hexdigest()
        key = (h, int(Y))   # 同 X 不同宏=不同动作选择样本, 允许并存
        if key in seen:
            continue
        if per.get(int(Y), 0) >= cap:
            continue
        seen.add(key)
        per[int(Y)] = per.get(int(Y), 0) + 1
        outX.append(X)
        outS.append(S)
        outY.append(int(Y))
        outSrc.append(src)
    return (np.stack(outX).astype(np.uint8), np.stack(outS),
            np.array(outY, dtype=np.int64), np.array(outSrc), per)


class FeatCtx:
    """复刻训练侧 side/visual 特征（4/5N+391 布局, GEN2）。"""

    def __init__(self, char):
        self.char = char
        lib = CHAR_LIBS[char]
        self.macros = lib['macros']
        self.n = len(self.macros)
        self.names = [m[0] for m in self.macros]
        self.fb = FeatureBuilder(self.n)
        self.fb._char_name = char
        self.visual_hist = []
        self.dir_frames = 0
        self.last_dir = None
        self.macro_reach, self.macro_reach_v = resolve_reach(
            self.macros, char)
        self.reach_mask = (self.macro_reach > 0) & np.array(
            [n in lib['attack'] for n in self.names], bool)
        self.reach_v_mask = (self.macro_reach_v > 0) & np.array(
            [n in lib['attack'] for n in self.names], bool)
        self.macro_startup = resolve_startup(self.macros, char)
        self.startup_mask = self.macro_startup > 0
        self.opp_id = getattr(TMTrainer, '_CHAR_POOL_IDX', {}).get(char)
        self.opp_vx = 0.0

    def _push_visual(self, left, right, objs):
        img = TMTrainer._render_frame(None, left, right, objs)
        self.visual_hist.append(img.ravel())
        if len(self.visual_hist) > 5:
            self.visual_hist.pop(0)

    def _visual(self):
        if len(self.visual_hist) < 3:
            return None
        f0, f1, f2 = self.visual_hist[-3], self.visual_hist[-2], \
            self.visual_hist[-1]
        d1 = np.clip(f2.astype(np.int16) - f1.astype(np.int16),
                     0, 255).astype(np.uint8)
        d2 = np.clip(f1.astype(np.int16) - f0.astype(np.int16),
                     0, 255).astype(np.uint8)
        return np.concatenate([f2, d1, d2])

    def _side(self, left, right, weather, bullets, last_macro,
              last_macro2):
        core = self.fb.build(left, right, weather, bullets)
        if self.opp_id is not None and self.opp_id <= 19:
            core[227 + self.opp_id] = 1.0
        elif self.opp_id is not None:
            core[TMTrainer._EXT_OPP_OFF + (self.opp_id - 20)] = 1.0
        core[33] = min(self.dir_frames, 62) / 62.0
        n = self.n
        s = np.zeros(5 * n + FeatureBuilder.CORE_DIMS, dtype=np.float32)
        s[last_macro] = 1.0
        s[n + last_macro2] = 1.0
        s[2 * n:2 * n + FeatureBuilder.CORE_DIMS] = core
        b0 = 2 * n + FeatureBuilder.CORE_DIMS
        adx = abs(right['position.x'] - left['position.x'])
        ady = abs(right['position.y'] - left['position.y'])
        s[b0:b0 + n] = (np.clip((adx - self.macro_reach) / 200.0, -1, 1)
                        * self.reach_mask)
        s[b0 + n:b0 + 2 * n] = (np.clip((ady - self.macro_reach_v) / 200.0,
                                        -1, 1) * self.reach_v_mask)
        ut = eff_untech(right)
        s[b0 + 2 * n:] = (np.clip((ut - self.macro_startup) / 50.0, -1, 1)
                          * self.startup_mask)
        return s

    def feed(self, left, right, weather, objs):
        """逐帧更新特征上下文（visual 栈/朝向/对手速度EMA）。"""
        self._push_visual(left, right, objs)
        d_now = 1 if left['direction'] > 0 else -1
        if d_now != self.last_dir:
            self.dir_frames = 0
            self.last_dir = d_now
        else:
            self.dir_frames += 1
        bullets = self.fb.track_bullets(objs, own=left)
        self.fb.update_opp(10 / 62, left, right, weather,
                           opp_vx=self.opp_vx)
        return bullets


def execute_macro(env, ctx, script, max_frames=240):
    """执行宏并返回 (strict_ok, dmg, acts)。"""
    hp0 = None
    queue = []
    ME.enqueue_script(queue, script)
    dname = 'X'
    gate = 0
    pending = 0.0
    hist = []
    tail = 0
    dmg = 0.0
    acts = set()
    left = right = weather = objs = None
    for f in range(max_frames + 45):
        r = step(env, {}, {})
        if r is None:
            break
        left, right, weather, objs = r[0], r[1], r[2], r[3]
        if hp0 is None:
            hp0 = float(right['hp'])
        bullets = ctx.feed(left, right, weather, objs)
        d = pending
        if f < max_frames and (queue or tail < 45):
            if queue:
                dx = right['position.x'] - left['position.x']
                frozen = left['hitStop'] > 0 or right['hitStop'] > 0
                hist.append(float(d))
                hit_mem = float(sum(hist[-24:]))
                try:
                    queue, gate, dname, inp = ME.advance_queue(
                        queue, gate, left, right, d, 0.0, frozen,
                        float(left['spirit']), dx, dname, GUARD_PREP_SET,
                        GUARD_ALL_IDS, lambda o: (False, True, {}),
                        lambda: None, hit_mem=hit_mem)
                except Exception:
                    break
                il = dict(NEUTRAL)
                if isinstance(inp, dict):
                    for k, v in inp.items():
                        if k in ('H', 'V'):
                            il[k] = v
                        elif k in ('A', 'B', 'C', 'D'):
                            il[k] = bool(v)
                rb = step(env, il, {})
                if rb is None:
                    break
                left = rb[0]
                right = rb[1]
                pending = max(0.0, float(right['hp']) - float(right['hp']))
                pending = 0.0  # placeholder, corrected below
            else:
                tail += 1
        dmg = float(hp0) - float(right['hp'])
        if int(left['action']) not in (0,) and not (50 <= int(left['action']) <= 78):
            acts.add(int(left['action']))
    strict = (dmg >= 300.0) or (len(acts) >= 2)
    return strict, dmg, sorted(acts)[:8]


def capture_row(env, ctx, macro_id, script, scenario, x0, dx, ry, ts):
    """在决策点采集一行(X,S,Y) + 执行复验(strict)。"""
    if scenario == 'wakeup':
        r0 = sync(env, x0, x0 + dx)
        if r0 is None:
            return None
        # 击倒: 左 C/2C 8F → 等 knockdown
        for keys in ({'C': True, 'V': 1}, {'C': True}):
            for _ in range(8):
                step(env, dict(NEUTRAL, **keys), {})
        knocked = False
        for _ in range(30):
            r = step(env, dict(NEUTRAL), {})
            if r is None:
                break
            if int(r[1]['action']) in KNOCK:
                knocked = True
                break
        if not knocked:
            return None
        try:
            env.inst._send(struct.pack("<B4f", 14, x0, 0.0, x0 + dx, 0.0))
        except Exception:
            pass
    else:
        r0 = sync(env, x0, x0 + dx, ry)
        if r0 is None:
            return None
    # 决策点: 3 帧稳定视觉栈
    r = None
    for _ in range(4):
        r = step(env, dict(NEUTRAL), {})
        if r is None:
            return None
    left, right, weather, objs = r
    ctx.feed(left, right, weather, objs)
    bullets = None
    # 决策点特征(此时采集; 执行后回填)
    for _ in range(2):
        rb = step(env, dict(NEUTRAL), {})
        if rb is None:
            return None
        ctx.feed(rb[0], rb[1], rb[2], rb[3])
        left, right, weather, objs = rb
    X = ctx._visual()
    if X is None:
        return None
    bullets = ctx.fb.track_bullets(objs, own=left)
    S = ctx._side(left, right, weather, bullets, macro_id, macro_id)
    # 执行宏复验
    strict = False
    try:
        # 注意: execute_macro 重新 step, 决策点状态需在宏入队前
        queue = []
        ME.enqueue_script(queue, script)
        dname = 'X'
        gate = 0
        hist = []
        pending = 0.0
        hp0 = float(right['hp'])
        acts = set()
        dmg = 0.0
        for f in range(285):
            if queue:
                dxv = right['position.x'] - left['position.x']
                frozen = left['hitStop'] > 0 or right['hitStop'] > 0
                hist.append(float(pending))
                try:
                    queue, gate, dname, inp = ME.advance_queue(
                        queue, gate, left, right, pending, 0.0, frozen,
                        float(left['spirit']), dxv, dname, GUARD_PREP_SET,
                        GUARD_ALL_IDS, lambda o: (False, True, {}),
                        lambda: None, hit_mem=float(sum(hist[-24:])))
                except Exception:
                    break
                il = dict(NEUTRAL)
                if isinstance(inp, dict):
                    for k, v in inp.items():
                        if k in ('H', 'V'):
                            il[k] = v
                        elif k in ('A', 'B', 'C', 'D'):
                            il[k] = bool(v)
            else:
                il = dict(NEUTRAL)
            hp_b = float(right['hp'])
            rb = step(env, il, {})
            if rb is None:
                break
            left, right, weather, objs = rb
            pending = max(0.0, hp_b - float(right['hp']))
            dmg = hp0 - float(right['hp'])
            a = int(left['action'])
            if a and not (50 <= a <= 78):
                acts.add(a)
            if not queue and f > 5:
                # 尾随 30F 结算
                for _ in range(30):
                    rb = step(env, dict(NEUTRAL), {})
                    if rb is None:
                        break
                    left, right = rb[0], rb[1]
                    dmg = hp0 - float(right['hp'])
                break
        strict = (dmg >= 300.0) or (len(acts) >= 2)
    except Exception:
        return None
    if not strict:
        return None
    src = json.dumps({'char': ctx.char, 'macro': ctx.names[macro_id],
                      'scenario': scenario, 'x0': x0, 'dx': dx,
                      'ry': ry, 'ts': ts, 'dmg': round(dmg, 1),
                      'acts': sorted(acts)[:6]}, ensure_ascii=False)
    return X, S, src


def build_manifest(char, n_macros, X, Sv, Yv, npz_name, ts, names):
    """锚数据 manifest（provenance/来源/R1 合规登记）。"""
    return {
        'char': char, 'ts': ts, 'source': 'offline_replay_anchor',
        'n_rows': int(len(Yv)), 'n_macros': int(n_macros),
        'S_width': int(Sv.shape[1]), 'X_width': int(X.shape[1]),
        'layout': '5N+391:v2', 'r1_compliant': True,
        'note': '只写己方输入; 对手=木头人无输入; 非人类分布(provenance见 src)',
        'per_macro': {names[i]: int((Yv == i).sum())
                      for i in sorted(set(Yv.tolist()))},
        'npz': npz_name,
    }


def collect(char, out_dir, seeds=2):
    lib = CHAR_LIBS[char]
    macs = lib['macros']
    names = [m[0] for m in macs]
    Y = np.load(os.path.join(r'D:\temp\th123_models',
                             'bc_%s_Y.npy' % char), mmap_mode='r')
    tot = len(Y)
    targets = []
    for i, n in enumerate(names):
        if not any(k in n for k in TARGET_KEYS):
            continue
        rows = int((Y == i).sum())
        if rows / max(1, tot) < 0.005:   # 覆盖<0.5% 的连段类目标
            targets.append(i)
    print('[anchor] %s targets=%d: %s' % (char, len(targets),
                                          [names[i] for i in targets]))
    Xs, Ss, Ys, srcs = [], [], [], []
    env = EvalEnv(21090 + ord(char[0]) % 7, char_left=char,
                  char_right=char, vs_com=False, tps=None)
    ctx = FeatCtx(char)
    ts = time.strftime('%Y%m%d_%H%M%S')
    try:
        for _ in range(240):
            if step(env, dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        per_macro = {}
        for mid in targets:
            per_macro[names[mid]] = 0
            for scenario in ('mid', 'corner', 'close', 'air', 'wakeup'):
                for seed in range(seeds):
                    if scenario == 'mid':
                        x0 = 420.0 + 60 * seed
                        dx = 55.0 + 8 * seed
                        ry = 0.0
                    elif scenario == 'corner':
                        x0 = 900.0 - 40 * seed
                        dx = 70.0 - 5 * seed
                        ry = 0.0
                    elif scenario == 'close':
                        x0 = 500.0 + 25 * seed
                        dx = 40.0
                        ry = 0.0
                    elif scenario == 'air':
                        x0 = 480.0 + 40 * seed
                        dx = 80.0
                        ry = 120.0
                    else:
                        x0 = 500.0 + 20 * seed
                        dx = 60.0
                        ry = 0.0
                    if per_macro[names[mid]] >= 400:
                        break
                    try:
                        row = capture_row(env, ctx, mid, macs[mid][1],
                                          scenario, x0, dx, ry, ts)
                    except Exception as e:
                        print('  skip %s/%s: %r' % (names[mid],
                                                   scenario, e))
                        continue
                    if row is None:
                        continue
                    X, S, src = row
                    Xs.append(X)
                    Ss.append(S.astype(np.float32))
                    Ys.append(mid)
                    srcs.append(src)
                    per_macro[names[mid]] += 1
            print('  %-10s rows=%d' % (names[mid], per_macro[names[mid]]),
                  flush=True)
    finally:
        try:
            env.close()
        except Exception:
            pass
    if not Xs:
        print('[anchor] %s 无有效行' % char)
        return None
    X, Sv, Yv, srcv, _per = finalize_rows(Xs, Ss, Ys, srcs, cap=400)
    per_macro = {names[i]: int(_per.get(i, 0)) for i in _per}

    os.makedirs(out_dir, exist_ok=True)
    npz = os.path.join(out_dir, 'bc_anchor_%s_%s.npz' % (char, ts))
    np.savez_compressed(npz, X=X, S=Sv, Y=Yv, src=srcv)
    manifest = build_manifest(char, len(macs), X, Sv, Yv,
                              os.path.basename(npz), ts, names)
    mj = os.path.join(out_dir, 'manifest_%s_%s.json' % (char, ts))
    io.open(mj, 'w', encoding='utf-8').write(
        json.dumps(manifest, ensure_ascii=False, indent=1))
    print('[anchor] %s rows=%d X=%s S=%s -> %s'
          % (char, len(Yv), X.shape, Sv.shape, npz))
    return npz, mj, manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chars', default='reimu,marisa,suika')
    ap.add_argument('--seeds', type=int, default=2)
    ap.add_argument('--out', default=DEFAULT_OUT)
    a = ap.parse_args()
    res = {}
    for ch in [c.strip() for c in a.chars.split(',') if c.strip()]:
        r = collect(ch, a.out, a.seeds)
        if r:
            res[ch] = r[2]
    print('[anchor] DONE', json.dumps(res, ensure_ascii=False)[:500])


if __name__ == '__main__':
    main()
