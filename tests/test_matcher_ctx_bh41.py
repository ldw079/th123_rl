# -*- coding: utf-8 -*-
"""BH-4.1行为测试: matcher连段语境 — 按钮帧评分/攻击优先/中性抑制/
向后兼容(无语境=逐位不变)。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, r'D:\temp\soku_arch')
from bc_match import StreamMatcher  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


BIT = {'up': 1 << 0, 'down': 1 << 1, 'left': 1 << 2, 'right': 1 << 3,
       'A': 1 << 4, 'B': 1 << 5, 'C': 1 << 6, 'D': 1 << 7}


def u16(*keys):
    v = 0
    for k in keys:
        v |= BIT[k]
    return v


MACROS = [
    ("连段A", [(("A",), 4), ((), 2), (("A",), 4), ((), 2), (("A",), 4)]),
    ("5B", [(("B",), 10)]),
    ("待机", [((), 30)]),
    ("前进", [(("right",), 20)]),
    ("后退", [(("left",), 20)]),
]
ATK = {'连段A', '5B'}


def walk(stream, ctx=None, attack=ATK):
    m = StreamMatcher(MACROS, threshold=0.88, attack_names=attack)
    return m.walk(stream, [1] * len(stream), intro_frames=2,
                  combo_ctx=ctx)


def main():
    N = u16()

    # ===== 向后兼容: 无语境(attack_names=None或combo_ctx=None)逐位不变 =====
    # A连打流: 按A4-松2-按A4(连段A模式但夹微走位)
    # 构造: A×4 + right×3(微走位) + A×4
    stream1 = [u16('A')] * 4 + [u16('right')] * 3 + [u16('A')] * 4 \
        + [N] * 12
    base = walk(stream1, ctx=None)
    base2 = StreamMatcher(MACROS, threshold=0.88).walk(
        stream1, [1] * len(stream1), intro_frames=2)
    check('无attack_names向后兼容', sorted(base) == sorted(base2))

    # ===== 语境抑制: ctx内待机标签被丢弃, ctx外保留 =====
    # 流: 中性×4 + A×1(制造决策点) + 中性×30(松键点→待机标签)
    stream2 = [N] * 4 + [u16('A')] * 1 + [N] * 30
    no_ctx = walk(stream2, ctx=None)
    names_n = {MACROS[h[1]][0] for h in no_ctx}
    check('语境外待机标签正常', '待机' in names_n, str(names_n))
    ctx_all = [False] * len(stream2)
    in_ctx = walk(stream2, ctx=ctx_all)
    names_c = {MACROS[h[1]][0] for h in in_ctx}
    check('ctx=False不抑制(兼容)', '待机' in names_c)
    ctx_all[4] = True      # 按压点(帧4)
    ctx_all[5] = True      # 松键点(帧5) — 两决策点均落入语境
    in_ctx2 = walk(stream2, ctx=ctx_all)
    names_c2 = {MACROS[h[1]][0] for h in in_ctx2}
    check('ctx=True待机被抑制', '待机' not in names_c2, str(names_c2))

    # ===== attack_names=None → 语境全灭(开关语义) =====
    m_off = StreamMatcher(MACROS, threshold=0.88, attack_names=None)
    res_off = m_off.walk(stream2, [1] * len(stream2), intro_frames=2,
                         combo_ctx=[True] * len(stream2))
    check('attack_names=None语境全灭',
          any(MACROS[h[1]][0] == '待机' for h in res_off))

    # ===== 按钮帧评分: 语境内连段A(按钮序列对/夹微走位)胜纯走位 =====
    # 流: A×4 + right×3 + A×4 + N×10 — 语境外连段A满分10帧难全对
    # (夹了3帧right), 语境内按钮帧(8帧A)全对 → s_btn=1.0
    ctx3 = [False] * 6 + [True] * 15
    res3 = walk(stream1, ctx=ctx3)
    # 决策点4(right开始)在ctx[4]=False; 决策点7(A再按)ctx[7]=True
    hit_at = {h[0]: MACROS[h[1]][0] for h in res3}
    check('语境内按钮序列命中攻击类',
          any(n in ATK for n in hit_at.values()),
          str(hit_at))

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
