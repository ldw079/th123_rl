# -*- coding: utf-8 -*-
"""R61(用户2026-10-05裁定"d+鼓励快速胜利")奖励经济学行为测试:
1. 低段擦弹费率随局时衰减(0帧=0.01, 6000帧=0, 超饱和=0);
2. 拖时间收割死亡: 任意帧序列的低段累计收入硬上界≤0.01×6000/2=30
   (旧版10408帧局收+104低段 → suika实测收割);
3. 快胜奖金: 速决+6/回合, 半时+3, 顶满+0, 超时+0;
4. 正常局(前中期擦弹)收入几乎不受影响(3000帧内平均费率≥0.005)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

from train_tm import (graze_low_rate, fastwin_bonus,  # noqa: E402
                      ko_round_reward, R_KO_ROUND,
                      GRAZE_LOW_RATE, GRAZE_SAT_F, R_FASTWIN)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def main():
    # 1. 衰减形状
    check("费率@0帧=全额", graze_low_rate(0) == GRAZE_LOW_RATE)
    check("费率@半饱和=半额",
          abs(graze_low_rate(GRAZE_SAT_F / 2) - GRAZE_LOW_RATE / 2) < 1e-9)
    check("费率@饱和=0", graze_low_rate(GRAZE_SAT_F) == 0.0)
    check("费率@超饱和=0", graze_low_rate(99999) == 0.0)
    check("费率单调不增",
          all(graze_low_rate(f) >= graze_low_rate(f + 100) - 1e-12
              for f in range(0, 10000, 100)))

    # 2. 拖时间死亡: 最坏情况(每帧都擦弹)低段累计上界
    worst = sum(graze_low_rate(f) for f in range(0, 20000))
    check("低段硬上界≤30.1", worst <= GRAZE_LOW_RATE * GRAZE_SAT_F / 2 + 0.1,
          "最坏累计=%.1f (旧恒定版10408帧=104)" % worst)
    check("旧收割局收入砍半以上", worst < 50, "%.1f" % worst)

    # 3. 快胜奖金
    check("速决满额", fastwin_bonus(0) == R_FASTWIN,
          "+%.1f" % fastwin_bonus(0))
    check("半时半额",
          abs(fastwin_bonus(1860) - R_FASTWIN / 2) < 1e-9)
    check("顶满=0", fastwin_bonus(3720) == 0.0)
    check("超时=0", fastwin_bonus(9999) == 0.0)
    check("双回合胜叠加", fastwin_bonus(1000, 2) == 2 * fastwin_bonus(1000))

    # 4. 正常局影响小: 3000帧内平均费率≥半额
    avg = sum(graze_low_rate(f) for f in range(3000)) / 3000
    check("正常局平均费率≥0.005", avg >= GRAZE_LOW_RATE / 2,
          "avg=%.4f" % avg)

    # 5. R61b: KO时双方血量差(用户2026-10-05)
    # 胜侧: KO胜(opp≈0)与旧own-hp公式数值连续
    check("KO胜连续性(9000vs0)",
          abs(ko_round_reward(9000, 0, True)
              - R_KO_ROUND * (0.3 + 0.9)) < 1e-9,
          "%.1f" % ko_round_reward(9000, 0, True))
    # 顶时胜: 碾压>擦分险胜(新信号)
    _dom = ko_round_reward(6000, 1000, True)
    _chip = ko_round_reward(5000, 4900, True)
    check("顶时胜碾压>险胜", _dom > _chip + 2,
          "碾压%.1f vs 险胜%.1f" % (_dom, _chip))
    check("胜值域[3,13]", all(3.0 <= ko_round_reward(a, b, True) <= 13.0
                              for a, b in ((0, 0), (10000, 0),
                                           (5000, 4900), (10000, 9900))))
    # 败侧: 惜败半罚/碾压全罚(原恒-10)
    _close = ko_round_reward(100, 500, False)
    _stomp = ko_round_reward(0, 9000, False)
    check("惜败>碾压(半罚)", abs(_close - (-5.0)) < 0.5
          and abs(_stomp - (-9.5)) < 0.5,
          "惜败%.1f 碾压%.1f (旧恒-10)" % (_close, _stomp))
    check("败值域[-10,-5]必负",
          all(-10.0 <= ko_round_reward(a, b, False) <= -5.0
              for a, b in ((0, 10000), (100, 500), (5000, 0),
                           (3000, 3100))))
    # 胜负经济学不倒挂: 最惨胜(+3)仍优于最惜败(-5)
    check("最惨胜>最惜败", ko_round_reward(0, 0, True) > ko_round_reward(
        10000, 9999, False))

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
