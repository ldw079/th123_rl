# docs/ 文档索引（2026-10-13 归档整理; 2026-10-14晚计数刷新）

> 本次整理: 审查报告（19 份）移入 `_reviews/`; 历史规划/分析/方案（12 份）移入 `_plans/`;
> 根目录只留**活跃文档**（主规划/操作手册/数据参考）。全部文件未做内容修改, 仅位置变更。

## 根目录 · 活跃文档

| 文件 | 性质 | 说明 |
|---|---|---|
| `master_plan_2026-10-05.md` | **唯一任务主档** | 六大工作流+排期; 状态列随波更新 |
| `fleet_ignition_runbook.md` | 操作手册 | fleet 点火/监控/收队步骤 |
| `audit_protocol.md` | 操作手册 | 审计/从零审查执行协议 |
| `action_ids_{reimu,marisa,suika}.md` | 数据参考 | SokuLib 枚举权威表（生成物） |
| `soku_action_ids.md` | 数据参考 | 枚举总表 |
| `hitlab_tables.md` | 数据参考 | hitlab 帧数据实测 |
| `combo_mining.md` | 数据参考 | 连段挖掘方法 |
| `data/guide_tables/cleista/` | **权威数据** | cleista API 20角色帧数据(build 8bd50f33) + non_main_charge.json(17角色蓄力97条) |
| `tools/cleista_api_fetch.py` | 工具 | cleista API抓取(限速/ETag/署名) |
| `tools/cleista_nonmain_charge.py` | 工具 | 非主力17角色蓄力探针(?charged=1) |
| `tools/charge_usage_report.py` | 工具 | CH-5蓄力使用观察报表(只读episodes) |
| `tools/feature_liveness.py` | **仪表** | 特征活性巡检(29+8段期望表, 应活段恒死报警) |
| `tools/s4_acceptance_probe.py` | 工具 | S-4验收探针(3场对空→跳宏率降, 需W_gru训练后) |
| `tools/adaptation_probe.py` | 工具 | S-8变招压力环境(规则反制者+分析模式) |
| `tools/jz1_truth_replay.py` | 工具 | JZ-1真值回放验证(airDash/冷却/技能/破珠) |
| `tools/migrate_s2_343.py` | 工具 | 模型CORE_DIMS迁移(330→343→358, 幂等) |
| `tools/migrate_macros_wave.py` | 工具 | 模型宏数迁移(尾增零初始化, 幂等) |
| `jz1_features.py` | 预制件 | JZ-1 15维A档字段(已接线feat_builder) |
| `frame_adv.py` | 纯函数 | 攻击等级表驱动帧差(cleista真值) |
| `rep_format_notes.md` | 数据参考 | rep 格式实测笔记 |
| `multi_instance_input.md` | 数据参考 | TM 通道全档 |
| `mod_masking_runtime_dump.md` | 数据参考 | mod 遮蔽运行时验证 |
| `architecture_gap_analysis.md` | 历史分析（活跃引用） | 架构差距（v2 时代, AGENTS 引用） |
| `com_ladder_log.md` | 运行日志 | COM 阶梯爬升记录 |
| `audit/` | 审计工件 | 自动化审计输出 |
| `bugs/` | 缺陷工件 | 缺陷记录 |

## 根目录 · 宪章/入口（不在 docs/）

| 文件 | 说明 |
|---|---|
| `METHODOLOGY.md` | 宪法文档（最高规范） |
| `AGENTS.md` | 开发智能体入口路由 |
| `PLANNING_AGENT.md` | 规划智能体宪章（三段式强制） |
| `HANDOVER.md` | 交接文档（下一个智能体入口） |
| `ARCHITECTURE.md` | 架构快照（部分过时, 顶部有横幅） |

## `_reviews/` · 审查报告存档（22 份, 按时间序）

| 文件 | 轮次/性质 | 要点 |
|---|---|---|
| `full_review_2026-10-03.md` | 第九轮 | 6×P0（崩溃循环/死特性/数据错位）→ R38 修复 |
| `…_round2.md` | 第十轮 | BC 双偏差+宏表 8 错 → R39 |
| `…_round3.md` | 第十一轮 | mod/soku_arch 盲区关闭, M-1/M-2/INPUTLOG 建议 |
| `…_round4.md` | 第十二轮 | R40 核验+四残余 |
| `…_round5.md` | 第十三轮 | 重启验收通过+学习健康度 |
| `…_round6.md` | 第十四轮 | R44 扩容审计（1 阻塞+1 高+2 中） |
| `…_round7.md` | 第十五轮 | R45-R50 冲刺波（F1/F2/F3 等） |
| `…_round8.md` | 第十六轮 | R51 四道闸核验 |
| `…_round9_strict.md` | 第十七轮·从严 | S1 deck 死接线/S2 ppo_gpu 六缺陷/S3 门禁空转 |
| `…_round10_fleet_strict.md` | 第十八轮·从严 | fleet 四缺陷（饥饿/bc/rng/counts） |
| `…_round11_perception.md` | 第十九轮 | R57/R58 感知层验收+审查者自纠 |
| `full_review_from_zero_2026-10-04.md` | **从零 #1** | 4 零先验代理: 3 P0+5 P1（fleet 四连环/池序碰撞/dx330） |
| `…_round12_r60.md` | 第二十轮 | 从零#1 修复核验（11/11 实修） |
| `…_round13_fleet_live.md` | 第二十一轮 | fleet 点火实录（v15, F-1/F-3 产线生效） |
| `…_round14_r61wave.md` | 第二十二轮 | A3 hitlab 裁决+B1 SC 词汇+gate_runner_v2 弃置副本 |
| `…_round15_CEwave.md` | 第二十三轮 | C/E 工作流冲刺（执行器统一/教学三件） |
| `full_review_from_zero_2_2026-10-06.md` | **从零 #2** | 3 P0+8 P1（fleet 308/316 死链/入队丢载荷/eval 死工具） |
| `…_round16_fixcheck.md` | 第二十四轮 | 从零#2 修复核验（P0×3 实修, 两个配制度化测试） |
| `arch_review_2026-10-07_r63_fixes.md` | 补审 | R63 修复的架构审查 |
| `charge_semantics_probe_2026-10-14.md` | CH-0探针 | 蓄力语义(pose无签名结案/2074窗中位33帧) |
| `jz_field_semantics_probe_2026-10-14.md` | JZ-0探针 | 封包字段语义(15维入账裁定) |
| `jz2b_macro_timing_audit_2026-10-14.md` | JZ-2b审计 | 宏时序vs cleista站(萃香3偏差修正+系统动作互证) |

