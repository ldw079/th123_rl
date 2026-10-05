# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf8')
src = open(r'%USERPROFILE%\Desktop\workplace\th123_rl\outer_loop.py',
           encoding='utf8').read()
i = src.find('outer_loop.lock')
print(src[max(0, i - 900):i + 400])
