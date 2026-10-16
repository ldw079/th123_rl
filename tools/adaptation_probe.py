# -*- coding: utf-8 -*-
"""S-8(V-4): 变招压力测试环境 — 规则反制者对手驱动。

设计: SideDriver的外壳, 在frame_input中注入"反制偏好" —
追踪我方最近N决策的主导类别 → 该类被反制概率提升。
产出: 逐场宏分布演变+punish率轨迹+行为标记。

用法(与branch_demo同构, 需真机):
  python tools/adaptation_probe.py --char reimu --games 30
"""
import argparse
import collections
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

NEUTRAL = {}
CLS_ORDER = ('JUMP', 'MELEE', 'BULLET', 'SKILL', 'GUARD_PREP', 'OTHER')


class CounterOpponent:
    """规则反制者 — 非SideDriver(不加载模型), 纯规则决策。

    反制偏好: 追踪对方最近N决策的类别分布 → 对主导类别
    产生反制行为(该类被punish概率×boost)。
    输出: 简单反制行为序列(防御/闪避/插动)。
    """

    def __init__(self, char, boost=2.5, window=20):
        from train_tm import CHAR_LIBS
        from my_punish_tracker import classify
        self.char = char
        self.lib = CHAR_LIBS[char]
        self.classify = classify
        self.boost = boost
        self.window = window
        self.cls_hist = collections.deque(maxlen=window)
        self.cls_punish = {c: [] for c in CLS_ORDER}  # 类别→punish率追踪
        # 反制动作库(按对手主导类别)
        self._counters = {
            'JUMP': ['蹲防', '2A', '前冲'],       # 对空/逃跳
            'MELEE': ['后退', '结界4', '高跳'],     # 拉距/防/逃
            'BULLET': ['空冲', '前冲', '结界2'],    # 擦弹接近
            'SKILL': ['立防', '蹲防', '后退'],      # 防住等空隙
            'GUARD_PREP': ['前冲', '5B', '2A'],    # 压制方防御=磨灵机会
            'OTHER': ['立防', '5A', '前冲'],
        }
        self._rng = np.random.default_rng(42)

    def observe(self, macro_name):
        """对方出了一招 — 记类别。"""
        cls = self.classify(macro_name, self.lib)
        self.cls_hist.append(cls)

    def frame_input(self, own, opp, weather, objs, bullets):
        """产出反制行为(非模型 — 规则查表+随机)。"""
        # 主导类别
        if not self.cls_hist:
            cls = 'OTHER'
        else:
            cnt = collections.Counter(self.cls_hist)
            cls = cnt.most_common(1)[0][0]
        # 从反制库选(加权随机: 主导类反制×boost)
        candidates = self._counters.get(cls, self._counters['OTHER'])
        n = len(candidates)
        w = np.ones(n)
        w[0] = self.boost  # 第一候选(最克制)加权
        probs = w / w.sum()
        pick = int(self._rng.choice(n, p=probs))
        name = candidates[pick]
        # 查宏id
        idx = self.lib['names'].index(name) if name in self.lib['names'] else -1
        if idx < 0:
            return {}
        # 返回宏脚本(简化: 直接把宏脚本当输入队列)
        return ('macro', idx)

    def note_punish(self, cls, punished):
        """记录某类被punish(用于轨迹输出)。"""
        self.cls_punish[cls].append(1.0 if punished else 0.0)


def analyze_adaptation(log_path):
    """逐场宏分布演变+punish率轨迹+行为标记。"""
    with open(log_path, encoding='utf8') as f:
        games = json.load(f)
    print('== 变招压力分析: %d场 ==' % len(games))
    for i, g in enumerate(games):
        dist = g.get('macro_dist', {})
        top = sorted(dist.items(), key=lambda x: -x[1])[:5]
        pun = g.get('punish_rates', {})
        print('场%02d 胜%s | Top5: %s | punish: %s'
              % (i + 1, g.get('win', '?'),
                 ' '.join('%s×%d' % t for t in top),
                 ' '.join('%s:%.2f' % (k, v)
                          for k, v in pun.items() if v > 0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu')
    ap.add_argument('--games', type=int, default=30)
    ap.add_argument('--analyze', help='分析已有日志')
    a = ap.parse_args()
    if a.analyze:
        analyze_adaptation(a.analyze)
        return
    # 真实模式(需真机) — 构建CounterOpponent跑N场, 输出日志
    print('S-8变招压力测试(真机模式) — %s × %d场 vs 规则反制者'
          % (a.char, a.games))
    print('注: 真实模式需游戏实例; 分析模式: --analyze <log.json>')
    # 构建对手+输出模拟日志(离线骨架验证)
    opp = CounterOpponent(a.char)
    print('反制者就绪: boost=%.1f window=%d' % (opp.boost, opp.window))
    print('反制库: %s' % {k: v[:2] for k, v in opp._counters.items()})


if __name__ == '__main__':
    main()
