# -*- coding: utf-8 -*-
"""W1(研究借鉴方案§W1): 能力归因 — 延迟消融评估通道.

同一模型快照在k帧观察延迟下评估 → 强度-延迟曲线.
延迟垫片(DelayedView)作用于**全管线**: 特征构建/帧级事件/宏执行器
门判定全部消费延迟后状态(生态效度口径, 方案审查②裁定).

档位(用户裁定2026-10-13): k ∈ {0, 3, 5, 8}帧(≈0/48/81/129ms@62fps).
主档5帧(≈81ms).
"""
from __future__ import annotations

import os
import sys
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')


class DelayedView:
    """k帧观察延迟垫片 — push当前帧, 返回k帧前的帧.

    全管线口径: 调用方将DelayedView的返回值喂给SideDriver(特征/事件/
    宏门全走延迟), 计分用真值不受影响.
    """

    def __init__(self, k):
        self.k = int(k)
        self.buf = deque(maxlen=self.k + 1)
        self.warmup = 0   # 未满k帧的帧数(报告用)

    def push(self, frame):
        """喂入当前帧tuple, 返回k帧前的帧(不足k返回None=中性帧)."""
        self.buf.append(frame)
        if len(self.buf) <= self.k:
            self.warmup += 1
            return None
        return self.buf[0]

    def reset(self):
        self.buf.clear()
        self.warmup = 0


def run_delayed_matchup(char_a, char_b, port, games=60, tps=None,
                        delay_frames=0, snap_b=None):
    """单对位×单延迟档 → (wins, losses, timeout_n, timeout_loss).

    与eval_matrix.run_matchup同构, 区别: 观察经DelayedView延迟k帧.
    对手不延迟(测"我们让步多少").
    """
    from soku_client2 import GameEnded, OPCODE_GAME_ENDED
    from side_driver import EvalEnv, SideDriver
    from kit_config import STORE_DIR

    env = EvalEnv(port, char_left=char_a, char_right=char_b,
                  vs_com=False, tps=tps, render=False)
    driver = SideDriver(char_a, 'L')
    driver.set_opponent(char_b)   # P1-6(从零#5): 对手角色注入
    # P1-1(从零#5): 活档(_fleet 优先)
    from kit_config import live_model_path
    model_path = live_model_path(char_a, STORE_DIR)
    driver.load(model_path)

    opp = SideDriver(char_b, 'R')
    # P1-6(审计#6残余): 对手驱动同样要注入对家角色 — 原只注入了 A 侧驱动,
    # 对手 one-hot 段(227+池序)在 B 侧仍全零 = A/B 样本分布不对称。
    opp.set_opponent(char_a)
    opp_model = snap_b or live_model_path(char_b, STORE_DIR)
    opp.load(opp_model)
    opp.reset_match()
    driver.reset_match()

    # 排干intro
    from soku_client2 import OPCODE_GAME_FRAME
    NEUTRAL = {}
    for _ in range(240):
        try:
            if env.step(NEUTRAL, NEUTRAL) is None:
                break
        except Exception:
            break

    dv = DelayedView(delay_frames)
    wins_a = wins_b = timeout_n = timeout_loss = 0
    exc_a = exc_b = 0   # 审计遗留: 异常计数留痕(不静默吞)
    score_prev = (0, 0)
    inp_a = {}
    inp_b = {}

    try:
        for frames in range(45000):
            # 全管线延迟: SideDriver吃延迟后状态
            r = env.step(inp_a, inp_b)
            if env.last_match:
                _w, ls, rs = env.last_match
                if ls > rs:
                    wins_a += 1
                elif rs > ls:
                    wins_b += 1
                env.last_match = None
                dv.reset()
                driver.reset_match()
                opp.reset_match()
                inp_a = inp_b = {}
                if wins_a + wins_b >= games:
                    break
                continue
            if r is None:
                # P2修(从零#4): timeout_n原为死计数器(初始化+返回但永不
                # 递增 — 承诺的超时统计不存在)。真语义: env无果终止
                # (连接断/局中止)计timeout; 顶时判负(game无时钟, 见
                # JZ-2§1.6撤回)不存在, timeout_loss恒0并注记
                timeout_n += 1
                break
            left, right, weather, objs = r
            sl, sr = left.get('score', 0), right.get('score', 0)
            # 顶时判定
            _now_scores = (sl, sr)
            if frames > 1000 and _now_scores == score_prev:
                pass  # 让自然超时/结算走env.last_match
            score_prev = _now_scores

            # 观察延迟: a侧吃延迟帧, b侧不延迟
            delayed = dv.push((left, right, weather, objs))
            if delayed is not None:
                d_left, d_right, d_weather, d_objs = delayed
                try:
                    inp_a = driver.frame_input(
                        d_left, d_right, d_weather, d_objs, []) or {}
                except Exception:
                    exc_a += 1
                    inp_a = {}
            else:
                inp_a = {}
            try:
                inp_b = opp.frame_input(right, left, weather, objs, []) or {}
            except Exception:
                exc_b += 1
                inp_b = {}
    except Exception as e:
        print('[W1] 对局异常(%s)' % e)
    finally:
        try:
            env.inst.close()
        except Exception:
            pass

    if exc_a > 10 or exc_b > 10:
        print('[W1] 异常率过高: a侧%d b侧%d (计入分母可能失真)' % (
            exc_a, exc_b))
    # timeout_loss: 非想天则无回合时钟(JZ-2§1.6撤回记录) — 恒0,
    # 保留签名兼容; timeout_n=env无果终止计数(P2从零#4激活)
    return wins_a, wins_b, timeout_n, timeout_loss, dv.warmup


def pilot(char='reimu', opp_chars=('marisa', 'suika'),
          delays=(0, 3, 5, 8), games_per=60, port=20910):
    """减配试点: 1角色×2对手×4档(方案§W1 v2裁定)."""
    from portmap import SEGMENTS
    lo, hi = SEGMENTS['eval']
    assert lo <= port <= hi, 'port不在eval段'

    print('==== W1延迟消融试点: %s × %s × 档位%s × %d局 ====' % (
        char, opp_chars, delays, games_per))
    results = {}
    for opp in opp_chars:
        for k in delays:
            t0 = time.time()
            wa, wb, tn, tl, warmup = run_delayed_matchup(
                char, opp, port, games=games_per,
                delay_frames=k)
            wr = wa / max(wa + wb, 1)
            results[(opp, k)] = {'wins': wa, 'losses': wb,
                                 'wr': round(wr, 3),
                                 'wall_s': round(time.time() - t0)}
            print('  %s vs %s @%d帧: %dW-%dL (%.0f%%) %.0fs' % (
                char, opp, k, wa, wb, wr * 100,
                time.time() - t0))
    return results


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu')
    ap.add_argument('--games', type=int, default=60)
    ap.add_argument('--port', type=int, default=20910)
    a = ap.parse_args()
    res = pilot(char=a.char, games_per=a.games, port=a.port)
    import json
    out = os.path.join(HERE, 'w1_pilot_%s.json' % a.char)
    k_map = {'%s@%d' % (o, d): v for (o, d), v in res.items()}
    json.dump(k_map, open(out, 'w', encoding='utf8'),
              ensure_ascii=False, indent=1)
    print('结果:', out)
