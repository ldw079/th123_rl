# 公开化收尾操作方案（审计侧，2026-10-17）

> **定位**：补 `docs/_plans/public_release_hardening_plan_2026-10-17.md` v3 的缺口。
> v3 结论为「切 public 前仅剩 §③ runbook」；本轮从零#5 审计证明**该结论不成立**
> （三处阻断，见 §1）。本文件是**审计侧交付**：正文所有权归规划（`docs/_plans/`），
> 执行归施工；规划可整体并入主方案或转为 PR-6/7/8。
> **前提**：`origin` = `ldw079/th123_rl`（当前 **private**），`main = origin/main = 21bfcdb`。
> **不写代码、不改数据**——本方案只给动作与验收（审计与修复分离）。

---

## 1. 现状（实测，截止 2026-10-17 20:00）

| 检查项 | 实测 | 判定 |
|---|---|---|
| 当前树 Windows 用户名 `96120` | 0 处 | ✅ |
| `main` / `origin/main` 历史含 `96120` | 0（仅本地 `pre-rewrite-backup` 有，未推送） | ✅ |
| **另一台机器用户名** `<other-machine>\Users\...` | **6 行 / 1 文件**，且 `git log main -S` **命中** | ❌ 阻断 |
| **第三方玩家昵称 + 10 位 ID**（`_player_anon`、`_player_anon2`） | **37 行 / 5 文件**，且 `git log main -S` **命中** | ❌ 阻断 |
| `%USERPROFILE%` 字面量（排除 `_archive/`、`tools/quarantine/`） | **25 文件 / 36 处**（含门禁 2 测试 + `bc_build.py`） | ❌ 阻断 |
| 门禁 | **637 PASS / 5 WARN / 2 FAIL → 阻断** | ❌ 阻断 |
| `soku_arch`（`bc_build/bc_match/oracle_batch2` 顶层硬依赖） | 入库 **0 文件**，仅存在于 `D:\temp\soku_arch` | ❌ 阻断 |
| `_archive/` 被跟踪文件 | **117 个**（含 2 个 npz 共 ≈0.46MB） | ⚠ 决策 |
| 密钥 / 邮箱 / 公网 IP | 全树 0 命中 | ✅ |
| 游戏资产 / 模型 / BC / `.rep` | 0（`data/` `dist/` 均 ignore） | ✅ |
| 出处纪律 | `docs/soku_action_ids.md` 钉 SokuLib 仓库+commit+作者；cleista 遵守 llms.txt（50/分<120/分、ETag、署名） | ✅ |

**v3 里两句话必须更正**：
1. 「公开化审计完成: 无 PII」→ 只对 `96120` 一族成立；另有一台机器的用户名与 37 处第三方昵称未纳入扫描规则。
2. 「切 public 前仅剩 §③ runbook」→ 实际还差 3 批（PR-6/7/8），≈2 人日。

---

## 2. 决策点（用户先裁，4 项）

| # | 决策 | 选项 | 建议 |
|---|---|---|---|
| D1 | 是否**二次历史重写**清 PII | A 一次性重写清干净 / B 只清 HEAD、接受历史残留 / C 暂不公开 | **A**（PII 一旦被索引收不回；且已重写过一次，第二次成本边际递减） |
| D2 | `soku_arch` 怎么办 | A vendor 入库 / B README 声明"不提供" | **A**（若是自有包；否则 B 并写清后果） |
| D3 | `_archive/` 是否继续公开 | A 重写时一并剔除（`--invert-paths`）/ B 保留 | **A**（117 个退役探针，且内含大量 `%USERPROFILE%` 旧串，公开只增加噪音与误读） |
| D4 | 会话 JSON 脱敏粒度 | A 整条删除 / B 匿名化保留结构 | **B**（`tools/eval_matrix.py:301` 只用 `len(new_reps)`，保留长度即不破消费） |

---

## 3. 执行顺序（关键：**先内容 → 再一次性重写 → 最后切可见性**）

> 反例（不要这样做）：先重写历史、再改内容 → 会重写两次、force-push 两次、worktree 重置两次。

### Phase 0 冻结与备份（约 10 分钟）

- 本地备份分支（**永不 push**，2 周后删）：`git branch pii-backup-20261017`
- 整仓镜像（重写唯一可靠回滚）：`git clone --mirror . D:\temp\repo-mirror-20261017`
- 记录基线：`git rev-parse HEAD`、`git ls-remote origin`
- 窗口纪律：全程**禁止**执行 `tools/train_start.py`（其前置清理会误杀对照臂，见
  `bug_2026-10-17_control_arm_silent_death`）；重写前工作树必须干净（本审计报告与本方案
  先提交或 stash）。
