# -*- coding: utf-8 -*-
import ast, sys
sys.stdout.reconfigure(encoding='utf8')
for f in ('outer_loop.py', 'standard_tree.py', 'train_tm.py'):
    p = r'%USERPROFILE%\Desktop\workplace\th123_rl' + '\\' + f
    ast.parse(open(p, encoding='utf-8').read())
    print('%s: 语法OK' % f)
