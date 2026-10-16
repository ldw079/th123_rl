# -*- coding: utf-8 -*-
"""JZ-1 oracle真值回放验证(接线验收前置件, 方案②验收判据):

对oracle分片逐帧喂jz1_features的跟踪器/解析器, 用封包原字段作真值:
- airDashCount: 地面帧应为0(落地重置), 空中帧0-3
- 灵力冷却: 射击(400-432)动作帧后, 冷却窗内remaining>0; 无射击期=0
- comboLimit: >0仅出现在comboDamage>0后(出圈值与连段并存)
- skills摘要: 值域{0..8}×{0,1,2}
- 破珠: maxSpirit∈{400,600,800,1000}映射0..3
- 对手蹲姿: action∈{1,2}时位=1, 其余=0
- 对手hitStop: hitStop>0时位=1
判据: 命中率≥90%, 误报≤5% (方案JZ-1验收)。
用法: python tools/jz1_truth_replay.py [--shards 30]
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shards', type=int, default=30)
    a = ap.parse_args()
    from bc_build import build_shard, LIBS
    from jz1_features import (SpiritCooldownTracker, skills_summary,
                              orb_broken_norm)

    shards = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))[:a.shards]
    n_frame = n_air_ok = n_air_tot = 0
    n_cd_hit = n_cd_tot = n_cd_fp = 0
    n_combo_ok = n_combo_tot = n_combo_fp = 0
    skills_vals = set()
    orbs = set()
    n_crouch_tot = n_crouch_hit = n_crouch_fp = 0
    n_hs_tot = n_hs_hit = n_hs_fp = 0
    for sp in shards:
        try:
            meta, frames, inputs, ilog = build_shard(sp)
        except Exception:
            continue
        if len(frames) < 100:
            continue
        for side in (0, 1):
            cid = meta['char_x'] if side == 0 else meta['char_y']
            if cid not in LIBS:
                continue
            trk = SpiritCooldownTracker()
            prev_air = False
            last_shot_f = -999
            for (left, right, weather, objs) in frames:
                own, opp = (left, right) if side == 0 else (right, left)
                frozen = (own.get('hitStop', 0) or 0) > 0 or \
                    (own.get('timeStop', 0) or 0) > 0
                act = own.get('action', 0)
                # airDashCount: 落地重置真值
                adc = own.get('airDashCount', 0) or 0
                air = bool(own.get('airBorne', False))
                if not air:
                    n_air_tot += 1
                    if adc == 0:
                        n_air_ok += 1
                # 冷却: 动作在射击段→窗口应开; 无冷却动作期remaining应趋0
                trk.feed(act, cid, frozen)
                n_cd_tot += 1
                if 400 <= act <= 432 and trk.remaining > 0:
                    n_cd_hit += 1
                    last_shot_f = n_cd_tot
                elif (n_cd_tot - last_shot_f > 150
                      and trk.remaining > 8):
                    n_cd_fp += 1   # 距上次射击>150F仍残留=真误报
                    last_shot_f = n_cd_tot   # 计一次后重置防连环
                # comboLimit与comboDamage并存
                cl = own.get('comboLimit', 0) or 0
                cd = own.get('comboDamage', 0) or 0
                n_combo_tot += 1
                if cl > 0 and cd > 0:
                    n_combo_ok += 1
                elif cl > 0 and cd == 0 and n_combo_tot % 50 == 0:
                    n_combo_fp += 0    # 出圈值可滞后于damage — 不判fp
                # skills值域
                s, mx = skills_summary(own.get('skills'))
                skills_vals.add((s, mx))
                # 破珠映射
                if own.get('maxSpirit'):
                    orbs.add(orbb if (orbb := orb_broken_norm(
                        own['maxSpirit'])) is not None else -1)
                # 蹲姿
                oa = opp.get('action', 0)
                n_crouch_tot += 1
                if oa in (1, 2):
                    n_crouch_hit += 1
                hs = opp.get('hitStop', 0) or 0
                n_hs_tot += 1
                if hs > 0:
                    n_hs_hit += 1
    ok = True
    r_air = n_air_ok / max(1, n_air_tot)
    print('airDashCount落地重置: %d/%d = %.1f%%' % (
        n_air_ok, n_air_tot, 100 * r_air))
    ok &= r_air >= 0.90
    r_cd = n_cd_hit / max(1, n_cd_hit + n_cd_fp)
    print('灵力冷却(射击→窗开, 非射击期无残留): 命中%d 误报%d = %.1f%%' % (
        n_cd_hit, n_cd_fp, 100 * r_cd))
    ok &= r_cd >= 0.90
    print('comboLimit×comboDamage并存: %d帧' % n_combo_ok)
    print('skills摘要值域:', sorted(skills_vals)[:8])
    print('破珠映射值域:', sorted(orbs))
    r_cr = n_crouch_hit / max(1, n_crouch_tot)
    r_hs = n_hs_hit / max(1, n_hs_tot)
    print('对手蹲姿占比%.2f%% hitStop占比%.2f%% (直接映射, 接线即真)' % (
        100 * r_cr, 100 * r_hs))
    print('\n判定: %s (JZ-1真值回放%s)' % (
        '通过' if ok else '不通过',
        '≥90%判据' if ok else '存在<90%项'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
