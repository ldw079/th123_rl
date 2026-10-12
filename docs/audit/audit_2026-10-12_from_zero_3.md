# 从零全盘审查 #3(2026-10-12 晚)

> **基线**: commit `19ef5cd`(HEAD, 工作区干净)。方法: 4 个零先验子代理分片
> (A 动作路径/B 学习核心/C 产品面/D fleet 治理)+ 审查者亲验全部 P1 论断 +
> 中央五项(门禁/编译 import/纪律横扫/三面对账/文档对账)+ 变异自检抽查。
> 距 #2(2026-10-06)约 20+ 修订波, 过 ≥5 波触发线。
> fleet 审查全程运行中(采样 20:15-20:45), 未受干扰。

## 总判定

**代码主链健康: 门禁 583/0/0、59 模块编译+import 全绿、CORE_DIMS 派生链
无硬编码残留、episode 契约/先更后删/原子落盘主路径正确、CpuWatchdog 实盘
循环正确、维度链 330/70-76-77/680-710-715 与文档全对账。**
但发现 **6 项 P1**(其中两项直接削弱治理与观测基础设施), 详见 bug 档。

## P1(六项, 全部亲验或动态实证; 立档于 docs/bugs/)

| # | 发现 | 证据 | bug 档 |
|---|---|---|---|
| 1 | **变异自检基础设施失效**: 沙箱 FILES 清单缺 series_manager.py(d672c2d 入库未同步), test_series_stage1_e1 沙箱内必炸 → 基线不绿, 自检一条变异都跑不了; 另有死变异×2(CORE_DIMS=316 已漂移 330; mod_provenance md5 失配) | 实测 SELFTEST_TAGS 跑出"[自检失败] 基线不绿"; FILES 清单亲验 | bug_2026-10-12_selftest_sandbox_stale |
| 2 | **对手侧 R34 守备豁免恒失效**: side_driver.py:397 传 dec_name=None → `None not in GUARD_PREP_SET` 恒真 → 对手立防/蹲防启动窗永远被清队; 注释修了 SET 参数漏了名字参数 | 亲验两调用方参数; 代理动态复现(同队列 dec_name="立防" 存活、None 被清) | bug_2026-10-12_side_driver_dec_name |
| 3 | **吞吐报告路径常量含真实 TAB 字节**: `r'D:<TAB>emp'` → mtime 恒 OSError → fleet 合计恒 0(运维决策数失真, JSON 不含该合计) | cat -A 亲验 `D:^Iemp`; 代理 AST 求值复现 | bug_2026-10-12_throughput_tab_path |
| 4 | **R79 提交宣称与实现不符**: `habits_retracted` 作废机制代码零写入点(grep 全库), 报告 JSON 里的该字段系手工编辑; 且 human_match 路径无透明字段无有效性门, 同垃圾序列产出习惯报告不留痕 | grep 亲验; 代理动态复现(全近距 5 元组 → far_stand_guard 100%) | bug_2026-10-12_habits_retract_nowriter |
| 5 | **ppo.py↔ppo_gpu.py 更新不等价(梯度接合点)**: 前向/头梯度等价, 但 conv 主干与对手子网梯度大面积反号(Wc2 3653/18432, Wo1 464/2400)。根因①ppo.py:889 vf_adam.step 先于 :894 用 W1v 回传(混代); ②numpy 封顶反向只补 1/cap 不完整。Adam 首步≈sign(g)·lr → 每步分歧 ±2×PI_LR(实测 0.0006) | 代理动态实证(同种子同批梯度 hook 对比); 行号亲验 | bug_2026-10-12_ppo_dual_impl_grad |
| 6 | **train_start 无差别杀全部 th123.exe**: `taskkill /IM th123.exe /F` 会误杀用户游玩中的原版整合包游戏与离线 oracle 重放实例(跨工具误伤); --stop 复用 pre_flight 附带跑协议测试+league 种子(副作用未声明) | 静态亲验命令构成; 自杀路径已修(-ne $me 亲验有效) | bug_2026-10-12_trainstart_killall_th123 |

## P2(十九项, 择要; 未立档, 修复时随 P1 波处理)

