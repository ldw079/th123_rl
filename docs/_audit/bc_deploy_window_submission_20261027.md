# BC 部署窗提交包（2026-10-27 10:30；R17 预注册+窗脚本证据）

> 供 auditor 列签（`bc_deploy_window_audit_20261027.md` 10:20 前）。
> 依据：R17；Lead 11:56 批准（12:00 审计 PASS）。

## 1. 预注册
- `docs/_plans/window_bc_anchor_deploy_20261027_prereg.md`
- 假设：补锚标签→低频连段/压制/择宏选择率↑，KL/ent/空挥不退化。
- 单变量：BC trio 行数（+168/+169/+172=509，`--apply --no-dedupe`）。
- 指标/样本门/停止规则/回滚/DoD/独立复算：见预注册。

## 2. 部署包
- `docs/_audit/bc_anchor_deploy_package_20261026.md`（§1 完整 sha256、§2/§8 实际命令、
  §3 被否决去重、§8 A 裁定、§5 冲突口径、§6 缺行/低配额）。
- 数据：`D:\temp\th123_anchor\bc_anchor3_{reimu,marisa,suika}_*.npz`（509 行）。
- dry-run：`D:\temp\th123_anchor\bc_anchor_v3_merge_dryrun_nodeplace.txt`（dedupe:false，merged 429579/353791/329422）。

## 3. 窗脚本
- `D:\temp\bc_deploy_window.ps1`（parse 待验）：helper `--live` 停 → 维护锁 → 备份硬链 → 3×
  `--apply --no-dedupe` → `bc_deploy_verify.py`（行数/宽度/meta）→ WMI 重启 → health PASS →
  learner 日志 BC 加载证据 → release；失败恢复备份。
- 回滚：备份 `bc_backup_deploy_20261027` + 单次 WMI 重启。

## 4. 待 auditor 列签项
1. 预注册是否符合 R17（单变量/样本门/停止规则/回滚/frozen fixture）；
2. 包 §2/§8 命令可复制、路径实际、sha256 完整；
3. 窗脚本顺序/回滚是否覆盖失败路径；
4. 部署后 24h 指标采集与独立复算安排；
5. 通过后 Lead 批 → 10-27 10:30 窗。
