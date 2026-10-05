# -*- coding: utf-8 -*-
"""调试: 逐个候选子串打印 find_windows 结果。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
from capture import find_windows

for sub in config.TITLE_CANDIDATES:
    ws = find_windows(sub)
    print("%r -> %s" % (sub, [t for _, t in ws]))
