# 审计：R197/W1 收尾独立复核（钉 HEAD `edbc843`）

> **基线**：HEAD `edbc843`（= R197 `a6dcbf0` + 规划文档 4 提交 ff 合并；`git diff --stat a6dcbf0..HEAD`
> 仅 `docs/INDEX.md` + 编排图/CPU-H 方案 3 文档，生产内容不变）。审计时刻 2026-10-18 12:17–12:22。
> 门禁工件：`D:\temp\gate_r197_final.txt`（mtime 12:12:51，PASS 行 **668**、`^\s*FAIL` 行 **0**，末行
> `==== 契约门禁: 668 PASS / 0 WARN / 0 FAIL ====`）；`D:\temp\gate_r197_final.exit` = 单字节 `0x30`=**"0"**
> （12:12:52），生成器 `D:\temp\run_gate_r197_final.py` 以 `subprocess.run(...).returncode` 落盘 →
> **exit=0 已证（非仅提交声称）**。HEAD 实测：`gate_selftest.MUTATIONS`=**206**、`tests/test_*.py`=**92**。
> 工作树 12:18 采样非干净（`M tools/gate_selftest_parallel.py`、`?? tools/load_gate.py` = W2-1 在途，不属 W1，
> 未审）；本复核一律读 HEAD 对象（`git show HEAD:path`）。

