# th123_rl 审查报告（第十八轮 · R52-R56 新代码严审）

> 日期: 2026-10-04 22:10 · 方式: 只读严审（新模块逐个亲读 + 接线点逐一核验）
> 范围: 17:00 后全部新代码——R52 启动修复、R53 deck 续局包、R54/R54b ppo_gpu 重写、R49 pose 特征、**R56 fleet 全栈**（episode_core/actor_worker/learner_hub/fleet_supervisor/portmap 扩展）
> 前置状态: 我方独立完整自检 108+1 全拦截（含修复后的 2 条漏网）; ppo_gpu 往返双向 0.00000000 亲测

---

## 1. 总评

**R56 fleet 实现质量高于预期**：组合复用 TMTrainer（比设计稿的函数抽取更强的防漂移——任何 train_tm 改进自动进 fleet, 论证成立且已在代码注释中留档）; 三条红线全部有机制+断言双侧落地; 四个注入点（`_fleet_logp_rec`/`_snapshot_pool`/`_submit_update` 覆盖/`build_opp_cycle`）在生产代码里有真实挂点（train_tm:386/718/1350/1623 逐一核验）; A/B 期 `_fleet` 后缀隔离; 单写者纪律; 陈旧度仪表在 [learner] 行。但从严揪出 **2 高 + 3 中** 个实质缺陷, 其中两个在多 actor 一上线就会生效。

## 2. 严审发现（按严重度）

### 2.1 [高·多 actor 即生效] collect_episodes 饥饿偏差

`learner_hub.collect_episodes`（:90-94）按**文件名字典序**排序取 `[-k:]`。文件名格式 `ep_{char}_{actor:02d}_{ep:05d}_{ts}` → 排序主键是 **(actor_id, ep_idx)** 而非时间。两个以上 actor 时, actor00 的局永远排在序列前部——`[-k:]` 恒取高编号 actor 的最新局, **低编号 actor 的经验被系统性饿死**（其文件滞留目录, 队列无界增长, "目录残留数=滞后仪表"的读数随之失真）。单 actor 无症状（掩盖性强）。
**修法**: `os.scandir` + 按 mtime 排序（或文件名内嵌单调 ts 作主键）。建议 test_fleet_protocol 补"多 actor 交错写入 → learner 消费覆盖所有 actor"用例。

### 2.2 [高·学习质量] bc_extra 终身固定 64 行

`learner_hub.load_bc_bank`（:51-69）在启动时采样一次 64 行, `update_from_episodes` 每批复用**同一组**专家行。单实例 trainer 是每次 update 重采样（`_sample_bc`）——锚的意义在于从 9k-16k 库持续抽样, 固定 64 行会把 bcw 拉力过拟合到这 64 个样本上。
**修法**: 每次 update 前重采样（rng 按 update 序号派生, 保持可复现）。

### 2.3 [中·红线③子项] 每局 RNG 状态复位

actor 模式下 `tr.ppo` 永不更新 → `tr.ppo.rng` 状态冻结; 每局 `_ppo_act = deepcopy(self.ppo)` 从**完全相同的 rng 状态**出发（actor_worker:166-180 只在换版本时重播种）。后果: 12% 探针的随机掷点、采样噪声的**随机序列逐局重复**（游戏状态不同所以动作不同, 但探索的随机结构同构——跨局相关性, 正是红线③要防的）。注释里"局间由deepcopy的rng状态自然推进"的判断不成立（推进的是 _ppo_act 的副本, 源头不动）。
**修法**: `run_with_snapshot` 每局 `tr.ppo.rng = default_rng(seed_base + ver*1e6 + state['ep'])`。

### 2.4 [中] actor 宏计数与 learner 合并档脱钩

actor 从**生产无后缀档**初始化本地 macro_counts（TMTrainer 构造路径）, learner 把增量合并到 `_fleet` 后缀档（:192-211）。配额探索（counts<150 判定）永远基于陈旧的启动值+本 actor 自增——跑得越久偏差越大。
**修法**: 快照目录附带 counts（actor 换版时一并载入）, 或 stats.json 下行通道。

