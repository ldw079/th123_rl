# -*- coding: utf-8 -*-
"""从movepattern XML生成 per角色 动作桶表 → action_tables.py(数据模块)。
桶: attack(体术/技能) · shot(射击技动画) — 按每move首帧图像前缀归类。
防御/受击/移动系为全角色通用id(见opp_model.py头部), 不入本表。"""
import io
import os
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf8')
ROOT = r'D:\touhou\hisoutensoku2026-06-15\美化包\_sokuExtractedFiles\data\character'
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHARS = {'reimu': 'reimu', 'marisa': 'marisa', 'suika': 'suika',
         # R44(2026-10-04): 六新角色入表(铃仙的XML目录名=udonge)
         'sakuya': 'sakuya', 'patchouli': 'patchouli', 'yuyuko': 'yuyuko',
         'reisen': 'udonge', 'komachi': 'komachi', 'tenshi': 'tenshi',
         # R45(2026-10-04): 剩余11角色(琪露诺=chirno, 美铃=meirin)
         'alice': 'alice', 'youmu': 'youmu', 'remilia': 'remilia',
         'yukari': 'yukari', 'aya': 'aya', 'iku': 'iku', 'sanae': 'sanae',
         'cirno': 'chirno', 'meiling': 'meirin', 'utsuho': 'utsuho',
         'suwako': 'suwako'}

out = ['# -*- coding: utf-8 -*-',
       '"""角色动作桶表 — tools/gen_action_tables.py 从解包movepattern',
       'XML自动生成(权威源, 勿手改; 重新生成: 运行该工具)。"""']
out.append('')
for ch, xdir in CHARS.items():
    # R44: 个别XML的image属性含Shift-JIS高位字节(如patchouli弹幕图名
    # bulletI\x82\x82000) — 按ASCII替换为下划线后解析(只影响图像名,
    # 帧号/hitbox数据不受影响)
    raw = open(os.path.join(ROOT, xdir, '%s.xml' % xdir), 'rb').read()
    clean = bytes(b if 0x20 <= b <= 0x7e or b in (0x09, 0x0a, 0x0d)
                  else 0x5f for b in raw)
    root = ET.fromstring(clean)
    buckets = {'attack': [], 'shot': []}
    reach = {}
    reach_v = {}
    for mv in root.iter('move'):
        mid = int(mv.get('id'))
        pres = set()
        mx = 0
        my = 0
        for f in mv.iter('frame'):
            im = f.get('image')
            if im:
                pres.add(os.path.splitext(im.strip())[0].lower())
            # R24: 每帧hit.box的right/left最大绝对值=横向到达;
            # R25(用户提醒: 判定二维): up/down最大绝对值=纵向到达
            hb = f.find('hit')
            if hb is not None:
                for b in hb.findall('box'):
                    mx = max(mx, abs(int(b.get('right'))),
                             abs(int(b.get('left'))))
                    my = max(my, abs(int(b.get('up'))),
                             abs(int(b.get('down'))))
        # 任一帧含该类动画即算(起手帧常为stand姿势, 首帧规则会漏分);
        # attack优先(混合动画按主语义归攻击)
        if any(p.startswith('attack') for p in pres):
            buckets['attack'].append(mid)
        elif any(p.startswith('shot') for p in pres):
            buckets['shot'].append(mid)
        if mx > 0:
            reach[mid] = mx
        if my > 0:
            reach_v[mid] = my
    out.append('%s_ATTACK_IDS = frozenset(%r)' % (ch, sorted(set(buckets['attack']))))
    out.append('%s_SHOT_IDS = frozenset(%r)' % (ch, sorted(set(buckets['shot']))))
    out.append('%s_REACH = %r' % (ch, dict(sorted(reach.items()))))
    out.append('%s_REACH_V = %r' % (ch, dict(sorted(reach_v.items()))))
    print('%s: attack %d个, shot %d个, reach %d个, reach_v %d个'
          % (ch, len(set(buckets['attack'])), len(set(buckets['shot'])),
             len(reach), len(reach_v)))

out.append('')
out.append('CHAR_ACTION_TABLES = {')
for ch in CHARS:
    out.append("    '%s': {'attack': %s_ATTACK_IDS, 'shot': %s_SHOT_IDS,"
               " 'reach': %s_REACH, 'reach_v': %s_REACH_V},"
               % (ch, ch, ch, ch, ch))
out.append('}')
p = os.path.join(HERE, 'action_tables.py')
io.open(p, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('→', p)
