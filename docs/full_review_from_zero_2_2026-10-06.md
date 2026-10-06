# 从零全盘审查 #2（2026-10-06 凌晨）

> 方法: 4 个零先验子代理分片（动作路径/学习核心/产品面/fleet+治理）+ 审查者亲验 6 项最高风险论断。距 #1 约 20 个修订波——恰为 F1 制度预设触发点。
> 与 #1 的关系: #1 的修复全部保持; 本轮全部发现为 **R61 冲刺波（316 扩维/执行器抽取/C6 生成器/E 产品面）引入的新缺陷**——共性病根: **单元测试过、集成缝全断**。

---

## 0. 审查者自纠（第四次, 模式与前三次同源）

第二十三轮（昨晚 23:50）我审查了 R61t 的 feat_builder 改动（40K 更新+test_guard_height 更新）却**没有 diff CORE_DIMS 常量**——308→316 的变更从我眼皮底下溜过, 直接导致本轮 fleet P0 在我的增量审查里不可见。教训第四次入册: **看文件必须看顶部常量区, "测试过了"不构成"布局没变"。**

## 1. P0（三项, 全部有代码级/动态证据）

### P0-A fleet learner 维度推断过期——**fleet 当前静默不可用**【亲验】
- R61t 把 `CORE_DIMS 308→316`（F-8 段 11 重设计落地, train_tm 正确用 `FeatureBuilder.CORE_DIMS`）, 但 `learner_hub.py:270` 硬编码 `5*n_out+308`。
- 链条（代理运行时复现）: 生产模型 666 宽 → learner 以 658 构网 → load 时 side/值头**保持随机**（ppo_gpu 只打印不拒）→ 把腐坏模型发布为 v1 → actor 上真 666 宽数据 → update 抛形状错 → **episodes 在 update 前已被删**（P1-C）→ 批批消费批批丢失, 版本冻在 v1。**fleet 看起来活着, 实际零学习。**
- test_fleet_protocol 的 B4 用同一过期公式 → "前向等价"在随机权重上空转。
- 修法: n_side 从 `feat_builder.CORE_DIMS` 派生 + 加载后宽度断言（响亮）+ "生产模型零形状警告加载"行为门禁。

### P0-B train_tm 入队丢弃门载荷——C1 语法从 P1 侧不可用【亲验】
- `train_tm.py:1569` `macro_queue.append((ks, 0))` 把 branch 字典/link 元组当 0 扔掉; side_driver:265 正确保留 fr。
- 后果（代理复现）: 任何含 branch/link 的宏在训练侧 `AttributeError`（被重建处理器吞成环境重建×5→退出码 1）, 而对手侧正确执行——**最大训练/评估偏斜**。当前潜伏（无现役宏用新语法）——但 R61u 的全部目的就是这个语法, 按文档配方添加第一个宏即触发。
- 修法: 一行（`(ks, fr)`）+ 入队路径集成测试（现有测试全部绕过入队直接构造队列——这是逃逸原因）。

### P0-C 两个游戏侧工具从未能运行【代理动态验证】
- `eval_matrix.run_matchup`: `last_state` 从未赋值（帧 61 必 NameError）+ `frame_input.__wrapped__` 不存在（先 AttributeError）——双双被 `except: pass` 吞 → **每个 matchup 0-0, 全矩阵战报是对零矩阵的排名**。
- `branch_demo.run_branch`: 对闭包取 `len()` → 首帧 TypeError, 进程即死。
- 两者均零调用者零测试——E1/F6 的"交付"只存在于测试文件的合成路径里。

## 2. P1（八项）

