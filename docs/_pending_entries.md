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

（队列已清空 — 2026-10-17 21:5x 施工消费记录）
- 原条目 1/2/3（PARALLEL_WORKFLOW 入宪 + AGENTS/HANDOVER 路由行）→ **已转录**
  （METHODOLOGY 3.60 / AGENTS 头部路由区 / HANDOVER 当前栈速览）。
- 原条目 4（R4 第二权威源）→ 见上方第 1 条, **挂起待用户裁定**。
- 原条目 5（PR-1 许可文件）→ **已核对**: LICENSE(MIT)/docs/LICENSE-docs.md(CC-BY-4.0)/
  docs/DATA_POLICY.md/README 访客段均在库, 无施工待办 → 消费完毕。
- 原条目 6（PR-2 余项路径适配）→ **已执行, 但口径按审计侧修正**: 不包 expandvars
  （那只修本机), 改为**仓库相对/文件位置派生** + `kit_config.REPO_ROOT/repo_path/
  expand` 单源; 覆盖 2 测试/bc_build(分片 glob→repo 相对, 实测 1724 片)/
  oracle_batch2/run_parallel/6 tools; 6 个运行产物 json 路径脱敏并入 .gitignore
  → 详见 METHODOLOGY 3.60(R170)。
- 原条目 7（git 历史已重写通知）→ **已收到**; 施工侧已同步（HEAD 756558b 起为
  重写后历史, 旧哈希仅存本地 pre-rewrite-backup）。控制臂锚 46920e9→ef7f92f 已按树哈希
  重钉(见 _plans/public_release_hardening_plan_2026-10-17.md)。
