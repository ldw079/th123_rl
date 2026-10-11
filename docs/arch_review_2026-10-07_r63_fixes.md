# th123_rl 架构审查与修复（R63 · 2026-10-07）

> 方式: 4 个零先验子代理分片审计（动作层 / fleet+learner / 特征布局 / 实时运行证据）
> + 审查者逐行复核核心学习路径 + 工作区实测。
> 全程只读审查；修复阶段改代码，未改动任何训练数据。
> **审查基线**: `tools/contract_check.py` = 535 PASS / 0 WARN / 0 FAIL（修复前）。

## 0. 结论摘要

| 级别 | 发现 | 处置 |
|---|---|---|
| P0-1 | 镜像连**上下轴**一起翻 → 朝向左时约一半决策执行的不是策略选的那一招 | ✅ 已修+测试 |
| P0-2 | episode 尺寸**无代际契约** → 旧码 actor × 新码 learner = 批量丢数据 + 静默零学习 | ✅ 已修+测试 |
| P1-1 | 奖励仪表把"不入回报的量"计入总和、又漏掉真扣分项 | ✅ 已修 |
| P1-2 | Adam 优化器状态不落盘 → 每次 learner 重载有一步偏置校正冲量 | ◐ 仅记录（机制确证，未改） |
| P1-3 | numpy 采样 ↔ torch 更新**无跨实现对等性测试** | ◐ 记录（未改） |
| P1-5 | fleet 治理六缺口（失监督/锁不隔离/池越权删/GPU静默重随机/孤儿游戏/actor排空） | ✅ 已修（除 restart 预算衰减） |
| P2 | 对手技能槽位越界崩溃、奖励诊断、超级字面量等 | 部分已修，见 §5 |

**当前状态**: 修复后门禁 **551 PASS / 0 WARN / 0 FAIL**。
**⚠ 运行中的 7 个训练进程仍跑旧代码**（Python 模块只在启动时载入）——P0-1/P0-2 的
行为修复需**重启训练**才生效。

---

## 1. P0-1 镜像轴（行为修复）

### 事故
`train_tm.keys_to_input(keys, mirror=True)` 原写 `if axis in ("H","V") and mirror: val=-val`
（`train_tm.py:324`），把**屏幕上下**（V）也一起翻转。调用点 `train_tm.py:1295`
（`self._last_dir < 0`）与 `side_driver.py:423`（对手侧）。

### 判据（三条独立证据，非推测）
1. **姊妹实现**：`bc_match.py:29-40` 只翻 H，其 docstring 明确记载"原连 V(up/down)
   一起翻 … 换边段的空中宏标签静默丢失/错配"——**同型 bug 已修在 bc_match、漏在 train_tm**。
2. **极性约定**：`soku_client2.py:312-326` `up=V:+1` / `down=V:-1`，V 是屏幕上下，
   镜像是左右翻转，上下语义不变。
3. **第三实现**：`tools/branch_demo.py:200-202` 同样只翻 H。
   （注：`bc_match.KEY_TO_BIT` 的 V 极性与 train_tm **故意相反**且各自自洽，
   `bc_match.py:18` 有明示——比较时必须换算极性，见测试 §4b。）

### 后果链
`_last_dir<0` 时 `up→V=-1` 被发成"下"：`高跳=(down,(),up)` 退化为普通跳、
`j8A→j2A`、`斜上冲/斜后跳` 上下互换。而轨迹/distill/`bc_targets`/掩码记录的
**仍是策略原本选的那一招** → 约一半决策的信用分配被污染；对手侧同时被喂镜像键。

### 修法
`axis == "H"`（单行）。配对测试 `test_mirror_axis_r63.py`：H 翻/V 不变、
高跳回归、`mir_keys`(键名法)≡`keys_to_input`(极性法)、跨实现镜像规则一致（换极后）、
极性锚点（防未来"好心"改 `KEY_TO_BIT`）。

---

## 2. P0-2 episode 尺寸代际契约（架构修复）

