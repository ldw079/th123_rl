# -*- coding: utf-8 -*-
"""A/B后批次·BC v3.4换装程序(mmap版, 2026-10-14用户裁定).

前置: ①bc_*_v3.npz三份齐 ②A/B final裁定已核(净分未降=可换装;
本批实测: 保留A1-2/净分+8.3pp/验收未达成——顶时判负100%正是本
换装要对症的病灶)。
动作: 旧npz+旧trio备份 → v3全量转trio入STORE(mmap, 零采样损失)
→ 验证 → 提示舰队重启生效。
回滚: BAK目录内文件拷回STORE并删除STORE下trio三件套。
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from bc_io import npz_to_trio, load_bank   # noqa: E402

V3_DIR = r'D:\temp\th123_bc_v3'
STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
BAK = os.path.join(V3_DIR, 'pre_v3_backup')
CHARS = ('reimu', 'marisa', 'suika')


def main():
    # 前置0(P1硬门禁, bug_2026-10-14_bc_trio_swap_lock): 舰队必须已停 —
    # learner持trio mmap句柄终身, 运行中换装=PermissionError半路崩+
    # 混血三件套风险。探测失败也拒绝(fail-closed)。
    from bc_io import fleet_running
    if fleet_running():
        print('!! 拒绝: 训练族进程存活(learner/actor/监督器/游戏)。')
        print('!! 先停机: python tools/train_start.py --stop')
        return 2
    print('前置OK: 舰队已停(无训练族进程)')
    # 前置1: v3三份齐 + 行数健全(60行假库事故防线, 2026-10-14晚)
    import numpy as np
    for ch in CHARS:
        p = os.path.join(V3_DIR, 'bc_%s_v3.npz' % ch)
        assert os.path.exists(p), '缺 %s (重建未完?)' % p
        d = np.load(p)
        n = len(d['Y'])
        d.close()
        assert n >= 50000, '%s仅%d行(<50k, 疑封顶bug/失败重建) — 拒绝' % (ch, n)
        print('前置OK: %s %d行' % (ch, n))
    # 前置2: 裁定确认
    print('!! 核对 /d/temp/ab_final_verdict.log: 净分未降(本批+8.3pp)=可换装。')
    print('!! 输入 YES 执行换装(mmap trio全量, 零采样损失):')
    if input().strip() != 'YES':
        print('中止(未确认)')
        return 1
    os.makedirs(BAK, exist_ok=True)
    for ch in CHARS:
        # 备份旧npz与旧trio(可回滚)
        old_npz = os.path.join(STORE, 'bc_%s.npz' % ch)
        if os.path.exists(old_npz) and not os.path.exists(
                os.path.join(BAK, 'bc_%s.npz' % ch)):
            shutil.copy2(old_npz, os.path.join(BAK, 'bc_%s.npz' % ch))
        for suf in ('_X.npy', '_S.npy', '_Y.npy', '_C.npy', '_meta.json'):
            t = os.path.join(STORE, 'bc_%s%s' % (ch, suf))
            if os.path.exists(t):
                shutil.copy2(t, os.path.join(BAK, 'bc_%s%s' % (ch, suf)))
        # v3全量转trio(命名bc_{char}, loader trio优先)
        src = os.path.join(V3_DIR, 'bc_%s_v3.npz' % ch)
        base = npz_to_trio(src, out_dir=STORE,
                           out_stem='bc_%s' % ch)   # max_rows=0全量
        # 验证: mmap加载+抽64行 — 期望宽度从现行宏库派生
        # P2修(从零#4): 原硬编码{'reimu':70,'marisa':76,'suika':77}在
        # 宏库扩展波(88/93/91)后必错 — 宏数/特征宽只有一个真值源
        X, S, Y = load_bank(ch, store=STORE)
        from feat_builder import FeatureBuilder
        from train_tm import CHAR_LIBS
        _exp = 5 * len(CHAR_LIBS[ch]['macros']) + FeatureBuilder.CORE_DIMS
        assert S.shape[1] == _exp, (ch, S.shape[1], _exp)
        import numpy as np
        idx = np.random.default_rng(0).integers(0, len(Y), 64)
        assert X[idx].shape == (64, X.shape[1])
        print('就位: %s %d行(mmap✓ 抽样64✓)' % (os.path.basename(base), len(Y)))
    print('换装完成 — 舰队重启(train_start --stop/--start)后生效;')
    print('回滚: %s → STORE 并删STORE下bc_*_*.npy' % BAK)
    return 0


if __name__ == '__main__':
    sys.exit(main())
