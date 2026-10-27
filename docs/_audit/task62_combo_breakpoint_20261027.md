# task-62 连段断点量化（选择率基线 + 口径，2026-10-27 host 22:00）

## 1. 选择率证据（已出）
- 脚本：`tools/combo_baseline_20261027.py`
- 数据：`D:\temp\combo_baseline_20261027.json`；文档 `docs/_audit/combo_baseline_20261027.md`
- 分母/窗口：`episodes_keep` 每 char 最近 120 局（裁剪后训练期片段）；逐决策计数，不含评估/旧代。
- 结果：
  | 角色 | 局 | 决策 | combo/pressure 选择率 | poke | defense | approach |
  |---|---|---|---|---|---|---|
  | reimu | 184 | 130,887 | **1.2%** | 79.4% | 19.3% | 0.1% |
  | marisa | 196 | 110,913 | **3.6%** | 73.8% | 22.4% | 0.2% |
  | suika | 155 | 181,701 | **3.2%** | 77.3% | 19.1% | 0.4% |
- 结论：**选择率 1.2–3.6% 是首要断点**（连段宏几乎不被选），不是执行层独有。

## 2. 口径差异（禁止混用）
- episodes：`macro_avg_frames` = 决策序列中同 act 连续长度均值 → **1.85/2.06/2.17F**（决策单位）。
- rep：`macro_avg_frames` = 原始输入变化 run 均值 → **13.47F**（输入帧单位，含 hold/方向持续）。
- 两者**定义不同**，不能互相比较；task-62 统一口径后再做跨源对照。

## 3. 完成率/断点（待仪表）
- 当前无逐决策 `confirm_timeout/gate_truncate/hit打断/attempts/completed` 遥测 → 只有选择率+lab；完成率需 task-62 仪表（actor 侧计数）。
- lab：strict 39/50 combo（11 条空中/压起身/空链失败，场景缺口），目标独立 damage 未全覆盖；lab `.rep` 不可得（EvalEnv 未录像），明日窗口后开 SokuReplays/完整对局补 1 条再验。

## 4. 修复优先级（选择率主线）
1) BC 锚 09:45（给连段选择信号）；
2) 连段课程/选择信号（phase-3b 场景+命中链奖励，env 可关；预注册单变量窗）；
3) task-73/63 续接/取消（命中→续段、被防→停）；
4) 11 条 lab 空中/OTG 场景构造+执行器 gate；
5) task-62 仪表（attempts/completed/confirm/gate/hit）先量化再改机制。

## 6. 连段分类判定（用户 22:27 定稿；禁止混判）
| 类目 | dummy setup | 判定指标 |
|---|---|---|
| ①出伤连段 | 站/受击 dummy | **comboLimit≥100**、路线、comboDamage/count |
| ②压制连段 | dummy 全防御（站防/蹲防/FD 显式） | 无隙/gap frames、frame advantage、灵力削减、推板（**不看伤害/limit**） |
| ③压起身 | 击倒→起身 | meaty 帧、防住/穿 |
| ④择 | dummy 防 | 中/下/投 选项成功率 |
| ⑤空连/对空 | 浮空 dummy | 浮空高度/路线/limit |
| ⑥爆灵/推板 | 防御/破防目标 | 破防/位移目标 |
- setup 必须显式写 `class/dummy_state/guard_mode/fd/位置/距离`；同一 dummy 状态不得混判。
- **39/50、37/58 作废**，按类目重跑逐条；失败标不可实现/断连/被防/空挥。
- 输出必带 `class`+`dummy_state`；TrialMode 真值优先。

## 7. TrialMode 作为游戏原生裁判（用户 22:33 提议）
- 路径 `D:\touhou\hisoutensoku2026-06-15\th123\modules\TrialMode`；自带书面连段（步骤/可选/延迟/合格标准）与判定。
- 计划：①调研通关信号（内存 flag/score.dat/UI 文本/日志）→ 手动通 1 条对照；②自动：把 combo 写成 TrialMode pack，宏驱动输入，读 pass/fail/limit/damage/hits/rep；③首批用用户 88 trial 包（含 8 条 explicit input）作真值；④以后所有采集连段走 TrialMode 判定，替代 proxy/limit 自证。
- 明日 BC/UKEMI 后第一优先（今晚停训）。
