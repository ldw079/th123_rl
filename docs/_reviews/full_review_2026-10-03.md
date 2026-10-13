# th123_rl 从严全面审查报告（第九轮）

> 日期: 2026-10-03 · 审查方式: 只读（未改动任何代码/数据/配置）
> 范围: 全仓库（RL 核心 / 环境与协议层 / 数据管线 / 门禁治理 / C 代码 / 工程卫生）
> 方法: 人工精读核心模块 + 4 路并行子代理深审 + 训练日志/模型工件实证核查
> 结论可信度标注: 【实证】= 有日志/数据/互相关实验证据; 【静态】= 代码结构推演; 【子审】= 子代理核查结论（已抽查关键推理）

---

## 0. 总体结论

项目的方法论文档体系与工程自觉（宪法、门禁+变异自检、事故换制度、原子写、响亮失败）在个人项目中属罕见的高水准；**架构选型（TM 锁步通道 + 宏动作空间 + 势函数塑形）是正确且被实证支撑的**。

但本次审查发现：

1. **训练正处于一次未被察觉的生产事故中**——三个 2026-10-02 引入的现行 bug 使三角色从 10-02 晚起陷入"每局崩溃→丢数据→重建→进程每 4~52 分钟死亡重启"的退化循环（监督日志实证）。
2. **专家数据管线存在系统性帧对齐漂移**——全部 BC 标签取自专家未来 1~4 秒（互相关实证）。
3. **两个 R35 新特性是静默死代码**（价值引导选宏、经验回放）。
4. 治理体系存在"声称的保障"与"实际执行的保障"的实质缺口（C9 血统不闭环、C15 与文档不符、缺路径即空转）。

---

## 1. P0 — 正在发生的事故

### P0-1 train_tm.py 受击中止后空队列取值 → IndexError 崩溃循环【实证】

位置: `train_tm.py:935-1004`。宏队列推进结构:

```python
if macro_queue and not frozen:
    if d_take > 80:
        macro_queue = []          # 受击中止清队
    if (R34防御中断条件):          # 独立 if，不是 elif 链头
        macro_queue = []
    elif macro_queue:             # 灵力门控
        ...
    else:
        keys, fl = macro_queue[0]  # ← 队列已被受击中止清空时: IndexError
```

- 触发条件: 单帧承伤 > 80（任何像样的一击）且 R34 条件不成立。典型场景为**远距离被弹幕命中**（dx≥300 使 R34 近距条件失败）；近战命中通常被 R34 条件掩盖。
- 后果链: IndexError → 穿透 `_run_episode` → 通用 except → **整局数据丢弃**（异常发生在 `_submit_update` 之前）→ 环境 close+重建（1s×5 重试）→ `_consec_fail++` → 连续 5 次后 exit(1) → 监督器重启。
- 实证: `D:\temp\train_reimu.log` 尾部即此崩溃往复循环（scene 2→6 → IndexError → 重建 → 重复）; 三角色日志计数 reimu 22 / marisa 35 / suika 23; `train_supervision.log` 显示 10-02 23:59 前整夜每 4~52 分钟死亡一次。
- 对照: `side_driver.py:381` 的同源逻辑有 `if self.macro_queue:` 守卫——两份拷贝漂移的直接恶果。
- 修复方向: 受击中止清队后 `continue` 跳过本帧推进，或把三段改为 side_driver 式 `if self.macro_queue:` 守卫结构。

### P0-2 side_driver.py 缺 `GUARD_ALL_IDS` 导入 → NameError【实证】

位置: `side_driver.py:367` 使用 `GUARD_ALL_IDS`，但模块头部（:18-22）只导入 `CHAR_LIBS, keys_to_input, _parse_sc_targets`。因 `and` 短路，仅当"对手动作∈[300,600) 且我方动作<100"（= P1 攻击、P2 移动/待机，高频）时求值到该名字 → NameError → 同样炸掉整局。
实证: reimu 日志出现 `NameError: name 'GUARD_ALL_IDS' is not defined`。
门禁漏网原因: C15 的 8 个测试无一覆盖 R34 分支。
修复: 头部补 `from opp_model import GUARD_ALL_IDS`。

### P0-3 "价值引导宏选择"（R35 差距#3-L1）为静默死特性【静态】

位置: `train_tm.py:1083-1084`:

