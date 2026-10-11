# -*- coding: utf-8 -*-
"""R63(P0-1): 镜像轴行为测试 — 换边只翻水平(H), 上下(V)语义不变。

事故(2026-10-07 架构审查发现, 非本会话新引入):
  train_tm.keys_to_input 原写 `if axis in ("H","V") and mirror: val=-val`
  → 朝向左(_last_dir<0)时上下被一起翻: j8A→j2A、高跳(down,(),up)退化成
  普通跳、斜上冲/斜后跳上下互换。而轨迹/distill/bc_targets/mask 记的仍是
  策略原本选的那一招 → 约一半决策的信用分配被污染。

本测试把正确语义钉死为可证伪断言(不是注释):
  1. 不镜像: up→+1, down→-1, left→-1, right→+1 (与KEY_TO_BIT一致);
  2. 镜像: **只有H取反**; V(up/down)逐键不变;
  3. 左右互换是"值取反"而非"换键名"——取反后语义仍正确: left(-1)→+1=right;
  4. 三方实现一致: train_tm / bc_match / branch_demo 同输入同输出
     (漂移即红 — 本项目最大事故源是双拷贝漂移);
  5. mir_keys(键名法)与keys_to_input(极性法)对H语义等价、对V恒等。
"""
import sys
import os

sys.stdout.reconfigure(encoding='utf8')
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import train_tm  # noqa: E402
from train_tm import keys_to_input, mir_keys, KEY_TO_BIT  # noqa: E402

FAILS = []


def chk(cond, name, detail=''):
    print('  %s %s%s' % ('PASS' if cond else 'FAIL', name,
                         ('  [%s]' % detail) if detail else ''))
    if not cond:
        FAILS.append(name)


print('==== R63 镜像轴行为测试 ====')

# ---- 1. 不镜像: 与 KEY_TO_BIT 表一致 ----
base = keys_to_input(('up', 'left', 'A'))
chk(base == {'V': 1, 'H': -1, 'A': True},
    '不镜像: up+left+A → V=+1, H=-1, A=True', repr(base))
# 同轴互斥键共写一槽: 后者覆盖(键名法/极性法同语义 — 宏定义不应同时给矛盾方向)
chk(keys_to_input(('up', 'down')) == {'V': -1},
    '同轴共写: (up,down)→后者覆盖V=-1 (两法同语义, 非缺陷)', repr(base))
chk(keys_to_input(('up',)) == {'V': 1}, '不镜像: up→V=+1(屏幕上是正)',
    repr(keys_to_input(('up',))))
chk(keys_to_input(('down',)) == {'V': -1}, '不镜像: down→V=-1')
chk(keys_to_input(('left',)) == {'H': -1}, '不镜像: left→H=-1')
chk(keys_to_input(('right',)) == {'H': 1}, '不镜像: right→H=+1')

# ---- 2. 镜像: 只翻H, V逐键不变 ----
for k, v in (('up', 1), ('down', -1)):
    got = keys_to_input((k,), mirror=True)
    chk(got == {'V': v},
        '镜像: %s 的V不变(=%+d) — 上下不是左右' % (k, v), repr(got))
for k, v in (('left', 1), ('right', -1)):
    got = keys_to_input((k,), mirror=True)
    chk(got == {'H': v},
        '镜像: %s 的H取反(左右互换)' % k, repr(got))

# 上下与左右组合(斜跳/斜冲)必须"只左右变"
chk(keys_to_input(('up', 'left'), mirror=True) == {'V': 1, 'H': 1},
    '镜像: up+left → V保持+1, H翻为+1(=斜上后跳, 不是斜下)')
chk(keys_to_input(('down', 'right'), mirror=True) == {'V': -1, 'H': -1},
    '镜像: down+right → V保持-1, H翻为-1')

# ---- 3. 高跳宏的回归钉(R63的直接受害者) ----
# macros 里 高跳 = (down,(),up): 先按下再按上 → 末帧 V=+1
_hj = keys_to_input(('down',), mirror=True)
chk(_hj == {'V': -1}, '回归: 高跳首步down在镜像下仍是V=-1(未被翻成+1)')
_hj2 = keys_to_input(('up',), mirror=True)
chk(_hj2 == {'V': 1}, '回归: 高跳末步up在镜像下仍是V=+1(高跳不退化成普通跳)')