### 事故（实测于 `learner_reimu.log`）
代码在活进程脚下变更（CORE_DIMS 316→330、宏数 63→70）时：
- 写者(actor, 旧码)按**自己的**尺寸产 episode（`n_side = 5*len(CHAR_LIBS[char]['macros']) + CORE_DIMS`）；
- 读者(learner, 新码)按**模型档**推断尺寸（`n_out = W2.shape[1]`）；
- `np.concatenate` 抛 `ValueError: … size 623 and … 666` / `RuntimeError: mat1 and mat2 shapes cannot be multiplied (2329x666 and 680x70)`；
- 被 `except Exception` 兜成"批隔离 N 个继续" → 整批进 `failed/` **永久丢弃**，
  learner 无限 continue。

实测证据：`learner_reimu.log:7-19` **13×** `模型侧宽623≠派生631 — 拒绝启动`；
`:28-36/:65-66/:95-96/:104-105/:173-174` 5× 批隔离；`fleet/episodes/failed/` **26 个文件**。
两侧进程都"活着" → **看起来在训练，实际每批都丢**。

### 病根
episode 是**只有 schema 版本号、没有尺寸/布局指纹**的裸 npz；尺寸由双方各自推断，
且写者侧 `PPOTrainer.load` 还会对旧宏数模型做**静默生长迁移**（`ppo.py:250-271`），
使 actor 毫无察觉地继续产"错代"数据。

### 修法
1. `episode_core.EP_SCHEMA 1→2` + 契约块 `{char, n_out, n_side, n_macros, feat_dim, code_n_macros}`；
2. `build_contract()` / `check_contract()` / `code_macro_count()`（**代码侧**宏数真值源）；
3. `save_episode_npz` 落盘前**写者自检**（声明 vs 数组实际形状不符即拒写）；
4. `load_episode_npz` 四项校验：键/schema/契约自洽/声明vs实际，并支持 `expect_contract`；
   不符抛新异常 `EpisodeContractError`——**与"单批数据坏"区分开**，不走删文件路径；
5. `learner_hub`：
   - 启动前**入队预检**：盘上最新一代 episode 必须与代码同代，不符 → 隔离整队 + `exit(1)`；
   - 主循环遇 `EpisodeContractError` → 隔离整队 + **响亮退出**（让监督器重启）；
   - 校验"模型档宏数 == 当前代码宏数"（动作维代际）；
6. `actor_worker` 序列化时写入契约。

配对测试 `test_contract_r63.py`：正常往返 / 写者自检拒写 / 声明与形状不符拒收 /
**旧代际宏数拒收（生产事故形态复现）** / v1 档拒收且**不删除** / 未来 schema 拒收 /
契约正常时消费路径不被误伤。

---

## 3. P1 修复

### P1-1 奖励仪表误导（已修）
`[奖励成分]` 原打印 `总和 = sum(rew_mix.values())`，其中 `dmg/taken`
**从不加进 `seg_rew`**（HP 已由势函数差分覆盖，`train_tm.py:1412-1413` 自述），
而真正扣分的 `micro_tax` **不在 mix 里** → 打印的总和既含幻影项、又漏扣分项，
**与真实回报不同源**（用户按此行做奖励经济学调参 = 读错量纲）。
现：分栏打印"诊断(不入回报)"与"入账"，小计只累计真实入账通道，并打印实际回报。
`micro_tax` 键也补入 mix 初始化（原只 `get` 到不初始化）。

