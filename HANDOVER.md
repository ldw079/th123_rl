# TH123 对战 AI 项目交接文档

> 日期: 2026-10-16 · 增量(**BH-4.1 matcher连段语境✓[真受击帧攻击标签43/46/33%]**/BH-3感知修复三项✅/BH-1仪表盘✅/BH-4.2采集进行中/BH-4.3先验表✅/CE离线件全谱✅/git两波提交87bb8b3+fa8b34d) · 供下一个智能体直接接手

> **2026-10-18 交接快照（R170-R195 收口；另一智能体接手时先读这段）**
>
> **门禁**: 709 PASS / 2 WARN / 0 FAIL（裸跑看退出码，勿用管道吞码）；变异 **231** 条；行为测试 107 档。
> **W1 验收门禁**: `D:\temp\gate_r197_final.txt`（12:12:51, exit=0, 原始末行 `668 PASS / 0 WARN / 0 FAIL`）。
> **R200 门禁**: `D:\temp\gate_r200.txt`（14:29:59, exit=0, 原始末行 `671 PASS / 0 WARN / 0 FAIL`；
> 本批补注册 `test_load_gate.py` C15(43 项)+白名单对账断言/变异, 变异 208, C15 93）。
> **R201 门禁**: `D:\temp\gate_r201.txt`（16:15:34, exit=0, 原始末行 `675 PASS / 0 WARN / 0 FAIL`；
> 任务 task-10 池序映射 20/20 + task-13 bcw 代码默认 0.05 + 2 C15/2 断言/2 变异已验红）。
> **R202 门禁**: `D:\temp\gate_r202.txt`（16:46:13, exit=0, 原始末行 `677 PASS / 0 WARN / 0 FAIL`；
> LE-0a 对照臂孤儿回收豁免（supervisor reap_orphans 查询加 th123_rl_control 排除）+
> 逐处扫描断言/变异/C15 已验红；事故账: 对照臂中断 639s + 游戏 21080 缺失 ~8.5min）。
> **R203 门禁**: `D:\temp\gate_r203_11a204c_20261019_061616.txt`（06:16:16, exit=0, 原始末行
> `681 PASS / 0 WARN / 0 FAIL`；H-1 wd 0.00 拒收守卫 + task-18 证据卫生: 门禁证据一次写入
> (`tools/run_gate_evidence.py`)、R200 两处补配对变异、BC CE×bcw 留档、ON prelim 修标、
> 旧矩阵"映射前"标注；变异 214 / C15 98）。
> **R204 门禁**: `D:\temp\gate_r204_b0c5d22_20261019_091506.txt`（09:15:06, exit=0, 原始末行
> `683 PASS / 0 WARN / 0 FAIL`；task-15 人测通路修正: 0x34C 角色自动识别 + 活档链(代际守卫) +
> set_opponent(P1) 修 OOD + `--probe-chars` 只读；变异 215 / C15 99）。
> **R205 门禁**: `D:\temp\gate_r205_71836be_20261019_175012.txt`（17:20, exit=0, 原始末行 `688 PASS / 2 WARN / 0 FAIL`；
> task-21 v1 空间 24 维(CORE_DIMS 358→382, TH123_FEAT_SPACE 回滚) + Phase1 空间奖励
> (TH123_REW_SPACE 保守档) + 旧前缀等价 3.6e-15 + BC 行级 zero-fill v2；变异 220 / C15 101；
> 用户裁定 bcw 保留 0.05（评估数据归档））。
> **R211 门禁**: `D:\temp\gate_r213_9bd5e42_20261020_190802.txt`（19:08, exit=0, 原始末行 `709 PASS / 2 WARN / 0 FAIL`）；
> Gen-1 修复版: hist **8 拍环形缓冲**(`window_hist` 左零填充 → 每决策 (8,3), episode hist (N,8,3))
> + 预检强制 MEM=0(协议与记忆代际无关) + 加性 W_mem/env=0 回滚 + Wf 死重删除；
> 本窗仅 `TH123_MEM_DECISIONS=8`（**批放大 B(2局+120s) 延后下一窗**）；变异 231 / C15 107）。
> **R210 门禁**: `D:\temp\gate_r211_92bcb08_20261020_141259.txt`（14:12, exit=0, 原始末行 `704 PASS / 2 WARN / 0 FAIL`）；
> task-29/30 执行层统一 mask 层: 地空门控(受身 both/后跳·白楼剑·铜钱 ground/命令技分地空) +
> 不可动门控(action-id 硬直集 50-78/150-167/倒地; 158·159-166 全 mask) + DD 收窄 150-157;
> 空 mask→仅待机/配置异常响亮报错; env=0 逐位; 变异 228 / C15 106）。
> **R209 门禁**: `D:\temp\gate_r209_42da35f_20261020_095631.txt`（10:00, exit=0, 原始末行 `701 PASS / 2 WARN / 0 FAIL`）；
> 首跑 `gate_r209_42da35f_20261020_095206.txt` 有 `test_gpu_onestep 7P/2F` 瞬态 → 单跑 9P/0F + 重跑全绿，判 flake（留痕）。
> 本批=task-20 进攻奖励(R-a/R-d/R-e, bias 入 stored_logp 红线①) + task-28 DD 仅正防(150-167)门控；
> 变异 226 / C15 105）。
> **R206 门禁**: `D:\temp\gate_r206_cc479a9_20261019_205315.txt`（20:53, exit=0, 原始末行 `695 PASS / 2 WARN / 0 FAIL`；
> A1/A2(CPU-H P-B/P-C): wd 扩 5 字段(ts family n_rej machine aux, 旧读者兼容) + machine/aux 口径 +
> L3 machine_alert/heavy.stop(不杀 fleet) + dashboard 三口径 + load_gate 接入 bc_build/eval/audit；
> task-16 behavior_deep_report 三表工具入库；变异 223 / C15 103）。
> **仓库**: HEAD=`edbc843`=`origin/main`（已推送）= R197 `a6dcbf0` + 规划文档 4 提交 ff 合并
> （生产内容与 a6dcbf0 相同）；三 worktree: 主仓 / `D:\temp\th123_rl_control`(330 代对照臂栈, detached)
> / `D:\temp\th123_rl_planning`；2026-10-18 做了**第三次全历史重写**（剔除 `_archive`），新哈希
> main `9cb67db`(→现 edbc843) / planning `ae6c39f` / 控制臂 `8720cdd`，备份 `D:\temp\repo-mirror-20261018b`。
> **当前在跑**: 主臂(supervisor+3 learner+3 actor+3 游戏) + 对照臂(learner+actor@21080, **绝对路径**启动)。
> 训练族 CPU 看 `D:\temp\th123_models\fleet_heartbeat.wd` 第二列（红线 75%）。
>
> **P0-6 已收官**（SC 复合宏标签；真因=**卡 ID 撞车**，不是审计猜的"取错帧"）:
> 三库换代 429,411 / 353,622 / 329,250 行（S 798/833/813），已换装并通过
> `tools/bc_accept.py --where store`；标签实数 `TM·必杀SC连`=24,295 / `TM·6a终结`=271 /
> `TM·空连终结`=6,389（修前恒 0）。**换库后必须重建情境库索引**（`tools/situation_library.py`，行号空间）。
>
> **未完成（接手优先）**:
> 1. **改动面增量变异 sweep（20 条, 2 workers）** —— **R197 已恢复并跑通前半**: 两条自证断言先修（见 #5），
>    `SELFTEST_TAGS='P1-2断言,P2版本断言'` 单跑已 **2红/0漏网/0未判定**（11:33, exit=1 632s/641s,
>    基线绿守卫先过）；20 条全量试跑在 **6/20 红**后被用户中止（沙箱 `test_r17_ppo` 把整机拉到
>    85-100%，族口径 20-30% 不可见，见坑 10）。**用户裁定 B1: 增量 20 条 + 全量 206 条统一推到
>    今晚 20:00 夜间窗**（分离进程、2 workers、分两晚；闸门任务=W2-1）。
>    复跑命令: `$env:SELFTEST_TAGS='...'` + `python -u tools\gate_selftest_parallel.py 2`
>    （内含基线绿守卫；**必须分离进程**，见坑 2；夜间窗外受 load_gate 闸门约束）
> 2. **全量变异 206 条** —— 需低载窗，约 2 核 × 20h。
> 3. ~~`docs/THIRD_PARTY.md` 待规划确认 + INDEX 登记~~ **已关闭**: 规划已确认并合入 main
>    （`docs/INDEX.md:35` 已登记 THIRD_PARTY；`bc_accept` 登记见 :25；soku_arch 授权=R191"自有代码→MIT"）；**P1-2 温度用户裁定"先不改"**（仅报告披露）。
> 4. 用户自有: CA-1 第四口径（管理员跑一次 `eval_vs_th123ai.py`）、人测窗口。
> 5. **审计#6（postR196, 11:08-11:16）已出**: `docs/audit/audit_2026-10-18_postR196.md` — 无新增 P0。
>    两条 P1 新发现已随 R197 修复（R181/R183 **自证断言假绿**；README 复现声明把不入库的
>    `data/guide_tables` 说成齐全 → 改为如实声明）；P1-13 数据层（活 trio 早于 R185）待下轮重建窗（用户裁定）；
>    W2 候选分级见审计 §三。
> 6. **P1-6 残余（W2，W1 不改行为）**: `tools/attribution_probe.py:69` / `tools/branch_demo.py:170` /
>    `tools/danger_reveal.py:245-254` 未注 `opp_char_id`（门禁 `contract_check.py:2239-2243` 覆盖不到）→
>    这些读数仍 OOD，不得用于强度/归因结论。
>
> **今日新坑（务必看）**:
> 1. **重建必须逐路串行**: 3 路并行 bc_build 会 OOM（3×6GB 吃满 31.5GB → 换页假死；
>    np.stack 峰值单进程翻倍）。上限 2 路，且不要与 fleet 同时。
> 2. **长任务不能跑在会话托管作业里**: Harness 重启会连带杀掉，40 分钟重建白跑零产物；
>    一律 `Start-Process -WindowStyle Hidden` + 日志重定向。
> 3. **判进度看 CPU 时间Δ 与产物，不看日志行**；进程判活用 `Get-Process -Id`，
>    **不要**用 `Win32_Process` 的 CommandLine 过滤（会瞬时为空 → 假"已结束"）。
> 4. `train_start.py --stop` 会豁免控制臂（cmdline 含 `th123_rl_control` + 绝对路径启动）→ 停主臂后单独停/启控制臂。
> 5. 池快照"resolve 后到 load 前被 learner 修剪"竞态已在 **R190** 修（回退生产模型，别回退）。
> 6. 看门狗空表=查询失败→`None` 哨兵（**不是 0%**，R182）；版本文件损坏要响亮（R183）。
> 7. 重写只改对象库，**多 worktree 磁盘副本要单独核**（规划 worktree 曾留含 PII 旧副本，已还原）。
> 8. 换装链: `bc_accept --where v3` → 停双臂 → `"YES" | python tools/bc_swap_v3.py` → 门禁 →
>    双臂点火 → `bc_accept --where store` → 重建情境库索引；回滚 `D:\temp\th123_bc_v3\pre_v3_backup`。
> 9. 可清（确认本代库稳定后）: `pre_v3_backup` 与 `D:\temp\bc_store_backup_20261018`（各 ~18GB）；
>    `D:\temp\gate_sandbox` 停 sweep 后应为空（残件=泄漏，要清）。
> 10. **族口径红线看不到树外重载**: 2 workers 沙箱 `contract_check`+`test_r17_ppo`（单进程≈5 核）
>    把**整机**拉到 85-100%，而训练族口径仅 20-30% 不触发 75% 红线（R14 族口径只管训练树）。
>    → 重活白天不跑；夜间窗由 **W2-1 CPU-H**（`tools/load_gate.py` 整机/内存/族 preflight +
>    5s 监控 + 协作停止）闸门约束；用户可感知的卡顿=事故。

