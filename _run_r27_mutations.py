# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'tools'))
import gate_selftest as gs

_FULL = list(gs.MUTATIONS)
gs.MUTATIONS = [m for m in _FULL if 'R26' in m[3] or 'R27' in m[3]]
print("定向变异自检: %d条" % len(gs.MUTATIONS))
sys.exit(gs.main())
