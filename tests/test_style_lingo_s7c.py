# -*- coding: utf-8 -*-
"""S-7C风格语言投影行为测试(合并终版方案).

describe_style: 跳频/射击/稳健度/漂移/资源依赖各轴语义;
style_advice: 对应提示; 边界(不足75维/None).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

from style_lingo import describe_style, style_advice   # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def feats(jump=0.0, bullet=0.0, guard=0.3, attack=0.3, drift=0.0,
          low_guard=1.0, low_attack=0.0):
    f = [0.0] * 75
    f[0], f[1] = guard, attack
    f[8] = jump
    f[13] = bullet
    f[20] = drift
    base_low = 21 + 40
    f[base_low], f[base_low + 1] = low_guard, low_attack
    return f


def main():
    # 轴语义
    check('频繁起跳', '频繁起跳' in describe_style(feats(jump=10)))
    check('很少起跳', '很少起跳' in describe_style(feats(jump=0.5)))
    check('弹幕压制型', '弹幕压制型' in describe_style(feats(bullet=20)))
    check('近身缠斗型', '近身缠斗型' in describe_style(feats(bullet=1)))
    check('稳健防御', '稳健防御' in describe_style(
        feats(guard=0.8, attack=0.2)))
    check('激进压制', '激进压制' in describe_style(
        feats(guard=0.1, attack=0.9)))
    check('风格多变', '风格多变' in describe_style(feats(drift=0.8)))
    check('低灵仍激进', '低灵仍激进' in describe_style(
        feats(low_guard=0.2, low_attack=0.8)))
    # 均衡默认(跳频取适中区间1.5-8)
    d = describe_style(feats(jump=3.0, bullet=6.0))
    check('均衡措辞', '起跳适中' in d and '风格稳定' in d, d)
    # 提示
    a = style_advice(feats(jump=10))
    check('对空提示', '对空' in a, a)
    a2 = style_advice(feats(bullet=20))
    check('穿弹提示', 'GRAZE' in a2 or '高跳' in a2, a2)
    check('无特征不出提示', style_advice(feats()) == '')
    # 边界
    check('None→风格未知', describe_style(None) == '风格未知')
    check('短数组→风格未知', describe_style([0.0] * 10) == '风格未知')

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
