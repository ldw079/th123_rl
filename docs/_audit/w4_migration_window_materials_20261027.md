# W4 迁移窗材料（2026-10-27 离线备，非部署）

## 1. 前置
- R17-12 已正式关闭（15:26）；仍须 W4-1..10 AC + auditor 核 + Lead 批，**不自动开窗**。
- 一次迁移合并：slot registry（C=256，旧 id 不变）+ task-71 残差 v1（≤5 段/hold）；task-68 CORE 扩维同窗。
- 不早于 BC 09:45/UKEMI 10:30 之后；与 BC 窗不混。

## 2. 证据（已具备）
- `tools/w4_migrate_dryrun.py` → identity/bitwise PASS（3 char）。
- `tools/w4_migrate_real.py` → **副本模型**扩 256，identity_old_cols/old_logits_bitwise True；**副本已删=回滚演练**；生产模型未动。
- **宏 golden**：`D:\temp\w4_macro_golden_20261027.json`：reimu 88/`908f5799…`、marisa 95/`6b1fe6d9…`、suika 91/`0a80…`（旧 id/name 逐字比对）。
- slot registry 单测 9/9；action_resid 11/11；action_chunk 7/7；strategy_z 5/5（env0 默认）。

## 3. 迁移步骤（窗内，≤10min 目标）
1. 锁 + helper `--assume-locked` 停训（readers=0）+ 备份 models/registry；
2. 副本迁移模型（w4_migrate_real 同逻辑）→ 旧 logits bitwise 校验 → 替换生产；
3. registry 写 models/macro_registry.json（C=256/旧 id 保留/manifest）；
4. WMI 重启 → health/games4/旧行为 identity → 旧宏 golden 比对；
5. 失败回滚：恢复备份模型+registry，WMI 重启，health PASS；记录 incident。

## 4. 未完成（不得称全 AC）
- 真实迁移脚本尚未在**生产**跑（仅副本）；W4-8 吞吐基准、旧模型扩列 bitwise 已验但端到端训练 A/B 未跑；movement golden 仅宏名单，非 replay 帧级。
- 待 W4 窗列签后执行；此前不部署。
