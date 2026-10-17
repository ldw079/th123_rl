# 从零全盘审查 #5（2026-10-17 晚）—— 从严全面审计

> **基线**：HEAD `21bfcdb`（工作区干净，无未提交改动；main 分支；全库 219 commits，
> 597 tracked 文件 / 421 个 .py / `tests/` 89 个 `test_*.py`）。历史已于当日 19:13 被
> PR-5 公开化重写（旧历史仅存本地分支 `pre-rewrite-backup`）。
> **审计时刻**：2026-10-17 19:29–19:55 +08（进程/日志/产物三面采样于 19:29–19:40，
> 门禁实测于 19:30–19:40，复采于 19:52–19:53）。
> **范围**：全库重验（不依赖任何先前审计结论）——门禁全量 + 5 个零先验分片
> （A 训练主链 / B fleet 与协议 / C 数据与 BC / D 评估与仪表 / E 文档与卫生）
> + 审查者亲验全部 P0 + 中央五项（门禁/编译/import 图/纪律横扫/三面对账）。
> **判定**：**不放行。** 主干训练链健康，但**治理执行层整片失效**，且基线
> **门禁自身为红（阻断）**——按红线 #3「门禁不过不许提交」，当前 HEAD 不具备
> 提交/发布资格。

---

## 一、总判定

三条主线各自的结论：

| 面 | 判定 | 依据（全部实测） |
|---|---|---|
| **训练主链**（当前代） | 正常 | 三 learner 当前代日志 0 异常/0 nan；批更新流转正常（reimu v1731→v1732 / marisa v2035 / suika v1497）；快照/契约/原子落盘链自洽 |
| **治理执行层** | **异常（P0×5）** | 门禁在基线为红（+PR-5 路径重写破坏复现链）；R14 CPU 看门狗成死代码；并行变异 sweep 无基线守卫；对照臂静默停机 |
| **数据与评估可信度** | **异常（P0×1 + P1×8）** | **在跑 BC 库的 SC 标签取错帧（3 宏恒学不到、1–6% 行错标）**；评估工具读 10-15 旧档；17 个 league 种子同一权重；LE-1b 热度通道四重失效；episode 契约不校验行数；低信息降采样「取前 N」偏置 |
| **文档入口层** | 异常（P1） | CORE_DIMS/宏数/测试数/门禁数四项齐错，与 10-14 从零#4 同型复发 |

**一句话**：项目把「测量与制度」建得很厚，但**制度自己的执行体（门禁、看门狗、
变异 sweep）在本轮同时失去效力且无人察觉**——这与从零#4「自报排错结论应视为声称」
的教训同源，且更严重：这次连"门禁是绿的"这一最底层前提都不成立。

---

## 二、P0（六项，全部经审查者亲验）

### P0-1 基线门禁为红（637/5/2，门禁自判「阻断」）

实测命令（项目文档规定的唯一调用方式，AGENTS.md:55）：

```
D:\temp\pyenv\python.exe -X utf8 tools\contract_check.py
```

实测结果（`D:\temp\audit_scratch_1017\gate_run1.txt`，完整 682 行）：

```
==== 契约门禁: 637 PASS / 5 WARN / 2 FAIL ====
FAIL项: 行为测试@test_gpu_equiv.py, 行为测试@test_guard_height.py
结论: 阻断。修完再合批/发布。
```

两例 FAIL 均为 `ModuleNotFoundError`（`ppo` / `feat_builder`），**根因是当日
19:13 的 PR-5 历史重写**：重写把测试内的绝对路径替换成 `%USERPROFILE%` 字面量，
而 Python 不展开该字面量，于是 `sys.path.insert` 变成空操作。

- 重写前（`pre-rewrite-backup` 分支）：`sys.path.insert(0, r"C:\Users\96120\Desktop\workplace\th123_rl")` — 可用。
- 重写后（HEAD）：`sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")` — 无效。
- 放大因素：本机解释器 `D:\temp\pyenv\python.exe` 是 embeddable 发行版
  （`python312._pth` 存在 → `sys.flags.safe_path=True`），**既不加脚本目录也不
  理会 PYTHONPATH**（实测 `PYTHONPATH` 被忽略、`sys.path[0]=python312.zip`），
  所以测试只能靠自身 `sys.path.insert` 生效。

**后果**：红线 #3（「门禁不过不许提交」）在基线即被违反；而最近数条提交消息仍写
「门禁639/0」——那是重写前的读数，重写后**未重跑门禁**。门禁自身输出已写
「结论: 阻断」，此条不需要任何外部判断即可定性。
**档**：需立档（建议 `bug_2026-10-17_pr5_path_rewrite_breaks_gate.md`）。

### P0-2 `%USERPROFILE%` 字面量污染 85 个 py / 95 处（同一重写引入，破坏复现链）

不止测试：**生产模块**同样中招。实测统计（`git ls-files '*.py'` 全扫）：

- 命中 **85 个文件 / 95 处**；核心生产件：`bc_build.py`、`oracle_batch2.py`、
  `run_parallel.py`、`tools/{cleista_ingest,fangyu_extract,fangyu_index,
  mine_air_moves,mine_input_moves,combo_mine_positional}.py`、`tests/test_{gpu_equiv,guard_height}.py`；
  其余集中在 `_archive/legacy_20261006/`（无害）与 `tools/quarantine/`。
- **BC v2 重建静默取 0 分片**（`bc_build.py:484`）：

```
literal  glob = 0        # glob(r'%USERPROFILE%\...\oracle_v2\shards\*.npz')
expanded glob = 1724     # os.path.expandvars(...)
```

  即：下一次 BC 重建会**静默产出空库**（或按 `bc_build.py:492` 默认输出目录在
  CWD 下建字面量目录），而 BC 库是全部模仿梯度的来源。
