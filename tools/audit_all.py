# -*- coding: utf-8 -*-
"""审计功能集合(用户2026-10-07指令: 定时审计已关, 功能归本脚本手动调用)。

开头跑综合仪表板(status_dashboard), 后接深度审计段:
  A. 综合仪表板(一屏全貌: 舰队/角色/特征/GRU/行为/数据层)
  1. 策略树审计(红线)
  2. 日志尾读(批更新/奖励/matchup/异常)
  3. COM难度阶梯
  4. fleet附录(episodes/快照/宏计数)
  5. 特征活性巡检(oracle重放)

用法: python tools/audit_all.py [--chars reimu,marisa,suika] [--quick]
  --quick  跳过耗时项(活性巡检/策略树)
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

PY = sys.executable
RED_BASE = {'reimu': 7, 'marisa': 12, 'suika': 13}   # 基线(10-06停机)


def sec(t):
    print('\n' + '=' * 8, t, '=' * 8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chars', default='reimu,marisa,suika')
    ap.add_argument('--quick', action='store_true',
                    help='跳过耗时项')
    args = ap.parse_args()
    chars = args.chars.split(',')

    # A. 综合仪表板(一屏全貌)
    sec('A 综合仪表板')
    r = subprocess.run(
        [PY, '-X', 'utf8', os.path.join(HERE, 'status_dashboard.py')]
        + (['--quick'] if args.quick else []),
        cwd=ROOT)

    # 1. 训练健康
    sec('1 训练健康')
    r = subprocess.run(['tasklist'], capture_output=True,
                       text=False)
    out = r.stdout.decode('gbk', errors='replace')
    n_game = out.count('th123.exe')
    n_py = sum(1 for line in out.splitlines()
               if line.startswith('python.exe'))
    mode = ('暂停(预期0)' if n_game == 0 and n_py == 0
            else '运行中' if n_game >= 2 else '!! 异常: 实例不足')
    print('th123×%d python×%d → %s' % (n_game, n_py, mode))

    # 2. 策略树审计
    sec('2 策略树审计(红线 vs 基线%s)' % RED_BASE)
    for ch in chars:
        r = subprocess.run(
            [PY, '-X', 'utf8', os.path.join(ROOT, 'standard_tree.py'),
             'audit', ch], capture_output=True, text=False,
            cwd=ROOT)
        out = r.stdout.decode('utf-8', errors='replace')
        red = [l for l in out.splitlines() if '红线' in l]
        n = 0
        if red:
            import re
            m = re.search(r'(\d+)个节点', red[0])
            n = int(m.group(1)) if m else -1
        flag = ('↑增加!!' if n > RED_BASE.get(ch, 99)
                else 'OK' if n <= RED_BASE.get(ch, 99) else '?')
        print('%-8s 红线%d (基线%d) %s'
              % (ch, n, RED_BASE.get(ch, -1), flag))
        if red:
            print('   ', red[0].strip()[:120])

    # 3. 日志尾读
    sec('3 日志尾读')
    for ch in chars:
        for path in (r'D:\temp\learner_%s.log' % ch,
                     r'D:\temp\train_%s.log' % ch):
            if os.path.exists(path):
                mt = time.strftime('%m-%d %H:%M', time.localtime(
                    os.path.getmtime(path)))
                lines = io.open(path, encoding='utf-8',
                                errors='replace').read().splitlines()
                tail = lines[-200:]
                ep = [l for l in tail if '决策' in l]
                rew = [l for l in tail if '奖励成分' in l]
                mu = [l for l in tail if 'matchup' in l.lower()]
                arch = [l for l in tail if '流派战绩' in l]
                err = [l for l in tail if '警报' in l or '异常' in l]
                print('--- %s (mtime %s) ---' % (ch, mt))
                for l in (ep or ['无批更新'])[-2:]:
                    print('  批', l.strip()[:100])
                for l in (rew or ['无奖励行'])[-1:]:
                    print('  奖', l.strip()[:105])
                for l in mu[-2:]:
                    print('  对', l.strip()[:90])
                for l in arch[-2:]:
                    print('  流派', l.strip()[:90])
                for l in err[-2:]:
                    print('  !!', l.strip()[:100])
                break

    # 4. COM难度
    sec('4 COM难度阶梯')
    r = subprocess.run([PY, '-X', 'utf8',
                        os.path.join(HERE, 'com_ladder_report.py')],
                       capture_output=True, cwd=ROOT)
    print(r.stdout.decode('utf-8', errors='replace'))

    # 5. fleet附录(episodes积压/快照版本)
    sec('5 fleet状态')
    eps = glob.glob(r'D:\temp\th123_models\fleet\episodes\*.npz')
    print('episode积压: %d' % len(eps))
    for ch in chars:
        vf = r'D:\temp\th123_models\fleet\snap_%s\version' % ch
        if os.path.exists(vf):
            print('  %s 快照v%s' % (ch, open(vf).read().strip()))

    # 6. 特征活性巡检(P2防复发级, 从零#4建议#5 — ~1.5min/角色;
    #    应活段恒死=exit 1在此显红)
    sec('6 特征活性巡检(oracle重放)')
    r = subprocess.run([PY, '-X', 'utf8',
                        os.path.join(HERE, 'feature_liveness.py'),
                        '--shards', '6', '--char', '0'],
                       capture_output=True, cwd=ROOT)
    out = r.stdout.decode('utf-8', errors='replace')
    for ln in out.splitlines():
        if 'ALERT' in ln or '巡检' in ln:
            print(' ', ln.strip())
    if r.returncode != 0:
        print('  !! 巡检红 — 应活段恒死(P0-1类), 见上')

    print('\n(基线红线可在本文件RED_BASE更新; 历次周期诊断内容已全集于本脚本)')


if __name__ == '__main__':
    main()
