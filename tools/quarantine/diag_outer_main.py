# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf8')
src = open(r'%USERPROFILE%\Desktop\workplace\th123_rl\outer_loop.py',
           encoding='utf8').read()
i = src.find('def main')
if i < 0:
    i = src.find('__main__')
print(src[max(0, i):i + 2500])
