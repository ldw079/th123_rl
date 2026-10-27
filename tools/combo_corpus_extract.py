# -*- coding: utf-8 -*-
"""task-79 连段语料抽样提取（只读）: 人类 replay 输入段→连段候选.

单进程低优先级; 抽样 3000 场(各目录分层) + oracle 191; 输出:
  D:\temp\combo_corpus_sample_20261027.json (清单/频次/矩阵草稿)
连段候选定义(proxy): 己方连续攻击输入(A/B/C/dash)片段, 间隔≤10帧, 长度≥3
  → 记录 char/段长/键位/起手方向。
"""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, r'D:\temp\soku_arch')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl')
from soku_arch.rep_file import parse_rep_file, inputs_by_side  # noqa

ROOT = r'D:\TR丹尼尔棉咖啡等录像精选'
ORACLE = r'C:\Users\96120\Desktop\workplace\th123_rl\data\oracle\shards'
OUT = r'D:\temp\combo_corpus_sample_20261027.json'
LOG = r'D:\temp\combo_corpus_sample_20261027.log'
N_SAMPLE = 3000
ATK = (1 << 4) | (1 << 5) | (1 << 6) | (1 << 7)  # A/B/C/dash


def char_map():
    from train_tm import CHAR_LIBS
    return {l['id']: n for n, l in CHAR_LIBS.items()}


def segs(seq, gap=10, minlen=3):
    out = []
    cur = 0
    last_atk = -999
    for i, raw in enumerate(seq):
        raw = int(raw)
        if raw & ATK:
            if i - last_atk <= gap:
                cur += 1
            else:
                if cur >= minlen:
                    out.append(cur)
                cur = 1
            last_atk = i
        else:
            if cur and i - last_atk > gap:
                if cur >= minlen:
                    out.append(cur)
                cur = 0
    if cur >= minlen:
        out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=N_SAMPLE)
    ap.add_argument('--out', default=OUT)
    a = ap.parse_args()
    log = open(LOG, 'w', encoding='utf-8')
    cmap = char_map()
    files = []
    for d in ('其他', '国内', '日本'):
        fs = glob.glob(os.path.join(ROOT, d, '**', '*.rep'), recursive=True)
        fs = sorted(fs)
        if a.n >= 60000:
            files += fs
        else:
            step = max(1, len(fs) // max(1, a.n // 3))
            files += fs[::step][:max(1, a.n // 3)]
    oracle = sorted(glob.glob(os.path.join(ORACLE, '*.npz')))[:191]
    rec = {'human_sample': len(files), 'oracle': len(oracle),
           'segments': 0, 'by_char': {}, 'seg_len_hist': {},
           'key_hist': {}, 'matrix': {}, 'files_ok': 0, 'files_fail': 0,
           'ts': time.time()}
    t0 = time.time()
    for n, p in enumerate(files):
        try:
            rep = parse_rep_file(p)
            arr = inputs_by_side(list(rep.inputs))
            side = 0 if 'mian' in os.path.basename(p).lower().split(' vs ')[0] else 1
            ch = cmap.get(int(rep.char_x if side == 0 else rep.char_y), '?')
            for L in segs(arr[:, side]):
                rec['segments'] += 1
                rec['by_char'][ch] = rec['by_char'].get(ch, 0) + 1
                b = str(min(64, (L // 3) * 3))
                rec['seg_len_hist'][b] = rec['seg_len_hist'].get(b, 0) + 1
            rec['files_ok'] += 1
        except Exception:
            rec['files_fail'] += 1
        if (n + 1) % 200 == 0:
            log.write('[%s] %d/%d seg=%d ok=%d fail=%d %.0fs\n' % (
                time.strftime('%H:%M:%S'), n + 1, len(files), rec['segments'],
                rec['files_ok'], rec['files_fail'], time.time() - t0))
            log.flush()
    # oracle proxy: x 11维无输入段语义 → 仅统计局数(不伪造连段)
    rec['oracle_note'] = 'oracle x=11维帧特征, 无输入段语义; 不计连段, 仅作局数样本'
    json.dump(rec, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    log.write('DONE %s\n' % json.dumps({k: rec[k] for k in
              ('human_sample', 'files_ok', 'files_fail', 'segments')}))
    log.close()
    print(json.dumps({k: rec[k] for k in ('human_sample', 'files_ok',
                                          'files_fail', 'segments',
                                          'by_char')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
