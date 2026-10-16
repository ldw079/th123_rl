# -*- coding: utf-8 -*-
"""特征活性巡检仪表(从零#4建议#5, 防复发级):

P0-1教训: note_decision吞并局级重置块 → 技能等级/B段/动量等在
训练+评估+BC三侧恒死数小时, 无任何测试/仪表拦截("恒死特征段"
合成测试拦不住 — 合成序列不走真决策循环)。

本仪表: 抽K个oracle分片, **与bc_build同路径**(matcher命中→
note_decision→build)重放, 按段统计core维活性 → 恒死段报警。
期望表注明"设计性恒死"豁免(在线only/池依赖)。

用法: python tools/feature_liveness.py [--shards 12] [--char 0]
退出码: 有意外恒死段=1(可入audit_all/CI)。
"""
import argparse
import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

# 段期望表(与feat_builder build()推进序一致; 巡检报告用)
SEGMENTS = [
    (0, 16, '1核心标量', True), (16, 16, '2动作类', True),
    (32, 2, '3朝向', True), (34, 14, '4位置带', True),
    (48, 4, '5速度资源', True), (52, 6, '6弹幕威胁', False),
    (58, 36, '7威胁网格', False), (94, 36, '8未来占据', False),
    (130, 22, '9卡牌感知', False), (152, 75, '10对手建模', True),
    (227, 26, '11对局适应', False), (253, 4, '12势函数', False),
    (257, 10, '13擦弹防守', False), (267, 8, '14a弹速统计', False),
    (275, 8, '14b动作历史', False), (283, 6, '14c密度梯度', False),
    (289, 3, '14e我方空间', False), (292, 3, '14f动量', True),
    (295, 3, '14g资源差', True), (298, 4, '14h威胁补充', False),
    (302, 2, '14i状态计时', False), (304, 4, '14j pose块', False),
    # 段名勘误(2026-10-14晚, suika新库核验后): [308..315]=R61t F5
    # 扩展角色one-hot(对手id≥8才非零 — 语料全池内对手=合法零, 晴岚式
    # 设计性恒0); 真B段已出卡=[316..329](技能12+SC+系统, 89.7%活✓)
    (308, 8, 'R61t F5扩展角色one-hot', None),
    (316, 14, 'B段对手已出卡(技能12+SC+系统2)', True),
    (330, 4, 'S-2 punish率', False),
    (334, 2, 'S-3预测(在线only)', None),      # 设计性: 离线恒0
    (336, 4, 'S-5决策序列', True),
    (340, 2, 'S-7风格pc', False),
    (342, 1, 'K5池外位(语料全池内)', None),   # 设计性: 语料恒0
    # JZ-1 A档字段段(2026-10-15): 真值回放99.8%/99.3%通过
    (343, 2, 'JZ-1 airDash双侧', True),
    (345, 2, 'JZ-1 灵力冷却双侧', True),
    (347, 2, 'JZ-1 comboLimit双侧', False),     # 连段中才有值
    (349, 4, 'JZ-1 技能摘要双侧', False),        # 用卡时才有值
    (353, 2, 'JZ-1 破珠双侧', None),            # 破珠稀有=合法零
    (355, 1, 'JZ-1 对手蹲姿', False),            # 蹲姿占1.6%
    (356, 1, 'JZ-1 对手hitStop', True),          # hitStop占8.5%
    (357, 1, 'JZ-1 healingCharm', None),         # 0.019%稀有
]
# expected_must_alive=True: 该段至少1维在真语料非恒死, 否则报警
# (P0-1类重置块吞并正好打这类: 动量/动作历史/决策序列)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shards', type=int, default=12)
    ap.add_argument('--char', type=int, default=0)
    ap.add_argument('--min-samples', type=int, default=200)
    a = ap.parse_args()

    from bc_build import LIBS, build_shard, mirror_frames, mirror_input
    from bc_match import StreamMatcher
    from feat_builder import FeatureBuilder
    from my_punish_tracker import classify as clsfy
    from train_tm import CHAR_LIBS

    name, lib = LIBS[a.char]
    matcher = StreamMatcher(lib, threshold=0.88)
    fb = FeatureBuilder(len(lib))
    fb._char_name = name
    shards = sorted(glob.glob(os.path.join(
        ROOT, 'data', 'oracle_v2', 'shards', 'tr*.npz')))[:a.shards]
    cores = []
    for sp in shards:
        try:
            meta, frames, inputs, ilog = build_shard(sp)
        except Exception:
            continue
        if ilog is None or len(frames) < 100 or meta.get('err'):
            continue
        if meta['char_x'] != a.char and meta['char_y'] != a.char:
            continue
        for side in (0, 1):
            if side == 0 and meta['char_x'] != a.char:
                continue
            if side == 1 and meta['char_y'] != a.char:
                continue
            fr = frames if side == 0 else mirror_frames(frames)
            u16 = ilog[0] if side == 0 else mirror_input(ilog[1])
            facings = [1 if f[0]['direction'] > 0 else -1 for f in fr]
            hits = matcher.walk(u16, facings)
            if not hits:
                continue
            hit_at = {h[0]: h[1] for h in hits}
            fb.reset_match()
            hist = []
            prev_my = prev_opp = None
            _CLS_ORDER = ('JUMP', 'MELEE', 'BULLET', 'SKILL',
                          'GUARD_PREP', 'OTHER')
            for i, (left, right, weather, objs) in enumerate(fr):
                bullets = fb.track_bullets(objs)
                # S-1惩罚tracker在线喂数(HP差分, expert_punish_track同型)
                hp_my = left.get('hp', 10000)
                hp_opp = right.get('hp', 10000)
                if prev_my is not None:
                    fb.punish.frame(
                        max(0, prev_my - hp_my),
                        300 <= right.get('action', 0) < 600,
                        max(0, prev_opp - hp_opp),
                        150 <= right.get('action', 0) <= 166)
                prev_my, prev_opp = hp_my, hp_opp
                hist.append(1)
                if len(hist) > 3:
                    hist.pop(0)
                if i in hit_at and len(hist) == 3:
                    fb.update_opp(10 / 62, left, right, weather, opp_vx=0.0)
                    nm = lib[hit_at[i]][0]
                    _cls = clsfy(nm, CHAR_LIBS[name])
                    fb.punish.begin(_cls)
                    # 与bc_build同时序: 先build后note(P1-7②)
                    core = fb.build(left, right, weather, bullets)
                    fb.note_decision(_CLS_ORDER.index(_cls))
                    cores.append(np.asarray(core, dtype=np.float32))
        if len(cores) >= a.min_samples * 2:
            break
    if len(cores) < a.min_samples:
        print('样本不足(%d<%d) — 提高shards或检查语料' % (len(cores), a.min_samples))
        return 1
    V = np.stack(cores)
    print('特征活性巡检: %s %d样本×%d维 (分片%d)'
          % (name, len(V), V.shape[1], len(shards)))
    alerts = []
    for off, width, seg, expect in SEGMENTS:
        seg_v = V[:, off:off + width]
        nz = float((np.abs(seg_v) > 1e-7).any(axis=1).mean())
        status = '活' if nz > 0.01 else '死'
        tag = ''
        if expect is True and nz <= 0.01:
            tag = ' !!ALERT 应活段恒死'
            alerts.append(seg)
        elif expect is None:
            tag = ' (设计性豁免)'
        print('  [%3d..%3d] %-18s 非零率%6.1f%% %s%s'
              % (off, off + width - 1, seg, nz * 100, status, tag))
    if alerts:
        print('\n!! %d个应活段恒死 — P0-1类重置吞并/接线断裂特征' % len(alerts))
        return 1
    print('\n巡检通过: 应活段全部有活性')
    return 0


if __name__ == '__main__':
    sys.exit(main())
