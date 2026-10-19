# -*- coding: utf-8 -*-
r"""behavior_deep_report: 训练侧行为深度仪表 三表基线(入库工具; task-16).

用法: python tools/behavior_deep_report.py [--since "YYYY-MM-DD HH:MM"] [--until ...]
环境: TH123_STORE / TH123_ACTOR_DIR / TH123_DEEP_OUT_JSON/TXT.

**口径声明**: 本报告是**训练侧**(fleet actor/learner 工件)基线; 与人测(rep)读数
不得混用/互相归因(人测 9-0 已确认=旧模型+OOD, 见审计#6b)。

数据源(只读):
  A) BH 旁车  STORE/fleet/episodes/bh_<char>_*.json  (cls/follow/combo fates)
  B) 帧日志   STORE/frame_logs/<char>/fl_*.pkl  (13状态字段/侧 + objs + 决策帧+宏ID)
  C) actor 日志 D:/temp/actor_<char>_<id>.log  ("[奖励成分]"行: 擦弹+值(N帧)/规避/空挥)
  D) 判定库 behavior_health / frame_events.FrameEventDetector / feat_builder
     (track_bullets/check_graze/threat_predict — 与训练逐帧同源) / CHAR_LIBS /
     my_punish_tracker.classify

三表(用户 2026-10-18 三条观察的量化):
  表1 有效攻击性: 决策级攻击率(宏口径, 标注宏放大) + 状态级攻击窗结局
      (命中/被防/空挥/被打断) + 有效转化率 + 接敌距离/前压/接近率;
      **输入级(按键)攻击率: 训练侧不可得**(帧日志无输入流, episode无inputs键) — 如实标注
  表2 防御与擦弹时机:
      防御: 威胁定义 A=对手出招启动(300-598上升沿), B=弹幕TTI<0.3s(18.6帧)边沿;
            响应窗 W=20帧内进入防御硬直(150-158); 给响应率与 P50/P90; 分母=威胁事件数
      擦弹: **精确事件率=actor日志 graze_frames/局**(训练同源计数) + 帧日志 check_graze
            复算(与训练逐帧同源), 时机=擦弹帧处最近弹 TTI(帧) 分布 + 弹进120px→擦弹 帧差
  表3 连段完成度: ①BH旁车 fates(hit/blocked/dropped/interrupted, 大样本, 宏名判据)
      ②完整连段起手→结算(状态口径, is_combo_macro) 分受击/空挥/被防/超时(无结算)
所有数字带分母/样本量; 输出带时间戳+口径版本号(+ --since/--until 供 bcw ON 后同比).
"""
from __future__ import annotations

import glob
import io
import json
import os
import pickle
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(_HERE)
sys.path.insert(0, REPO)
sys.stdout.reconfigure(encoding='utf8')

from kit_config import STORE_DIR as STORE  # noqa: E402  (TH123_STORE/config 四层回落)
ACTOR_DIR = os.environ.get('TH123_ACTOR_DIR', r'D:\temp')

from behavior_health import (FL_FIELDS, aggregate, is_attack_macro,  # noqa: E402
                             is_combo_macro, rates)
from feat_builder import FeatureBuilder, GAME_FPS, threat_predict  # noqa: E402
from frame_events import (E_NONE, E_NEAR_MISS, E_OPP_JUMP,  # noqa: E402
                          E_OPP_STARTUP, FrameEventDetector)
from my_punish_tracker import classify  # noqa: E402
from train_tm import CHAR_LIBS  # noqa: E402

OUT_JSON = os.environ.get(
    'TH123_DEEP_OUT_JSON',
    os.path.join(os.getcwd(),
                 'behavior_deep_%s.json' % time.strftime('%Y%m%d')))
OUT_TXT = os.environ.get(
    'TH123_DEEP_OUT_TXT',
    os.path.join(os.getcwd(),
                 'behavior_deep_%s.txt' % time.strftime('%Y%m%d')))
EPS = os.path.join(STORE, 'fleet', 'episodes')
FL = os.path.join(STORE, 'frame_logs')
ACTOR_GLOB = os.path.join(ACTOR_DIR, 'actor_%s_*.log')
BH_LAST = int(os.environ.get('DEEP_BH_LAST', '400'))
FL_LOGS = int(os.environ.get('DEEP_FL_LOGS', '25'))
ACTOR_GAMES = int(os.environ.get('DEEP_ACTOR_GAMES', '30'))
VERSION = 'v3-20261018'
PHASE = 'PRE-bcw (bcw=0.00, 训练侧)'