- 学习: ppo_gpu ratio 无 ±20 clamp(numpy 有, 降级不对称); BC 幽灵自模仿
  不对称(numpy 自模仿/GPU 跳过, fleet 路径不触发); learner_hub 两处
  `except: pass` 静默(与 R67e 教训同型); episode 部分更新不回滚(vf 已步进,
  盘档≠内存); ROUND_WIN/-5 静态阈值假设(奖励经济学变更时需同步)。
- fleet: seed_ 前缀清理过滤缺失(learner 只清自己目录, 当前不触发=潜伏);
  reap_orphans 不回收剥削者孤儿; 心跳可被重启风暴饿死(8×30s>90s → 假
  离线账); .tmp.npz 无清理方(降容硬杀残留)+ _dg_cleanup 理论可删活 actor
  临时件; _spawn_actor 日志 fd 不显式关。
- 动作: 按键步输入不镜像泄漏一帧(sc: 步首帧, train_tm 侧); 灵力门 <100
  连零灵耗体术宏整队清空(0-2000 量纲, 领域裁定); delay_then 死语法
  (文档有代码无)。
- 工具: eval_matrix/human_match 平局记右方胜; branch_demo 截断无标记;
  teach 的 V 在侧向量分布外评估(3n 块置零未披露); league_weekly 跨块
  累积求和口径膨胀(比例不受影响); SeriesManager 按设计未接线(非缺陷,
  但启用开关/接线点尚不存在, 部署时需补)。
- 文档: bc_build docstring"5N+308"漂移(代码正确); throughput GAP_DEAD_S
  注释漂移; bc_build:352 直写 savez 非原子(违宪法 §5.2)。
- 已立档未修: far_passive 零远距帧兜底(见 docs/bugs/)。

## 中央五项结果

| 项 | 结果 |
|---|---|
| 门禁全量 | 583/0/0 实测通过 |
| 编译+import | 59 模块 0 失败(仅 _archive 旧档 SyntaxWarning) |
| 纪律横扫 | 维度字面量仅存测试合成网; 原子落盘违规 1 处(bc_build:352); 无 tmp 残留; json 写出均 ensure_ascii 或 tmp 路径 |
| 三面对账 | 8-10 进程(watchdog 治理中)/learner 在写/心跳新鲜; 模型快照 v 序与日志吻合 |
| 文档对账 | CORE_DIMS=330、宏数 70/76/77、n_side 680/710/715 全对上; AGENTS 修订行为历史戳(可接受) |

## 与 #2(10-06)的对照

#2 的 P0 三项(fleet 维度硬编码/入队丢载荷/工具空转)修复全部保持; 本轮
全部新发现为 **10-07 之后 20+ 波冲刺引入**或**治理工具未随新模块同步**,
共性病根仍是: **单元测试过、集成缝与"新模块入治理清单"的同步缺位**
(series_manager 未入沙箱 FILES 是最新实例)。

## 建议(待用户指令, 审计不修)

1. P1 六项按 bug 档修复(优先 1/2/5 — 治理基础设施/训练语义/双实现等价)。
2. P2 批量随下个修复波; 文档漂移随手清。
3. 制度建议: "新模块入库检查单"增加一条 — 同步 gate_selftest 的 FILES
   与沙箱行为测试依赖(本轮 P1-1 的直接防复发)。

## 修复记录(2026-10-12 P1波, 审计后同日)

P1 六项全部修复+验证(详见各 bug 档"状态"行): ①自检沙箱 FILES 补件+
死变异迁锚(基线绿/163+1 变异拦截, 含新增 P1-5 变异); ②side_driver
dec_name 对称修复(23 PASS); ③TAB 路径一字修+控制字符扫(5 PASS);
④habits_retracted 真实写入+human_match 有效性门对齐(17 PASS);
⑤ppo 混代回传+封顶 zmax 项(数值 rel=3e-9, onestep 8 PASS 三跑稳定,
符号级零翻转); ⑥train_start 按路径精确杀+--stop 副作用剥离。
另: far_passive 零远距帧兜底档随 R79 双兜底关闭。P2 十九项未处理
(留下一修复波)。