- 不需要停 fleet：本方案不触 `store/`、不重建 BC。

**验收**：`git branch --list 'pii-backup-*'` 有输出；镜像目录存在且 `git fsck` 干净。

---

### Phase 1 PII 脱敏（工作树，≈0.5 人日）— 归属：施工

| # | 文件 | 现状 | 改法 |
|---|---|---|---|
| 1 | `tools/human_match_sessions/sess_20261013_213252.json` | `new_reps` 6 条含 `<other-machine>\Users\...` + 玩家昵称 | 值改为 `"rep_001.rep"`…`"rep_006.rep"`；新增 `"redacted":"2026-10-17"`、`"n_reps":6`；**保留 key 与数组长度** |
| 2 | `sess_20261015_{165447,170129,170909}.json` | 同型（5–6 条） | 同上 |
| 3 | `tools/human_solo_report.json` | 15 处 `rep` 字段含玩家昵称 | `rep` → `"rep_%03d.rep"`；**保留 `md5`（唯一键）与 `valid`/`invalid_reason`** |
| 4 | `config.py:44` | 注释引用第三方 `.pf` 文件名 | 改为「用户指认键位与某 AI profile 一致」 |

**执行前必查消费方**（改动安全性的依据，已实测）：
- `tools/eval_matrix.py:301`：`len(d.get('new_reps', []))` → 只依赖长度 ✅
- `tools/habit_punish_demo.py:111`：`json.load(open(REPORT))` 后按条取字段 —— **执行前
  先 `grep` 其字段名**（当前只用到 `rep` 作为标签则安全；若按文件名匹配需同步改）。
- `tools/human_match_v2.py:530-560`（写者）：`_dst = os.path.join(REP_DIR, ts + _fn)` 后
  `new_reps.append(_dst)` → 记录的是**运行者本机的绝对路径**（收件机上就成了
  `<other-machine>\Users\Downloads\...`），且 `_fn` 是**原 rep 文件名**（自带第三方玩家昵称）。
  **同一批必须改两处**：①`_dst` 改 `%Y%m%d_%H%M%S_%03d.rep`（丢弃原名）；②`new_reps`
  记 `os.path.basename(_dst)`（或记 `sha1` 前 12 位）。否则下一场人测又会长回 PII。
  注：`REP_DIR = STORE_DIR/human_reps`（`D:\temp\th123_models\human_reps`，仓外），
  故 `.rep` 本体不入库——泄漏的只是**路径字符串**。

**验收**：
```bat
git grep -n -I -E "Users[\\/][A-Za-z0-9._-]{2,}" -- .        :: 期望 0
git grep -n -I -E "_player_anon|_player_anon2|<other-machine>"   -- .        :: 期望 0
python -c "import json,glob;[json.load(open(f,encoding='utf8')) for f in glob.glob('tools/human_match_sessions/*.json')]"
```
并对比 `len(new_reps)` 改前后一致（写进提交信息）。

**回滚**：`git checkout -- tools/human_match_sessions tools/human_solo_report.json config.py`

---

### Phase 2 门禁回绿（≈0.5 人日）— 归属：施工

> 这是**当前唯一"红线级"阻塞**：红线 #3 要求 0 FAIL。

**2.1 两个测试改标准头（不要用 expandvars）**
`tests/test_gpu_equiv.py:14`、`tests/test_guard_height.py:18` 现为
`sys.path.insert(0, r'%USERPROFILE%\...')`（空操作）。改成仓库其余 87 个测试的同款：

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

理由：不依赖 cwd / PYTHONPATH / 机器路径；沙箱内同样成立（本机解释器是 embeddable
发行版，`safe_path=True`，既不加脚本目录也不吃 `PYTHONPATH`）。

**2.2 Python 默认路径收口到 `kit_config` 单一事实源**（活文件 6 个工具 + 3 个模块）
- 新增 `kit_config.expand(p)`（`os.path.expandvars` 封装）与 `kit_config.repo_path(*parts)`；
- 改：`tools/{cleista_ingest,combo_mine_positional,fangyu_extract,fangyu_index,mine_air_moves,mine_input_moves}.py`、
  `oracle_batch2.py`、`run_parallel.py`；
