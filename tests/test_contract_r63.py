# -*- coding: utf-8 -*-
"""R63(P0-2): episode 尺寸代际契约行为测试。

事故(2026-10-07 架构审查, 实测于 learner_reimu.log):
  代码在活进程脚下变更(CORE_DIMS 316→330 / 宏数 63→70)时, 旧码actor继续
  按**自己的**尺寸产episode, 新码learner按**模型档**推断尺寸 →
  np.concatenate 抛 ValueError → 整批进 failed/ 永久丢失 + learner 无限
  continue(两侧进程都"活着")。实测: 13次启动拒绝 + 5次批隔离 + 26个
  failed文件(~300MB)。

本测试把修复语义钉成可证伪断言:
  1. 正常契约: 写→读往返, contract块完整且自洽;
  2. 写者自检: 声明与实际数组形状不符 → **拒绝落盘**(响亮);
  3. 读者自洽: contract与数组形状不符 → EpisodeContractError;
  4. 读者代际: contract.n_out ≠ 当前代码宏数 → EpisodeContractError
     (这是抓"actor跑旧码"的核心判据);
  5. v1档(schema=1, 无contract块) → 明确拒收且**不被删除**;
  6. expect_contract不符(learner视角) → 拒收;
  7. 契约正常时 update_from_episodes 仍可消费(修复不误伤正常路径)。
"""
import json
import os
import shutil
import sys
import tempfile

import numpy as np

sys.stdout.reconfigure(encoding='utf8')
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import episode_core as EC  # noqa: E402
from episode_core import (build_contract, check_contract,  # noqa: E402
                          code_macro_count, episode_meta, load_episode_npz,
                          save_episode_npz, EpisodeContractError, EP_SCHEMA)
from feat_builder import FeatureBuilder  # noqa: E402

FAILS = []


def chk(cond, name, detail=''):
    print('  %s %s%s' % ('PASS' if cond else 'FAIL', name,
                         ('  [%s]' % detail) if detail else ''))
    if not cond:
        FAILS.append(name)


CHAR = 'reimu'
N_OUT = code_macro_count(CHAR)
CORE = FeatureBuilder.CORE_DIMS
N_SIDE = 5 * N_OUT + CORE
FEAT = 64          # 合成视觉宽度(契约feat_dim按数组实际回写 — 不误报)
NDEC = 6

print('==== R63 episode 契约行为测试 ====')
print('  (代码侧: char=%s n_out=%d CORE_DIMS=%d n_side=%d schema=%d)'
      % (CHAR, N_OUT, CORE, N_SIDE, EP_SCHEMA))
chk(N_OUT is not None and N_OUT > 0, 'code_macro_count可解析', str(N_OUT))

TMP = tempfile.mkdtemp(prefix='_r63_contract_')


def mk_arrays(n_side=N_SIDE, n_out=N_OUT, n=NDEC, feat=FEAT):
    return dict(
        feats=np.zeros((n, feat), dtype=np.uint8),
        sides=np.zeros((n, n_side), dtype=np.float32),
        acts=np.zeros(n, dtype=np.int64),
        rews=np.zeros(n, dtype=np.float32),
        masks=np.ones((n, n_out), dtype=bool),
        bc_targets=np.zeros(n, dtype=np.int64),
        opp_next=-np.ones(n, dtype=np.int64),
        logps=np.full(n, -np.log(n_out), dtype=np.float32),
        ep_terms=np.array([True]),
        distill=np.zeros((0, 11), dtype=np.float32),
    )


# ---- 1. 正常往返 ----
_c = build_contract(CHAR, N_OUT, N_SIDE, N_OUT)
chk(check_contract(_c) == [], '2a 契约自洽(代码侧宏数/布局一致)',
    str(check_contract(_c)))
_p1 = save_episode_npz(TMP, CHAR, 0, 1, mk_arrays(),
                       episode_meta(CHAR, 0, 1, 3, 7, NDEC, contract=_c))
_a, _m = load_episode_npz(_p1)
chk(_m['contract']['n_out'] == N_OUT and _m['contract']['n_side'] == N_SIDE,
    '1a 往返: contract块完整读出')
