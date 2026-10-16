# -*- coding: utf-8 -*-
"""BC库IO单源(2026-10-14, 用户裁定mmap方案):

trio三件套(bc_{char}_X.npy/_S.npy/_Y.npy + meta.json)优先,
mmap_mode='r'按页加载 — 全量数据驻磁盘, 内存近零, 零质量损失
(此前npz全量驻留: v3.4行回收×5→5.2G/字符×3learner顶爆32G机,
分层采样封顶虽保标签占比但损标签内状态多样性 — mmap免费午餐)。
npz回退兼容(沙箱/旧库)。每update仅采64行→~1MB随机读, 无压力。
"""
from __future__ import annotations

import json
import os

import numpy as np


def _default_dirs(store=None):
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = []
    if store:
        dirs.append(store)
    if os.environ.get('TH123_STORE'):
        dirs.append(os.environ.get('TH123_STORE'))
    dirs.append(os.path.join(here, 'data', 'bc'))
    return dirs


def find_bank(char, suffix='', store=None, dirs=None):
    """找BC库: 返回(kind, base) — kind∈{'trio','npz',None}.

    trio优先(同名npz与trio并存时mmap版胜出)。
    """
    for d in (dirs or _default_dirs(store)):
        base = os.path.join(d, 'bc_%s%s' % (char, suffix))
        if all(os.path.exists(base + k)
               for k in ('_X.npy', '_S.npy', '_Y.npy')):
            return 'trio', base
        if os.path.exists(base + '.npz'):
            return 'npz', base + '.npz'
    return None, None


def _arr_sha256(a):
    """分块内容哈希(5.2G X阵不整块驻内存/不整块拷贝)."""
    import hashlib
    h = hashlib.sha256()
    flat = (a if a.flags.c_contiguous
            else np.ascontiguousarray(a)).reshape(-1)
    CH = 1 << 22                     # 4M元素/块
    for i in range(0, flat.size, CH):
        h.update(flat[i:i + CH].tobytes())
    return h.hexdigest()[:16]


def verify_trio(base):
    """trio代际契约(P1修复, bug_2026-10-14_bc_trio_swap_lock):

    meta.json=完成标记(写在三数组replace之后) + 三数组内容哈希绑定。
    缺meta/哈希不符/行数不符 → **响亮拒绝**(raise — 静默回落纯PPO
    或混代际锚训练都不可接受)。
    """
    import hashlib
    mp = base + '_meta.json'
    if not os.path.exists(mp):
        raise RuntimeError(
            '[bc_io] trio不完整: 缺meta.json(换装/转换中断?) — %s*\n'
            '  修复: 重跑npz_to_trio或从备份回滚' % base)
    meta = json.load(open(mp, encoding='utf8'))
    hs = meta.get('hashes')
    if not hs or not all(k in hs for k in ('X', 'S', 'Y')):
        raise RuntimeError(
            '[bc_io] trio meta无内容哈希(旧版转换产物?) — %s' % mp)
    X = np.load(base + '_X.npy', mmap_mode='r')
    S = np.load(base + '_S.npy', mmap_mode='r')
    Y = np.load(base + '_Y.npy', mmap_mode='r')
    if len(Y) != meta.get('rows') or X.shape[0] != len(Y):
        raise RuntimeError(
            '[bc_io] trio行数与meta不符(%d vs %s) — %s'
            % (len(Y), meta.get('rows'), mp))
    for k, a in (('Y', Y), ('S', S), ('X', X)):
        got = _arr_sha256(a)
        if got != hs[k]:
            raise RuntimeError(
                '[bc_io] trio代际不一致: %s哈希%s≠meta %s — 混代际锚\n'
                '  (%s) 修复: 重跑换装或回滚' % (k, got, hs[k], mp))
    return meta


