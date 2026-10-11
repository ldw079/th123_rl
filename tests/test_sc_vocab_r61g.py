# -*- coding: utf-8 -*-
"""R61g(B1)行为测试: SC词汇入BC匹配器(M2里程碑组件)。
1. 匹配器: 含sc:步的宏可被专家SC按压匹配(原结构性排除=SC标签恒0%);
2. sc:步展开为纯SC位时间线(朝向无关);
3. expert_bits 8元组含SC位(AandB→SC经battle_to_trainer);
4. resolve_sc_label: 手牌选中位→具体卡宏; 无匹配/空手返None(丢行)。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

sys.path.insert(0, r'D:\temp\soku_arch')
from bc_match import (StreamMatcher, expert_bits, inp_bits,  # noqa: E402
                      macro_timelines, sc_press_bits)
from bc_build import resolve_sc_label  # noqa: E402
from train_tm import _parse_sc_targets  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


# 合成宏库: 两个SC宏(sc:200/sc:201) + 一个普通宏 + 待机
MACROS = [
    ("5A", [(("A",), 4), ((), 6)]),
    ("卡·测试甲", [("sc:200", 0)]),
    ("卡·测试乙", [("sc:201", 0)]),
    ("待机", [((), 30)]),
]


def main():
    # 1. sc:步展开
    tl = macro_timelines(MACROS, mirror=False)
    sc_tl = tl[1][1]                       # full timeline of 卡·测试甲
    check("sc:步可展开", sc_tl is not None
          and len(sc_tl) == len(sc_press_bits()))
    check("sc时间线=纯SC位", sc_tl == sc_press_bits()
          and sc_tl[0][6] is True and sc_tl[0][5] is False)

    # 2. 匹配器: 专家SC按压命中SC宏
    m = StreamMatcher(MACROS, threshold=0.85)
    neutral = inp_bits({})                 # (0,0,F,F,F,F,F,F)
    scframe = inp_bits({"SC": True})
    # 专家流: 60帧intro + 待机20 + SC按压4 + 待机20
    stream = [neutral] * 80 + [scframe] * 4 + [neutral] * 20
    # 需要battle编码u16: 卡键=battle侧AandB位(bit8),
    # battle_to_trainer把它映射为trainer SC位(input_codec:197)
    AAND_B_BIT = 1 << 8
    u16s = [AAND_B_BIT if f[6] else 0 for f in stream]
    facings = [1] * len(stream)
    hits = m.walk(u16s, facings)
    sc_hit = [h for h in hits if MACROS[h[1]][0].startswith("卡·")]
    check("SC按压被匹配", len(sc_hit) >= 1,
          "hits=%s" % [(h[0], MACROS[h[1]][0]) for h in hits])
    check("SC命中帧≈80", sc_hit and 78 <= sc_hit[0][0] <= 82,
          "帧=%s" % (sc_hit[0][0] if sc_hit else -1))

    # 3. expert_bits 8元组(AandB battle位→SC trainer位)
    eb = expert_bits(AAND_B_BIT)
    check("expert_bits含SC位", len(eb) == 8 and eb[6] is True,
          str(eb))
    eb2 = expert_bits(1 << 4)              # battle A位(bit4)
    check("expert_bits A位独立", len(eb2) == 8 and eb2[2] is True
          and eb2[6] is False)

    # 4. 具体卡解析
    tgts = _parse_sc_targets(MACROS)
    idx_by_name = {m[0]: i for i, m in enumerate(MACROS)}
    # 手牌: 选中=200(卡·测试甲), 第2张=201
    hand = bytes([200, 1, 201, 2, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
    r = resolve_sc_label(tgts, idx_by_name, hand)
    check("选中200→卡·测试甲", r == 1, "idx=%s" % r)
    hand2 = bytes([201, 2, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
    r2 = resolve_sc_label(tgts, idx_by_name, hand2)
    check("选中201→卡·测试乙", r2 == 2, "idx=%s" % r2)
    hand3 = bytes([0xFF] * 10)
    check("空手→None(丢行)", resolve_sc_label(tgts, idx_by_name, hand3)
          is None)
    hand4 = bytes([199, 1, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
    check("未知卡199→None(空表优于错表)",
          resolve_sc_label(tgts, idx_by_name, hand4) is None)

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
