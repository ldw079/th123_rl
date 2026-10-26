# BC 锚 P0 修复材料（task-60 v2；2026-10-25 23:30；未部署，待 auditor 复审）

> 针对 auditor `docs/audit/anchor_audit_20261026.md` P0/P1 的修复说明与证据。
> 数据：`D:\temp\th123_anchor\bc_anchor_<char>_20261025_2222xx.npz`（v3 生成，P0-1 修复后）；
> 生成代码 `tools/bc_anchor_collect.py`（v2）；验证 `tools/bc_anchor_verify.py`。
> **未部署**；15:00 窗已取消，待复审后另排（Lead：17:00 或 10-27）。

## 1. P0-1 标签泄漏（已修复 + 负例）
- 修复：`FeatCtx._side()` 前 2N 宏 one-hot **只写决策前因果历史**（本数据集固定=待机 idle）；
  `capture_row()` 不再传 target；采集时逐行 `assert_no_target_leak(S,n,mid)`：`S[Y]==0 且 S[N+Y]==0`，
  否则 raise（生成中止）。
- 负例测试：`tests/test_bc_anchor_v1.py` 手工把 `S[Y]=1` → `assert_no_target_leak` 抛错（PASS）。
- 重生成后逐行复核（`bc_anchor_verify.py`）：
  | char | rows | **target_leak_rows** |
  |---|---|---|
  | reimu | 137 | **0** |
  | marisa | 132 | **0** |
  | suika | 144 | **0** |
- S 宏槽现只含 idle；不含 Y（审计可逐行验证）。

## 2. P0-2 独立真值（2 来源）
### 2.1 同位置盲复验（主；不经 executor）
- 方法：从 npz `src.seq`（生成时记录的**原始逐帧输入 RLE**）在**新对局同位置**盲放：
  sync → 6 帧 idle lead-in（与生成对齐）→ 按记录输入逐帧执行（右侧恒空）→ 统计 combo_ok
  （dmg≥300 且 ≥2 攻击动作）。**不使用 macro_executor**，故与生成器独立。
- 抽样 60 行/角色（总 180）：
  | char | n | ok | rate |
  |---|---|---|---|
  | reimu | 60 | 56 | **0.933** |
  | marisa | 60 | 58 | **0.967** |
  | suika | 60 | 57 | **0.950** |
  | 合计 | 180 | 171 | **0.950** |
### 2.2 留出小偏移场景（鲁棒性；第二来源）
- 生成时对每行在 **held-out 位置**（mid +12/+5px 等）用同一记录输入盲放，记录 ok；
  采集内一致率：reimu 120/137=0.876、marisa 122/132=0.924、suika 134/145=0.924。
- 判读：位置微扰下部分位移敏感 combo 失效属预期；主证据用同位置盲复验（0.95），
  留出率作鲁棒性/覆盖参考，不作为"生成器自证"。
### 2.3 对比基准
- 手动输入基准（task-58）：A 连打 1510 dmg vs replay 200 dmg → 已证明 combo 在游戏内可完成；
  本轮盲复验进一步证明"记录的原始输入序列可复现 combo"，非 executor 回放自证。

## 3. P1 状态
| 项 | 状态 | 证据/说明 |
|---|---|---|
| P1-1 单宏配额 | **部分** | min: reimu 7、marisa 9、suika 1；缺行宏见 §4；补采计划明日 10:30 后（topup 工具已写） |
| P1-2 same-X 多 Y | **记录** | 冲突数 reimu 101/marisa 107/suika 96；**未强删**（避免清空低配额）；manifest `same_x_conflicts` 记录，留给审计裁定去重策略 |
| P1-3 严格判据宽松 | **已修** | combo_ok=dmg≥300 且 ≥2 攻击动作（非仅 acts≥2）；本次 137/132/144 行 combo_ok=**100%**（0 dmg 行被剔除） |
| P1-4 部署原子性 | **已实现** | `tools/bc_anchor_merge.py` v2：staging 全文+journal 状态机+备份硬链+三文件+meta hash 对账+bc_io 加载校验+失败整体回滚；`--apply` 默认 dry-run；生产 X 逐行去重（apply 时） |
| P1-5 R15 行为测试 | **已补** | `tests/test_bc_anchor_v1.py` 16 项：P0-1 泄漏负例/历史 one-hot/combo_ok 边界/RLE/冲突计数/manifest；C15 登记；盲复验由 verify 工具产出独立证据 |
| manifest 命令/hash/seed | **已补** | generator/gen_cmd/verify_cmd/hashes/seed_base/heldout/conflicts |

