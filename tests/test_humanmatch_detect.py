# -*- coding: utf-8 -*-
"""task-15(2026-10-19) 人测通路行为测试: 0x34C 角色识别 + 活档加载链 + probe.

覆盖(离线, 不碰游戏):
  1. map_char_id: 20 角色 CHAR_LIBS id → 名; 未知/越界/None → None(不猜);
  2. _ckpt_guard: 真活档通过; 伪旧代(旧宏数/旧宽度)拒绝并给原因;
  3. resolve_model: live坏→pool seed好 的回退顺序 + tried 记录;
     全候选不兼容 → SystemExit(响亮拒绝, 禁静默/禁自动迁移);
  4. model_stamp 含 path/mtime(报告可溯源字段);
  5. 源码锚: 0x34C/0x350 + char_ids + live_model_path + set_opponent(p1c)
     + --probe-chars / --detect-only + probe 只读(不载模型)路径存在。
"""
import io
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.stdout.reconfigure(encoding='utf8')

import numpy as np  # noqa: E402

import human_match_v2 as hm  # noqa: E402
from feat_builder import FeatureBuilder  # noqa: E402
from kit_config import STORE_DIR, live_model_path  # noqa: E402
from train_tm import CHAR_LIBS, TMTrainer  # noqa: E402

N = 0
BAD = 0


def ck(cond, name):
    global N, BAD
    N += 1
    if cond:
        print('  PASS  %s' % name)
    else:
        BAD += 1
        print('  FAIL  %s' % name)


# ---- 1) id→名 20/20 + 未知拒绝 ----
_n = 0
for name, idx in TMTrainer._CHAR_POOL_IDX.items():
    if hm.map_char_id(CHAR_LIBS[name]['id']) == name:
        _n += 1
ck(_n == 20, 'map_char_id 20/20 (CHAR_LIBS id→名)')
ck(all(hm.map_char_id(b) is None for b in (20, 255, -1, None, 'x')),
   '未知/越界 id → None(不猜)')

# ---- 2) _ckpt_guard: 真活档 + 伪旧代 ----
_lp = live_model_path('reimu', STORE_DIR)
_ok, _why = hm._ckpt_guard(_lp, 'reimu')
ck(_ok, '真活档 _ckpt_guard 通过(%s)' % _why)
tmp = tempfile.mkdtemp(prefix='hm15t_')
try:
    _n_out = len(CHAR_LIBS['reimu']['macros'])
    _bad = os.path.join(tmp, 'old.npz')
    np.savez(_bad, W2=np.zeros((10, 70), np.float32),
             W_side=np.zeros((680, 70), np.float32))
    _ok2, _why2 = hm._ckpt_guard(_bad, 'reimu')
    ck(not _ok2 and 'n_out' in _why2, '伪旧代模型拒绝并给原因: %s' % _why2)

    # ---- 3) resolve_model: live坏 → pool seed 好 ----
    _pdir = os.path.join(tmp, 'fleet', 'pool', 'reimu')
    os.makedirs(_pdir, exist_ok=True)
    _seed = os.path.join(_pdir, 'seed_x.npz')
    np.savez(_seed, W2=np.zeros((3, _n_out), np.float32),
             W_side=np.zeros((5 * _n_out + FeatureBuilder.CORE_DIMS, _n_out),
                             np.float32))
    np.savez(os.path.join(tmp, 'model_ppo_reimu_fleet.npz'),
             W2=np.zeros((10, 70), np.float32),
             W_side=np.zeros((680, 70), np.float32))
    _path, _src, _stamp, _tried = hm.resolve_model('reimu', store=tmp)
    ck(_src == 'pool_seed' and _path == _seed,
       'resolve_model: 坏 live → pool_seed 回退(顺序正确)')
    ck(len(_tried) == 1 and 'why' in _tried[0],
       '被跳过的旧代候选记录原因(tried)')
    ck(_stamp and 'path' in _stamp and 'mtime' in _stamp,
       'model_stamp 含 path/mtime(可溯源)')

    # ---- 4) 全不兼容 → SystemExit ----
    tmp2 = tempfile.mkdtemp(prefix='hm15b_')
    try:
        np.savez(os.path.join(tmp2, 'model_ppo_reimu.npz'),
                 W2=np.zeros((10, 70), np.float32),
                 W_side=np.zeros((680, 70), np.float32))
        try:
            hm.resolve_model('reimu', store=tmp2)
            _raised = False
        except SystemExit:
            _raised = True
        ck(_raised, '全候选不兼容 → SystemExit(禁静默/禁自动迁移)')
    finally:
        import shutil
        shutil.rmtree(tmp2, ignore_errors=True)
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

# ---- 5) 源码/CLI 锚: 0x34C 检测 + 活档 + set_opponent + probe 只读 ----
_src = io.open(os.path.join(ROOT, 'tools', 'human_match_v2.py'),
               encoding='utf8').read()
ck('CHARMGR_CHAR_IDX = 0x34C' in _src and 'CHARMGR_PLAYER_IDX = 0x350'
   in _src and 'def char_ids(' in _src, '源码锚: 0x34C/0x350 + char_ids')
ck('live_model_path' in _src and 'def resolve_model(' in _src
   and 'model_stamp' in _src, '源码锚: 活档链 + model_stamp')
ck('driver.set_opponent(p1c)' in _src, '源码锚: set_opponent(P1) 修 OOD')
ck('--probe-chars' in _src and '--detect-only' in _src
   and 'PROBE ' in _src, '源码锚: probe/detect 只读模式')
# probe 分支在载模型之前 return(只读: 不载模型/不写输入)
_i_probe = _src.find("if probe or detect_only:")
_i_driver = _src.find("driver = SideDriver(p2c, 'R')")
ck(0 < _i_probe < _i_driver, 'probe 分支先于模型加载/驱动(只读顺序)')

_r = subprocess.run([sys.executable, '-X', 'utf8',
                     os.path.join(ROOT, 'tools', 'human_match_v2.py'),
                     '--help'], capture_output=True, text=True)
ck(_r.returncode == 0 and '--probe-chars' in (_r.stdout or ''),
   'CLI --help 含 --probe-chars')

print('\n==== task-15 人测通路: %d PASS / %d FAIL ====' % (N, BAD))
sys.exit(0 if BAD == 0 else 1)
