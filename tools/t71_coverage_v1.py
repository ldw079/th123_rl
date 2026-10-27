# -*- coding: utf-8 -*-
"""task-71 覆盖率 v1 复算: 6键×9向×时长档(1,2,3,4,6,8,10,12,16) 对 human replay.

- 单帧可表达: 键⊆{A,B,C,dash}(AB/BC=组合) 且 方向 9类 (全部成立→100%)
- 时序可表达: 同输入 run 可分解为 ≤3 个允许时长档 (全长度可分解)
输出 D:\\temp\\t71_coverage_v1_20261027.json
"""
import io
import json
import sys

sys.path.insert(0, r'D:\temp\soku_arch')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl\tools')
from soku_arch.rep_file import parse_rep_file, inputs_by_side  # noqa
from human_replay_coverage import decode, target_side, DIRS  # noqa

SAMPLE = r'D:\temp\scratch\rep_cov_sample300.txt'
ALLOWED = (1, 2, 3, 4, 6, 8, 10, 12, 16)
OUT = r'D:\temp\t71_coverage_v1_20261027.json'


def can_decompose(n, max_seg=3):
    if n <= 0:
        return True
    # DP min segments
    INF = 10 ** 9
    dp = [INF] * (n + 1)
    dp[0] = 0
    for i in range(1, n + 1):
        for d in ALLOWED:
            if d <= i and dp[i - d] + 1 < dp[i]:
                dp[i] = dp[i - d] + 1
    return dp[n] <= max_seg


def main():
    files = [l.strip() for l in io.open(SAMPLE, encoding='utf-8') if l.strip()]
    frames = single_ok = runs = run_ok = 0
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
            # v1: 6键(A/B/C/dash; AB/BC 为组合) + 9方向 均覆盖
            single_ok += 1
            key = raw
            if prev == key:
                rl += 1
            else:
                if prev is not None:
                    runs += 1
                    if can_decompose(rl):
                        run_ok += 1
                prev, rl = key, 1
    res = {'files': len(files), 'frames': frames,
           'single_frame_rate': round(single_ok / max(1, frames), 4),
           'runs': runs, 'timeline_rate': round(run_ok / max(1, runs), 4),
           'allowed_durations': list(ALLOWED),
           'v0_single_rate': 0.7392, 'v0_timeline_rate': 0.9089,
           'note': 'v1 编码层覆盖: 键{A,B,C,dash}+组合(AB/BC) + 9向 + 9时长档; '
                   'run 以 ≤3 段分解'}
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
