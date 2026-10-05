# -*- coding: utf-8 -*-
"""模型水平一览: 一条命令查看所有角色战绩/学习指标/COM评估/模型状态。
用法: D:\temp\pyenv\python.exe -X utf8 status.py [--com N局]
"""
import sys, os, re, time, glob, subprocess
sys.stdout.reconfigure(encoding='utf8')

BASE = r'%USERPROFILE%\Desktop\workplace\th123_rl'
MODELS = r'D:\temp\th123_models'
REPORTS = os.path.join(MODELS, 'reports')

def fmt_age(ts):
    dt = time.time() - ts
    if dt < 60:
        return '%d秒前' % dt
    if dt < 3600:
        return '%d分钟前' % (dt / 60)
    return '%.1f小时前' % (dt / 3600)

print('═' * 62)
print('  模型水平一览 — %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
print('═' * 62)

# ---- 1. 连接状态 ----
r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                   encoding='gbk', errors='replace')
# R19(审查2026-10-02): 只收本机mod监听段(20800-20999) — 原版把对端
# 临时端口也计入(2训练器=4条记录即虚报"运行中")且':208'漏掉209xx段
_ports = set()
for ln in (r.stdout or '').splitlines():
    if 'ESTABLISHED' not in ln:
        continue
    try:
        _p = int(ln.split()[1].rsplit(':', 1)[-1])
    except (ValueError, IndexError):
        continue
    if 20800 <= _p <= 20999:
        _ports.add(_p)
ports = sorted(_ports)
status = '运行中' if len(ports) >= 3 else '部分停止!'
print('\n【训练状态】%s (连接: %s)' % (status, ', '.join(ports) or '无'))

# ---- 2. 各角色战绩与学习指标 ----
print('\n【各角色】')
print('%-8s %-8s %-22s %s' % ('角色', '模型更新', '战绩', '学习指标'))
print('-' * 62)
for ch in ('reimu', 'marisa', 'suika'):
    # 模型文件
    mp = os.path.join(MODELS, 'model_ppo_%s.npz' % ch)
    model_age = fmt_age(os.path.getmtime(mp)) if os.path.exists(mp) else '不存在'

    # 日志
    lp = r'D:\temp\train_%s.log' % ch
    wr, metrics = '-', '-'
    if os.path.exists(lp):
        txt = open(lp, encoding='utf-8', errors='replace').read()
        ms = re.findall(r'\[matchup\] vs (\S+): (\d+)W-(\d+)L \((\d+)%\)', txt)
        if ms:
            m = ms[-1]
            wr = '%sW-%sL(%s%%)' % (m[1], m[2], m[3])
        eps = re.findall(
            r'\[ep\] 帧\d+ 决策\d+ 回报([\d.-]+) 熵([\d.]+) '
            r'\|KL\|([\d.]+) \w+ ([\d.]+) 值损([\d.]+)', txt)
        if eps:
            e = eps[-1]
            metrics = '熵%s KL%s 值损%s' % (e[1][:4], e[2][:5], e[4][:5])
    print('%-8s %-8s %-22s %s' % (ch, model_age, wr, metrics))

# ---- 3. COM 评估(最新) ----
ce = os.path.join(REPORTS, 'com_eval_log.md')
if os.path.exists(ce):
    txt = open(ce, encoding='utf-8', errors='replace').read()
    blocks = txt.strip().split('## ')
    if len(blocks) > 1:
        latest = blocks[-1].strip().splitlines()
        print('\n【COM 评估】%s' % latest[0])
        for l in latest[1:4]:
            if l.strip():
                print('  %s' % l.strip())

# ---- 4. 对手池快照 ----
pool = os.path.join(MODELS, 'pool')
if os.path.isdir(pool):
    print('\n【对手池】')
    for d in sorted(os.listdir(pool)):
        sub = os.path.join(pool, d)
        if os.path.isdir(sub):
            snaps = os.listdir(sub)
            if snaps:
                latest_f = max(snaps)
                age = fmt_age(os.path.getmtime(os.path.join(sub, latest_f)))
                print('  %-8s %d快照 (最新%s %s)' % (d, len(snaps), latest_f[:15], age))

# ---- 5. 自博弈对战矩阵 ----
matchups = sorted(glob.glob(os.path.join(REPORTS, 'matchup_*.json')))
if matchups:
    import json
    try:
        m = json.load(open(matchups[-1], encoding='utf-8'))
        ts = os.path.basename(matchups[-1]).replace('matchup_', '').replace('.json', '')
        print('\n【对战矩阵】%s' % ts)
        chars = ['reimu', 'marisa', 'suika']
        print('  %-8s' % '', '  '.join('%-8s' % c for c in chars))
        for a in chars:
            row = []
            for b in chars:
                key = '%s>%s' % (a, b)
                if key in m and m[key].get('winrate') is not None:
                    row.append('%-8s' % ('%.0f%%' % (m[key]['winrate'] * 100)))
                else:
                    row.append('%-8s' % '-')
            print('  %-8s%s' % (a, '  '.join(row)))
    except Exception:
        pass

# ---- 6. BC 数据 ----
bc_dir = os.path.join(BASE, 'data', 'bc')
if os.path.isdir(bc_dir):
    print('\n【BC 专家数据】')
    for ch in ('reimu', 'marisa', 'suika'):
        p = os.path.join(bc_dir, 'bc_%s.npz' % ch)
        if os.path.exists(p):
            import numpy as np
            d = np.load(p, allow_pickle=False)
            print('  %-8s %d行' % (ch, len(d['Y'])))

print('\n' + '═' * 62)
print('  用法: python status.py [--com N] 运行N局COM评估')
print('═' * 62)

# ---- 可选: 即时COM评估 ----
if '--com' in sys.argv:
    idx = sys.argv.index('--com')
    n = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 5
    print('\n【即时 COM 评估(%d局/角色)】' % n)
    sys.path.insert(0, BASE)
    sys.path.insert(0, r'D:\temp\soku_arch')
    from outer_loop import com_eval, current_model
    for ch in ('reimu', 'marisa', 'suika'):
        try:
            r = com_eval(ch, games=n)
            total = r['wins'] + r['losses']
            wr = r['wins'] / total * 100 if total else 0
            print('  %-8s %dW-%dL (%.0f%%)' % (ch, r['wins'], r['losses'], wr))
        except Exception as e:
            print('  %-8s 失败: %s' % (ch, str(e)[:60]))
