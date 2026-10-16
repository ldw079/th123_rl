# -*- coding: utf-8 -*-
"""审计2026-10-14合入门槛: rep→宏映射往返对抗测试集.

P0回归(极性反转): 方向互斥对 — 指定轴wild时前进/后退互相吞,
待机→跳跃, 左右移→后跳, 2B/6B/j2B→5B, 6C→5C。
核心门槛: **全库往返** — 每个宏的脚本合成为输入流, 匹配器必须
找回该宏自己(标签在命中列表中)。任何掩码/平局规则回退都会在此爆红。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

sys.path.insert(0, r'D:\temp\soku_arch')
from bc_match import StreamMatcher                    # noqa: E402
from train_tm import CHAR_LIBS                        # noqa: E402

PASS, FAIL = [], []
# battle位(input_codec实证): bit0=up bit1=down bit2=left bit3=right
# bit4-7=A,B,C,D bit8=AandB→trainer SC
BATTLE = {'up': 1 << 0, 'down': 1 << 1, 'left': 1 << 2, 'right': 1 << 3,
          'A': 1 << 4, 'B': 1 << 5, 'C': 1 << 6, 'D': 1 << 7,
          'SC': 1 << 8}


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def script_to_u16(script):
    """宏脚本→battle u16帧列表(穿门合成完整hit路脚本 — 裁定一
    门后窥视/线A分支门都需要全脚本案例试确认路径; sc:=3帧SC脉冲;
    branch走hit路由, link走门后步骤)."""
    out = []
    for ks, fr in script:
        if isinstance(ks, str):
            if ks.startswith('sc:'):
                out.extend([BATTLE['SC']] * 3)
                continue
            if ks.startswith(('confirm', 'cconfirm')):
                continue              # 穿门: 门后步骤照常合成
            if ks == 'branch' and isinstance(fr, dict):
                if fr.get('hit'):
                    out.extend(script_to_u16(fr['hit']))
                continue
            if ks == 'link' and isinstance(fr, (tuple, list)) \
                    and len(fr) == 2:
                out.extend(script_to_u16(fr[1]))
                continue
            break
        v = 0
        for k in ks:
            v |= BATTLE[k]
        out.extend([v] * int(fr))
    return out


def run_stream(m, frames_u16, mirror=False):
    facings = [-1 if mirror else 1] * len(frames_u16)
    return m.walk(frames_u16, facings, intro_frames=2)


def synth(lib_macros, name, pre=60, post=25):
    """宏名→合成流(中性+宏输入+中性), 返回(流, 宏起始帧).

    待机等全中性宏无输入变化→无决策点, 前置一个B脉冲制造dp。
    """
    script = dict(lib_macros)[name]
    body = script_to_u16(script)
    if not any(body):
        pre_frames = [0] * (pre - 6) + [BATTLE['B']] * 3 + [0] * 3
        return pre_frames + body + [0] * post, len(pre_frames)
    n = [0] * pre + body + [0] * post
    return n, pre


# 审计P2已知同形组(输入域不可分, 组内归属即算往返通过):
AMBIG_GROUPS = [
    {'连段A', '连段B', '连段C', '版边连A'},
    {'5A', '5A确认'},
    {'2A', '2A确认', 'TM·2a连'},
    {'jA', '空连A'},
    {'后退', '立防'},          # 审计续③: 按住后=走后=立防, 仅对手攻击态可分
]
# SC卡族: 按键形态全同(具体卡由bc_build手牌差分解析) — 按前缀归组
SC_GROUP = {'卡·当前'}         # 占位: group_of动态并入所有'卡·'宏


def group_of(nm, all_names=None):
    if nm.startswith('卡·'):
        return {n for n in (all_names or []) if n.startswith('卡·')}
    for g in AMBIG_GROUPS:
        if nm in g:
            return g
    return {nm}


def main():
    lib = CHAR_LIBS['reimu']
    names = [m[0] for m in lib['macros']]
    m = StreamMatcher(lib['macros'], threshold=0.88)

    # ---- 方向互斥(P0极性) ----
    s = [0] * 60 + [BATTLE['right']] * 20 + [0] * 25
    lb = [names[h[1]] for h in run_stream(m, s)]
    check("右保持→前进系(非后退)", ('前进' in lb or '前冲' in lb)
          and '后退' not in lb and '后跳' not in lb, str(lb))
    s = [0] * 60 + [BATTLE['left']] * 20 + [0] * 25
    lb = [names[h[1]] for h in run_stream(m, s)]
    check("左保持→后退/立防(非前进)", ('后退' in lb or '立防' in lb)
          and '前进' not in lb, str(lb))
    s = [0] * 60 + [BATTLE['B']] * 5 + [0] * 60
    lb = [names[h[1]] for h in run_stream(m, s)]
    check("纯中性段→待机(非跳跃)", '待机' in lb and '跳跃' not in lb, str(lb))

    # ---- 审计混淆对: X→5B/5C错吞 ----
    for nm, good in (('2B', '2B'), ('6B', '6B'), ('6C', '6C'),
                     ('jB', 'jB')):
        if nm not in dict(lib['macros']):
            continue
        s, f0 = synth(lib['macros'], nm)
        lb = [names[h[1]] for h in run_stream(m, s)]
        check("%s往返不被5B/5C吞" % nm, good in lb
              and '5B' not in lb and '5C' not in lb, str(lb))

    # ---- P1升级(审计续②): 同帧按压型(方向+B同时, 无预压) ----
    s = [0] * 60 + [BATTLE['down'] | BATTLE['B']] * 8 + [0] * 25
    lb = [names[h[1]] for h in run_stream(m, s)]
    check("2B同帧按压→2B(非5B)", '2B' in lb and '5B' not in lb, str(lb))
    s = [0] * 60 + [BATTLE['right'] | BATTLE['B']] * 8 + [0] * 25
    lb = [names[h[1]] for h in run_stream(m, s)]
    check("6B同帧按压→6B(非5B)", '6B' in lb and '5B' not in lb, str(lb))

    # ---- 全库往返(核心门槛; 同形组按组内归属) ----
    n_ok = n_bad = 0
    bad = []
    for nm in names:
        s, f0 = synth(lib['macros'], nm)
        if len(s) - 85 < 3:          # 前缀<3帧: 匹配器下限, 结构性跳过
            continue
        hits = run_stream(m, s)
        g = group_of(nm, names)
        near = [h for h in hits
                if names[h[1]] in g and abs(h[0] - f0) <= 4]
        if near:
            n_ok += 1
        else:
            n_bad += 1
            lb = [names[h[1]] for h in hits]
            bad.append('%s→%s' % (nm, lb[:3]))
    check("全库往返≥90%% (%d/%d)" % (n_ok, n_ok + n_bad),
          n_bad <= (n_ok + n_bad) * 0.1, '漏: ' + '; '.join(bad[:6]))

    # ---- 裁定一(类甲): 门后窥视 ----
    # 连段B全脚本(门后DA) → 连段B; 连段C(门后2B) → 连段C
    for nm in ('连段B', '连段C', 'TM·2a连', '空连A'):
        if nm not in dict(lib['macros']):
            continue
        s, f0 = synth(lib['macros'], nm)
        hits = run_stream(m, s)
        near = [h for h in hits
                if names[h[1]] == nm and abs(h[0] - f0) <= 4]
        check("门后窥视:%s全脚本→自身" % nm, bool(near),
              str([(h[0], names[h[1]]) for h in hits]))
    # 裸2A(无门后延续) → 2A(回落基础宏, 不再被确认版吞)
    s, f0 = synth(lib['macros'], '2A')
    lb = [names[h[1]] for h in run_stream(m, s)]
    check("裸2A→2A(基础宏回落)", '2A' in lb, str(lb))
    # 短A戳无延续(连段前缀未确认) → 不再标连段A
    s = [0] * 60 + [BATTLE['A']] * 4 + [0] * 30
    lb = [names[h[1]] for h in run_stream(m, s)]
    check("未确认连段前缀→丢弃(非连段A)",
          all(nm not in lb for nm in ('连段A', '连段B', '连段C')),
          str(lb))
    # 2A确认(门后downB) → 2A确认
    s, f0 = synth(lib['macros'], '2A确认')
    lb = [names[h[1]] for h in run_stream(m, s)]
    check("2A确认(门后downB)→2A确认", '2A确认' in lb, str(lb))

    # ---- 镜像端往返抽样(流同步翻转H位) ----
    def flip_h(u):
        l, r = u & 0x4, u & 0x8
        return (u & ~0xC) | (r >> 1 if r else 0) | (l << 1 if l else 0)

    for nm in ('前进', '6B', '空翔前'):
        if nm not in dict(lib['macros']):
            continue
        s, f0 = synth(lib['macros'], nm)
        s = [flip_h(u) for u in s]
        hits = run_stream(m, s, mirror=True)
        g = group_of(nm, names)
        near = [h for h in hits
                if names[h[1]] in g and abs(h[0] - f0) <= 2]
        check("镜像往返:%s" % nm, bool(near),
              str([names[h[1]] for h in hits]))

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