## `_plans/` · 历史规划/分析/方案存档（23 份）

| 文件 | 性质 | 状态 |
|---|---|---|
| `goal_feasibility_superhuman_2026-10-04.md` | 可行性 v1（六天花板） | 历史基线; 已被 v3 取代 |
| `technique_coverage_analysis_2026-10-04.md` | 技法覆盖分析（167 项 vs 架构四层） | 感知✓/执行件✓/时序◐; L2/L1 已闭合 |
| `model_checkup_and_vulnerabilities_2026-10-04.md` | 模型体检+漏洞登记册 | 病灶 A1-A6 中 A4/A5 已闭合 |
| `combo_and_perception_improvement_2026-10-04.md` | 连段+感知改进方案 | Part1 感知已交付; Part2 即 C 工作流（已完） |
| `scenario_b_fleet_design_2026-10-04.md` | fleet 设计文档 | 三红线+组件设计; 已实现并点火 |
| `feasibility_reflection_v3_2026-10-06.md` | 可行性 v3/v3.1（证据视角） | **最新判词: 架构的账付得差不多, 证据的账刚开始还** |
| `series_opponent_prediction_plan_2026-10-06.md` | BO15 系列赛方案 | 阶段 0 仪表已上线; 阶段 1-4 待启动 |
| `unresolved_issues_solutions_2026-10-12.md` | v3.1 十项未决方案（A-J） | A1-2 势差对称化已部署; 其余进行中/待启动 |
| `rep_stack_fixes_2026-10-12.md` | rep 解析栈四缺口修复 | 缺口 3 frames() 陷阱待修; 1/2 验证待跑 |
| `research_borrowing_plan_2026-10-13.md` | 研究地图借鉴方案 v2（W1-W5） | 终版; 排期 B→W1→W2 |
| `architecture_gap_analysis.md` | 架构差距分析（v2 时代） | AGENTS 引用, 保留在根 |
| `six_gap_solutions.md` | 六差距解决方案 | 历史文档（v2 时代） |
| `f6_superhuman_distance_2026-10-07.md` | F6 超人距离框架 | COM 标尺饱和自知; 顶端标尺 B 待立项 |
| `top_yardstick_v2_rpm_vjoy_2026-10-13.md` | B 顶端标尺方案 v2（RPM+vJoy） | 终版; B2' 改道后架构; 待施工 |
| `b_problem_statement_2026-10-13.md` | B 问题陈述书（供规划） | 已消费（产出 v2 方案） |
| `adaptive_retooling_plan_2026-10-14.md` | 模型侧变招方案（V-1..V-6） | 已被合并方案取代 |
| `expert_psych_game_capture_plan_2026-10-14.md` | 专家心理博弈捕获（P-1..P-4） | 已被合并方案取代（P-4 重设计为 S-7） |
| `adaptive_psych_merged_plan_2026-10-14.md` | 变招×心理博弈合并方案（S-1..S-8） | **活跃执行方案**; 三波 ≈12 人日 |
| `charge_attack_support_plan_2026-10-14.md` | 蓄力攻击支持方案（CH-0..CH-5） | 技法 L2 盲区; ≈4 人日; CH-0/2 可即行 |
| `system_mechanics_completion_plan_2026-10-14.md` | 系统机制补全方案（JZ-0..JZ-5） | 攻略重读×代码核验: A档8字段/B档8表/C档7词汇; ≈7.5 人日; JZ-0/2 可即行 |
| `capability_extension_plan_2026-10-15.md` | 能力扩展方案（CE-0..CE-7） | 招式级惩罚×实体语义×位置预测×自打挖掘×位置路由门×推板势; ≈9 人日; CE-0 探针已完成(v2); CE-7 奖励项部署排 A/B 验收后 |
| `behavioral_health_recovery_plan_2026-10-15.md` | **行为健康修复方案（BH-0..BH-6，v4 重构版）— 当前最高优先** | 六症状×六根因(+对位盲); BC 排查四判决定稿(语料健康/字段语义/碎片化标注/三角色泡泡); untech 门最优先→冻结窗+八仪表+BC 四子项合批重建; ≈7 人日+1-2 周治疗窗; **CE/JZ/CH 余波排队待 BH 退出** |
| `branch_gate_activation_2026-10-13.md` | 分支门激活方案（CH-1..CH-4 框架） | branch宏confirm→四路路由 |
| `kit_portable_python_plan_2026-10-13.md` | 轻量采集包迁移方案 | kit zip→收件人runner→数据回传 |
| `top_yardstick_human_match_plan_2026-10-13.md` | 人测标尺对局方案 | B线顶端标尺配套 |
| `pending_rulings_2026-10-14.md` | 待裁定事项清单 | 用户裁定入口 |

---
*归档原则: 审查报告不改内容只归档; 规划文档历史版本归档、活跃版本留根（master_plan）; 数据参考/操作手册不归档。新文档产生时按此原则归位。*
