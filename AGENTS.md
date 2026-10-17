# AGENTS.md — th123 对战 AI 项目路由(LLM 协作开发入口)

> 本文件是唯一入口路由。改代码前先读这里; 规范细节以 `METHODOLOGY.md`(宪法)为准。
> **交接文档: `HANDOVER.md`(新智能体接手时第一读)。**
> **审计工作入口: `docs/audit_protocol.md`(审计智能体路由, 与本文件同级); bug 立档: `docs/bugs/`。**
> **三智能体并行工作流: `PARALLEL_WORKFLOW.md`(单写者规则 + docs/_pending_entries.md 队列, 2026-10-16 试行) — 写文件前先查写入权。**
>
> 两条最高教义: **非想天则是 62 帧游戏**(帧↔秒一律 /62, 禁 60); **用户报告的观察是地面真相**。
> 修订 2026-10-08: fleet 架构 + DCB(流派适应三件) + B 风格估计器 + 剥削者。
> 修订 2026-10-14晚: BC v3.4换装(trio mmap)+CORE_DIMS 343(S-2变招/心理/风格段)+模型/种子迁移;
> JZ-2攻略八表+JZ-3三门(错防掩蔽/投技门/抓跳)+从零#4 P0×3当日修复(note_decision重置块回迁/
> 重启耗尽ALERT/BC宽度点火硬门禁); 门禁从零#4时点 618/2/1(行为测试70/70对账入册)。
> 修订 2026-10-12: R14 CPU红线≤75%(torch限2/低优先级/看门狗自动降容/--tps透传); 门禁570/0/0
> 修订 2026-10-11: 交接对账+接手推进 — 门禁实测 568/0/0; 训练 21:22 起带 20 角色 league 对手生态(D3'/R65); train_start 自杀 bug 已修(METHODOLOGY 2.65-2.66)。

## 0. 当前通道(fleet 架构, 2026-10-08)

| 项 | 值 |
|---|---|
| 启动 | `python tools/train_start.py --mode fleet --actors 3 --exploiter reimu` 或双击 `启动训练.bat` |
| 监督 | `fleet_supervisor.py --actors N`(learner 5s 错峰 + actor 20s 错峰 + 死亡重启) |
| learner | `learner_hub.py --char X`(ppo_gpu 批更新, episode npz 消费, 快照发布) |
| actor | `actor_worker.py --char X --actor N --port P`(train_tm 组合复用, episode npz 写入) |
| 剥削者 | `exploiter.py --char X --fleet`(镜像锁死打主策略, exploit_ 前缀入池) |
| league20 | 对手周期27位=主角色块×3交错+league17静态种子+COM(D3'/R65); `tools/seed_league_pool.py` 点火自愈 |
| 环境 | `tm_env.py`(TCP 锁步, 同进程续局, 崩溃重启车道环回) |
| 学习 | `ppo.py`(numpy, 单实例) / `ppo_gpu.py`(torch, fleet learner) |
| 特征 | `feat_builder.py`(**CORE_DIMS=358** = S-2段343 + JZ-1段15, 含14维对手风格段) |
| 执行器 | `macro_executor.py`(统一宏推进, train_tm+side_driver 共用) |
| 事件 | `frame_events.py`(帧级事件检测+反应掩码, B2 策略条件化) |
| 卡组 | `deck_sampler.py`(课程采样 + C 对抗性四层加权) |
| 产物 | `D:\temp\th123_models\model_ppo_{char}.npz`(+_v) / `fleet\episodes\` / `fleet\snap_{char}\` |
| 日志 | `D:\temp\learner_{char}.log` / `D:\temp\actor_{char}_{id}.log` |
| 审计 | `python tools/audit_all.py`(或双击 `审计.bat`) |

Python: `D:\temp\pyenv\python.exe`(3.12). 训练游戏: `D:\touhou\hisoutensoku2026-06-15\th123_train`.

## 0b. fleet 协议(scenario_b 设计)

- **红线①**: actor 采样时记录 logP(a)(含探针/bias/价值引导) → learner 消费为 stored_logp(真 ratio)
- **红线②**: actor 局边界轮询 version → 原子加载快照 → 每局冻结
- **红线③**: actor 按 (actor_id, version) 重播种 rng → 防同流
- **单写者**: 模型/计数/蒸馏/池快照 → learner 唯一写; episode npz → actor 唯一写
- episode schema: v2(含 contract 块); v1 文件被拒收入隔离区

## 0c. 神谕数据通道(专家数据)

- 游戏: `D:\temp\rl_game`(隔离副本)
- 工具: `oracle_batch2.py`(v2 全量包, BC 构建正统来源)
- 数据: `data\oracle\shards\`(191 局双边)
- R1 边界: 回放数据提取合法; live 对战只写己方输入

## 1. 门禁

```bat
D:\temp\pyenv\python.exe -X utf8 tools\contract_check.py
```

- 必须 0 FAIL 才能提交
- 变异自检: `SELFTEST_TAGS=<标签> python tools/gate_selftest.py`
- 当前断言: **658 PASS / 0 WARN / 0 FAIL**(2026-10-18 裸跑实测, 原始末行入提交), 变异 197 条, 行为测试 92 档

## 2. 奖励体系(当前)

| 通道 | 来源 | 值 |
|---|---|---|
| 伤害/承伤 | 势函数差分 | POT_W 映射 |
| KO 回合 | 血量差分档 | win∈[3,13] lose∈[-10,-5] |
| 快胜奖金 | 剩余时间比例 | 最高+6/回合 |
| 擦弹 | 两级费率+局时衰减 | 全额段+衰减低段 |
| 规避 | TTI+位移 | +0.20/事件 |
| 空挥 | 非命中非被防 | -0.06×倍率 |
| 空中被动 | >30 帧悬空 | -0.003/帧 |
| **微收追扣** | **R62 败回合** | **-70%×微收入** |
| 距离势差 | R61z engage | 前进+后退- |

## 3. 宏库体系

| 角色 | 宏数 | 来源 |
|---|---|---|
| reimu | **88** | 手写+原子+压起身+C4+分支波 |
| marisa | **95** | 同上(蓄力真值+系统卡+DD+HJC) |
| suika | **91** | 同上(623B萃鬼投技族) |
| 17 新角色 | 各 60-80 | R44 生成+C6 TM 连段 |

宏语法: 键步/confirm/cconfirm/branch/link/ender/sc: — 由 `macro_executor.py` 统一推进.

## 4. DCB 流派适应体系(2026-10-07/08)

| 件 | 层 | 机制 |
|---|---|---|
| D 仪表 | L1+L2+L3 | `tools/deck_matchup.py`(4 模式) |
| C 对抗池 | L1+L2+L3 | `deck_sampler.sample_deck_weighted`(败率加权) |
| B 估计器 | 14 维 | feat_builder 对手已出卡差分 → core[316..329] |

闭环: D 测出弱流派 → C 自动加权采样 → B 给模型感知输入 → 策略泛化.

## 5. 红线(不可违反)

1. 公平对战: 只写己方输入, 不读对手输入指令
2. 内存写入仅限训练过程, 有界, 字节预检
3. 门禁不过不许提交
4. CORE_DIMS 变更必须全链同步
5. 共享档单写者纪律
6. 原子落盘(tmp+replace)
7. 62fps 教义(帧↔秒 /62)
8. **CPU负载红线(R14)**: 训练全家总CPU ≤75% — learner torch限2线程(TH123_TORCH_THREADS可调)/全树BELOW_NORMAL/supervisor看门狗**口径=训练族进程树CPU(非整机, R170)**/6采样滚动窗均值>75%降容(可恢复暂停)/<65%连续两满窗恢复/--tps 360降载

## 6. 工具速查

| 工具 | 作用 |
|---|---|
| `tools/train_start.py` | 启动/停止训练 |
| `tools/audit_all.py` | 全量审计 |
| `tools/deck_matchup.py` | 流派 matchup 实测 |
| `tools/com_ladder_report.py` | COM 难度读数 |
| `tools/eval_matrix.py` | 380 matchup 矩阵 |
| `tools/branch_demo.py` | 分支演示(E1) |
| `tools/bc_label_migrate.py` | BC 库 layout 标签迁移 |
| `tools/migrate_style_b.py` | 模型 316→330 迁移 |
| `tools/migrate_bc_b.py` | BC 库 316→330 迁移 |
| `tools/exploiter.py` | 剥削者入口 |