### P1-5 fleet 治理（已修 6 项）
| 项 | 原缺陷 | 修法 |
|---|---|---|
| GPU 静默重随机 | `ppo_gpu.load` 对缺失参数只打印（`strict=False`）→ **缺 value 档时随机 critic 立即被发布**，并驱动 30% 的价值引导宏重选；numpy 版同场景是 raise（双实现不对称） | 缺必需参数即 `ValueError` 拒绝加载；仅侧头/对手子网络为合法可选缺失 |
| 池越权删除 | learner 池清理无 `exploit_` 前缀过滤 → 周期性删掉剥削者的针对性对手快照 | 前缀分流，只清理本 learner 自己写的 |
| 快照/队列不隔离 | 锁按 suffix 隔离但 `snap_dir`/`EP_DIR` 共享 → `--suffix ""`（迁移）与 `_fleet` 可同时跑并互相删数据；`docs/fleet_ignition_runbook.md` 的自由度正是这个隐患（其明说"切换日如需带 learner 空 suffix"） | `episode_core.fleet_snap_dir/fleet_ep_dir` 单一实现；`_fleet` 走历史路径（现网零变化），其余 suffix 独立子目录 |
| 孤儿回收不彻底 | `os.kill(pid,9)` 只杀 worker，游戏子进程残留**占住监听端口**，portmap 随后把同端口发给新 actor | `taskkill /F /T` 整树回收（含超时崩溃路径） |
| actor 排空 | supervisor 不传 `--episodes`，actor 默认 1000 局跑满 `exit 0` → 被判"正常完成"**永久移出车队**；`while actors or learners` 随后永久空转 | 传 `ACTOR_EPISODES` 大预算 + exit 0 视为"生产者退出"重启 |
| 对手技能槽位越界 | `feat_builder.py:255` `_opp_revealed_skill[pid-100]` 数组宽 12，而 patchouli 技能 id 112/113/114 → **IndexError** → 局被丢弃+环境重建×5→`exit 1`（对当前 3 角色潜伏，池一扩即引爆） | 越界不写+计数+首次告警（不静默隐藏缺口） |

### P1-2 Adam 优化器状态（仅记录，未改）
`save()` 只写 `meta`（temp/beta/bcw/updates/rstd/lr_scale），**不写** `m/v/t`；
`load()` 末尾无条件重建优化器。故每次重载后 `t=1`，`m̂=m/0.1`、`v̂=v/0.001`
→ 一阶矩校正被放大 10×（比值后仍有一次性冲量），约 10 步衰减。
第一次探针给出 cold/warm=2.33×，但**该测量混淆了策略收敛**（warm 步取自已收敛处），
故不作为幅度证据；受控探针（同权重同梯度、仅优化器状态不同）在跑的 54 分钟内
与活训练抢 CPU（本机 CPU 已是绑定瓶颈，见 §4），我主动终止 —— **机制由代码确证，
幅度未测**。`_adaptive_lr_scale` 有 `[0.3,3.0]` 夹逼且持久化，故不是"永久零学习"型 P0。
**建议**：持久化 `t`（配合 `m/v` 或按 `_updates` 推进），并加"重载前后首步位移比 ≤1.2×"门禁。

### P1-3 跨实现对等性（仅记录，未改）
`stored_logp` 由 actor 的 **numpy** 前向记录（`actor_worker.py:102-108`），
ratio 由 learner 的 **torch** 前向计算（`ppo_gpu.py:421-424`）。项目自身的等价
测试是 numpy↔numpy 与 torch↔torch；**生产实际组合（跨实现）无测试**。
任何前向不等价都会变成优势估计的系统偏置且被 clip 掩盖。
**建议**：加一条"同权重同状态 numpy logp ≈ torch logp（±1e-5）"常驻断言。

---

## 4. 实时证据（审查期间在跑的那一版）

| 指标 | reimu | marisa | suika |
|---|---|---|---|
| 16:13 起更新数 / 有效速率 | 26 (8.3/h) | 23 (7.3/h) | 25 (8.0/h) |
| 每次更新消费局数 | 1.96 | 2.35 | 1.92 |
| 陈旧度 max/mean | 4 / 2.12 | 3 / 2.09 | 3 / 1.96 |
| temp / beta / bcw / lr_scale | 0.50 / 0.001 / 1e-12 / 0.30 | 同 | 同 |

- **退火全部饱和、BC 锚已死**（`bcw≈1e-12` = `BC_W_MIN=0`）→ 无活跃退火，
  有效 LR = 3e-4×0.3 = 9e-5。