| # | 发现 | 证据 |
|---|---|---|
| P1-A | **ender 未在任一调用方接线**: 执行器按契约返回 `("ender", indices)` 作 current_input——无调用方检查, 元组落入 `_sc_next_input` → 后续 SC 帧字典更新崩溃（复现）; 菜单掩码从未实施（文档称复用事件掩码——未接线） | macro_executor:184-194 ↔ train_tm:1368/side_driver:391 |
| P1-B | **teach 价值讲解死亡 + 情境编码错位**: `_, V =` 3 元组解包（**本会话第三个同型解包 bug**）→ 异常被吞 → V≡0 → 排名退化为宏序号、测试的"情境敏感"断言是 hardcoded True; 即便修解包, 硬编码 core 偏移与 feat_builder 实际布局错位（spirit 写进角落位、own_hp 留 0="我死了"、opp_air 写进卡槽位） | teach.py:96-116【亲验解包】 |
| P1-C | **episode 先删后更**: `update_from_episodes` 在 load 循环内 `os.remove`, update 崩溃=整批永久丢失（P0-A 的放大器） | learner_hub:186 |
| P1-D | **supervisor 自毁 + 一小时死**: `reap_orphans()` 在 boot **之后**调用——WMI 匹配自家新拉起的车队（ppp 不在存活集）→ **启动 ~175s 后杀死自己的全部子进程**; `STORE` 未定义 → 首个 league 周期(3600s) NameError 杀死监督器 | fleet_supervisor:94/209【亲验位置】 |
| P1-E | **c6 生成器角色 ID 表 11/17 错**: 与 card_tables/gen_newchar_libs/train_tm 三方真值交叉比对——9 个 SC 费用取自**别的角色**（youmu 203=3 实为 5 等）+ 截断名碰撞产生**重复宏名**（remilia/komachi 各一对, 名字索引静默解析到第一个） | tools/c6_integrate:27-31【代理程序化比对】 |
| P1-F | **habit_detector 旗舰检测器失效**: "起身蹲防"只录 `act<50`（防御态 150-166 永不入样本——只能测"起身蹲着待机"）; `pressure_backjump` 的 `opp_attacking` 恒 False（初始化后从未置真）——五习惯实际三活二死 | habit_detector:77-109 |
| P1-G | **bc_match 镜像翻转 V 轴**: mirror 版 keys_to_input 把 up/down 也翻了——专家流从不翻 V → 换边段的空中宏标签静默丢失/错配; 另 train_tm 与 bc_match 的 KEY_TO_BIT **V 极性相反**（各自对, 同名表反义——复制陷阱无文档） | bc_match:36-44 |
| P1-H | **frame_events 前缀匹配错解析**: `2A` 恒命中 `2A确认`（库序在前）——时间关键的防御反应实际插入带门连段; suika 只是碰巧库序在尾; pick 与 mask 两处 continue/break 不对称 | frame_events:278-287【代理动态确认】 |

## 3. P2（择要; 完整清单见各代理报告存档）

- **numpy↔GPU 一步更新权重不等价**（代理从相同权重各走一步的探针: 总体 cos 0.99 但对手偏置 cos≈0、逐张量 rel-diff 至 1.3）——根因四件: 损失归约 sum-vs-mean 约定、rstd EMA 先除后更（numpy 先更后除）、联合梯度裁剪共享预算、bc_targets=None 时的**幽灵自模仿**（探针 C: b2 25% 符号翻转）。GPU 另有四项鲁棒性缺口: 无 NaN 梯度守卫（一坏批→内存网永久 NaN→僵尸 learner）、形状不符只打印不拒（P0-A 的共犯）、缺 sum(ep_lens)==N 断言、统计字典缩水。**"语义等价"只在前向/序列化层成立**——值路径逐步精确（rel_diff=0.0000）除外。
- gate_selftest **基线无法绿**: 沙箱 FILES 缺 macro_executor/difficulty/habit_detector（side_driver 导入即崩）+ 8 条死变异（R61t/u 重构后未迁）+ 3 条重复——治理工具本身处于失效状态。
- 治理固化加剧: C13-fleet 段 ~90% 精确文本钉（连 SplitMix32 常数都被钉）。
- fleet 侧: disk_guard 三病（字典序删最新/跨角色删 episode/never-False）; **池快照写在 actor 不读的路径**（league 对手冻结在生产快照）; com_difficulty 共享文件多写者; _remake_env 丢 fleet 车道; **构造路径首局恒系统卡**（deck 在构造后才赋值——R53 只修了续局路径, ~15-20% 局无技能/SC）; 版本号非单调（损坏→重发 v1→actor 静默回滚古权重）。
- 产品面: c6 的 TM 宏**未过规范化**（R46 死招类第三次复发——yukari/tenshi/youmu/cirno 实测含 <5 帧预置攻击步）; easy 的 ban_sc 漏掉含 sc: 步的 TM 连段（自毁式宏而非禁用）; trialmode 转换器 j5a/j6a/d6 token 死路径 + 214 记法直接拒收; bc_build LAYOUT 串过期（'5N+308:v2' vs 实际 5N+316）; batch_explain 双轴垃圾输出（dx×1000、macro_id=-1→恒报最后一个宏）。
- 执行器细部: 分支门单帧瞬时 d_deal 无结算窗（R5 教训未继承到新门）; R34 守备豁免 P1/P2 参数不对称; 帧级事件清队不清 dec_name（误记空挥）; 守卫 ID 集第三副本（158 空防语义缺口未文档）。

