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
