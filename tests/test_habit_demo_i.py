# -*- coding: utf-8 -*-
"""I项(教学闭环产物2): habit_punish_demo — 行为断言(不起游戏).

钉住:
  1. expand_macros: 脚本循环补满total(首版12帧放空=对照无效的教训) +
     键位展开(H/V/A-D) + 角色库过滤;
  2. pick_auto_habit: 按严重度(高>中>低)取最新报告习惯;
  3. verdict双向: 习惯分支多伤→"成立"; 改正分支多伤→"模型短板"
     (2026-10-12实测: 立防0伤/前冲-500 — 当前模型破不了全场格挡,
     判定必须如实报短板而非硬说"成立");
  4. _ScriptedOpp: 逐帧推进+reset_match归零.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import habit_punish_demo as D

FAILS = []


def check(name, cond, detail=''):
    print('%-56s %s %s' % (name, 'PASS' if cond else 'FAIL',
                           detail if not cond else ''))
    if not cond:
        FAILS.append(name)


# ---- 1. expand_macros: 循环补满+键位展开 ----
fn, script, used = D.expand_macros('suika', ['立防'], total=240)
check('脚本循环补满240帧(立防全程)', len(script) == 240)
check('立防=持后(H:-1)', all(s == {'H': -1} for s in script[:5])
      and script[0] == {'H': -1})
fn2, script2, used2 = D.expand_macros('suika', ['前冲'], total=240)
check('前冲含前进方向(H:1)', any(s.get('H') == 1 for s in script2))
check('不存在的宏被过滤', D.expand_macros('suika', ['不存在的宏'],
                                          total=10)[2] == [])
fn3, script3, _ = D.expand_macros('suika', ['立防'], total=None)
check('total=None不循环(原语义)', len(script3) < 50)

# ---- 2. pick_auto_habit: 严重度排序 ----
tmp = tempfile.mkdtemp(prefix='hd_i_')
rep = os.path.join(tmp, 'r.json')
json.dump([{'char': 'suika', 'habits': ['far_stand_guard']},
           {'char': 'reimu', 'habits': ['empty_spirit_attack',
                                        'far_stand_guard']}],
          open(rep, 'w', encoding='utf8'))
D.REPORT = rep
h, c, err = D.pick_auto_habit()
check('auto取最严重(高>低): empty_spirit_attack',
      h == 'empty_spirit_attack' and c == 'reimu' and err is None,
      'got %s %s %s' % (h, c, err))
D.REPORT = os.path.join(tmp, 'none.json')
h2, c2, err2 = D.pick_auto_habit()
check('无报告→错误信息', h2 is None and err2)

# ---- 3. verdict双向(数值语义: d=改正-习惯, 正=习惯更伤=成立) ----
v1 = D._verdict_text(-1200, -400, '弹幕牵制')
check('习惯多伤→成立', '惩罚演示成立' in v1 and '800' in v1, v1)
v2 = D._verdict_text(0, -500, '弹幕牵制')
check('改正多伤→模型短板(今日实测形态: 立防0/前冲-500)',
      '记为模型短板' in v2 and '500' in v2, v2)
v3 = D._verdict_text(-400, -400, 'x')
check('差异不显著', '不显著' in v3, v3)
src = open(os.path.join(ROOT, 'tools', 'habit_punish_demo.py'),
           encoding='utf8').read()
check('对手默认=生产模型(短板暴露语义)',
      "SideDriver(char, 'R')" in src and 'model_ppo_%s.npz' in src)
check('HABIT_DEMOS五习惯全覆盖',
      set(D.HABIT_DEMOS) == {'far_stand_guard', 'wakeup_crouch_guard',
                             'wakeup_stand_guard', 'pressure_backjump',
                             'empty_spirit_attack'})

# ---- 3.5 R77b: 工具PORT类型(branch_demo/habit_punish_demo) ----
import branch_demo as BD
check('PORT为int(branch_demo/habit_punish_demo)',
      isinstance(BD.PORT, int) and isinstance(D.PORT, int))

# ---- 4. _ScriptedOpp: 逐帧推进+reset ----
opp = D._ScriptedOpp(fn)
a = opp.frame_input({}, {}, {}, [], [])
b = opp.frame_input({}, {}, {}, [], [])
check('ScriptedOpp逐帧推进', a == script[0] and b == script[1])
opp.reset_match()
c = opp.frame_input({}, {}, {}, [], [])
check('reset_match归零', c == script[0])

print()
if FAILS:
    print('FAIL(%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('ALL PASS (15)')
