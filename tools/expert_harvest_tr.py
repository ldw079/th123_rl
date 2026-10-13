# -*- coding: utf-8 -*-
r"""专家库扩容: TR等七段+高手rep集合(用户2026-10-12赠, 61,572个).

优先级: ①双边(现役三角互打, ~964 — 双侧都可采) ②单边(高手操作现役
角色, ~13k — 按顶级夹分批, 体量大需先裁定存储). 内容md5去重(vs 既有
expert_reps + 已采manifest). 产物追加 oracle_v2/shards + manifest
(bc_build既有消费契约, shard名tr前缀隔离).

归因隔离纪律: 采集是惰性数据, 不触训练; **BC库重建在A/B裁定后**.

用法: python tools/expert_harvest_tr.py [--limit 20] [--kind both|ours]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')

from oracle_batch2 import run_one, ORACLE_SET, OUT, ML
from portmap import reserved_port
import numpy as np

SRC_ROOT = r'D:\TR丹尼尔棉咖啡等录像精选'
OLD_EXPERT = r'D:\temp\expert_reps'
PORT = reserved_port('expert_harvest')   # probe段
TPS = 480
OURS = {0, 1, 9}


def _md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def scan(kind='both'):
    """walk TR集合 → [('both'|'ours', path, rel)]. both=双侧现役;
    ours=高手侧现役(对手任意)."""
    out = []
    for dirpath, _dirs, files in os.walk(SRC_ROOT):
        for fn in sorted(files):
            if not fn.lower().endswith('.rep'):
                continue
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) < 121:   # R81b: 截断rep预过滤
                    continue
                with open(p, 'rb') as f:
                    b = f.read(64)
                if len(b) < 64 or b[0] != 0xD2:
                    continue
                cx, cy = b[14], b[63]
            except OSError:
                continue
            both = cx in OURS and cy in OURS
            ours = (cx in OURS or cy in OURS)
            if kind == 'both':
                if both:
                    out.append(('both', p, os.path.relpath(p, SRC_ROOT)))
            elif kind == 'ours':
                if ours and not both:
                    out.append(('ours', p, os.path.relpath(p, SRC_ROOT)))
    return out


def _done_md5s(man):
    """已采集的内容md5集合(manifest行含md5字段者) + 旧库全量md5."""
    done = set()
    if os.path.exists(man):
        for ln in open(man, encoding='utf8'):
            try:
                m = json.loads(ln).get('md5')
                if m:
                    done.add(m)
            except ValueError:
                continue
    # 旧expert_reps的md5(1521个 — 一次性成本约30s)
    if os.path.isdir(OLD_EXPERT):
        for fn in os.listdir(OLD_EXPERT):
            if fn.lower().endswith('.rep'):
                try:
                    done.add(_md5(os.path.join(OLD_EXPERT, fn)))
                except OSError:
                    continue
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='0=不限')
    ap.add_argument('--kind', choices=['both', 'ours'], default='both')
    args = ap.parse_args()

    from soku_arch.rep_file import parse_rep_file
    shards_dir = os.path.join(OUT, 'shards')
    os.makedirs(shards_dir, exist_ok=True)
    man = os.path.join(OUT, 'manifest.jsonl')

    print('[TR] 扫描源(%s)...' % args.kind)
    todo_all = scan(args.kind)
    print('[TR] 候选 %d 个 — 计算去重集(旧库1521个md5)...' % len(todo_all))
    done = _done_md5s(man)
    todo = []
    seen = set()
    for kind, p, rel in todo_all:
        try:
            h = _md5(p)
        except OSError:
            continue
        if h in done or h in seen:
            continue
        seen.add(h)
        todo.append((kind, p, rel, h))
        if args.limit and len(todo) >= args.limit:
            break
    print('[TR] 去重后待采 %d 个%s' % (
        len(todo), '(limit=%d)' % args.limit if args.limit else ''))

    # mod切换(oracle观测集) + 用后逐字节恢复
    orig = None
    if os.path.exists(ML):
        with open(ML, 'rb') as f:
            orig = f.read()
    with open(ML, 'w', encoding='utf8', newline='') as f:
        json.dump({'modules': {'modules/%s/%s.dll' % (m, m):
                               {'enabled': True} for m in ORACLE_SET}}, f, indent=4)

    t0 = time.time()
    ok_n = bad_n = 0
    try:
        for i, (kind, path, rel, h) in enumerate(todo):
            shard = 'tr%05d_%s.npz' % (i, h[:8])
            ilog_tmp = os.path.join(shards_dir, shard + '.ilog.tmp')
            try:
                rep, pkts, offsets, rounds, scores, err, dur = run_one(
                    path, PORT, TPS, 'trH.rep', ilog_path=ilog_tmp)
            except Exception as e:
                # 审计2026-10-13采集链#2: 兜底parse是死代码 — err置位+
                # offsets恒空 → 闸必拒 → 放弃, parse结果从不被消费
                # (R81b的try包parse只为防崩, 现连parse一起删)。
                err, pkts, offsets, rounds, scores = 'exc:%s' % str(e)[:60], \
                    b'', [], [], []
                dur = 0
                rep = None
            if rep is None or len(offsets) <= 100 or err is not None:
                bad_n += 1
                print('  [%d/%d] 放弃 %s err=%s 帧数%d' % (
                    i + 1, len(todo), rel[:40], err, len(offsets)))
                for _st in (ilog_tmp,):
                    if _st and os.path.exists(_st):
                        os.remove(_st)
                continue
            meta = {'rep': os.path.basename(path), 'src': 'TR精选',
                    'kind': kind, 'folder': rel.split(os.sep)[0:2][-1],
                    'md5': h, 'char_x': rep.char_x, 'char_y': rep.char_y,
                    'pal_x': rep.pal_x, 'pal_y': rep.pal_y,
                    'deck_x': list(rep.deck_x), 'deck_y': list(rep.deck_y),
                    'seed': rep.seed, 'n_inputs': rep.n_frames,
                    'frames': len(offsets), 'rounds': rounds,
                    'score_final': list(scores[-1]) if scores else None,
                    'err': err, 'dur_s': round(dur, 1), 'shard': shard,
                    'fmt': 'L105R105W4N17'}
            ilog_arr = None
            try:
                ilog_arr = np.loadtxt(ilog_tmp,
                                      dtype=np.uint16).reshape(-1, 4)
            except Exception:
                ilog_arr = None
            kw = {}
            if ilog_arr is not None and len(ilog_arr) >= len(offsets) >= 1:
                kw['ilog'] = ilog_arr[:len(offsets)]
                meta['ilog'] = True
            tmp = os.path.join(shards_dir, shard + '.tmp.npz')
            np.savez(tmp,
                     pkts=np.frombuffer(pkts, dtype=np.uint8),
                     offsets=np.array(offsets, dtype=np.int64),
                     inputs=np.array([rep.inputs[2 * f:2 * f + 2]
                                      for f in range(min(rep.n_frames,
                                                         len(offsets)))],
                                     dtype=np.uint16),
                     rounds=np.array(rounds),
                     meta=np.array(json.dumps(meta, ensure_ascii=False)),
                     **kw)
            os.replace(tmp, os.path.join(shards_dir, shard))
            if ilog_tmp and os.path.exists(ilog_tmp):
                os.remove(ilog_tmp)
            with open(man, 'a', encoding='utf8') as f:
                f.write(json.dumps(meta, ensure_ascii=False) + '\n')
            ok_n += 1
            el = time.time() - t0
            print('  [%d/%d] %s 帧%d %s %.0fs(均%.0fs)' % (
                i + 1, len(todo), os.path.basename(path)[:36],
                len(offsets), 'OK', dur, el / (i + 1)))
    finally:
        if orig is not None:
            with open(ML, 'wb') as f:
                f.write(orig)
    print('[TR] 完成: 采集%d 放弃%d 墙钟%.0fmin' % (
        ok_n, bad_n, (time.time() - t0) / 60))


if __name__ == '__main__':
    main()