**当前栈速览(2026-10-18 R195)**: CORE_DIMS=**358**(S-2段343+JZ-1段15); 并行开发必读 `PARALLEL_WORKFLOW.md`(写入权+队列); 门禁**709/2/0**;
宏数reimu88/marisa95/suika91(蓄力cleista真值+系统卡+DD+HJC);
S-4 GRU序列记忆全链就绪(阶段2a); BH方案v4执行中: **BH-3.1/3.2/3.3
感知修复✅** / **BH-1 行为健康仪表盘✅**(bh旁车+CE-0.1帧日志开关+
tools/behavior_report.py八表) / **BH-4.1 matcher连段语境✅**(按钮帧
评分+中性抑制; 真受击帧攻击标签 reimu 24.6→43.1%/marisa 27.8→
46.4%/suika 20.4→32.7%[萃香HJC机构归因待全量复核]; 度量环
tools/bh41_measure.py) / **BH-4.2 对位语料采集✅完成**(51/51对×14-15片=762,
[多rep并行采集落地: 每worker独立游戏目录rl_game_w1-3+SOKUAI_GAME_DIR
+ML事故教训: --no-mod-switch下ML是外部契约, 启动崩溃的finally还原
会静默破坏它→握手OK零帧秒退循环]) / **BH-4.3 先验表✅**("19"=衣玖
已确认, 唯余高个子名单unverified)
(matchup_combo_prior.json; "19"与高个子名单unverified待用户确认)。
**BH-4.4 合批重建执行中**(训练暂停窗口, bc_build三角色并行吸收
四子项+S-6[untech门+段位表+matcher语境+762对位分片+I列]; 重建实弹
抓出bc_build两处对位兼容bug[LIBS键/池位]已修76cc402; 完成→bc_swap_v3
→fleet重启)。
CE离线件全谱就绪(R131-139); 观察期继续。门禁**709/2/0**(2026-10-21 19:08 裸跑实测); 帧日志需
TH123_FRAME_LOG=1。关键数据: cleista/(API全量+守备段位134档)+
guard_height.json+matchup_combo_prior.json+move_displacement_*.json。
> 读完本文即可开始工作; 细节按需查阅引用文档。历史版见 git log。
> 读完本文即可开始工作; 细节按需查阅引用文档。历史版见 git log。