### 2.5 [中·已在训练中生效] R49 "pose/段位感知"为虚假特性

`feat_builder.py:313-339` 三重问题:
1. `_my_pose/_opp_pose/_my_pf/_opp_pf` 四变量**计算后从未写入任何维度**（注释称"写入段3空闲位", 段 3 实际只写 back_turned 与 0.0）——纯死代码;
2. "下段 0.5 标记"的门控 `128 <= action < 256` 覆盖的是**受击/倒地段**——攻击区 300-598 根本拿不到标记;
3. 即便范围修正, `(action//64)%2` 也区分不了 2A(303) 与 5A(300)（两者 //64 同为 4）——低/中段的区分在招式 ID 本身, 不在区间折半。
**结论: "段位/蓄力可见"的宣称不成立**——特征层对段位仍然全盲（技法覆盖分析 L2 缺口未闭合）。门禁断言大概率是子串型放行了它。
**修法**: 四个 pose 值实写入段 3 的 [o+1]（turn_recency 挪到别处）或段 9 死维; 段位用"对手当前招式 ID ∈ 下段表"的显式查表位（数据源: XML 权威表）。

### 2.6 [低·记录] 其他

- league/COM 阶梯统计分散在各 actor 的 scratch/stats.json——supervisor 的 `league_alloc(stats)` 聚合源未及细验（若读错路径则 league 退化为均分, 不崩）;
- `load_bc_bank` 用 `rng(0)` 固定采样——与 2.2 同根;
- fleet 段 21000-21299 与既有段几何不交叠（亲验）; C12 断言是否已枚举 fleet 车道待确认;
- episode_core 的 EP_KEYS 无 schema 版本字段（格式演化时旧文件歧义, 建议加 v1）。

## 3. 验证通过项（值得记录）

| 项 | 核验 |
|---|---|
| 红线①双侧 | actor 采样时记录 logP（train_tm:1350 决策点挂点真实）+ submit 长度断言兜底 + learner stored_logp（ppo_gpu:255-260 带长度断言）|
| 红线② | 局边界读 version + 先写快照文件后写版本号的原子序（publish 顺序正确）|
| 单写者 | actor 四改道（counts/pi/v→scratch, 池/蒸馏禁写）; learner 独占合并 |
| GAE 边界 | 逐局 ep_lens 传入, 不跨局泄漏 |
| rebuild_port 补丁 | 对模块属性打补丁 + train() 运行时 from-import 取到补丁版——手法正确 |
| R52 六修复 | frozen 前置定义/导入别名/names→CHAR_LIBS/choices→choice/EV_NAMES/weights——训练实跑零异常佐证 |
| R53 deck 续局包 | _restart_same_process 双 deck 源（修复者称+贴文佐证, 本轮未逐字复核——列入下次抽查） |
| R54b 往返 | 我方严格往返测试 0.00000000 双向 |

## 4. 行动建议（按序）

1. **修 2.1（饥饿）与 2.2（bc 固定采样）**——多 actor 上线前必须; 各一行级改动 + test_fleet_protocol 补用例;
2. 修 2.3（每局重播种）与 2.4（counts 下行）;
3. 2.5 pose 特性: 要么实做（查表段位位 + pose 入死维）要么删除死代码并修正文档宣称——**不许保留"特性存在"的假象**（这正是第十七轮"存在≠生效"教训的再现）;
4. fleet 上线前跑一次 test_fleet_protocol + 双 actor 干跑（本地 2 actor × 1 learner, 验证饥饿修复与 A/B 隔离）;
5. 2.6 诸项随下波清理。

## 5. 方法论备注

R49 pose 与第十七轮 S1/S2 同型——**"宣称的特性"与"实际生效的特性"之间隔着 接线/生效/正确 三道坎**, 门禁若只用子串断言就永远绿。建议把本次 2.5 的修法（显式查表位 + 行为断言: 构造蓄力状态的特征向量必须变化）作为"感知特性断言"的模板。

*本轮全程只读; 未修改任何文件。fleet 尚未上线（训练仍为单实例三角色运行中）——所有发现都在生效前窗口内, 修复零风险。*
