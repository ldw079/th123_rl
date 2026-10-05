# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf8')
src = open('run_parallel.py', encoding='utf8').read()
i = src.find('train_tm')
print(src[max(0, i - 600):i + 900])
