# -*- coding: utf-8 -*-
import time, sys, os
sys.stdout.reconfigure(encoding='utf8')
p = r'D:\temp\soku_arch\logs\mod_trace.log'
s1 = os.path.getsize(p)
t1 = time.time()
time.sleep(6)
s2 = os.path.getsize(p)
t2 = time.time()
rate = (s2 - s1) / (t2 - t1)
print('trace增长 %.1f B/s' % rate)
print('CBattle行长约48B, 每行=120帧逻辑')
print('=> 逻辑帧率约 %.0f fps (480tps应≈500+, 实时=62)' % (rate / 48 * 120))