chk(_m['contract']['feat_dim'] == FEAT,
    '1b 写者按数组实际回写feat_dim(合成宽度不误报)',
    str(_m['contract']['feat_dim']))
chk(_m['snap_ver'] == 3 and _m['decisions'] == NDEC, '1c 原meta字段未破坏')

# ---- 1d. 契约的**写者声明字段**必须与代码侧同源 ----
# 这是变异自检逼出来的断言: 门禁若只钉"build_contract存在", 把actor改成
# 写死尺寸(如 build_contract('reimu',3,3,3))也能过。这里直接验证
# actor_worker.submit 实际传的四个实参都取自本网络/宏库。
_aw = open(os.path.join(os.path.dirname(_HERE), 'actor_worker.py'), encoding='utf8').read()
chk("build_contract(char, tr.n_macros, int(tr.ppo.N_SIDE), tr.n_macros)"
    in _aw,
    '1d actor写契约的四个实参全部取自自身网络(宏数/N_SIDE不写死)')
# 且契约内 code_n_macros 必须等于代码侧(写者自述与代码同代)
chk(int(_m['contract']['code_n_macros']) == int(N_OUT),
    '1e 契约内code_n_macros==代码宏数',
    '%s vs %s' % (_m['contract']['code_n_macros'], N_OUT))

# ---- 1f. 模型代际判据(单一实现, 行为覆盖) ----
from episode_core import check_model_generation  # noqa: E402
chk(check_model_generation(CHAR, N_OUT) is None,
    '1f 模型代际判据: 相符放行')
_r_bad = check_model_generation(CHAR, N_OUT - 7)
chk(_r_bad is not None and ('宏数' in _r_bad or 'n_out' in _r_bad),
    '1g 模型代际判据: 不符给出原因(调用方据此拒绝启动)', str(_r_bad)[:80])
chk(check_model_generation('__no_such_char__', 5) is not None,
    '1h 模型代际判据: 角色宏库不可导入 → 也不放行(不静默降级)')

# ---- 2. 写者自检: 声明与实际不符 → 拒绝落盘 ----
try:
    save_episode_npz(TMP, CHAR, 0, 2, mk_arrays(n_side=N_SIDE - 8),
                     episode_meta(CHAR, 0, 2, 3, 7, NDEC, contract=_c))
    chk(False, '2a 写者自检: sides宽不符 → 拒写', '未抛异常')
except EpisodeContractError as e:
    chk(True, '2a 写者自检: sides宽不符 → 拒写', str(e)[:70])
try:
    save_episode_npz(TMP, CHAR, 0, 3, mk_arrays(n_out=N_OUT - 5),
                     episode_meta(CHAR, 0, 3, 3, 7, NDEC, contract=_c))
    chk(False, '2b 写者自检: masks宽不符 → 拒写', '未抛异常')
except EpisodeContractError as e:
    chk(True, '2b 写者自检: masks宽不符 → 拒写', str(e)[:70])

# ---- 3/4. 读者: 伪造不同代际的契约文件 ----
def _forge(n_out, n_side, n_macros, tag, feat=FEAT, code_n=None):
    """直接写一个契约与内容不符/代际不符的npz(绕过写者自检)。"""
    p = os.path.join(TMP, 'forge_%s.npz' % tag)
    arr = mk_arrays(n_side=n_side, n_out=n_macros, feat=feat)
    meta = episode_meta(CHAR, 0, 99, 1, 1, NDEC)
    _mm = json.loads(meta)
    _mm['contract'] = {
        'char': CHAR, 'n_out': int(n_out), 'n_side': int(n_side),
        'n_macros': int(n_macros), 'feat_dim': int(feat),
        'code_n_macros': int(code_n if code_n is not None else n_out),
    }
    data = dict(arr)
    data['meta'] = np.array(json.dumps(_mm))
    data['schema'] = np.array(EP_SCHEMA)
    np.savez(p, **data)
    return p


