# -*- coding: utf-8 -*-
"""trailmod 连段包只读盘点 + 并入 task-79 语料 (不执行 exe/不改原文件)."""
import glob
import hashlib
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, r'D:\temp\soku_arch')
sys.path.insert(0, r'C:\Users\96120\Desktop\workplace\th123_rl')
from soku_arch.rep_file import parse_rep_file, inputs_by_side  # noqa

ROOT = r'D:\touhou\hisoutensoku2026-06-15\Trialmode连段包'
WORK = r'D:\temp\trailmod_work'
OUT = r'D:\temp\combo_corpus_trailmod_20261027.json'
MD = r'C:\Users\96120\Desktop\workplace\th123_rl\docs\_audit\trailmod_inventory_20261027.md'
ATK = (1 << 4) | (1 << 5) | (1 << 6) | (1 << 7)


def segs(seq, gap=10, minlen=3):
    out = []
    cur = 0
    last = -999
    for i, raw in enumerate(seq):
        raw = int(raw)
        if raw & ATK:
            if i - last <= gap:
                cur += 1
            else:
                if cur >= minlen:
                    out.append(cur)
                cur = 1
            last = i
        else:
            if cur and i - last > gap:
                if cur >= minlen:
                    out.append(cur)
                cur = 0
    if cur >= minlen:
        out.append(cur)
    return out


def rar_list(path):
    # 只读: rarfile 若可用; 否则 7z l; 都不执行解压到原目录
    try:
        import rarfile
        with rarfile.RarFile(path) as rf:
            return rf.namelist()
    except Exception:
        pass
    try:
        import subprocess
        r = subprocess.run(['7z', 'l', '-ba', path], capture_output=True,
                           text=True, timeout=60)
        if r.returncode == 0:
            return [l.split()[-1] for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        pass
    return None


def main():
    files = []
    for dirpath, dirs, fs in os.walk(ROOT):
        for f in fs:
            files.append(os.path.join(dirpath, f))
    rec = {'root': ROOT, 'files': len(files),
           'bytes': sum(os.path.getsize(p) for p in files),
           'by_ext': {}, 'zip': {}, 'rar': {}, 'rep': [],
           'json': [], 'notes': [], 'segments': 0, 'files_ok': 0,
           'files_fail': 0}
    for p in files:
        ext = os.path.splitext(p)[1].lower()
        rec['by_ext'][ext] = rec['by_ext'].get(ext, 0) + 1
        if ext == '.zip':
            try:
                with zipfile.ZipFile(p) as z:
                    names = z.namelist()
                rec['zip'][os.path.basename(p)] = {
                    'n': len(names),
                    'rep': sum(1 for n in names if n.lower().endswith('.rep')),
                    'json': sum(1 for n in names if n.lower().endswith('.json')),
                    'sample': names[:8]}
            except Exception as e:
                rec['notes'].append('zip fail %s %r' % (os.path.basename(p), e))
        elif ext == '.rar':
            names = rar_list(p)
            rec['rar'][os.path.basename(p)] = (
                {'n': len(names),
                 'sample': names[:8]} if names else {'error': 'unreadable/rar tool missing'})
        elif ext == '.json':
            try:
                d = json.load(open(p, encoding='utf-8'))
                rec['json'].append({'file': os.path.basename(p),
                                    'keys': list(d)[:10]
                                    if isinstance(d, dict) else 'list',
                                    'n': len(d) if hasattr(d, '__len__') else 0})
            except Exception as e:
                rec['notes'].append('json fail %r' % e)
        elif ext == '':
            # trialmode 连段定义(无扩展名 JSON): 只读解析
            try:
                d = json.load(open(p, encoding='utf-8'))
                if isinstance(d, dict) and 'expected' in d:
                    ch = (d.get('player') or {}).get('character') or \
                         (d.get('dummy') or {}).get('character')
                    rec.setdefault('trial_combos', []).append({
                        'file': os.path.relpath(p, ROOT),
                        'char': ch, 'type': d.get('type'),
                        'expected': d.get('expected'),
                        'frames': len(d.get('inputs') or []),
                        'explicit_inputs': 'inputs' in d,
                        'stage': d.get('stage')})
                    rec['trial_n'] = rec.get('trial_n', 0) + 1
                    if 'inputs' in d:
                        rec['trial_explicit'] = rec.get('trial_explicit', 0) + 1
                else:
                    rec['notes'].append('extless non-trial %s' %
                                        os.path.basename(p))
            except Exception as e:
                rec['notes'].append('extless fail %s %r' %
                                    (os.path.basename(p), e))
        elif ext == '.rep':
            try:
                r = parse_rep_file(p)
                arr = inputs_by_side(list(r.inputs))
                for side in (0, 1):
                    for L in segs(arr[:, side]):
                        rec['segments'] += 1
                        rec['rep'].append({'file': os.path.basename(p),
                                           'len': L})
                rec['files_ok'] += 1
            except Exception:
                rec['files_fail'] += 1
    rec['matrix_candidates'] = rec.get('trial_n', 0) + sum(
        v.get('rep', 0) + v.get('n', 0) for v in rec['zip'].values()
        if isinstance(v, dict)) + rec['segments']
    json.dump(rec, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    lines = ['# trailmod 连段包只读盘点（2026-10-27）', '',
             '- 路径 `%s`' % ROOT,
             '- 文件 %d / %.1fMB' % (rec['files'], rec['bytes'] / 1048576),
             '- 扩展: %s' % rec['by_ext'], '',
             '## zip 内容', '']
    for k, v in rec['zip'].items():
        lines.append('- %s: files=%s rep=%s json=%s' % (
            k, v.get('n'), v.get('rep'), v.get('json')))
    lines += ['', '## rar 内容', '']
    for k, v in rec['rar'].items():
        lines.append('- %s: %s' % (k, v))
    lines += ['', '## JSON 定义', '']
    for j in rec['json']:
        lines.append('- %s: keys=%s n=%s' % (j['file'], j['keys'], j['n']))
    lines += ['', '## trialmode 连段定义',
              '- trial_n=%d (explicit_inputs=%d)' % (rec.get('trial_n', 0), rec.get('trial_explicit', 0))]
    for t in (rec.get('trial_combos') or [])[:20]:
        lines.append('- %s | %s | frames=%s | %s' % (
            t['file'], t['char'], t['frames'], t['expected']))
    lines += ['', '## .rep', '- files_ok=%d fail=%d segments=%d' % (
        rec['files_ok'], rec['files_fail'], rec['segments']),
        '- 矩阵可用候选数(粗)= %d' % rec['matrix_candidates'],
        '', '说明：只读盘点；未执行 exe、未解压到原目录；rar 不可读时记录缺失。']
    io.open(MD, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(json.dumps({k: rec[k] for k in ('files', 'by_ext', 'segments',
                                          'files_ok', 'files_fail',
                                          'matrix_candidates')},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