- **`bc_build.py:484` 分片 glob 改 repo 相对**：`data/oracle_v2/shards`（实测库内 **1724** 片）
  与 `data/oracle/shards`（191 片），保留 `TH123_ORACLE_SHARDS` 环境变量覆盖。
  当前字面量 glob 实测 = **0**，展开 = 1724 —— 这是"下次重建静默产空库"的直接入口。

**2.3 防复发断言（结构防线，本项目惯例）**
- `tools/contract_check.py` 加一条：活文件（排除 `_archive/`、`tools/quarantine/`）内
  `%USERPROFILE%` 计数 == 0；
- `tools/gate_selftest.py` 登记对应变异（把 `expandvars` 去掉 → 断言必须红），
  否则新断言本身没有变异钉。

**2.4 运行产物 `tools/*.json`（6 个含旧路径）**
`ab_verdict_a12_*`×3、`eval_matrix_quick_*`×3：建议**删除并补 `.gitignore` 白名单**
（它们是运行产物，含 `%USERPROFILE%` 与时间戳，长期只会继续漂移）。

**验收**：
```bat
D:\temp\pyenv\python.exe -X utf8 tools\contract_check.py   :: 期望 0 FAIL（原始末行入提交信息）
D:\temp\pyenv\python.exe -X utf8 tests\test_gpu_equiv.py
D:\temp\pyenv\python.exe -X utf8 tests\test_guard_height.py
git grep -n -I "%USERPROFILE%" -- . | findstr /v "_archive"
python -c "import bc_build,sys;sys.path.insert(0,'.');print(bc_build.__file__)"  :: 分片探测 dry-run = 1724
```
**风险**：默认路径改动可能影响本机三 worktree → 用 `TH123_*` 覆盖并实跑
`--help` 级冒烟（`train_tm` / `human_match_v2` / `eval_matrix` / `deck_matchup`）。

---

### Phase 3 复现性声明与依赖（≈0.25 人日）— 归属：施工（文档走队列）

1. **`soku_arch`（D2=A）**：vendor 进仓库 `soku_arch/`，加许可证头；若是第三方则 README 明写"不提供"。
2. **README 三件套**：
   - 「快速开始」加框：**面向维护者本机**（`D:\temp\pyenv` / `D:\touhou\...` / `D:\temp\soku_arch`）；
   - 新增**已知状态**段：门禁实测数字（当前 637/5/2，修复后回填）、外部依赖清单、明确"不可复现项"；
   - 明确「仅本地离线研究，不用于联机对战」。
3. **`.bat` 统一回落**：实测 9 个 bat 中 **8 个已有** `if not exist "%PY%" set PY=python`，
   仅 **`流派实测.bat`** 缺，补齐即可。
4. `requirements.txt` 补一行"非 pip 依赖见 README 已知状态"。

**验收**：`git clone` 到 **不同路径**（如 `D:\temp\clone_test`），按 README 走一遍，
把实际失败项写进"已知不可复现"清单（**写失败也是合格交付**，不许留空）。

---

### Phase 4 许可与第三方来源（≈0.25 人日）— 归属：规划（正文）

1. 新增 `docs/THIRD_PARTY.md`：逐项 `来源 / 许可 / 我们加工到什么程度`。
   - **SokuLib `src/Action.hpp`**（`docs/soku_action_ids.md` 的来源）：**许可证待核**
     ——必须确认能否以 CC-BY-4.0 再分发该枚举表；不能则改为"版权归 SokuLib，按其许可引用"。
   - cleista（`llms.txt`：仅 API、限速、署名）；wikiwiki；CHM 攻略（仅引用结论）。
2. `docs/LICENSE-docs.md` 加限定句："CC-BY-4.0 仅覆盖本仓库原创整理部分；第三方内容版权归原作者。"
3. 用 `git grep -nE "cleista|wikiwiki|SokuLib|SokuAI|CHM"` 反查，确保表无遗漏。

**验收**：反查命中项逐一在表内有对应行；`docs/THIRD_PARTY.md` 出现在 `docs/INDEX.md`（走队列）。

---

### Phase 5 一次性历史重写（仅 D1=A；1–2 小时）— 归属：施工（高风险）

> **必须在 Phase 1/2 内容提交之后执行**，保证只重写一次。