- **有效步进率 40 fps**（设计 tps=480 的 8-9%）；72 分 41 秒的 Modern Standby
  吃掉 28% 窗口；~40-47% 的局死在 240s 超时并被标 `truncated`。
- **更新耗时是绑定瓶颈**：`torch 2.14.0+cpu`（`DEVICE=cpu`），5.0-5.6 决策/秒，
  单次更新中位 270-428s、最大 884s。
- 20 次 `[警报] 对手整局输出仅-0`（空转对手）**照样进训练**。
- ⚠ `Get-ChildItem` 在本机返回**过期目录元数据**（实测 log 被报小/报旧），
  只有 `Get-Item`/`[IO.FileInfo]` 的 mtime 可信 —— 后续审计注意。

---

## 5. 未修（记录在案）

| 项 | 说明 |
|---|---|
| P1-2 优化器状态持久化 | 见上（机制确证，未实施） |
| P1-3 numpy↔torch 跨实现门禁 | 见上 |
| P1-5 supervisor 重启预算不衰减 | `fleet_supervisor` 无"长命回补"（`run_parallel.py:83-85` 有）；配合大预算后触发概率极低，暂留 |
| P1-4 镜像语义两处实现 | `train_tm:1295` 与 `side_driver:423` 各一份（P0-1 正是这种结构的下场）；建议并入 `macro_executor` 单源 |
| P2 `nbias` 阈值不一致 | 采样门用"原子宏 1000"，先验公式硬编码 150 → 计数 150-1000 的原子宏拿到**负先验**，与 R50 注释语义相反 |
| P2 空掩码兜底降级 | 全掩码时回退 `base_mask`，ender/事件约束可被绕过并作为合法数据入轨迹 |
| P2 逐槽出卡判据 | `feat_builder:250-259` 用逐槽不等，库内正统是多重集差（`skill_levels.py:83-91`）；实测 7.92× 高报（87.4% 假阳），`[328]/[329]` 饱和失真 |
| P2 17 角色档代际残留 | 66 宏、`W_side` 全零、`n_side=5n+308`；门禁 R63 断言已会点出 |
| P2 测试基线漂移 | `gate_selftest.py:111` 变异目标 `CORE_DIMS = 316` 已不存在（该布局漂移变异不再守护） |

---

## 5b. 追加：F6 超人距离度量（用户 2026-10-07 要求"完善到可用"）

见专项文档 `docs/f6_superhuman_distance_2026-10-07.md`。摘要：

- **原实现是占位口径**：`metric = top['avg_wr'] - top['var']`（胜率均值减方差，
  无量纲意义、无基准）。盘上真实矩阵实证其危害：marisa 每对**只打 2 局**全胜
  → `metric = 1.0`（满分）。
- **现改为三件可证伪的量**：① `dominance` = 最薄弱对位的 Wilson 95% 下界
  （自测证明：全胜 3-0 但被某对手 0-4 → 平均仍有 0.692 而**下界 0.000**，
  "平均值会骗人"）；② `human_anchor` = **真实人类基线**，接
  `data/oracle/shards` 191 局真人网络对战重放（此前从未接线的项目唯一真人数据），
  逐角色/逐对位带 Wilson 区间；③ `comparison` = 只在**同口径**时给"距离"。
- **"距离"这个数现在仍给不出，且是如实留空**：人类数据是"真人 vs 真人"，
  模型矩阵是"模型 vs 模型快照"，**对手分布不同 → 胜率之差不是能力之差**。
