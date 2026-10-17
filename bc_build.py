# -*- coding: utf-8 -*-
"""BC数据集构建器: v2神谕分片(全量包) → (视觉特征, 侧特征, 宏ID, 置信度)。

与train_tm的特征构建逐位一致:
- 视觉=3帧80×60差分栈(14400维uint8), 决策点产出
- 侧=5N+308: [宏one-hot N][上宏 N][core308+对手one-hot][gap_x N][gap_y N]
  [untech差 N] — 与train_tm._build_side同构(R24/R25/R30/R38)
- 宏标签=StreamMatcher对专家输入流的贪心匹配(置信度过滤+待机降采样)

R38(第九轮审计P0-5/P0-6):
- 状态流与输入流时间轴错位(+70~+240帧, 局内漂移) — 原按原始下标配对
  =每行特征取自标签前1~4秒的状态。现经bc_align逐帧滞后映射重排后才
  配对, 并做事后复检(|残余lag|>24的窗口不产行)。
- 旧版构建4N+308且磁盘文件系repad零填充(gap/gap_y/untech全零) —
  现5N+308原生构建, meta带layout版本; repad脚本对该版本拒跑。
"""
from __future__ import annotations

import glob
import json
import os
import struct
import sys

import numpy as np

# D2(公开化未决): soku_arch 是外部包(vendor 与否待用户裁定) — 至少改为可覆盖
sys.path.insert(0, os.environ.get('TH123_SOKU_ARCH', r'D:\temp\soku_arch'))
# P0-2(从零#5): 仓库根由本文件位置派生 — 原 用户家目录宏 字面量(package
# expandvars 也只在本机成立), 访客克隆到别处 import 必失败。
_REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _REPO)
from soku_arch.packet_schema import CS_SIZE, unpack_player
from bc_align import estimate_lag_map, realign, post_validate
from bc_match import StreamMatcher, LOW_INFO
from feat_builder import FeatureBuilder, eff_untech, HIT_ACT_IDS
from macros import MACROS, NORMALIZED_AFFECTED  # noqa: F401 (导入触发规范化)
from macros import MACROS as M_REIMU
from macros.marisa import MACROS_MARISA
from macros.suika import MACROS_SUIKA
from reach_maps import resolve_reach, resolve_startup

OBJ_FMT = '<b2f4H'
OBJ_SZ = struct.calcsize(OBJ_FMT)
LIBS = {0: ('reimu', M_REIMU), 1: ('marisa', MACROS_MARISA),
        9: ('suika', MACROS_SUIKA)}
IDLE_KEEP = 0.15      # 待机标签保留比例(其决策含量低)
CONF_MIN = 0.92       # BC行置信度门槛(比匹配器门槛更严)
ALIGN_PASS_MIN = 0.5  # 对齐复检窗通过率下限(低于=整片拒收)
# 从零#2(产品面P2): 布局串从CORE_DIMS派生 — 原硬编码'5N+308:v2',
# R61t扩维316后过期(repad守卫按旧宽判断=误动作)
from feat_builder import FeatureBuilder as _FB
LAYOUT = '5N+%d:v2' % _FB.CORE_DIMS  # 侧向量布局版本(repad守卫用)


def _hand_flat(p):
    """unpack_player的hand=5×(id,cost)元组 → train_tm同款10字节扁平。"""
    out = bytearray()
    for pair in p['hand']:
        out += bytes((int(pair[0]) & 0xFF, int(pair[1]) & 0xFF))
    return bytes(out)


def parse_frames(pkts, offsets):
    """pkts/offsets → [(left, right, weather, objs)] 逐帧。"""
    out = []
    for i, off in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else len(pkts)
        left = unpack_player(bytes(pkts[off:off + CS_SIZE]))
        right = unpack_player(bytes(pkts[off + CS_SIZE:off + 2 * CS_SIZE]))
        left['hand'] = _hand_flat(left)
        right['hand'] = _hand_flat(right)
        left['skills'] = bytes(int(v) & 0xFF for v in left['skills']) \
            if not isinstance(left['skills'], (bytes, bytearray)) else left['skills']
        right['skills'] = bytes(int(v) & 0xFF for v in right['skills']) \
            if not isinstance(right['skills'], (bytes, bytearray)) else right['skills']
        wd, wa, wt = struct.unpack_from('<bbH', pkts, off + 2 * CS_SIZE)
        p = off + 2 * CS_SIZE + 4
        n = pkts[p]
        p += 1
        objs = []
        for _ in range(n):
            objs.append(struct.unpack_from(OBJ_FMT, pkts, p))
            p += OBJ_SZ
        out.append((left, right, {'displayed': wd, 'active': wa,
                                  'timer': wt}, objs))
    return out


