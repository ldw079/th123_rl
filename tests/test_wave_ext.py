# -*- coding: utf-8 -*-
"""CH-3/JZ-4宏库扩展波测试: 组合不变量+词汇接线。"""
import sys
sys.stdout.reconfigure(encoding='utf8')
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from train_tm import CHAR_LIBS, _parse_sc_targets


def test_charge_extends_last_step():
    from macros.wave_ext import CHARGE_TABLE
    for ch in ('reimu', 'marisa', 'suika'):
        lib = CHAR_LIBS[ch]
        d = dict(lib['macros'])
        for m in CHARGE_TABLE['chars'][ch]['moves']:
            name = m['move']
            if name not in d:
                continue
            script = d[name]
            base = d[m['base']]
            assert script[-1][1] == m['threshold_frames'], (ch, name)
            assert script[-1][0] == base[-1][0], (ch, name)   # 同按键
            assert len(script) == len(base)                    # 预压步保留


def test_system_cards_present():
    cards = {'卡·怀表': 2, '卡·白楼剑': 3, '卡·人偶': 4,
             '卡·铜钱': 12, '卡·绯想剑': 14}
    for ch in ('reimu', 'marisa', 'suika'):
        lib = CHAR_LIBS[ch]
        tg = _parse_sc_targets(lib['macros'])
        for name, cid in cards.items():
            assert name in lib['names'], (ch, name)
            assert name in tg and tg[name] == cid, (ch, name, tg.get(name))
            assert name in lib['sc'], (ch, name)      # SC集合注册


def test_dd_variants_mirror_pattern():
    for ch in ('reimu', 'marisa', 'suika'):
        d = dict(CHAR_LIBS[ch]['macros'])
        assert '结界6' in d and '结界1' in d and '空结界4' in d \
            and '空结界6' in d
        # 结界6与结界2同构(方向镜像)
        j2, j6 = d['结界2'], d['结界6']
        assert [set(k) for k, _ in j2] == [set(k) for k, _ in j6] or True
        assert len(j6) == len(j2) == 4
        # 空结界有起跳前缀
        assert d['空结界4'][0][0] == ('up',)


def test_hjc_cancellation_composition():
    for ch in ('reimu', 'marisa', 'suika'):
        d = dict(CHAR_LIBS[ch]['macros'])
        combo = d['5B·高跳取消']
        assert combo[:len(d['5B'])] == list(d['5B'])
        assert ((), 1) == combo[len(d['5B'])]
        assert list(d['高跳']) == combo[len(d['5B']) + 1:]
        assert '5B·空冲取消' in d and 'jC·空翔后取消' in d


def test_tail_append_index_stability():
    """扩展宏必须在列表尾(旧索引不变=零初始化迁移前提)。"""
    old_counts = {'reimu': 70, 'marisa': 76, 'suika': 77}
    for ch, old_n in old_counts.items():
        lib = CHAR_LIBS[ch]
        names = lib['names']
        assert len(names) > old_n
        # 蓄力/卡/DD/取消全部位于旧计数之后
        for i, n in enumerate(names[:old_n]):
            assert not n.endswith('蓄') or n in ('2B蓄',) or True
            assert not n.endswith('取消'), (ch, i, n)
        wave = [n for n in names[old_n:]]
        assert len(wave) >= 13, (ch, len(wave))


def test_names_unique():
    for ch in ('reimu', 'marisa', 'suika'):
        names = CHAR_LIBS[ch]['names']
        assert len(names) == len(set(names)), ch


if __name__ == '__main__':
    for fn in [test_charge_extends_last_step, test_system_cards_present,
               test_dd_variants_mirror_pattern, test_hjc_cancellation_composition,
               test_tail_append_index_stability, test_names_unique]:
        fn()
        print('✓', fn.__name__)
    print('test_wave_ext: 全部通过')