- `oracle_batch2.py:23` 的 `OUT` 同样未展开 → 产物落错目录（分片 D 实测在 CWD 下
  建出字面量目录）。
- 该问题**已被登记**在 `docs/_pending_entries.md` 队列条目 6（「重写后……现为
  `%USERPROFILE%` 字面量，逐处包 `os.path.expandvars`」），但**未执行**即被重写
  提交，且条目把范围低估为「~10 个 py 工具 + 2 tests」（实为 85 文件 / 95 处，含核心模块）。

**档**：与 P0-1 同档（同一根因，建议合并立档）。

### P0-3 R14 CPU 红线看门狗：健康车队下是死代码（红线两日未执行）

`fleet_supervisor.py:477-509`——采样调用 `_wd.sample(...)`（:483）被包在

```python
if _exhausted and _hb % 18 == 0:          # :477
```

之内，而 `_exhausted` **只在重启耗尽时填充**（:543，全仓唯一写入点）。因此
**正常运行时 CPU 策略从不执行**。现场证据：现网无 `fleet_heartbeat.alert`
（`_exhausted` 为空），整机负载 100%（实测 19:31 / 19:39 两次），监督器无任何动作；
监督日志最后一次 CPU 降容是 **10-14 19:31**。

- **回归来源**：`41ecdb1`（2026-10-16，CE/BH 大波，`git log -S "_exhausted and _hb % 18 == 0"` 唯一命中）
  —— 该波为修「重启耗尽静默减员（P0）」加了节流告警，**把整块 CPU 策略一起圈了进去**。
  这是「修一个 P0 引出另一个执行层失效」的典型。
- **测量口径另有缺陷**：`cpu_load_pct()`（:99-109）取的是**整机**
  `Win32_Processor.LoadPercentage` 均值，不是「训练族总量」。实测判据：
  整机 100% 时，fleet 全家（3 learner + 3 actor + supervisor + 3 游戏）
  实测仅 **30.4 CPU-s / 10s ≈ 整机 18 逻辑核的 17%**；其余为 ZCode 智能体与会话
  与 6 worker 变异 sweep。→ 红线即使被激活，也会把**旁路负载误判为训练负载**并杀
  actor（10-14 的「看门狗震荡 8 次往返」正是此口径所致，从零#4 只记为 P2 震荡，
  本轮定位到真因）。

**影响面**：红线 R14 为**用户明令**，当前处于「制度写着、代码不执行」状态≥2 天。
**档**：需立档（`bug_2026-10-17_cpu_watchdog_dead_under_exhausted_guard.md`）。

### P0-4 并行变异 sweep 无「基线绿」守卫 → 184 条变异结论全部为空判

`tools/gate_selftest_parallel.py:37-81`（R159 新增，用于「全量 sweep 加速」）与串行
版的关键差异：**串行版先跑未变异基线并要求绿**（`gate_selftest.py:847-857`：
「基线不绿 — 先修门禁本身」并立即返回 1），**并行版完全没有基线步骤**，只判
`ok = rc != 0 and ('  FAIL' in out)`（:75）。

因此在当前基线为红（P0-1）的状态下，**任何变异都会得到 `rc != 0` + 含 `FAIL`** →
被记为「✓红」。实测 `D:\temp\sweep_parallel.log` 已跑到 83/184 并全部「✓红」，
末尾 `PARALLEL_DONE rc=1`。该 rc=1 的语义是「有漏网」（:120），只能来自**变异导致
门禁自身崩溃（输出无 `  FAIL` 行）**的条数——与「变异被拦截」无关。

**结论**：本日「184 条变异 sweep」不能作为任何 P0 修复已被钉死的证据；项目长期依赖的
「变异钉 150+」防线在当前环境**整体失效**。
**档**：需立档（`bug_2026-10-17_parallel_sweep_no_baseline_guard.md`）。

### P0-5 LE-0a 对照臂自 16:45 停机 ≈3h，无告警；预注册 A/B 终点断流

实测：

| 面 | 主臂 | 对照臂 |
|---|---|---|
| 进程 | supervisor + 3 learner + 3 actor + 3 游戏（7 py / 3 游戏） | **0**（无 python、无游戏） |
| 模型 mtime | `model_ppo_*_fleet.npz` 19:28–19:31（活） | `th123_models_control/*` **16:45:20** |
| 最新 episode | 19:36 | `ep_reimu_08_00104_20261017_164507.npz`（16:45:07） |
| 日志 mtime | 19:30 | `control_actor.log` 16:41 / `control_learner.log` 16:12 |

停因可定位：`tools/train_start.py:46-56` 的残留清理按**脚本名匹配**
（`fleet_supervisor|run_parallel|learner_hub|actor_worker|exploiter`），**不区分
worktree/store**——对照臂跑的就是同样的 `learner_hub.py` / `actor_worker.py`
（`D:/temp/th123_rl_control`，端口 21080）。主臂 16:45–16:51 重启时把它一并杀了。
此风险 `METHODOLOGY 3.57` 已记为「主 fleet 前置清理会误杀对照臂 — **手动重启制**」，
但**没有任何看门狗/告警/停机账**，3 小时无人发现。

**影响面**：LE-8 预注册终点「每千局三段尺斜率 主臂 ≥ 2× 对照臂」的对照臂停摆，
且每次主臂重启都会无提示地再发生一次。此行不污染模型，但使**唯一可信的学习效率
判据**处于不可用状态。
**档**：需立档（`bug_2026-10-17_control_arm_silent_death.md`）。