# 3. 自洽但形状不符(声明n_out=代码值, 但实际数组是另一尺寸)
_p_old = _forge(N_OUT, N_SIDE - 8, N_OUT - 8, 'shapemismatch')
try:
    load_episode_npz(_p_old)
    chk(False, '3a 读者: 声明与数组形状不符 → 拒收', '未抛异常')
except EpisodeContractError as e:
    chk(True, '3a 读者: 声明与数组形状不符 → 拒收', str(e)[:80])

# 4. **核心回归**: 旧代际(宏数不同) — 这正是生产事故形态
_p_gen = _forge(N_OUT - 7, 5 * (N_OUT - 7) + CORE, N_OUT - 7, 'oldgen')
try:
    load_episode_npz(_p_gen)
    chk(False, '4a 读者: 旧代际宏数 → 拒收(生产事故形态)', '未抛异常')
except EpisodeContractError as e:
    chk('宏数' in str(e) or 'n_out' in str(e),
        '4a 读者: 旧代际宏数 → 拒收(生产事故形态)', str(e)[:90])

# 4b. learner视角: expect_contract 直接比对
try:
    load_episode_npz(_p1, expect_contract={'n_out': N_OUT - 7})
    chk(False, '4b 读者: expect_contract不符 → 拒收', '未抛异常')
except EpisodeContractError as e:
    chk('契约不符' in str(e), '4b 读者: expect_contract不符 → 拒收',
        str(e)[:80])

# 4c. **仅"代际"不符**而形状自洽 — 只有代码侧宏数校验能抓住它。
# (4a的伪造件形状也错, 会被形状断言挡下; 变异自检证明那样的断言是弱的:
#  check_contract恒空时4a依然红, 所以必须补这条"形状全对但代际错"的用例。)
_p_gen2 = _forge(N_OUT - 7, 5 * (N_OUT - 7) + CORE, N_OUT - 7, 'oldgen2')
try:
    load_episode_npz(_p_gen2)
    chk(False, '4c 读者: 形状自洽但宏数旧代际 → 拒收(仅代际校验可抓)', '未抛异常')
except EpisodeContractError as e:
    chk('当前代码宏数' in str(e) or '宏数' in str(e),
        '4c 读者: 形状自洽但宏数旧代际 → 拒收(仅代际校验可抓)', str(e)[:95])

# ---- 5. v1档(schema=1, 无contract) → 明确拒收且不删 ----
_p_v1 = os.path.join(TMP, 'v1_no_contract.npz')
_arr = mk_arrays()
_data = dict(_arr)
_data['meta'] = np.array(episode_meta(CHAR, 0, 5, 1, 1, NDEC))  # 无contract
_data['schema'] = np.array(1)
np.savez(_p_v1, **_data)
try:
    load_episode_npz(_p_v1)
    chk(False, '5a v1无契约档 → 明确拒收', '未抛异常')
except EpisodeContractError as e:
    chk(True, '5a v1无契约档 → 明确拒收', str(e)[:80])
chk(os.path.exists(_p_v1), '5b 拒收不改写/不删除文件(证据保留)')

# 5c. 未来schema
_p_fut = os.path.join(TMP, 'future.npz')
_d2 = dict(mk_arrays())
_d2['meta'] = np.array(json.dumps({'char': CHAR}))
_d2['schema'] = np.array(EP_SCHEMA + 1)
np.savez(_p_fut, **_d2)
try:
    load_episode_npz(_p_fut)
    chk(False, '5c 未来schema → 拒收', '未抛异常')
except EpisodeContractError:
    chk(True, '5c 未来schema → 拒收')

# ---- 6. check_contract 对缺块/畸形输入不崩 ----
chk(check_contract(None) != [], '6a check_contract(None) 返回问题而非崩溃')
chk(check_contract({'char': CHAR}) != [], '6b 缺键被报出')
_bad_self = dict(_c)
_bad_self['n_macros'] = N_OUT - 3
chk(any('n_macros' in b for b in check_contract(_bad_self)),
    '6c n_macros≠n_out 被捕获')

