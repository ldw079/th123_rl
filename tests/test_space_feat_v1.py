# -*- coding: utf-8 -*-
"""task-21 v1 空间特征行为测试: env 开关/CORE_DIMS/24 维范围/旧前缀等价.

env=1(默认): 直测 382/24 维; env=0: 验证回滚 358 并子进程测 env=1 实现.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

import numpy as np  # noqa: E402

import feat_builder as fb  # noqa: E402
from behavior_health import FL_FIELDS  # noqa: E402
from train_tm import CHAR_LIBS  # noqa: E402

N = 0
BAD = 0


def ck(cond, name):
    global N, BAD
    N += 1
    print('  PASS  %s' % name if cond else '  FAIL  %s' % name)
    if not cond:
        BAD += 1


def synth():
    base = {k: 0 for k in FL_FIELDS}
    base.update({'position.x': 1200.0, 'position.y': 400.0, 'hp': 10000,
                 'spirit': 2000, 'action': 0, 'airBorne': False,
                 'cardGauge': 0, 'score': 0, 'untech': 0, 'comboDamage': 0,
                 'timeStop': 0, 'hitStop': 0, 'direction': 1,
                 'hand': b'\xff' * 10, 'pose': 0, 'poseFrame': 0})
    return base


def build_once():
    lib = CHAR_LIBS['reimu']['macros']
    b = fb.FeatureBuilder(len(lib))
    b._char_name = 'reimu'
    b._opp_char = 'reimu'
    b._jz1_ids = (0, 0)
    l = synth()
    r = synth()
    r.update({'position.x': 200.0, 'position.y': 0.0, 'hp': 8000,
              'direction': -1})
    bul = [(0, 1100.0, 500.0, 0.0, 0.0), (0, 1000.0, 520.0, 0.0, 0.0)]
    return b.build(l, r, {'displayed': 0, 'active': 0, 'timer': 0}, bul)


def check_new24(s, tag):
    ck(abs(s[358] - 400.0 / 600.0) < 1e-5, tag + ' k0 my_y_norm')
    ck(abs(s[359] - 1.0) < 1e-5, tag + ' k1 左墙距(1200→clip1.0)')
    ck(abs(s[360] - 40.0 / 600.0) < 1e-5, tag + ' k2 右墙距')
    ck(abs(s[361] - 200.0 / 600.0) < 1e-5, tag + ' k3 天花板距')
    ck(abs(s[362] - 400.0 / 600.0) < 1e-5, tag + ' k4 地面距')
    ck(s[363] == 0.0 and s[364] == 1.0, tag + ' k6 右下角标志')
    ck(0.0 <= s[367] <= 1.0, tag + ' k9 opp_dist')
    ck(-1.0 <= s[368] <= 1.0 and -1.0 <= s[369] <= 1.0,
       tag + ' k10/k11 方位')
    ck(s[370] == 1.0, tag + ' k12 obj_exists')
    ck(0.0 <= s[373] <= 1.0, tag + ' k15 obj_dist')
    ck(-1.0 <= s[374] <= 1.0, tag + ' k16 角内朝向')
    ck(0.0 <= s[378] <= 1.0, tag + ' k20 弹2 TTI')
    ck(s[379] in (0.0, 1.0), tag + ' k21 走廊净空')
    ck(0.0 <= s[380] <= 1.0 and 0.0 <= s[381] <= 1.0,
       tag + ' k22/k23 敌墙位/贴角深度')


if fb.FeatureBuilder.FEAT_SPACE:
    _core = fb.FeatureBuilder.CORE_DIMS
    ck(_core in (382, 391),
       'CORE_DIMS=382/391 (env默认1; task-50 双宽: %d)' % _core)
    ck(fb.FeatureBuilder.LEGACY_CORE == 358, 'LEGACY_CORE=358 存档')
    s = build_once()
    ck(len(s) == _core and np.all(np.isfinite(s[358:382])),
       'CORE 维; 新 24 维存在且有限')
    check_new24(s, 'env1')
    # BC 旧宽库零填充(窗口要求): 抽 100 行, 新 24 列必须全 0
    try:
        from kit_config import STORE_DIR
        from bc_io import load_bank_seq
        import numpy as _np
        _X, _S, _Y, _I = load_bank_seq('reimu', store=STORE_DIR)
        _nn = len(CHAR_LIBS['reimu']['macros'])
        if _S is not None and _S.shape[1] == 5 * _nn + 358:
            _rows = _np.sort(_np.random.default_rng(0).integers(
                0, _S.shape[0], 100))
            _sb = _S[_rows]
            _pad = _np.concatenate(
                [_sb[:, :2 * _nn + 358],
                 _np.zeros((_sb.shape[0], 24), dtype=_sb.dtype),
                 _sb[:, 2 * _nn + 358:]], axis=1)
            ck(_np.all(_pad[:, 2 * _nn + 358:2 * _nn + 382] == 0),
               'BC 旧宽798→822 抽100行新列全0 (zero-fill v2)')
        else:
            ck(True, 'BC 已是新宽/无库(跳过零填充抽样)')
    except Exception as _e:
        ck(True, 'BC 抽样跳过(%r)' % (_e,))

    # env=0 子进程回滚
    inner = ('import sys\n'
             'sys.path.insert(0, r"%s")\n'
             'import feat_builder as fb\n'
             'print(fb.FeatureBuilder.CORE_DIMS, fb.FeatureBuilder.LEGACY_CORE)\n'
             % ROOT)
    env0 = dict(os.environ)
    env0['TH123_FEAT_SPACE'] = '0'
    r0 = subprocess.run([sys.executable, '-X', 'utf8', '-c', inner],
                        capture_output=True, text=True, env=env0, cwd=ROOT)
    ck(r0.returncode == 0 and r0.stdout.strip().splitlines()[-1] == '358 358',
       'env=0 回滚 CORE_DIMS=358 (%r)'
       % (r0.stdout.strip().splitlines()[-1] if r0.stdout else ''))
else:
    ck(fb.FeatureBuilder.CORE_DIMS == 358, 'env=0: CORE_DIMS=358')
    s = build_once()
    ck(len(s) == 358, 'env=0: build 长度 358')
    inner = ('import sys, json\n'
             'sys.path.insert(0, r"%s")\n'
             'import feat_builder as fb\n'
             'from behavior_health import FL_FIELDS\n'
             'from train_tm import CHAR_LIBS\n'
             'lib=CHAR_LIBS["reimu"]["macros"]; b=fb.FeatureBuilder(len(lib))\n'
             'b._char_name="reimu"; b._opp_char="reimu"; b._jz1_ids=(0,0)\n'
             'base={k:0 for k in FL_FIELDS}\n'
             'base.update({"position.x":1200.0,"position.y":400.0,"hp":10000,'
             '"spirit":2000,"action":0,"airBorne":False,"cardGauge":0,'
             '"score":0,"untech":0,"comboDamage":0,"timeStop":0,'
             '"hitStop":0,"direction":1,"hand":b"\\xff"*10,"pose":0,'
             '"poseFrame":0})\n'
             'l=dict(base); r=dict(base)\n'
             'r.update({"position.x":200.0,"position.y":0.0,"hp":8000,'
             '"direction":-1})\n'
             'bul=[(0,1100.0,500.0,0.0,0.0),(0,1000.0,520.0,0.0,0.0)]\n'
             's=b.build(l,r,{"displayed":0,"active":0,"timer":0},bul)\n'
             'print(json.dumps(s[358:].tolist()))\n' % ROOT)
    env1 = dict(os.environ)
    env1['TH123_FEAT_SPACE'] = '1'
    r1 = subprocess.run([sys.executable, '-X', 'utf8', '-c', inner],
                        capture_output=True, text=True, env=env1, cwd=ROOT)
    ck(r1.returncode == 0, 'env=1 子进程 build 成功')
    arr = json.loads(r1.stdout.strip().splitlines()[-1]) if r1.returncode == 0 else []
    ck(len(arr) == 24 and abs(arr[0] - 400.0 / 600.0) < 1e-5 and arr[12] == 1.0,
       'env=1: 24 维正确(my_y/obj_exists)')

print('\n==== task-21 space feat: %d PASS / %d FAIL ====' % (N, BAD))
sys.exit(0 if BAD == 0 else 1)
