# -*- coding: utf-8 -*-
"""离线分析: 神谕流 vs 两种驱动流(已存npz)。"""
import numpy as np
import sys
sys.stdout.reconfigure(encoding='utf8')

orc = np.load(r'D:\temp\oracle_obstest0.npz')['x']
d_swap0 = np.load(r'D:\temp\drive_obstest0_oracleenv.npz')['x']
print('神谕 %d帧, swap0驱动 %d帧' % (len(orc), len(d_swap0)))

print('\n== 神谕: 回合事件附近 ==')
for k in range(5740, 5752):
    r = orc[k]
    print('  帧%d hp=%d/%d x=%.0f/%.0f act=%d/%d score=%d:%d w=%d/%d t=%d' % (
        k, r[0], r[1], r[2] / 10, r[3] / 10, r[4], r[5], r[6], r[7],
        r[8], r[9], r[10]))
print('  ...')
for k in range(10265, 10277):
    r = orc[k]
    print('  帧%d hp=%d/%d act=%d/%d score=%d:%d' % (k, r[0], r[1], r[4], r[5], r[6], r[7]))

print('\n== swap0驱动: 回合事件@8246 附近 ==')
for k in range(8240, 8252):
    r = d_swap0[k]
    print('  帧%d hp=%d/%d act=%d/%d score=%d:%d' % (k, r[0], r[1], r[4], r[5], r[6], r[7]))

print('\n== 神谕 前600帧 hp/位置 摘样 ==')
for k in range(0, 700, 50):
    r = orc[k]
    print('  帧%3d hp=%d/%d x=%.0f/%.0f act=%d/%d' % (
        k, r[0], r[1], r[2] / 10, r[3] / 10, r[4], r[5]))
print('\n== swap0驱动 前600帧 ==')
for k in range(0, 700, 50):
    r = d_swap0[k]
    print('  帧%3d hp=%d/%d x=%.0f/%.0f act=%d/%d' % (
        k, r[0], r[1], r[2] / 10, r[3] / 10, r[4], r[5]))

# 双向配对正确度: 前600帧逐帧匹配率(四种映射)
def match_rate(a, b, mirror=False):
    n = min(len(a), len(b))
    if mirror:
        # 比较左神谕 vs 右驱动(hp/x互换)
        cnt = tot = 0
        for i in range(n):
            tot += 1
            if (a[i][4] == b[i][5] and a[i][5] == b[i][4]
                    and a[i][2] == -b[i][3] + 12800):
                cnt += 1
        return cnt, tot
    cnt = sum(1 for i in range(n) if a[i][4] == b[i][4] and a[i][5] == b[i][5])
    return cnt, n

c, t = match_rate(orc[:600], d_swap0[:600])
print('\n动作列匹配(swap0): %d/%d' % (c, t))