IX = {k: i for i, k in enumerate(FL_FIELDS)}
GUARD_LO, GUARD_HI = 150, 158
THREAT_EVENTS = (E_OPP_STARTUP, E_NEAR_MISS, E_OPP_JUMP)
BROAD = ('MELEE', 'SKILL', 'BULLET')
ATTR_MAX = 60
RESP_W = 20
GUARD_LABEL = '防御硬直态(150-158=成功挡下/guard-stun)'
BULLET_TTI = 0.3 * GAME_FPS        # 18.6 帧阈值 (R19 训练同源)


def _r(x, nd=4):
    return None if x is None else round(x, nd)


def _pct(a, b):
    return _r(100.0 * a / b, 2) if b else None


def _f(x, nd=1, dash='n/a'):
    return dash if x is None else ('%.*f' % (nd, x))


def _pctile(xs, p):
    if not xs:
        return None
    import numpy as np
    return float(np.percentile(np.asarray(xs, dtype=float), p))


def _mtimes(files):
    ts = []
    for p in files:
        try:
            ts.append(os.path.getmtime(p))
        except OSError:
            pass
    if not ts:
        return None, None
    return (time.strftime('%Y-%m-%d %H:%M', time.localtime(min(ts))),
            time.strftime('%Y-%m-%d %H:%M', time.localtime(max(ts))))


def _sel(files, since, until):
    out = []
    for p in files:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if since is not None and m < since:
            continue
        if until is not None and m > until:
            continue
        out.append(p)
    return out


def parse_actor_games(char, since=None, until=None):
    """actor日志 [奖励成分] 行 → 最近 N 局: graze值/graze_frames/规避/空挥/回报."""
    fs = sorted(glob.glob(ACTOR_GLOB % char),
                key=lambda p: os.path.getmtime(p))
    if not fs:
        return {'files': [], 'games': [], 'n_games': 0,
                'frames_total': 0, 'graze_frames_total': 0,
                'graze_per_1000f': None,
                'graze_frames_mean_per_game': None,
                'graze_per_1000f_mean': None,
                'graze_reward_mean_per_game': None,
                'evade_mean_per_game': None,
                'whiff_penalty_mean_per_game': None,
                'note': '无actor日志'}
    p = fs[-1]
    lines = io.open(p, encoding='utf-8', errors='replace').read().splitlines()
    pat = re.compile(r'擦弹\+([\d.]+)\((\d+)帧\)')
    ep_pat = re.compile(
        r'\]\s+\d+:\d+:\d+\s+ep(\d+)\s+(\d+)决策\s+v\d+\s+帧(\d+)')
    games = []
    pending = None
    for ln in lines:
        if '奖励成分' in ln:
            m = pat.search(ln)
            if not m:
                continue
            rec = {'graze_reward': float(m.group(1)),
                   'graze_frames': int(m.group(2))}
            for key, rx in (('evade', r'规避([+-][\d.]+)'),
                            ('whiff', r'空挥([+-][\d.]+)'),
                            ('ko', r'KO([+-][\d.]+)'),
                            ('reward', r'回报([+-][\d.]+)')):
                mm = re.search(rx, ln)
                if mm:
                    rec[key] = float(mm.group(1))
            pending = rec
            continue
        if pending is not None:
            em = ep_pat.search(ln)
            if em:
                _m_time = re.search(r'\]\s+(\d+):(\d+):(\d+)', ln)
                if _m_time:
                    _td = time.localtime()
                    pending['ts'] = time.mktime(
                        (_td.tm_year, _td.tm_mon, _td.tm_mday,
                         int(_m_time.group(1)), int(_m_time.group(2)),
                         int(_m_time.group(3)), 0, 0, -1))
                pending['ep'] = int(em.group(1))
                pending['decisions'] = int(em.group(2))
                pending['frames'] = int(em.group(3))
                pending['graze_per_1000f'] = _r(
                    1000.0 * pending['graze_frames'] / pending['frames'], 2) \
                    if pending['frames'] else None
                games.append(pending)
                pending = None
    # --since/--until 分精度窗口过滤(actor 日志跨重启追加, 必须按局末时间过滤;
    # 2026-10-18 ON 采样修正: 原取"最近30局"会混入停机前局)
    if since is not None:
        games = [g for g in games if g.get('ts') is None or g['ts'] >= since]
    if until is not None:
        games = [g for g in games if g.get('ts') is None or g['ts'] <= until]
    games = games[-ACTOR_GAMES:]
    gs = sum(g['graze_frames'] for g in games)
    fsum = sum(g.get('frames', 0) for g in games)
    return {
        'files': [os.path.basename(p)],
        'sample_window': [time.strftime('%Y-%m-%d %H:%M',
                                        time.localtime(os.path.getmtime(p)))] * 2,
        'games': games, 'n_games': len(games),
        'frames_total': fsum,
        'graze_frames_total': gs,
        'graze_per_1000f': _r(1000.0 * gs / fsum, 2) if fsum else None,
        'graze_frames_mean_per_game': _r(gs / len(games), 1) if games else None,
        'graze_per_1000f_mean': _r(sum(
            g.get('graze_per_1000f') or 0.0 for g in games) / len(games), 2)
        if games else None,
        'graze_reward_mean_per_game': _r(
            sum(g['graze_reward'] for g in games) / len(games), 2) if games else None,
        'evade_mean_per_game': _r(
            sum(g.get('evade', 0.0) for g in games) / len(games), 2) if games else None,
        'whiff_penalty_mean_per_game': _r(
            sum(g.get('whiff', 0.0) for g in games) / len(games), 2) if games else None,
        'note': 'graze_frames=训练循环 check_graze 命中帧数(每局重置, 与奖励同源); '
                'frames=actor日志局帧数; 率=graze_frames/千帧',
    }


