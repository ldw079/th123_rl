# B · 顶端标尺完备方案——真人 vs 模型直接对局（终版 · 2026-10-13）

> 需求: 用户令"把 B（人 vs 模型标尺）的方案设计完备"。
> 前置: 未决问题方案 §B（骨架三件: mod P2-only / HumanMatchEnv / 测量协议）已部分落地——本方案在实况核验基础上补全为**可直跑的完备设计**。
> 定位: 主规划 E 工作流核心项; **同时解锁教学产品化（§I）**——真人输入流是习惯检测的唯一数据源。

---

## 0. 现状核验（时点 2026-10-13 12:16, 基线 `39c19e3`）

| # | 盘点项 | 实况（亲验） | 缺口 |
|---|---|---|---|
| 1 | mod P2-only | **源码已实现**（main.cpp:53-56 `SOKUAI_P2_ONLY` 环境变量分支, :58 钩子内条件跳过 P1 覆写） | **未编译部署**——build_tm.bat 依赖的 D:/VS 工具链 10-11 被清理; 现部署 mod 不含此功能 |
| 2 | HumanMatchEnv | **tools/human_match.py 已有 209 行**（tps=60/render=True/键位 VK 表/BO-N/场终统计/rep 归档/action_seq 采集） | mod='mod' 模式在未部署前不可用; 走 poll=轮询应急路线 |
| 3 | SeriesManager | **series_manager.py 78 行已实现**（series_len/win/in_series/match_number_next; train_tm:537-538 已接, 归因隔离默认 legacy=0） | human_match 未接 SeriesManager（BO-N 自行计数, 不复用）; 完整 BO15 待系列方案阶段 1 |
| 4 | 键位轮询 | `GetAsyncKeyState` 轮询 → 协议输入位, config.py KEYMAP 同源 | **无 SC 键映射**（U=SW=切卡, 缺"用卡"键 I=SC）; 轮询频率未标定 |
| 5 | 习惯链 | habit_detector + habit_punish_demo 已在; human_match 后半段 action_seq→detect_habits→habit_report **已接** | 无（本项完工） |
| 6 | eval_matrix | run_matchup(char_a,char_b,port,games,tps) 无 human 入口 | 无 vs-Human 段; 无同尺锚定 |
| 7 | rep 取证 | human_match 归档 rep 路径到 json | 已有 |

**结论**: B 的**代码基础比方案文档预期的更完整**——mod 源码、Env、SeriesManager、习惯链四件全部在库。缺的是: **①mod 编译部署（工具链修复）②SC 键补全③锚定局协议④F6 接入⑤BO15 系列整合**。以下按这五个缺口给完备设计。

---

## 1. B-1 · mod 编译部署（正路开通, 1-2 人日）

**问题**: build_tm.bat 依赖的 D:/VS 工具链被清理——mod 源码有 P2-only 功能但编译不出。

**方案**:
1. **工具链恢复（0.5-1 人日）**: 确认需要的最小工具集（从 build_tm.bat + CMakeLists 逆向: MSVC cl.exe / MinGW gcc / SokuLib 头文件）; 优先找本机已有（`where cl` / `where gcc` / VS 安装目录）; 若需安装: **[用户裁定项 B-1a]** 安装路径与许可（VS Build Tools 免费版 vs MinGW）;
2. **编译+血统全流程（0.5 人日）**: 恢复后跑 build_tm.bat → C9 断言（源码哈希==构建产物==部署 MD5）→ update_provenance → 部署至 th123_train;
3. **冒烟验证（并入 B-4 首测）**: SOKUAI_P2_ONLY=1 下游戏启动, P1 键盘直通、P2 TCP 驱动——首次人测即冒烟。

**回退**: 工具链不可恢复时, human_match 的 poll 模式已可用（GetAsyncKeyState 轮询, 无需 mod 改动）——但**轮询有 ~1-2 帧延迟且窗口失焦即断**（GetAsyncKeyState 全局态但受前台影响）, 仅作过渡, 不作长期标尺。

**验收**: `md5sum 部署DLL == provenance JSON deployed_md5`; human_match mode='mod' 一局完整（P1 人类物理键控制, 无轮询日志行）。
**门禁**: C9 血统断言更新（新 MD5 + 源码哈希）+ 变异（P2-only 分支删除必须红——C15 新增行为测试: 模式下 P1 输入≠TCP 发送值）。

## 2. B-2 · HumanMatchEnv 补全（0.5 人日, 与 B-1 并行）