def render_frame(left, right, objs):
    img = np.zeros((60, 80), dtype=np.uint8)
    cx = int(np.clip(left["position.x"] / 16.0, 0, 79))
    cy = int(np.clip((600.0 - left["position.y"]) / 16.0, 0, 59))
    img[cy, cx] = 255
    ox = int(np.clip(right["position.x"] / 16.0, 0, 79))
    oy = int(np.clip((600.0 - right["position.y"]) / 16.0, 0, 59))
    img[oy, ox] = 180
    for o in objs[:48]:
        bx = int(np.clip(o[1] / 16.0, 0, 79))
        by = int(np.clip((600.0 - o[2]) / 16.0, 0, 59))
        v = 96 + (o[6] & 0x3F)
        if img[by, bx] < 90:
            img[by, bx] = v
    return img


def _hand_ids(hand_bytes):
    """hand 10字节 → (ids, sel)。与train_tm._parse_hand同构。"""
    ids = [hand_bytes[i * 2] for i in range(5)
           if hand_bytes[i * 2] != 0xFF]
    sel = hand_bytes[0] if hand_bytes[0] != 0xFF else None
    return ids, sel


def resolve_sc_label(sc_tgts, idx_by_name, hand_bytes):
    """R61g(B1): SC通用标签→具体卡宏。专家按下卡键时用的是**选中卡**
    (hand[0]); 匹配器给出的SC标签是"某卡被使用"(所有SC共享按键形态)
    — 此处按手牌选中位解析到sc_target==该卡ID的宏。
    返回具体宏idx; 无匹配返回None(该行丢弃 — 空表优于错表)。
    sc_tgts: {宏名: 目标卡ID}(_parse_sc_targets产物);
    idx_by_name: {宏名: idx}。"""
    _ids, sel = _hand_ids(hand_bytes)
    if sel is None:
        return None
    for name, t in sc_tgts.items():
        if t == sel and name in idx_by_name:
            return idx_by_name[name]
    # 泛卡宏(tgt=-1, 用当前选中)兜底
    for name, t in sc_tgts.items():
        if t == -1 and name in idx_by_name:
            return idx_by_name[name]
    return None


def build_shard(path):
    d = np.load(path, allow_pickle=True)
    meta = json.loads(str(d['meta']))
    frames = parse_frames(d['pkts'], d['offsets'])
    inputs = d['inputs']
    # R40(第十一轮§6-1): mod输入日志 — 与状态帧同帧1:1的精确输入
    # (li,lo,ri,ro; 用inKeys=第0/2列)。返回None=旧分片(走互相关)。
    ilog = None
    if 'ilog' in d.files:
        arr = d['ilog']
        # 尾部可差数行(终局日志先于收帧结束) — 起始对齐, ilog≥帧数时截断
        if (arr.ndim == 2 and arr.shape[1] == 4
                and len(arr) >= len(frames) > 0):
            arr = arr[:len(frames)]
            ilog = (arr[:, 0].astype(np.uint16), arr[:, 2].astype(np.uint16))
    return meta, frames, inputs, ilog


def mirror_frames(frames):
    """右侧玩家视角→左视角镜像(帧侧): x→1280-x, 朝向取反。"""
    mf = []
    for left, right, weather, objs in frames:
        rl = dict(right)
        rr = dict(left)
        rl['position.x'] = 1280.0 - right['position.x']
        rr['position.x'] = 1280.0 - left['position.x']
        rl['direction'] = -right['direction']
        rr['direction'] = -left['direction']
        mobjs = [(o[0], 1280.0 - o[1], o[2]) + tuple(o[3:]) for o in objs]
        mf.append((rl, rr, weather, mobjs))
    return mf


def mirror_input(u16):
    """输入镜像: bit2/3(左右)互换, 向量化。"""
    return ((u16 & 0xFFF3) | (((u16 & 0x08) >> 1) | ((u16 & 0x04) << 1))
            ).astype(np.uint16)


