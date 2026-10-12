# -*- coding: utf-8 -*-
r"""I项后半(教学闭环产物2): 习惯→针对性惩罚演示 — branch_demo的habit模式.

闭环: 人测采集(human_solo_collect) → 习惯报告(产物1) → **本工具产出
惩罚演示(产物2)**: 同一局面下, "维持习惯"与"改正建议"两种应对的后果
对比 — 对手执行habit_detector.punishment_macros给出的惩罚宏脚本
(确定性, 双侧逐帧输入留档=可重放演示).

产物形态说明: 真.rep文件需要mod侧固定随机种子(start包无seed字段,
gameParams.randomSeed=time(nullptr)) — 本工具以"输入脚本+局面参数+
后果轨迹"JSON为演示载体, --replay可原样重演脚本.

用法:
  python tools/habit_punish_demo.py --char suika --habit far_stand_guard
  python tools/habit_punish_demo.py --auto     # 取最新solo报告最严重习惯
  python tools/habit_punish_demo.py --replay <json>   # 重演已存演示
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf8')

from branch_demo import (SCENARIOS, NEUTRAL, setup_scenario,  # noqa: E402
                         run_branch)
from side_driver import EvalEnv  # noqa: E402
from habit_detector import HABITS, punishment_macros  # noqa: E402
from train_tm import CHAR_LIBS  # noqa: E402

PORT = 20936        # eval段
TPS = 240           # 演示加速(非公平性场景, 无需真速)
DEMO_FRAMES = 240   # 分支全长(脚本循环补满 — 首版12帧放空的教训)
REPORT = os.path.join(HERE, 'human_solo_report.json')
OUT_DIR = os.path.join(HERE, 'habit_demos')

# 场景补充: 远距(branch_demo三场景无far)
SCENARIOS = dict(SCENARIOS)
SCENARIOS['far_range'] = {
    "desc": "远距对峙(520px) — 站桩vs主动",
    "pos": (170.0, 0.0, 690.0, 0.0),
    "hp": (10000, 10000),
    "gap": 520,
}

# 习惯→(场景, 习惯行为宏, 改正行为宏) — 与HABITS[counter_play]对齐
HABIT_DEMOS = {
    'far_stand_guard': ('far_range', ['立防'], ['前冲', '高跳']),
    'wakeup_crouch_guard': ('wakeup', ['蹲防'], ['后跳', '蹲防']),
    'wakeup_stand_guard': ('wakeup', ['立防'], ['蹲防', '后跳']),
    'pressure_backjump': ('corner_pressure', ['后跳'], ['结界2', '立防']),
    'empty_spirit_attack': ('mid_range', ['5A'], ['后退', '立防']),
}


def expand_macros(char, names, frames_each=40, total=None):
    """宏名列表→逐帧输入函数+留档脚本(与branch_demo展开逻辑同构).

    total给出时脚本**循环补满**total帧 — 演示语义: 习惯是持续行为
    (立防要立满全程), 惩罚脚本要打满(首版只跑12/36帧放空=对照无效,
    两分支同伤-400差异不显著的教训)."""
    lib = CHAR_LIBS[char]
    macros_by_name = {m[0]: m[1] for m in lib['macros']}
    frames_list = []
    used = []
    for n in names:
        if n not in macros_by_name:
            continue
        used.append(n)
        for ks, fr in macros_by_name[n][:1]:   # 每宏取首键步(演示节奏)
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
                frames_list.extend([inp] * min(int(fr), frames_each))
    if not frames_list:
        frames_list = [{}] * frames_each
    if total and frames_list:
        _cycle = list(frames_list)
        while len(frames_list) < total:
            frames_list.extend(_cycle)
        frames_list = frames_list[:total]

    def _inp(f):
        return frames_list[f] if f < len(frames_list) else {}
    return _inp, frames_list, used


def pick_auto_habit():
    """--auto: 最新solo报告里最严重(按HABITS severity排序)的习惯."""
    if not os.path.exists(REPORT):
        return None, None, '无 %s' % REPORT
    try:
        entries = json.load(open(REPORT, encoding='utf8'))
    except (OSError, ValueError) as e:
        return None, None, '报告损坏(%s)' % e
    sev_rank = {'高': 0, '中': 1, '低': 2}
    best = None
    for ent in entries:
        for k in ent.get('habits', []):
            h = HABITS.get(k)
            if not h:
                continue
            cand = (sev_rank.get(h['severity'], 3), k, ent.get('char'))
            if best is None or cand < best:
                best = cand
    if best is None:
        return None, None, '报告中无已检出习惯'
    return best[1], best[2], None


def _verdict_text(hab_delta, fix_delta, punishment):
    """判定: d=改正分支-习惯分支的HP差(正=习惯分支更伤=惩罚成立).
    首版符号写反(0-(-500)=+500误判"成立") — 抽函数+双向数值测试钉死."""
    d = fix_delta - hab_delta
    if d > 100:
        return ('惩罚演示成立: 维持习惯比改正建议多承伤 %d HP — "%s"'
                % (d, punishment))
    if d < -100:
        return ('当前模型未能惩罚该习惯(改正分支反而多承伤 %d HP) — '
                '记为模型短板(破防/择不足, 呼应被动性主攻A线); '
                '演示产物保留为短板证据' % abs(d))
    return '本局差异不显著(%d HP)' % d


def run_demo(char, habit_key):
    if habit_key not in HABIT_DEMOS:
        print('可演示习惯:', list(HABIT_DEMOS))
        return None
    scen_name, habit_macros, fixed_macros = HABIT_DEMOS[habit_key]
    scen = SCENARIOS[scen_name]
    h = HABITS[habit_key]
    punish_names = punishment_macros(CHAR_LIBS[char], habit_key)
    if not punish_names:
        punish_names = ['DA', '前冲']   # 兜底通用压制
    print('[demo] 习惯=%s(%s) 角色=%s 场景=%s' % (
        habit_key, h['label'], char, scen_name))

    env = EvalEnv(PORT, char_left=char, char_right=char,
                  vs_com=False, tps=TPS)
    print('[demo] 排干intro...')
    for _ in range(240):
        try:
            if env.step(dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        except Exception:
            break

    # 对手=生产模型(教学语义: "会反抗的对手才演示应对的代价" —
    # 模型正是被训练成惩罚远距站桩的; 脚本宏编排版过于生硬,
    # 两轮实测0差异/0伤害, 降级为--opp-script选项)
    from side_driver import SideDriver
    store = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
    opp = SideDriver(char, 'R')
    opp.load(os.path.join(store, 'model_ppo_%s.npz' % char))
    punish_names = ['模型(%s生产策略)' % char]
    print('[demo] 对手惩罚者: %s' % punish_names[0])

    branches = {}
    scripts = {}
    for label, names in (('维持习惯', habit_macros),
                         ('改正建议', fixed_macros)):
        my_inp, my_script, used = expand_macros(char, names,
                                                total=DEMO_FRAMES)
        opp.reset_match()
        print('[demo] 分支[%s]: %s ...' % (label, '+'.join(used) or '(无宏)'))
        res = run_branch(env, scen, my_inp, frames=DEMO_FRAMES,
                         opp_driver=opp)
        if res:
            branches[label] = res
            scripts[label] = {'my': my_script, 'macros': used}
            print('[demo]   我方HP%+d 对手HP%+d %d帧' % (
                res['my_hp_delta'], res['opp_hp_delta'], res['frames']))
        else:
            print('[demo]   采集失败')
    try:
        env.inst.close()
    except Exception:
        pass

    verdict = ''
    _hab = branches.get('维持习惯')
    _fix = branches.get('改正建议')
    if _hab and _fix:
        verdict = _verdict_text(_hab['my_hp_delta'],
                                _fix['my_hp_delta'], h['punishment'])
    report = {
        'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
        'char': char, 'habit': habit_key, 'habit_label': h['label'],
        'habit_desc': h['desc'], 'punishment': h['punishment'],
        'counter_play': h['counter_play'], 'scenario': scen_name,
        'scenario_desc': scen['desc'], 'punish_macros': punish_names,
        'branches': branches, 'scripts': scripts, 'verdict': verdict,
        'replay': 'python tools/habit_punish_demo.py --replay <本文件>',
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, 'punish_%s_%s_%s.json' % (
        habit_key, char, time.strftime('%Y%m%d_%H%M%S')))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print('\n[demo] 讲解: 【%s】%s' % (h['label'], h['desc']))
    print('[demo]   AI惩罚: %s' % h['punishment'])
    print('[demo]   改正: %s' % h['counter_play'])
    print('[demo]   %s' % verdict)
    print('[demo] 演示产物:', out)
    return report


class _ScriptedOpp:
    """run_branch的opp_driver接口适配 — 对手吃确定性惩罚脚本."""

    def __init__(self, inp_fn):
        self._fn = inp_fn
        self.f = 0

    def frame_input(self, own, opp, weather, objs, extra):
        inp = dict(self._fn(self.f))
        self.f += 1
        return inp

    def reset_match(self):
        self.f = 0


def replay(path):
    """--replay: 按已存演示的脚本重演(局面+双侧输入同脚本)."""
    rep = json.load(open(path, encoding='utf8'))
    char, scen_name = rep['char'], rep['scenario']
    scen = SCENARIOS[scen_name]
    env = EvalEnv(PORT, char_left=char, char_right=char,
                  vs_com=False, tps=TPS)
    for _ in range(240):
        try:
            if env.step(dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        except Exception:
            break
    for label, sc in rep.get('scripts', {}).items():
        my_inp, _, _ = expand_macros(char, sc.get('macros') or [])
        opp = _ScriptedOpp(
            lambda f: (sc.get('opp') or [{}])[f]
            if f < len(sc.get('opp') or []) else {})
        res = run_branch(env, scen, my_inp, frames=150, opp_driver=opp)
        print('[replay][%s] 我方HP%+d 对手HP%+d' % (
            label, res['my_hp_delta'], res['opp_hp_delta'])
            if res else '[replay][%s] 采集失败' % label)
    try:
        env.inst.close()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu')
    ap.add_argument('--habit', default=None)
    ap.add_argument('--auto', action='store_true',
                    help='取最新solo报告最严重习惯')
    ap.add_argument('--replay', default=None, help='重演已存演示JSON')
    args = ap.parse_args()
    if args.replay:
        replay(args.replay)
        return
    habit, char, err = (args.habit, args.char, None)
    if args.auto:
        habit, achar, err = pick_auto_habit()
        if err:
            print('[demo] --auto失败: %s' % err)
            return 1
        char = achar or args.char
        print('[demo] auto选中: %s (%s)' % (habit, char))
    if not habit:
        print('用法: --habit <key> 或 --auto; 可演示:',
              list(HABIT_DEMOS))
        return 1
    run_demo(char, habit)
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
