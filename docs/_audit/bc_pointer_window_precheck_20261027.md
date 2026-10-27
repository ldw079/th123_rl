# BC 指针窗 09:45 预检查/回滚清单（2026-10-27 晚准备）

> 09:45 窗前列签用；不写 bat/不停训的 env 演练已完成（`tools/bc_env_rehearsal.py`）。

## 1. 数据/证据（已 PASS）
- gen2 `D:\temp\bc_gen2_20261027`：reimu **429579/S831**、marisa **353791/S866**、suika **329422/S846**（=生产+509）。
- meta hashes **16hex** + `_I.npy`；C1 manifest 三份（rows/width/hash/parent/status/files）。
- **真实 loader**：`bc_io.load_bank`/`load_bank_seq` 三 char **PASS**（`bc_gen_verify --dir` VERIFY PASS）。
- **env 全流程演练**：gen2 PASS → fake env 严格拒绝（无静默 fallback）→ 恢复 gen2 PASS；`D:\temp\bc_env_rehearsal_20261027.json`。
- 生产 trio 未动；回滚备份 `bc_backup_deploy_20261027` 保留（成功后再清）。
- 门禁 **757/0/0**（本晚新测试登记后）。

## 2. 窗前预哈希（09:35 执行）
```bat
D:\temp\pyenv\python.exe -X utf8 tools\bc_gen_verify.py --dir D:\temp\bc_gen2_20261027
D:\temp\pyenv\python.exe -X utf8 -c "import sys;sys.path.insert(0,'.');import bc_io;print(bc_io.load_bank('reimu',dirs=[r'D:\temp\bc_gen2_20261027'],verify=True)[2].shape)"
```
记录：三 char 行/宽、`gen_manifest_gen2_*.json` sha256、`D` 余量、health。

## 3. 窗命令（≤10min）
1. `tools/fleet_lock.py --acquire bc-pointer ...`
2. `python tools/train_stop_clean.py --live --assume-locked --reason 'BC gen2 pointer 09:45'` → readers=0 断言
3. `bc_gen_verify --dir gen2`
4. bat 在 `train_start.py` **行前**插入 `set TH123_BC_DIR=D:\temp\bc_gen2_20261027`
5. WMI 重启 main+control+watcher → health PASS（等待 120×5s）
6. 证据：`TH123_BC_DIR` 行、`bc_io.find_bank`/loader 日志、PID/停机账；release 锁

## 4. 失败回滚（立即）
```bat
copy /Y D:\temp\train_batch_launch.bat.bc_pointer_backup D:\temp\train_batch_launch.bat
rem WMI 重启 main+control+watcher; health PASS
```
- 若 learner 仍 crash：确认 bat 无 `TH123_BC_DIR`；`bc_io.verify_trio` 日志；恢复生产 trio 备份（`bc_backup_deploy_20261027`）+重启；记录 incident。
- **不半途**：失败立即回滚，不重试 copy fallback。

## 5. 列签项
- 预注册（09:45/流程/回滚）+本清单 + gate 757 + env 演练/真实 loader 证据 + 生产未动。