---

## 一、项目是什么

用强化学习(PPO + 宏动作)在真实游戏进程内训练东方非想天则(th123)的对战 AI，
目标超人水平。游戏通过 mod(SokuAITrainer) 的 TCP 锁步协议与 Python 通信。

**两条最高教义**:
1. 非想天则是 **62 帧游戏**(帧↔秒一律 /62, 禁 60)
2. **用户报告的观察是地面真相**(模型指标再好也盖不过用户看到的实际行为)

## 二、环境

| 项 | 值 |
|---|---|
| Python | `D:\temp\pyenv\python.exe`(3.12, 便携) |
| 原版游戏 | `D:\touhou\hisoutensoku2026-06-15\th123`(用户日常整合包) |
| 训练游戏 | `D:\touhou\hisoutensoku2026-06-15\th123_train`(独立目录, 最小 mod 集) |
| 模型存储 | `D:\temp\th123_models\`(可通过 kit_config.py 或 config.json 覆盖) |
| 仓库 | `%USERPROFILE%\Desktop\workplace\th123_rl\` |
| Git | PortableGit 2.56.0 at `D:\temp\PortableGit`(PATH 已持久化) |
| OS | Windows 10 x64 |
| soku_arch | `D:\temp\soku_arch\`(外部包: TrainerClient/rep解析/input_codec) |
| 高手rep库 | `D:\TR丹尼尔棉咖啡等录像精选`(61,572个) |

## 三、核心文件(改代码前必读)

| 文件 | 作用 | 何时改 |
|---|---|---|
| `METHODOLOGY.md` | **宪法+修订记录** — 一切裁定/事故/制度/验收的权威记录 | 每次提交后追加修订号 |
| `kit_config.py` | **路径单一事实源** — config.json > 环境变量 > 本机默认 | 路径变更只改这里 |
| `train_tm.py` | 训练器主文件(PPO+宏+特征+奖励) | 奖励/策略/宏变更 |
| `ppo.py`/`ppo_gpu.py` | 双实现(numpy/torch) — 必须保持梯度等价 | 模型架构变更 |
| `fleet_supervisor.py` | 车队监督(CPU红线看门狗/league分配/心跳) | 运维变更 |
| `soku_client2.py` | TCP锁步协议客户端 | 协议变更 |
| `tools/human_match_v2.py` | **人测runner**(RPM观察+内存写行动) | 人测流程变更 |
| `tools/eval_matrix.py` | 评估矩阵(四口径+vs_Human+被动仪表) | 评估变更 |
| `tools/contract_check.py` | **门禁**(690断言/0 WARN, 0 FAIL 才可提交) | 新增断言+配对变异 |
| `tools/gate_selftest.py` | 变异自检(沙箱逐条变异→门禁必红) | 新增变异 |
| `portmap.py` | 端口段划分(20800-21299) | 端口变更 |
| `series_manager.py` | BO15系列赛管理(阶段1, flag门控) | 系列赛启用时 |

## 四、训练启动/停止

**推荐: 双击 `一键启动.bat`** — 菜单式控制台(启动/停止/状态/审计/报表/备份),
自动检测舰队状态, 中文界面由 Python 输出(bat 只写纯 ASCII 规避编码问题)。

```bash
# 交互菜单(等同双击 一键启动.bat)
D:\temp\pyenv\python.exe tools/launcher.py

