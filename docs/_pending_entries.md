# 待转录队列（docs/_pending_entries.md）

> 用途见 PARALLEL_WORKFLOW.md §0：非单写者向施工独写文件提交的条目。
> 施工每次 git 提交前消费：转录到目标文件后**删除对应条目**。
> 格式：目标文件 | 建议内容 | 日期 | 提交方

---

1. **METHODOLOGY.md §0 红线表 R4** | 建议增补第二权威源：
   "**wikiwiki.jp/th123ai API 语义表**（fflags/aflags 逐位/动作值全表/
   obj-ID 対応表/get_special_data，社区逆向+官方 document.txt 交叉）——
   与 cleista 分域: cleista=帧数据权威，wiki 语义表=引擎标志/动作分类
   权威；未确认位（wiki 标注'解析中'）不得当定论，采用前须实测交叉。
   证据: docs/th123ai_community_ai_analysis_2026-10-16.md §7。" | 2026-10-17 | 规划
   > **状态: 挂起待用户裁定** — §0 是纪律红线表, 其增补按宪法"修订权"
   > 条需用户批准; 施工不代决。裁定"准"后由施工转录。
   > 备查: 若准, 同批在 R4 行末补"分域"措辞, 并在 §10 事故清单加一行
   > "语义标志靠猜→wiki 语义表入源(CA-0/CA-2 已按此核验 objs 未命中)"。

（队列消费记录 — 2026-10-18 11:1x 施工 W1-EXEC）
- 条目「docs/THIRD_PARTY.md 已起草, 待规划确认 + INDEX 登记」→**已关闭**:
  规划已完成并合入 main（`docs/INDEX.md:25` 实测已登记 `tools/bc_accept.py`;
  soku_arch 授权已由 R191 裁定"自有代码→MIT"并落 `soku_arch/VENDORED.md`+SPDX 头）。
- 条目「_archive 历史半程（第二次重写未用 --invert-paths）」→**已关闭**:
  R192 第三次全历史重写已按 `--invert-paths --path _archive` 剔除
  （全历史 0 提交, HEAD 树哈希不变; 见 METHODOLOGY 3.63）。
- 条目「docs/INDEX.md 登记 bc_accept 验收工具」→**已关闭**（同上, 规划 88f49ab 已登记）。
- 条目「R4 第二权威源（wikiwiki.jp/th123ai）」→**仍挂起待用户裁定**（见上方第 1 条）。
- 原 2026-10-17 消费记录（PARALLEL_WORKFLOW 入宪 / R4 挂起 / PR-1 许可核验 /
  PR-2 路径适配 / git 重写通知）→ 见 METHODOLOGY 3.60(R170) 与历史 git log, 均已闭环。