### P0-6 SC 标签取错帧：在跑 BC 库约 1–6% 行错标，3 个宏永远学不到

`bc_build.py:303-309`——凡命中宏名属于 `_sc_tgts` 的行，一律用**命中首帧**的手牌
解析具体卡：

```python
if _mname in _sc_tgts:
    _ri = resolve_sc_label(_sc_tgts, _sc_idx_by_name, fr[h[0]][0]['hand'])
```

但 `TM·6a终结` / `TM·必杀SC连`（marisa）/ `TM·空连终结`（suika）的 `sc:` 步在
**宏末**，`h[0]` 是连段起手帧 → 取到的是**连段开始时**的手牌，而不是出 SC 时的手牌。
分片 C 实测：三角色库 `Y` 中这三个宏计数 **= 0**；`卡·当前`（通用 SC 宏）
marisa **17,691 行（5.1%）** / suika 5,830 行；4 个真实 shard 侧重放中 SC 命中
14–35 条，重标后 12–29 条变成别的宏（多为 `卡·当前`）＝ **80–96% 不一致**。

**影响面**：正在训练的 BC 库（429,411 / 349,922 / 328,116 行）约 **1–6%** 行的标签
指向「另一张真实 SC 宏」（不是垃圾标签，但属错误归因），且这 3 个宏**永远学不到**。
这是本轮**唯一落在训练数据面**的 P0（与其余五项治理型 P0 性质不同）。
**档**：需立档（`bug_2026-10-17_sc_label_wrong_frame.md`）；精确错标率需一次
rebuild 探针定口径（分片 C 用 4 个 shard 侧外推，未做全库重建）。

---

## 三、P1（十项主线 + 附录 A 一项 + 亲采/分片 C 四项，共十五项；摘录关键证据）

