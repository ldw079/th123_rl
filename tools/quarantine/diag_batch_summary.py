# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding='utf8')
rows = []
for ln in open(r'%USERPROFILE%\Desktop\workplace\th123_rl\data\oracle\manifest_lane0.jsonl',
               encoding='utf8'):
    try:
        rows.append(json.loads(ln))
    except Exception:
        pass
print('总条目:', len(rows))
ok = [r for r in rows if r.get('err') is None and r['frames'] > 100]
match = [r for r in rows if r.get('match') is True]
mismatch = [r for r in rows if r.get('match') is False]
unknown = [r for r in rows if r.get('match') is None]
errs = [r for r in rows if r.get('err')]
print('成功局: %d, 错误局: %d' % (len(ok), len(errs)))
print('比分核对: 一致=%d 不一致=%d 无文件名比分=%d' % (len(match), len(mismatch), len(unknown)))
for r in mismatch[:10]:
    print('  不一致:', r['rep'][:60], '终局', r['score_final'], 'vs 文件名', r['score_filename'])
for r in errs[:10]:
    print('  错误:', r['rep'][:50], r['err'], 'frames=', r['frames'])
tot = sum(r['frames'] for r in ok)
print('总帧数: %d (%.1f小时游戏时间)' % (tot, tot / 62 / 3600))
