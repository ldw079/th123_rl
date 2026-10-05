# -*- coding: utf-8 -*-
"""R61c(主规划B5)势函数双修测试:
1. γ因子在位(GAMMA_POT=0.999, Ng式r'=γΦ(s')−Φ(s));
2. card_gauge覆盖参数(晴岚哨兵的值通道) — 覆盖时真值被完全忽略;
3. card项量级上限±2.0(与从零审计读数一致);
4. 势函数无动作依赖(同状态同值 — 可刷分不可能的性质)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

from train_tm import state_potential, GAMMA_POT, POT_W  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def st(gauge=1000, my_hp=10000, opp_hp=10000):
    return ({"hp": my_hp, "spirit": 1000, "cardGauge": gauge,
             "position.x": 600.0, "position.y": 0.0},
            {"hp": opp_hp, "spirit": 1000,
             "position.x": 700.0, "position.y": 0.0})


def main():
    check("γ=0.999在位", GAMMA_POT == 0.999, str(GAMMA_POT))
    # 覆盖通道: 真值9999, 覆盖0 → card项=0(真值被完全忽略)
    l, r = st(gauge=9999)
    p_override0 = state_potential(l, r, card_gauge_val=0)
    p_override2k = state_potential(l, r, card_gauge_val=2000)
    p_real = state_potential(l, r)
    check("覆盖完全生效", abs(p_real - p_override2k) < 1e-9,
          "real≈override2k(封顶)")
    check("覆盖隔离真值", abs((p_override2k - p_override0)
                              - POT_W['card_gauge'] * 2000) < 1e-9,
          "差=%.2f(=card项满幅2.0)" % (p_override2k - p_override0))
    # 量级上限: card项满幅=±2.0
    check("card项上限2.0", abs(POT_W['card_gauge'] * 2000 - 2.0) < 1e-9)
    # 无动作依赖: 同状态两次调用同值
    check("状态确定性", state_potential(l, r) == state_potential(l, r))
    # 高势驻留: γ<1使r'=γΦ−Φ<0(驻高势态微负漂移 — γ=1时恒0)
    phi = p_real
    check("驻高势态负漂移", GAMMA_POT * phi - phi < 0,
          "每帧%.4f(γ=1时=0)" % (GAMMA_POT * phi - phi))

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