```python
_V, = self._ppo_act._v_forward(_Xn, side.reshape(1, -1))[1:]
```

`_v_forward` 返回 3 元组（`ppo.py:541`），`[1:]` 为 2 元组，`_V, = ` 解包必然 ValueError，被 `:1105 except Exception: pass` 吞掉。**整段 critic 前瞻选宏从未执行过一次**。另 `_base_v`（:1084）算出后从未参与比较（`_best_v` 初值 -1e9）——半成品。因失败后回退普通采样，无任何外在症状。
修复: `_V = ...[1]`；若保留特性，`_base_v` 需真正参与阈值比较。

### P0-4 PPO 经验回放（R35 差距#4-B）双重失效【静态】

位置: `ppo.py:649-654`（及 636-647）:

1. `X[_hi][_cap:]` 应为 `[:_cap]`——实际丢弃**前** cap 个高优势样本保留其余；且优势归一化后 |adv|>1 的样本数通常 < `cap=min(500, 0.3N)`，此时切出**空数组** → 回放池几乎恒空，"每批混入 20%"从未生效。
2. 即便池非空: 回放行拼进了 X/S/A/R/adv/ret（:640-645）却**未扩展 mask M** → `_pi_forward_batch(X, S, mask=M)` 形状不符抛异常 → 被异步线程 except 吞掉 → 整次更新静默丢失。

两个 bug 互相掩盖，形成"永不真正工作也永不报错"的特性。
修复: 切片改 `[:_cap]` 且为回放行拼接对应 mask 行（或移除该特性并记录）。

### P0-5 神谕数据 (输入,状态) 对齐漂移 +65~+250 帧/局 —— 全部 BC 标签系统性取自专家未来【实证·子审】

- `oracle_batch.py:166-168` / `oracle_batch2.py:155-158` 按原始下标配对 `frames[i]↔inputs[i]`；`bc_build.py` 截断双双等长后逐行配对。
- 互相关实证（用与 `bc_match.py:45-47` 完全相同的解码路径，方向输入 H ↔ 我方位置差分，扫描滞后 -400..+400，6 个已交付 shard）: 最优滞后全部在 **+70~+240 帧**（滞后 0 处相关 <0.3；真实滞后处 0.7~0.9）；shard 006 前半段 +3、后半段 +165——**局内漂移**，非常数头偏移。
- 根因推断: 状态流开局跳过 ~65 帧、每次回合切换再差 ~90 帧（190/191 局 frames≠n_inputs，差值 -377..+9180，均被静默截断）。
- 后果: `data/bc/*.npz`（reimu 9475 / marisa 3540 / suika 8969 行）每行特征来自其标签输入位置之前 1~4 秒的状态——**同时是系统性错标与未来信息泄漏**。BC 锚与 `bc_extra` 混入行都在教"看过去的状态、模仿未来的动作"。
- 修复方向: 入库前逐 shard 做对齐校验（如 H↔Δx 互相关，最优滞后≠0 拒收），或改用 mod 回显的输入帧号做硬对齐；重建三角色 BC 库。

### P0-6 BC 库侧维布局失配（零填充而非重建）+ repad 再跑腐蚀 suika【实证·子审】

- 现行 `train_tm.py:292` 用 `n_side=5N+308`；`bc_build.py:181` 仍构建 `4N+308`（文件头"与train_tm逐位一致"声明为假）。磁盘 bc 文件实测宽 5N+308（623/653/658），但 **gap_x/gap_y/untech 三块全零**（reach 表可解析 17/63 个灵梦宏正值）→ 被"零填充到新宽度"而非重建；与实时决策行形成训练/推理分布失配，恰污染 R24/R25/R30 引入的射程/时序块。
- `repad_bc_r17.py:26-43` 宽度守卫对 suika（658）恰好整除通过断言后**在错误段插入 48 零列**且不刷新已存在的 .bak——重跑一次即静默腐蚀 suika BC 库（还会丢 meta 键）。
- 修复: 重写 bc_build 到 5N+308 并重建；repad 守卫改为显式布局版本号。

---

## 2. P1 — 高风险缺陷

### 2.1 门禁体系（tools/contract_check.py 等）【子审】