def load_bank(char, suffix='', store=None, dirs=None, verify=True):
    """加载BC库(X,S,Y)。trio→mmap(memmap, 按页)+代际校验;
    npz→全量(ndarray)。

    返回(X,S,Y)或None(无库)。trio不完整/哈希不符→RuntimeError响亮
    (不静默回落 — 混代际BC锚训练污染不可接受)。
    verify=False跳过哈希校验(诊断用; 启动路径默认全验)。
    """
    kind, base = find_bank(char, suffix, store, dirs)
    # P2修(从零#4): 宽度守卫 — npz回退路径(data/bc旧330代库)无代际
    # 校验, 错宏数/错特征代的库被静默载入=混锚训练。trio有meta哈希
    # 校验豁免; npz在此按现行宏库派生期望宽度硬验。
    if kind == 'npz':
        d = np.load(base)
        S = d['S']
        from feat_builder import FeatureBuilder as _FB
        try:
            from train_tm import CHAR_LIBS as _CL
            _exp = 5 * len(_CL[char]['macros']) + _FB.CORE_DIMS
            if S.shape[1] != _exp:
                raise RuntimeError(
                    'npz库宽度漂移: %s S=%d≠派生%d — 旧代际库'
                    '(data/bc的330代?)误用, 拒载' % (base, S.shape[1], _exp))
        except KeyError:
            pass            # 非主力角色无CHAR_LIBS条目 — 不设期望
        return d['X'], S, d['Y']
    if kind == 'trio':
        if verify:
            verify_trio(base)
        X = np.load(base + '_X.npy', mmap_mode='r')
        S = np.load(base + '_S.npy', mmap_mode='r')
        Y = np.load(base + '_Y.npy', mmap_mode='r')
        return X, S, Y
    return None


def npz_to_trio(npz_path, out_dir=None, max_rows=0, seed=4321,
                out_stem=None):
    """npz→trio三件套+meta.json(可选行数封顶 — mmap下默认0=全量).

    out_stem: 目标命名(换装时bc_reimu_v3→bc_reimu, 缺省取源文件名)。
    代际契约(P1修复): 每文件tmp+replace原子; **meta.json最后写**且
    含三数组内容哈希 — meta=完成标记, load_bank校验绑定(中断/混代际
    =响亮拒载, 不给静默混锚训练留门)。
    """
    out_dir = out_dir or os.path.dirname(os.path.abspath(npz_path))
    stem = out_stem or os.path.splitext(
        os.path.basename(npz_path))[0]                        # bc_reimu_v3
    base = os.path.join(out_dir, stem)
    d = np.load(npz_path, allow_pickle=True)
    X, S, Y = d['X'], d['S'], d['Y']
    C = d['C'] if 'C' in d.files else None
    meta = json.loads(str(d['meta'])) if 'meta' in d.files else {}
    d.close()
    if max_rows and len(Y) > max_rows:
        rng = np.random.default_rng(seed)
        sel = np.zeros(len(Y), dtype=bool)
        for lab in np.unique(Y):
            li = np.where(Y == lab)[0]
            k = max(1, int(round(len(li) * max_rows / len(Y))))
            sel[rng.choice(li, size=min(k, len(li)), replace=False)] = True
        X, S, Y = X[sel], S[sel], Y[sel]
        if C is not None:
            C = C[sel]
        meta['capped_from'] = int(len(sel))
        meta['capped_to'] = int(sel.sum())
    for suf, arr in (('_X.npy', X), ('_S.npy', S), ('_Y.npy', Y),
                     ('_C.npy', C)):
        if arr is None:
            continue
        tmp = base + suf + '.tmp.npy'
        np.save(tmp, arr)
        os.replace(tmp, base + suf)
    meta['rows'] = int(len(Y))
    meta['hashes'] = {'X': _arr_sha256(X), 'S': _arr_sha256(S),
                      'Y': _arr_sha256(Y)}
    tmp = base + '_meta.json.tmp'
    with open(tmp, 'w', encoding='utf8') as f:
        json.dump(meta, f, ensure_ascii=False)
    os.replace(tmp, base + '_meta.json')
    return base


def fleet_running():
    """训练族进程探测(P1修复: 换装硬门禁).

    learner持trio mmap句柄终身 — 运行中换装=PermissionError半路崩+
    混血三件套风险。True=有任何训练族python或th123游戏进程存活。
    误报修复(2026-10-14): 限定python.exe进程名+带.py后缀匹配 —
    原正则被探测命令自身的bash包装进程自匹配(命令行含关键词)。
    """
    import subprocess
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "(Get-CimInstance Win32_Process -Filter "
             "\"Name='python.exe'\" | Where-Object {"
             "$_.CommandLine -match 'learner_hub[.]py|"
             "actor_worker[.]py|fleet_supervisor[.]py'} "
             "| Measure-Object).Count; "
             "(Get-Process th123 -ErrorAction SilentlyContinue "
             "| Measure-Object).Count"],
            capture_output=True, text=True, timeout=30)
        counts = [int(x) for x in r.stdout.strip().split()
                  if x.strip().isdigit()]
        return any(c > 0 for c in counts)
    except Exception as e:
        print('[bc_io] fleet_running探测失败(按运行中处理, 拒绝换装): %s'
              % e)
        return True   # 探测失败=保守拒绝(fail-closed)