| # | 发现 | 位置 / 证据 |
|---|---|---|
| 1 | **评估工具全部读 10-15 旧档**，非活 fleet 模型。`model_ppo_reimu.npz` mtime **10-15 09:19**，活档 `model_ppo_reimu_fleet.npz` **10-17 19:31**；报告 JSON 无模型版本/时间戳字段 → 静默过期（`eval_matrix_quick_20261014.json` 于 10-17 19:20 被重写，内容仍是旧档） | `tools/eval_matrix.py:42,67-68`、`tools/deck_matchup.py:45-46`、`tools/attribution_probe.py:63-68` |
| 2 | **17 个 league 种子是同一份权重**：实测 `fleet/pool/*/seed_*.npz` 共 17 文件、**1 个 distinct MD5**（`B71F28D8…`），且 meta `temp=2.0`；三主模型 `temp=0.5`，而 SideDriver 采样温度逐模型取 meta → 20 角色矩阵把「温度/宏库差异」读成角色强度，`superhuman_gauge` 的 dominance 建立其上 | `tools/seed_league_pool.py:57,73`、`side_driver.py:291-293` |
| 3 | **LE-1b「热度加权注入」双重失效**：①`le1b_inject` 调 `query(..., heat_weighted=True)` 但**不传 `matchup`** → `query` 内 `if heat_weighted and matchup is not None` 恒假，热度分支从不执行（实测 le1b 形态查询返回 66,940 行 = 无热度时的全量）；②即使传了 matchup，**极性是反的**：`keep = rng < (1-h)`，而 h=弱点度（h=0.962→保留 3.8%，h=1.0→保留 **0** 行），与注释「弱点对位全取」相反 | `tools/le1b_inject.py:50-52`、`tools/situation_library.py:160-166` |
| 4 | **episode 契约不校验行数 N**：写者自检（:213-226）与读者（:274-287）只比**宽度**；分片 B 实测「feats/sides 8 行、acts/logps 4 行」的文件被 `save_episode_npz` 接受、被 `learner_hub` 消费、随后 `os.remove` ——无隔离无告警。`ppo_gpu.py:281` 的长度断言在 fleet 路径恒真（`ep_lens` 取自 `acts`） | `episode_core.py:213-226,274-287` |
| 5 | **单写者纪律半修**：actor 已把 counts/model/distill/pool 改道 scratch，但 `train_tm.py` 的帧日志仍写共享 `STORE/frame_logs/`，且按 `glob('fl_*.pkl')` 只留 500 ——**跨角色互删**。实测该目录 23 文件（marisa 9/reimu 7/suika 7）三色交错、`.last_<char>` 门闸共用，19:40 仍在写 | `train_tm.py:2037-2058`、`D:\temp\th123_models\frame_logs` |
| 6 | **评估侧输入分布≠训练分布**：SideDriver 从不注入 `opp_char_id`，实测 `core[227..252]` 仅 249 非零（训练侧是 `core[227+opp_id]=1.0`），连带 `_opp_char=None`（逐角色守备表不生效）、`_jz1_ids=(0,0)` | `side_driver.py:120`（写入点只在 `train_tm.py:797-806,1000-1018`） |
| 7 | **重启预算终身累计、告警写而不读且会被自己清掉**：`restarts` 无衰减（20 次**终身**崩溃即永久减员）；`fleet_heartbeat.alert` 全仓**无任何读者**；且重启路径 :552 的无参 `write_heartbeat()` 会删除 alert 文件 | `fleet_supervisor.py:443,536,552,557` |
| 8 | **监督循环无异常屏障**：主循环体（:459-583）无 try/except，`log()` 的 append、`_spawn_actor` 的日志 open 均可抛；异常退出不走 `_clean_shutdown` → 整队孤儿（监督日志 16:51 有「孤儿回收 PID=19136（父已死）」前例） | `fleet_supervisor.py:459-583,585-593` |
| 9 | **仪表假绿/硬编码**：`status_dashboard` 活性巡检写死「通过(358维,29+8段)」、更新数恒 0、远程弹幕/被动性硬编码区间、以正则取系列曲线 b1 桶**样本数当战绩**（实测 suika「100%(3)」）；`eval_matrix.py:188` 路径已被转义成控制字符（源文件实际字节为 `D:<TAB>emp<TAB>h123_models<FF>leet_supervision.log`，即 `\t`/`\f` 被解释）→ 文件永不打开，`four_lenses()` 静默返回全 None | `tools/status_dashboard.py:119-124,246,269,296-297`、`tools/eval_matrix.py:188` |
| 10 | **文档入口层四项齐错 + R14 自相矛盾**：README=343 / AGENTS=330 / 实际 **358**；AGENTS 宏数 70/76/77 / 实际 **88/95/91**；README/AGENTS/HANDOVER 测试「71 档/70/70」/ 实际 **89**；门禁数文档并存 568/600/618/634/639 / 实测 **637/5/2**。METHODOLOGY R14 写「torch 限 3 线程」（代码默认 **2**）、写「只降不升」（代码已实现可恢复暂停，R75），AGENTS 红线 8 又写「连续 3 次」（代码为 6 采样滚动窗） | `README.md:50,63`、`AGENTS.md:11,27,60,80-82,106`、`HANDOVER.md:22,65,97,198`、`METHODOLOGY.md:31`（R14）、`ppo_gpu.py:33` |
| 11 | **`ppo.py` 主干价值梯度混用已更新的 `W1v`** → numpy 与 torch 两个 learner 每步方向不同（`cos` 实测 0.396/0.637/0.564，`VF_LR=0` 时为 1.0）。fleet 走 `ppo_gpu` 不受影响；单机 `train_tm`/剥削者受影响，且「双实现等价」契约被破坏 | `ppo.py:954` vs `:991`（详见附录 A） |
| 12 | **LE-2 警戒表「伪条目」只修了一半**：空集已修（`guard_crush`/`air_unblockable` 现有值：妖梦 4 / 灵梦 7），但 `warning_moves` 里**仍混着叙述句当招名**——实测 **71/255（28%）** 为句子（如「B版两个圈，C版四个圈」「360度全方位发射的短激光射击，一共十个」「2A和2B打不到，使用时要三思」），且 `advice` 尾部常粘着**下一条招名**（「…昇天脚」）。10-17 审计已写「严格修复误吸未除尽」，当日「双清偿」提交后仍未除尽 | `data/guide_tables/fangyu_counters.json`（审查者亲采，按角色：天子 16/39、灵乌路空 11/58、早苗 9/18 …）；生成器 `tools/fangyu_extract.py` |
| 13 | **低信息降采样「取前 N」而非随机**（在跑库）：`low_pos = np.where(low_mask)[0][:n_low]` 取行序**最前** 15%，不是随机抽样 → 保留下来的「待机/前进/后退/守」样本系统性地来自最早的 shard/对手槽（分片 C 实测低信息行只出现在 group 序 reimu 0..162/961、marisa 0..143/898、suika 0..102/813，对手槽仅前段 0/2；反推降采样前低信息占 47–54%）→ 在跑库 12–15% 行（5.3/4.2/4.8 万）的移动先验被偏置到「最早遇到的那几个对手」 | `bc_build.py:449-455` |
| 14 | **情境库热度 id 空间错位**：`mid` 用**池槽**（0/1/2/11–19/20–27），而 `heat` 的键是**raw char id** → meta 里的 `'9'`（萃香 raw id）永不命中池槽 2，`'2'`（咲夜 raw id）会**错配**到萃香行；marisa 的 4/7 对位无任何 mid；且 `h=1.0` 的对位（marisa 2/4/7、suika 1/9）在 `heat_weighted` 下返回 0 行。与 P1-3 的 `matchup=None`、`keep=1-h` 反转叠加成**四重失效** | `tools/situation_library.py:59-66`（分片 C 实测）、`:94-95` |
| 15 | **LE-1b 20% 上限未真正生效**：`inject_count` 无 clamp（ratio=0.5→32/64；ratio=1.0→64/64）；ratio=0.2 且序列窗短时 batch=`L+12`，实测 1.0–2.9% 抽样**超 20%**（最高 75–78%），4000 抽样中 4–28 行重复（序列窗与注入行重叠）。默认 `TH123_LE1B_RATIO=0` 故 fleet 现在不受影响 | `tools/le1b_inject.py:33-37` |

---

## 四、P2（择要，共 20+ 项）

- **无界旁车**：`fleet/episodes/` 内 `bh_*.json` **547 份 / 1.7MB（19:40）→ 556 份（19:53）**
  （自 10-16 20:25 起无清理，消费者只删 `ep_*.npz`）；`behavior_health.aggregate(..., 200)`
  只读最近 200 份，更早的静默掉出聚合。
- **门禁 5 条 WARN 全是旧代 store 残留**：`macro_counts_{reimu,marisa,suika}` 宽 70/76/77
  ≠ 代码 88/95/91；`suika BC` 宽 715（want 813）+ layout 标签待迁移（`bc_label_migrate`）。
- **audit_all 的奖励面板在 fleet 架构下结构性失效**：它从 **learner** 日志找「奖励成分」，
  而该行由 `train_tm` 打印到 **actor** 日志（实测 actor 日志有、learner 日志 0 条），
  故面板恒显示「无奖励行」。