| 问题 | 详情 |
|---|---|
| C9 血统不闭环 | `contract_check.py` 从不读 `built_path`；"部署 DLL=所声明源码构建产物"仅靠人工跑 `update_provenance.py` 时的一次性拒绝；JSON 无签名——换 DLL + 手改 `deployed_md5` 可全绿。遮蔽行为只查源码关键字（`WEATHER_MOUNTAIN_VAPOR`/`WEATHER_AURORA`），行为证据仅 09-22 一次性 probe（其 dump MD5 与现部署 DLL 一致，已核）。 |
| 缺路径即空转 | C5（模型）/C9（DLL/源根）/C13（BC 库）在 `D:\` 缺失时降 WARN≈什么都不验证；同时 C16 缺 `D:\touhou\...` 直接 FAIL、C12 硬编码本仓库绝对路径 `%USERPROFILE%\...data\bc`（:739-743，含 `STORE if False else` 死表达式）——门禁是单 PC 仪器，兼具静默通过与虚假失败两种模式。 |
| 无机制接线 | "退出码非0阻断合批"仅约定。全仓库无 CI/hook/训练入口调用 contract_check；亦非 git 仓库。`TH123_STORE` 还允许把工件检查指向干净副本。 |
| C15 与文档不符 | AGENTS.md 称"子进程真跑 test_*.py"，实为 8 文件白名单（:929-942）。8 个确为真测试（白名单承重且正确，错的是文档）；43 个根级 test_* 中 35 个被排除，~20 个若真被 glob 会因 import 已归档模块而崩。 |
| 子串断言占比 | ~130/172 条为文本/AST 模式匹配（如 `"os.replace" in src`、`"== 117" in src`、`_ALLOW60` 白名单任何含"80"的行放过裸 60）。C13/C14/C16 与 105/117B 常量**无配对变异**，违反自家"断言必须配变异"红线（AGENTS §2）。 |
| 变异自检归因缺口 | gate_selftest 只验证"门禁变红"不归因到具体检查项；沙箱泄漏自认（`test_side_driver_semantics.py` 硬编码读真实 `D:\temp` 模型，绕过 `TH123_STORE`）。 |

### 2.2 数据管线静默失败链【子审】

- `oracle_batch*.py`: 出错/空/失配 shard 照常写盘、记 done、永不复采（v2 manifest 含 0 帧条目；'fault@N'/'idle-noframe' 条目在列）; v1 的比分核验字段 `match` **全部为 null**——宣称的"67局比分100%一致"从未真正跑过（文件名解析产出 None 也未拒绝）。
- `bc_build.py:130-133` 只按长度≥100 过滤，不看 err/match/frames≠n_inputs。
- `oracle_observe.py:111-112` 空收帧打印后 **exit 0**——自动化无法察觉失败。
- `oracle_observe.py:29` / `oracle_batch.py:116` 用**反斜杠键 + UTF-8 BOM** 写 ModLoaderSettings.json——直接违反 AGENTS.md:22-27 加载器格式纪律（`oracle_batch2.py:109-111` 已是正确写法）。
- `train_bc.py:50-53`: 全局乱序后 85/15 切分，相邻近重复帧跨 train/test（验证精度虚高）；RNG 无种子不可复现。
- `distill.py:41-43`: 报告的"准确率"是训练集准确率，无留出。

### 2.3 critic 静默重随机已实际发生过【实证】

reimu 日志出现 `[加载] 价值文件加载失败...重新随机化critic!`（旧版 ppo.py 行为；现行代码 R37 已改为响亮失败，grep 确认现行无该文案）。这是 ARCHITECTURE.md 记载的"d2 断裂期"事故类重演。另: 当前磁盘模型 meta 显示 `adaptive_lr_scale=0.1`（下限）——R18 修了 KL 读数方法，但残留 0.1 使有效策略 LR = 3e-5，需多次低 KL 更新才能爬回；解读战绩曲线时须计入。

---

## 3. P2 — 算法与设计层面

1. **off-policy 回放混入 PPO 语义不干净**: 回放行 logp_old 取当前策略（ratio≡1）+ 沿用旧批归一化 adv——等价无重要性修正的 AWR 式更新，且 adv 跨批统计口径混用。修复 P0-4 后会暴露。建议删除或明示为行为正则化并重算 ratio。
2. **logit 封顶反传不一致**（`ppo.py:504-505`）: 前向按行缩放 Z（s=zmax/8），反向 dz 未乘 1/s——封顶激活时梯度幅度系统性偏差；且用 `abs(Z).max` 触发，大负 logit 也压扁整行。
3. **KL 度量是 |Δlogp| 均值而非 KL**（`ppo.py:877`），阈值语义与名不符; `kl_stopped` 置位后无 break（EPOCHS=1 下无实害）。
4. **非终局尾部自举 `tail=vseg[-1]`**（`ppo.py:623`）: 用自身状态值自举自身，超时段 GAE 有偏（末段优势趋 0）。注释已承认，记录在案。
5. **"选中卡 one-hot"近乎失效**（`feat_builder.py:459-462`）: `sel < 8` 按原始卡 ID 截断——系统卡 8~20、技能卡 100+、符卡 200+（含自家 SC 宏目标卡 200/210）全部落入"空"桶，与空手不可区分。应改类型桶（系统/技能/SC）。
6. **决策层旁路堆叠**: R34 防御中断、灵力门控、12% 配额探针、连段 bias、（死的）价值引导、`_expert_rec` 手工 BC 锚——大量"策略之外"的行为修改; 探针/bias 影响行为策略而更新侧不记账，ratio 有系统性小偏差。旁路越多 PPO 语义越稀，且历史上已出现"训练内 COM 4-1 vs 真评估 0-3"式的行为层/评估层失配。
7. **死代码**: `train_tm.py:313-317` `expert_ids` 属性无任何消费者。
8. **复制粘贴式"同源"**: `_eff_dirs/_norm_presteps` 1020 字符在 macros.py / macros_marisa.py / macros_suika.py 逐字节相同; train_tm 与 side_driver 的执行器互为拷贝——P0-1/P0-2 即两份拷贝漂移产物。
9. **宏库迁移遗留**: 磁盘模型 N=59（W2 (128,59)、W_side (603,59)、W1v (3179,128) 自洽），现行宏库 63——零初始化迁移可接管，但说明产物落后宏库一代，配合 §2.3 的 critic 事故，近期训练连续性存疑。

---

## 4. P3 — 工程卫生【子审·普查】

### 4.1 可达性普查（自 18 个活跃入口 BFS）

- **LIVE 26 个**（18 声明 + 8 传递: config, reach_maps, skill_levels, action_tables, level_macros, portmap, standard_tree, side_driver）。
- **DEAD 104/142（73%）**，其中 ~55 个因 import 已归档模块（`bridge_inject/hud_sensor/inject/soku_client`）必然 ImportError（test_v6-v9、test_mem_drive1-4、test_kick2/3、scan_* 全家等）。
- 陷阱级死入口: `speedhack.py`（import 不存在的 hud_sensor，自身即坏）、`selftest.py/.bat`（同名干扰真正的变异自检 gate_selftest）、`demo.bat`（跑不存在的 loop.py）、`restart_train_tmp.bat`（杀硬编码 PID 的一次性残留）。
- LIVE 代码有**未声明的外部依赖**: `bc_build/bc_match/oracle_*/status` 依赖 `D:\temp\soku_arch` 包（sys.path 硬编码）。

### 4.2 根目录污染

| 类别 | 内容 |
|---|---|
| 孤儿大文件 | `p2_eps_pool.npz` **508MB，全仓库零引用** |
| 退役二进制 | input_bridge.dll + input_bridge3-9.dll（8 份）、diag.dll、fgspoof.dll、speedhack.dll、injector.exe + 5 个 .c 源 + speedhack.txt |
| 杂物 | `-x`（4 字节文本"8696"，疑误重定向产物，时间戳与注入工具同期） |
| 过时工件 | distill_data_*.npz / model_ppo.npz / macro_counts.npy（旧无后缀名，live 代码只读 D 盘 STORE） |
| 结构矛盾 | AGENTS §3 明言 input_bridge* 属退役通道应归档，驱动脚本已进 `_archive/root_dead_r17`，**载荷却留在根目录**——"腰斩归档" |

### 4.3 C 代码问题（均已退役但在根目录）【子审】

- `fgspoof.c:18`: 无守卫 `*(HWND*)0x89FF90`——错宿主进程首次调用即崩（全组最高危）。
- `diag.c:122/:83-84`: DllMain 内无守卫 `*(void***)0x8A0E30` + 未检查 GetModuleFileNameA 的长度运算可溢出 path[MAX_PATH] 5 字节; 无上限逐秒追加日志（同类于本项目已发生的 1.5GB 磁盘事故）。
- `input_bridge.c:19/:25-36`: 48B 文件映射 vs 52B 结构潜在越界; `:80-91` 计数器 int 溢出 UB（tps480 下 ~20h）; `:223-224` 非对齐代码补丁的线程挂起守卫静默退化; `:8` 头注释公平性声明与实现（双写 P1/P2）不符。
- 三个 IAT 钩子 DLL 共享缺陷（speedhack.c:85-91 / fgspoof.c:48-54 / diag.c:59-65）: `OriginalFirstThunk==0` 回退把已解析地址当名字 RVA——绑定导入模块一碰即崩; >512 模块静默全跳过; DllMain 重活（loader lock 死锁风险）。
- `speedhack.c:22-51`: reanchor 非原子（换倍速瞬间时间跳变）。
- `injector.c:29-42`: 失败路径 VirtualAllocEx 泄漏; "INJECTED" 报假成功（不查远程线程退出码）。

### 4.4 工程基线缺失

无 git（任何层级）、无根 README（在 _archive）、无 requirements/pyproject、无 tests/ 目录（43 个 test_* 散落根级）、无 lint/类型配置、无 .gitignore（首次 git add 会吞 508MB 孤儿档与 __pycache__）。live 代码/bat 硬编码 `D:\temp\pyenv`、`D:\temp\th123_models`、`D:\touhou\...`——可移植性为零。bat: `一键开训.bat` 健康（编码/回退链正确，但引用不存在的 runtime\ 目录）; `查看水平.bat` 硬编码绝对路径无回退。

### 4.5 文档漂移清单

| 位置 | 漂移 |
|---|---|
| ARCHITECTURE.md §3 | "4 epochs / γ=0.995 / KL>0.03早停" vs 代码 EPOCHS=1 / γ=0.999 / 自适应LR |
| ARCHITECTURE.md §2.1 | "宏入队时按朝向冻结" vs 代码逐帧镜像 |
| AGENTS.md §0 | "全 modpack 含 ChainCFix+FixMeiling236" vs 实况恰 3 mod（C16 强制）+ 同节"最小mod集"自相矛盾 |
| AGENTS.md §1/§6 | C15 描述（test_*.py 全跑）vs 白名单 8 文件 |
| AGENTS.md §5/§6 | "260维核心" vs 308 |
| AGENTS.md §6 | 匹配阈值"0.85" vs 实际生效 0.88（0.85 是 bc_match 未用的类默认） |
| config.py 头 | "不读游戏进程内存(纯视觉)"——TM 通道已读（且有 R2 预检写） |
| contract_check.py 头 | 仍只列 C1-C6; 段序 C12→C14→C13 与变异注释标号错位 |
| gate_selftest.py 头 | "11个被检文件"（实 21） |
| oracle_batch2.py | 完全未登记（AGENTS §0b/§4 只列 v1） |

---

## 5. 框架合理性总评

**做得对的（应保持）**:
- 通道选型: mod TCP 锁步替代抓屏/注入（遮挡免疫、弹幕精确坐标、解锁高 tps 无头三开）——实证支撑的正确决策。
- 宏动作空间坍缩 + 双确认门 + 情境/射程/背向掩码 + 零初始化迁移 + 势函数塑形（差分不可刷分）+ 对手子网络辅助损失——对"单人 + numpy + 真实游戏进程"约束的恰当组合。
- ppo.py 手工反传经逐行核验基本正确（im2col/col2im/unpool、三路梯度共享 trunk 汇合、熵梯度公式重新推导无误、上升/下降符号约定一致）。
- tm_env/soku_client2 的事故吸收（deadline 制收包、幂等 close、端口车道化、boot 互斥、僵尸口探测）明显来自大量真实教训，质量高于绝大多数同类项目。
- 持久化纪律（原子写、NaN 拒存、meta 数组、断裂修复清单）与监督器（exit 0/130/1 区分）设计到位。

**结构性弱点（事故根源）**:
1. **"同源"靠复制粘贴而非共享抽象**——macros×3、train_tm/side_driver、oracle_batch×2 的漂移已产出本次 3 个现行 bug 中的 2 个。**最大事故源**。
2. **测试金字塔倒置**: 变异自检很精致，但没有任何"合成 episode 端到端跑通不抛异常"的冒烟测试——一个 200 行的假包回放测试可同时抓住 P0-1/P0-2/P0-3。门禁重心在"历史回归可证伪"，不在"新路径可达性"。
3. **静默降级旁路聚集于新特性**: except:pass（价值引导）、静默空回放、静默入库坏 shard、WARN 降级门禁——与"响亮失败"宪法精神相悖，且都在 R34/R35 新代码上。
4. **文档治理 > 代码现实**: 70KB 宪法 + 172 断言的规模，掩盖了行为级验证占比低的事实; 宪法自身也已漂移（见 §4.5）。

---

## 6. 行动清单（按优先级）

**P0 立即（恢复训练健康）**
1. 修 `train_tm.py:935` 队列推进结构（清队后跳过本帧或加 `if macro_queue:` 守卫，对齐 side_driver）。
2. `side_driver.py` 头部补 `from opp_model import GUARD_ALL_IDS`。
3. 加端到端冒烟测试: 合成假包驱动 `_run_episode` / `frame_input` 数百帧，覆盖 R34 各分支/受击中止/门步/sc 步，断言无异常; 纳入 C15。
4. 修 `ppo.py:651-654` 回放切片 `[:_cap]` + 回放行 mask 拼接（或移除特性）; 修 `train_tm.py:1083` 解包（`[1]`）。
5. 重启训练前清点: 检查三角色模型 meta 的 `adaptive_lr_scale` 与最近一次 critic 重随机时间点，评估需要回滚的快照。

**P1 短期（数据正确性）**
6. oracle 入库对齐校验（逐 shard H↔Δx 互相关，最优滞后≠0 拒收）+ 失败 shard 不写盘/不记 done + 空收帧 exit 1。
7. bc_build 重写到 5N+308 并重建三角色 BC 库; repad 脚本加布局版本守卫。
8. oracle_observe/oracle_batch 的 mod 配置写入改原生格式（照抄 oracle_batch2）。
9. AGENTS.md 修正 C15/§0 modpack 行; contract_check 去硬编码路径（环境变量化）; C13/C14/C16 与 105/117B 常量补配对变异。

**P2 中期（结构）**
10. 抽 `macros_common.py` + `macro_executor.py` 消灭三份宏库与双执行器拷贝。
11. 根目录大扫除: 104 死脚本 + 11 二进制 + 5 源文件 + `-x` + 508MB 孤儿档 → `_archive/`; `speedhack.py`/`selftest.py`/`demo.bat`/`restart_train_tmp.bat` 一并处理。
12. git init + .gitignore + requirements.txt（含 soku_arch 外部依赖声明）; LIVE 路径全部环境变量化。
13. 选中卡 one-hot 改类型桶; 删除 `expert_ids` 死属性。

**P3 记录**
14. 文档对齐一轮（§4.5 清单）; 决定 off-policy 回放的最终语义（删除或明示 AWR 式并重算 ratio）; logit 封顶反传补 1/s 缩放。

---

## 附录: 审查覆盖与证据索引

| 模块 | 方式 | 关键发现 |
|---|---|---|
| ppo.py | 逐行精读+梯度推导 | P0-4; P2-2/3/4; 熵梯度/反传核验通过 |
| train_tm.py | 逐行精读 | P0-1; P0-3; P2-5/6/7; 日志实证 |
| tm_env.py / soku_client2.py | 逐行精读 | 协议/清理质量高; 105B 结构手工复算一致 |
| feat_builder / threat / opp_model / config | 精读 | P2-5; 段宽 308 复算一致; OPP 切片 [152,227) 一致 |
| side_driver / outer_loop / run_parallel | 精读 | P0-2; 监督/锁设计合格 |
| 数据管线（oracle*/bc_*/train_bc/distill/repad/seed） | 子代理深审+互相关实验 | P0-5; P0-6; §2.2 |
| tools 门禁四件套 | 子代理深审+哈希核验 | §2.1（现部署 DLL/JSON/构建产物哈希一致，门禁本机为绿） |
| C 代码 5 件 + 二进制 | 子代理深审 | §4.3 |
| 工程卫生普查 | 子代理 import 图 BFS | §4.1/4.2/4.4 |
| 训练日志/监督日志/模型工件 | 实证核查 | IndexError 22/35/23; NameError; critic 重随机; meta LR=0.1 |

*本报告由只读审查生成; 未修改任何代码、数据、配置或模型。*
