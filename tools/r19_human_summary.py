# -*- coding: utf-8 -*-
"""R19 人测赛后摘要: 读取最新 human_match_v2 会话 JSON + 录像, 生成摘要."""
import glob
import json
import os
import sys

SESS = r'C:\Users\96120\Desktop\workplace\th123_rl\tools\human_match_sessions\sess_*.json'
REPS = r'D:\temp\th123_models\human_reps\*.rep'
OUT = r'D:\temp\r19_human_summary_20261027.md'


def main():
    files = sorted(glob.glob(SESS), key=os.path.getmtime)
    if not files:
        print('NO_SESSION')
        return 1
    # 取最近非 _hl 会话（live）; 无则最新
    live = [p for p in files if '_hl' not in os.path.basename(p)]
    p = (live or files)[-1]
    d = json.load(open(p, encoding='utf-8'))
    reps = sorted(glob.glob(REPS), key=os.path.getmtime)
    lines = ['# R19 人测摘要（自动生成）', '',
             '- 会话 JSON: `%s`' % p,
             '- 时间: %s | char=%s | 帧数=%s' % (
                 d.get('ts'), d.get('char'), d.get('frames')),
             '- 模型: `%s` source=%s' % (d.get('model_path'),
                                        d.get('model_source')),
             '- model_stamp: `%s`' % json.dumps(d.get('model_stamp'),
                                               ensure_ascii=False),
             '- 检测: L=%s / R=%s', ]
    lines[-1] = '- 检测: L=%s / R=%s' % (d.get('detected', {}).get('p1_char'),
                                          d.get('detected', {}).get('p2_char'))
    lines += ['- **系列: 人%d - 模型%d** | matches=%s' % (
        d.get('human_wins', 0), d.get('model_wins', 0), d.get('matches')),
        '- R1 协议: %s' % d.get('protocol'),
        '- 录像 rep 数: %d（%s）' % (len(reps),
                                ', '.join(os.path.basename(x) for x in reps[-3:])),
        '',
        '## 败因/漏洞候选（自动粗筛）',
        '- 会话未记录逐局细节，需结合 rep 回放/帧日志人工分析；先看人胜/模型胜。',
        '',
        '## 待用户判断（yes/no）',
        '1) 行为是否比基线自然/有改善？',
        '2) 哪些操作/连段模型做不到？',
        '3) 连段/压制是否自然？',
        '4) 是否发现不公平/读输入/作弊？',
        '5) 是否愿意作为本轮 R19 验收通过？']
    open(OUT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('OUT', OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
