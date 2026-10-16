# -*- coding: utf-8 -*-
"""CH-5(2026-10-15): 蓄力宏使用观察报表 — 只读episode npz, 零侵入。

方案验收: "观察不设硬指标门槛(涌现性学习), 但必须有数据: 两周后战报
若蓄力使用率恒为0, 登记为学习动力学问题转S-9'同批裁定, 而非静默搁置"。
本工具产出该数据: 使用率/使用-回报相关/新系统卡与DD/HJC扩展宏同报。
用法: python tools/charge_usage_report.py [--eps 200]
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

EP_DIR = os.path.join(r'D:\temp\th123_models', 'fleet', 'episodes')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--eps', type=int, default=0, help='只取最近N个(0=全部)')
    a = ap.parse_args()
    from train_tm import CHAR_LIBS

    for ch in ('reimu', 'marisa', 'suika'):
        names = CHAR_LIBS[ch]['names']
        charge = {i for i, n in enumerate(names) if n.endswith('蓄')}
        cards = {i for i, n in enumerate(names)
                 if n in ('卡·怀表', '卡·白楼剑', '卡·人偶',
                          '卡·铜钱', '卡·绯想剑')}
        dd = {i for i, n in enumerate(names)
              if n in ('结界6', '结界1', '空结界4', '空结界6')}
        hjc = {i for i, n in enumerate(names) if n.endswith('取消')}
        eps = sorted(glob.glob(os.path.join(EP_DIR, 'ep_%s_*.npz' % ch)),
                     key=os.path.getmtime)
        eps = [e for e in eps if not e.endswith('.tmp.npz')]
        if a.eps:
            eps = eps[-a.eps:]
        if not eps:
            print('%s: 无episode' % ch)
            continue
        n_dec = 0
        use = {'蓄力': 0, '系统卡(新5张)': 0, 'DD变体': 0, 'HJC取消': 0}
        ep_usage, ep_rew = [], []
        for p in eps:
            try:
                d = np.load(p, allow_pickle=True)
                acts, rews = d['acts'], d['rews']
            except Exception:
                continue
            n_dec += len(acts)
            c = sum(1 for x_ in acts if x_ in charge)
            use['蓄力'] += c
            use['系统卡(新5张)'] += sum(1 for x_ in acts if x_ in cards)
            use['DD变体'] += sum(1 for x_ in acts if x_ in dd)
            use['HJC取消'] += sum(1 for x_ in acts if x_ in hjc)
            ep_usage.append(c / max(1, len(acts)))
            ep_rew.append(float(rews.sum()))
        if n_dec == 0:
            print('%s: 0决策' % ch)
            continue
        corr = (float(np.corrcoef(ep_usage, ep_rew)[0, 1])
                if len(ep_usage) > 2 and np.std(ep_usage) > 0 else None)
        print('%s: %d局 %d决策' % (ch, len(eps), n_dec))
        for k, v in use.items():
            print('  %-12s %6d次 (%.2f%%)' % (k, v, 100.0 * v / n_dec))
        print('  使用-回报相关: %s'
              % ('%.3f' % corr if corr is not None else '(方差0=未使用)')
              + ('  ⚠恒0 → S-9\'登记' if use['蓄力'] == 0 else ''))
    print('\n(CH-5口径: 使用率>0即有数据; 恒0两周→S-9\'同批裁定, 不静默)')


if __name__ == '__main__':
    main()
