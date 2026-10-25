# TH123 对战 AI(th123_rl)

用强化学习(PPO + 宏动作)在**真实游戏进程内**训练东方非想天则(th123)的对战 AI,
目标超人水平。游戏经 mod(SokuAITrainer)的 TCP 锁步协议与 Python 通信;
本地 fleet 架构(learner 批更新 + actor 采集 + 剥削者 + 20 角色 league 对手生态)持续训练。

> **访客须知**: 这是研究型项目, 复现需要 **东方非想天则 (Touhou 12.3) 游戏本体**
> + 自制 game mod + Windows 环境, 且训练数据(回放语料/模型权重)不在本仓库分发
> (见 [docs/DATA_POLICY.md](docs/DATA_POLICY.md))。下方"快速开始"面向维护者本机
> 环境; 通用流程见 [docs/fleet_ignition_runbook.md](docs/fleet_ignition_runbook.md)。
> 本项目与黄昏フロンティア/社区 AI 工具(th123_ai)无隶属关系, 帧数据表的来源
> 标注见各文档内引用。

## 两条最高教义

1. 非想天则是 **62 帧游戏**(帧↔秒一律 /62, 禁 60)
2. **用户报告的观察是地面真相**(模型指标再好也盖不过用户看到的实际行为)

## 文档(按阅读顺序)

| 文件 | 何时读 |
|---|---|
| [HANDOVER.md](HANDOVER.md) | 接手第一读 — 环境/架构/操作/制度/踩坑速览 |
| [AGENTS.md](AGENTS.md) | 改代码前 — 通道/门禁/红线/工具速查(入口路由) |
| [METHODOLOGY.md](METHODOLOGY.md) | 唯一权威宪法 — 一切制度与版本日志(冲突处以它为准, 尾部为最新条目) |
| [docs/master_plan_2026-10-05.md](docs/master_plan_2026-10-05.md) | 任务全景与状态(超人清单) |
| [docs/fleet_ignition_runbook.md](docs/fleet_ignition_runbook.md) | fleet 点火/切换/回退操作手册 |

## 快速开始

```bat
启动训练.bat    :: fleet 3 actor + reimu 剥削者(等价: python tools\train_start.py --mode fleet --actors 3 --exploiter reimu)
停止训练.bat    :: python tools\train_start.py --stop
审计.bat        :: 全量审计(tools\audit_all.py)
流派实测.bat    :: DCB 仪表四模式(tools\deck_matchup.py)

:: 门禁(改代码后必过, 必须 0 FAIL)
D:\temp\pyenv\python.exe -X utf8 tools\contract_check.py
```

> **以上「快速开始」面向维护者本机** — 下面的路径(`D:\temp\pyenv` / `D:\touhou\...`)
> 是开发机约定; 访客克隆后请看下面的「已知状态」按需改环境变量
> (`TH123_GAME_DIR` / `TH123_STORE` / `TH123_SOKU_ARCH` 等, 见 `kit_config.py`)。

