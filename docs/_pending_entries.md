# 待转录队列（docs/_pending_entries.md）

> 用途见 PARALLEL_WORKFLOW.md §0：非单写者向施工独写文件提交的条目。
> 施工每次 git 提交前消费：转录到目标文件后**删除对应条目**。
> 格式：目标文件 | 建议内容 | 日期 | 提交方

---

1. **METHODOLOGY.md 修订记录** | 建议追加一行（版本号顺延）：
   "- 3.2x (2026-10-16, **R1xx 三智能体并行工作流入宪（用户批准试行）**):
     单写者规则+队列机制+worktree 分工立档 `PARALLEL_WORKFLOW.md`
     （根目录入口层）; 规划 worktree=planning 分支@D:/temp/
     th123_rl_planning（当日合并/永不部署）; 审计按哈希钉读;
     对照臂 worktree 不变。实测动因: 并行开发文档编辑撞车×3+。" | 2026-10-16 | 规划

2. **AGENTS.md 头部路由区** | 建议在"审计工作入口"行后加一行：
   "> **三智能体并行工作流: `PARALLEL_WORKFLOW.md`（单写者规则+
   worktree 分工, 2026-10-16 试行）——写文件前先查写入权。**" | 2026-10-16 | 规划

3. **HANDOVER.md 交接必读** | 建议在头部"供下一个智能体直接接手"附近
   加："并行开发必读 `PARALLEL_WORKFLOW.md`（写入权+队列）;
   规划侧文档变更看 docs/_plans/ 与 INDEX。" | 2026-10-16 | 规划

4. **METHODOLOGY.md 修订记录** | 建议追加一行（版本号顺延）：
   "- 3.2x (2026-10-17, R1xx 权威源分域增补): R4 红线新增第二权威源
     **wikiwiki.jp/th123ai API 语义表**（fflags/aflags 逐位/动作值
     全表/obj-ID 対応表/get_special_data，社区逆向+官方 document.txt
     交叉）——与 cleista 分域: cleista=帧数据权威，wiki 语义表=引擎
     标志/动作分类权威；未确认位（wiki 标注'解析中'）不得当定论，
     采用前须实测交叉。证据: docs/th123ai_community_ai_analysis_
     2026-10-16.md §7（动作 ID 与我方 action_tables.py 逐 ID 实证
     同源）。" | 2026-10-17 | 规划

5. **根目录 LICENSE + docs/LICENSE-docs（PR-1，待用户裁定档位后）** |
   见 docs/_plans/public_release_hardening_plan_2026-10-17.md §④
   决策 1——默认推荐 MIT(代码)+CC-BY-4.0(文档)双列，README 加
   徽标行。用户裁定前**不创建**。 | 2026-10-17 | 规划

6. **代码侧用户名脱敏（PR-2 代码半边，~10 个 py + 12 个 bat）** |
   规则见 public_release_hardening_plan §PR-2: .bat 中
   `%USERPROFILE%`→`%USERPROFILE%`; py 默认路径逐处改
   `os.path.expanduser`/相对路径并跑门禁+本机冒烟（三 worktree 不
   可破坏）; `_archive` 一律不动。文档侧约 5 个 md 由规划自行处理。
   **与 BH-4.4 批错开提交**。 | 2026-10-17 | 规划
