# BC 锚 v3 部署包登记（2026-10-26；Lead 裁定版；12:00 auditor 最终）

> 数据：`D:\temp\th123_anchor\bc_anchor3_*.npz`（topup 最终版）。**未部署**；10-27 10:30 部署待批。
> Lead 裁定：same-X 多 Y **保留并登记，不强删**；X 去重照常；manifest 记录冲突样本与理由。

## 1. 数据与校验
| char | npz | rows | 生产+锚 | 宽 X/S | 泄漏行 | 严格combo | 盲放 | 留出 | 冲突组 | 缺行宏 | 低配额 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| reimu | `bc_anchor3_reimu_20261026_003321.npz` | 168 | 429411+168 | 14400x831 | 0 | 100% | 见 QC | 见 QC | 25 | 原子·空链、择·投、压起身·空、压起身·穿 | 原子·确认5A:4 |
| marisa | `bc_anchor3_marisa_20261026_003459.npz` | 169 | 353622+169 | 14400x866 | 0 | 100% | 见 QC | 见 QC | 24 | 原子·确认5A、择·投、压起身·穿 | 原子·空链:1 |
| suika | `bc_anchor3_suika_20261026_003624.npz` | 172 | 329250+172 | 14400x846 | 0 | 100% | 见 QC | 见 QC | 24 | 原子·确认5A、压起身·穿 | TM·空连终结:2、原子·空链:1 |

## 2. manifest（hash/命令）
| char | manifest | X hash | S hash | Y hash | gen_cmd | verify_cmd |
|---|---|---|---|---|---|---|
| reimu | `manifest3_reimu_20261026_003321.json` | 344a8340d5f4386f | 0f1f073b35727d86 | cdd9cce982119eae | `python tools/bc_anchor_collect.py --chars reimu --seeds N` | `python tools/bc_anchor_verify.py --char reimu --npz <npz>` |
| marisa | `manifest3_marisa_20261026_003459.json` | c51102f570a113d6 | a389cf2a3643351e | 78e540e41f302f67 | `python tools/bc_anchor_collect.py --chars marisa --seeds N` | `python tools/bc_anchor_verify.py --char marisa --npz <npz>` |
| suika | `manifest3_suika_20261026_003624.json` | 6ec8e9800b396889 | bab98aa4e60ba738 | a61256965c9e68d1 | `python tools/bc_anchor_collect.py --chars suika --seeds N` | `python tools/bc_anchor_verify.py --char suika --npz <npz>` |

## 3. same-X 多 Y 冲突登记
- **策略：保留+登记**（Lead 裁定）；X 去重仅合并阶段对生产 X 去做重。
- 冲突报告：`D:\temp\th123_anchor\conflicts_report_20261026.json`（组数 reimu 25 / marisa 24 / suika 24；行级计数 120/128/115 为旧口径）。
- 每 char 前 5 组样本见报告 JSON `conflict_sample`；manifest 保留 provenance。

## 4. 部署流程（10-27 10:30；待批）
1. 备份硬链 `bc_backup_anchor_<char>_<ts>`；
2. `python tools/bc_anchor_merge.py --char X --anchor <npz3> --apply`（生产 X 去重/原子/journal/校验/失败回滚）；
3. `bc_io` 强校验（hash cache 关）+ 行数/宽度/标签；
4. 重启 learner（mmap BC）→ 验收 coverage/选择率/KL/ent/4 游戏；
5. 失败：journal 回滚 + 单次重启。

## 5. dry-run 证据
- reimu 429411+168=429579（S831）；marisa 353622+169=353791（S866）；suika 329250+172=329422（S846）；宽度/Y 校验通过（`bc_anchor_v3_merge_dryrun.txt`）。