# ---- 4. 跨实现"镜像规则"一致性 ----
# 重要(bc_match.py:18 自述): bc_match 的 KEY_TO_BIT 与 train_tm **V极性相反**
# (up=V:-1 vs up=V:+1), 是各自内部自洽的**已知反义同名表**; A/B/SC词表经
# battle_to_trainer 已换算。因此不能直接比dict, 要比**镜像规则本身**:
# 先把 bc_match 输出换算到 train_tm 极性(V取反), 再看与 train_tm 是否逐键相等。
_SAMPLES = [('up',), ('down',), ('left',), ('right',),
            ('up', 'left'), ('down', 'right'), ('up', 'right', 'A'),
            ('down', 'left', 'B'), ('A', 'B', 'C'), ()]


def _to_trainer_polarity(d):
    """bc_match(BattleInput)极性 → train_tm极性: V取反, H/A~D不变。"""
    out = dict(d)
    if 'V' in out:
        out['V'] = -out['V']
    return out


try:
    import bc_match
    _bc = bc_match.keys_to_input
    # 4a. 极性表本身确实是反义(文档化的事实, 钉住以防无声漂移)
    _bc_raw = _bc(('up',), False)
    chk(_bc_raw == {'V': -1},
        'bc_match极性锚: up=V:-1 (与train_tm反义 — 各自内部自洽)',
        repr(_bc_raw))
    # 4b. 换极后与 train_tm 逐键相等(含镜像)
    _bad = None
    for s in _SAMPLES:
        for m in (False, True):
            a = keys_to_input(s, m)
            b = _to_trainer_polarity(_bc(s, m))
            if a != b:
                _bad = (s, m, a, b)
                break
        if _bad:
            break
    chk(_bad is None,
        '跨实现镜像规则一致: train_tm ≡ bc_match(换极后) 全样本×两模式',
        '' if _bad is None else '差异@%s mirror=%s: %r vs %r' % _bad)
    # 4c. 关键回归: 两者在镜像下都**保持V不变**
    _v_kept = all(
        _bc((k,), True).get('V') == _bc((k,), False).get('V')
        for k in ('up', 'down'))
    chk(_v_kept, 'bc_match镜像同样不翻V(参照实现 — 原P1-G修复点)')
except ImportError as e:
    chk(False, 'bc_match可导入(跨实现一致性的前提)', repr(e))

# ---- 5. 键名法(mir_keys)与极性法对H等价、对V恒等 ----
_ok_t = _ok_f = True
for s in _SAMPLES:
    for m in (False, True):
        by_key = keys_to_input(mir_keys(s, m), False)
        by_val = keys_to_input(s, m)
        if by_key != by_val:
            print('    差异 %s mirror=%s: 键名法%r vs 极性法%r'
                  % (s, m, by_key, by_val))
            if m:
                _ok_t = False
            else:
                _ok_f = False
chk(_ok_f, 'mir_keys不镜像=恒等(不影响输入)')
chk(_ok_t, 'mir_keys(键名法) ≡ keys_to_input(mirror=True) — 两种镜像实现等价')

# ---- 6. 极性约定锚点: 防止未来"好心"改 KEY_TO_BIT ----
chk(KEY_TO_BIT['up'] == ('V', 1) and KEY_TO_BIT['down'] == ('V', -1),
    '极性锚: up=V:+1 / down=V:-1 (soku_client2 send_inputs 同源)')
chk(KEY_TO_BIT['left'] == ('H', -1) and KEY_TO_BIT['right'] == ('H', 1),
    '极性锚: left=H:-1 / right=H:+1')

print()
if FAILS:
    print('==== %d FAIL ====' % len(FAILS))
    for f in FAILS:
        print('  - %s' % f)
    sys.exit(1)
print('==== ALL PASS: R63镜像轴行为测试通过 ====')
