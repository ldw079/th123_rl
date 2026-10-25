# -*- coding: utf-8 -*-
"""task-60 v2: BC 补锚离线采集（修复 P0-1 标签泄漏 + P0-2 独立真值 + P1）。

R1: 隔离游戏 replay，只写己方输入；对手木头人无输入；未读取对手输入。
R15: 每行 combo_ok 行为判据(dmg>=300 且 >=2 攻击动作) + **独立盲复验**(held-out
场景，按记录的原始输入序列盲放，不经 executor) + provenance。
P0-1: S 前 2N 宏 one-hot 只含**决策前历史**(本数据集固定=待机)，绝不写 target；
      逐行断言 S[Y]==0 且 S[N+Y]==0。
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
CAP_PER_MACRO = 400
MIN_LABEL_SHARE = 0.005


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


def sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()[:16]


def finalize_rows(Xs, Ss, Ys, srcs, cap=CAP_PER_MACRO):
    seen = set()
    outX, outS, outY, outSrc = [], [], [], []
    per = {}
    same_x = {}
    conflicts = 0
    for X, S, Y, src in zip(Xs, Ss, Ys, srcs):
        h = hashlib.md5(np.asarray(X).tobytes()).hexdigest()
        key = (h, int(Y))
        if key in seen:
            continue
        if per.get(int(Y), 0) >= cap:
            continue
        if h in same_x and int(Y) not in same_x[h]:
            conflicts += 1
        same_x.setdefault(h, set()).add(int(Y))
        seen.add(key)
        per[int(Y)] = per.get(int(Y), 0) + 1
        outX.append(X)
        outS.append(S)
        outY.append(int(Y))
        outSrc.append(src)
    return (np.stack(outX).astype(np.uint8), np.stack(outS),
            np.array(outY, dtype=np.int64), np.array(outSrc), per,
            conflicts)


def combo_ok(dmg, acts):
    """行为判据: 伤害>=300 且 >=2 个攻击动作(非仅 acts>=2)。"""
    return bool(dmg >= 300.0 and len(acts) >= 2)


def rle_compress(seq):
    """输入序列 RLE: [{键:bool}] → [[[键,True],...] 帧数]."""
    out = []
    for d in seq:
        key = tuple(sorted((k, v) for k, v in d.items() if v))
        if out and out[-1][0] == key:
            out[-1][1] += 1
        else:
            out.append([key, 1])
    return [[list(k), n] for k, n in out]


def assert_no_target_leak(S, n, macro_id):
    """P0-1: S 前 2N 宏 one-hot 槽不得含 target 宏."""
    if S[macro_id] > 1e-6 or S[n + macro_id] > 1e-6:
        raise RuntimeError('P0-1 标签泄漏: target 宏 %d 出现在 S 宏槽'
                           % macro_id)
    return True


def blind_run(env, inputs, max_frames=None):
    """独立盲复验: 从当前对局状态按记录输入序列盲放(不经 executor)。"""
    hp0 = None
    acts = set()
    frames = 0
    for keys in inputs:
        if max_frames and frames >= max_frames:
            break
        r = step(env, keys, {})
        if r is None:
            break
        left, right = r[0], r[1]
        if hp0 is None:
            hp0 = float(right['hp'])
        a = int(left['action'])
        if a and not (50 <= a <= 78):
            acts.add(a)
        frames += 1
    dmg = (hp0 - float(right['hp'])) if hp0 is not None else 0.0
    return dmg, sorted(acts)


class FeatCtx:
    """复刻训练侧 side/visual 特征（5N+391 布局, GEN2）。"""

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
        # 决策前历史(因果): 本数据集固定 idle/待机, 不含 target
        self.idle_idx = next((i for i, n in enumerate(self.names)
                              if n == '待机'), 0)
        self.last_macro = self.idle_idx
        self.last_macro2 = self.idle_idx

    def reset_history(self):
        self.last_macro = self.idle_idx
        self.last_macro2 = self.idle_idx

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

    def _side(self, left, right, weather, bullets):
        core = self.fb.build(left, right, weather, bullets)
        if self.opp_id is not None and self.opp_id <= 19:
            core[227 + self.opp_id] = 1.0
        elif self.opp_id is not None:
            core[TMTrainer._EXT_OPP_OFF + (self.opp_id - 20)] = 1.0
        core[33] = min(self.dir_frames, 62) / 62.0
        n = self.n
        s = np.zeros(5 * n + FeatureBuilder.CORE_DIMS, dtype=np.float32)
        # 只写决策前因果历史(本数据集=待机), 不含 target
        s[self.last_macro] = 1.0
        s[n + self.last_macro2] = 1.0
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


def _scenario_keys(x0, dx, ry, macro_id):
    """生成集位置。"""
    return x0, dx, ry


HELDOUT = {
    'mid': (12.0, 5.0, 0.0),
    'corner': (-10.0, -3.0, 0.0),
    'close': (6.0, 3.0, 0.0),
    'air': (8.0, 4.0, 8.0),
    'wakeup': (6.0, 2.0, 0.0),
}


def capture_row(env, ctx, macro_id, script, scenario, x0, dx, ry, ts):
    """采集一行(X,S,Y) + 生成复验(combo_ok) + 独立盲复验(held-out)。"""
    ctx.reset_history()
    if scenario == 'wakeup':
        r0 = sync(env, x0, x0 + dx)
        if r0 is None:
            return None
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
    # 决策点特征（3 帧视觉栈 + 历史=待机）
    r = None
    for _ in range(4):
        r = step(env, dict(NEUTRAL), {})
        if r is None:
            return None
    left, right, weather, objs = r
    ctx.feed(left, right, weather, objs)
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
    S = ctx._side(left, right, weather, bullets)
    n = ctx.n
    # P0-1 自动检查: target 宏不在 S 的宏 one-hot 槽
    assert_no_target_leak(S, n, macro_id)
    # 生成复验: 记录原始输入序列(供独立盲复验)
    inputs = []
    hp0 = float(right['hp'])
    acts = set()
    dmg = 0.0
    queue = []
    ME.enqueue_script(queue, script)
    dname = 'X'
    gate = 0
    hist = []
    pending = 0.0
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
        inputs.append({k: bool(v) for k, v in il.items()})
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
            for _ in range(30):
                inputs.append(dict(NEUTRAL))
                rb = step(env, dict(NEUTRAL), {})
                if rb is None:
                    break
                left, right = rb[0], rb[1]
                dmg = hp0 - float(right['hp'])
            break
    if not combo_ok(dmg, acts):
        return None
    # 独立盲复验(held-out 场景, 原始输入盲放, 不经 executor)
    hx0, hdx, hry = HELDOUT.get(scenario, HELDOUT['mid'])
    hx = x0 + hx0
    hdxv = dx + hdx
    if scenario == 'wakeup':
        r0 = sync(env, hx, hx + hdxv)
        if r0 is not None:
            for keys in ({'C': True, 'V': 1}, {'C': True}):
                for _ in range(8):
                    step(env, dict(NEUTRAL, **keys), {})
    else:
        r0 = sync(env, hx, hx + hdxv, max(0.0, ry + hry))
    if r0 is None:
        held = {'ok': False, 'dmg': 0.0, 'error': 'heldout_sync'}
    else:
        hdmg, hacts = blind_run(env, inputs)
        held = {'ok': bool(combo_ok(hdmg, hacts)),
                'dmg': round(float(hdmg), 1),
                'acts': hacts[:6]}
    # RLE 压缩输入序列(供复验/审计)
    src = json.dumps({
        'char': ctx.char, 'macro': ctx.names[macro_id],
        'macro_id': int(macro_id), 'scenario': scenario,
        'gen_pos': [x0, dx, ry], 'ts': ts,
        'dmg': round(float(dmg), 1), 'acts': sorted(acts)[:6],
        'combo_ok': True, 'heldout': held,
        'seq': rle_compress(inputs),
    }, ensure_ascii=False)
    return X, S, src


def build_manifest(char, n_macros, X, Sv, Yv, npz_name, ts, names,
                   extra=None):
    m = {
        'char': char, 'ts': ts, 'source': 'offline_replay_anchor',
        'generator': 'tools/bc_anchor_collect.py v2',
        'gen_cmd': 'python tools/bc_anchor_collect.py --chars %s --seeds N'
                   % char,
        'verify_cmd': 'python tools/bc_anchor_verify.py --char %s --npz <npz>'
                      % char,
        'n_rows': int(len(Yv)), 'n_macros': int(n_macros),
        'S_width': int(Sv.shape[1]), 'X_width': int(X.shape[1]),
        'layout': '5N+391:v2', 'r1_compliant': True,
        'target_leak_check': 'S[Y]==0 and S[N+Y]==0 (all rows)',
        'hashes': {'X': sha(X), 'S': sha(Sv), 'Y': sha(Yv)},
        'note': '只写己方输入; 对手=木头人无输入; 非人类分布(provenance in src)',
        'per_macro': {names[i]: int((Yv == i).sum())
                      for i in sorted(set(Yv.tolist()))},
        'npz': npz_name,
    }
    if extra:
        m.update(extra)
    return m


def collect(char, out_dir, seeds=4):
    lib = CHAR_LIBS[char]
    macs = lib['macros']
    names = [m[0] for m in macs]
    Y = np.load(os.path.join(r'D:\temp\th123_models',
                             'bc_%s_Y.npy' % char), mmap_mode='r')
    tot = len(Y)
    targets = [i for i, n in enumerate(names)
               if any(k in n for k in TARGET_KEYS)
               and int((Y == i).sum()) / max(1, tot) < MIN_LABEL_SHARE]
    print('[anchor] %s targets=%d: %s' % (char, len(targets),
                                          [names[i] for i in targets]))
    Xs, Ss, Ys, srcs = [], [], [], []
    env = EvalEnv(21090 + ord(char[0]) % 7, char_left=char,
                  char_right=char, vs_com=False, tps=360)
    ctx = FeatCtx(char)
    ts = time.strftime('%Y%m%d_%H%M%S')
    held_tot = held_ok = 0
    try:
        for _ in range(240):
            if step(env, dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        per_macro = {}
        for mid in targets:
            per_macro[names[mid]] = 0
            seqs = (('mid', 420.0, 55.0, 0), ('corner', 900.0, 70.0, 0),
                    ('close', 500.0, 40.0, 0), ('air', 480.0, 80.0, 120),
                    ('wakeup', 500.0, 60.0, 0))
            # 前两轮标准 seeds + 低配额补采(追加种子)
            plan = list(range(seeds))
            for scenario, base_x, base_dx, ry in seqs:
                for seed in plan:
                    if per_macro[names[mid]] >= CAP_PER_MACRO:
                        break
                    if per_macro[names[mid]] >= 20:
                        continue
                    x0 = base_x + (60 if scenario == 'mid' else
                                   -40 if scenario == 'corner' else
                                   25 if scenario == 'close' else
                                   40 if scenario == 'air' else 20) * seed
                    dx = base_dx + (8 if scenario == 'mid' else
                                    -5 if scenario == 'corner' else
                                    (9 if scenario == 'close' else
                                     12 if scenario == 'air' else 8)) * seed
                    try:
                        row = capture_row(env, ctx, mid, macs[mid][1],
                                          scenario, x0, dx,
                                          float(ry), ts)
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
                    try:
                        h = json.loads(src).get('heldout') or {}
                        held_tot += 1
                        held_ok += 1 if h.get('ok') else 0
                    except Exception:
                        pass
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
    X, Sv, Yv, srcv, _per, conflicts = finalize_rows(Xs, Ss, Ys, srcs)
    per_macro = {names[i]: int(_per.get(i, 0)) for i in _per}
    os.makedirs(out_dir, exist_ok=True)
    npz = os.path.join(out_dir, 'bc_anchor_%s_%s.npz' % (char, ts))
    np.savez_compressed(npz, X=X, S=Sv, Y=Yv, src=srcv)
    extra = {'seed_base': seeds,
             'heldout_consistency': {
                 'n': int(held_tot),
                 'ok': int(held_ok),
                 'rate': round(held_ok / max(1, held_tot), 3)},
             'same_x_conflicts': int(conflicts),
             'quota_min': min(per_macro.values()) if per_macro else 0}
    manifest = build_manifest(char, len(macs), X, Sv, Yv,
                              os.path.basename(npz), ts, names, extra)
    mj = os.path.join(out_dir, 'manifest_%s_%s.json' % (char, ts))
    io.open(mj, 'w', encoding='utf-8').write(
        json.dumps(manifest, ensure_ascii=False, indent=1))
    print('[anchor] %s rows=%d X=%s S=%s heldout=%.2f conflicts=%d -> %s'
          % (char, len(Yv), X.shape, Sv.shape,
             manifest['heldout_consistency']['rate'], conflicts, npz))
    return npz, mj, manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chars', default='reimu,marisa,suika')
    ap.add_argument('--seeds', type=int, default=4)
    ap.add_argument('--out', default=DEFAULT_OUT)
    a = ap.parse_args()
    res = {}
    for ch in [c.strip() for c in a.chars.split(',') if c.strip()]:
        r = collect(ch, a.out, a.seeds)
        if r:
            res[ch] = r[2]
    print('[anchor] DONE', json.dumps(res, ensure_ascii=False)[:600])


if __name__ == '__main__':
    main()
