# -*- coding: utf-8 -*-
"""B2'(用户裁定2026-10-12): 原版游戏人测采集 — 行为断言.

背景: 训练mod路径在人测会话异常(渲染/帧率), 裁定改原版游戏采集+
特化版专供训练。本测试钉住 human_solo_collect 的关键契约(不起游戏):
  1. _archive: rep归档(复制成功返回路径, 失败返回None);
  2. _snapshot: replay树递归枚举(嵌套子目录含.rep);
  3. process_archive: monkeypatch resolve_rep(无游戏) → 报告条目落盘
     (md5/习惯字段/追加语义) + _processed_hashes幂等去重;
  4. mod切换往返: _switch_mods写oracle集 + _restore_mods逐字节恢复.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import human_solo_collect as H

FAILS = []


def check(name, cond, detail=''):
    print('%-52s %s %s' % (name, 'PASS' if cond else 'FAIL',
                           detail if not cond else ''))
    if not cond:
        FAILS.append(name)


tmp = tempfile.mkdtemp(prefix='hs_b2_')

# ---- 0. R77b: PORT必须是int(G2首版元组bug — bind当场TypeError) ----
check('PORT为int端口(reserved_port访问器)',
      isinstance(H.PORT, int) and 20800 <= H.PORT <= 21299,
      repr(H.PORT))

# ---- 1. _archive: 归档复制 ----
H.ARCHIVE = os.path.join(tmp, 'arch')
src_rep = os.path.join(tmp, 'a.rep')
open(src_rep, 'wb').write(b'\xD2' + b'\x00' * 127)
p1 = H._archive(src_rep)
check('archive返回路径且内容一致', p1 and os.path.exists(p1)
      and open(p1, 'rb').read() == open(src_rep, 'rb').read())
check('archive坏源返回None', H._archive(os.path.join(tmp, 'nope.rep')) is None)

# ---- 2. _snapshot: 递归枚举(嵌套) ----
H.REPLAY_DIR = os.path.join(tmp, 'replay')
os.makedirs(os.path.join(H.REPLAY_DIR, 'sub', 'deep'), exist_ok=True)
for rel in ('top.rep', os.path.join('sub', 's.rep'),
            os.path.join('sub', 'deep', 'd.rep'), 'ignore.txt'):
    open(os.path.join(H.REPLAY_DIR, rel), 'wb').write(b'x' * 16)
snap = H._snapshot()
check('snapshot递归含3个rep且排除非rep',
      len(snap) == 3 and any(p.endswith('deep\\d.rep') or
                             p.endswith('deep/d.rep') for p in snap))

# ---- 3. process_archive: 报告条目(无游戏, resolve打桩) ----
H.REPORT = os.path.join(tmp, 'report.json')


def fake_resolve(path):
    meta = {'char': 'suika', 'opp_char': 'reimu', 'mode': 2,
            'date': '10-12', 'n_frames_rep': 10}
    seq = [(i, 0, 1000, 0) for i in range(90)] + \
          [(i, 160, 1000, 0) for i in range(90, 120)]
    return meta, seq, (2, 1), None


H.resolve_rep = fake_resolve
entry = H.process_archive(p1)
data = json.load(open(H.REPORT, encoding='utf8'))
check('报告落盘且含条目', len(data) == 1)
e = data[0]
check('条目字段(char/md5/比分/解算帧数)',
      e['char'] == 'suika' and e['md5'] == H._md5(p1)
      and e['final_score_left_right'] == [2, 1]
      and e['resolved_frames'] == 120)
check('习惯字段经habit_detector真实检出',
      isinstance(e.get('habits'), list) and len(e['habits']) >= 1
      and all(k in ('wakeup_crouch_guard', 'wakeup_stand_guard',
                    'pressure_backjump', 'far_stand_guard',
                    'empty_spirit_attack') for k in e['habits']),
      str(e.get('habits')))
check('err透传到条目', e['err'] is None)

# 幂等: 同md5再处理一次应被_processed_hashes识别
H.process_archive(p1)
check('重复处理产生第二条(报告追加语义)',
      len(json.load(open(H.REPORT, encoding='utf8'))) == 2)
check('processed_hashes含该md5', H._md5(p1) in H._processed_hashes())

# ---- 4. mod切换往返(逐字节恢复) ----
H.ML = os.path.join(tmp, 'ML.json')
orig_json = '{"modules": {"modules/X/X.dll": {"enabled": true}}}'
open(H.ML, 'w', encoding='utf8', newline='').write(orig_json)
saved = H._switch_mods()
now = json.load(open(H.ML, encoding='utf8'))
check('switch后mod集==oracle观测集',
      sorted(k.split('/')[-1].replace('.dll', '')
             for k in now['modules']) == sorted(H.ORACLE_SET))
H._restore_mods(saved)
check('restore逐字节恢复', open(H.ML, 'rb').read()
      == orig_json.encode('utf8'))

print()
if FAILS:
    print('FAIL(%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('ALL PASS (10)')
