# BC 锚 v3 部署包登记（v2 完整版，2026-10-26；12:00 auditor 最终）

> 数据：`D:\temp\th123_anchor\bc_anchor3_*.npz`（topup 最终版）。**未部署**；10-27 10:30 待 12:00 PASS + Lead 批。

## 1. 数据/哈希（完整 sha256 64 hex）
| char | npz | npz sha256 | manifest | manifest sha256 | X sha256 | S sha256 | Y sha256 |
|---|---|---|---|---|---|---|---|
| reimu | `bc_anchor3_reimu_20261026_003321.npz` | `ca72f84e62d9349590af1b2bad0542bb2efe7928e8e23d98422c30decb23dec8` | `manifest3_reimu_20261026_003321.json` | `88685986f98db91e93e797f75dd73dd5e516e01f97710ce088c484e8c0a1a900` | `344a8340d5f4386fc4e37799acfeb2050dc7d5783c208d28fd3c0e06103ed4ad` | `0f1f073b35727d86791551f11037ef124f38ef71fc99064df282ff06ec0cd25b` | `cdd9cce982119eae3254180d132fb0463977ec4ed72ac9665c32d70d39ddb7b2` |
| marisa | `bc_anchor3_marisa_20261026_003459.npz` | `e62e6a8a5786f38827895661f1d8fdbf34c4f3db1efca02a781a4a9699c0b084` | `manifest3_marisa_20261026_003459.json` | `2626bdb2f988f39b178248085f6d38a08818d11c3a44a9465d43e1e8dba522b8` | `c51102f570a113d6354f607a522acc096be52c803e4046ac3fef44a7cb49c566` | `a389cf2a3643351e46b980f8933ca289c78e5e0c3a3eef0cc36d4bdeae1c44a1` | `78e540e41f302f67207da5c2fca54b99289b103498b47d26c8b0f9a1e11e0b8c` |
| suika | `bc_anchor3_suika_20261026_003624.npz` | `6a184a5c7e7a904f24cdd581131298d79c29542fd8ecf66f5583b47e7600fa75` | `manifest3_suika_20261026_003624.json` | `4f0fcb2555c50ad954308350b066cc3e454ae806de779016227fe09eae56fc2f` | `6ec8e9800b396889dbd98f6d7e134edd0b34c0402d9d89a456142b5c453e0390` | `bab98aa4e60ba73809ed0ffe8c24677f6116f3febfb39444fcd7f9bcd2296a8c` | `a61256965c9e68d1c620be40bf2ce047999401b455004294e8d0bda5e6d9aecf` |

## 2. 生成/复验命令（可直接执行）

### reimu（168 行；seed_base=初始 collect --seeds 4；topup 追加 seeds 4..6 （--max-extra-seeds 3~6））
```bat
D:\temp\pyenv\python.exe -X utf8 tools\bc_anchor_verify.py --char reimu --npz "D:\temp\th123_anchor\bc_anchor3_reimu_20261026_003321.npz" --blind 50
D:\temp\pyenv\python.exe -X utf8 tools\bc_anchor_merge.py --char reimu --anchor "D:\temp\th123_anchor\bc_anchor3_reimu_20261026_003321.npz" --apply
```
- manifest: `D:\temp\th123_anchor\manifest3_reimu_20261026_003321.json`（sha256 见上表）

### marisa（169 行；seed_base=初始 collect --seeds 4；topup 追加 seeds 4..6 （--max-extra-seeds 3~6））
```bat
D:\temp\pyenv\python.exe -X utf8 tools\bc_anchor_verify.py --char marisa --npz "D:\temp\th123_anchor\bc_anchor3_marisa_20261026_003459.npz" --blind 50
D:\temp\pyenv\python.exe -X utf8 tools\bc_anchor_merge.py --char marisa --anchor "D:\temp\th123_anchor\bc_anchor3_marisa_20261026_003459.npz" --apply
```
- manifest: `D:\temp\th123_anchor\manifest3_marisa_20261026_003459.json`（sha256 见上表）

### suika（172 行；seed_base=初始 collect --seeds 4；topup 追加 seeds 4..6 （--max-extra-seeds 3~6））
```bat
D:\temp\pyenv\python.exe -X utf8 tools\bc_anchor_verify.py --char suika --npz "D:\temp\th123_anchor\bc_anchor3_suika_20261026_003624.npz" --blind 50
D:\temp\pyenv\python.exe -X utf8 tools\bc_anchor_merge.py --char suika --anchor "D:\temp\th123_anchor\bc_anchor3_suika_20261026_003624.npz" --apply
```
- manifest: `D:\temp\th123_anchor\manifest3_suika_20261026_003624.json`（sha256 见上表）

## 3. dedupe 预览（生产 X 去重，`--dedupe` 默认 apply 开启）
| char | 生产行 | 锚输入 | 保留 | 去重丢弃 | 合并后 |
|---|---|---|---|---|---|
| reimu | 429411 | 168 | 19 | 149 | 429430 |
| marisa | 353622 | 169 | 15 | 154 | 353637 |
| suika | 329250 | 172 | 33 | 139 | 329283 |

> 旧 dry-run 的 `dedupe:false` 输出为**预览档**（未对生产 X 去重）；实际 apply 使用上表去重后行数。

## 4. 独立复验（盲放/留出）
| char | 同位置盲放(60) | 留出 | QC 文件 |
|---|---|---|---|
| reimu | 46/50 | 145 | `D:\temp\scratch\bc_anchor_v2_qc.json` |
| marisa | 48/50 | 159 | `D:\temp\scratch\bc_anchor_v2_qc.json` |
| suika | 49/50 | 162 | `D:\temp\scratch\bc_anchor_v2_qc.json` |
- 合计盲放 **143/150 = 0.953**（reimu 46/50、marisa 48/50、suika 49/50）；留出 0.863/0.941/0.942。

## 5. 冲突口径（避免误读）
- **row-level** 120/128/115 = 涉及 same-X 多 Y 的**行数**（旧口径）；
- **groups** 25/24/24 = 不同 X 哈希且包含 >1 个 Y 的**组数**（报告 JSON 口径）；
- 策略：**保留并登记，不强删**；X 去重仅 apply 时对生产 X 做；manifest 保留 provenance。
- 报告：`D:\temp\th123_anchor\conflicts_report_20261026.json`。

## 6. 缺行/低配额（target 宏）
| char | 缺行宏 | 低配额 |
|---|---|---|
| reimu | 原子·空链、择·投、压起身·空、压起身·穿 | 原子·确认5A:4 |
| marisa | 原子·确认5A、择·投、压起身·穿 | 原子·空链:1 |
| suika | 原子·确认5A、压起身·穿 | TM·空连终结:2、原子·空链:1 |

## 7. 部署/回滚
- 备份硬链 `bc_backup_anchor_<char>_<ts>`；apply 原子/journal/失败回滚；
- `bc_io` 强校验（hash cache 关）→ 重启 learner → 验收 coverage/选择率/KL/ent/4 游戏；
- 失败：journal 回滚+单次重启。