# 裁定一1e: 后退/立防按对手攻击态区分(action_tables的ATTACK/SHOT集)
from action_tables import (reimu_ATTACK_IDS, reimu_SHOT_IDS,   # noqa: E402
                           marisa_ATTACK_IDS, marisa_SHOT_IDS,
                           suika_ATTACK_IDS, suika_SHOT_IDS)
_OPP_ATK = {
    0: reimu_ATTACK_IDS | reimu_SHOT_IDS,
    1: marisa_ATTACK_IDS | marisa_SHOT_IDS,
    9: suika_ATTACK_IDS | suika_SHOT_IDS,
}
_ALL_ATK = frozenset().union(*_OPP_ATK.values())
GUARD_WINDOW = 10      # 对手攻击判定窗(含startup, 帧)


def refine_guard_labels(hits, fr, opp_cid, lib):
    """后退↔立防重归属: 对手[hit帧, hit帧+GUARD_WINDOW)内进入
    攻击/射击action → 立防; 否则后退。非此二宏的hits原样透传。"""
    idx_back = idx_guard = None
    for i, m in enumerate(lib):
        if m[0] == '后退':
            idx_back = i
        elif m[0] == '立防':
            idx_guard = i
    if idx_back is None or idx_guard is None:
        return hits
    atk = _OPP_ATK.get(opp_cid, _ALL_ATK)
    out = []
    for h in hits:
        f = h[0]
        if h[1] in (idx_back, idx_guard):
            opp_attacking = any(
                fr[j][1].get('action', 0) in atk
                for j in range(f, min(f + GUARD_WINDOW, len(fr))))
            h = (f, idx_guard if opp_attacking else idx_back, h[2])
        out.append(h)
    return out