对现有 tools/human_match.py 的**增量修改**（不重写）:

| 项 | 改动 |
|---|---|
| SC 键 | VK 表补 `I: 0x49` → 协议 `'SC': True`（用卡）——与 config.py KEYMAP 同源（SC=I, SW=U） |
| 轮询频率 | poll 循环加注释标定（当前每锁步帧一次=62Hz, 足够; 但记入文档防误改） |
| render=True | 已在——文档级确认: 人测必须渲染（TCP DISPLAY 命令, 无 mod 依赖） |
| SeriesManager 接入 | `--bo N` 参数改走 SeriesManager(series_len=N, series_win=(N+1)//2)——复用系列方案的先到 ceil(N/2) 语义; BO15 即 series_len=15, series_win=8 |
| 模式选择 | `--mode mod/poll` 显式参数; mod 不可用时自动降 poll + 醒目警告 |

**验收**: BO3 模式下一场完整（人类胜或模型胜, 场终/系列统计正确, rep 归档）。
**门禁**: 键位映射行为断言（GetAsyncKeyState 模拟→协议位, 含 SC）+ SeriesManager 接入断言。

## 3. B-3 · 测量协议（0.5 人日设计 + 首测 1 小时会话）

### 3.1 同尺锚定（核心设计——使"模型 vs 人类"的比分可解释）

**问题**: 一个人类的"强"是什么水平？没有锚, 3:0 和 0:3 都无法定位模型刻度。

**方案**: 每次测量会话固定三段（总 ~45-60 分钟）:
1. **锚定段（~15 分钟）**: 同一人类打 **3 局 COM Lunatic**（vs_com=True, com_difficulty=3）——人类的 COM 胜率=其在 COM 标尺上的位置; 模型的 COM 胜率已有周报——**两者投影到同一 COM 刻度上**;
2. **主测段（~20-30 分钟）**: 人类 vs 模型 **BO5**（首测; 完整 BO15 待系列方案阶段 1 稳定后升级）;
3. **可选第二段（~10 分钟, 首测跳过）**: 人类 vs 池快照（选 1 个非当前模型的快照, 测"模型 vs 同水平对手"的人类分差——后续做 Elo 混合标尺的基础）。

### 3.2 会话报告格式

```json
{
  "session_id": "hm_20261013_1430",
  "measurer": "user",
  "anchor": {"com_lunatic": "2W-1L"},
  "main": {"char": "reimu", "bo": 5, "score": "3-2", "per_game": [...]},
  "rep_paths": [...],
  "habits": [...],           // habit_detector 输出
  "notes": "..."             // 会话元数据（模型版本/端口/模式）
}
```

### 3.3 周度节律

- **固定测量员**（用户裁定③: 用户自任）+ **固定时段**（减少状态漂移）;
- 每周一次, 报告追加进 `human_match_report.json` + F6 战报新增"vs Human"段;
- **趋势判定**: 连续 4 次会话的 BO5 比分移动平均（单次样本太小不可判——Wilson CI 在 n=5 时宽度 >0.5）。

### 3.4 人类输入日志（教学产品化的数据源, §I 联动）

human_match 的 action_seq 已采游戏侧 resolved action——**额外补采键盘原始输入流**（与 resolved action 平行存档, 帧对齐）:
- 用途 A（习惯检测）: habit_detector 当前消费 resolved action; 键盘原始流可检测**输入习惯**（如"总在受击后立刻按防"= 慌防）——比 resolved action 更接近"教学"语义;
- 用途 B（延迟测量）: 键盘按下→游戏生效的帧差 = 该人类的反应延迟（W1 延迟消融的人类真实锚点!）;
- 存储: 会话 json 内 `raw_keys: [[frame, key_bits], ...]`（帧号+u16, 与 rep 输入流同构——直接复用 bc_match 的解码）。

**验收**: 一次完整三段会话产出: 锚定局比分 + BO5 主测比分 + rep 归档 + 习惯报告 + raw_keys 流。
**门禁**: 会话 json 格式断言 + raw_keys 非空断言。

## 4. B-4 · F6 评估矩阵接入（0.5 人日）

- `tools/eval_matrix.py` 增 `vs_human` 段: 读 human_match_report.json, 输出"会话×比分×锚定"表;
- **超人距离更新**: v3.1 的超人距离框架中"顶端标尺"从"缺位"改为"人测数据"——计算方式: 模型对人类 BO5 胜率 > 50% 且锚定段人类 COM Lunatic 胜率 > 60%（即测量员确为强人类）时, 记"已超该测量员"; 单测量员不足以宣称"超人"（需 ≥2 测量员或 1 测量员 + COM 饱和证据）;
- **显式限制声明**: 单人标尺测的是"超一个人类"而非"超人类顶尖"——报告措辞必须区分。

**验收**: eval_matrix 报告出现 vs_Human 段; 超人距离行有数据（或显式"标尺缺位"）。

## 5. B-5 · BO15 完整系列整合（依赖系列方案阶段 1, 不重设计）

- SeriesManager 已实现（78 行, legacy=0 默认）——human_match 的 `--bo 15` 直接走 SeriesManager(series_len=15, series_win=8);
- **系列内对手画像不重置**: human_match 中 SideDriver 的 feat_builder.reset_match 由 SeriesManager 管控（与训练侧同构）;
- 完整 BO15 首测**不建议首次即用**——先用 BO5 跑通全链, 系列方案阶段 1 在训练侧稳定后再升级。

## 6. 风险表

| 风险 | 概率 | 缓解 |
|---|---|---|
| VS 工具链不可恢复（B-1 卡死） | 中 | poll 模式过渡（已可用）; 标注"轮询延迟 1-2 帧"的测量不确定性 |
| 单测量员偏差（"超 user"≠"超人类"） | 高（确定） | 报告显式区分; 中期引入第二测量员或 COM 饱和佐证 |
| 人类"知道对手是 AI"改变打法 | 中 | 会话 notes 记录心理状态; 不做盲测（伦理+实操成本） |
| tps=60 下模型帧级事件退化 | 低 | 帧级事件以逻辑帧计（62fps 教义）, tps 只改墙钟节奏; 首测观察事件频率 |
| 键盘映射错误（SC 缺失/错位） | 低 | B-2 行为断言; 首测前用户确认键位手感 |
| 与 fleet 并存抢资源 | 中 | probe 端口段 + 人测会话级低频（周一次, 非持续）; tps=60 负载远低于训练 |

## 7. 排期

```
B-2 Env 补全(0.5d) ──┐
B-1 工具链+编译(1-2d) ─┤── 并行; B-1 完成后切 mode='mod'
B-3 协议设计(0.5d) ────┤
                        ▼
              首次完整会话(1h, 含锚定+BO5+习惯+raw_keys)
                        ▼
B-4 F6 接入(0.5d) ── → 周度节律开始
B-5 BO15 升级 ── 系列方案阶段 1 稳定后
```
总计 **2.5-3.5 人日 + 首测 1 小时**（B-1 工具链风险另计）。与 W 系列和研究借鉴方案的排期关系: **B 先行**（已裁定）。

## 8. 用户裁定项

| # | 项 | 状态 |
|---|---|---|
| B-1a | VS 工具链安装路径与许可 | **待裁定**（Build Tools 免费 vs MinGW） |
| ~~③~~ | 测量员人选 | **已裁定**: 用户自任 |
| B-5' | BO15 首测时机 | 建议: BO5 跑通 2 次会话后升级; 用户可提前 |

## 9. 不变面

- R1 公平红线全程（人测模式是 R1 的**字面实现**: 只写己方=P2 输入, P1=人类物理键盘/mod 直通）;
- mod 改动走血统全流程（C9/变异/冒烟）;
- 测量工具不触训练主链;
- 会话数据单写者（human_match_report.json 仅人测进程写）;
- **poll 模式仅过渡**: 一旦 mod 部署成功, mode='poll' 标记 deprecated（轮询延迟记入报告不确定性声明）。

## 10. 总验收

| 项 | 量化阈值 | 测量方法 |
|---|---|---|
| mod 部署 | C9 血统三重一致（源码==构建==部署 MD5） | contract_check + provenance |
| 首次会话 | 三段完整（锚定+BO5+归档）; raw_keys 非空; 键位含 SC | 会话 json + 人工确认 |
| F6 接入 | vs_Human 段出现; 超人距离行有据 | eval_matrix 报告 diff |
| 公平性 | tps=60 全程; P1 无 TCP 覆写（mod 模式日志零轮询行） | 会话日志 |
| 周度趋势 | 4 次会话后移动平均可计算 | human_match_report.json 时间序列 |

---
*本方案三段齐备（现状核验 2026-10-13 12:16 / 可执行方案 / 验收途径）, 合规 PLANNING_AGENT.md。实施修订同步 METHODOLOGY 修订记录。*