# 直接命令
D:\temp\pyenv\python.exe tools/train_start.py --mode fleet --actors 3 --tps 360
D:\temp\pyenv\python.exe tools/train_start.py --stop

# 状态(一屏全貌 ~5s) / 全量审计(~2min 含活性巡检)
D:\temp\pyenv\python.exe tools/status_dashboard.py --quick
D:\temp\pyenv\python.exe tools/audit_all.py

# 明细日志
tail -5 D:\temp\th123_models\fleet_supervision.log
```

**CPU红线 ≤75%**(用户明令): 看门狗自动降容/恢复actor(均值>75%暂停最新, <65%恢复).

**停机口径(2026-10-17用户裁定)**: 停机=正常操作, 不是事故 — 训练时长按
**累计有效训练帧**计(M1/观察窗/LE同此); 用户玩原版/主动暂停照常, 模型与BC全持久化.

**对照臂(LE-0a)启动纪律**: 必须用**绝对脚本路径**启动(如 `D:/temp/th123_rl_control/actor_worker.py`)
— 前置清理按命令行里的 worktree 路径豁免, 用相对路径启动的对照臂**不免疫**(R170b 实弹).
参考口径: `learner_hub.py --char reimu` + `actor_worker.py --char reimu --actor 8 --port 21080 --tps 360`,
`TH123_STORE=D:\temp\th123_models_control`, cwd=该 worktree.

## 五、门禁(每次提交前必须全绿)

```bash
D:\temp\pyenv\python.exe tools/contract_check.py
# 必须 exit 0 —— 2026-10-21 19:08 实测 709 PASS / 2 WARN / 0 FAIL(gate_r213_9bd5e42_20261020_190802.txt 原始末行)
```

**纪律**: 裸跑(不pipe)+检查退出码. `| tail` 会吞退出码(f4668e1事故).

## 六、当前状态(2026-10-14 午后)

### 已完成(本日)
- **A/B final裁定**: 保留A1-2(净分+8.3pp✓), 验收未达成(顶时判负
  100%✗) — 详见 /d/temp/ab_final_verdict.log
- **BC v3.4换装上线**(12:17重启生效): 三库mmap trio全量802,314行
  (弹幕先验6.7-12.6倍/格挡/连段族), 分支宏12个+OPP_GUARD/
  COMBO_DROP事件+sc首帧镜像修复同批; 旧库备份可回滚
- **换装首读数**(被动曲线150局滚动窗): reimu远弹1.6%→**22-26%过线**,
  suika 47-61%, marisa爬坡中; 开局攻击率显著上升
- **变招×心理博弈合并方案第一波全落地**: S-1 MyPunishTracker/
  S-2 CORE_DIMS 343(13维接线在线+离线)/S-3 return_pred/S-5专家
  punish后处理(757 sidecars)/S-7A风格嵌入(语料800矩阵top8=48.3%)/
  S-7C风格语言投影(teach接线)/S-7B前置(distill 13列)
- **第二波预备**: S-4 opp_gru.py(87维输入/隐24/可重放, flag-off)
- **审计/裁定闭环**: 变异自检4漏网(含空操作变异自纠)/bc_trio换装
  锁+代际契约/极性反转+同帧按压变体/sc镜像泄漏/灵力门B/C收窄
  (裁定四A); K5并入S-2(裁定五)/streak不作负例(裁定六B)

### 等待中
- **BC 343重建**(S-2特征入BC行): 后台运行, ~16:00完成 →
  **收官序列: 停机→bc_swap_v3.py(YES)→重启**(模型_map_row自动迁移
  330→343+灵力门+全S-2特征+distill 13列) → fleet_protocol转绿
- 观察窗: 重启后B1-B4变招/P-B1~4心理博弈读数起算(2周)

### 后续批次
- E1b系列模式启用(训练结构层 — 与S-2观察窗分开)
- S-4接线本体(ppo/ppo_gpu+onestep等价)/S-6(搭下次重建)/S-7B本体
- K5对手池扩容(池外暴露真根治)/变异自检完整重跑/TR12k收割
6. 剥削者lane复跑(CPU预算评估后)
7. 第二波: K5对手池外位(与换装分开验证)

## 七、关键制度(违者门禁红)

| 制度 | 内容 | 出处 |
|---|---|---|
| R14 | CPU≤75%红线 | 用户明令 |
| R1 | 只写己方输入 | 公平红线 |
| C9 | mod改动走血统全流程 | mod_provenance.json |
| C15 | 行为测试入C15 | 每次新特性 |
| C16 | th123_train mod集==最小集 | ModLoaderSettings |
| FILES完备性 | 行为测试imports×沙箱清单 | AST常驻断言 |
| 原子落盘 | tmp+replace, 不裸写 | 宪法§5.2 |
| 归因隔离 | 观测工具不触训练 | B3先例 |

## 八、人测流程(已全通, 下次零调试)

```bash
# 一键启动(自动禁mod+等游戏+接管P2)
# 推荐: 双击 人测对战.bat  (或 launcher 菜单选 [M])
D:\temp\pyenv\python.exe tools/human_match_v2.py --char reimu --seconds 600