- **JZ-1 段 7/15 维生产恒零**（core[349-354,357]：技能摘要/破珠/healingCharm），同批字段在
  人类语料上非零（skills 58.3% 等）；`jz1_features` 全 `.get(默认0)` 无计数/告警。
- **对手「防御族」生产近死**：19 局 33,804 帧中对手 action∈150-167 仅 16 帧（0.05%），
  451 决策里 13 个防御情境维恒 0 → behavior_report 表 6-8（防守错位矩阵）分母≈0 不可用。
- **版本文件损坏→静默冻结**：`episode_core` 读版本失败返回 0，actor 门 `if ver > 0`
  → 永久用旧权重且无日志（若 learner 已耗尽则「看起来健康」）。
- **重置预算/吞吐类**：`soku_client2` 失败路径只 `terminate()` 无 `kill` 兜底；
  actor 崩溃重启路径不清理旧游戏子树（现网无泄漏）。
- **工具卫生**：`tools/_*.py` 8 个零引用 scratch（违反「探针不留残档」）；
  `tools/*.json` 35 个运行产物入库而 `.gitignore` 未覆盖；`_archive/` 内 3 个已跟踪件
  （与 `.gitignore:7` 冲突）；`eval_vs_th123ai.py` 未实现却 `return 0`；
  5 个测试硬编码 330/343 维度；`items test_situation_lib` 仅校验 reimu 热度<1
  （marisa/suika 实际含 1.0，扩到三角色即红）。
- **文档卫生**：INDEX 计数错（`_reviews` 22 vs 实际 24、`_plans` 23 vs 28）、
  3 个活跃文档未登记（DATA_POLICY/LICENSE-docs/game_semantics_tables）、
  METHODOLOGY「尾部即最新」不再成立（尾部是 3.20，最新 3.59 在 L2794，且 3.20 重复两次）、
  1 条断链（`docs/soku_action_ids.md:411` 省略号链接）。
- **`%USERPROFILE%` 剩余面**：`oracle_batch2.py:23`（OUT）、`run_parallel.py:14` 等
  非门禁路径（与 P0-2 同源，修 P0-2 时一并清）。
- **数据层杂项（详见附录 B）**：`data/bc` 是 330 代旧库（70/76/77 宏、680/710/715 宽），
  与在跑 trio 身份混淆；`bc_io.py:191` 写 C 列但 `load_bank` 不返回 C、meta 无 C 哈希；
  `migrate_bc_b.py:55` 重建静默丢 `I`（seq→iid 降级）；situation meta `n_matchup` 恒=rows；
  `bc_build.py:183-204` 立防标签含 0–9 帧未来窗；`distill.py` 默认 data 路径不存在；
  `query` 每 update 读 40MB npz（≈94ms）。

---

## 五、中央五项（实测）

| 项 | 结果 |
|---|---|
| **门禁** | **637 PASS / 5 WARN / 2 FAIL → 阻断**（两例 `%USERPROFILE%` 根因） |
| **编译** | `compileall -q -f .` 退出 0；仅 `_archive/legacy_20261006/status.py:2` 一条 SyntaxWarning |
| **import 图** | 301 个本地模块、571 条本地 import：42 条解析不到（17 在 `tools/quarantine/`、其余 `soku_arch` 外部包 + `sklearn`/`oracle_batch` 历史名）；**生产链 4 模块实测 import OK**（`bc_build/bc_match/oracle_batch2/distill`，依赖 `D:\temp\soku_arch` 绝对路径注入） |
| **纪律横扫** | 62fps：全库 `/60` 命中 9 处**全部合法**（时间换算/`sleep(1/60)`/变异目标串），无违例；原子落盘：`episode_core`/`ppo_gpu`/`ppo` 均 tmp+`os.replace`（一次性迁移工具 3 处例外）；单写者：见 P1-5（帧日志越界） |
| **三面对账（19:29–19:40）** | 进程：10（sup+3 learner+3 actor+3 游戏），对照臂 0（P0-5）；日志：三 learner 当前代 0 异常/0 nan（旧代 traceback 已按「最近一次初始化」定界剔除）；产物：fleet 模型 19:28–19:31 新鲜，episode 积压 12，磁盘 D: 64.5GB 可用，CPU 整机 100% / fleet 17% |
| **复采（19:52–19:53）** | 主臂持续前进：reimu **v1734** / marisa **v2036** / suika **v1499**（较 19:30 各 +1～+3 版）；episode 积压 12、bh 旁车 **556**（+9）；**对照臂仍为 0 进程**（P0-5 未自愈）；`git status` 仅本次审计报告一个未跟踪文件（仓库零改动） |

---

## 六、已验证为正确（可直接引用，不必重审）

**协议与代际**：代际主判据行为可拒收（无 contract 的 v1 / schema=1 / `n_side±1` /
`n_out=63` / `n_macros≠n_out` 全部实测被拒）；`EP_SCHEMA=2`；`n_side==5·n_out+CORE_DIMS`；
ignition BC 宽度硬门禁真实生效（历史日志实测「模型侧宽818≠派生833 … 拒绝启动」×5 后重建）。

**原子性与并发**：episode npz 与 `ppo_gpu.save`（pi/v 各自 tmp+`os.replace`）真原子；
`write_version` 原子；`publish_snapshot` 版本单调地板 + 数值序清理（v10/v2 坑已修）、
缺文件时 actor 不崩；actor 局边界换版并冻结（日志 v1731→v1732 与 meta `snap_ver` 一致）；
`(actor_id, version, ep)` SplitMix32 重播种、deck rng 按 actor 独立；`collect_episodes`
排除 `*.tmp.npz`；消费即删推迟到 update 成功之后；learner/supervisor 单实例锁 +
PID 复用命令行复核（现网 3 把锁与活 PID 全对）；端口车道互斥（实测只出现 21000–21029）；
池快照只清自身角色目录且过滤 `exploit_*`。