```bat
:: 1) 规则文件（注意误伤）
::   <other-machine>\Users            → %USERPROFILE%   （单反斜杠）
::   <other-machine>\Users          → %USERPROFILE%   （JSON 双反斜杠）
::   <other-machine>/Users            → %USERPROFILE%
::   /c/<other-machine>/Users            → %USERPROFILE%
::   __player_anon(     → _player_anon(    （带前缀，避免误伤普通词）
::   _player_anon2(                  → _player_anon2(   （带前缀+括号，避免误伤正文里的“_player_anon2”）
git filter-repo --replace-text rules.txt --force
::   D3=A 时追加： --path _archive --invert-paths
```

**副作用清单（逐条走一遍）**：
1. 全部 commit 哈希变化 → 对照臂锚 `46920e9` 失锚，**按树哈希重钉**（不是按提交哈希）；
2. `main` + `planning` 双分支 `force-push`（`--force-with-lease`）；
3. 3 个 worktree（`D:\temp\th123_rl_control` / `_planning` / 主检出）全部重置；
4. GitHub 侧旧哈希缓存（新仓库无 PR 历史，影响≈0）。

**验收**（三重）：
```bat
:: ① 全历史复扫（不是只看 HEAD）
git rev-list --all | %% { git grep -I -E "Users[\\/]|_player_anon|_player_anon2\(" $_ 2>nul }
:: ② 计数=0；③ 控制臂重钉后跑一次身份校验（比对树哈希）
git log --all --format="%H" -- fleet_supervisor.py
```
**回滚**：`D:\temp\repo-mirror-20261017` 整仓还原 + 远端再 force-push。

---

### Phase 6 切 public + 事后核验（5 分钟）— 用户手动

沿用主方案 §③ runbook，**加两件**：
1. 切换**前**：GitHub 侧匿名视角抽查（隐身窗口开 raw 链接，确认无 PII 渲染）；`gh api` 抽查 3 个关键文件。
2. 切换**后 24h**：`site:github.com ldw079/th123_rl <玩家名>` 搜索是否被索引；fork 数异常增长；Issues 首批提问。

---

## 4. 总验收清单（切 public 的硬门）

- [ ] 门禁 **0 FAIL**（提交信息附原始末行 + mtime）
- [ ] tracked 内：`Users[\\/]` / 第三方昵称 / `today` / `96120` 均 **0**
- [ ] 全历史（`main` + `planning`，不含 backup）同款 **0**
- [ ] `git ls-files | grep -E "\.(npz|rep|dll|exe|zip)$"` 仅白名单（D3=A 后应为 **0**）
- [ ] README 三要素（访客须知 / 已知状态 / 仅本地研究）+ 维护者框
- [ ] `docs/THIRD_PARTY.md` 在位且被 INDEX 登记
- [ ] 异路径 `git clone` 冒烟做过，失败项已写入"已知不可复现"
- [ ] 主方案 v3 的两处结论已更正（§1 两条）

---

## 5. 排期与归属

| Phase | 内容 | 人日 | 归属 | 可否并行 |
|---|---|---|---|---|
| 0 | 备份/镜像/基线 | 0.05 | 施工 | — |
| 1 | PII 脱敏（含写者改 basename） | 0.5 | 施工 | 与 2 可并行（不同文件） |
| 2 | 门禁回绿 + expandvars 收口 + 防复发断言 | 0.5 | 施工 | 同上 |
| 3 | 复现性（vendor/README/bat） | 0.25 | 施工（文档走队列） | 与 4 并行 |
| 4 | 许可与来源表 | 0.25 | 规划 | 与 3 并行 |
| 5 | 一次性历史重写 + 三 worktree 重置 | 0.2 | 施工（高风险窗口） | **串行**（须在 1/2 之后） |
| 6 | 切 public + 事后核验 | 0.05 | 用户手动 | 串行 |
| **合计** | | **≈1.8 人日** | | |

对比主方案 v3 的"仅剩 5 分钟 runbook"——**这是本轮审计对排期最直接的修正**。

---

## 6. 与主方案 v3 的差异（回填清单，走 `docs/_pending_entries.md`）

1. v3「无 PII」→ 更正为「`96120` 已清；**另有一台机器用户名 6 处 + 第三方昵称 37 处**在
   tracked 且已在 `main` 历史」。
2. v3「切 public 前仅剩 §③ runbook」→ 更正为「尚需 **PR-6 PII 二次清除+重写** /
   **PR-7 门禁回绿+expandvars 收口** / **PR-8 复现性与许可**」三批。
3. 队列条目 6 的范围低估：写的是「~10 py 工具 + 2 tests」，实测**活文件 25 / 36 处**
   （含门禁 2 测试、`bc_build.py`、`oracle_batch2.py`、`run_parallel.py` 与 6 个 `tools/*.json` 产物）。
