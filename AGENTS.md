# AGENTS.md — th123 对战 AI 项目路由（LLM 协作开发入口）

> 本文件是唯一入口路由。改代码前先读这里; 规范细节以 `METHODOLOGY.md`（宪法）为准。
> 两条最高教义: **非想天则是 62 帧游戏**（帧↔秒一律 /62, 禁 60）; **用户报告的观察是地面真相**。
> 修订 2026-09-24(第八轮审查后): 新增神谕数据通道§0b、隔离区§3b、训练监督说明。
> 修订 2026-10-01(R17对手建模): §0特征/学习行更新(308维+子网络), §6入列新工具。

## 0. 当前通道（唯一在训通道）

| 项 | 值 |
|---|---|
| 入口 | `run_parallel.py [episodes]`（三角色并行: 灵梦20800 / 魔理沙20810 / 萃香20820, tps480; **带子进程监督: 死亡30s后自动重启, 记录在 D:\temp\train_supervision.log**） |
| 训练器 | `train_tm.py --char X --port P --slot N`（每角色一进程; **启动期构造失败也重试5次**） |
| 环境 | `tm_env.py`（TCP锁步: 同进程续局, 输入回填, 首帧容错; **崩溃重启端口在10宽车道内环回, 不再漂移**） |
| 学习 | `ppo.py`（宏策略PPO: 共享卷积主干 + 侧路径 + BC锚 + **对手子网络75→32→16 + 动作预测辅助损失**， 参数见宪法§5; update返回含\|KL\|/优势幅度/价值损失/预aux命中率） |
| 特征 | `feat_builder.py`（**308维核心**(对手建模段75: 历史40+资源条件8) + 2N宏one-hot）+ `opp_model.py`（75维对手读层）+ `threat.py`（TTI/来袭, `GAME_FPS=62`） |
| 宏库 | `macros.py` / `macros_marisa.py` / `macros_suika.py`（新增宏走宪法§3.5十步SOP） |
| 产物 | `D:\temp\th123_models\model_ppo_{char}.npz`(+`_v`), `macro_counts_{char}.npy`, `distill_data_{char}.npz` |
| 日志 | `D:\temp\train_{char}.log`（stdout, UTF-8; [ep]行含 \|KL\|/优势/值损/视差诊断） |
| 规则环境 | **th123_train 最小mod集 = {MemoryPatch, SokuAITrainer, SokuDirectXOptimizations}**(C16门禁强制; 2026-09-28事故后裁定 — ChainCFix/FixMeiling236仅神谕通道用, 不在训练集) |

> **⚠ SokuModLoader 配置纪律(2026-09-24事故教训)**: `ModLoaderSettings.json`
> **必须用加载器原生格式** — 正斜杠键(`modules/X/X.dll`)、无BOM、其自身缩进。
> 反斜杠键/带BOM/改换行的重写都会让加载器解析失败 → 全部模块(含训练mod)
> 静默不加载 → 游戏120s连不上, 且窗口标题**不显示"Game on port N"**(标题=
> 网络初始化的副产物, 是加载健康的第一现场指标)。**改任何游戏目录配置前:
> 先字节级备份; 改后必须拉一个测试游戏验证连接+端口标题。**
> 已知良好基线: `th123_train\ModLoaderSettings.json.bak_rl`(RL时期原生格式)。

Python 解释器: `D:\temp\pyenv\python.exe`（3.12, 便携）。训练用游戏为独立目录 th123_train（最小mod集）。

## 0b. 神谕数据通道（专家数据唯一正统来源, 2026-09-24 用户批准）

- **原理**: 专家rep由游戏原生重播器自播(网战rep的输入语义只有这条通路能忠实复现),
  我们的mod以被动模式(SOKUAI_OBSERVE=1)推105B状态流 → 构造性一致的(输入,状态)对。
- **游戏副本**: `D:\temp\rl_game`（用户整合包隔离副本 + th105; 模块集:
  MemoryPatch/ReplayDnD-old/SokuAITrainerEnv/ChainCFix/FixMeiling236 — 22mod全开会阻断mod连接, giuroll/AIPlayer/PracticeEX在重播时崩溃, 均已禁用）。
- **工具**: `oracle_observe.py <rep> <port 20960-20999> <out.npz>`(单局观测),
  `oracle_batch.py <lane> <n_lanes> <port> [tps]`(v1批量摘要),
  **`oracle_batch2.py <port> [tps]`(v2全量包 — BC构建的正统来源, 105B×2+天气+对象;
  R38起: 失败shard不写盘不记done)**。
  端口均限定probe段防串流live训练。