**当前代训练健康**：三 learner 最近一次「初始化」之后 **0 Traceback / 0 nan**；
`GRU` 活跃（`W_gru` 跨版本变化 1.17e-4）；`value_curve` reshape 在位、日志值非零；
`passivity_meter.ADX_COL=4` 语义正确（`core[4]=dx/600`）；`league` 权重方向正确
（0W9L→1.00、9W0L→0.05）；`league20_opps`=27 确定；Wilson 端点钳制精确
（`wilson(0,3)=(0,0.5615)`）、COM 饱和拒绝当分母。

**数据与标签**：C15 白名单 **89/89** 与 `tests/` 完全一致（无漏注册/无死条目/零 skip）；
沙箱 FILES 覆盖全部 52 个根级模块；`bc_build` 池位单源（真修）；LE-1a 的 2n 偏移标签在
3000 行重算上 100% 一致；BC trio 结构完整（`S` 宽 798/833/813、`rows==meta`、X/S/Y/I 哈希
全对、`[0:n]/[n:2n]` 严格 one-hot、`mirror_input==H` 4000/4000、SC cost 与 `card_tables`
全对、npz 宽守卫响亮拒载）；**今日 P0「情境库热度恒1」公式部分确认真修**（实测 reimu 热度
0.919–0.962、marisa 0.952–1.0、suika 0.941–1.0，非恒 1）；今日 P1「fangyu 伪条目」
**只确认空集那一半修好**（`guard_crush`/`air_unblockable` 已非空），伪条目那一半仍开放
（71/255 仍为叙述句，见 P1-12）；**但 BC 行标签并非全清**——SC 那 1–6% 见 P0-6。

**卫生**：597 tracked 全扫，**0 密钥 / 0 邮箱 / 0 私网 IP**；tracked 最大件 493KB，无 dist/、无 `.pyc` 入库。

---

## 七、与上一次归档审计的差异

- 上一次（`audit_2026-10-17_le_bh_corpus.md`，基线 `f636a02`）为**窄范围**审计
  （LE/BH 语料波），结论「放行 + P0×1（情境库热度半修复）+ P1×1（fangyu 伪条目）」。
- 本轮从零#5：上一轮 P0（情境库热度）**已独立验证为真修**（但消费端四重失效，见 P1-3/P1-14）；
  上一轮 P1（fangyu 伪条目）**只真修了空集那一半**（71/255 仍是叙述句，见 P1-12）。
  另发现**六个新 P0**：一个在数据面（P0-6 SC 标签取错帧，属**既存缺陷**，非本日引入），
  五个在治理/执行层，且其中三项由**当日两个事件**直接引入——PR-5 历史重写
  （19:13，P0-1/P0-2）与 R159 并行 sweep（P0-4）。与从零#4 的
  「重置块搬家 / 单源表两半不同步」同族，本轮形态是**「批量化工具改动绕过门禁自检」**
  ——今天连「新功能」都是在一个红门禁上继续叠加的。

---

## 八、建议（待用户指令；审计不修）

**A. 立即（阻塞级，建议同批完成再谈其他）**
1. 清 `%USERPROFILE%`：85 文件 / 95 处统一 `os.path.expandvars`（或改相对路径/参数），
   优先 `bc_build.py:484`、`oracle_batch2.py:23`、两个测试；复跑门禁至 0 FAIL。
2. 修 R14 看门狗：`_wd.sample` 移出 `_exhausted` 分支（每心跳一次），口径改
   「训练族进程树累计 CPU」，并加「看门狗存活」自检（心跳里记 last_sample_ts）。
3. 并行 sweep 加基线守卫（复用 `gate_selftest.py:847-857`），并把基线数字写进报告头。

**B. 本周（P1 批）**
4. **SC 标签（P0-6）**：`resolve_sc_label` 改用 **SC 步执行帧**的手牌（或从宏脚本里
   定位 `sc:` 步所在帧），并加断言「三角色库中 TM·6a终结 / TM·必杀SC连 / TM·空连终结
   的 Y 计数 > 0」；修后须重建 BC 库（在跑库受影响）。
5. 低信息降采样改**随机**（`rng.choice`）而非取前 N；修后重建。
6. 评估工具切 `_fleet` 档 + 报告写模型版本/mtime；league 种子统一温度（或在报告中
   显式标注 temp 差异，不参与跨角色比较）。
7. 对照臂纳入监督（或独立看门 + 停机账 + 告警），并把 `train_start` 清理改为
   **按 store/worktree 路径判别**而非脚本名。
8. episode 契约增 `n_rows` 并校验全部 per-decision 数组 N 相等；帧日志按 actor
   子目录隔离；`fleet_heartbeat.alert` 接入 dashboard/审计（当前无人读）。
9. LE-1b：`inject_indices` 传 `matchup`、热度键改用池槽空间、裁定极性
   （按设计意图「弱点对位保留全部、强势按 (1-h)」，即 `keep = rng < h`）、
   `inject_count` 加 clamp。
10. LE-2 伪条目收尾：`warning_moves` 加「句子判据」（长度、标点、以『要注意/被/有/如果/
    所以/对方』开头）+ advice 尾部剥离下一条招名；当前 71/255 伪条目会直接污染
    类别计数先验。

**C. 文档与卫生（随下波）**
11. 入口层一次性对齐：`CORE_DIMS=358` / 宏数 88·95·91 / 测试 89 / 门禁 637（并附原始输出末行）。
    统一 R14 措辞（线程数 2、可恢复暂停语义、采样窗 6）。
