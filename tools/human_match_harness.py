# -*- coding: utf-8 -*-
"""task-69 人测 harness MVP (本机流程; 不接训练/不作弊).

R1: 只记录/写入己方输入；不读取用户(对手)输入；本模块不提供对手输入接口。
MVP: mock 模式跑 BoN 流程(无游戏内接入)，产出摘要+录像日志+快照冻结 hash，
用于先跑通"模型 vs 用户"人测流程；真实游戏接入后续版本。
"""
import argparse
import hashlib
import json
import os
import random
import time

SCHEMA = 1


class HumanMatchHarness:
    def __init__(self, bo=10, seed=0, snapshot='model_ppo_reimu_v0',
                 out_dir=r'D:\temp\human_match'):
        self.bo = int(bo)
        self.seed = int(seed)
        self.snapshot = snapshot
        self.out_dir = out_dir
        self.rng = random.Random(seed)
        self.own_inputs = []          # 只允许己方输入
        self.results = []
        self.started = time.time()
        self.forbidden_reads = 0

    def record_own_input(self, frame, keys):
        """只写己方输入; keys=己方 6键位图/方向；不接收对手输入."""
        self.own_inputs.append({'frame': int(frame), 'own': keys})

    def _try_read_opponent(self):
        """R1 哨兵: 任何读取对手输入的调用都记 forbidden 并拒绝."""
        self.forbidden_reads += 1
        raise PermissionError('R1: 禁止读取对手输入')

    def play_round(self, game_idx):
        # mock 局: 己方输入本地生成；对手输入不读取(无接口)
        frames = self.rng.randint(600, 1200)
        for f in range(0, frames, 2):
            self.record_own_input(f, {'dir': self.rng.choice([4, 5, 6]),
                                      'A': self.rng.random() < 0.1})
        win = self.rng.random() < 0.5
        self.results.append({'game': game_idx, 'frames': frames,
                             'win': win, 'own_inputs': len(range(0, frames, 2))})

    def summary(self):
        wins = sum(1 for r in self.results if r['win'])
        return {
            'schema': SCHEMA,
            'bo': self.bo,
            'seed': self.seed,
            'snapshot': self.snapshot,
            'snapshot_hash': hashlib.sha256(self.snapshot.encode()).hexdigest()[:16],
            'games': len(self.results),
            'wins': wins,
            'losses': len(self.results) - wins,
            'own_inputs': len(self.own_inputs),
            'forbidden_reads': self.forbidden_reads,
            'r1': 'only_own_inputs',
            'started': self.started,
            'results': self.results,
        }

    def run(self):
        for g in range(self.bo):
            self.play_round(g)
        os.makedirs(self.out_dir, exist_ok=True)
        ts = time.strftime('%Y%m%d_%H%M%S')
        summ = self.summary()
        p = os.path.join(self.out_dir, 'summary_%s.json' % ts)
        json.dump(summ, open(p, 'w', encoding='utf-8'), ensure_ascii=False,
                  indent=1)
        rp = os.path.join(self.out_dir, 'replay_%s.json' % ts)
        json.dump({'own_inputs': self.own_inputs[:5000],
                   'note': 'R1: 仅己方输入; 对手输入未读取'},
                  open(rp, 'w', encoding='utf-8'), ensure_ascii=False)
        return summ, p, rp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--bo', type=int, default=10)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--snapshot', default='model_ppo_reimu_v0')
    ap.add_argument('--out-dir', default=r'D:\temp\human_match')
    a = ap.parse_args()
    if not a.mock:
        print('MVP: 仅支持 --mock（真实游戏接入后续版本）')
        return 1
    h = HumanMatchHarness(bo=a.bo, seed=a.seed, snapshot=a.snapshot,
                          out_dir=a.out_dir)
    summ, p, rp = h.run()
    print(json.dumps({k: summ[k] for k in ('bo', 'games', 'wins', 'losses',
                                           'own_inputs', 'forbidden_reads',
                                           'r1', 'snapshot_hash')},
                     ensure_ascii=False))
    print('summary', p)
    print('replay', rp)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