def build_rows(char_id, shards, log=print):
    """一个角色的全部BC行。"""
    name, lib = LIBS[char_id]
    # BH-4.1: 攻击/连段类宏名集(连段语境按钮帧评分的受益词汇) —
    # lib的attack集=近战/弹幕/必杀/连段/压制/空中体术全攻击族
    from train_tm import CHAR_LIBS as _CL
    _atk_names = _CL[name]['attack'] if name in _CL else None
    # BH-4.2: 对位语料的对手ID(2-19)超出本文件LIBS键(仅三主力) —
    # ID→名走全量CHAR_LIBS反向表(首次重建实弹抓出KeyError:12);
    # 池序=TMTrainer._CHAR_POOL_IDX单源(0/1/2+11-19段11, 20+扩展区)
    _ID2NAME = {l['id']: n for n, l in _CL.items()}
    from train_tm import TMTrainer
    _POOL_IDX = TMTrainer._CHAR_POOL_IDX
    matcher = StreamMatcher(lib, threshold=0.88,
                            attack_names=_atk_names)
    n_macros = len(lib)
    # R61g(B1): SC具体卡解析表(宏名→目标卡ID / 宏名→idx)
    from train_tm import _parse_sc_targets
    _sc_tgts = _parse_sc_targets(lib)
    _sc_idx_by_name = {m[0]: i for i, m in enumerate(lib)}
    fb = FeatureBuilder(n_macros)
    # R39(第十轮审计P1-2): 技能等级230-233/手牌技能可用性234-237由
    # _char_name驱动 — 原漏设 → BC行8维恒零, 与在线分布失配
    fb._char_name = name
    # R39(第十轮审计P1-1): 对手one-hot用**池序**(train_tm._wire_opp_ids
    # 同款 reimu=0/marisa=1/suika=2 — 修订2.7契约"只允许[o..o+2]")。
    # 原写原始角色ID(suika=9→core[236]落进技能可用性块, 违反自家契约)
    _POOL_O = {0: 0, 1: 1, 9: 2}
    reach_arr, reach_v_arr = resolve_reach(lib, name)
    reach_mask = reach_arr > 0
    reach_v_mask = reach_v_arr > 0
    startup_arr = resolve_startup(lib, name)
    startup_mask = startup_arr > 0
    X, S, Y, C, I = [], [], [], [], []
    sid = 0          # S-6: shard序id(每shard×侧一个; 同id行连续)
    n_sh = 0
    n_drop_win = 0
    n_exact = 0
    for sp in shards:
        meta, frames, inputs, ilog = build_shard(sp)
        if inputs.ndim != 2 or len(inputs) < 100 or len(frames) < 100:
            continue      # 空帧/错误分片防护(慢速续跑期曾产出0帧行)
        if meta.get('err'):
            continue      # R38: 录制期报错的分片不入库
        if meta['char_x'] != char_id and meta['char_y'] != char_id:
            continue
        if ilog is not None:
            # ---- R40精确对齐: mod同帧输入日志(状态帧↔生效输入1:1,
            # 含开局/回合切换的rep缺失帧) — 全帧有效, 跳过互相关 ----
            u16L = ilog[0]
            u16R = ilog[1]
            valid = np.ones(len(frames), dtype=bool)
            n_ok = n_tot = 1
            log('  [精确对齐] %s' % os.path.basename(sp))
            n_exact += 1
        else:
            # ---- R38对齐: 状态↔输入逐帧滞后映射(左流估计, 双流共用) ----
            u16L_raw = np.asarray(inputs[:, 1], dtype=np.uint16)
            u16R_raw = np.asarray(inputs[:, 0], dtype=np.uint16)
            lag, valid0 = estimate_lag_map(frames, u16L_raw)
            u16L = realign(u16L_raw, lag, valid0)
            valid, n_ok, n_tot = post_validate(frames, u16L, valid0)
            if n_tot and n_ok / n_tot < ALIGN_PASS_MIN:
                log('  [对齐拒收] %s 通过%d/%d' % (os.path.basename(sp),
                                                  n_ok, n_tot))
                continue
            n_drop_win += n_tot - n_ok
            u16R = realign(u16R_raw, lag, valid0)
        for side in (0, 1):
            if side == 0:
                if meta['char_x'] != char_id:
                    continue
                # rep输入流=[右,左]交错 → 左方=inputs[:,1]
                fr, u16, opp_cid = frames, u16L, meta['char_y']
            else:
                if meta['char_y'] != char_id:
                    continue
                fr = mirror_frames(frames)
                u16 = mirror_input(u16R)
                opp_cid = meta['char_x']
            sid += 1        # S-6: 本shard×侧行的连续组id
            # 匹配(真实朝向)
            facings = [1 if f[0]['direction'] > 0 else -1 for f in fr]
            # BH-4.1: 连段语境数组(对手真受击∧近距) — 帧元组[1]恒为
            # 对手侧(side0=右原始, side1=镜像后右=原左翻转, 均为index 1)
            _combo_ctx = [
                (f[1].get('action', 0) in HIT_ACT_IDS
                 and abs(f[1]['position.x'] - f[0]['position.x']) < 250)
                for f in fr]
            hits = matcher.walk(u16, facings, combo_ctx=_combo_ctx)
            hits = [h for h in hits if h[2] >= CONF_MIN and h[0] >= 2
                    and h[0] < len(fr)]
            # R61g(B1): SC通用标签→具体卡宏(按当帧手牌选中位解析;
            # 解析失败的SC行直接丢 — SC标签占比>0靠具体卡命中)
            _fixed = []
            for h in hits:
                _mname = lib[h[1]][0]
                if _mname in _sc_tgts:
                    _ri = resolve_sc_label(
                        _sc_tgts, _sc_idx_by_name, fr[h[0]][0]['hand'])
                    if _ri is None:
                        continue          # 无法定位具体卡 — 丢弃
                    h = (h[0], _ri, h[2])
                _fixed.append(h)
            hits = _fixed
            # 裁定一1e(2026-10-14用户裁定): 后退/立防状态上下文 —
            # 两者输入全同(按住后), 仅对手攻击态可分; 对手攻击/射击
            # 窗口内的back-hold=立防, 否则=后退(取代纯时长机械区分)
            hits = refine_guard_labels(hits, fr, opp_cid, lib)
            if not hits:
                continue
            fb.reset_match()
            # S-2离线注入(2026-10-14): 维330-342的BC行来源 —
            # ①K5池外位; ②S-5 sidecar的punish率(同款匹配器命中帧1:1
            # join, 无sidecar=0); ③决策序列由下方逐hit喂note_decision;
            # ④风格段由fb.opp(fb.update_opp驱动)+语料PCA原生产出;
            # ⑤S-3预测位离线=0(专家无自身模型 — 在线/离线分布差在案)
            from my_punish_tracker import classify as _clsfy
            from train_tm import CHAR_LIBS as _CHAR_LIBS_D
            fb.opp_outside_pool = 0.0 if opp_cid in (0, 1, 9) else 1.0
            # BH-3.2: 守备段位逐角色表按对手名查(与train_tm在线同构;
            # 库内低段位值随下次重建(BH-4.4)吸收)
            fb._opp_char = _ID2NAME.get(opp_cid) or LIBS[opp_cid][0]
            # P2修(审计2026-10-16): JZ-1冷却char_id双侧注入
            fb._jz1_ids = (char_id, opp_cid)
            _side = 0 if side == 0 else 1
            _sc_rate = {}
            _root = os.path.dirname(os.path.abspath(__file__))
            _scp = os.path.join(_root, 'data', 'oracle_v2', 'punish',
                                os.path.basename(sp))
            if os.path.exists(_scp):
                try:
                    _sd = np.load(_scp)
                    for _f, _r in zip(_sd['%d_f' % _side],
                                      _sd['%d_rate' % _side]):
                        _sc_rate[int(_f)] = _r
                except Exception:
                    pass
            _CLS_ORDER = ('JUMP', 'MELEE', 'BULLET', 'SKILL',
                          'GUARD_PREP', 'OTHER')
            hist = []
            last_m, last_m2 = 0, 0
            last_dir, dir_frames = 1, 0
            opp_x_prev, opp_vx = None, 0.0
            hit_at = {h[0]: (h[1], h[2]) for h in hits}   # 帧→(宏idx, 置信度)
            bullets = []
            for i, (left, right, weather, objs) in enumerate(fr):
                if not valid[i]:
                    hist = []       # 对齐复检失败窗口: 视觉栈也不跨污染
                    continue
                bullets = fb.track_bullets(objs)
                d_now = 1 if left['direction'] > 0 else -1
                dir_frames = 0 if d_now != last_dir else dir_frames + 1
                last_dir = d_now
                if opp_x_prev is not None:
                    opp_vx = 0.9 * opp_vx + 0.1 * (right['position.x']
                                                    - opp_x_prev)
                opp_x_prev = right['position.x']
                hist.append(render_frame(left, right, objs).ravel())
                if len(hist) > 3:
                    hist.pop(0)
                if i in hit_at:
                    if len(hist) == 3:
                        fb.update_opp(10 / 62, left, right, weather,
                                      opp_vx=opp_vx)
                        # S-2离线注入: sidecar先验punish率(1e同源)
                        # P1-7②(从零#4): **先build后note** — 对齐在线
                        # 时序(train_tm :1623 build → :1805 note)。原版
                        # 先note后build=维336(streak含当前)/338(换类)在
                        # 离线含当前标签而在线不含 → 标签经维度泄漏给BC锚
                        _r = _sc_rate.get(i)
                        if _r is not None:
                            for _ci, _cn in enumerate(_CLS_ORDER):
                                fb.punish.rate[_cn] = float(_r[_ci])
                        core = fb.build(left, right, weather, bullets)
                        core[33] = min(dir_frames, 62) / 62.0
                        # 对手角色one-hot(train_tm._wire_opp_ids同款池序)
                        # BH-4.2: 对位语料对手(2-19) — 池序走全量
                        # _CHAR_POOL_IDX按名查, 前12走段11槽(11-19),
                        # 后8走扩展区(core[308+i]) — 原_POOL_O只认三
                        # 主力(首次重建实弹抓出第二处KeyError:12)
                        _onm = _ID2NAME.get(opp_cid)
                        _oid = (_POOL_IDX.get(_onm)
                                if _onm else None)
                        if _oid is None:
                            _oid = _POOL_O[opp_cid]
                        if _oid <= 19:
                            core[227 + _oid] = 1.0
                        else:
                            core[308 + (_oid - 20)] = 1.0
                        _nm = lib[hit_at[i][0]][0]
                        fb.note_decision(_CLS_ORDER.index(
                            _clsfy(_nm, _CHAR_LIBS_D[name])))
                        if _r is not None:
                            _c_id = _CLS_ORDER.index(
                                _clsfy(_nm, _CHAR_LIBS_D[name]))
                            fb.punish.n_done[_CLS_ORDER[_c_id]] = (
                                fb.punish.n_done.get(_CLS_ORDER[_c_id], 0) + 1)
                        # R38: 布局[宏N][上宏N][core][gap_x N][gap_y N]
                        # [untech N] — 与train_tm._build_side逐位同构
                        s = np.zeros(5 * n_macros + fb.CORE_DIMS,
                                     dtype=np.float32)
                        s[last_m] = 1.0
                        s[n_macros + last_m2] = 1.0
                        s[2 * n_macros:2 * n_macros + fb.CORE_DIMS] = core
                        _adx = abs(right['position.x'] - left['position.x'])
                        _ady = abs(right['position.y'] - left['position.y'])
                        _b0 = 2 * n_macros + fb.CORE_DIMS
                        s[_b0:_b0 + n_macros] = np.clip(
                            (_adx - reach_arr) / 200.0, -1, 1) * reach_mask
                        s[_b0 + n_macros:_b0 + 2 * n_macros] = np.clip(
                            (_ady - reach_v_arr) / 200.0, -1, 1) \
                            * reach_v_mask
                        # BH-4.2: untech过动作门(与train_tm同构; 库内
                        # untech块值随下次重建(BH-4.4)吸收此变化)
                        _opp_ut = eff_untech(right)
                        s[_b0 + 2 * n_macros:] = np.clip(
                            (_opp_ut - startup_arr) / 50.0, -1, 1) \
                            * startup_mask
                        f0, f1, f2 = hist[0].astype(np.int16), \
                            hist[1].astype(np.int16), hist[2].astype(np.int16)
                        d1 = np.clip(f2 - f1, 0, 255).astype(np.uint8)
                        d2 = np.clip(f1 - f0, 0, 255).astype(np.uint8)
                        X.append(np.concatenate([hist[2], d1.ravel(),
                                                 d2.ravel()]))
                        S.append(s)
                        Y.append(hit_at[i][0])
                        C.append(hit_at[i][1])
                        I.append(sid)   # S-6: shard序id(同shard同侧连续)
                        last_m2, last_m = last_m, hit_at[i][0]
        n_sh += 1
    if not X:
        return name, None, {'shards_used': n_sh, 'windows_dropped': n_drop_win,
                            'shards_exact': n_exact}
    X = np.stack(X)
    S = np.stack(S)
    Y = np.array(Y, dtype=np.int64)
    C = np.array(C, dtype=np.float32)
    I = np.array(I, dtype=np.int64)   # S-6: 每行shard组id
    # 低决策含量宏降采样(第九轮§3: 待机/前进/后退/立防/蹲防一起)
    # S-6: sel排序保序 — 同shard行保持相邻(连续窗口采样的前提;
    #   比例不变, 仅恢复原始决策顺序)
    low_mask = np.array([lib[int(y)][0] in LOW_INFO for y in Y])
    keep = ~low_mask
    n_low = int(low_mask.sum() * IDLE_KEEP)
    if n_low:
        low_pos = np.where(low_mask)[0][:n_low]
        sel = np.sort(np.concatenate([np.where(keep)[0], low_pos]))
        X, S, Y, C, I = X[sel], S[sel], Y[sel], C[sel], I[sel]
    return name, (X, S, Y, C, I), {'shards_used': n_sh,
                                   'windows_dropped': n_drop_win,
                                   'shards_exact': n_exact}