- **更正（用户 2026-10-07 实测口径）**：先前把缺口判成"缺真人 vs COM 数据"是**错的**。
  用户实测：**真人打 COM 胜率 100%，COM 远逊于真人** → COM 标尺在天花板处
  **饱和不可分辨**（人类与超人在此读数相同），补上这份数据也**不能**当分母。
  缺的不是那份数据，而是**能区分顶端的标尺**（真人 vs 该模型直接对打，或
  同一批"人类也会输"的固定对手）。
  代码据此新增 `COM_VS_HUMAN` 常量 + `com_ruler_verdict()` 四档判定
  （低于人类下限 / 不可区分 / 饱和达顶 / 无数据），并**明确拒绝**由
  "打COM全胜"推出超人结论。自测还抓出我原写法里 `lo >= hw` 是个**死分支**
  （hw=1.0 时双侧 Wilson 下界不可能 ≥1），已改为 `lo >= hw - near`。
- **另一条必须记住的限定**：同架构模型互打的对位胜率度量的是**对抗池广度**，
  不能读作角色/策略的绝对强弱；镜像对位≈50% 是算法对称性必然结果，不是平衡性结论。
  输出已改称"按平均对位胜率"并加注。

---

## 6. 门禁与证据

| 步骤 | 命令 | 结果 |
|---|---|---|
| 修复前基线 | `tools\contract_check.py` | 535 PASS / 0 WARN / 0 FAIL |
| 修复后门禁 | `tools\contract_check.py` | **551 PASS / 0 WARN / 0 FAIL** |
| 新增行为测试 | `test_mirror_axis_r63.py` | ALL PASS |
| 新增行为测试 | `test_contract_r63.py` | ALL PASS（含生产事故形态复现） |
| fleet 协议 | `test_fleet_protocol.py` | 24 PASS / 0 FAIL（契约块改造后） |
| 变异自检（增量） | `SELFTEST_TAGS=R63 tools\gate_selftest.py` | **全部拦截，exit 0**（见 §6.1） |
| 其它回归 | `test_exploiter_d4.py` / `test_style_b.py` / `test_meta_roundtrip.py` | 全绿 |

### 6.1 变异自检（已跑完）
R63 新增 9 条配对变异，**全部被门禁拦截**：

```
变异[train_tm.py | R63(P0-1)回退: 镜像连V一起翻…] exit=1 ✓红
变异[episode_core.py | R63(P0-2)回退: schema退回v1…] exit=1 ✓红
变异[episode_core.py | R63(P0-2)回退: check_contract恒返回空…] exit=1 ✓红
变异[episode_core.py | R63(P0-2)回退: 读者契约不符不再抛…] exit=1 ✓红
变异[actor_worker.py | R63(P0-2)回退: actor写死/写错契约…] exit=1 ✓红
变异[learner_hub.py | R63(P0-2)回退: learner不校验模型档代际…] exit=1 ✓红
变异[episode_core.py | R63(P0-2)回退: 模型代际判据恒真…] exit=1 ✓红
==== 变异自检: 全部153+1条变异均被门禁拦截 ====
```

命令（增量模式，全量约 130 条 × 单轮门禁 ≈ 十余小时，故按 R61 增量过滤只跑本轮）：
```bat
set SELFTEST_TAGS=R63
D:\temp\pyenv\python.exe -X utf8 tools\gate_selftest.py
```

#### 6.1.1 第一轮变异自检抓出 4 条"弱断言"（**修复者自己的错误**，留档）
第一轮跑出 `4条漏网 — 对应断言是空的`。核实后确认：**不是漏修，是我的门禁断言锚错**。
按 AGENTS.md「变异测试只保证断言可证伪，不保证前提为真」，这是该制度的直接价值：

| 原断言 | 变异动作 | 为何没红 | 修法 |
|---|---|---|---|
| `"EP_SCHEMA = 1" in ec or "EP_SCHEMA = 2" in ec` | schema→1 | 自己写的 `or` 把两种都放行 | 改正向 `"EP_SCHEMA = 2" in ec` |
| `fn_has(...,"check_contract","code_macro_count(contract")` | `check_contract` 恒返回空 | **真实覆盖缺口**：读者仍靠"声明 vs 数组形状"独立判定 → "代码侧宏数校验"从未被覆盖 | 补用例 **4c**：形状**全对**但宏数旧代际（只有代际校验能抓） |
| `"build_contract(char, tr.n_macros" in aw` | actor 写 `build_contract('reimu',3,3,3)` | 只钉函数名前缀，未钉**实参是否取自自身网络** | 钉完整实参 + 测试 1d |
| `fn_has("learner_hub","run_learner","code_macro_count(char)")` | 改成 `code_macro_count(char) or n_out` | 子串仍在，被 `or` 绕过 | 判据抽成 `episode_core.check_model_generation()` 单一实现 → 门禁锚"判定+抛出"结构 + 测试 1f/1g/1h |

