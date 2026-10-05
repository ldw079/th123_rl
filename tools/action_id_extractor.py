# -*- coding: utf-8 -*-
"""从解包的movepattern XML提取 动作ID→语义 类目表。
数据源: 美化包_sokuExtractedFiles/data/character/<char>/<char>.xml
每个<move id=N>的帧引用图像名(stand/walkBack/guardUpper/attackA/...),
图像名前缀=动作语义 — 这是游戏自身的动作定义, 属R4级权威源(非实测推断)。
输出: docs/action_ids_<char>.md + 语义桶汇总(供代码ID集校准)。"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf8')
ROOT = r'D:\touhou\hisoutensoku2026-06-15\美化包\_sokuExtractedFiles\data\character'
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'docs')

# 图像名前缀 → 语义类目(按 Soku 动画命名惯例)
PREFIX_MAP = [
    ('standUp', '起身'),
    ('stand', '站立/姿态'),
    ('sit', '蹲'),
    ('walkBack', '后退走'),
    ('walkFront', '前进走'),
    ('dashBackAir', '空中后冲'),
    ('dashFrontAir', '空前冲'),
    ('dashBack', '后冲'),
    ('dashFront', '前冲'),
    ('dashStop', '冲刹'),
    ('jumpBack', '后跳'),
    ('jumpFront', '前跳'),
    ('jump', '跳跃/滞空'),
    ('guardUpperB', '立防防御受击'),
    ('guardUnderB', '蹲防防御受击'),
    ('guardBAir', '空防防御受击'),
    ('guardBUpper', '立防防御受击'),
    ('guardBUnder', '蹲防防御受击'),
    ('guardAir', '空防姿态'),
    ('guardUpper', '立防姿态'),
    ('guardUnder', '蹲防姿态'),
    ('guardObject', '防御物'),
    ('guard', '防御(其它)'),
    ('hitSit', '受击蹲姿'),
    ('hitUpper', '受击上段'),
    ('hitUnder', '受击下段'),
    ('hitAir', '受击空中'),
    ('hitSpin', '受击旋转'),
    ('hit', '受击(其它)'),
    ('down', '倒地'),
    ('crash', '撞墙'),
    ('invin', '无敌'),
    ('attack', '攻击'),
    ('shot', '射击(弹幕技)'),
    ('bullet', '弹幕实体'),
    ('spell', '符卡'),
    ('emotion', '表情'),
    ('object', '物件'),
    ('face', '立绘'),
    ('stand', '站立/姿态'),   # 兜底
]


def classify(imgs):
    cats = set()
    for im in imgs:
        base = os.path.splitext(os.path.basename(im.strip()))[0]
        for pre, cat in PREFIX_MAP:
            if base.startswith(pre):
                cats.add(cat)
                break
        else:
            cats.add('?')
    return cats


def main():
    chars = sys.argv[1:] or ['reimu', 'marisa', 'suika']
    for ch in chars:
        p = os.path.join(ROOT, ch, '%s.xml' % ch)
        if not os.path.exists(p):
            print('%s: 无xml' % ch)
            continue
        tree = ET.parse(p)
        rows = []
        for mv in tree.getroot().iter('move'):
            mid = int(mv.get('id'))
            imgs = [f.get('image') for f in mv.iter('frame')
                    if f.get('image')]
            cats = classify(imgs) if imgs else {'(空)'}
            rows.append((mid, mv.get('index'), sorted(cats),
                         imgs[0] if imgs else ''))
        rows.sort()
        outp = os.path.join(OUT_DIR, 'action_ids_%s.md' % ch)
        with io.open(outp, 'w', encoding='utf-8') as f:
            f.write('# %s 动作ID表(movepattern XML提取, %s)\n\n' % (
                ch, __doc__.splitlines()[0]))
            f.write('| move id | 类目 | 首帧图像 |\n|---|---|---|\n')
            for mid, idx, cats, im in rows:
                f.write('| %d | %s | %s |\n' % (mid, '+'.join(cats), im))
        print('==== %s: %d个move → %s ====' % (ch, len(rows),
                                               os.path.basename(outp)))
        # 汇总: 每类目的id集合(打印关键类目)
        bycat = {}
        for mid, _, cats, _ in rows:
            for c in cats:
                bycat.setdefault(c, []).append(mid)
        for c in ('立防姿态', '蹲防姿态', '空防姿态', '立防blockstun',
                  '蹲防blockstun', '空防blockstun', '后退走', '前进走',
                  '后冲', '前冲', '倒地', '受击上段', '受击蹲姿', '受击空中',
                  '受击旋转', '攻击', '射击(弹幕技)', '符卡'):
            ids = bycat.get(c, [])
            if ids:
                print('  %-14s %d个: %s' % (c, len(ids),
                                            ids[:14] if len(ids) > 14 else ids))


if __name__ == '__main__':
    main()
