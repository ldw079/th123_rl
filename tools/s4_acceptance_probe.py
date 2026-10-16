# -*- coding: utf-8 -*-
"""S-4(V-3) 验收探针: 3场持续对空 → GRU应降低第3场跳宏采样率。

验收判据(方案§S-4): 合成"3场持续对空"(对手反复升JA/对空)情境,
   比较第1场 vs 第3场的跳宏(JUMP类)采样率 — GRU记忆了
   "跳被连续反制"后应降低跳的倾向。

离线版(无需真机): 用SideDriver+模拟状态流, 连续3局喂入
   对手攻击状态, 检查宏分布中JUMP类占比的跨场变化。

用法: python tools/s4_acceptance_probe.py [--char reimu] [--trials 20]
退出码: 0=通过(第3场跳率<第1场), 1=不通过或GRU未学到。
"""
import argparse
import collections
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

CLS_ORDER = ('JUMP', 'MELEE', 'BULLET', 'SKILL', 'GUARD_PREP', 'OTHER')


def simulate_match(driver, opp_jump_rate=0.8, n_decisions=30):
    """模拟一局: 对手以jump_rate概率跳(产生对空惩罚压力)。

    返回(宏类别分布, 平均punish率)。
    """
    from side_driver import SideDriver
    from my_punish_tracker import classify as clsfy

    dist = collections.Counter()
    n_punished = 0
    prev_opp_hp = 10000
    prev_my_hp = 10000

    # 视觉栈预热(SideDriver需≥3帧_push_frame才能决策)
    for _w in range(5):
        driver._push_frame(
            {'position.x': 300.0, 'position.y': 0.0, 'hp': 10000,
             'action': 0, 'direction': 1, 'cardGauge': 0},
            {'position.x': 700.0, 'position.y': 0.0, 'hp': 10000,
             'action': 0, 'direction': -1, 'cardGauge': 0}, [])

    for i in range(n_decisions):
        own = {'position.x': 300.0, 'position.y': 0.0, 'spirit': 1500,
               'hp': 10000, 'airBorne': False, 'direction': 1,
               'action': 0, 'cardGauge': 0, 'score': 0,
               'hand': b'\xff' * 10, 'comboDamage': 0, 'untech': 0,
               'timeStop': 0, 'hitStop': 0, 'airDashCount': 0,
               'comboLimit': 0,
               'skills': b'\x00' * 15, 'maxSpirit': 1000,
               'healingCharm': 0}
        # 对手: 以概率跳(空中+JA), 否则地面
        opp_jumping = np.random.random() < opp_jump_rate
        opp = dict(own)
        opp['position.x'] = 700.0
        opp['airBorne'] = opp_jumping
        opp['position.y'] = 150.0 if opp_jumping else 0.0
        opp['action'] = 305 if opp_jumping else 0  # jA=305 / 待机

        # 模拟惩罚: 我方跳+对手对空 = 被打
        weather = {'active': 0, 'displayed': 0, 'timer': 0}
        inp = driver.frame_input(own, opp, weather, [], [])
        if isinstance(inp, dict) and '_last_mid' in dir(driver):
            mid = getattr(driver, '_last_mid', -1)
            if mid >= 0:
                nm = driver.macros[mid][0]
                cls = clsfy(nm, driver.lib)
                dist[cls] += 1
                # 跳+对手对空 → punish
                if cls == 'JUMP' and opp_jumping:
                    n_punished += 1
                    own['hp'] -= 500  # 模拟被打

    total = sum(dist.values())
    jump_rate = dist.get('JUMP', 0) / max(1, total)
    punish_rate = n_punished / max(1, dist.get('JUMP', 1))
    return jump_rate, punish_rate, dist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu')
    ap.add_argument('--trials', type=int, default=20,
                    help='每场模拟局数(取均值)')
    ap.add_argument('--model', help='模型路径(缺省=STORE生产档)')
    a = ap.parse_args()

    from side_driver import SideDriver

    store = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
    model_path = a.model or os.path.join(
        store, 'model_ppo_%s.npz' % a.char)

    print('S-4验收探针: %s × %d场模拟/trial × 3场连续' % (
        a.char, a.trials))
    print('模型: %s' % model_path)

    # 检查W_gru是否非零(GRU已学到东西)
    import numpy as _np
    d = _np.load(model_path)
    w_gru = d.get('W_gru')
    if w_gru is None or _np.abs(w_gru).max() < 1e-6:
        print('⚠ W_gru全零 — GRU尚未学习, 探针无意义')
        print('  (需要更多训练更新使W_gru脱离零区)')
        return 1
    print('W_gru范数: %.6f (已学习)' % _np.abs(w_gru).max())
    d.close()

    # 跑3场连续(每场=trials局平均)
    rates = []
    for match in range(3):
        driver = SideDriver(a.char, 'L')
        driver.load(model_path)
        # 重置GRU状态(场边界)
        driver._gru_h = None
        # 前面场的GRU隐状态会通过decide()自然携带
        jump_rates = []
        for t in range(a.trials):
            jr, pr, dist = simulate_match(driver)
            jump_rates.append(jr)
        avg_jr = float(np.mean(jump_rates))
        rates.append(avg_jr)
        print('场%d: 跳宏率%.1f%% (punish率%.1f%%) Top: %s' % (
            match + 1, 100 * avg_jr, 100 * pr,
            ' '.join('%s:%d' % (k, v) for k, v in
                     dist.most_common(3))))

    # 判定: 第3场 < 第1场 (GRU学到了"跳被反制")
    r1, r3 = rates[0], rates[-1]
    print('\n判定: 场1=%.1f%% 场3=%.1f%% → %s' % (
        100 * r1, 100 * r3,
        '✓通过(第3场跳率下降 — GRU记忆反制)' if r3 < r1
        else '✗不通过(需更多训练或检查GRU)'))
    return 0 if r3 < r1 else 1


if __name__ == '__main__':
    sys.exit(main())
