# -*- coding: utf-8 -*-
"""task-80 tactic 基线: 从 episodes 的 acts 分布推断 tactic 代理(只读).

分类(按宏名):
  approach: 前进/前冲/空翔前/前跳/飞翔/DA/前压
  pressure: 压制/压/择/连段/连/崩/爆灵
  defense : 防御/立防/蹲防/受身/起身/结界/逃/后跳/后退
  poke    : 5A/2A/5B/2B/5C/6A/6B/6C/jA/jB/jC 等
  其它/卡
输出: D:\temp\tactic_baseline_20261027.json
"""
import glob
import json
import os
import sys

import numpy as np

ROOT = r'C:\Users\96120\Desktop\workplace\th123_rl'
sys.path.insert(0, ROOT)
from train_tm import CHAR_LIBS  # noqa: E402

OUT = r'D:\temp\tactic_baseline_20261027.json'
CATS = {
    'approach': ('前进', '前冲', '空翔前', '前跳', '飞翔', 'DA', '前'),
    'pressure': ('压制', '压', '择', '连段', '连', '崩', '爆', '推板'),
    'defense': ('防御', '立防', '蹲防', '受身', '起身', '结界', '逃',
                '后跳', '后退', '空防'),
}


def cat(name):
    for c, keys in CATS.items():
        if any(k in name for k in keys):
            return c
    if name.startswith('卡'):
        return 'card'
    return 'poke'


def main():
    res = {'chars': {}}
    for ch, lib in CHAR_LIBS.items():
        names = [m[0] for m in lib['macros']]
        cats = {'approach': 0, 'pressure': 0, 'defense': 0, 'poke': 0,
                'card': 0}
        files = glob.glob(os.path.join(
            r'D:\temp\th123_models', '**', 'ep_%s_*.npz' % ch),
            recursive=True)
        files += glob.glob(os.path.join(
            r'D:\temp\th123_models\fleet\episodes_keep', ch, 'ep_*.npz'))
        n_dec = 0
        for p in files:
            try:
                with np.load(p, allow_pickle=True) as z:
                    A = np.asarray(z['acts'], np.int64)
                for a in A:
                    if 0 <= a < len(names):
                        cats[cat(names[a])] += 1
                        n_dec += 1
            except Exception:
                continue
        if n_dec:
            res['chars'][ch] = {'episodes': len(files), 'decisions': n_dec,
                                'cats': cats,
                                'rates': {k: round(v / n_dec, 3)
                                          for k, v in cats.items()}}
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    print(json.dumps(res, ensure_ascii=False)[:1200])
    return 0


if __name__ == '__main__':
    sys.exit(main())