- **已有数据**: `data\oracle\shards\`(191局双边rep, 226万帧, 67局带文件名比分100%一致)。
- **R1边界(用户裁定2026-09-24)**: 回放数据含双方历史输入属记录事实, 提取/存储合法;
  **live对战仍只写己方输入** — R1原义不变。旧 `rep_distill.py`(重放对手输入进游戏)已隔离。

## 1. 门禁（改代码后必须过, 分钟级）

> **前置条件**: 门禁C9依赖本机路径 — 游戏根`D:\touhou\hisoutensoku2026-06-15\th123_train`
> 与mod构建根`D:\temp\build`。缺失时C9相关项降为WARN(可移植), 哈希不匹配仍FAIL。
> mod源根可用`TH123_MODROOT`环境变量覆盖(变异沙箱即用此机制)。

```
D:\temp\pyenv\python.exe -X utf8 tools\contract_check.py     # A级契约断言(计数见其输出)
D:\temp\pyenv\python.exe -X utf8 tools\gate_selftest.py      # 变异自检(改断言后必跑)
D:\temp\pyenv\python.exe -X utf8 tools\update_provenance.py  # 重编mod后更新血统档案
D:\temp\pyenv\python.exe -X utf8 tools\runtime_masking_probe.py  # 遮蔽运行时实测(一次性已验)
```

A级契约(不需要游戏): 62fps教义 / 特征布局 / 协议不变量(105B) /
PPO语义(**行为断言**: 真跑update验熵上升) / 产物schema(zip完整性) / 奖励活性(AST) /
基准树教义(三角色) / **mod血统(C9: 引用的源码必须是部署DLL的构建输入)**。
**退出码非0 = 阻断合批。**
**可信度边界**: 门禁已过变异自检(全部历史bug注入变红); 但**变异测试只保证
断言可证伪, 不保证前提为真** — 引用外部事实(mod行为/游戏机制)的断言必须
有C9血统记录或R6溯源, 无溯源的外部事实断言视为待确认(第四轮审计教训)。
B级（每批自检）与C级（基准树audit）见宪法§7。

## 2. 红线（违者即事故, 全文见宪法§0 R1-R10）

- 只写己方输入, 严禁读对手输入指令（公平对战）。
- 内存写入仅限训练过程、有界、字节预检; 不改 keybd_event 默认逻辑。
- 不猜数据/不猜状态（帧数据、场景值一律取自实测或攻略CHM）。
- 用户观察>实现推断; 遇歧义直接问用户。
- **62帧教义(R10)**: 逻辑帧↔秒换算用 `threat.GAME_FPS`(=62), 严禁出现 `/60`。
  **边界: R10不约束协议tps参数(60≈原速)与SPEED包 — 严禁"好心"把tps改成62**。
- **信息对称(R11)**: 包内字段按构造公平(mod已遮蔽晴岚手牌/极光真实效果);
  可用对手手牌数等包字段; **严禁绕过mod直读游戏内存取被遮蔽量**。
- **单写者纪律**: 同一`.py`同时只允许一个agent改; 不并行开两个实验批;
  任何"声称已修"必须附门禁输出+复现命令(反方验证员可执行复核)。
- **断言可证伪**: 新增门禁断言时必须同步在 `gate_selftest.py` 加配对变异。

## 3. 退役通道（_archive/, 勿改勿引）

抓屏时代(v1/v2): `train_rl.py`, `loop.py`, `capture.py`, `perception.py` 主导的旧管线,
`input_bridge*.dll` v1-9 注入器, `lazy_boot.py` 旧编排, `make_package.py` 懒人版打包。
历史文档 `README.md`/`OPERATIONS.md`/`懒人版说明.md` 已归档（其结论已并入宪法）。
`ARCHITECTURE.md` 与 `docs/multi_instance_input.md` 为**部分过时快照**(顶部有横幅),
数值冲突时以宪法+门禁为准。
诊断脚本（`test_*`, `diag_*`, `scan_*`, `watch_*` 等）多为一次性, 参考可, 复用需核。

## 3b. 隔离区（tools/quarantine/, 勿运行勿引用）

第八轮审查§7处置(2026-09-24): 同步问题调查期的死工具与一次性脚本。
- **死工具**: consistency_audit / determinism_check / input_loss_analysis /
  pairing_test / rep_observe_session（对不存在的API编写、空样本即PASS、零调用者）;
  **rep_distill**（R1冲突: 把回放对手输入写进游戏; Y≡-1; 编造常量列）。
- **正统替代 = 神谕通道§0b**。隔离区脚本不得运行、不得并入live产物。

## 4. 常用操作

| 任务 | 命令 |
|---|---|
| 开训（三角色, 带监督） | `run_parallel.py 500` |
| 单角色补训 | `train_tm.py --char reimu --port 20800 --slot 0 --tps 480` |
| 契约门禁 | `tools\contract_check.py` |
| 变异自检 | `tools\gate_selftest.py`(改断言后必跑) |
| 看进度 | `type D:\temp\train_reimu.log`（尾部; \|KL\|/优势/值损/视差在[ep]行） |
| 看监督日志 | `type D:\temp\train_supervision.log` |
| 基准树教义查看/审计 | `standard_tree.py standard marisa` / `standard_tree.py audit suika`（三角色各自树） |
| 外环: 单matchup评估 | `outer_loop.py match reimu marisa --games 2`（VS_PLAYER双控, 端口20900区） |
| 外环: 快照入池/全矩阵战报 | `outer_loop.py snapshot` / `outer_loop.py report --games 2` |
| 外环: COM定期检验 | `outer_loop.py comeval`（cycle内含; 独立手动跑用此命令） |
| 外环: 周期调度 | `outer_loop.py cycle --games 2 --interval 3600`（与训练并行; 锁已带存活检测） |
| 自对弈训练(外环训练半环) | `train_tm.py --char reimu --opp marisa --opp suika --suffix _exp --port 20920 --slot 3 --tps 480`（对手=池快照轮换; --suffix隔离产物防双训练器写同档） |
| 神谕: 专家rep单局观测 | `oracle_observe.py <rep> 20970 out.npz` |
| 神谕: 批量提取 | `oracle_batch.py 0 1 20963 480`（端口限probe段20960-20999） |

## 5. 结构速查（现行职责）

```
train_tm.py    训练层: 观测构建/宏执行/奖励/采样/异步更新/SC状态机/空挥结算
tm_env.py      环境层: 开局/同进程续局/输入回填 — 训练器不碰协议细节
soku_client2.py 协议层: TCP锁步客户端(CS_FMT 105B, 对象项17B, 输入包117B)
ppo.py         学习层: 纯PPO实现 — 不含游戏知识, 不import游戏模块
feat_builder.py 特征层: 308维核心(威胁网格/卡牌/对手建模75/势函数) + R38选中卡类型桶
threat.py      威胁预测: TTI闭式解 — GAME_FPS=62 单一帧率常量
macros*.py     宏库: 每角色一份(名称/脚本/分类集合/SC_COST)
```

修改任何文件前: 过一遍宪法§8变更管理; 改完: 跑门禁; 训练中改代码需重启进程生效。

## 6. R17 补登记（2026-09-28 从零全面审查后；2026-10-01 对手建模四件套入列）

| 职责 | 入口 |
|---|---|
| BC数据构建（**训练数据源**） | `bc_build.py` / `bc_match.py`（匹配器, 阈值0.88 / CONF_MIN 0.92; R38: bc_align对齐+5N+308原生布局） |
| 运维: 质量监视 / 水平查看 | `monitor.py 300`（秒） / `status.py`（= 查看水平.bat） |
| 门禁: 行为测试套件 | `tools/contract_check.py` 的 **C15**（子进程真跑10个白名单行为测试, 退出码即门禁 — R38起含冒烟+回放语义） |
| 门禁: 训练安装mod集不变量 | **C16**（恰为 {MemoryPatch, SokuAITrainer, **SokuDirectXOptimizations**}；DXOpt = 多实例 D3D 共存必需，实测 3/3 vs 2/3） |
| 单实例锁 | `run_parallel`（`D:\temp\run_parallel.lock`）+ `outer_loop.lock`，均带 PID 存活检测 |
| 死代码隔离位 | `_archive/`（`root_dead_r17` = 危险注入类；`tools/quarantine` = 旧隔离） |
| R17①对手特征(75维) | `opp_model.py`（历史40+资源8）+ `feat_builder.py` 段10（CORE_DIMS=308） |
| R17③④子网络+预测辅助 | `ppo.py`（OPP_CORE_OFF=152/OPP_DIM=75；FD深测 `test_r17_ppo.py`， 门禁快版 `test_opp_subnet.py`） |
| R17重铺垫/播种(一次性) | `repad_bc_r17.py`（BC库+48零列, 备份.r16.bak）/ `seed_r17.py`（三角色全新初始化+池播种；旧产物在 `_archive_r17_opp_model/`） |

根目录只放活跃模块；其余 ~110 个不可达脚本的批量清理为 P2 遗留（逐个核对引用后移入 `_archive/`）。
