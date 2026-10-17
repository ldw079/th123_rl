# -*- coding: utf-8 -*-
"""P0-6(从零#5)行为测试: SC 标签不得把复合连段终结宏覆盖成同卡的裸SC宏。

真因(实测, 非推测):
  复合宏 TM·6a终结(sc:219) / TM·必杀SC连(sc:219) / TM·空连终结(sc:200)
  的卡ID与裸卡宏**撞车** —— sel=219 时 resolve_sc_label 先命中「卡·邪恋」,
  sel=200 先命中「卡·星星」。原实现对**所有**名字落在 _sc_tgts 的宏都做
  二次解析, 于是匹配器已经正确识别的连段终结宏被覆盖成"同卡的另一个SC宏",
  结果这三个宏在三角色库里 Y 恒 0(永远学不到), 另有约 1–6% 行归因错误。

本测试钉死三件事(全部用**真实宏库**, 不自造向量 — R133/R138b 教训):
1. 复合宏(含按键步 + 末步 sc:) 必须**不**在 bare_sc_names 集内;
2. 裸SC宏(脚本无任何按键步) 必须在集内(它们才需要按选中卡解析);
3. 三个真实复合宏逐个断言 + 其卡ID确实与某裸宏撞车(证明这是真冲突而非空断言)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf8')

import bc_build as B                      # noqa: E402
from train_tm import _parse_sc_targets    # noqa: E402

N = 0
BAD = 0


def ck(cond, name):
    global N, BAD
    N += 1
    if cond:
        print('  PASS  %s' % name)
    else:
        BAD += 1
        print('  FAIL  %s' % name)


# 复合宏 → 其 sc 卡ID(实测自宏库, 三方交叉: 脚本/sel撞车/标签覆盖)
COMPOSITE = {1: ('TM·6a终结', 'TM·必杀SC连'), 9: ('TM·空连终结',)}
BARE_MUST = {0: ('卡·当前',), 1: ('卡·当前', '卡·星星'), 9: ('卡·当前',)}

for cid, names in COMPOSITE.items():
    name, lib = B.LIBS[cid]
    tg = _parse_sc_targets(lib)
    bare = B.bare_sc_names(lib, tg)
    scripts = {m[0]: m[1] for m in lib}
    for nm in names:
        ck(nm in tg, '%s/%s 在SC目标表内(前提真实)' % (name, nm))
        ck(nm not in bare,
           '%s/%s 是复合宏 → 不得进入按卡二次解析集' % (name, nm))
        ck(not B._is_bare_sc_macro(scripts[nm]),
           '%s/%s 脚本含按键步 → _is_bare_sc_macro=False' % (name, nm))
        # 撞车实证: 它的卡ID确实被某个裸宏占用(否则本修复没有目标)
        coll = [n for n in bare if tg[n] == tg[nm]]
        ck(bool(coll),
           '%s/%s 卡ID %r 与裸宏撞车(修复的真实目标): %s'
           % (name, nm, tg[nm], coll[:3]))

for cid, names in BARE_MUST.items():
    name, lib = B.LIBS[cid]
    tg = _parse_sc_targets(lib)
    bare = B.bare_sc_names(lib, tg)
    for nm in names:
        ck(nm in bare, '%s/%s 是裸SC宏 → 必须保留按卡解析' % (name, nm))

# 交叉一致性: 集内每个名字的脚本都确实无按键步
_all_ok = True
for cid in (0, 1, 9):
    name, lib = B.LIBS[cid]
    tg = _parse_sc_targets(lib)
    scripts = {m[0]: m[1] for m in lib}
    for nm in B.bare_sc_names(lib, tg):
        if not B._is_bare_sc_macro(scripts[nm]):
            _all_ok = False
ck(_all_ok, 'bare_sc_names 与 _is_bare_sc_macro 口径一致(三库全量)')

# 空集守卫: 裸SC宏集不得为空(否则所有SC卡宏都会退化成通用标签)
for cid in (0, 1, 9):
    name, lib = B.LIBS[cid]
    ck(len(B.bare_sc_names(lib, _parse_sc_targets(lib))) >= 2,
       '%s 裸SC宏集基数量(%d)' % (name,
                              len(B.bare_sc_names(lib, _parse_sc_targets(lib)))))

print()
print('==== %d PASS / %d FAIL ====' % (N - BAD, BAD))
sys.exit(1 if BAD else 0)