def bh_table(char, since=None, until=None):
    allf = glob.glob(os.path.join(EPS, 'bh_%s_*.json' % char))
    files = sorted(_sel(allf, since, until),
                   key=lambda p: (os.path.getmtime(p), p))[-BH_LAST:]
    # 用临时目录视图聚合(aggregate 只接受目录+char): 复制文件名列表的做法
    # 不复制文件 → 直接本地聚合, 与 behavior_health.aggregate 同语义.
    agg = {'n_files': len(files), 'n_dec': 0, 'cls': {},
           'follow': {'hit_atk': 0, 'hit_n': 0, 'nohit_atk': 0, 'nohit_n': 0},
           'combo': {'hit': 0, 'blocked': 0, 'dropped': 0, 'interrupted': 0},
           'combo_by_opp': {}, 'trans': {}}
    for p in files:
        try:
            r = json.load(io.open(p, encoding='utf8'))
        except Exception:
            continue
        agg['n_dec'] += r.get('n_dec', 0)
        for k, v in r.get('cls', {}).items():
            agg['cls'][k] = agg['cls'].get(k, 0) + v
        for k in agg['follow']:
            agg['follow'][k] += r.get('follow', {}).get(k, 0)
        for k in agg['combo']:
            agg['combo'][k] += r.get('combo', {}).get(k, 0)
        for k, v in r.get('trans_top', {}).items():
            agg['trans'][k] = agg['trans'].get(k, 0) + v
    rr = rates(agg)
    n = agg['n_dec']
    strict = sum(v for k, v in agg['cls'].items() if is_attack_macro(k))
    broad = sum(v for k, v in agg['cls'].items() if k in BROAD)
    combo = agg['combo']
    cn = sum(combo.values())
    a, b = _mtimes(files)
    return {
        'source': 'BH旁车(训练侧)',
        'files': agg['n_files'], 'sample_window': [a, b], 'decisions': n,
        'class_counts': dict(sorted(agg['cls'].items(),
                                    key=lambda kv: -kv[1])),
        'attack_rate_strict_pct': _pct(strict, n),
        'attack_rate_broad_pct': _pct(broad, n),
        'attack_rate_note': '宏ID决策口径; 连续步长不一→与按键口径不可直接换算(宏放大)',
        'followup_hit_atk_pct': _r(100 * rr['followup_hit'], 2),
        'followup_nohit_atk_pct': _r(100 * rr['followup_nohit'], 2),
        'combo_total_bh': cn,
        'combo_rates_pct': {
            'hit': _pct(combo['hit'], cn), 'blocked': _pct(combo['blocked'], cn),
            'dropped': _pct(combo['dropped'], cn),
            'interrupted': _pct(combo['interrupted'], cn),
        },
        'combo_note': 'BH表3判据=宏名含"连段/空连/版边连/目押"或MELEE/SKILL且名含"连";'
                      '覆盖窄(TM·复合连段终结等不计入)',
        'trans_top': dict(list(rr['trans_top'].items())[:8]),
    }


