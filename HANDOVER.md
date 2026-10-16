# TH123 对战 AI 项目交接文档

> 日期: 2026-10-16 · 增量(**BH-3.2 守备段位逐角色表[clesita实测20/20, 旧表两错修正]**/BH-3.1 untech语义门(P1清偿)/CE-7推板势/CE-3.4位置路由门/CE-5离线分歧率仪表/CE-4目标索引修复) · 供下一个智能体直接接手

**当前栈速览(2026-10-16)**: CORE_DIMS=**358**(S-2段343+JZ-1段15);
宏数reimu88/marisa95/suika91(蓄力cleista真值+系统卡+DD+HJC);
S-4 GRU序列记忆全链就绪(阶段2a); BH方案v4执行中: **BH-3.1/3.2/3.3
感知修复✅** / **BH-1 行为健康仪表盘✅**(behavior_health.py+bh旁车+
CE-0.1帧日志开关[TH123_FRAME_LOG默认关]+tools/behavior_report.py
八表) / **BH-4.2 语料扩对位采集进行中**(765 rep=15对×51对, tr*分片
+manifest pair字段, 断点续采, ~过夜; 库内12,246候选全覆盖) /
**BH-4.3 对位先验表✅**(matchup_combo_prior.json: UU/早苗/YM/⑨
解码+"19"与高个子名单unverified待确认); **剩余: BH-4.1 matcher
连段语境(1d) → BH-4.4 合批重建(untech门+段位表+matcher+扩位语料
四合一, 与S-6同批)**。
CE离线件全谱就绪(R131-139); 观察期继续。门禁633/0; 变异锚点干跑
tools/_anchor_check.py(救过两次变异定义写反)。帧日志需
TH123_FRAME_LOG=1。关键数据: cleista/(API全量+守备段位134档)+
guard_height.json+matchup_combo_prior.json; move_displacement_*.json。
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
| `tools/contract_check.py` | **门禁**(618+断言, 全绿才可提交) | 新增断言 |
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

## 五、门禁(每次提交前必须全绿)

```bash
D:\temp\pyenv\python.exe tools/contract_check.py
# 必须 exit 0 (从零#4时点 618 PASS / 2 WARN / 1 FAIL—FAIL为在途注册缺口, 已清)
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
