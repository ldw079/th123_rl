# -*- coding: utf-8 -*-
"""W2阶段1(2026-10-14): 反事实危险显影卡 — 同一局面, 实际宏 vs 替代宏
的N次续演结果分布对比(宏动作天然规避单帧替换失真)。

随机源(计划v2审查③: 至少启用两项, 显式且可复现):
  ① 策略采样温度 temp≥0.5 (接管者ppo按副本播种)
  ② 对手规格轮换 ≥2风格 (对手池快照+COM, 每副本换)
  ③ 种子 = md5(局面|分支|副本序号) → ppo.rng (①③同源不同义)

分布非退化(硬验收): N≥20续演须≥2种不同终局, 否则该批次作废(void)。
风险表对齐: ①接管者标注(本版=原策略接管, 温度显式); ②对手≥2风格
启动时断言; ③报告附各副本终局列表供人工抽查。

用法(真实模式, 需训练游戏+空闲CPU):
  python tools/danger_reveal.py --char reimu --scenario mid_range \
      --actual "立防" --alt "前冲,DA" --n 20 --output danger.json
mock模式(测试/演示, 无游戏):
  python tools/danger_reveal.py --mock --actual "立防" --alt "前冲,DA"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf8')

NEUTRAL = {"A": False, "B": False, "C": False, "D": False,
           "SC": False, "SW": False, "H": 0, "V": 0}
DANGER_HP_DEFAULT = 2500        # 危险兑现 = 承伤≥25%(或KO负)
KO_LOSS, KO_WIN, TIMEOUT = 'ko_loss', 'ko_win', 'timeout'


def stable_seed(*parts):
    """随机源③: 种子=md5(局面|分支|副本序号) — 可复现且跨副本分散."""
    h = hashlib.md5('|'.join(str(p) for p in parts).encode('utf8'))
    return int(h.hexdigest()[:8], 16)


# ---------------------------------------------------------------- 宏脚本
def build_macro_script(char, names):
    """宏名序列 → 逐帧输入列表(与branch_demo同构: H/V轴+ABCD)."""
    from train_tm import CHAR_LIBS
    lib = CHAR_LIBS[char]
    by_name = {m[0]: m[1] for m in lib['macros']}
    frames_list = []
    for n in names:
        if n not in by_name:
            raise SystemExit('未知宏: %s (角色%s可用: %s)'
                             % (n, char, list(by_name)[:8]))
        for ks, fr in by_name[n]:
            if not isinstance(ks, str):
                inp = {}
                for k in ks:
                    if k == 'right':
                        inp['H'] = 1
                    elif k == 'left':
                        inp['H'] = -1
                    elif k == 'up':
                        inp['V'] = -1
                    elif k == 'down':
                        inp['V'] = 1
                    elif k in ('A', 'B', 'C', 'D'):
                        inp[k] = True
                frames_list.extend([inp] * int(fr))
    return frames_list


def mk_input(frames_list):
    def _inp(f):
        return frames_list[f] if f < len(frames_list) else {}
    return _inp


# ---------------------------------------------------------------- 续演批次
def ending_signature(e):
    """终局签名 — 非退化判据用(胜/负/超时 ×KO ×伤害分桶500).

    计划原文"≥2种不同终局"的意图=检测随机源失效(N条相同轨迹),
    不是惩罚真收敛的安全路线 — 伤害分桶让真实轨迹差异可观测,
    而随机源失效时N副本完全相同仍恒为1种签名。
    """
    return (e['outcome'], e['ko'], min(abs(e['my_hp_delta']) // 500, 4))


def run_batch(replica_fn, n, situation_id, branch_name,
              danger_hp=DANGER_HP_DEFAULT):
    """N次续演 → 终局列表 + 分布统计 + 非退化判定.

    replica_fn(i, seed) → 单副本终局dict(由调用方注入真实/mock实现).
    """
    endings = []
    for i in range(n):
        seed = stable_seed(situation_id, branch_name, i)   # 随机源③
        e = replica_fn(i, seed)
        e['i'] = i
        e['seed'] = seed
        endings.append(e)
    sigs = {ending_signature(e) for e in endings}
    void = len(sigs) < 2          # 硬验收: ≥2种终局, 否则作废
    n_loss = sum(1 for e in endings if e['outcome'] == KO_LOSS)
    danger = [e for e in endings
              if e['outcome'] == KO_LOSS or e['my_hp_delta'] <= -danger_hp]
    my_d = [e['my_hp_delta'] for e in endings]
    op_d = [e['opp_hp_delta'] for e in endings]
    return {
        'branch': branch_name,
        'n': n,
        'void': void,
        'endings': endings,
        'stats': {
            'distinct_endings': len(sigs),
            'ko_loss_rate': round(n_loss / n, 3),
            'danger_rate': round(len(danger) / n, 3),
            'my_hp_delta_mean': round(sum(my_d) / n, 1),
            'opp_hp_delta_mean': round(sum(op_d) / n, 1),
            'my_worst': min(my_d),
        },
    }


def make_card(actual, alt, cfg):
    """危险显影卡字段(笔记§七): 人类条件标注列暂空(计划原文)."""
    return {
        'card': '反事实危险显影卡',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'situation': cfg['situation_desc'],
        'takeover': '原策略接管(temp=%.2f) — 风险①标注' % cfg['temp'],
        'random_sources': {
            'sampling_temp': cfg['temp'],
            'opponent_rotation': cfg['opponents'],
            'seed_formula': 'md5(局面|分支|副本序号)→ppo.rng',
            'n_sources_active': 2 + (1 if cfg['temp'] >= 0.5 else 0),
        },
        'danger_rule': '承伤≥%d 或 KO负 = 危险兑现' % cfg['danger_hp'],
        'actual': {'macro': cfg['actual_names'], **actual['stats']},
        'tempting_alternative': {
            'macro': cfg['alt_names'],
            **alt['stats'],
            'penalty_note': '危险兑现率与实际路线之差 = 替代的隐藏代价',
        },
        'human_condition': '(暂空 — 教学闭环阶段2接入)',
        'batch_validity': {
            'actual_void': actual['void'],
            'alt_void': alt['void'],
            'verdict': '作废重跑' if (actual['void'] or alt['void']) else '有效',
        },
        'per_replica_endings': {
            'actual': [{'i': e['i'], 'outcome': e['outcome'],
                        'my_d': e['my_hp_delta'], 'opp_d': e['opp_hp_delta'],
                        'seed': e['seed']} for e in actual['endings']],
            'alt': [{'i': e['i'], 'outcome': e['outcome'],
                     'my_d': e['my_hp_delta'], 'opp_d': e['opp_hp_delta'],
                     'seed': e['seed']} for e in alt['endings']],
        },
    }


# ---------------------------------------------------------------- mock续演
class MockEnv:
    """确定性mock续演 — 集成测试用(无游戏, 不占CPU).

    结果分布由(branch, 对手风格, 副本种子)决定:
      alt ×风格0(猛攻快照): 90% KO负 — 合成必败分支
      alt ×风格1(COM):      55% 大承伤
      actual×任意:          ~5% KO负, 其余小承伤 — 安全路线
    mode='degenerate'时恒返回同一终局(测作废路径)。
    """

    STYLES = ['pool_snapshot_aggro', 'com']

    def __init__(self, mode='normal'):
        self.mode = mode
        self.f = 0

    def replica(self, branch, style_idx, seed):
        import numpy as np
        rng = np.random.default_rng(seed)
        if self.mode == 'degenerate':
            return {'outcome': TIMEOUT, 'ko': False,
                    'my_hp_delta': -100, 'opp_hp_delta': -100,
                    'frames': 600}
        p_ko = 0.9 if (branch == 'alt' and style_idx == 0) else \
            (0.55 if branch == 'alt' else 0.05)
        if rng.random() < p_ko:
            d = 6000 + int(rng.random() * 3000)
            return {'outcome': KO_LOSS, 'ko': True,
                    'my_hp_delta': -min(d, 10000), 'opp_hp_delta': -200,
                    'frames': 300}
        d = (3200 + int(rng.random() * 1500)) if branch == 'alt' else \
            (300 + int(rng.random() * 500))
        return {'outcome': TIMEOUT, 'ko': False,
                'my_hp_delta': -d, 'opp_hp_delta': -(400 + d // 3),
                'frames': 600}


def run_mock(cfg):
    env = MockEnv(cfg.get('mock_mode', 'normal'))
    batches = {}
    for branch, names in (('actual', cfg['actual_names']),
                          ('alt', cfg['alt_names'])):
        def replica_fn(i, seed):
            style = i % len(MockEnv.STYLES)      # 随机源②轮换
            e = env.replica(branch, style, seed)
            e['opp_style'] = MockEnv.STYLES[style]
            return e
        batches[branch] = run_batch(replica_fn, cfg['n'],
                                    cfg['situation_id'], branch)
    return make_card(batches['actual'], batches['alt'], cfg)


# ---------------------------------------------------------------- 真实续演
def run_real(cfg):
    """真实模式: EvalEnv + SideDriver(接管者+对手轮换) — 与branch_demo同构.

    CPU红线纪律: 真实模式仅在舰队空闲时人工启动, 本函数不做自动重试。
    """
    import struct
    from soku_client2 import (GameEnded, OPCODE_SET_HEALTH,   # noqa: F401
                              OPCODE_SET_POSITION, OPCODE_SET_WEATHER)
    from side_driver import EvalEnv, SideDriver
    from portmap import reserved_port

    scen = cfg['scenario_dict']
    env = EvalEnv(reserved_port('danger_reveal'),
                  char_left=cfg['char'], char_right=cfg['char'],
                  vs_com=False, tps=None)
    print('排干intro...')
    for _ in range(240):
        try:
            if env.step(dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        except Exception:
            break

    store = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
    me = SideDriver(cfg['char'], 'L')
    me.load(os.path.join(store, 'model_ppo_%s.npz' % cfg['char']))
    opp_drivers = []
    for spec in cfg['opponents']:
        if spec.startswith('pool:'):
            ch = spec.split(':')[1]
            d = SideDriver(ch, 'R')
            d.load(os.path.join(store, 'model_ppo_%s_pool.npz' % ch))
        elif spec == 'com':
            d = SideDriver(cfg['char'], 'R', com_difficulty='hard')
        else:
            raise SystemExit('对手规格未知: %s' % spec)
        # P1-6(审计#6残余): 对手驱动的对家=me(cfg['char']) — pool/com 两
        # 规格的安全角色身份都已知且同源(COM=同角色), 不是猜 ID。
        d.set_opponent(cfg['char'])
        opp_drivers.append((spec, d))
    assert len(opp_drivers) >= 2, '对手规格须≥2风格(风险②稻草人)'
    try:   # P2(从零#4): env已建 — 之后任意路径finally关连接

        def setup(sc):
            lx, ly, rx, ry = sc['pos']
            env.inst._send(struct.pack('<BHH', OPCODE_SET_HEALTH,
                                       sc['hp'][0], sc['hp'][1]))
            env.inst._send(struct.pack('<B4f', OPCODE_SET_POSITION,
                                       lx, ly, rx, ry))
            if sc.get('weather') is not None:
                env.inst._send(struct.pack('<BH', OPCODE_SET_WEATHER,
                                           sc['weather']))
            for _ in range(60):
                env.step(dict(NEUTRAL), dict(NEUTRAL))

        batches = {}
        for branch, names in (('actual', cfg['actual_names']),
                              ('alt', cfg['alt_names'])):
            fl = build_macro_script(cfg['char'], names)
            script_fn = mk_input(fl)
            cfg['macro_frames'] = len(fl)

            def replica_fn(i, seed, _sf=script_fn, _br=branch):
                return _real_replica(env, me, opp_drivers, scen, setup,
                                     _sf, _br, i, seed, cfg)
            batches[branch] = run_batch(replica_fn, cfg['n'],
                                        cfg['situation_id'], branch,
                                        danger_hp=cfg['danger_hp'])
    finally:
        # P2修(从零#4): 原close只裹自身 — run_batch/make_card中途抛出
        # =env泄漏; finally保证任意路径关连接
        try:
            env.close()
        except Exception:
            pass
    return make_card(batches['actual'], batches['alt'], cfg)


def _real_replica(env, me, opp_drivers, scen, setup, script_fn, branch,
                  i, seed, cfg):
    """单副本真实续演: 设局→强制宏窗口→原策略接管→KO/超时."""
    import numpy as np
    from soku_client2 import GameEnded

    me.ppo.rng = np.random.default_rng(seed)               # 随机源①③
    opp_name, opp = opp_drivers[i % len(opp_drivers)]      # 随机源②
    # P1-6(审计#6残余): 对手风格逐副本轮换 → me 的对手角色必须随**本副本
    # 实际对家**注入(与训练侧逐局对手注入同分布); pool:<ch>→ch, com→同角色。
    _opp_char = (opp_name.split(':', 1)[1] if opp_name.startswith('pool:')
                 else cfg['char'])
    me.set_opponent(_opp_char)
    me.reset_match()
    opp.reset_match()
    setup(scen)
    my0 = op0 = None
    outcome, ko = TIMEOUT, False
    opp_inp = {}
    f = 0
    left = right = {'hp': 0}
    try:
        for f in range(cfg['frames']):
            if f < cfg['macro_frames']:
                my_inp = script_fn(f) or {}                # 强制偏离窗口
            else:
                my_inp = {}                                # 接管窗口(见下)
            r = env.step(my_inp, opp_inp)
            if r is None:
                break
            left, right = r[0], r[1]
            if my0 is None:
                my0, op0 = left['hp'], right['hp']
            # 原策略接管(强制宏放完): 接管者=me(rng已按种子播种)
            if f >= cfg['macro_frames']:
                try:
                    my_inp_n = me.frame_input(
                        left, right, r[2] if len(r) > 2 else {},
                        r[3] if len(r) > 3 else [], [])
                    if my_inp_n:
                        r2 = env.step(my_inp_n, opp_inp)
                        if r2 is None:
                            break
                        left, right = r2[0], r2[1]
                except Exception:
                    pass
            try:
                opp_inp = opp.frame_input(
                    right, left, r[2] if len(r) > 2 else {},
                    r[3] if len(r) > 3 else [], []) or {}
            except Exception:
                opp_inp = {}
            if left['hp'] <= 0:
                outcome, ko = KO_LOSS, True
                break
            if right['hp'] <= 0:
                outcome, ko = KO_WIN, True
                break
    except GameEnded as e:
        w = getattr(e, 'winner', None)
        outcome = KO_LOSS if w != 0 else KO_WIN
        ko = True
        left, right = {'hp': 0}, {'hp': 0}
    my_d = (left['hp'] - my0) if my0 is not None else 0
    op_d = (right['hp'] - op0) if op0 is not None else 0
    return {'outcome': outcome, 'ko': ko,
            'my_hp_delta': my_d, 'opp_hp_delta': op_d,
            'frames': f, 'opp_style': opp_name}


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--mock-mode', default='normal',
                    choices=['normal', 'degenerate'])
    ap.add_argument('--char', default='reimu')
    ap.add_argument('--scenario', default='mid_range')
    ap.add_argument('--situation', default=None,
                    help='JSON局面文件(pos/hp/weather) — 覆盖模板')
    ap.add_argument('--actual', required=True, help='实际宏名, 逗号分隔')
    ap.add_argument('--alt', required=True, help='替代宏名, 逗号分隔')
    ap.add_argument('--opponents', default=None,
                    help='对手规格逗号分隔, 如 pool:reimu,com (≥2风格)')
    ap.add_argument('--n', type=int, default=20)
    ap.add_argument('--temp', type=float, default=0.7)
    ap.add_argument('--frames', type=int, default=900)
    ap.add_argument('--danger-hp', type=int, default=DANGER_HP_DEFAULT)
    ap.add_argument('--output', default=None)
    a = ap.parse_args()

    assert a.n >= 20, 'N≥20(计划验收下限)'
    assert a.temp >= 0.5, '采样温度≥0.5(随机源①)'

    if a.situation:
        sd = json.load(open(a.situation, encoding='utf8'))
        situation_desc = 'custom:' + os.path.basename(a.situation)
    else:
        from branch_demo import SCENARIOS
        sd = SCENARIOS[a.scenario]
        situation_desc = '%s(%s)' % (a.scenario, sd.get('desc', ''))

    cfg = {
        'char': a.char, 'scenario_dict': sd,
        'situation_id': '%s|%s|%s' % (a.char, a.scenario or 'custom',
                                      sd['pos']),
        'situation_desc': situation_desc,
        'actual_names': [s.strip() for s in a.actual.split(',')],
        'alt_names': [s.strip() for s in a.alt.split(',')],
        'opponents': [s.strip() for s in (a.opponents
                                          or 'pool:%s,com' % a.char).split(',')],
        'n': a.n, 'temp': a.temp, 'frames': a.frames,
        'danger_hp': a.danger_hp,
        'mock_mode': a.mock_mode,
    }

    card = run_mock(cfg) if a.mock else run_real(cfg)
    out = a.output or os.path.join(
        HERE, 'danger_reveal_%s%s.json' % (
            'mock_' if a.mock else '', time.strftime('%Y%m%d_%H%M%S')))
    with open(out, 'w', encoding='utf8') as fp:
        json.dump(card, fp, ensure_ascii=False, indent=1)
    print('报告:', out)
    print('实际路线 : 危险率%.0f%% 终局%d种%s' % (
        card['actual']['danger_rate'] * 100,
        card['actual']['distinct_endings'],
        ' [作废!]' if card['batch_validity']['actual_void'] else ''))
    print('替代路线 : 危险率%.0f%% 终局%d种%s' % (
        card['tempting_alternative']['danger_rate'] * 100,
        card['tempting_alternative']['distinct_endings'],
        ' [作废!]' if card['batch_validity']['alt_void'] else ''))
    print('裁决:', card['batch_validity']['verdict'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
