# -*- coding: utf- -*-
"""S-1 MyPunishTracker行为测试(合并终版方案2026-10-14第一波).

验收: 合成"连续跳跃被对空"→jump_punish_rate>0.6; 被防无伤=NEUTRAL
不计punish; 分类优先级; EMA单次结果不满格。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

from my_punish_tracker import (MyPunishTracker, classify,    # noqa: E402
                               PUNISHED, LANDED, WHIFFED, NEUTRAL)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def run_macro(t, cls, frames):
    """驱动一个宏: frames=[(d_take, opp_atk, d_deal, blocked)]。"""
    t.begin(cls)
    out = None
    for f in frames:
        t.frame(*f)
    return t.end()


def main():
    # 1. 合成验收: 连续跳跃被对空(10跳8punish)
    t = MyPunishTracker()
    for _ in range(10):
        out = run_macro(t, 'JUMP', [
            (0, False, 0, False), (600, True, 0, False),
            (0, True, 0, False)])
        assert out == PUNISHED
    check('连续跳跃被对空→jump_pr>0.6',
          t.punish_rate('JUMP') > 0.6, '%.2f' % t.punish_rate('JUMP'))

    # 2. 同期近战命中→melee不受牵连
    for _ in range(6):
        run_macro(t, 'MELEE', [(0, False, 0, False), (0, False, 500, False)])
    check('命中=LANDED不涨punish', t.punish_rate('MELEE') < 0.1,
          '%.2f' % t.punish_rate('MELEE'))

    # 3. 被防无伤=NEUTRAL(被防≠吃亏)
    t2 = MyPunishTracker()
    for _ in range(8):
        out = run_macro(t2, 'MELEE', [(0, False, 0, True)])
        assert out == NEUTRAL
    check('被防=NEUTRAL不计punish', t2.punish_rate('MELEE') == 0.0)

    # 4. 挥空=WHIFFED; EMA单次不满格(α=0.3)
    t3 = MyPunishTracker()
    run_macro(t3, 'BULLET', [(0, False, 0, False)] * 5)
    check('挥空=WHIFFED', t3.n_done['BULLET'] == 1)
    t3.begin('JUMP')
    t3.frame(800, True, 0)
    t3.end()
    check('单次punish(LE-3加速0.9)',
          abs(t3.punish_rate('JUMP') - 0.9) < 1e-9)

    # 5. 分类优先级与名集
    check('classify立防→GUARD_PREP', classify('立防') == 'GUARD_PREP')
    check('classify高跳→JUMP', classify('高跳') == 'JUMP')
    check('classify待机→OTHER', classify('待机') == 'OTHER')
    from train_tm import CHAR_LIBS
    lib = CHAR_LIBS['reimu']
    check('classify 5B→BULLET(lib)', classify('5B', lib) == 'BULLET')
    check('classify 623B→SKILL(lib)', classify('623B', lib) == 'SKILL')
    check('classify 5A→MELEE(lib)', classify('5A', lib) == 'MELEE')
    # 623B同时在skill与melee? 优先级bullet>skill>melee验序
    check('优先级: bullet先于skill',
          classify('236B', lib) == 'BULLET'
          and '236B' in lib['skill'])

    # 6. 主导类读数(S-2维10辅助)
    t4 = MyPunishTracker()
    for _ in range(5):
        run_macro(t4, 'JUMP', [(500, True, 0)])
    for _ in range(2):
        run_macro(t4, 'MELEE', [(0, False, 0)])
    check('主导类punish读数', abs(t4.my_dominant_punished() - 0.3 * (
        1 + 0.7 + 0.7**2 + 0.7**3 + 0.7**4)) < 1e-6 or
        t4.my_dominant_punished() > 0.5,
        '%.2f' % t4.my_dominant_punished())

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
