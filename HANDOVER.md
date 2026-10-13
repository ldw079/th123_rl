# TH123 对战 AI 项目交接文档

> 日期: 2026-10-13 · 大更新(首测完成/可迁移化/B线全通/600门禁) · 供下一个智能体直接接手
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
| `tools/contract_check.py` | **门禁**(600+断言, 全绿才可提交) | 新增断言 |
| `tools/gate_selftest.py` | 变异自检(沙箱逐条变异→门禁必红) | 新增变异 |
| `portmap.py` | 端口段划分(20800-21299) | 端口变更 |
| `series_manager.py` | BO15系列赛管理(阶段1, flag门控) | 系列赛启用时 |

## 四、训练启动/停止

```bash
# 启动(手动, 用户裁定)
D:\temp\pyenv\python.exe tools/train_start.py --actors 3 --tps 360

# 停止
D:\temp\pyenv\python.exe tools/train_start.py --stop

# 状态查看
tail -5 D:\temp\th123_models\fleet_supervision.log
```

**CPU红线 ≤75%**(用户明令): 看门狗自动降容/恢复actor(均值>75%暂停最新, <65%恢复).

## 五、门禁(每次提交前必须全绿)

```bash
D:\temp\pyenv\python.exe tools/contract_check.py
# 必须 exit 0 (当前 600 PASS / 0 WARN / 0 FAIL)
```

**纪律**: 裸跑(不pipe)+检查退出码. `| tail` 会吞退出码(f4668e1事故).

## 六、当前状态(2026-10-13 晚)

### 已完成
- **首次人 vs 模型 BO5**(用户3-0, 基建全通, METHODOLOGY 3.00)
- **B线全通**: B-1观察(12项偏移实证)+B-2行动(内存写)+B-3 runner+B-4 F6
- **可迁移化**: kit_config + build_kit(11MB采集包)
- **研究借鉴方案W3/W4/W5**: 四口径/价值轨迹/exploit衰减
- **E阶段1 SeriesManager**: 已建未启用(flag门控, 待A/B后)
- **E阶段3前置 GRUCell**: numpy实现+torch等价验证
- **高手rep库**: 61,572个(双边768 shards已采集)
- **F项吞吐标定**: 157局/h(3actor红线内), D2'关闭
- **H项学习曲线**: 三角色均上升(非平台)

### 等待中
- **A/B 24h验收**: 奖励对称化(A1-2)累计~16h/24h, 明天凌晨满
  → `python tools/ab_verdict_a12.py` 出三指标裁定
- **W1延迟消融试点**: 后台运行中(attribution_probe.py)

### A/B通过后的批次
1. E阶段1b启用(系列模式+eval --series+meta落盘)
2. BC库重建(768高手shards)
3. sc首帧镜像+灵力门修复(推迟项)
4. 剥削者lane复跑(CPU预算评估后)

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
D:\temp\pyenv\python.exe tools/human_match_v2.py --char reimu --seconds 1800

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

## 十一、文档索引

| 文档 | 位置 |
|---|---|
| 宪法+修订记录 | `METHODOLOGY.md`(v3.00) |
| B线方案(顶端标尺) | `docs/_plans/top_yardstick_v2_rpm_vjoy_2026-10-13.md` |
| 研究借鉴方案 | `docs/_plans/research_borrowing_plan_2026-10-13.md` |
| 系列赛方案 | `docs/_plans/series_opponent_prediction_plan_2026-10-06.md` |
| 未决问题方案 | `docs/_plans/unresolved_issues_solutions_2026-10-12.md` |
| 审计报告 | `docs/audit/`(最新: strict_r82_r90b) |
| Bug档案 | `docs/bugs/` |
| 问题陈述(B线) | `docs/_plans/b_problem_statement_2026-10-13.md` |
| 可行性反思v3 | `docs/_plans/feasibility_reflection_v3_2026-10-06.md` |