def frame_tables(char, since=None, until=None):
    allf = glob.glob(os.path.join(FL, char, 'fl_*.pkl'))
    files = sorted(_sel(allf, since, until),
                   key=lambda p: (os.path.getmtime(p), p))[-FL_LOGS:]
    lib = CHAR_LIBS[char]['macros']
    fb = FeatureBuilder(len(lib))
    fb._char_name = char
    o = {
        'files': 0, 'frames': 0, 'decisions': 0,
        'attack_windows': 0, 'win_hit': 0, 'win_blocked': 0,
        'win_whiff': 0, 'win_interrupted': 0,
        'hit_damage_total': 0.0, 'engage_bands': {}, 'engage_dx_sum': 0.0,
        'engage_n': 0, 'attack_forward_n': 0, 'attack_forward_den': 0,
        'approach_frames': 0, 'motion_frames': 0,
        # 防御
        'threatA_events': 0, 'threatA_guard': 0, 'threatA_delays': [],
        'threatB_events': 0, 'threatB_guard': 0, 'threatB_evade80': 0,
        'threatB_delays': [],
        'guard_frames': 0, 'stand_guard_frames': 0,
        'crouch_guard_frames': 0, 'air_guard_frames': 0,
        'hp_drop_frames': 0, 'hp_drop_guarded_prev10': 0,
        # 擦弹(check_graze 训练同源)
        'graze_frames': 0, 'graze_tti': [], 'graze_leadin': [],
        # 连段(状态口径)
        'combo_windows': 0, 'combo_hit': 0, 'combo_blocked': 0,
        'combo_whiff': 0, 'combo_interrupted': 0, 'combo_damage': [],
        'combo_by_macro': {},
    }
    a, b = _mtimes(files)
    o['sample_window'] = [a, b]
    for p in files:
        try:
            d = pickle.load(open(p, 'rb'))
        except Exception:
            continue
        fr = d.get('frames') or []
        decs = d.get('decisions') or []
        if not fr or not decs:
            continue
        o['files'] += 1
        n = len(fr)
        o['frames'] += n
        my_hp = [int(f[0][IX['hp']]) for f in fr]
        op_hp = [int(f[1][IX['hp']]) for f in fr]
        my_a = [int(f[0][IX['action']]) for f in fr]
        op_a = [int(f[1][IX['action']]) for f in fr]
        my_x = [float(f[0][IX['position.x']]) for f in fr]
        op_x = [float(f[1][IX['position.x']]) for f in fr]
        my_y = [float(f[0][IX['position.y']]) for f in fr]
        my_dir = [float(f[0][IX['direction']]) for f in fr]
        # --- 擦弹: check_graze 逐帧复算(与训练同源) + TTI/lead-in ---
        _prev_tti = None
        for t in range(n):
            l = {k: fr[t][0][j] for j, k in enumerate(FL_FIELDS)}
            objs = fr[t][2] or []
            try:
                bl = fb.track_bullets(list(objs), own=l)
            except Exception:
                bl = []
            d_take = max(0, my_hp[t - 1] - my_hp[t]) if t > 0 else 0
            try:
                gz = fb.check_graze(l, bl, d_take)
            except Exception:
                gz = 0
            if gz:
                o['graze_frames'] += 1
                try:
                    tti, inc = threat_predict(l.get('position.x', 0.0),
                                              l.get('position.y', 0.0),
                                              bl, GAME_FPS)
                except Exception:
                    tti = None
                if tti is not None:
                    o['graze_tti'].append(float(tti))
                lead = None
                for back in range(1, 31):
                    tt = t - back
                    if tt < 0:
                        break
                    near = False
                    for ob in (fr[tt][2] or []):
                        try:
                            dx = float(ob[1]) - my_x[tt]
                            dy = float(ob[2]) - my_y[tt]
                            if (dx * dx + dy * dy) ** 0.5 < 120:
                                near = True
                                break
                        except Exception:
                            continue
                    if near:
                        lead = back
                        break
                if lead is not None:
                    o['graze_leadin'].append(lead)
            # 防御威胁B: TTI<0.3s 边沿
            _cur = None
            if bl:
                try:
                    _tti, _inc = threat_predict(l.get('position.x', 0.0),
                                                l.get('position.y', 0.0),
                                                bl, GAME_FPS)
                    _cur = _tti
                except Exception:
                    _cur = None
            _prev_tti = _cur
        # --- 决策(0基) + 攻击事件归因 ---
        D = []
        for (fn, mid) in decs:
            i = int(fn) - 1
            if not (0 <= i < n):
                continue
            mid = int(mid)
            nm = lib[mid][0] if 0 <= mid < len(lib) else '?'
            D.append((i, nm, classify(nm, CHAR_LIBS[char])))
        o['decisions'] += len(D)
        hits, myhits, guards = [], [], []
        for t in range(1, n):
            if op_hp[t] < op_hp[t - 1]:
                hits.append(t)
            if my_hp[t] < my_hp[t - 1]:
                myhits.append(t)
            if GUARD_LO <= op_a[t] <= GUARD_HI:
                guards.append(t)
        atkD = [(i, nm, cls) for (i, nm, cls) in D if cls in BROAD]

        def _attr(events):
            out = {}
            for t in events:
                cand = None
                for (i, nm, cls) in atkD:
                    if i < t and t - i <= ATTR_MAX:
                        cand = i
                    elif i >= t:
                        break
                if cand is not None:
                    out[cand] = out.get(cand, 0) + 1
            return out
        hit_attr, my_attr, guard_attr = (_attr(hits), _attr(myhits),
                                         _attr(guards))
        for (i, nm, cls) in atkD:
            o['attack_windows'] += 1
            if my_dir[i] * (op_x[i] - my_x[i]) > 0:
                o['attack_forward_n'] += 1
            o['attack_forward_den'] += 1
            dx = abs(op_x[i] - my_x[i])
            band = ('<120' if dx < 120 else '120-250' if dx < 250
                    else '250-400' if dx < 400 else '>=400')
            o['engage_bands'][band] = o['engage_bands'].get(band, 0) + 1
            o['engage_dx_sum'] += dx
            o['engage_n'] += 1
            fate = ('hit' if i in hit_attr else 'interrupted' if i in my_attr
                    else 'blocked' if i in guard_attr else 'whiff')
            if fate == 'hit':
                o['win_hit'] += 1
                _hf = next(t for t in hits if i < t <= i + ATTR_MAX)
                o['hit_damage_total'] += max(0, op_hp[_hf - 1] - op_hp[_hf])
            else:
                o['win_' + fate] += 1
            if is_combo_macro(nm, cls):
                o['combo_windows'] += 1
                mb = o['combo_by_macro'].setdefault(nm, {'n': 0, 'hit': 0})
                mb['n'] += 1
                if fate == 'hit':
                    o['combo_hit'] += 1
                    mb['hit'] += 1
                    _hf = next(t for t in hits if i < t <= i + ATTR_MAX)
                    o['combo_damage'].append(
                        max(0, op_hp[_hf - 1] - op_hp[_hf]))
                else:
                    o['combo_' + fate] += 1
        # 接近率
        for t in range(1, n):
            dp = abs(op_x[t - 1] - my_x[t - 1])
            dn = abs(op_x[t] - my_x[t])
            if abs(dn - dp) > 1e-6:
                o['motion_frames'] += 1
                if dn < dp:
                    o['approach_frames'] += 1
        # 防姿/受击前防
        for t in range(1, n):
            aa = my_a[t]
            if GUARD_LO <= aa <= GUARD_HI:
                o['guard_frames'] += 1
                if aa <= 153:
                    o['stand_guard_frames'] += 1
                elif aa <= 157:
                    o['crouch_guard_frames'] += 1
                else:
                    o['air_guard_frames'] += 1
            if my_hp[t] < my_hp[t - 1]:
                o['hp_drop_frames'] += 1
                if any(GUARD_LO <= my_a[x] <= GUARD_HI
                       for x in range(max(0, t - 10), t)):
                    o['hp_drop_guarded_prev10'] += 1
        # --- 防御威胁A/B: 边沿→响应 ---
        det = FrameEventDetector()
        prev_act_out = None
        prev_tti_threat = False
        for t in range(n):
            l = {k: fr[t][0][j] for j, k in enumerate(FL_FIELDS)}
            r = {k: fr[t][1][j] for j, k in enumerate(FL_FIELDS)}
            # A: 对手攻击启动(300-598)上升沿 (训练同源: frame_events E_OPP_STARTUP)
            try:
                ev, _w = det.detect(l, r, bool(l.get('hitStop', 0)))
            except Exception:
                ev = E_NONE
            if ev == E_OPP_STARTUP:
                o['threatA_events'] += 1
                for dt in range(0, RESP_W + 1):
                    tt = t + dt
                    if tt >= n:
                        break
                    if GUARD_LO <= my_a[tt] <= GUARD_HI:
                        o['threatA_guard'] += 1
                        o['threatA_delays'].append(dt)
                        break
            # B: 弹幕 TTI<18.6帧 上升沿
            objs = fr[t][2] or []
            try:
                bl2 = fb.track_bullets(list(objs), own=l)
                tti, inc = threat_predict(l.get('position.x', 0.0),
                                          l.get('position.y', 0.0),
                                          bl2, GAME_FPS)
                is_thr = (tti is not None and tti < BULLET_TTI and inc > 0)
            except Exception:
                is_thr = False
            if is_thr and not prev_tti_threat:
                o['threatB_events'] += 1
                got_g = got_e = False
                for dt in range(0, RESP_W + 1):
                    tt = t + dt
                    if tt >= n:
                        break
                    if GUARD_LO <= my_a[tt] <= GUARD_HI and not got_g:
                        got_g = True
                        o['threatB_guard'] += 1
                        o['threatB_delays'].append(dt)
                        break
                # 规避: 20帧内位移>80px
                for dt in range(0, RESP_W + 1):
                    tt = t + dt
                    if tt >= n:
                        break
                    if abs(my_x[tt] - my_x[t]) > 80:
                        got_e = True
                        o['threatB_evade80'] += 1
                        break
            prev_tti_threat = is_thr
    # ---- 派生 ----
    aw = o['attack_windows']
    for k in ('hit', 'blocked', 'whiff', 'interrupted'):
        o['%s_rate_pct' % k] = _pct(o['win_' + k], aw)
    o['damage_per_hit'] = _r(o['hit_damage_total'] / o['win_hit'], 1) \
        if o['win_hit'] else None
    o['engage_mean_dx'] = _r(o['engage_dx_sum'] / o['engage_n'], 1) \
        if o['engage_n'] else None
    o['attack_forward_pct'] = _pct(o['attack_forward_n'],
                                    o['attack_forward_den'])
    o['approach_rate_pct'] = _pct(o['approach_frames'], o['motion_frames'])
    o['decisions_per_1000f'] = _r(1000.0 * o['decisions'] / o['frames'], 2) \
        if o['frames'] else None
    o['attack_windows_per_1000f'] = _r(1000.0 * aw / o['frames'], 2) \
        if o['frames'] else None
    o['graze_per_1000f'] = _r(1000.0 * o['graze_frames'] / o['frames'], 2) \
        if o['frames'] else None
    o['threatA_guard_pct'] = _pct(o['threatA_guard'], o['threatA_events'])
    o['threatA_delay_p50'] = _pctile(o['threatA_delays'], 50)
    o['threatA_delay_p90'] = _pctile(o['threatA_delays'], 90)
    o['threatB_guard_pct'] = _pct(o['threatB_guard'], o['threatB_events'])
    o['threatB_evade80_pct'] = _pct(o['threatB_evade80'], o['threatB_events'])
    o['threatB_delay_p50'] = _pctile(o['threatB_delays'], 50)
    o['threatB_delay_p90'] = _pctile(o['threatB_delays'], 90)
    o['guard_frame_pct'] = _pct(o['guard_frames'], o['frames'])
    o['stand_guard_pct_of_guard'] = _pct(o['stand_guard_frames'],
                                         o['guard_frames'])
    o['crouch_guard_pct_of_guard'] = _pct(o['crouch_guard_frames'],
                                          o['guard_frames'])
    o['hp_drop_guarded_prev10_pct'] = _pct(o['hp_drop_guarded_prev10'],
                                           o['hp_drop_frames'])
    o['graze_tti_p50'] = _pctile(o['graze_tti'], 50)
    o['graze_tti_p90'] = _pctile(o['graze_tti'], 90)
    o['graze_leadin_p50'] = _pctile(o['graze_leadin'], 50)
    o['graze_leadin_p90'] = _pctile(o['graze_leadin'], 90)
    cw = o['combo_windows']
    for k in ('hit', 'blocked', 'whiff', 'interrupted'):
        o['combo_%s_pct' % k] = _pct(o['combo_' + k], cw)
    o['combo_damage_mean'] = _r(sum(o['combo_damage'])
                                / len(o['combo_damage']), 1) \
        if o['combo_damage'] else None
    o['combo_by_macro'] = dict(sorted(o['combo_by_macro'].items(),
                                      key=lambda kv: -kv[1]['n'])[:8])
    return o