| # | 项 | 判定 | 证据（file:line / 命令+时点） |
|---|---|---|---|
| 1 | **两条自证断言修复** | **通过**（3 点保留） | HEAD `tools/contract_check.py:2262`=`"if _key not in _VERSION_WARNED:" in src(episode_core)`、`:2271`=`"report['model_temp'] = _temps" in src(eval_matrix)`；二者正是 `gate_selftest.py:645-652` 变异旧串的精确命中体（替换后子串消失→断言必红；静态模拟 `D:\temp\verify_mut_r197.py` 输出 mutant-cond-absent=True / loose-old-cond-still-true=True）。行为证据 `D:\temp\sweep_selftag_r197.out.log`（11:17:22→11:32:20）：基线绿 ✓(exit=0)、2 条变异均 ✓红(exit=1 632s/641s)、末行「2红/0漏网/0未判定, 墙钟11min」，与耗时不矛盾（约 898s−641s≈基线 257s）。保留：①日志未记 `SELFTEST_TAGS` 原文/被测树哈希，"被测树=HEAD"只能由 43min 后 R197 diff 推定；②"红因=目标断言"未留存该次门禁 FAIL 行（静态上仅该两断言引用被删串、无测试兜底该两串，推断成立）；③"exit=1"是单变异门禁退出码，sweep 总退出码未落盘。**漏洞判断**：这两条不再被"串存在"绕过；但其他断言同类自证未系统扫描（审计#6 仅抽验），且 204 条变异仍未测（B1 夜间窗）=已知残余 |
| 2 | **入口数字** | **通过**（1 点保留） | AGENTS:61 / README:52 = `668 PASS/0 WARN/0 FAIL`、变异 206、测试 92；HANDOVER 旧数 643/5/0、658、f7e5d65 实测已无（`git show HEAD:HANDOVER.md` grep）；三方与 gate PASS=668/FAIL=0、HEAD MUTATIONS=206、HEAD tests=92 一致。保留：HANDOVER 顶部仍写 `HEAD=4e13aa5`（R197 后应为 a6dcbf0 / 现 edbc843），快照 HEAD 行过期（docs-only，低危） |
| 3 | **README 复现声明** | **通过** | HEAD README「可复现项」已改：明确 `data/` 全域不入库（`git ls-files data/`=0、`.gitignore:5`）、直读 `data/guide_tables/*.json` 的断言（`contract_check.py:2282`、`tests/test_fangyu_counters_le2.py:15-27`）干净 clone 会 FAIL、"复现验证方式"须放入本地 `data/` → 与实况自洽，无新失实 |
| 4 | **METHODOLOGY 3.65** | **通过**（2 点保留） | HEAD `METHODOLOGY.md:11` 版本头=3.65·R196-197·门禁 668/0/0·变异 206（准确）；3.65 正文（R196 快照入宪 / 审计#6 两条 P1 已清 / R197 修复与 SELFTEST_TAGS 单跑 / 入口数字 / 队列 / R184 证据）与实际改动一致，且自披露 3 个 R184 缺口（bc_accept 不验哈希、无 C 哈希、备份缺 `_I.npy`）与实测一致。保留：①"白天 20 条试跑 **4/20** 全红"与 `sweep_r197.out.log` 实见 **6/20 ✓红**不符；②"11:37 开跑" vs `sweep_r197.err.log` 创建 **11:33:21**（差 4min）；③"沙箱已清 7.05GB/1301 文件"未留日志（当前 `gate_sandbox` 0 文件、D 61.5GB 与清理结果自洽，过程数字未证实） |
| 5 | **队列消费** | **通过**（1 点保留） | HEAD `docs/_pending_entries.md`：仅余 R4 wiki 语义表（挂起待用户裁定，正确）+ 消费记录；`_archive` 关闭理由（R192 `--invert-paths`，历史 5→0 提交已复核）与 bc_accept INDEX 登记（`docs/INDEX.md:25`）成立。保留：THIRD_PARTY 关闭引 `INDEX.md:25`（实为 `bc_accept` 行），THIRD_PARTY 登记实为 **INDEX:35** → 引用行号错/混项（结论仍成立；HANDOVER/METHODOLOGY 3.65 同错扩散） |
| 6 | **R184 验收归档** | **通过** | 只读文件/meta 未重跑：trio meta rows 429411/353622/329250、seq_aware=true、hashes 键 X/S/Y/I 齐、S 宽 798/833/813（Y/I sha256 审计#6 已独立复算等）；`accept_v3_all.json` 05:08:42 与 `accept_store.json` 05:12:20 双跑 `all_ok:true`（11:10 R197 复跑亦 all_ok）；备份 `pre_v3_backup` 15 档/18.22GB + `bc_store_backup_20261018` 12 档/18.22GB；`pre_v3_backup` Y 反算 429411/349922/328116 与记载一致；情境库索引 05:17-05:18 重建（晚于换装 05:12） |
| 7 | **R197 提交树** | **通过** | `git show a6dcbf0 --numstat` = **7 文件**（AGENTS/HANDOVER/METHODOLOGY/README/_pending_entries/audit#6 报告 + `tools/contract_check.py`），+**215**/−**64** 与声明一致；生产代码仅 contract_check.py（9+/2−，断言收紧），无 data/model/其他 py 夹带；`gate_selftest*.py` 未改（两条变异为既有）。HEAD `edbc843`=a6dcbf0+4 规划文档提交，生产内容不变。`gate_r197_final` exit=0 **已证**（见基线） |

## 对 W1 关闭的意见

**W1 关闭成立。** 唯一阻塞项（两条自证断言）已真修：断言条件精确对齐既有变异锚、2/2 变异红
（0 漏网/0 未判定）、门禁 exit=0 **已证**、668/0/0 与入口数字三方一致；README 复现声明、队列、
R184 验收归档与实况一致。保留 3 项均非阻断（docs-only）：HANDOVER 快照 HEAD 行过期（4e13aa5→edbc843）、
THIRD_PARTY 关闭引 INDEX 行号错（25↔35）、METHODOLOGY 白天试跑数字与日志不合（4 vs 6 条 / 11:37 vs 11:33），
建议 W2 文档批顺带更正。另注：B1 夜间窗的增量 20 条+全量 206 条仍为已知未完成；`bcw=0.00`（活 trio 换代
当前对策略梯度无直接作用）已由 METHODOLOGY 3.65 自披露，属 W2 用户裁定项，不影响 W1 关闭。

**局限**：未重跑门禁/变异 sweep；历史时点 CPU/沙箱清理过程数字不可复现（以现有日志/工件为准）；
门禁工件生成于提交前 3min，"所跑树=HEAD 内容"按提交 diff 推定而非哈希留证。
