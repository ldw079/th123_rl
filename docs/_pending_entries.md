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