def parse_argv():
    since = until = None
    for i, a in enumerate(sys.argv):
        if a == '--since' and i + 1 < len(sys.argv):
            since = time.mktime(time.strptime(sys.argv[i + 1],
                                              '%Y-%m-%d %H:%M'))
        if a == '--until' and i + 1 < len(sys.argv):
            until = time.mktime(time.strptime(sys.argv[i + 1],
                                              '%Y-%m-%d %H:%M'))
    return since, until


def main():
    since, until = parse_argv()
    # 2026-10-18 task-18 修标: 原 phase 硬编码 PRE-bcw; 传 --since 时是 ON 窗采样.
    _phase = PHASE if since is None else (
        'ON-window (since %s; 训练侧; bcw=代码默认0.05, 非0.00)'
        % time.strftime('%Y-%m-%d %H:%M', time.localtime(since)))
    res = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
           'version': VERSION, 'phase': _phase,
           'window_filter': [None if since is None else
                             time.strftime('%Y-%m-%d %H:%M',
                                           time.localtime(since)),
                             None if until is None else
                             time.strftime('%Y-%m-%d %H:%M',
                                           time.localtime(until))],
           'chars': {}}
    for char in ('reimu', 'marisa', 'suika'):
        res['chars'][char] = {
            'bh': bh_table(char, since, until),
            'frames': frame_tables(char, since, until),
            'actor': parse_actor_games(char, since, until),
        }
    res['method'] = {
        'version': VERSION,
        'phase': _phase,
        'label': '训练侧(fleet actor/learner 工件) — 不得与人测读数混用/互相归因',
        'sources': {
            'BH旁车': os.path.join(EPS, 'bh_<char>_*.json')
            + ' (最近%d份/角色)' % BH_LAST,
            '帧日志': os.path.join(FL, '<char>', 'fl_*.pkl')
            + ' (最近%d份/角色; 30min抽样)' % FL_LOGS,
            'actor日志': 'D:/temp/actor_<char>_*.log 的[奖励成分]行 (最近%d局)' % ACTOR_GAMES,
            '判定库': 'behavior_health + frame_events.FrameEventDetector + '
                    'feat_builder(track_bullets/check_graze/threat_predict, 训练同源) + '
                    'train_tm.CHAR_LIBS + my_punish_tracker.classify',
        },
        '口径': {
            '攻击率(决策级)': '宏ID决策口径; 严格=MELEE+SKILL, 宽=+BULLET; '
                        '宏放大说明: 决策间隔随宏步长变化, 与按键率不可直接换算',
            '输入级攻击率': '**训练侧不可得**: 帧日志仅13状态字段+objs+宏ID, '
                       'episode.npz 无 inputs 键; 人测侧有(见 rep 分析), 不可混用',
            '攻击窗结局': '事件归因: 对手hp降=命中 / 对手防御硬直150-158=被防 / '
                      '我方hp降=被打断 / 60帧内无事件=空挥; 归因=最近一次攻击决策且≤60帧',
            '前压/接敌': '状态直读 direction*(opp_x-my_x)>0; 距离=|opp_x-my_x|px',
            '防御威胁A': '对手出招启动(训练同源 E_OPP_STARTUP)事件数; 响应窗%d帧内'
                      '进入%s' % (RESP_W, GUARD_LABEL),
            '防御威胁B': '弹幕 threat_predict TTI<%.1f帧 且 incoming>0 的上升沿; '
                      '响应窗%d帧内进入%s或位移>80px(规避)' % (
                          BULLET_TTI, RESP_W, GUARD_LABEL),
            '擦弹': '精确事件: actor日志 graze_frames/局(训练循环同源计数); '
                   '帧日志 check_graze 逐帧复算(同源) → 率/千帧、TTI分布、'
                   '弹幕进120px→擦弹帧差',
            '连段': '①BH旁车 fates(大样本, 宏名判据, 覆盖窄) ②状态口径完整连段: '
                   'is_combo_macro 决策→60帧内结局(受击/空挥/被防/无结算)',
        },
        '样本与分母': '每格数字均带 n/分母; 样本窗见各来源 sample_window',
        '不可得': [
            '输入级攻击率(训练侧): 无输入流工件(帧日志13状态字段/无inputs; episode无inputs键)',
            '受击后30帧应对分布: 无受击事件标注 → hp降+前10帧防御硬直代理(已给率)',
            '伤害归属: 以hp差分代理(无逐击事件)',
        ],
    }
    io.open(OUT_JSON, 'w', encoding='utf8').write(
        json.dumps(res, ensure_ascii=False, indent=1))
    L = []
    ap = L.append
    ap('【训练侧】行为深度仪表 三表基线 %s  version=%s phase=%s' % (
        res['generated'], VERSION, res['phase']))
    ap('口径: 训练侧=fleet actor/learner 工件; 人测读数不可混用(审计#6b: 人测=旧模型+OOD)')
    for char in ('reimu', 'marisa', 'suika'):
        b = res['chars'][char]['bh']
        f = res['chars'][char]['frames']
        ac = res['chars'][char]['actor']
        ap('=' * 86)
        ap('[%s] 帧日志 %d份/%d帧(%.0fs) 窗%s..%s | BH %d份/%d决策 | actor %d局'
           % (char, f['files'], f['frames'], f['frames'] / 62.0,
              f['sample_window'][0], f['sample_window'][1],
              b['files'], b['decisions'], ac['n_games']))
        ap('表1 有效攻击性（训练侧）')
        ap('  决策级: 严格 %s%%(n=%d) | 宽(含弹幕) %s%% | 攻击窗/千帧 %s(n=%d窗口)'
           % (_f(b['attack_rate_strict_pct'], 2), b['decisions'],
              _f(b['attack_rate_broad_pct'], 2),
              _f(f['attack_windows_per_1000f']), f['attack_windows']))
        ap('  状态级结局: 命中 %s%% | 被防 %s%% | 空挥 %s%% | 被打断 %s%% (分母 n=%d) | '
           '伤害/命中 %s' % (_f(f['hit_rate_pct']), _f(f['blocked_rate_pct']),
                           _f(f['whiff_rate_pct']),
                           _f(f['interrupted_rate_pct']),
                           f['attack_windows'], _f(f['damage_per_hit'])))
        ap('  → 有效攻击转化率(=命中率) %s%%; 单列: 空挥 %s%% / 被防 %s%%'
           % (_f(f['hit_rate_pct']), _f(f['whiff_rate_pct']),
              _f(f['blocked_rate_pct'])))
        ap('  接敌 %spx 分带=%s | 攻击时前压 %s%% | 接近率 %s%% | 续打 命中后 %s%% vs '
           '未命中 %s%%' % (_f(f['engage_mean_dx'], 0),
                          json.dumps(f['engage_bands'], ensure_ascii=False),
                          _f(f['attack_forward_pct']),
                          _f(f['approach_rate_pct']),
                          _f(b['followup_hit_atk_pct']),
                          _f(b['followup_nohit_atk_pct'])))
        ap('  输入级攻击率: 不可得(训练侧无输入流工件)')
        ap('表2 防御与擦弹时机（训练侧）')
        ap('  [防御A] 威胁=对手出招启动上升沿 n=%d | %d帧内防御接触 %s%% | 延迟P50=%sF '
           'P90=%sF' % (f['threatA_events'], RESP_W,
                        _f(f['threatA_guard_pct']),
                        _f(f['threatA_delay_p50'], 0),
                        _f(f['threatA_delay_p90'], 0)))
        ap('  [防御B] 威胁=弹幕TTI<%.1f帧上升沿 n=%d | %d帧内防御接触 %s%% | 规避(位移>80px)'
           ' %s%% | 延迟P50=%sF P90=%sF' % (
               BULLET_TTI, f['threatB_events'], RESP_W,
               _f(f['threatB_guard_pct']), _f(f['threatB_evade80_pct']),
               _f(f['threatB_delay_p50'], 0), _f(f['threatB_delay_p90'], 0)))
        ap('  %s帧占比 %s%%(立%s%%/蹲%s%%) | 被命中前10帧有防 %s%% (hp降 n=%d)'
           % (GUARD_LABEL, _f(f['guard_frame_pct']),
              _f(f['stand_guard_pct_of_guard']),
              _f(f['crouch_guard_pct_of_guard']),
              _f(f['hp_drop_guarded_prev10_pct']), f['hp_drop_frames']))
        ap('  [擦弹-精确] actor日志 %d局: graze_frames均 %s帧/局 (合计%d; 局帧合计%d; '
           'actor率 %s/千帧) | 帧日志 check_graze 复算 %s帧(千帧率 %s) | '
           '擦弹帧TTI P50=%sF P90=%sF | 弹进120px→擦弹帧差 P50=%sF P90=%sF' % (
               ac['n_games'], _f(ac['graze_frames_mean_per_game']),
               ac['graze_frames_total'], ac.get('frames_total') or 0,
               _f(ac.get('graze_per_1000f')), f['graze_frames'],
               _f(f['graze_per_1000f']), _f(f['graze_tti_p50'], 1),
               _f(f['graze_tti_p90'], 1), _f(f['graze_leadin_p50'], 0),
               _f(f['graze_leadin_p90'], 0)))
        ap('表3 连段完成度（训练侧）')
        cr = b['combo_rates_pct']
        ap('  ①BH旁车 fates n=%d: hit %s%% | blocked %s%% | dropped %s%% | '
           'interrupted %s%%' % (b['combo_total_bh'], _f(cr['hit']),
                               _f(cr['blocked']), _f(cr['dropped']),
                               _f(cr['interrupted'])))
        ap('  ②状态口径完整连段 n=%d: 完成(命中) %s%% | 受击打断 %s%% | 被防 %s%% | '
           '空挥 %s%% | 连段伤害均值 %s' % (
               f['combo_windows'], _f(f['combo_hit_pct']),
               _f(f['combo_interrupted_pct']), _f(f['combo_blocked_pct']),
               _f(f['combo_whiff_pct']), _f(f['combo_damage_mean'])))
        ap('  BH判据说明: %s' % b['combo_note'])
        ap('')
    ap('== 不可得项(如实) ==')
    for x in res['method']['不可得']:
        ap(' - ' + x)
    io.open(OUT_TXT, 'w', encoding='utf8').write('\n'.join(L) + '\n')
    print('\n'.join(L))
    print('\n产物: %s\n      %s' % (OUT_JSON, OUT_TXT))


if __name__ == '__main__':
    main()