第二轮剩 2 条为**变异字符串写错**（源码是 `return [...]` 而非 `return (...)`；
工具自身即报 `变异定义失效`），按源码原文修正后全红。**此表的意义**：
"断言存在" ≠ "断言有效" —— 锚在标识符上、或写成 `or` 兜底的断言是空断言。

### 6.1.2 自检工具自身的两处缺陷（本轮一并修复）

跑本轮变异时工具连崩两次，根因都在**治理工具自己**身上：

| 缺陷 | 机制 | 后果 | 修法 |
|---|---|---|---|
| **失败时沙箱不自清** | `base = tempfile.mkdtemp()` 在 `try` **之前**创建 → `build_sandbox` 抛错时 `finally` 不执行 | 半建沙箱（**~1.5GB/份**）永久残留 `%TEMP%`；实测残留两份把系统盘从数GB压到 **1.27GB**，后续断言全因磁盘满而崩（表现为 `WinError 112`，看起来像门禁坏了） | `base` 移入 `try` 内并判空 |
| **无磁盘预检** | 沙箱含 mod 源码树 + 2份 store 副本 + BC 库 ≈1.5GB/份，而 `%TEMP%` 通常在系统盘 | 拷到一半抛 `OSError WinError 112`，裸 traceback，无法区分"盘满"与"门禁坏" | 大件拷贝前查盘（<0.4GB 则跳过 modroot，C9 按 AGENTS.md 降 WARN）+ 新增 `SELFTEST_TMPDIR` 可把沙箱指到大盘（本轮即 `D:\temp\selftest_sb`，D: 有 124GB） |

> 这两条本身是"治理工具失效"的同型事故——与从零#2 记录的
> `gate_selftest 基线无法绿`（沙箱 FILES 缺件）同类：**工具坏了会伪装成被测对象坏了**。
> 修复后清理回 2.4GB 空间。

---

## 7. 亲验记录（审查者独立复核，非仅采信子代理）

- 镜像极性：亲读 `train_tm.py:318-327`、`bc_match.py:18/29-40`、`soku_client2.py:312-326`，
  并核 `branch_demo.py:195-202`。
- 代际事故：亲验 `learner_reimu.log` 13 次启动拒绝 + 5 次批隔离 + `failed/` **26 个文件**、
  `fleet.lock` 不存在、无 `fleet_supervisor` 进程。
- 常量：亲测 `CORE_DIMS=330`、宏数 70/76/77、`W_side=(680,70)` 等。
- `_CORE_DIMS = 280`（`ppo.py:255`）**不是**过期常量：它是旧档守卫的下界，
  由 `old_side` 自适应 —— 我最初的怀疑经特征布局子代理实测后被否定，已更正。
- `ppo_gpu.py:429` 的 `mse_loss` 尺寸告警**良性**（尾部 minibatch=1 时
  `V` 退化为 0-d，逐对广播语义正确），实测四种形状组合确认。

## 8. 下一步（建议顺序）

1. **重启训练**（P0-1/P0-2 行为修复生效的前提）；重启前按 runbook §0 归档旧代际 episode。
2. 补 P1-3 跨实现等价门禁（低成本、可证伪）。
3. 处理 17 角色档代际残留（重建或删除）。
4. P2 清单按需挑选（建议先修 `nbias` 阈值不一致与逐槽出卡判据 —— 两者都在静默影响学习信号）。
