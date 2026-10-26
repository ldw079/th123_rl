# -*- coding: utf-8 -*-
"""task-70: 全库 .rep 分层索引（只读；解析/角色/帧数/hash/年代）.

用法:
  python tools/human_replay_index.py [--root ...] [--limit N] [--workers W]
 输出: JSONL 索引 + summary JSON（失败样本记录）。
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time

ROOT_REP = r'D:\TR丹尼尔棉咖啡等录像精选'
OUT = r'D:\temp\scratch\human_replay_index_20261026.jsonl'
SUMMARY = r'D:\temp\scratch\human_replay_index_summary_20261026.json'
sys.path.insert(0, r'D:\temp\soku_arch')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl')


def char_names():
    try:
        from train_tm import CHAR_LIBS
        return {l['id']: n for n, l in CHAR_LIBS.items()}
    except Exception:
        return {}


def one(p, cmap):
    from soku_arch.rep_file import parse_rep_file, inputs_by_side
    rec = {'path': p, 'size': os.path.getsize(p),
           'mtime': int(os.path.getmtime(p))}
    try:
        rep = parse_rep_file(p)
        arr = inputs_by_side(list(rep.inputs))
        rec.update({
            'ok': True, 'frames': int(len(arr)),
            'duration_s': round(len(arr) / 62.0, 1),
            'char_x': cmap.get(int(rep.char_x), int(rep.char_x)),
            'char_y': cmap.get(int(rep.char_y), int(rep.char_y)),
            'seed': int(rep.seed),
            'year': int(time.strftime('%Y', time.localtime(
                os.path.getmtime(p)))),
            'sha1': hashlib.sha1(open(p, 'rb').read()).hexdigest(),
        })
    except Exception as e:
        rec.update({'ok': False, 'err': repr(e)[:160]})
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=ROOT_REP)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--out', default=OUT)
    a = ap.parse_args()
    files = []
    for d in sorted(os.listdir(a.root)):
        sub = os.path.join(a.root, d)
        if not os.path.isdir(sub):
            continue
        fs = glob.glob(os.path.join(sub, '**', '*.rep'), recursive=True)
        files += fs
    files = sorted(files)
    if a.limit > 0:
        files = files[:a.limit]
    print('[index] files=%d workers=%d' % (len(files), a.workers), flush=True)
    cmap = char_names()
    t0 = time.time()
    out = open(a.out, 'w', encoding='utf-8')
    ok = fail = 0
    fails = []
    if a.workers <= 1:
        for i, p in enumerate(files):
            rec = one(p, cmap)
            if rec.get('ok'):
                ok += 1
            else:
                fail += 1
                fails.append(rec)
            out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            if (i + 1) % 200 == 0:
                print('[index] %d/%d ok=%d fail=%d %.1fs' % (
                    i + 1, len(files), ok, fail, time.time() - t0),
                    flush=True)
    else:
        from multiprocessing import Pool
        with Pool(a.workers) as pool:
            for i, rec in enumerate(pool.imap_unordered(
                    _worker, [(p, cmap) for p in files], chunksize=16)):
                if rec.get('ok'):
                    ok += 1
                else:
                    fail += 1
                    fails.append(rec)
                out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                if (i + 1) % 500 == 0:
                    print('[index] %d/%d ok=%d fail=%d %.1fs' % (
                        i + 1, len(files), ok, fail, time.time() - t0),
                        flush=True)
    out.close()
    summary = {'root': a.root, 'files': len(files), 'ok': ok, 'fail': fail,
               'elapsed_s': round(time.time() - t0, 1),
               'fail_samples': fails[:20],
               'out': a.out}
    with open(SUMMARY, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False)[:800])
    return 0


def _worker(args):
    return one(args[0], args[1])


if __name__ == '__main__':
    sys.exit(main())
