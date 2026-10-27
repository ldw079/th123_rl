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

## 3. 窗脚本（v2，parse OK）
- `D:\temp\bc_deploy_window.ps1`：**先维护锁** → helper `--live --assume-locked` 停 → 备份（4 文件）+ **pre-deploy 全 hash** → 3×
  `--apply --no-dedupe` → `bc_deploy_verify.py`（行数/宽度/meta）→ WMI 重启 → health PASS →
  learner 日志 BC 加载证据 → release；失败：恢复备份 + WMI 重启 + health 复核 + rollback hash 记录。
- 回滚：备份 `bc_backup_deploy_20261027`（4 文件）+ journal 状态核 + WMI 重启 + health；失败升级。

## 4. 待 auditor 列签项
1. 预注册是否符合 R17（单变量/样本门/停止规则/回滚/frozen fixture）；
2. 包 §2/§8 命令可复制、路径实际、sha256 完整；
3. 窗脚本顺序/回滚是否覆盖失败路径；
4. 部署后 24h 指标采集与独立复算安排；
5. 通过后 Lead 批 → 10-27 10:30 窗。


## 5. 16:26 失败/修复/重试（更新）
- 失败：`os.replace` staging 被占用 PermissionError WinError 32（16:26 与 18:30 两次）；**真根因=merge 自身 `mmap_mode` 持有生产 X/S/Y**；已回滚+WMI 重启 health PASS，停机各约 5min。
- 修复：merge `_replace_retry` 10×2s；窗脚本停后等 5s+读者检查 abort；`test_bc_replace_retry` 2/2；门禁 **749/0/0**。
- 数据未变：trio 行数/宽/X/S/Y/meta hash == pre；journal rolled_back；staging 清。
- 重试：**2026-10-26 19:30**（19:20 前列签）；replace 失败时 copy fallback；流程/回滚不变。

## 6. copy fallback 安全（19:00）
- replace 失败→`_copy_retry` copy 覆盖生产；每个文件 copy 后 sha256(staging)==sha256(生产) 校验；不一致→回滚；journal 记 fallback+hash。
- 256MB 模拟占用释放测试 PASS；失败 finally 恢复备份+WMI 重启+health；门禁 **749/0/0**（19:02 `gate_bc_retry3.txt`）。

## 7. 20:30 前证据（20:00）
- gate **749/0/0**（gate_bc_retry4.txt，19:59）；retry **30×2s**；copy fallback **禁用**。
- **65s 持有测试 PASS**：30×2s 耗尽 60.1s 抛错、目标 hash 不变（无部分写）；30s 持有→30.0s 成功；`bc_lock65_evidence.txt`。
- 60s 测试不入 C15 原因：close 与最后重试同刻竞态假红；独立脚本 65s 错开为强证据。
- 数据未变：trio 行/宽/hash=pre；20:30 重试，流程/回滚不变。

## 8. gen2 提前构建证据（2026-10-27 09:03）
- D:\temp\bc_gen2_20261027：reimu 429579/S831、marisa 353791/S866、suika 329422/S846；c_gen_verify **PASS**；C1 manifest 三份；ind_bank env 指向 gen2；D 38.72GB；生产未动。
- 12:50 前交 auditor 列签；13:00+ 窗内仅切 TH123_BC_DIR+WMI+health（≤10min）。

## 9. reader/回滚演练（2026-10-27 10:24，c_pointer_drill.ps1）
- 演练日志 D:\temp\bc_pointer_drill_20261027.log：
  - 停 main/control/watcher 后 **readers=0**（断言 PASS）；
  - fake TH123_BC_DIR 写入 bat → 恢复备份，**bat sha256 前后相等**（D7DA3700…）；
  - WMI 重启 main+control+watcher → **health PASS**（sup1/3L/3A/ctl2/games4）；
  - 锁释放；**训练已恢复**。
- 结论：窗内 readers 断言/失败回滚（bat+WMI+health）可执行，有日志证据。
- 门禁 **753/0/0**；gen2 verify PASS；TH123_BC_DIR 严格（禁静默 fallback）测试 4/4。
