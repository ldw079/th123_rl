# -*- coding: utf-8 -*-
"""CE-5阶段一离线探针行为测试 — S'手术语义钉死:
仅改距离位(其余逐位保真)/方向规范/饱和守卫/射程块同式。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from counterfactual_probe import (C_ADX, C_ADXBAND, C_DX, C_OPPCORNER,
                                  C_OWNBAND, C_OWNCORNER, C_OX, C_OXI,
                                  recover_positions, surgery)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


N = 88
CORE = 358


def mk_S(own_x, dx, seed=3):
    """合成侧向量: 距离锚位真值, 其余随机(改没改一眼可辨)。"""
    rng = np.random.default_rng(seed)
    S = rng.standard_normal((1, 5 * N + CORE)).astype(np.float32) * 0.3
    c = 2 * N
    S[0, c + C_OX] = own_x / 620.0
    S[0, c + C_OXI] = 1.0 - own_x / 620.0
    S[0, c + C_DX] = np.clip(dx / 600.0, -1, 1)
    S[0, c + C_ADX] = np.clip(abs(dx) / 600.0, 0, 1)
    # 随机覆盖带位避免全零歧义
    S[0, c + C_OWNBAND:c + C_OWNBAND + 3] = 0.9
    S[0, c + C_ADXBAND:c + C_ADXBAND + 4] = 0.9
    S[0, c + C_OPPCORNER] = 0.9
    S[0, c + C_OWNCORNER] = 0.9
    return S


def main():
    reach = np.zeros(N, dtype=np.float32)
    reach[:10] = 120.0                       # 前10宏有射程
    rmask = (reach > 0).astype(np.float32)

    # 1. 位置恢复round-trip
    own_x, dx = recover_positions(mk_S(400.0, 150.0)[0, 2 * N:2 * N + CORE])
    check('位置恢复', abs(own_x - 400) < 1e-3 and abs(dx - 150) < 1e-3)

    # 2. 手术: 仅改距离位(其余逐位保真)
    S = mk_S(400.0, 150.0)
    Sp = surgery(S.copy(), 1.0, 100.0, 20.0, reach, rmask, N)
    check('手术不返回None', Sp is not None)
    c = 2 * N
    # 新dx = 150 + 100 - 20 = 230; own_x2 = 420
    check('dx更新', abs(float(Sp[0, c + C_DX]) - 230.0 / 600.0) < 1e-5)
    check('adx更新', abs(float(Sp[0, c + C_ADX]) - 230.0 / 600.0) < 1e-5)
    check('own_x带更新', abs(float(Sp[0, c + C_OX]) - 420.0 / 620.0) < 1e-5
          and abs(float(Sp[0, c + C_OXI]) - (1 - 420.0 / 620.0)) < 1e-5)
    # own_x2=420 → 带1(350-850); adx=230 → 带1(130-250)
    check('own位置带one-hot', Sp[0, c + C_OWNBAND + 1] == 1.5
          and Sp[0, c + C_OWNBAND + 0] == 0.0
          and Sp[0, c + C_OWNBAND + 2] == 0.0)
    check('adx带one-hot', Sp[0, c + C_ADXBAND + 1] == 1.5
          and Sp[0, c + C_ADXBAND + 0] == 0.0
          and Sp[0, c + C_ADXBAND + 2] == 0.0
          and Sp[0, c + C_ADXBAND + 3] == 0.0)
    # opp_x2 = 420+230 = 650 → 不贴角; own 420 → 不贴角
    check('贴角标志重算', Sp[0, c + C_OPPCORNER] == 0.0
          and Sp[0, c + C_OWNCORNER] == 0.0)
    # 射程块: clip((230-reach)/200)*mask
    exp = np.clip((230.0 - reach) / 200.0, -1, 1) * rmask
    got = Sp[0, c + CORE:c + CORE + N]
    check('射程差块同式', np.allclose(got, exp.astype(np.float32), atol=1e-6))
    # 其余维度逐位保真(收集手术改动的全部索引)
    touched = (set(c + i for i in (C_DX, C_ADX, C_OX, C_OXI))
               | set(range(c + C_OWNBAND, c + C_OWNBAND + 3))
               | set(range(c + C_ADXBAND, c + C_ADXBAND + 4))
               | {c + C_OPPCORNER, c + C_OWNCORNER}
               | set(range(c + CORE, c + CORE + N)))
    other = [i for i in range(S.shape[1]) if i not in touched]
    check('非距离位逐位保真', np.array_equal(S[0, other], Sp[0, other]))

    # 3. 入角路由验证: 大推板把对手推进右角 → 贴角标志翻1.5
    # own=600 dx=30(opp=630), push=510 → dx2=540, opp2=1140>1120 ✓
    # (own须<620否则位置饱和; 注释留推导账)
    S3 = mk_S(600.0, 30.0)
    Sp3 = surgery(S3.copy(), 1.0, 510.0, 0.0, reach, rmask, N)
    c3 = 2 * N
    check('推入右角→opp贴角', Sp3[0, c3 + C_OPPCORNER] == 1.5)

    # 4. 方向规范: sign=-1(对手在我左)推板量同样远离自己(dx更负)
    S4 = mk_S(500.0, -200.0)                 # opp在左(300)
    Sp4 = surgery(S4.copy(), -1.0, 100.0, 0.0, reach, rmask, N)
    check('sign=-1推离', abs(float(Sp4[0, c + C_DX]) + 300.0 / 600.0) < 1e-5)

    # 5. 饱和守卫: own_x≥620(clip=1) → None
    S5 = mk_S(620.0, 100.0)
    check('own饱和→None', surgery(S5.copy(), 1.0, 50, 0,
                                  reach, rmask, N) is None)
    # dx饱和(≥600) → None
    S6 = mk_S(400.0, 600.0)
    check('dx饱和→None', surgery(S6.copy(), 1.0, 50, 0,
                                 reach, rmask, N) is None)

    print('\n%d PASS / %d FAIL' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