环境: Python 3.12(`D:\temp\pyenv\python.exe` 便携) · 游戏 `D:\touhou\hisoutensoku2026-06-15\th123_train`
· 模型存储 `D:\temp\th123_models\` · Windows 10 x64。依赖见 `requirements.txt`。

## 已知状态(2026-10-18 实测, 供访客判断"能复现到什么程度")

| 项 | 状态 |
|---|---|
| **门禁** | `738 PASS / 0 WARN / 0 FAIL`（`tools/contract_check.py`，裸跑退出码 0；变异 265 条；TH123_GEN2=1 口径 `gate_window7_final2.txt`） |
| 行为测试 | `tests/` 118 档，全部入 C15 白名单对账（`tests/test_*.py` 集合==白名单，缺口必红） |
| 核心常量 | `CORE_DIMS=358`（S-2段343+JZ-1段15）；宏数 reimu 88 / marisa 95 / suika 91；`n_side` = 798/833/813 |
| **`soku_arch`** | 已 **vendor 入库**（`soku_arch/`，30 档 283KB，见其 `VENDORED.md`）；**授权已裁**：自有代码 → 并入根 MIT（R191 用户裁定），出处/血统见该文件 |
| 可复现项 | 代码/门禁/行为测试/宏库**齐全**；但 **`data/` 全域不入库**（`git ls-files data/`=0，见 `.gitignore`）——门禁/C15 中直读 `data/guide_tables/*.json` 的断言（如 fangyu 警戒表 `contract_check.py:2274-2294`、`tests/test_fangyu_counters_le2.py:15-27`）在**干净 clone 下会 FAIL**，须放入本地数据副本（开发机或 kit）方可全绿 |
| **不可复现项** | ① **训练数据**（BC 库 / oracle 分片 / 回放语料）与 **模型权重** 不在本仓库（见 `docs/DATA_POLICY.md`）；② **游戏本体** `th123` 与自制 mod（`SokuAITrainer` 等 DLL）需自备，`th123_train` 目录是开发机副本；③ 依赖外部**高手 rep 库**（6 万+ rep）的采集脚本无法在缺数据时复跑；④ **本地数据表**（`data/guide_tables/` 含 cleista 帧数据表等）不入库 —— 门禁/测试直读这些档，缺档时按预期报红（数据边界，非代码回归） |
| 训练规模 | 本机 3 actor + 3 learner + 20 角色对手生态（league）；CPU 红线 ≤75% |
| 用途边界 | **仅本地离线研究** —— 不用于联机对战、不随游戏分发、不提供任何绕过公平性的通道 |

> 复现验证方式: `git clone` 到**不同路径** → 改 `TH123_*` 环境变量 → 放入本地 `data/`（见 `docs/DATA_POLICY.md`）→ 跑 `tools/contract_check.py`；
> 未放数据时门禁预期红在直读 `data/` 的断言（数据边界，非代码问题）。
> 上表"不可复现项"即预期失败面, 失败项请按 `docs/_plans/public_release_hardening_plan_2026-10-17.md` 核对。

## 目录结构

```
th123_rl/
├── train_tm.py            主训练器(奖励/宏/门控/对手轮换, actor 组合复用)
├── ppo.py / ppo_gpu.py    PPO 数学层(numpy 单实例 / torch fleet learner, 语义对齐)
├── feat_builder.py        特征构建(CORE_DIMS=358, S-2变招/心理/风格段+JZ-1段)
├── macro_executor.py      统一宏执行器(train_tm+side_driver 共用)
├── fleet_supervisor.py    fleet 监督器(league 分配/死亡重启/停机卫生)
├── learner_hub.py         fleet 中央 learner(episode 消费/快照发布)
├── actor_worker.py        fleet 采集进程(episode 序列化/单写者纪律)
├── episode_core.py        episode npz 契约(单一事实源, R63 代际契约)
├── tm_env.py / soku_client2.py / portmap.py   游戏环境与 TCP 协议
├── side_driver.py         对手侧推理驱动(评估+自对弈)
├── exploiter.py / league.py / opp_model.py    剥削者/league 加权/对手建模
├── deck_sampler.py / card_tables.py           卡组采样(C 对抗性池)
├── frame_events.py        帧级事件检测+反应掩码
├── bc_*.py / distill.py / teach.py            BC 库/蒸馏诊断/教学层
├── macros/                宏库包(__init__=灵梦库+共享规范化器, 20 角色各一档)
├── tests/                 行为测试(**118 档**, 门禁 C15 白名单全量对账)
├── tools/                 工具(train_start/audit_all/contract_check/评估仪表…)
├── docs/                  文档(主规划/审查报告/设计文档/手册)
├── data/                  本地数据(BC 库/神谕分片, gitignore)
└── _archive/              退役归档(README 记录血统, git mv 保历史)
```

## 工作流

1. 读 `METHODOLOGY.md` 尾部最新版本条目了解上下文
2. 改代码 → 跑 `tools/contract_check.py`(必须全绿)→ 提交 git
3. 训练相关变更 → 重启训练(`train_start.py`)
4. 定期 `audit_all.py` 产出诊断报告

## 许可

- **代码**: [MIT License](LICENSE)
- **文档**(`*.md`): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.zh)
  (见 [docs/LICENSE-docs.md](docs/LICENSE-docs.md))
- **数据边界**: 训练数据与模型权重不在本仓库分发,
  见 [docs/DATA_POLICY.md](docs/DATA_POLICY.md)
