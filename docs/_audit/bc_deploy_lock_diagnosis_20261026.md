# BC 部署失败诊断 + 指针切换评估（2026-10-26 20:45）

> 结论先行（auditor 口径）：**机制已证**——`os.replace` 在 **delete-deny 句柄**存在时 WinError32；
> 但 **`shutil.copyfile` 可成功**；小 store 可复现；mmap 已排除（gc 0）；**持有 PID/句柄/AV 日志未取到 → 疑 AV/索引**。
> 今晚不再开窗；BC 顺延 **UKEMI 后（13:00+）**；修复=安全 copy fallback（sha256 校验+回滚）或指针切换。

## 1. 事实（4 次尝试，全部安全回滚）
| 时间 | 结果 | 停机 | 数据 |
|---|---|---|---|
| 16:26 | WinError32 staging→生产 X；finally 回滚+WMI，16:29:50 health PASS | ~5min | pre 一致 |
| 18:30 | 同上；18:33:08 health PASS | ~5min | pre 一致 |
| 18:40（未列签提前） | 同上；18:45:05 health PASS | ~6min | pre 一致 |
| 20:30 | 30×2s 仍 WinError32；20:35:12 health PASS | ~6min | pre 一致 |

## 2. 诊断证据
- **不是 mmap**：replace 前 `gc.get_objects()` 中指向目标的 `np.memmap`=0；显式 `_mmap.close()` 后仍失败。
- **不是 staging 长期锁**：失败后立即 `Move-Item staging\bc_reimu_X.npy` **成功**（无残留锁）。
- **不是文件不可访问**：replace 前对 staging 与生产 X 均 `os.open(O_RDWR)` **成功**；但 `os.replace` 持续 WinError32
  → 说明存在 **delete-deny 句柄**（允许读写、不允许删除/重命名），常见于 **AV/索引/哈希缓存/搜索**。
- **小 store 可复现**：KB 级 fake trio+anchor 走 `apply_merge` 同样 WinError32（非大文件特有；排除"5.7GB 大小"）。
- **copyfile 可行**：同环境下 `shutil.copyfile(staging→生产)` **成功**（小 store 实测），`_copy_retry` 后进程可继续。
- **真锁超时无部分写**：65s 持有测试 → replace 30×2s 耗尽 60.1s 抛错，目标 hash 不变；30s 持有→30.0s 成功。
- **未能锁定具体 PID/句柄**：本机无 handle.exe/openfiles 权限；psutil 不可用；AV 扫描/隔离日志未取到。
  **口径：机制已证（delete-deny），持有者未定位（疑 AV/索引）；明日窗前后再取证据；不写死根因。**

## 3. 修复方案（二选一，均需 R17 列签）
### A. 安全 copy fallback（已实现）
- replace 30×2s 失败后：逐文件 `shutil.copyfile(staging→生产)`；
- 每文件 copy 后 **sha256(staging)==sha256(生产)**，不一致→抛错→finally 恢复 backup+WMI 重启；
- journal 记 `replace_fallback`/`replace_fallback_hashes`；copy 非原子，但 hash 校验+回滚覆盖风险；
- 小 store 复现 PASS；65s 真锁测试证明 replace 超时无部分写；copy 失败路径（目标不可写）→异常→回滚。
- 风险：copy 中断可能留下半文件；hash 校验在 copy 完成后，若进程崩溃在 copy 中需 rollback（backup 完整）。
### B. 指针切换（auditor 条件可接受）
- 写 `bc_<char>_genN` 完整 trio+meta（不 replace 生产）；切换 loader 指向（junction/`TH123_BC_DIR`）；
- 无 reader+维护锁下原子切换+WMI 重启；失败切回旧指针+重启；
- C1 manifest（gen/width/hash/parent/device/status）+loader 强校验、禁静默 fallback；
- 等价校验 new=old+509/行宽/Y/hash；回滚演练；**改动更大但彻底绕开 replace 锁**。

## 4. 建议
- **明日 UKEMI 后先试 A**（已实现+小 store/65s/256MB 证据），若仍失败→改 B；
- 若用户可加 **AV 排除目录**（`D:\temp\th123_models` 及 staging 目录），可恢复干净 replace 路径（优先治本）。
- 新窗预注册：`window_bc_anchor_deploy_20261027_prereg.md` §10（copy fallback/回滚/24h 监控）。
