# -*- coding: utf-8 -*-
"""R61n(C4): 表里择成对宏+压起身套件 — 三现役角色.

表里择(mixup): 同一前置动作, 中段/下段二择 — 对手防御方向猜错即中.
  攻略核心: "择的本质是让对手无法同时防两个方向"
  实现: 前冲(同一动画)→中段(6A/3A系) vs 前冲→下段(2A/2B系)

压起身(okizeme): 对手倒地起身的压制套路.
  攻略核心: "起身有无敌帧, 但无敌结束瞬间是最大破绽"
  实现: 三种时机(即攻/延迟/空攻)覆盖不同起身选项
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

# ===== 表里择成对宏 =====
# 格式: (宏名, 脚本) — 前置动作完全一致, 最终攻击方向不同
# 对手视角: 看到前冲→无法预判中段还是下段→50/50猜防

MIXUP_MACROS = {
    'reimu': [
        # 中段择: 前冲→6A(站立防) — 空中 overhead 属性
        ("择·中段", [
            (("right", "D"), 6),      # 前冲(同一动画, ≥5帧预置)
            ((), 2),                   # 制造停顿(择的时机)
            (("right",), 6),           # 前走一小步(虚晃, ≥5帧)
            (("right", "A"), 10),     # 6A = 中段攻击
        ]),
        # 下段择: 前冲→2A(蹲防) — 地面 low 属性
        ("择·下段", [
            (("right", "D"), 6),      # 前冲(同一动画)
            ((), 2),                   # 同一停顿
            (("right",), 6),           # 同一虚晃
            (("down",), 6),            # 蹲下(最后一刻才变, ≥5帧)
            (("down", "A"), 10),      # 2A = 下段攻击
        ]),
        # 投技择: 前冲→投(A+D) — 防御不能, 拆投10F窗
        ("择·投", [
            (("right", "D"), 6),
            ((), 2),
            (("right",), 6),
            (("A", "D"), 6),          # 投技
        ]),
    ],
    'marisa': [
        ("择·中段", [
            (("right", "D"), 6),
            ((), 2),
            (("right",), 6),
            (("right", "A"), 10),
        ]),
        ("择·下段", [
            (("right", "D"), 6),
            ((), 2),
            (("right",), 6),
            (("down",), 6),
            (("down", "A"), 10),
        ]),
        ("择·投", [
            (("right", "D"), 6),
            ((), 2),
            (("right",), 6),
            (("A", "D"), 6),
        ]),
    ],
    'suika': [
        ("择·中段", [
            (("right", "D"), 6),
            ((), 2),
            (("right",), 6),
            (("right", "A"), 12),
        ]),
        ("择·下段", [
            (("right", "D"), 6),
            ((), 2),
            (("right",), 6),
            (("down",), 6),
            (("down", "A"), 12),
        ]),
        ("择·投", [
            (("right", "D"), 6),
            ((), 2),
            (("right",), 6),
            (("A", "D"), 6),
        ]),
    ],
}

# ===== 压起身套件 =====
# 对手倒地→起身的压制: 三种时机+三种攻击类型
# 起身无敌约4F, 无敌结束后是最大破绽(攻略: "起身读み")

OKIZEME_MACROS = {
    'reimu': [
        # 即攻(meaty): 对手起身瞬间已命中 — 对手按攻击则被打康
        ("压起身·即", [
            (("down", "A"), 12),      # 2A持续帧长, 覆盖起身无敌
            ((), 4),                   # 硬直
            (("A",), 8),              # 5A追击
        ]),
        # 延迟攻: 对手起身后再打 — 对手防了则打防, 对手跳则打空
        ("压起身·延迟", [
            ((), 8),                   # 等待起身
            (("A",), 10),             # 5A
            ((), 2),
            (("down", "A"), 10),     # 2A二择
        ]),
        # 空攻: 跳跃攻击打逆 — 蹲防不能, 须站防或升龙
        ("压起身·空", [
            (("up",), 6),             # 跳(非攻击方向, 不受预置门)
            (("down",), 6),           # 下方向(≥5帧)
            (("down", "A"), 12),     # j2A = 空中下攻(overhead)
        ]),
        # 起身穿: 向后穿人(逃脱压制)
        ("压起身·穿", [
            (("left", "D"), 6),      # 后结界
            ((), 4),
            (("left",), 8),          # 后退
        ]),
    ],
    'marisa': [
        ("压起身·即", [
            (("down", "A"), 12),
            ((), 4),
            (("A",), 8),
        ]),
        ("压起身·延迟", [
            ((), 8),
            (("A",), 10),
            ((), 2),
            (("down", "A"), 10),
        ]),
        ("压起身·空", [
            (("up",), 6),
            (("down",), 6),
            (("down", "A"), 12),
        ]),
        ("压起身·穿", [
            (("left", "D"), 6),
            ((), 4),
            (("left",), 8),
        ]),
    ],
    'suika': [
        ("压起身·即", [
            (("down", "A"), 14),
            ((), 4),
            (("A",), 10),
        ]),
        ("压起身·延迟", [
            ((), 10),
            (("A",), 12),
            ((), 2),
            (("down", "A"), 12),
        ]),
        ("压起身·空", [
            (("up",), 6),
            (("down",), 6),
            (("down", "A"), 14),
        ]),
        ("压起身·穿", [
            (("left", "D"), 6),
            ((), 4),
            (("left",), 8),
        ]),
    ],
}


def integrate(char):
    """向角色宏库末位追加表里择+压起身宏+类别集更新。"""
    import re
    fpath = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'macros', ('%s.py' % char)
        if char != 'reimu' else '__init__.py')
    src = open(fpath, encoding='utf8').read()

    # 找到宏变量名
    if char == 'reimu':
        var = 'MACROS'
    else:
        m = re.search(r'(MACROS_[A-Z_]+)\s*=', src)
        var = m.group(1)

    mixup = MIXUP_MACROS[char]
    oki = OKIZEME_MACROS[char]
    all_new = mixup + oki
    names = [n for n, _ in all_new]

    # 角色对应的类别集变量名(三现役命名各不同)
    if char == 'reimu':
        melee_var = 'MELEE_MACROS'
        combo_var = 'COMBO_MACROS'
        names_var = 'MACRO_NAMES'
    else:
        _u = char.upper()
        melee_var = 'MELEE_MACROS_%s' % _u
        combo_var = 'COMBO_MACROS_%s' % _u
        names_var = 'MACRO_NAMES_%s' % _u

    with open(fpath, 'a', encoding='utf8') as f:
        f.write('\n# ==== R61n(C4): 表里择+压起身套件 ====\n')
        for name, script in all_new:
            steps = []
            for k, fr in script:
                steps.append('(%r, %d)' % (tuple(k), fr))
            f.write('%s.append((%r, [%s]))\n' % (var, name, ', '.join(steps)))
        all_names_str = ', '.join(repr(n) for n in names)
        f.write('%s |= {%s}\n' % (melee_var, all_names_str))
        f.write('%s |= {%s}\n' % (combo_var, all_names_str))
        f.write('%s = [m[0] for m in %s]\n' % (names_var, var))
        # 规范化追加的宏(追加发生在文件末尾=规范化步骤之后)
        f.write('# R61n: 追加宏的规范化(预置帧≥5 — hitlab标定阈值)\n')
        f.write('%s[-%d:] = [(n, _norm_presteps(sc)) for n, sc in %s[-%d:]]\n'
                % (var, len(all_new), var, len(all_new)))
        f.write('%s = [m[0] for m in %s]\n' % (names_var, var))
        # N_MACROS同步(追加前已计算, 不随append走)
        if char == 'reimu':
            n_var = 'N_MACROS'
        else:
            n_var = 'N_MACROS_%s' % char.upper()
        f.write('%s = len(%s)\n' % (n_var, var))

    print('%s: +7宏(择3+压4) → %s' % (char, os.path.basename(fpath)))


def main():
    for char in ('reimu', 'marisa', 'suika'):
        integrate(char)
    print('--- 3角色×7宏 = 21条 ---')


if __name__ == '__main__':
    main()
