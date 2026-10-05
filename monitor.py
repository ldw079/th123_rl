# -*- coding: utf-8 -*-
"""训练质量监视器: 定期采集连接/日志指标/BC加载状态, 写入监视报告。
用法: monitor.py [间隔秒, 默认300]"""
import subprocess, sys, time, os, re, json
sys.stdout.reconfigure(encoding='utf8')

INTERVAL = int(sys.argv[1]) if len(sys.argv) > 1 else 300
REPORT = r'D:\temp\train_monitor.md'
LOGS = {ch: r'D:\temp\train_%s.log' % ch
        for ch in ('reimu', 'marisa', 'suika', 'reimu_exp')}
PAT = re.compile(
    r'\[ep\] 帧(\d+) 决策(\d+) 回报([\d.-]+) 熵([\d.]+) \|KL\|([\d.]+) '
    r'优势([\d.]+) 值损([\d.]+)')
MATCH = re.compile(r'\[matchup\] vs (\S+): (\d+)W-(\d+)L \((\d+)%\)')
BC = re.compile(r'\[BC\] 专家库 (\S+): (\d+)行')


def snapshot():
    r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                       encoding='gbk', errors='replace')
    # R19(审查2026-10-02): 原版取本端列但含':208'即收 — 对端临时端口
    # (如48416)也计入, 2个训练器(4条记录)即虚报3+; 且':208'漏掉209xx
    # (eval/probe流量不可见)。改: 只收本机mod监听段(20800-20999)端口。
    ports = set()
    for ln in (r.stdout or '').splitlines():
        if 'ESTABLISHED' not in ln:
            continue
        try:
            p = int(ln.split()[1].rsplit(':', 1)[-1])
        except (ValueError, IndexError):
            continue
        if 20800 <= p <= 20999:
            ports.add(p)
    ports = sorted(ports)
    lanes = {}
    for ch, p in LOGS.items():
        try:
            txt = open(p, encoding='utf-8', errors='replace').read()[-4000:]
        except OSError:
            lanes[ch] = {'error': 'log missing'}
            continue
        eps = PAT.findall(txt)
        ms = MATCH.findall(txt)
        bc = BC.findall(txt)
        d = {}
        if eps:
            last5 = eps[-5:]
            d['回报'] = round(sum(float(e[2]) for e in last5) / len(last5), 1)
            d['熵'] = round(sum(float(e[3]) for e in last5) / len(last5), 2)
            d['|KL|'] = round(sum(float(e[4]) for e in last5) / len(last5), 4)
            d['优势'] = round(sum(float(e[5]) for e in last5) / len(last5), 3)
            d['值损'] = round(sum(float(e[6]) for e in last5) / len(last5), 1)
            d['局数'] = len(eps)
        if ms:
            w, l = int(ms[-1][1]), int(ms[-1][2])
            d['胜率'] = '%dW-%dL(%d%%)' % (w, l, int(ms[-1][3]))
        if bc:
            d['BC'] = '%s行' % bc[-1][1]
        elif '[BC] 无专家库' in txt:
            d['BC'] = '无'
        lanes[ch] = d
    return ports, lanes


def report(ports, lanes):
    lines = ['## 训练监视 %s' % time.strftime('%H:%M:%S'), '']
    lines.append('连接: %s' % (ports or '无!'))
    for ch, d in sorted(lanes.items()):
        if 'error' in d:
            lines.append('- **%s**: %s' % (ch, d['error']))
            continue
        parts = ['%s=%s' % (k, v) for k, v in sorted(d.items())]
        lines.append('- **%s**: %s' % (ch, ' | '.join(parts)))
    txt = '\n'.join(lines) + '\n'
    with open(REPORT, 'a', encoding='utf8') as f:
        f.write(txt + '\n')
    print(txt)


if __name__ == '__main__':
    print('监视器启动(间隔%d秒, 报告→%s)' % (INTERVAL, REPORT))
    while True:
        p, l = snapshot()
        report(p, l)
        time.sleep(INTERVAL)
