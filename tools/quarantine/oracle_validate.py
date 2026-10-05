# -*- coding: utf-8 -*-
"""选两个不同比分的专家rep, 依次跑神谕验证比分==文件名。"""
import os, re, sys, shutil
sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, r'%USERPROFILE%\Desktop\workplace\th123_rl')
import oracle_observe as oo

root = r'D:\temp\expert_reps'
picks = []
pat = re.compile(r'\((\d)︰(\d)_[胜负]\)')
for fn in sorted(os.listdir(root)):
    if not fn.endswith('.rep'):
        continue
    m = pat.search(fn)
    if not m or m.group(1) == m.group(2):
        continue
    b = open(os.path.join(root, fn), 'rb').read(16)
    if b[0] != 0xD2:
        continue
    key = (int(m.group(1)), int(m.group(2)))
    # 要不同比分形态: 一个2:1, 一个2:0, 角色不同于10/1
    if key == (2, 1) and not any(k == (2, 1) for k, _ in picks) and b[14] not in (10,):
        picks.append((key, os.path.join(root, fn)))
    elif key == (2, 0) and not any(k == (2, 0) for k, _ in picks) and b[14] not in (10,):
        picks.append((key, os.path.join(root, fn)))
    if len(picks) >= 2:
        break

for key, path in picks:
    print('\n######## 预期比分 %d:%d  %s' % (key[0], key[1],
          os.path.basename(path)[:70]))
    oo.ORACLE_SET = oo.ORACLE_SET
    import types
    sys.argv = ['oracle_observe.py', path, '20990', r'D:\temp\oracle_val_%d%d.npz' % key,
                '--full']
    try:
        oo.main()
    except SystemExit:
        pass
    except Exception as e:
        print('[异常] %s' % e)