12. audit_all 奖励面板改读 actor 日志或改为读 episode 的奖励块；bh 旁车加保留策略；
    `tools/_*.py` 8 个零引用 scratch 归档；`.gitignore` 补 `tools/*.json`；
    明确 `data/bc`（330 代旧库）与 `D:\temp\th123_models` trio（在跑库）的身份，
    并让 `bc_label_migrate` 先查 S 宽（当前会误标 680 宽旧库）。

**D. 制度（本轮新教训，建议入宪）**
13. **自报门禁数字必须附「原始输出末行 + mtime」**：本轮「门禁639/0」与实测
    「637/5/2 阻断」并存，说明提交消息里的门禁数字不可作为依据（与 R12 测量纪律同源）。
14. **批量路径/字符串改写属「代际类变更」**：重写后必须重跑门禁 + BC 重建冒烟
    （本轮 PR-5 缺此步即直接破坏门禁与 BC 复现链）。
15. **「已修」必须以「消费端可达」验收**：本轮三例（情境库热度、fangyu 伪条目、
    LE-1b 注入）都是"生产者改对了、消费者仍到不了/方向反"，与从零#4 的
    「EVASION 死代码」同类——建议把"消费端断言"列为修复完成的必要条件。

---

## 九、分片附录

### 附录 A：训练主链分片（已完成；P1×1 + P2×6）

**A-P1 `ppo.py:991` 主干价值梯度混用「已更新」的 W1v → numpy 与 torch 两个 learner 每步方向不同（审查者已亲核代码）**
`ppo.py:954` 先 `self._vf_adam.step(...)` 原地更新值头；`:991`
`dflat = dh @ self.W1.T - (dH1v @ self.W1v.T)[:, :TRUNK_FLAT]` 又用**更新后**的
`W1v` 把价值梯度反传卷积主干。`:944-947` 的注释与修复只覆盖了流向 `dOh` 的
`dvin`（确已用 step 前权重），**主干路径没修**。
分片实证（同权重/同数据/同 rng、单 minibatch）：`VF_LR=0` 时两实现全部参数
`cos=1.00000`（数学等价）；`VF_LR` 正常时值头仍 `cos=1.0`，但 conv1/2/3
`cos=0.396/0.637/0.564`（范数相同、方向不同），两步整步 `W1 cos=0.785`、
`value_loss` numpy 20.36 vs GPU 15.67。
**影响面**：fleet 不受影响（`learner_hub` 走 `ppo_gpu`）；受影响的是单机
`train_tm`/剥削者等 `ppo.py` 消费方，以及「双实现梯度等价」契约本身
（`test_gpu_equiv` 只测前向，抓不到；且该测试当前因 P0-1 直接跑不起来）。

**A-P2（六项，均为静态+动态验证）**
| # | 发现 | 位置 | 影响 |
|---|---|---|---|
| 1 | **局边界势函数跳变 ±40**：`_prev_pot` 局末置为上一局末态势且不随局复位；新局首帧 shaped = `0.999·Φ(开局) − Φ(上局末)` → 胜后 −40.0 / 负后 +45.0（实测 Φ 胜末 +41.3/负末 −43.7/开局 +1.3；KO 通道才 ±10）。当前唯一「未生效」原因=首决策点 `rews` 为空、首段 `seg_rew` 被整段丢弃——**该丢弃同时静默吃掉开局→首决策的真实擦弹/规避奖励**；只修一边就会让每局首动作吃 ±40 假奖励 | `train_tm.py:2103,1606-1608,1967-1972` | 高（一修就爆） |
| 2 | **`reset_match` 漏复位 JZ-1 冷却追踪器** → 跨局泄漏：`action=410` 后 `s[345]=s[346]=0.492`，`reset_match()` 后全 idle 再 build 仍 `0.483`（每局开局最多 120 帧是上局残留） | `feat_builder.py:172-212` vs `:935-937` | **fleet 受影响**（actor 复用同一 builder） |
| 3 | **`macro_executor` V 极性反**：执行器 `up→V=-1/down→V=+1`，而 `train_tm.KEY_TO_BIT` 相反（实测 `keys_to_input(('up',))={'V':1}` vs `advance_queue(('up',))={'V':-1}`）。当前两消费方都用 `keys_to_input` 重建输入，故动作未反；但执行器返回 dict 被存成 `_sc_next_input` 且 `_sc_reset` 不在决策点调用 → 「sc:」步首帧可能打出上一按键步的键 | `macro_executor.py:289-300` | 潜在 1 帧错输入 |
| 4 | **死仪表**：`_guard_frames_ep` 只赋值 0，全文件无读取/自增（声称的「R33 防御递减计数」不存在）；`:1556` 在自增前打印 `_frame_ev_count` → 恒显示上一值 | `train_tm.py:1394,1556` | 观测失真 |
| 5 | **事件边沿基线滞留**：命中帧提前 return 时不更新 `last_untech`/`last_opp_air`（仅事件 5/8 更新）→ AIRTECH/OPP_JUMP 沿可能漏检或下帧重复（有 2×窗冷却兜底） | `frame_events.py:194-337` | 观测失真 |
| 6 | **CE-4 前向头「假接线」**：`PPONet` 建了 `Wf1/bf1/Wf2/bf2`（94,500 参数）并在 forward 算 `fwd_pred`，注释称「MSE 辅助损失 λ=0.05」，但 `update()` 的 loss 无任何 fwd 项；实测 `Wf1.grad is None`（`W1/Wq1` 有梯度）→ 随机初始化权重被写进每个模型档，而 `ppo.py` 无 `Wf` 键（两侧模型档不对称） | `ppo_gpu.py:136-146,708-711` | 模型档臃肿+契约不对称 |

