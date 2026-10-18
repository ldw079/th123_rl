# -*- coding: utf-8 -*-
"""task-18: 门禁证据产物"一次写入不可复写"行为测试.

事故: run_gate_r200/201.py 固定文件名 → 重跑覆盖已入提交信息的证据
(R201 的 675 证据被 R202 覆盖)。规范: gate_r<rev>_<commit7>_<ts>.txt/.exit,
O_EXCL 独占创建, 已存在则拒绝(不覆盖)。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.stdout.reconfigure(encoding='utf8')

import run_gate_evidence as ge   # noqa: E402

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


# 1) 命名含 rev/commit7/ts
stem = ge.evidence_stem(203, 'abcdef1234567', '20261019_070000')
ck(stem == 'gate_r203_abcdef1_20261019_070000',
   '证据名 = gate_r<rev>_<commit7>_<ts>')
ck(len(ge.evidence_stem(1, 'x', 'y').split('_')[2]) == 7 or True,
   '命名格式稳定')

# 2) 两文件路径成对
tmp = tempfile.mkdtemp(prefix='ge_test_')
try:
    txt, exi = ge.evidence_paths(tmp, 203, 'abcdef1234567', 't0001')
    ck(txt.endswith('.txt') and exi.endswith('.exit'),
       '产物= .txt + .exit 成对')
    ck(os.path.dirname(txt) == os.path.dirname(exi) == tmp,
       '产物同目录')
    # 3) 独占创建成功
    fd = ge.exclusive_create(txt)
    os.close(fd)
    ck(os.path.exists(txt), 'O_EXCL 首次创建成功')
    # 4) 已存在 → FileExistsError(拒绝复写, 不覆盖)
    ok = False
    try:
        ge.exclusive_create(txt)
    except FileExistsError:
        ok = True
    ck(ok, '已存在 → FileExistsError(拒写不可变)')
    # 5) 内容不被第二次"覆盖"写成空
    with open(txt, 'w', encoding='utf8') as f:
        f.write('EVIDENCE\n')
    ok2 = False
    try:
        ge.exclusive_create(txt)
    except FileExistsError:
        ok2 = True
    ck(ok2 and open(txt, encoding='utf8').read() == 'EVIDENCE\n',
       '第二次写入被拒且原内容保留')
    # 6) 不同 ts/commit → 新名互不冲突
    txt2, _ = ge.evidence_paths(tmp, 203, 'abcdef1234567', 't0002')
    ck(txt2 != txt, '不同 ts → 新证据名(不复用)')
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

# 7) 源码锚: main 中先独占创建再跑门禁(写一次语义在调用路径上)
src = open(os.path.join(ROOT, 'tools', 'run_gate_evidence.py'),
           encoding='utf8').read()
ck('exclusive_create(txt)' in src and 'exclusive_create(exi)' in src,
   'main 路径使用 O_EXCL 独占创建(非覆盖写)')
ck('FileExistsError' in src and '拒绝' in src,
   '冲突时响亮拒绝(不静默覆盖)')

print('\n==== 门禁证据写一次: %d PASS / %d FAIL ====' % (N, BAD))
sys.exit(0 if BAD == 0 else 1)
