# -*- coding: utf-8 -*-
"""bc_match v3行为测试(A1-3③): 掩码位+变长截断 — 弹幕漏标根因的变异钉.

锚定语义:
1. 变长: 5帧干净B按压命中5B(v2定长10帧必丢)
2. 掩码: 漂移B(按住右+B)命中5B; 但2B的down必match(不被5B吞)
3. 严格面: B+C同按不命中5B(未指定按钮必False); v2回退路径仍可用
4. 消费: 连续5B→5C两次独立命中
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

sys.path.insert(0, r'D:\temp\soku_arch')
from bc_match import StreamMatcher, inp_bits  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


# battle u16位(input_codec实证): bit0=up,bit1=down,bit2=left,bit3=right,
# bit4-7=A,B,C,D; bit8=AandB→trainer SC
BIT = {'up': 1 << 0, 'down': 1 << 1, 'left': 1 << 2, 'right': 1 << 3,
       'A': 1 << 4, 'B': 1 << 5, 'C': 1 << 6, 'D': 1 << 7}


def u16(*keys):
    v = 0
    for k in keys:
        v |= BIT[k]
    return v


MACROS = [
    ("5B", [(("B",), 10)]),
    ("5C", [(("C",), 12)]),
    ("2B", [(("down",), 6), (("down", "B"), 10)]),
    ("6B", [(("right",), 6), (("right", "B"), 10)]),
    ("待机", [((), 30)]),
    ("立防", [(("left",), 12)]),
    ("后退", [(("left",), 6)]),
]

N = u16()          # 中性


def run(stream, mode='v3'):
    m = StreamMatcher(MACROS, threshold=0.88, mode=mode)
    facings = [1] * len(stream)
    return m.walk(stream, facings, intro_frames=2)


def labels(hits):
    return [MACROS[h[1]][0] for h in hits]


def main():
    # 1. 变长: 60中性 + B×5 + 中性
    s = [N] * 60 + [u16('B')] * 5 + [N] * 20
    lb = labels(run(s))
    # 后续中性等待合法标注为待机(build侧降采样), 断言收窄:
    # 首标签=5B且无误标
    check("变长5帧B按压→5B", lb and lb[0] == '5B', str(lb))
    check("v2同流丢弃(对照)", labels(run(s, mode='v2')) == [],
          str(labels(run(s, mode='v2'))))

    # 2. 前向B(right+B×6) — 6B跳过变体认领(输入域本属6B, 审计续②);
    #    后向漂移B(left+B×6)无4B宏 → 5B兜底(轴wild)
    s = [N] * 60 + [u16('right', 'B')] * 6 + [N] * 20
    lb = labels(run(s))
    check("前向B→6B(跳过变体)", lb and lb[0] == '6B', str(lb))
    s = [N] * 60 + [u16('left', 'B')] * 6 + [N] * 20
    lb = labels(run(s))
    check("后向漂移B→5B兜底", lb and lb[0] == '5B', str(lb))

    # 3. 2B的down必match: down×6 + down+B×8 → 2B(不被5B吞)
    s = [N] * 60 + [u16('down')] * 6 + [u16('down', 'B')] * 8 + [N] * 20
    lb = labels(run(s))
    check("2B(down必match)→2B", lb and lb[0] == '2B', str(lb))

    # 4. 严格面: B+C同按×5 — 5B未指定按钮C必False → 不命中
    s = [N] * 60 + [u16('B', 'C')] * 5 + [N] * 20
    lb = labels(run(s))
    check("B+C同按不命中5B", '5B' not in lb, str(lb))

    # 5. 消费与连续: B×4 → C×4 两弹幕各自命中(5B消费后5C仍独立命中)
    s = [N] * 60 + [u16('B')] * 4 + [u16('C')] * 4 + [N] * 20
    lb = labels(run(s))
    check("连续5B→5C双命中", lb[:2] == ['5B', '5C'], str(lb))

    # 6. 镜像: 镜像端"前向"=left — left+B命中6B(mirror约束翻转)
    m = StreamMatcher(MACROS, threshold=0.88)
    s = [N] * 60 + [u16('left', 'B')] * 6 + [N] * 20
    hits = m.walk(s, [-1] * len(s), intro_frames=2)
    lb = labels(hits)
    check("镜像前向B→6B", lb and lb[0] == '6B', str(lb))

    # 7. 空键步=真中性: 纯left保持(无按钮)不得被待机吞掉 —
    #    15帧保持应命中立防(L=12更长)而非待机(方向wild首版bug)
    s = [N] * 60 + [u16('left')] * 15 + [N] * 20
    lb = labels(run(s))
    check("地面后保持→立防(非待机)", lb and lb[0] == '立防', str(lb))
    # 短后保持→后退/立防(输入同型, 宏序决胜 — 皆防御性标签即可)
    s = [N] * 60 + [u16('left')] * 4 + [N] * 20
    lb = labels(run(s))
    check("短后保持→防御类(非待机)",
          lb and lb[0] in ('后退', '立防'), str(lb))
    # 真中性→待机(攻击后回中性, 中性段命中待机)
    s = [N] * 60 + [u16('A')] * 4 + [N] * 30
    lb = labels(run(s))
    check("攻击后中性→含待机", '待机' in lb, str(lb))

    # 8. P1-6(从零#4): 左朝向门后延续 — families按朝向分套后,
    #    左朝向(facings=-1)全脚本必须确认自身(原硬编码mirror=False
    #    使左朝向段系统性错标; 修法首版的循环尾mirror残留亦在此暴露)
    from train_tm import CHAR_LIBS as _CL
    _lib = _CL['reimu']
    _names = [mm[0] for mm in _lib['macros']]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_bc_roundtrip_audit as _rta
    for nm in ('连段B', '连段C', '空连A'):
        if nm not in _names:
            continue
        s2, _f02 = _rta.synth(_lib['macros'], nm)
        # 左朝向=流同步翻H位(roundtrip flip_h同源) + facings=-1
        def _flip_h(u):
            l, r = u & 0x4, u & 0x8
            return (u & ~0xC) | (r >> 1 if r else 0) | (l << 1 if l else 0)
        s2m = [_flip_h(u) for u in s2]
        m2 = StreamMatcher(_lib['macros'], threshold=0.88)
        lb2 = [_names[h[1]] for h in m2.walk(s2m, [-1] * len(s2m),
                                             intro_frames=2)]
        check("左朝向门后延续:%s→自身" % nm, nm in lb2, str(lb2))
        m3 = StreamMatcher(_lib['macros'], threshold=0.88)
        lb3 = [_names[h[1]] for h in m3.walk(s2, [1] * len(s2),
                                             intro_frames=2)]
        check("右朝向对称:%s→自身" % nm, nm in lb3, str(lb3))

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
