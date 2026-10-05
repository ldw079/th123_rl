# -*- coding: utf-8 -*-
"""R61w(C5)行为测试: ender菜单 — 起手通过后策略选终结技."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from macro_executor import (advance_queue, make_ender_step,
                            starter_ender_pair, build_ender_menu)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def st(opp_untech=0, opp_a=0):
    return (
        {"action": 0, "hp": 10000, "spirit": 1000,
         "position.x": 500.0, "airBorne": False, "hitStop": 0},
        {"action": opp_a, "hp": 10000,
         "position.x": 600.0, "airBorne": False,
         "untech": opp_untech},
    )


GUARD_IDS = frozenset(range(150, 167)) - {158}


def noop():
    pass


def fake_sc(left):
    return False, False, {}


class FakeLib:
    def __init__(self, names, macros):
        self.names = names
        self.macros = macros


def main():
    # 1. make_ender_step 基本构造
    step = make_ender_step([3, 7, 12])
    check("ender步构造", step[0] == "ender" and step[1] == [3, 7, 12])

    # 2. executor遇到ender步 → 清队+返回信号
    l, r = st()
    q = [make_ender_step([1, 2])]
    q2, gf, dn, inp = advance_queue(
        q, 0, l, r, 0, 0, False, 1000, 100, "连段A",
        set(), GUARD_IDS, fake_sc, noop)
    check("ender清队", len(q2) == 0 and gf == 0)
    check("ender返回信号", isinstance(inp, tuple)
          and inp[0] == "ender" and inp[1] == [1, 2])

    # 3. starter_ender_pair 生成
    lib = {
        "names": ["待机", "5A", "连段A·地面", "连段A·版边", "连段A·空"],
        "macros": [
            ("待机", [((), 10)]),
            ("5A", [(("A",), 8)]),
            ("连段A·地面", [(("A",), 6), (("A",), 6)]),
            ("连段A·版边", [(("right", "A"), 8)]),
            ("连段A·空", [(("up",), 6), (("down", "A"), 10)]),
        ]}
    starter_script = [(("A",), 8), ((), 2)]
    s, _enders = starter_ender_pair(
        "连段A·起手", starter_script,
        ["连段A·地面", "连段A·版边", "连段A·空"], lib)
    check("起手宏生成", s is not None and s[0] == "连段A·起手")
    check("起手含confirm", any(k == "confirm" for k, _ in s[1]))
    check("起手含ender", any(k == "ender" for k, _ in s[1]))
    ender_step = next((k, v) for k, v in s[1] if k == "ender")
    check("ender索引正确", ender_step[1] == [2, 3, 4])

    # 4. build_ender_menu 批量生成
    starters = [
        ("起手A", [(("A",), 8)]),
        ("起手B", [(("down", "A"), 8)]),
    ]
    menu = build_ender_menu(lib, starters,
                            ["连段A·地面", "连段A·空"])
    check("菜单两个起手", len(menu) == 2)
    check("全部含ender", all(
        any(k == "ender" for k, _ in script)
        for _, script in menu))

    # 5. 不存在的ender名被过滤
    s2, e2 = starter_ender_pair("test", starter_script,
                                ["不存在的宏"], lib)
    check("无效ender返回None", s2 is None and e2 == [])

    # 6. 空ender列表返回None
    s3, _ = starter_ender_pair("test2", starter_script, [], lib)
    check("空ender返回None", s3 is None)

    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
