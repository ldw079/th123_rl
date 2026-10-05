# -*- coding: utf-8 -*-
"""R61i(C6): 17新角色Trialmode连段→宏库追加。
从trialmode_to_macro的combo_to_macro管线, 按角色生成追加片段并直接
写入macros_<char>.py末位(末位追加契约)。每角色取伤害topN条(≤8步)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

from trialmode_parse import PACKS, load_pack  # noqa: E402
from trialmode_to_macro import combo_to_macro  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEW_CHARS = ['yukari', 'komachi', 'meiling', 'sanae', 'youmu', 'yuyuko',
             'tenshi', 'suwako', 'alice', 'cirno']
MAX_PER = int(sys.argv[1]) if len(sys.argv) > 1 else 4


def _diff(steps):
    exact = sum(1 for s in steps if s.get('exact'))
    n = len(steps)
    has_sc = any('sc' in (s.get('move') or '')
                 for s in steps if isinstance(s, dict))
    return exact * 2 + (n > 8) * 2 + (n > 11) * 2 + has_sc * 1


def main():
    grand = 0
    for ch in NEW_CHARS:
        packs = PACKS.get(ch, [])
        if not packs:
            print('%s: 无数据' % ch)
            continue
        combos = []
        for pk in packs:
            combos.extend(load_pack(pk))
        # 过滤: 中等难度以下, ≤8步, 可全部转换
        ok = []
        for c in combos:
            if _diff(c['steps']) > 5 or len(c['steps']) > 8:
                continue
            moves = '_'.join(s['move'] for s in c['steps'])[:18]
            macro, bad = combo_to_macro(c['steps'], 'TM·%s' % moves)
            if macro:
                ok.append((c, macro))
        ok.sort(key=lambda x: -(x[0]['min_damage'] or 0))
        picked = ok[:MAX_PER]
        if not picked:
            print('%s: 0条可转换' % ch)
            continue
        # 写入macros_<ch>.py末位
        fpath = os.path.join(ROOT, 'macros_%s.py' % ch)
        src = open(fpath, encoding='utf8').read()
        import re
        m = re.search(r'(MACROS_[A-Z_]+)\s*=', src)
        var = m.group(1) if m else 'MACROS'
        with open(fpath, 'a', encoding='utf8') as f:
            f.write('\n# ==== R61i(C6): Trialmode连段追加(伤害top%d) ====\n'
                    % len(picked))
            for c, (name, script) in picked:
                steps = []
                for k, fr in script:
                    if isinstance(k, str):
                        steps.append('(%r, 0)' % k)
                    else:
                        # repr(tuple)正确生成单元素元组的尾逗号
                        steps.append('(%r, %d)' % (tuple(k), fr))
                f.write('%s.append((%r, [%s]))\n'
                        % (var, name, ', '.join(steps)))
            # 类别集更新: TM宏入COMBO(攻击集超集包含它)
            f.write('%s_COMBO_MACROS |= {%s}\n'
                    % (ch.upper(),
                       ', '.join(repr(c[1][0]) for c in picked)))
        grand += len(picked)
        print('%s: +%d条(共%d可转换, 取top%d) → %s'
              % (ch, len(picked), len(ok), MAX_PER,
                 os.path.basename(fpath)))
    print('--- 总追加: %d条 ---' % grand)


if __name__ == '__main__':
    main()
