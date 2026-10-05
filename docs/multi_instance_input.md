# 多实例输入注入 — 最终架构(2026-09-22 · TM通道全档)

> ⚠ **部分过时快照(2026-09-22横幅)**: 本文数值/状态可能滞后(已知: CharacterState
> 实为105字节 · 奖励尺度已改0.004/-0.005/±10)。**一切以 `METHODOLOGY.md` 与
> `tools/contract_check.py` 为准**; 入口路由见根目录 `AGENTS.md`。

> **宪法文档: METHODOLOGY.md** — 训练方法论与规范(纪律红线/奖励定律/
> 宏保真三律/协议不变量/事故清单), 一切变更以其为准。

## ⓪ 当前生产线(v3 定稿, 全部实测)

```
run_parallel.py ─ 三进程编排(灵梦20800/魔理沙20810/萃香20820, tps480)
 └─ train_tm.py ─ 每角色训练器
     ├─ tm_env.py ─ TMEnv: VS_COM开局/同进程续局/输入表回填/首帧容错
      │   └─ soku_client2.py ─ TCP锁步协议(105字节CharacterState×2+天气+弹幕对象)
     ├─ 虚拟视觉: 包渲染3×60×80网格 → ppo.py conv主干(14400维, N_SIDE/N_OUT参数化)
     ├─ 宏库: macros(灵梦55)/macros_marisa(61)/macros_suika(62) — 键名→输入位图
     ├─ 奖励: HP差分±(0.02/-0.025) + 回合胜负(±1.2, score差分) + 墙罚 + 灵力维持
     └─ 诊断: distill_data_<char>.npz(11列态势行) + 每10局标准树audit + 视觉方差告警
```

**吞吐实测**: tps480=436帧/s(7.3×); 同进程续局0冷启动(vs 进程重启6-8s);
无头(默认)单实例帧率持平省GPU。三实例并行 ≈ 1300帧/s总吞吐。

**关键决策记录**:
- **屏幕捕获废弃**(用户发问"视觉模块真的有必要吗"触发重审):
  遮挡冻结+刷新率锁死+屏幕宽度多开上限 → 虚拟视觉(包渲染同构网格);
- **同进程续局**: mod协议bug(半包/返回尺寸)修复后从"不可用"变"最优";
- **tps语义**: 每秒逻辑帧数(60=原速); 480甜点(960反而345fps)。

## 一、终极方案：自编译 PinkySmile TrainingMod + TCP 协议（全部验证通过）

### 组件
- **`SokuAITrainer.dll`**（VS2022/x86 编译, D:\temp\build\build_tm.bat）
  - 源码: PinkySmile/SokuAI TrainingMod + SokuDev/SokuLib@09fed34
  - 部署: `th123_train\modules\SokuAIOfflinePlayer\`（mod.json 指向 SokuAITrainer.dll）
- **独立训练目录** `D:\touhou\hisoutensoku2026-06-15\th123_train\`（3.5GB 全拷贝）
  - 最小 mod 集: **MemoryPatch(必须!带参启动硬依赖) + SokuAITrainer**
  - profile\SokuAI.pf 必须存在（缺档=开局崩溃）
- **`soku_client2.py`**: 协议客户端（TM 105字节 CharacterState; calcsize实证）
- **`tm_env.py`**: 多环环境（按局重启续局+输入表回填+变速后置）

### 我们修复的 PinkySmile mod 源码 bug（5处）
1. `CHECK_PACKET_SIZE` 半包错位: 收包循环改整包重组(carry缓冲)
2. INPUTS被拒返回1字节(应5): 启动期输入洪泛→mod流永久错位(err=0/10垃圾)
3. SET_POSITION 错误路径返回 SetWeatherPacket 尺寸
4. setupNetwork 无幂等: 场景机重放Logo→二次连接→sock替换→客户端孤儿化
5. startGame 时序: SELECT中拉回TITLE让CTitle原生消费startRequested
   (直接写LOADING会跳过场景机交接→loading卡死)
### 我们的适配修补
- Initialize 无参休眠(手动开局零干扰) / 保留全部渲染(黑屏修复:
  swapDisplay+Logo渲染哑化+fakeLoad贴图三处全关) / Direction cast×2

### 协议关键知识（踩坑记录）
- **锁步制**: mod每逻辑帧发状态后忙等输入 → 客户端必须持续发输入,
  停发=互锁死结; 加载期输入会收err=17(视为未进战斗继续喂)
- **tps=每秒逻辑帧数**(非倍率): 60=原速, 120=2倍; 开局前设tps会破坏启动
- 对象计数=双方objectCount之和; SPEED/DISPLAY等控制包会插帧回复OK
- verify要求sceneId∈{TITLE,SELECT}; 演示模式(选人闲置~10s)会锁死网络线程
- 游戏结束时mod侧可能悬半个输入包 → 按局重启进程(5s开销)最稳

### 实测指标
- VS_COM: 程序化开局(任意角色/卡组/场地) 一次过
- tps=120: 6602帧/60s=110fps(2倍速+完整渲染), 零错误零重启
- 输入验证: 干净对照 H=+1×180帧→Δ+174, H=-1×120帧→Δ-541
- VS_PLAYER(自对弈)模式: **已跑通**(2026-09-22 外环/自对弈训练半环在用);
  启动期偶发场景振荡由env自愈重启兜底, accept有120s超时(第六轮§7b)

## 二、已废弃的备选方案（留档）
- v8/v9 input_bridge(0x40A45D rel32重定向+KeymapManager计数器覆写):
  端到端验证通过(P1Δ558/P2Δ159/A键-450HP), 但手动管理场景/输入表,
  被 TM 方案整体取代。编译: gcc -m32 input_bridge.c
- keybd_event/SendInput: Giuroll LL钩子过滤注入键(INJECTED位), 物理键有效

## 三、纪律红线（用户明令）
- 公平对战: 只写己方输入, 不读对方输入指令
- 内存写入仅限训练过程、有界、字节预检
- 不改 keybd_event 默认路径

## 四、下一步
 - v1简化项回迁: 符卡宏(包手牌数据在手, sc状态机已接入2026-09-23)、
  奖励精修(势函数/微奖励/打康加成)、物理掩码(距离禁近战)
- v2: VS_PLAYER自对弈修复(对照C++侧用法) / 对手建模侧特征回迁
- 远期: tps>480实验(锁步往返优化) / 关渲染下进一步压CPU

## 五、参考来源
- PinkySmile/SokuAI TrainingMod(协议/startGame/gameParams直填开局)
- SokuDev/SokuLib@09fed34(KeymapManager布局/地址表/VTables)
- delthas/SWRSToys swrs.h(TamperNearJmpOpr/NativeDPadFix文档)