4. 新增教训入册建议：**"脱敏规则必须按'类别'扩展，不能只按'已知字符串'扩展"**
   ——本轮 `96120` 清了，`today`/玩家昵称没进规则；与 R12「无成功前提校验的测量不可信」同源。

---

## 7. 三个"不要"

1. **不要**先重写历史再改内容（会重写两次）。
2. **不要**用裸 sed 全量替换 `%USERPROFILE%`：多数活文件应改**仓库相对路径**或走
   `kit_config`，只有少数"用户家目录输入档"才该 `expandvars`。
3. **不要**在窗口内跑 `tools/train_start.py`（会连带杀掉对照臂，且当前对照臂已停机待恢复，
   恢复动作要与本方案错开，否则 A/B 记账更乱）。

---

## 8. 在途改动对照（2026-10-17 20:05 观测；工作树已非基线 21bfcdb）

> 审计进行中，构造会话已开始按同一批结论施工。以下为**只读观测**（未干预、未修改），
> 供规划/施工对齐，避免重复或漏项。

| 在途改动 | 状态 | 与本方案的差异 |
|---|---|---|
| `fleet_supervisor.py:480` CPU 看门狗移出 `_exhausted` 守卫 | ✅ 方向正确（P0-3 死代码那半已修） | **口径那半未修**：`cpu_load_pct()` 仍取整机 `LoadPercentage`。见下方 ⚠ |
| `tests/test_{gpu_equiv,guard_height}.py` 改 `os.path.expandvars(...)` | ⚠ **只修本机** | 本方案 2.1 要求改**仓库相对头**（`dirname(dirname(abspath(__file__)))`）。`expandvars` 展开后仍钉死 `…\Desktop\workplace\th123_rl`，**访客克隆到别处照样 import 失败** |
| `bc_build.py:484/492` 分片 glob 与 out_dir 改 `expandvars` | ⚠ **只修本机** | 应改 `os.path.join(ROOT,'data','oracle_v2','shards')`（库内实测 1724 片）+ `TH123_ORACLE_SHARDS` 覆盖；`bc_build.py:27` 仍硬编码 `D:\temp\soku_arch`（D2 未决） |
| `tools/{cleista_ingest,combo_mine_positional,fangyu_extract,fangyu_index}.py` | ⚠ 同类（expandvars） | 同上；另 `mine_air_moves/mine_input_moves` 本轮未见改动（仍在列） |
| `tools/_fix_userprofile.py`（新增未跟踪） | 施工临时工具 | 若最终入库请放 `tools/` 并登记；否则按"探针不留残档"删除 |

**⚠ 最高优先的连带风险（下一次 fleet 重启即生效）**：
看门狗现在**活了**，但度量仍是**整机负载**。审计实测同一时刻：整机 **100%**，而
fleet 全家仅占 **30.4 CPU-s/10s ≈ 18 核的 17%**（其余是 ZCode 会话与 6 worker 变异 sweep）。
→ 下次重启后，6 个连续采样（3 分钟）均值 >75% 即会**暂停最新 actor**；而恢复线
（均值<65% 连续两满窗）在旁路负载不退的情况下**永不满足** → 复现 10-14 的
"降容↔恢复"震荡（当次 32 分钟 8 次往返、并触发过全灭告警）。

**修法（与本方案 Phase 2 合并做）**：`cpu_load_pct()` 改为
**训练族进程树累计 CPU / 逻辑核数**（supervisor+learner+actor+th123 子树），
或至少加"旁路负载扣除"；并在心跳里记 `last_sample_ts` 以自检"看门狗是否还活着"。

**验收**：构造会话完成后必须重跑门禁并把**原始末行**回填（本报告 P0-1 锚在 21bfcdb；
在途改动可能会让门禁转绿，但"仓库相对头"那条仍未满足）。

**已实测（20:08，只读）**：在途 `expandvars` 改动后
`tests/test_gpu_equiv.py` = **exit 0**、`tests/test_guard_height.py` = **32 PASS / 0 FAIL**
→ 本机门禁预计可转绿；但这**只证明"本机能跑"**，不证明"访客能跑"（路径仍钉死
`%USERPROFILE%\Desktop\workplace\th123_rl`）。


---

*本文件为审计侧交付（自有命名空间）。若规划采纳：正文并入
`docs/_plans/public_release_hardening_plan_2026-10-17.md`（追加 v4 + 修订记录），
本文件保留为证据链。*