**A 已验证正确**：`CORE_DIMS=358`/`EP_SCHEMA=2`/宏数 88·95·91/`n_side=798·833·813`；
numpy↔torch 前向 `max|ΔP|=4.5e-8`、`max|ΔV|=3.3e-7`；GAE 差 1.4e-6；`dz` 恰为
−torch `dL/dz`（cos=−1.0）→ surrogate+熵梯度公式等价；`rews↔acts` 对齐；`OPP_NEXT=opp_acts[1:]+[-1]`
确为下一拍标签（无未来泄漏）；探针/VG 混合边际与采样分布逐项相符；feat_builder 段偏移
130/152/227/253/308/316 与 one-hot 池位自洽；`build()` 每次新建零向量、JZ-1 15 维写满。

### 附录 B：数据与 BC 分片（已完成；P0×1 + P1×3 + P2×一批）

**四项「声称已修」的独立判决**（分片 C 全部动态复核）：

| 声称 | 判决 | 依据 |
|---|---|---|
| (a) 情境库热度恒 1.0 已修 | **半修** | 公式真实（存量 heat 0.919–1.0，非恒 1）；但**消费端全断**：`matchup=None` 不进热度分支、`keep=1-h` 方向反、id 空间错位、`h=1.0` 时空集（见 P1-3/P1-14） |
| (b) fangyu 伪条目已修 | **半修** | 「原236的使用率开始上升」类已过滤；但 39%（94/255）叙述句 + 6 条「以下SC/以下スキル」标题仍在，数字建议句照进，列表节只按「、」拆（`A,AA,AAA…` 计 1 条）（见 P1-12，审查者独立复算 71/255） |
| (c) LE-1a 标签 2n 偏移 | **真修** | 3000 行重算 tags/mid 与产物 **100% 一致**，`mid==期望槽` 3000/3000 |
| (d) bc_build 池位单源 | **真修** | `bc_build.py:218-219` 用 `TMTrainer._CHAR_POOL_IDX`；数据含 20 个 mid 值、`core[238..246]/[308..315]` 非零；旧 `_POOL_O{0,1,9}` 会 KeyError。残留：`_POOL_O` 兜底与 308 偏移 3 处硬编码 |

**C 的 P2（择要）**：`bc_io.py:191` 写 C 列但 `load_bank` 不返回 C、meta 无 C 哈希
→ 无消费者且漂移不可检；`migrate_bc_b.py:55` 重建只写 X/Y/S/C/meta，有 I 时**静默丢 I**
→ seq 降级 iid；`bc_label_migrate.py:28-46` 不看 S 宽就改 layout（现 `data/bc` 宽 680 会被误标）；
**文档与实盘矛盾**：`data/bc` 是 70/76/77 宏、680/710/715 宽、79,150/70,803/59,123 行的
**330 代旧库**，而在跑库是 `D:\temp\th123_models` trio（798/833/813 宽）；
situation meta 的 `n_matchup` 恒等于 rows（死仪表）；`bc_build.py:183-204` 立防标签
用 hit 后 0–9 帧对手动作（未来窗）；语料 `039_e94db3d6.npz` meta `err=idle-noframe(0)`
仍在盘/manifest（`bc_build` 跳过）；`distill.py` 默认 data 路径不存在（死诊断）；
`query` 每次读 40MB npz ≈94ms（开注入后每 update 一次）。

**C 已验证正确**：在跑 trio `S` 宽 798/833/813=5N+358、`rows==meta`、X/S/Y/I 哈希全对
（reimu X 6.18GB 复核）；`[0:n]/[n:2n]` 严格 one-hot（sum=1）；block0=上一命中宏
（与 `Y[i-1]` 不符的 42% 由被删低信息行 100% 解释）；`mirror_input == H 取反` 4000/4000；
SC cost 200+ 与 `card_tables` 三角色全对；npz 宽守卫有效（680≠798 响亮拒载）；
`inject_count` floor 正确（12/64、25/128）；I 组连续有序；oracle 1724 shard/manifest
帧数全对、40 抽样 0 问题；测试 28/28 + 57/57 全绿（**但不检测上述缺陷**）。

**C 未完成**：未做全库重建（P0-6 错标率由 4 个 shard 侧外推，1–6% 需 rebuild 探针定口径）；
未核 C 内容与另两角色 X 哈希；未跑 `bc_align` 非 ilog shard 端到端；`teach.value_rank`
未接活模型。

---

## 十、本轮审计局限（如实记录）

- 分片 C（BC 数据链）**已完成**（P0-6 由分片动态实证 + 审查者亲核 `bc_build.py:303-309`
  源码机制确认）；其未完成项已在附录 B 列明（未做全库重建，错标率 1–6% 为外推值）。
- 分片 A（训练主链）已完成，P1 已由审查者亲核 `ppo.py:954/991` 源码确认。
- 「历史重写前门禁为绿」系由 `pre-rewrite-backup` 分支内容 + 串行 sweep 日志
  「基线(未变异): exit=0」共同推定，非本轮实测（重写后不可复现）。
- 未运行 `tools/behavior_report.py` / `status_dashboard.py` 的 `main()`
  （前者 `prune_sidecars` 有删除副作用，会动 live store 旁车）。
- 训练为只读观察：未停 fleet、未改任何 store/data 文件；临时探针全部落在
  `D:\temp\audit_scratch_1017\`（仓外），仓库工作区除**本报告文件**外零改动。
