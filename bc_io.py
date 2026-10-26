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
    # 指针切换: TH123_BC_DIR 优先(新 genN trio 目录; 无 env 时行为不变)
    if os.environ.get('TH123_BC_DIR'):
        dirs.append(os.environ.get('TH123_BC_DIR'))
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


_VCACHE_VER = 1


def _stat_stamp(paths):
    out = []
    for x in paths:
        try:
            st = os.stat(x)
            out.append([os.path.basename(x), int(st.st_size),
                        int(st.st_mtime_ns), int(st.st_ctime_ns)])
        except OSError:
            return None
    return out


def _verify_cache_path(base):
    return base + '_verify.json'


def _try_cached_verify(base, meta):
    """启动加速: 文件(大小+mtime)未变且缓存哈希一致 → 跳过全量哈希。

    env `TH123_BC_HASH_CACHE=0` 可关闭(强制全量校验)。缓存在替换三数组时
    因 mtime/大小变化自动失效 → 不会掩盖混代际。
    """
    if os.environ.get('TH123_BC_HASH_CACHE', '1') == '0':
        return False
    cp = _verify_cache_path(base)
    paths = [base + '_X.npy', base + '_S.npy', base + '_Y.npy']
    if meta.get('seq_aware') or meta.get('hashes', {}).get('I'):
        paths.append(base + '_I.npy')
    stamp = _stat_stamp(paths)
    if stamp is None:
        return False
    try:
        with open(cp, encoding='utf8') as f:
            c = json.load(f)
    except Exception:
        return False
    if (c.get('ver') != _VCACHE_VER or c.get('stamp') != stamp
            or c.get('hashes') != meta.get('hashes')):
        return False
    return True


def _write_cached_verify(base, meta):
    cp = _verify_cache_path(base)
    paths = [base + '_X.npy', base + '_S.npy', base + '_Y.npy']
    if meta.get('seq_aware') or meta.get('hashes', {}).get('I'):
        paths.append(base + '_I.npy')
    stamp = _stat_stamp(paths)
    if stamp is None:
        return
    try:
        tmp = cp + '.tmp'
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump({'ver': _VCACHE_VER, 'stamp': stamp,
                       'hashes': meta.get('hashes')}, f)
        os.replace(tmp, cp)
    except Exception:
        pass


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
    if _try_cached_verify(base, meta):
        return meta
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
    # S-6: I列哈希(meta登记seq_aware时必验)
    if hs.get('I'):
        ipath = base + '_I.npy'
        if not os.path.exists(ipath):
            raise RuntimeError(
                '[bc_io] meta含I哈希但缺_I.npy — %s*' % base)
        if _arr_sha256(np.load(ipath, mmap_mode='r')) != hs['I']:
            raise RuntimeError('[bc_io] I列代际不一致 — %s' % mp)
    _write_cached_verify(base, meta)
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


def load_bank_seq(char, suffix='', store=None, dirs=None):
    """S-6: 序列感知加载 → (X, S, Y, I); I=shard组id(无I列的旧库
    返回None → 调用方回落iid采样)。trio读_I.npy(meta标记seq_aware);
    npz读'I'键。哈希校验沿load_bank(同base)。"""
    X, S, Y = load_bank(char, suffix, store, dirs)
    if X is None:
        return None, None, None, None
    kind, base = find_bank(char, suffix, store, dirs)
    try:
        if kind == 'trio':
            ipath = base + '_I.npy'
            if os.path.exists(ipath):
                return X, S, Y, np.load(ipath, mmap_mode='r')
        else:
            d = np.load(base)
            if 'I' in d.files:
                return X, S, Y, d['I']
    except Exception as e:
        print('[bc_io] I列读取失败(%r) — 回落iid采样' % e)
    return X, S, Y, None


def sample_seq_window(I, k, rng):
    """S-6: 同shard连续窗口采样 → 行索引数组。

    I为按行排布的shard组id(同id行相邻 — bc_build保序保证)。
    随机选一个组, 组内随机起点取min(k, 组长)连续行; 组不足k时取整组
    (短组语义: 宁短勿跨 — 跨shard的"连续"是假序列)。
    I为None → 返回None(调用方回落iid)。"""
    if I is None or len(I) == 0:
        return None
    uniq, starts = np.unique(I, return_index=True)
    # 组长: 相邻组起点差(末组到行尾)
    bounds = np.append(starts, len(I))
    lens = np.diff(bounds)
    gi = rng.integers(0, len(uniq))
    L = int(lens[gi])
    st = int(starts[gi]) + (int(rng.integers(0, max(1, L - k + 1)))
                            if L > k else 0)
    return np.arange(st, st + min(k, L))


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
    I = d['I'] if 'I' in d.files else None    # S-6: shard组id(可缺)
    meta = json.loads(str(d['meta'])) if 'meta' in d.files else {}
    d.close()
    if max_rows and len(Y) > max_rows:
        rng = np.random.default_rng(seed)
        n_from = int(len(Y))
        sel = np.zeros(len(Y), dtype=bool)
        for lab in np.unique(Y):
            li = np.where(Y == lab)[0]
            k = max(1, int(round(len(li) * max_rows / len(Y))))
            sel[rng.choice(li, size=min(k, len(li)), replace=False)] = True
        sel = np.sort(np.where(sel)[0])       # S-6: 保序(同shard相邻)
        X, S, Y = X[sel], S[sel], Y[sel]
        if C is not None:
            C = C[sel]
        if I is not None:
            I = I[sel]
        meta['capped_from'] = n_from
        meta['capped_to'] = int(len(sel))
    for suf, arr in (('_X.npy', X), ('_S.npy', S), ('_Y.npy', Y),
                     ('_C.npy', C), ('_I.npy', I)):
        if arr is None:
            continue
        tmp = base + suf + '.tmp.npy'
        np.save(tmp, arr)
        os.replace(tmp, base + suf)
    meta['rows'] = int(len(Y))
    meta['seq_aware'] = I is not None
    hs = {'X': _arr_sha256(X), 'S': _arr_sha256(S), 'Y': _arr_sha256(Y)}
    if I is not None:
        hs['I'] = _arr_sha256(I)
    meta['hashes'] = hs
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
