# 空间感知只读地图（task-66，2026-10-25；未改代码）

> 目的：回答"感知够不够 vs 模型能不能动"。只读证据，配合 auditor efficacy 报告。
> 数据源：feat_builder.py/game_gates.py/train_tm.py 当前代码；episodes 抽样由
> auditor 用 `D:\temp\scratch\episode_sample_for_audit.py`（待生成）。

## 1. 特征索引地图（feat_builder.build 抽取，行号=代码位置）

> 说明：`o = 2*N` 起为段偏移（N=宏数，三角色 88/95/91）；CORE=391（GEN2）。
> 以下按代码赋值顺序列出（idx 为相对/绝对表达式，可回溯）。

- `s[o:o + 16]` （feat_builder.py:471） 放大2倍让网络"感受"位置差异足以改变决策
- `s[o + my_cls]` （feat_builder.py:486） 256-383=A系攻击, 384-511=B/C系+弹幕, 512-639=必杀/SC
- `s[o + 8 + opp_cls]` （feat_builder.py:488） 256-383=A系攻击, 384-511=B/C系+弹幕, 512-639=必杀/SC
- `s[o]` （feat_builder.py:492） === 3. 朝向 (2) ===
- `s[o + 1]` （feat_builder.py:493） === 3. 朝向 (2) ===
- `s[o + 3]` （feat_builder.py:500） R16§3修正: 原三段循环在i=0即break, 中段/高段永远不写(死区门禁抓出)
- `s[o + 4]` （feat_builder.py:501） R16§3修正: 原三段循环在i=0即break, 中段/高段永远不写(死区门禁抓出)
- `s[o + 5 + i]` （feat_builder.py:504） R16§3修正: 原三段循环在i=0即break, 中段/高段永远不写(死区门禁抓出)
- `s[o + 9 + i]` （feat_builder.py:508） R16§3修正: 原三段循环在i=0即break, 中段/高段永远不写(死区门禁抓出)
- `s[o + 13]` （feat_builder.py:512） (|dy|<=50: 格斗最常见状态, 原四带漏掉[-50,50]区间)
- `s[o]` （feat_builder.py:530） 为NaN)会永久污染 — 非有限差分跳过更新(保留旧EMA)
- `s[o + 1]` （feat_builder.py:531） 为NaN)会永久污染 — 非有限差分跳过更新(保留旧EMA)
- `s[o + 2]` （feat_builder.py:532） 为NaN)会永久污染 — 非有限差分跳过更新(保留旧EMA)
- `s[o + 3]` （feat_builder.py:533） 为NaN)会永久污染 — 非有限差分跳过更新(保留旧EMA)
- `s[o + i]` （feat_builder.py:545） R25: bullet_kin并行表(段6/8共用; 前缀切片与bullets下标对齐)
- `s[o + 3]` （feat_builder.py:546） R25: bullet_kin并行表(段6/8共用; 前缀切片与bullets下标对齐)
- `s[o + 4]` （feat_builder.py:547） R25: bullet_kin并行表(段6/8共用; 前缀切片与bullets下标对齐)
- `s[o + 5]` （feat_builder.py:548） R25: bullet_kin并行表(段6/8共用; 前缀切片与bullets下标对齐)
- `s[o + 4]` （feat_builder.py:568） 追踪弹(turn≥0.08弧/帧): 直线TTI高估 → 按dist/|v|悲观化
- `s[o + 5]` （feat_builder.py:569） 追踪弹(turn≥0.08弧/帧): 直线TTI高估 → 按dist/|v|悲观化
- `s[o + 4]` （feat_builder.py:571） 追踪弹(turn≥0.08弧/帧): 直线TTI高估 → 按dist/|v|悲观化
- `s[gx_off + i]` （feat_builder.py:592） 计入(逼近弹恒0), 威胁特征整体反向
- `s[gx_off + 30 + i]` （feat_builder.py:594） 计入(逼近弹恒0), 威胁特征整体反向
- `s[o + i]` （feat_builder.py:618） 弹幕判定二维(用户提醒: 勿忘纵向), fdy/gy全流程双轴。
- `s[o]` （feat_builder.py:625） === 9. 卡牌感知 (22) ===
- `s[o + 1]` （feat_builder.py:626） === 9. 卡牌感知 (22) ===
- `s[o + 2]` （feat_builder.py:631） 改类型桶: [空|系统≤20|技能100+|符卡200+] + 5维保留位)
- `s[o + 3]` （feat_builder.py:633） 改类型桶: [空|系统≤20|技能100+|符卡200+] + 5维保留位)
- `s[o + 4]` （feat_builder.py:635） 改类型桶: [空|系统≤20|技能100+|符卡200+] + 5维保留位)
- `s[o + 5]` （feat_builder.py:637） 改类型桶: [空|系统≤20|技能100+|符卡200+] + 5维保留位)
- `s[o + 11]` （feat_builder.py:646） 手牌构成one-hot 8(按系统/技能/SC类型桶)
- `s[o + 12]` （feat_builder.py:647） 手牌构成one-hot 8(按系统/技能/SC类型桶)
- `s[o + 13]` （feat_builder.py:648） 手牌构成one-hot 8(按系统/技能/SC类型桶)
- `s[o + 14]` （feat_builder.py:650） 选中存在标志(未校验耗费 — 耗费表在训练层) + 敌公开量3
- `s[o + 15]` （feat_builder.py:651） 选中存在标志(未校验耗费 — 耗费表在训练层) + 敌公开量3
- `s[o + 19]` （feat_builder.py:657） R17: 值从1.0提到1.5(位置信号放大, 与段4同步)
- `s[o + 20]` （feat_builder.py:659） R17: 值从1.0提到1.5(位置信号放大, 与段4同步)
- `s[o + 21]` （feat_builder.py:661） R17: 值从1.0提到1.5(位置信号放大, 与段4同步)
- `s[o:o + len(opp_feats)]` （feat_builder.py:666） === 10. 对手建模 (75: 基础27 + 历史40 + 资源8) ===
- `s[o:o + 22]` （feat_builder.py:671） 对手角色ID从包里拿不到(同角色镜像) → 由外部注入
- `s[o + 3 + _si]` （feat_builder.py:691） 编码等级
- `s[o + 7 + _si]` （feat_builder.py:695） 编码手牌可用性
- `s[o + 22]` （feat_builder.py:705） 对手建模层的全局行为聚合, 随对局演化, 直接可用)
- `s[o + 23]` （feat_builder.py:706） 对手建模层的全局行为聚合, 随对局演化, 直接可用)
- `s[o + 24]` （feat_builder.py:707） 对手建模层的全局行为聚合, 随对局演化, 直接可用)
- `s[o + 25]` （feat_builder.py:708） 对手建模层的全局行为聚合, 随对局演化, 直接可用)
- `s[o + 20]` （feat_builder.py:713） 即P1-a全量, 零迁移成本)
- `s[o + 21]` （feat_builder.py:714） 即P1-a全量, 零迁移成本)
- `s[o]` （feat_builder.py:721） 双谷势: 近战谷110 + 射击谷230
- `s[o + 1]` （feat_builder.py:722） 双谷势: 近战谷110 + 射击谷230
- `s[o + 2]` （feat_builder.py:723） 双谷势: 近战谷110 + 射击谷230
- `s[o + 3]` （feat_builder.py:728） R19: clip防x越界(1240-x可为负)
- `s[o]` （feat_builder.py:732） === 13. 擦弹/防守/时间 (10) ===
- `s[o + 1]` （feat_builder.py:737） R20: 实测防御ID集(原{110-115}恒不命中 → dim258死维)
- `s[o + 2]` （feat_builder.py:738） R20: 实测防御ID集(原{110-115}恒不命中 → dim258死维)
- `s[o + 3]` （feat_builder.py:742） 暴露无害, 但当"被打指示"用是反的。
- `s[o + 4]` （feat_builder.py:743） 暴露无害, 但当"被打指示"用是反的。
- `s[o + 5]` （feat_builder.py:746） 读数(仅28.4%真受击), 未门控时"对手被锁"信号~70%失真
- `s[o + 6]` （feat_builder.py:747） 读数(仅28.4%真受击), 未门控时"对手被锁"信号~70%失真
- `s[o + 7]` （feat_builder.py:748） 读数(仅28.4%真受击), 未门控时"对手被锁"信号~70%失真
- `s[o + 8]` （feat_builder.py:749） 读数(仅28.4%真受击), 未门控时"对手被锁"信号~70%失真
- `s[o + 9]` （feat_builder.py:750） 读数(仅28.4%真受击), 未门控时"对手被锁"信号~70%失真
- `s[o]` （feat_builder.py:761） (原版被arctan2(0,0)=0伪造成"向右"计入bin0)
- `s[o + 1]` （feat_builder.py:762） (原版被arctan2(0,0)=0伪造成"向右"计入bin0)
- `s[o + 2 + i]` （feat_builder.py:769） 弹幕方向分布(6方向one-hot)
- `s[o + min(prev2 // 2, 3)]` （feat_builder.py:775） 14b. 己方动作历史 (8): 最近2次动作类one-hot(4+4)
- `s[o + 4 + min(prev1 // 2, 3)]` （feat_builder.py:776） 14b. 己方动作历史 (8): 最近2次动作类one-hot(4+4)
- `s[o + i]` （feat_builder.py:790） → 段恒零, 由死区门禁行为测试抓出) — 改为真正的按列聚合
- `s[o]` （feat_builder.py:801） — 用户2026-09-29: 放大位置组合的战术含义)
- `s[o + 1]` （feat_builder.py:802） — 用户2026-09-29: 放大位置组合的战术含义)
- `s[o + 2]` （feat_builder.py:803） — 用户2026-09-29: 放大位置组合的战术含义)
- `s[o]` （feat_builder.py:823） R19 NaN防护: 非有限差分跳过(同段5)
- `s[o + 1]` （feat_builder.py:824） R19 NaN防护: 非有限差分跳过(同段5)
- `s[o + 2]` （feat_builder.py:825） R19 NaN防护: 非有限差分跳过(同段5)
- `s[o]` （feat_builder.py:828） 14g. 资源差 (3): 血差/灵差/gauge差(相对量, 核心标量只有绝对值)
- `s[o + 1]` （feat_builder.py:829） 14g. 资源差 (3): 血差/灵差/gauge差(相对量, 核心标量只有绝对值)
- `s[o + 2]` （feat_builder.py:830） 14g. 资源差 (3): 血差/灵差/gauge差(相对量, 核心标量只有绝对值)
- `s[o]` （feat_builder.py:849） R19符号修正: 同段7 — 逼近为正(原版反向)
- `s[o + 1]` （feat_builder.py:850） R19符号修正: 同段7 — 逼近为正(原版反向)
- `s[o + 2]` （feat_builder.py:851） R19符号修正: 同段7 — 逼近为正(原版反向)
- `s[o + 3]` （feat_builder.py:852） R19符号修正: 同段7 — 逼近为正(原版反向)
- `s[o]` （feat_builder.py:861） 已在段2, 时长是次级信息; 段位盲区是技法覆盖L2核心缺口, 价值更高)。
- `s[o + 1]` （feat_builder.py:870） 2B/2C无一下段(旧表虚报); j2A按角色可低可高(天子混合段位)。
- `s[o]` （feat_builder.py:874） (蓄力/段内进度可见; 原R49写尾静默覆盖14i后4维, R57移入账内)
- `s[o + 1]` （feat_builder.py:875） (蓄力/段内进度可见; 原R49写尾静默覆盖14i后4维, R57移入账内)
- `s[o + 2]` （feat_builder.py:876） (蓄力/段内进度可见; 原R49写尾静默覆盖14i后4维, R57移入账内)
- `s[o + 3]` （feat_builder.py:877） (蓄力/段内进度可见; 原R49写尾静默覆盖14i后4维, R57移入账内)
- `s[o]` （feat_builder.py:884） 固定起始316, 不受上方段宽调整漂移)
- `s[316:328]` （feat_builder.py:890） [328]=SC已出/5  [329]=系统卡已出/10 — 仅"已打出过的卡"(合法)
- `s[328]` （feat_builder.py:891） [328]=SC已出/5  [329]=系统卡已出/10 — 仅"已打出过的卡"(合法)
- `s[329]` （feat_builder.py:892） [328]=SC已出/5  [329]=系统卡已出/10 — 仅"已打出过的卡"(合法)
- `s[330]` （feat_builder.py:900） 由调用方注入同构值 — 在线/离线同一build路径, 无双拷贝。
- `s[331]` （feat_builder.py:901） 由调用方注入同构值 — 在线/离线同一build路径, 无双拷贝。
- `s[332]` （feat_builder.py:902） 由调用方注入同构值 — 在线/离线同一build路径, 无双拷贝。
- `s[333]` （feat_builder.py:903） 由调用方注入同构值 — 在线/离线同一build路径, 无双拷贝。
- `s[339]` （feat_builder.py:904） 由调用方注入同构值 — 在线/离线同一build路径, 无双拷贝。
- `s[334]` （feat_builder.py:907） 由调用方注入同构值 — 在线/离线同一build路径, 无双拷贝。
- `s[335]` （feat_builder.py:908） 由调用方注入同构值 — 在线/离线同一build路径, 无双拷贝。
- `s[336]` （feat_builder.py:919） 同类别连出(含当前)
- `s[338]` （feat_builder.py:921） 同类别连出(含当前)
- `s[337]` （feat_builder.py:927） 同类别连出(含当前)
- `s[340]` （feat_builder.py:935） S-7风格pc1/pc2: 惰性(语料缺=embedding返回None→0, 不阻塞)
- `s[341]` （feat_builder.py:936） S-7风格pc1/pc2: 惰性(语料缺=embedding返回None→0, 不阻塞)
- `s[342]` （feat_builder.py:946） 静默防刷屏), 损坏可从日志定位而不是特征层悄悄变零。
- `s[o + 0]` （feat_builder.py:980） k22 对手相对墙位|23 敌方贴角深度
- `s[o + 1]` （feat_builder.py:981） k22 对手相对墙位|23 敌方贴角深度
- `s[o + 2]` （feat_builder.py:982） k22 对手相对墙位|23 敌方贴角深度
- `s[o + 3]` （feat_builder.py:983） k22 对手相对墙位|23 敌方贴角深度
- `s[o + 4]` （feat_builder.py:990） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 4]` （feat_builder.py:992） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 5]` （feat_builder.py:994） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 6]` （feat_builder.py:995） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 7]` （feat_builder.py:996） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 8]` （feat_builder.py:997） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 9]` （feat_builder.py:998） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 10]` （feat_builder.py:999） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 11]` （feat_builder.py:1000） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 12]` （feat_builder.py:1009） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 13]` （feat_builder.py:1010） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 14]` （feat_builder.py:1011） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 15]` （feat_builder.py:1012） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 16]` （feat_builder.py:1014） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 17]` （feat_builder.py:1023） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 18]` （feat_builder.py:1024） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 19]` （feat_builder.py:1025） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 20]` （feat_builder.py:1028） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 21]` （feat_builder.py:1035） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 22]` （feat_builder.py:1036） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 23]` （feat_builder.py:1039） corner_urgency=(1-我方最近墙距/600)*(1-对手最近墙距/600)
- `s[o + 0]` （feat_builder.py:1052） k0..3 actable(frames_in_stun/est_left/near_end/actable), k4..8 天气5D
- `s[o + 1]` （feat_builder.py:1054） k0..3 actable(frames_in_stun/est_left/near_end/actable), k4..8 天气5D
- `s[o + 2]` （feat_builder.py:1056） k0..3 actable(frames_in_stun/est_left/near_end/actable), k4..8 天气5D
- `s[o + 3]` （feat_builder.py:1057） k0..3 actable(frames_in_stun/est_left/near_end/actable), k4..8 天气5D
- `s[o + 4 + _i]` （feat_builder.py:1063） k4..8 天气 5D(EffectEmbed 4D+timer 1D) — stage A2 接入前恒 0
- `s[o + 8]` （feat_builder.py:1064） k4..8 天气 5D(EffectEmbed 4D+timer 1D) — stage A2 接入前恒 0

