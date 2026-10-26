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