# 用户操作: 启动原版游戏 → VS PLAYER → P2选RL-AI → 打完
# 自动产出: tools/human_match_sessions/sess_*.json + rep归档
```

## 九、可迁移化

```bash
# 一键打包(11MB, 含50py+6模型+20宏库+收件人脚本)
D:\temp\pyenv\python.exe tools/build_kit.py --zip
# 产出: dist/th123rl_kit_v{date}.zip
```

收件人: 解压→setup.bat→start.bat→打完→export.bat→zip发回.

## 十、常见坑(历史教训索引)

| 坑 | 症状 | 解法 | 出处 |
|---|---|---|---|
| pipe吞退出码 | 门禁假绿 | 裸跑+echo $? | f4668e1 |
| heredoc反斜杠 | 路径变TAB | 用Edit工具 | 多次 |
| SokuAIOfflinePlayer挂载 | 冻结argv回放/挡输入 | 会话期禁用 | R88 |
| 常值段锚退化 | 校准器给假锚 | 双信道合取评分 | B-1 |
| 沙箱FILES漂移 | 变异自检瘫痪 | AST常驻断言 | P1-1/P1-3 |
| dec_name死接线 | grep绿灯但根因未除 | 锚到语义动作 | 审计#4 |
| TRAINING mod锁步爬行 | 人测~1fps | 改用内存写通道 | R88 |
| kit入口落错位 | 收件机找不到tools/human_match_v2.py | start.bat引用与落点同源派生(ENTRY_REL)+zip内postcheck | 2026-10-13 |
| config写读错位 | 收件机回落开发机幽灵路径崩溃 | kit_config双位置读取+kit模式未配置即报错+setup写完即验读 | 2026-10-13 |
| 验构件不验制品 | 组件全绿但zip发出去是坏的 | --zip内置收件人模拟(解压→包内Python→双向验证), 不绿不出包 | 2026-10-13 |
| **测试自造fiction(三例)** | 测试全绿但接的是虚构布局: trunk=128(实2918→现2560)/fwd_targets索引[34][40](实为位置带one-hot)/MSE分母 | 特征/维度类断言必须用真实builder/常量产出, 不自造向量 | R133/R138b |
| **forward签名变更后门禁不闭合** | 第7处调用方漏改(series_meter)被C15损坏掩盖数日 | 公共签名变更后完整跑一次门禁绿灯才算完; C15登记看diff上下文 | R137/R135 |
| **变异锚静默漂移** | CORE_DIMS=330变异在358代成死变异(模式不命中) | tools/_anchor_check.py干跑校验(秒级)入例行; 扩维后必跑 | R138 |
| **PPOTrainer类默认N_SIDE锚reimu** | marisa/suika加载撞维度(3374≠3409) | 跨角色实例化显式传n_side=5n+CORE_DIMS | R139 |
| **bug档影响面清单不全** | untech实际10处消费方, bug档只列5处(投技无敌/空中被动豁免/link门漏) | 修bug前grep全库扫同型消费方, 不能只信登记清单 | R140 |
| **上线即自检(W4/CE-1两例)** | 仪表/画像部署后测试全绿但生产路径恒空(测试走了另一调用形态) | 部署验收必须含"首批真数据非空"读数; 接口加参时grep全部生产调用点跟改 | 审计2026-10-16 |
| **改向提交漏版本头** | 裁定改向后宪法版本头仍带旧验收数字, 与正文矛盾 | 改向/回滚提交检查单加"版本头行同步" | 审计2026-10-16 |
| 裸python指向商店占位符 | 退出码49无输出 | 一律用`D:\temp\pyenv\python.exe`(见二、环境) | 2026-10-13 |
| 会话恢复即动手 | 约定/路径记忆丢失 | 恢复后先读本HANDOVER再动工 | 制度 |
| 匹配器逐帧精确相等 | 变长弹幕决策点全丢弃(标签1-2% vs 原始B/C帧2-8%) | v3掩码位+变长截断; 比对探针先行 | A1-3③ |
| battle位码凭记忆 | 0x80当B键(实为D/飞翔), 诊断结论错位 | 位码以input_codec实证为准(bit4-7=ABCD,bit8=SC) | 2026-10-14 |
| V极性双约定 | 执行侧(train_tm)up=+1, 标注侧(bc_match/input_codec)up=-1 | 各自正确; 跨域写断言先查两边KEY_TO_BIT | 2026-10-14 |
| 变异加零=空操作 | zeros+log_softmax恒等, 自检假绿 | 变异串要语义差(F.softmax冒充log); 逐条手工验红 | 2026-10-14 |
| 大产物写C盘 | BC重建X矩阵~6G写爆(100%满) | TH123_BC_OUT默认D盘; 沙箱/矩阵类默认落D | 2026-10-14 |
| sleep空转等后台 | 占轮次无产出, 用户等得不耐烦 | 后台任务靠完成通知驱动; 前台只做快查(<60s), 长等=启动新工作项 | 2026-10-14用户令入宪 |
| 新模块漏注册FILES | macros_branch落地漏注册→沙箱基线假红数日无人察觉 | 新py与FILES注册同一提交; 沙箱不拷data/ — 表驱动模块(读data/*.json)需沙箱同步(已加guide_tables+style_pca) | 2026-10-14 |
| 新测试漏注册C15白名单 | 21个测试跨批积累只在手跑时绿, 门禁从不执行(gru漂移无闸) | 落地测试与白名单注册同一提交; 对账: 白名单vs tests目录diff(现70/70) | 2026-10-14 |
| 静态锚串跟不了活常量 | CORE_DIMS变异锚三次复发(316→330→343每次手迁) | 锚由FeatureBuilder运行时派生(_rederive_dim_anchors); 新维度锚用r'^CONST = \d+$'格式即自动纳入 | 2026-10-14 |
| 默认参数定义时绑定路径 | load_components(path=_COMP_PATH)使monkeypatch/改路径静默失效 | 路径默认参数一律path=None+函数体运行时解析 | 2026-10-14 |
| 新宏插入位≠文件尾 | reimu波区插在upgrade后/择压起身append前 — 择压起身被顶+18索引(R23违反): 模型错挂+BC标签错位+库作废三重污染 | 扩展宏一律打在**文件真尾**(所有append之后); C5已加派生位置断言(计数断言不可再硬编码) | 2026-10-14深夜 |
| 沙箱缺模块级数据件 | wave_ext读macros/charge_table.json, 沙箱只拷.py — import即FileNotFoundError(guide_tables同类第二例) | 新模块带数据依赖→build_sandbox同步拷贝同批落地; 坑已两次, 第三次不应有 | 2026-10-14深夜 |
| 拖来的方案文档可能已修订 | 用户修订版(cleista权威源裁定)在档内, 按记忆v1执行带旧外推值进重建被杀两次 | 用户拖文件=重读全文再动工, 尤其"数据源升级/裁定"节 | 2026-10-14 |
| 改代码后变异锚失效 | 加参数(learner的gru_reprs)改了锚串→变异静默失效 | 改被测代码**同步**更新gate_selftest锚; 自检漏网项先查锚命中 | 2026-10-15 |
| 门禁维度硬编码漏迁 | JZ-1(343→358)只迁模型/种子/池, contract_check的343断言漏更→基线9FAIL | **迁移窗清单必含门禁自身**; 维度断言一律CORE_DIMS派生 | 2026-10-15 |
| 原版游戏闪退(MemoryPatch被禁) | th123目录MemoryPatch enabled=false→ModLoader初始化失败→双击无反应 | 排查: mtime定性+备份diff+启用dll存在性; 修=恢复true | 2026-10-15 |
| D盘增长快(BC重建) | 单次重建+换装26GB(npz13+备份13+trio13); 自检沙箱残留(st/10天5.7G) | 换装后按需清pre_v3_backup; 自检已自动回收(11前缀+父目录扫); clean_temp.py --d | 2026-10-15 |
| C盘Temp积累(21GB) | VS安装器残留+Python tempfile残留 → C盘99%满(历史事故前兆) | tools/clean_temp.py(五层保护, launcher[9]); 舰队活跃标记=th123_* 勿删 | 2026-10-15 |
| API抓取环境三态 | Windows系统curl被WAF拦(HTTP 0)/Git curl subprocess绝对路径截断体/bash内curl畅通 | 本机API抓取一律bash内curl; python工具留作ETag刷新入口 | 2026-10-14 |
| 改代码+迁模型时舰队在跑 | 运行中进程(旧代码)读磁盘新模型(新宽度)=崩溃循环 — JZ-1迁移时未先停舰09:40-09:45烧5分钟 | **任何代码/模型变更前先停舰队**(即使自称"零侵入"); 停舰→改→迁→重建→换装→点火一气呵成 | 2026-10-15 |
| 平面日志误读进度 | bc_build日志无角色分段头, "[精确对齐]"行数跨角色累计 — 773行≠"还在建reimu"(实际reimu已完成在建marisa) | 判进度先看输出目录npz的mtime+meta(shards_used/S宽), 别只数日志行 | 2026-10-14 |
| 文件存在≠现行代码产物 | 同名_v3.npz混有330代旧档(S宽710/715)与343新档(693) | 验收必查S宽=2N+343+3N与meta; 换代重建前删旧同名档 | 2026-10-14 |
| 无ilog旧分片静默慢算 | 走R38互相关对齐路径单片30-60秒且不打日志行, 表面"卡死"实则满核工作 | 判卡死先查进程CPU时间Δ(20秒Δ≈20秒=在工作), 别急杀 | 2026-10-14 |
| **路径只修本机(expandvars)** | R169 把绝对路径包 expandvars — 展开后仍钉死本机用户名, 访客克隆到别处 import/glob 全废(bc_build 分片 glob 字面量实测=0=下次重建静默产空库) | 仓库内路径一律**由文件位置派生**(`dirname(abspath(__file__))`/`kit_config.repo_path`); expandvars 只给用户家目录输入档; 门禁常驻断言"活py零字面量" | R170 |
| **变异验证用 git checkout 还原** | 还原变异时把同文件的**未提交改动**一起冲掉(本轮实损两处改动) | 变异前后用"内存原文写回"还原; 或先提交再做变异验证 | R170 |
| **新断言抓自己的注释** | "活py零字面量"断言首跑红10文件, 全是刚写的说明性注释 | 注释里引用被禁字面量用中文代称; 字面量只许出现在变异台/断言本体 | R170 |
| **看门狗口径=整机负载** | 整机100%而训练族仅17% → 误杀actor且恢复线永不满足(10-14震荡32min/8次) | 口径=训练族**进程树**累计CPU/逻辑核(树外旁路与对照臂天然排除)+存活sidecar+仪表读者 | R170 |

| **SC标签二次解析覆盖复合宏** | 三角色库中 TM·6a终结/TM·必杀SC连/TM·空连终结 的 Y 恒 0(永远学不到), 1–6% 行归因到同卡的另一个SC宏 | 真因不是"取错帧"(审计假设, 已由A/B实证否掉), 而是**卡ID撞车**: 复合宏 sc:219/200 与裸卡宏撞号 → 只对**裸SC宏**做按卡解析(`bare_sc_names`), 复合宏保留匹配器身份 | R171 |
| **前置清理误杀对照臂(第二形态)** | 给 python 侧加路径豁免后, 游戏段仍按 exe 路径判别 → 两臂共用同一 th123_train\th123.exe, 对照臂游戏被清、actor 连接重置整臂倒下 | 游戏段改**按父进程**(只清父进程∈本轮杀集的游戏); 对照臂另需**绝对路径启动**才会被路径豁免命中 | R170b |
| **门禁"transient"** | 同一测试两天时红时绿, 被写进提交信息当噪声 | "transient"=未定位问题的存放处: 本轮真相=源头秒级时间戳同秒覆盖(bug)+测试断言把bug当预期; 凡两次读数不一致, 必有一侧在编码错误语义 | R171b |
## 十一、文档索引
| **三库并行重建 OOM** | 3 进程×6GB 吃满 31.5GB(可用 0.1GB), marisa 日志停更 15min = 换页假死; 若到 np.stack 峰值(单进程翻倍)必 MemoryError | **最多 2 路并行**, 或串行; 开跑前看可用内存(≥10GB×路数); 判卡死看 CPU 时间Δ而非日志 | R171 |
| **长任务跑在会话托管作业里** | Harness 重启(23:36-23:45)把托管作业连带杀掉, 三路重建 40 分钟白跑且**零产物**(无错误输出) | 长任务用 `Start-Process -WindowStyle Hidden` 分离启动 + 重定向日志; 托管作业只用于短任务 | R171 |

| 文档 | 位置 |
|---|---|
| 宪法+修订记录 | `METHODOLOGY.md`(v3.00) |
| B线方案(顶端标尺) | `docs/_plans/top_yardstick_v2_rpm_vjoy_2026-10-13.md` |
| 研究借鉴方案 | `docs/_plans/research_borrowing_plan_2026-10-13.md` |
| 系列赛方案 | `docs/_plans/series_opponent_prediction_plan_2026-10-06.md` |
| 未决问题方案 | `docs/_plans/unresolved_issues_solutions_2026-10-12.md` |
| 审计报告 | `docs/audit/`(最新: audit_2026-10-18_postR196.md) |
| Bug档案 | `docs/bugs/` |
| 问题陈述(B线) | `docs/_plans/b_problem_statement_2026-10-13.md` |
| 可行性反思v3 | `docs/_plans/feasibility_reflection_v3_2026-10-06.md` |