## 4. 配额缺口（需补采或审计接受）
- **reimu**（137 行/10 宏）：`空连A` 7（低）；未生成行：`原子·空链`、`择·投`、`压起身·空`（严格判据下无合格 combo）。
- **marisa**（132/9 宏）：`B6C连` 9；未生成：`择·投`。
- **suika**（144/10 宏）：`原子·空链` **1**；未生成：`压起身·穿`。
- 缺口原因：严格 combo_ok 下这些宏在当前场景/时序无合格 combo（非数据丢失）；补采将扩场景
  （wakeup 方向/距离、贴墙、空中起始）并单独记录；若仍无合格行，建议审计接受"该宏无合格锚"并在
  部署包标注，不伪造行。

## 5. 部署计划（复审通过后另一窗口，17:00 或 10-27）
1. audit 复审（本材料+抽检 10-20 行逐帧）；
2. 备份硬链 `bc_backup_anchor_<char>_<ts>`；
3. `python tools/bc_anchor_merge.py --char X --anchor <npz> --apply`（dry-run→apply；X 去重；
   journal/回滚）；
4. `bc_io` 强校验（hash cache off）+ 行数/宽度/标签；
5. 重启 learner（mmap BC）→ 验收 coverage/选择率/KL/ent/4 游戏；
6. 失败：journal 回滚 + 单次重启。

## 6. 最终版（v3，2026-10-26 00:40；topup 后，12:00 前最终材料）

| char | 最终 npz | rows | 盲放抽样(50) | 采集内留出 | 跨Y冲突 | 缺行宏 | 低配额(<5) |
|---|---|---|---|---|---|---|---|
| reimu | `bc_anchor3_reimu_20261026_003321.npz` | 168 | 46/50=0.92 | 145/168=0.863 | 120 | 原子·空链、择·投、压起身·空、压起身·穿 | 原子·确认5A:4 |
| marisa | `bc_anchor3_marisa_20261026_003459.npz` | 169 | 48/50=0.96 | 159/169=0.941 | 128 | 原子·确认5A、择·投、压起身·穿 | 原子·空链:1 |
| suika | `bc_anchor3_suika_20261026_003624.npz` | 172 | 49/50=0.98 | 162/172=0.942 | 115 | 原子·确认5A、压起身·穿 | TM·空连终结:2、原子·空链:1 |

**说明**：
- 严格判据 combo_ok（dmg≥300 且 ≥2 攻击动作）最终 168/169/172 行 = 100%；P0-1 泄漏逐行=0；盲放独立复验合计 **143/150=0.953**。
- 跨 Y 冲突（同 X 不同宏）保留但逐条记录（避免清空低配额）；auditor 若要强去重，可跑 `--drop-cross-y` 变体（会显著减行，不推荐）。
- 缺行宏：严格 combo 判据下当前场景/时序无合格 combo（不伪造行）；建议审计裁定"该宏无合格锚"或后续单独扩场景补采。
- 部署用最终 npz3（见上表）+ `tools/bc_anchor_merge.py --apply`（X 去重/原子/journal/校验）。

**合并 dry-run（最终 npz3，只读）**：
- reimu: 429411+168=429579 行（X14400/S831，Y范围合法）
- marisa: 353622+169=353791（S866）
- suika: 329250+172=329422（S846）
- 三 char 宽度/Y 校验通过；--apply 未执行（待 17:00 窗/复审后）。

## 7. 部署包登记（2026-10-26 10:05；Lead 裁定）
- **缺行宏（target 宏，严格 combo 判据下无合格锚）**：
  - reimu：原子·空链、择·投、压起身·空、压起身·穿
  - marisa：原子·确认5A、择·投、压起身·穿
  - suika：原子·确认5A、压起身·穿
- **低配额（<5 行）**：reimu 原子·确认5A:4；marisa 原子·空链:1；suika TM·空连终结:2、原子·空链:1
- **same-X 多 Y 冲突**：**保留并登记，不强删**（Lead 裁定）；X 去重照常（merge 时生产 X 去重）；
  manifest 记录冲突样本与理由（见 `D:\temp\th123_anchor\conflicts_report_20261026.json`）。
  冲突组数：reimu 25 / marisa 24 / suika 24（按 npz 全表口径 120/128/115 为行级计数差异；
  以报告 JSON 为准）。
- **manifest 完整字段**：generator/gen_cmd/verify_cmd/target_leak_check/hashes(X/S/Y)/
  seed_base/heldout_consistency/conflicts/per_macro（见 `manifest3_*.json`）。
- **部署方式**：`tools/bc_anchor_merge.py --char X --anchor <npz3> --apply`（dry-run 已过：
  429411+168 / 353622+169 / 329250+172；宽 X14400/S831/866/846）。