def _shard_meta_probe(sp):
    """加速(2026-10-14, 用户令·CPU余量): npz成员惰性解压 — 只读meta
    即可判角色/err, 免掉无关分片的全量解压(pkts/inputs才是解压大头)。
    判据与build_rows主循环内的continue完全一致 → 行集不变, 纯IO节省。
    读坏的分片返回err=True(主循环同样会跳过)。"""
    try:
        with np.load(sp, allow_pickle=True) as d:
            m = json.loads(str(d['meta']))
            return m.get('char_x'), m.get('char_y'), bool(m.get('err'))
    except Exception:
        return None, None, True


def main(suffix=''):
    """suffix: 输出文件名后缀(--suffix _v3 → bc_reimu_v3.npz) —
    A/B窗口期不动在用库, 新版并行落盘, 验收后换装.
    --char CID: 只建该角色(0/1/9) — 三进程并行加速用(输出文件按
    角色天生不相交, 无写冲突)。"""
    import sys as _s
    only = None
    if '--char' in _s.argv:
        only = int(_s.argv[_s.argv.index('--char') + 1])
    # P0-2(从零#5): 分片根取**仓库相对**(库内实测 1724 片; 原 用户家目录宏
    # 字面量 glob 实测=0 → 下次重建会静默产空库, 而 BC 是全部模仿梯度来源)。
    _shard_root = (os.environ.get('TH123_ORACLE_SHARDS')
                   or os.path.join(_REPO, 'data', 'oracle_v2', 'shards'))
    shards_all = sorted(glob.glob(os.path.join(_shard_root, '*.npz')))
    print('v2分片:', len(shards_all))
    # 预过滤索引(每分片一次meta读, ~ms级)
    _probe = {sp: _shard_meta_probe(sp) for sp in shards_all}
    # 输出目录可配(默认C盘data/bc — 2026-10-14 C盘满事故后v3重建
    # 改道D盘; 换装时拷回或TH123_BC_DIR指认)
    out_dir = os.environ.get(
        'TH123_BC_OUT', r'D:\temp\th123_bc_v3' if suffix
        else os.path.join(_REPO, 'data', 'bc'))
    os.makedirs(out_dir, exist_ok=True)
    for cid in (0, 1, 9):
        if only is not None and cid != only:
            continue
        shards = [sp for sp in shards_all
                  if not _probe[sp][2] and cid in _probe[sp][:2]]
        print('[加速] %s: 相关分片%d/%d (meta预过滤)' % (
            LIBS[cid][0], len(shards), len(shards_all)))
        name, rows, st = build_rows(cid, shards)
        if rows is None:
            print('%s: 无数据 (%s)' % (name, st))
            continue
        X, S, Y, C, I = rows
        # 行数上限(2026-10-14): mmap方案裁定后默认0=全量(trio驻磁盘);
        # BC_MAX_ROWS仅作内存受限机器的回退(分层比例采样, 分布不变)
        # 修复(2026-10-14晚): 原漏'max_rows and'守卫 — 默认0时
        # 'len(Y)>0'恒真 → 每标签k=max(1,·)=1 → 60行假库事故
        # S-6: 封顶选择排序保序(同shard行相邻, 连续窗口采样前提)
        max_rows = int(os.environ.get('BC_MAX_ROWS', '0'))
        if max_rows and len(Y) > max_rows:
            rng = np.random.default_rng(1234 + cid)
            keep_n = max_rows
            sel = np.zeros(len(Y), dtype=bool)
            for lab in np.unique(Y):
                li = np.where(Y == lab)[0]
                k = max(1, int(round(len(li) * keep_n / len(Y))))
                sel[rng.choice(li, size=min(k, len(li)), replace=False)] = True
            sel = np.sort(np.where(sel)[0])
            X, S, Y, C, I = X[sel], S[sel], Y[sel], C[sel], I[sel]
            print('  行数封顶: %d→%d(分层比例采样, 保序)' % (
                len(Y), len(sel)))
        dist = np.bincount(Y, minlength=len(LIBS[cid][1]))
        p = os.path.join(out_dir, 'bc_%s%s.npz' % (name, suffix))
        # P2(审计#3, 宪法§5.2): 原直写savez非原子 — 中断=半档损坏
        _tmp = p + '.tmp.npz'
        np.savez(_tmp, X=X.astype(np.uint8), S=S, Y=Y, C=C, I=I,
                 meta=np.array(json.dumps({
                     'char': name, 'n_macros': len(LIBS[cid][1]),
                     'layout': LAYOUT, 'aligned': True,
                     'seq_aware': True, **st})))
        os.replace(_tmp, p)
        print('%s: %d行 X%s S%s → %s (分片%d, 弃窗%d)' % (
            name, len(Y), X.shape, S.shape, p, st['shards_used'],
            st['windows_dropped']))
        top = sorted(enumerate(dist), key=lambda t: -t[1])[:8]
        print('  宏分布Top8:', [(LIBS[cid][1][i][0], int(c)) for i, c in top])


if __name__ == '__main__':
    import sys as _sys
    _sfx = ''
    if '--suffix' in _sys.argv:
        _sfx = _sys.argv[_sys.argv.index('--suffix') + 1]
    main(_sfx)
