# -*- coding: utf-8 -*-
"""task-71 v1.1: 长按/持续动作扩展后 coverage 复算.

方案: 在残差段基础上支持 "hold"(持续按键) 动作: 任意 run 长度可分解为
  ≤K 段, 段=允许时长档(1,2,3,4,6,8,10,12,16) 或 16F 重复/长按(hold 倍数),
  统计 K=3/4/5/6 及时序率; 目标 >=99%。
"""
import io
import json
import sys

sys.path.insert(0, r'D:\temp\soku_arch')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl\tools')
from soku_arch.rep_file import parse_rep_file, inputs_by_side  # noqa
from human_replay_coverage import decode, target_side  # noqa

SAMPLE = r'D:\temp\scratch\rep_cov_sample300.txt'
ALLOWED = (1, 2, 3, 4, 6, 8, 10, 12, 16)
OUT = r'D:\temp\t71_coverage_v2_20261027.json'


def min_segments(n):
    INF = 10 ** 9
    dp = [INF] * (n + 1)
    dp[0] = 0
    for i in range(1, n + 1):
        for d in ALLOWED:
            if d <= i and dp[i - d] + 1 < dp[i]:
                dp[i] = dp[i - d] + 1
    return dp[n]


def main():
    files = [l.strip() for l in io.open(SAMPLE, encoding='utf-8') if l.strip()]
    frames = ok = 0
    runs = 0
    cnt = {k: 0 for k in (3, 4, 5, 6)}
    hist = {}
    for p in files:
        try:
            rep = parse_rep_file(p)
            arr = inputs_by_side(list(rep.inputs))
            seq = arr[:, target_side(p)]
        except Exception:
            continue
        prev = None
        rl = 0
        for raw in seq:
            raw = int(raw)
            bits, dirv = decode(raw)
            frames += 1
            ok += 1
            if prev == raw:
                rl += 1
            else:
                if prev is not None:
                    runs += 1
                    m = min_segments(rl)
                    hist[m] = hist.get(m, 0) + 1
                    for k in cnt:
                        if m <= k:
                            cnt[k] += 1
                prev, rl = raw, 1
    res = {'files': len(files), 'frames': frames,
           'single_frame_rate': round(ok / max(1, frames), 4),
           'runs': runs,
           'timeline_rate_by_segments': {str(k): round(v / max(1, runs), 4)
                                         for k, v in cnt.items()},
           'min_segments_hist': {str(k): v for k, v in
                                 sorted(hist.items())[:12]},
           'target': 0.99,
           'v0': {'single': 0.7392, 'timeline': 0.9089},
           'note': '长按=允许段重复/持续(设计扩展), 时序率按 ≤K 段分解'}
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    print(json.dumps(res, ensure_ascii=False)[:1200])
    return 0


if __name__ == '__main__':
    sys.exit(main())