### 空间辅助函数

- feat_builder.py:246 def track_bullets(self, objs, own=None):
- feat_builder.py:322 def update_opp(self, dt_s, left, right, weather, opp_vx=0.0):

## 2. 动作空间约束盘点（"能不能动"）

- air mask→仅待机/受限：`game_gates.py` 有 AIR_GATE/airBorne 相关门控=True
- immobile 白名单/不可动动作：True
- 掩码关键行：
  - `game_gates.py:5` - task-29: 地空门控(air/ground 显式分类; 命令技按名/静态表分地空; 受身不受 AIR_GATE)
  - `game_gates.py:10` env: TH123_ACT_MASK(总,默认1) TH123_AIR_GATE TH123_IMMOBILE_GATE TH123_DD_GUARD_ONLY
  - `game_gates.py:144` AIR_GATE = os.environ.get('TH123_AIR_GATE', '1') != '0'
  - `game_gates.py:145` IMMOBILE_GATE = os.environ.get('TH123_IMMOBILE_GATE', '1') != '0'
  - `game_gates.py:201` air = bool(left.get('airBorne'))
  - `game_gates.py:203` # (a) 地空门控(受身不归 AIR_GATE; 由不可动白名单控制)
  - `game_gates.py:204` if AIR_GATE:
  - `game_gates.py:211` if IMMOBILE_GATE:
  - `game_gates.py:212` allow = None
  - `game_gates.py:215` allow = UKEMI | WAKE
  - `game_gates.py:217` allow = set(UKEMI)
  - `game_gates.py:219` allow = allow | set(BUFFER_NAMES)
  - `game_gates.py:221` allow = allow | set(UKEMI_DIR_TOKENS)
  - `game_gates.py:223` allow = set()   # 只剩待机(方向/受身/跳跃/5A 全屏蔽)
  - `game_gates.py:225` allow = allow | set(GUARD_CANCEL_NAMES)
  - `game_gates.py:227` allow = set(GUARD_MACROS) | set(CARDS_GROUND) | {
  - `game_gates.py:230` allow = allow | set(BUFFER_NAMES)
  - `game_gates.py:232` allow = (set(BUFFER_NAMES) if (_buf_ok and not buf_block)
  - `game_gates.py:234` if allow is not None:
  - `game_gates.py:236` if n not in allow:

### 宏粒度（移动/跳跃类宏是否存在）

| 角色 | 宏数 | 移动/跳跃类宏 |
|---|---|---|
| reimu | 88 | 跳跃、后跳、空冲、高跳、斜后跳、飞翔、空冲后、5B·高跳取消、5B·空冲取消 |
| marisa | 95 | 跳跃、后跳、空冲、高跳、斜后跳、飞翔、空冲后、5B·高跳取消、5B·空冲取消 |
| suika | 91 | 跳跃、后跳、空冲、高跳、斜后跳、飞翔、空冲后、5B·高跳取消、5B·空冲取消 |

> 精确移动（逐帧方向/冲刺/44/66/飞翔/HJC）是否可选：取决于上述宏覆盖 + game_gates immobile 白名单；auditor 需用 episodes 的 acts 分布验证。

## 3. 空间相关奖励（当前生效值）

| 项 | 代码/值 |
|---|---|
| 空间奖励 step | `space_reward_step` 生效 |
| 空间奖励接口 | `def space_reward_step(self, left, right, d_take, fev):` |
| 空间奖励接口 | `_sp_r = space_reward_step(self, left, right,` |
| `POT_W` | `{` |
| `R_SPACE_EDGE` | `float(os.environ.get('TH123_REW_SPACE_EDGE', '0.0015'))` |
| `R_SPACE_ESCAPE` | `float(os.environ.get('TH123_REW_SPACE_ESCAPE', '0.03'))` |
| `R_SPACE_SURVIVE` | `float(os.environ.get('TH123_REW_SPACE_SURVIVE', '0.02'))` |
| `R_SPACE_DIV` | `float(os.environ.get('TH123_REW_SPACE_DIV', '0.01'))` |
| `R_SPACE_CROSS` | `float(os.environ.get('TH123_REW_SPACE_CROSS', '0.05'))` |

- 奖励常量样本: AIR_PASSIVE_GRACE = 30, COM_CLIMB_N = 20, COM_CLIMB_WR = 0.5, COM_FALL_N = 40, COM_FALL_WR = 0.2, GAMMA_POT = 0.999, GRAZE_FULL_CAP = 20.0, GRAZE_LOW_RATE = 0.01, GRAZE_SAT_F = 6000.0, LOW_SPIRIT_PEN = 300.0, MICRO_TAX_LOSS = 0.7, POOL_K = 3

## 4. 初步判读框架（待 auditor 数据后定论）

- 若特征有判别力（TTI/距离/角/弹 dx,dy 等已存在）但 **动作空间/掩码不允许**（精确移动缺失/air mask 过严/宏粒度太粗）→ 优先改动作/宏/奖励（task-63/registry/action residual），不是继续加维。
- 若 episodes 统计显示：空间事件（穿弹/贴边/绕上）发生时 do-nothing/guard 占比高且移动类动作不可选 → 支持"能不能动"是瓶颈。
- 反之若可选但从不选 → 策略/奖励问题（距离势/规避奖励是否被压制）。

## 5. 待补（auditor）

1) episodes 抽样脚本（近 N 局：state feat 索引/动作/mask/奖励分量）→ 统计稀疏/死角；
2) 空间事件命中率：TTI<30F 时动作分布（移动 vs 防御 vs 攻击）；
3) 动作可选性：mask 对移动宏的 allow 频率 vs 采样选择频率（可选但不选=策略问题）。
