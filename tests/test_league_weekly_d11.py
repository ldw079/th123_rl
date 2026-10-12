# -*- coding: utf-8 -*-
"""D1-1(未决方案§D) 配对测试: league_weekly 解析+两指标.

覆盖:
  1. league重算块解析(label/COM/W-L/块边界)
  2. 固化指数(单label份额; >50%告警)
  3. char级聚合+末位保护线(<30%且≥4局触发)
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.stdout.reconfigure(encoding='utf8')

from tools import league_weekly as lw

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAIL: %s" % label
    PASS += 1
    print("[PASS] %s" % label)


def main():
    tmp = tempfile.mkdtemp()
    log = os.path.join(tmp, 'sup.log')
    body = """[10-12 10:00:00] league重算:   COM                              0W- 16L (0%) 权重1.00
  reimu@20261008_202818            0W-  7L (0%) 权重1.00
  suika@20261008_202926            4W-  0L (100%) 权重0.50
[10-12 11:00:00] league分配: {'reimu': 1}
[10-12 12:00:00] league重算:   marisa@20261008_202815           1W-  4L (20%) 权重0.72
  suika@20261008_202926            2W-  2L (50%) 权重0.72
  sakuya@seed_20261011             6W-  0L (100%) 权重0.50
"""
    open(log, 'w', encoding='utf8').write(body)
    lw.SUP_LOG = log
    blocks = lw.parse_league_blocks(log)
    ok(len(blocks) == 2 and blocks[0]['rows'][0][0] == 'COM'
       and blocks[0]['rows'][0][1] == 0 and blocks[0]['rows'][0][2] == 16,
       '块解析(2块, COM 0-16)')
    rep = lw.analyze(blocks)
    ok(rep['total_games'] == (0 + 16) + (0 + 7) + (4 + 0) + (1 + 4)
       + (2 + 2) + (6 + 0) == 42, '总局数42')
    # 固化: 最大单label=sakuya 6局? COM 16局 → COM份额16/42=0.381
    ok(abs(rep['consolidation_index'] - 16 / 42) < 1e-3   # 工具3位舍入
       and rep['top_label'] == 'COM',
       '固化指数=COM份额16/42=%.3f' % rep['consolidation_index'])
    # char聚合: suika 6W-0L(100%) / reimu 0W-7L(0%<30%且7局→保护线) /
    # marisa 1W-4L(20%且5局→保护线)
    ca = rep['char_agg']
    ok(ca['suika']['w'] == 6 and ca['suika']['l'] == 2
       and ca['reimu']['w'] == 0 and ca['reimu']['l'] == 7,
       'char级聚合跨块累计(suika 6-2 / reimu 0-7)')
    ok(set(rep['floor_breach']) >= {'reimu 0%(0W-7L)', 'marisa 20%(1W-4L)'}
       and all('sakuya' not in x for x in rep['floor_breach']),
       '末位保护线触发reimu/marisa, 不触发sakuya(胜率达标)')

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    print("==== %d PASS / 0 FAIL ====" % PASS)


if __name__ == "__main__":
    main()