# ---- 7. 正常路径不被误伤: learner消费正常契约的episode ----
try:
    from learner_hub import update_from_episodes
    from ppo_gpu import PPOTrainerGPU
    import ppo as _ppo
    _REAL_FEAT = 3 * _ppo.CONV_H * _ppo.CONV_W   # conv前向要求真实视觉宽
    _aps = []
    for i in range(2):
        _c2 = build_contract(CHAR, N_OUT, N_SIDE, N_OUT, feat_dim=_REAL_FEAT)
        _aps.append(save_episode_npz(
            TMP, CHAR, 0, 100 + i,
            mk_arrays(feat=_REAL_FEAT, n=4),
            episode_meta(CHAR, 0, 100 + i, 1, 1, 4, contract=_c2)))
    _g = PPOTrainerGPU(n_side=N_SIDE, n_out=N_OUT)   # 随机初始化即可
    _st, _mc, _ne, _mv, _N = update_from_episodes(
        _g, _aps, CHAR, '_r63t', N_OUT,
        np.zeros(N_OUT, dtype=np.int64))
    chk(_ne == 2 and _N == 8,
        '7a 正常契约episode仍被消费(修复不误伤)', 'neps=%s N=%s' % (_ne, _N))
    chk(not any(os.path.exists(p) for p in _aps), '7b 消费后删除(原语义保持)')
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, '7 正常路径回归', '%s: %s' % (type(e).__name__, e))

# ---- P1-4(从零#5): 逐决策数组**行数**对账(原只比宽度) ----
# 事故形态: feats/sides 8 行、acts/logps 4 行的文件被接受、被 learner 消费、
# 随后 os.remove —— 无隔离无告警。写者与读者都必须拒收半截 episode。
print('  ---- P1-4 行数对账 ----')
_c_ok = build_contract(CHAR, N_OUT, N_SIDE, N_OUT, feat_dim=FEAT)
_ok_arr = mk_arrays(n=6)
_c_rows = EC.check_row_counts(_ok_arr)
chk(_c_rows == [], 'P1-4a 一致行数 → 对账为空', str(_c_rows))

_bad_arr = mk_arrays(n=6)
_bad_arr['acts'] = np.zeros(4, dtype=np.int64)      # 只 4 行
_rows = EC.check_row_counts(_bad_arr)
chk(len(_rows) == 1 and _rows[0][0] == 'acts' and _rows[0][1] == 4,
    'P1-4b 半截 acts(4/6行) → 对账命中', str(_rows))

# 写者: 拒收(响亮)而不是落盘
try:
    save_episode_npz(TMP, CHAR, 0, 90, _bad_arr,
                     episode_meta(CHAR, 0, 90, 1, 1, 6, contract=_c_ok))
    chk(False, 'P1-4c 写者拒收半截episode')
except EpisodeContractError as e:
    chk('行数' in str(e), 'P1-4c 写者拒收半截episode', str(e)[:60])

# 读者: 直接落一份(绕过写者自检)再读 → 必须拒收
_badp = os.path.join(TMP, 'ep_bypass.npz')
_d = dict(_bad_arr)
_d['meta'] = np.array(episode_meta(CHAR, 0, 91, 1, 1, 6, contract=_c_ok))
_d['schema'] = np.array(EP_SCHEMA)
np.savez(_badp, **_d)
try:
    load_episode_npz(_badp)
    chk(False, 'P1-4d 读者拒收半截episode(绕过写者)')
except EpisodeContractError as e:
    chk('行数' in str(e), 'P1-4d 读者拒收半截episode(绕过写者)', str(e)[:60])

# 回归: 一致行数的正常档仍可读
_goodp = save_episode_npz(TMP, CHAR, 0, 92, mk_arrays(n=6),
                          episode_meta(CHAR, 0, 92, 1, 1, 6, contract=_c_ok))
_ar, _me = load_episode_npz(_goodp)
chk(_ar['acts'].shape[0] == 6, 'P1-4e 正常档往返不误伤',
    str(_ar['acts'].shape))

shutil.rmtree(TMP, ignore_errors=True)
print()
if FAILS:
    print('==== %d FAIL ====' % len(FAILS))
    for f in FAILS:
        print('  - %s' % f)
    sys.exit(1)
print('==== ALL PASS: R63 episode契约行为测试通过 ====')
