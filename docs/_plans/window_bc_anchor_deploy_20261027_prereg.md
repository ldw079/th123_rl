# 窗口预注册（R17-1）：2026-10-27 10:30 BC 锚 v3 部署（data-only，≤15min）

> 依据：R17；Lead 11:56 批准（12:00 审计 PASS）；数据-only 单变量；维护锁/WMI/helper；冻结夹具。
> 数据包：`docs/_audit/bc_anchor_deploy_package_20261026.md`（裁定 A）。

## 窗名/日期/责任人
- 窗名：BC anchor v3 部署（+509 行，`--no-dedupe`）
- 日期：**2026-10-27 10:30**，≤15min（含重启与验证）
- 责任人：construction（执行）；auditor（独立复算/抽查）；Lead（批准）

## 假设（可证伪）
- H1：补锚行（低频连段/压制/择宏标签）使这些宏的**选择率↑**、BH combo 完成/命中↑，
  且 KL/ent/空挥不退化。
- 证伪：24h 后目标宏选择率未升或 KL/ent 恶化 → 回滚。

## 单变量
- 仅 BC trio 行数（+168/+169/+172=509；`--apply --no-dedupe`）；不动模型/env/代码/宏。

## 指标（预注册）
| 指标 | 定义 | 样本门 | 门限 |
|---|---|---|---|
| 目标宏选择率 | 连段/压起身/择/原子 等 target 宏决策/总决策 | ≥3000 决策/char | ↑（相对窗前后 24h 同夹具） |
| BH combo | combo hit / complete / dropped | ≥10 次/char 事件 | hit/complete↑、dropped 不升 |
| BC aux（锚留出集） | heldout 标签命中/损失 | 留出集 | 命中↑、损失不升 |
| 空挥/被确反 | 奖励成分/帧 | 窗前后 | 不恶化 |
| KL/ent | learner 日志均值 | 每批 | KL≤0.30、ent 不退化 |
| 健康 | 4 游戏/3 learner/3 actor/control/watcher、hb | 实时 | 缺员=停窗 |

## 冻结夹具
- 角色 reimu/marisa/suika；对手池版本/种子/局面集与窗起记录（baseline JSON+hash）；
- 评估脚本版本 + 窗前后各 ≥60min（24h 观察）；作废段：重启/锁期间。

## 停止规则 / 回滚
- 加载失败/行数不等（429579/353791/329422）/宽度≠831/866/846/哈希不符/hb 停更/缺员/
  crash → **立即 journal 回滚**（硬链备份）+ WMI 单次重启；KL>0.5 或 ent<0.6 持续 10min→回滚。
- 异常回滚后写 incident/decision log；不二次迁移。

## 执行（WMI/维护锁/helper）
1. helper `--live` 优雅停 main+control+watcher（先锁、停机账、标记）；
2. 窗脚本 acquire 维护锁 → 备份 trio 硬链+hash；
3. `bc_anchor_merge.py --char X --anchor <npz3> --apply --no-dedupe` ×3；
4. 校验行数/宽度/hash/bc_io 加载；门禁 748/0/0；
5. WMI 重启 main+control+watcher → health PASS → learner 日志 `专家库 … 行 (S宽✓)`；
6. 记录停机账/时间；release 锁；auditor 复核。

## DoD（可量化）
- 行数/宽度/hash/门禁/health 全 PASS；
- 部署后 24h 指标表完整记录并判定（保留/回滚，有证据）；
- auditor 独立复算窗前后数据（不采用施工自报聚合）；回滚演练可执行记录。


## 8. 首次尝试失败与重试（2026-10-26 16:26；R17 记录）
- **失败**：16:26:40 与 18:30:08 两次均 `os.replace` staging → 生产 `bc_<char>_X.npy` 报
  **PermissionError [WinError 32]**。**真根因（18:33 定位）**：`load_trio` 用 `np.load(..., mmap_mode='r')`
  打开生产 X/S/Y，merge 进程**自身持有的 mmap** 未释放就 `os.replace` 目标 → Windows 拒绝替换。
  merge 失败→finally 回滚+WMI 重启（16:29:50 / 18:33:08 health PASS，停机各约 5min）。
- **修复（第二轮，真正修复）**：`apply_merge` 在 replace 前 `X=S=Y=None; gc.collect()` 释放 mmap；
  `_replace_retry` 10×2s 保留（防其它占用）；回归测试 `mmap 释放后 replace 成功` 3/3 PASS
  （证明 mmap 未释放时 WinError 32、释放后成功）；窗脚本停后 5s+读者检查保留。
- **修复**：①`tools/bc_anchor_merge.py` 新增 `_replace_retry`（10×2s 退避，仍失败→抛错走回滚）；
  ②窗脚本 helper 停后 **等 5s + 确认无 main/control/watcher/health 读者**（readers≠0 abort）；
  ③staging 残留已清（保留 deploy 备份供重试）；④`tests/test_bc_replace_retry_v1.py` 2/2 PASS（占用释放→成功/持续占用→抛错）。
- **数据未变（核验）**：生产 trio 行数/宽 = **429411/831、353622/866、329250/846**（=包 §1 预部署值）；
  X/S/Y/meta sha256 与回滚日志 pre 值逐项一致；journal state=rolled_back；未改任何生产 BC 行。
- **重试窗**：18:30/18:40 两次仍失败（大 staging replace）；已加 **copy fallback**；**2026-10-26 19:30 重试**（19:20 前 auditor 列签）；流程同 §7（锁→helper --assume-locked→等 5s/读者→备份+pre hash→apply×3→verify→journal verified→WMI→health→24h 监控）；失败回滚+重启。
- 门禁：**749/0/0**（C15 新增 `test_bc_replace_retry_v1`；gate 文件/时间以最新实测为准）。

- **copy fallback 安全（2026-10-26 19:00 补齐）**：`_copy_retry` 非原子 copy → 每个文件 copy 后 **sha256(staging)==sha256(生产)** 校验；不一致→异常→回滚；journal 记 `replace_fallback` + `replace_fallback_hashes`；256MB 模拟占用释放测试 PASS；失败路径 finally 恢复备份+WMI 重启+health。
- **流程违规记录**：18:39 未列签提前重试（虽安全回滚）已记 decision log；19:30 严格按列签执行。