## 4. 正面基线（零先验机器验证）

- **20 宏库静态契约全绿**（两代理独立确认: 门位零违规/轴冲突零/sc: 全可解析/类别零幽灵——c6 交付前 R39 契约保持）;
- **帧级事件 ID 集一致且有 16/16 行为测试钉住**（R61d 裁决保持）; sc 词汇机制（R61g）行为正确;
- **fleet 四注入点与当前 train_tm 完全对齐**（含 F-11 后的 logps= 签名; 局边界 _ppo_act 刷新在 actor 模式实测触发）; 快照发布序/单写者/红线①③机制完好; tm_env/soku_client2 防御深度完好;
- **ppo.py 数学再次全对账**（clip/GAE/熵/replay/退火/迁移）; GPU 值路径逐步精确; 三套既有等价测试如实通过;
- Trialmode 数据源为真（真机连段包, 帧偏移/伤害值游戏实测级）——缺陷仅在转换层。

## 5. 修复优先级（前八）

1. **learner n_side 改 CORE_DIMS 派生 + 宽度断言 + 零形状警告门禁**（P0-A, 半小时, fleet 复活的前提）;
2. **supervisor: reap 前置 + STORE 定义 + episode 改 update 成功后删**（P1-C/D, 一小时）;
3. **train_tm 入队保留 fr + ender 调用方接线或临时禁用 ender 步**（P0-B/P1-A）;
4. **eval_matrix/branch_demo/teach 三工具修**（各一两行: last_state 初始化/wrapped 移除/len 条件删除/三元解包/偏移重写）+ E2 测试撤 hardcoded True;
5. **c6 CID 表修正 + 8 库重生成 + 重复名清理 + TM 宏规范化入生成器**（P1-E + P2 规范化复发）;
6. gate_selftest 复活（FILES 补三文件 + 8 死变异迁移）——治理恢复视觉得先于一切;
7. bc_match V 轴 / habit 检测器修正 / frame_events 前缀改精确名匹配;
8. 治理: C13-fleet 段从文本钉改行为断言（固化清单已存档）。

## 6. 方法论结论（#2 vs #1）

- **制度价值再次实证**: 本轮 3 个 P0 + 8 个 P1 全部是"单元测试绿、集成缝断"型——冲刺速度越快, 此病越重; **建议给 F1 制度追加触发条款: 凡"新模块+新调用方"成对落地时, 必须附一条贯通两者的集成测试方可合批**（fleet init/actor 集成/ender 调用方/eval 的 run_matchup 四个断点全是缺这条的直接后果）。
- **审查者锚定第四次实证**（本报告 §0）; 修订 SOP 应加入"常量横扫"步骤: 改任何 `CORE_DIMS`/`N_*` 类常量后, grep 全库旧值。
- numpy↔GPU 的"一步更新等价"探针（本轮代理自制）应转为常驻门禁断言——它一次抓出了四个语义差。

*本报告由 4 个零先验子代理 + 审查者亲验合成; 全程只读。*
