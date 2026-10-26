# -*- coding: utf-8 -*-
"""task-60 v2: BC 锚合并（dry-run 默认；--apply 需窗口）。

P1-4 修复:
- trio 级原子: staging 目录全文写入 + journal(状态机) + 备份硬链 + 失败整体回滚;
- 与生产 X 去重(逐行 hash 集合, 默认在 apply 时执行; dry-run 可 --dedupe 预览);
- 三文件+meta hash 对账 + bc_io 加载校验 (失败即回滚);
- manifest(生成/复验命令/hash/seed)写入 meta.anchor。
"""
import argparse
import gc
import hashlib
import io
import json
import os
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import bc_io  # noqa: E402

STORE = r'D:\temp\th123_models'
JOURNAL = os.path.join(STORE, 'bc_anchor_journal.json')




def _sha_file(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _copy_retry(src, dst, attempts=10, delay=2.0):
    """replace 失败时回退: copy 覆盖目标(非原子)+全文件 sha256 校验; 失败→回滚."""
    import time as _t
    last = None
    for i in range(attempts):
        try:
            shutil.copyfile(src, dst)
            if _sha_file(src) != _sha_file(dst):
                raise RuntimeError('copy hash mismatch')
            return True
        except (OSError, RuntimeError) as e:
            last = e
            print('[merge] copy retry %d/%d %s -> %s: %r'
                  % (i + 1, attempts, os.path.basename(src),
                     os.path.basename(dst), e))
            _t.sleep(delay)
    raise RuntimeError('copy failed after %d retries: %r' % (attempts, last))

def _replace_retry(src, dst, attempts=30, delay=2.0):
    """Windows: 目标/源被占用(WinError 32)→重试+退避; 仍失败→抛错由回滚处理."""
    import time as _t
    last = None
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return True
        except PermissionError as e:
            last = e
            print('[merge] replace retry %d/%d %s -> %s: %r'
                  % (i + 1, attempts, os.path.basename(src),
                     os.path.basename(dst), e))
            _t.sleep(delay)
    raise RuntimeError('replace failed after %d retries: %r' % (attempts, last))

def sha(a):
    return bc_io._arr_sha256(a)


def load_trio(char):
    base = os.path.join(STORE, 'bc_%s' % char)
    X = np.load(base + '_X.npy', mmap_mode='r')
    S = np.load(base + '_S.npy', mmap_mode='r')
    Y = np.load(base + '_Y.npy', mmap_mode='r')
    meta = json.load(io.open(base + '_meta.json', encoding='utf-8'))
    return X, S, Y, meta, base


def prod_x_hashes(char, chunk=4096):
    """生产 X 逐行 hash 集合(分块; 5GB 约数十秒)."""
    p = os.path.join(STORE, 'bc_%s_X.npy' % char)
    X = np.load(p, mmap_mode='r')
    hs = set()
    for i in range(0, len(X), chunk):
        blk = np.ascontiguousarray(X[i:i + chunk])
        for row in blk:
            hs.add(hashlib.md5(row.tobytes()).hexdigest())
    return hs


def prepare(char, anchor, dedupe=True):
    X, S, Y, meta, base = load_trio(char)
    with np.load(anchor, allow_pickle=True) as z:
        AX, AS = z['X'], z['S']
        AY = z['Y']
        Asrc = z['src'] if 'src' in z.files else np.array([])
    n_macros = int(meta['n_macros'])
    assert AX.shape[1] == X.shape[1], 'X 宽不一致'
    assert AS.shape[1] == S.shape[1], 'S 宽不一致'
    assert int(AY.min()) >= 0 and int(AY.max()) < n_macros, 'Y 越界'
    keep = np.ones(len(AY), bool)
    if dedupe:
        hs = prod_x_hashes(char)
        seen = set()
        for i, row in enumerate(np.ascontiguousarray(AX)):
            h = hashlib.md5(row.tobytes()).hexdigest()
            if h in hs or h in seen:
                keep[i] = False
            else:
                seen.add(h)
    AX, AS, AY, Asrc = AX[keep], AS[keep], AY[keep], Asrc[keep]
    rep = {'char': char, 'prod_rows': int(len(Y)),
           'anchor_rows_in': int(len(keep)), 'anchor_rows_keep': int(len(AY)),
           'dedup_dropped': int(len(keep) - len(AY)),
           'merged_rows': int(len(Y) + len(AY)),
           'X_width': int(X.shape[1]), 'S_width': int(S.shape[1]),
           'n_macros': n_macros, 'dedupe': bool(dedupe)}
    return rep, (X, S, Y, meta, base, AX, AS, AY, Asrc)


def _fsync(path):
    try:
        fd = os.open(path, os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
    except OSError:
        pass


def apply_merge(char, anchor, dedupe=True):
    rep, (X, S, Y, meta, base, AX, AS, AY, Asrc) = prepare(char, anchor,
                                                            dedupe)
    ts = time.strftime('%Y%m%d_%H%M%S')
    bdir = os.path.join(STORE, 'bc_backup_anchor_%s_%s' % (char, ts))
    sdir = os.path.join(STORE, '_staging_bc_%s_%s' % (char, ts))
    os.makedirs(bdir, exist_ok=True)
    os.makedirs(sdir, exist_ok=True)
    # 备份硬链
    for suf in ('_X.npy', '_S.npy', '_Y.npy', '_meta.json'):
        srcf = base + suf
        dst = os.path.join(bdir, os.path.basename(srcf))
        try:
            os.link(srcf, dst)
        except OSError:
            shutil.copy2(srcf, dst)
    # staging 全文生成
    nX = np.concatenate([np.asarray(X), AX]).astype(np.uint8)
    nS = np.concatenate([np.asarray(S), AS]).astype(np.float32)
    nY = np.concatenate([np.asarray(Y), AY]).astype(np.int64)
    assert nX.shape[1] == X.shape[1] and nS.shape[1] == S.shape[1]
    assert np.isfinite(nS).all()
    nmeta = dict(meta)
    nmeta['rows'] = int(len(nY))
    h = dict(meta.get('hashes') or {})
    h.update({'X': sha(nX), 'S': sha(nS), 'Y': sha(nY)})
    nmeta['hashes'] = h
    nmeta['anchor'] = {'source': 'offline_replay_anchor',
                       'npz': os.path.basename(anchor),
                       'n_rows': int(len(AY)),
                       'dedup_dropped': rep['dedup_dropped'],
                       'applied_ts': ts}
    paths = {}
    for suf, arr in (('_X.npy', nX), ('_S.npy', nS), ('_Y.npy', nY)):
        p = os.path.join(sdir, 'bc_%s%s' % (char, suf))
        np.save(p, arr)
        _fsync(p)
        paths[suf] = p
    pm = os.path.join(sdir, 'bc_%s_meta.json' % char)
    io.open(pm, 'w', encoding='utf-8').write(
        json.dumps(nmeta, ensure_ascii=False, indent=1))
    _fsync(pm)
    paths['_meta.json'] = pm
    journal = {'char': char, 'ts': ts, 'state': 'prepared',
               'base': base, 'backup': bdir, 'staging': sdir,
               'npz': os.path.abspath(anchor), 'rep': rep,
               'paths': {k: os.path.basename(v) for k, v in paths.items()},
               'hashes': {'X': sha(nX), 'S': sha(nS), 'Y': sha(nY)}}
    io.open(JOURNAL, 'w', encoding='utf-8').write(
        json.dumps(journal, ensure_ascii=False, indent=1))
    # 释放生产 trio 的 mmap: Windows 下对已 mmap 的目标做 os.replace 会
    # PermissionError(WinError 32) — 2026-10-26 两次部署失败的真正根因。
    # 显式关闭 memmap 句柄（仅置 None 可能仍有 np.memmap 引用）
    for _arr in (X, S, Y):
        _mm = getattr(_arr, '_mmap', None)
        if _mm is not None:
            try:
                _mm.close()
            except Exception:
                pass
    X = S = Y = None
    AX = AS = AY = None
    gc.collect()
    # 原子替换(逐文件 os.replace; journal 可回滚)
    try:
        try:
            for suf in ('_X.npy', '_S.npy', '_Y.npy', '_meta.json'):
                _replace_retry(paths[suf], base + suf)
        except RuntimeError as e:
            # 2026-10-26 20:42 诊断: os.replace 因 delete-deny 句柄失败, 但 copyfile
            # 可成功(小 store 复现 + 真锁 65s 证明 replace 超时无部分写)。
            # 安全 copy: 每文件 copy 后 sha256(staging)==sha256(生产), 失败→抛错回滚。
            print('[merge] replace fallback to copy:', repr(e))
            journal['replace_fallback'] = repr(e)[:300]
            journal['replace_fallback_hashes'] = {}
            for suf in ('_X.npy', '_S.npy', '_Y.npy', '_meta.json'):
                _copy_retry(paths[suf], base + suf)
                journal['replace_fallback_hashes'][suf] = _sha_file(base + suf)
        journal['state'] = 'applied'
        io.open(JOURNAL, 'w', encoding='utf-8').write(
            json.dumps(journal, ensure_ascii=False, indent=1))
        # 校验(bc_io 强校验)
        ok = True
        try:
            bx, bs, by, bi = bc_io.load_bank_seq(char, store=STORE)
            ok = (len(by) == rep['merged_rows']
                  and bx.shape[1] == X.shape[1]
                  and bs.shape[1] == S.shape[1])
        except Exception as e:
            journal['verify_error'] = repr(e)[:300]
            ok = False
        if not ok:
            raise RuntimeError('mergo verify failed')
        journal['state'] = 'verified'
        io.open(JOURNAL, 'w', encoding='utf-8').write(
            json.dumps(journal, ensure_ascii=False, indent=1))
        shutil.rmtree(sdir, ignore_errors=True)
        rep['backup'] = bdir
        print('[merge] APPLIED', json.dumps(rep, ensure_ascii=False))
        return rep
    except Exception as e:
        # 回滚
        for suf in ('_X.npy', '_S.npy', '_Y.npy', '_meta.json'):
            bk = os.path.join(bdir, os.path.basename(base + suf))
            if os.path.exists(bk):
                try:
                    os.replace(bk, base + suf)
                except OSError:
                    pass
        journal['state'] = 'rolled_back'
        journal['error'] = repr(e)[:300]
        io.open(JOURNAL, 'w', encoding='utf-8').write(
            json.dumps(journal, ensure_ascii=False, indent=1))
        shutil.rmtree(sdir, ignore_errors=True)
        raise


def rollback_from_journal():
    j = json.load(io.open(JOURNAL, encoding='utf-8'))
    bdir = j['backup']
    base = j['base']
    for suf in ('_X.npy', '_S.npy', '_Y.npy', '_meta.json'):
        bk = os.path.join(bdir, os.path.basename(base + suf))
        if os.path.exists(bk):
            os.replace(bk, base + suf)
    j['state'] = 'rolled_back_manual'
    io.open(JOURNAL, 'w', encoding='utf-8').write(
        json.dumps(j, ensure_ascii=False, indent=1))
    print('[merge] rolled back from journal', bdir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', required=True)
    ap.add_argument('--anchor', required=True)
    ap.add_argument('--apply', action='store_true', default=False)
    ap.add_argument('--dedupe', dest='dedupe', action='store_true',
                    default=True)
    ap.add_argument('--no-dedupe', dest='dedupe', action='store_false')
    ap.add_argument('--rollback', action='store_true', default=False)
    a = ap.parse_args()
    if a.rollback:
        rollback_from_journal()
        return 0
    if not a.apply:
        rep, _ = prepare(a.char, a.anchor, dedupe=False)
        print('[merge] dry-run:', json.dumps(rep, ensure_ascii=False))
        print('[merge] 未修改生产 trio（--apply + 窗口才生效）')
        return 0
    rep = apply_merge(a.char, a.anchor, dedupe=a.dedupe)
    print('[merge] done:', json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
