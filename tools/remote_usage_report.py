# -*- coding: utf-8 -*-
"""B3(F-9观察闭环): 330px外弹幕使用分布报告 — 远程行为是否涌现.

背景(主规划B3 / round12 §2): R60(F-9)解禁 dx>330 的弹幕/技能采样(原类级
330门误禁全部攻击族, 远程立回结构性不可学)。B3验收 = 48h 内远程弹幕份额
变化留档; 若未涌现 → 查掩码残余压制。

数据源(零新增仪表, 全部离线): fleet episode npz —
  sides[:, 2*n_macros + 5] = clip(|dx|/600, 0, 1)   (feat_builder核心标量段)
  acts = 实际执行宏ID(含探针/价值引导重选 = 真实行为, 非采样倾向)
  meta.contract.n_macros + CHAR_LIBS[char]["bullet"] 宏名集

口径: 逐决策按 |dx| 分桶(<bucket 近战区 / >=bucket 远程区), 弹幕族占该桶
  决策份额; 按 episode 文件名时间戳排序切窗对比(默认前后两半)。
  注意: meta.ts 只有 %H:%M:%S 无日期, 排序一律用文件名里的完整时间戳。

用法:
  python tools/remote_usage_report.py                    # 默认fleet, 前后两半
  python tools/remote_usage_report.py --windows 3 --bucket 330
  python tools/remote_usage_report.py --output D:\\...\\b3_report.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

EP_DIR = os.environ.get(
    'TH123_EP_DIR', r'D:\temp\th123_models\fleet\episodes')

# 核心标量段布局(feat_builder.build vals16): col4 = clip(|dx|/600, 0, 1)
# R67c(2026-10-12)修正: 原误用col5(=own_x/620, 己方站位)当距离 — B3首份
# 基线(b3_baseline_20261011.json)实测的是"站位在舞台右半"而非"远程",
# 结论作废待重测; col4经feat_builder标定测试钉死(tests/test_remote_usage_b3).
ADX_COL_IN_CORE = 4
ADX_SCALE = 600.0

_TS_RE = re.compile(r'_(\d{8})_(\d{6})\.npz$')


def _ep_sort_key(path):
    """文件名尾部 _YYYYMMDD_HHMMSS.npz → 排序键; 无匹配退回mtime."""
    m = _TS_RE.search(os.path.basename(path))
    if m:
        return m.group(1) + m.group(2)
    return '99999999999999'  # 无时间戳排最后(不干扰有据可依的排序)


def char_names_bullet(char):
    """(宏名列表, 弹幕名集合) — 与 TMTrainer 同源(CHAR_LIBS 顺序即宏ID序)."""
    from train_tm import CHAR_LIBS
    lib = CHAR_LIBS[char]
    names = [m[0] for m in lib["macros"]]
    return names, set(lib.get("bullet", ()))


def collect(ep_dir):
    """扫描 episode npz → [{char, ts, adx(np), acts(np), bullet(np.bool)}].

    schema≠2 或契约不符的旧档跳过并计数(不消费不删, R63哲学)。
    """
    import numpy as np
    from episode_core import load_episode_npz

    out, skipped = [], []
    for path in sorted(glob.glob(os.path.join(ep_dir, '*.npz'))):
        try:
            arrays, meta = load_episode_npz(path)
        except Exception as e:
            skipped.append('%s(%s)' % (os.path.basename(path),
                                       type(e).__name__))
            continue
        char = meta.get("char")
        n_macros = int(meta["contract"]["n_macros"])
        names, bullet_set = char_names_bullet(char)
        if len(names) != n_macros:
            skipped.append('%s(宏数不符)' % os.path.basename(path))
            continue
        sides = arrays["sides"]
        adx_col = 2 * n_macros + ADX_COL_IN_CORE
        adx = np.clip(sides[:, adx_col].astype(np.float64)
                      * ADX_SCALE, 0, ADX_SCALE)
        is_bullet = np.array([names[a] in bullet_set
                              for a in arrays["acts"]], dtype=bool)
        m = _TS_RE.search(os.path.basename(path))
        out.append({
            'char': char,
            'ts': (m.group(1) + '_' + m.group(2)) if m else '?',
            'adx': adx,
            'acts': arrays["acts"],
            'bullet': is_bullet,
        })
    out.sort(key=lambda e: e['ts'])
    return out, skipped


def report(ep_dir=EP_DIR, bucket=330.0, windows=2):
    """主报告: 逐角色逐窗 × 逐距离桶的弹幕份额 + 远程Top弹幕."""
    import numpy as np

    eps, skipped = collect(ep_dir)
    chars = sorted({e['char'] for e in eps})
    per_char = {c: [e for e in eps if e['char'] == c] for c in chars}

    result = {
        'ep_dir': ep_dir, 'bucket_px': bucket, 'windows': windows,
        'episodes': len(eps), 'skipped': skipped,
        'chars': {},
    }
    for c, ces in per_char.items():
        n = len(ces)
        win_reports = []
        for w in range(windows):
            lo = n * w // windows
            hi = n * (w + 1) // windows
            chunk = ces[lo:hi]
            if not chunk:
                # R67d(bug_2026-10-12_b3_empty_window_keyerror): 空窗补齐
                # 键集 — 原只写range/decisions, far_share_delta下标即KeyError
                # (触发: 单角色episode数<windows; 打印路径考虑过空窗而计算
                # 路径漏了 = 防御不对称型)
                win_reports.append({'range': [lo, hi], 'decisions': 0,
                                    'far_decisions': 0,
                                    'near_bullet_share': None,
                                    'far_bullet_share': None,
                                    'top_far_bullets': {}})
                continue
            adx = np.concatenate([e['adx'] for e in chunk])
            bul = np.concatenate([e['bullet'] for e in chunk])
            acts = np.concatenate([e['acts'] for e in chunk])
            far = adx >= bucket
            near_mask = ~far
            top_far = {}
            if far.any() and bul[far].any():
                names, _ = char_names_bullet(c)
                u, cnt = np.unique(acts[far & bul], return_counts=True)
                top_far = {names[int(i)]: int(k)
                           for i, k in sorted(zip(u, cnt),
                                              key=lambda x: -x[1])[:5]}
            win_reports.append({
                'range': [lo, hi],
                'ts_range': [chunk[0]['ts'], chunk[-1]['ts']],
                'decisions': int(len(adx)),
                'far_decisions': int(far.sum()),
                'near_bullet_share': float(
                    bul[near_mask].mean()) if near_mask.any() else None,
                'far_bullet_share': float(
                    bul[far].mean()) if far.any() else None,
                'top_far_bullets': top_far,
            })
        # R67d: 原and/or惯用法在delta恰为0.0时误入or None分支("无数据"
        # 误标真零变化); 改显式判空 — 与空窗键集补齐同批(bug档两处一起清)
        _d0 = win_reports[0].get('far_bullet_share')
        _d1 = win_reports[-1].get('far_bullet_share')
        result['chars'][c] = {
            'episodes': n,
            'windows': win_reports,
            'far_share_delta': (round(_d1 - _d0, 4)
                                if (_d0 is not None and _d1 is not None)
                                else None),
        }
    return result


def _fmt_share(v):
    return 'n/a' if v is None else '%5.1f%%' % (v * 100)


def print_report(rep):
    print('episodes=%d (跳过=%d) bucket=%.0fpx windows=%d'
          % (rep['episodes'], len(rep['skipped']), rep['bucket_px'],
             rep['windows']))
    for c, cr in rep['chars'].items():
        print('--- %s (%d局) ---' % (c, cr['episodes']))
        for w in cr['windows']:
            if w.get('decisions', 0) == 0:
                print('  窗[%d:%d] 空' % (w['range'][0], w['range'][1]))
                continue
            print('  窗[%d:%d] %s~%s 决策%d(远程%d) 弹幕份额 近%s/远%s'
                  % (w['range'][0], w['range'][1],
                     w['ts_range'][0], w['ts_range'][1],
                     w['decisions'], w['far_decisions'],
                     _fmt_share(w['near_bullet_share']),
                     _fmt_share(w['far_bullet_share'])))
            if w['top_far_bullets']:
                tops = ' '.join('%s×%d' % kv
                                for kv in w['top_far_bullets'].items())
                print('    远程Top: %s' % tops)
        d = cr['far_share_delta']
        if d is not None:
            verdict = '涌现↑' if d > 0.005 else (
                '持平' if d > -0.005 else '回落↓')
            print('  远程弹幕份额变化: %+0.4f (%s)' % (d, verdict))
        else:
            print('  远程弹幕份额变化: n/a (窗内无远程决策或样本空)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ep-dir', default=EP_DIR)
    ap.add_argument('--bucket', type=float, default=330.0)
    ap.add_argument('--windows', type=int, default=2)
    ap.add_argument('--output', default=None)
    args = ap.parse_args()

    rep = report(args.ep_dir, args.bucket, args.windows)
    print_report(rep)
    if args.output:
        tmp = args.output + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        os.replace(tmp, args.output)
        print('报告:', args.output)
    return 0 if rep['episodes'] else 1


if __name__ == '__main__':
    sys.exit(main())
