# Bug: 门后延续 families 硬编码 mirror=False — 左朝向段错标(未修, P1)

- **发现**: 2026-10-14 从零#4 分片B(动态复现)+审查者亲验。
- **症状**: bc_match.py:253 `families()` 内 `_script_continuation(
  macros[mi][1], False)` 硬编码 mirror=False, 而 walk 对 facings<0 段
  用 mirror=True 约束匹配。动态证实: 左朝向专家按正确镜像方向 → 延续
  无法确认; 按错误方向反而确认。影响所有左朝向段的带方向门后延续
  (连段 6A/66 系)系统性错标。
- **根因**: 门后延续(类甲门后窥视)是新功能, families 缓存未按朝向
  分套(主匹配路径 tl_facing/cons_facing 都分了, families 漏分)。
- **修复与验证**: 未修。修法: families 按 mirror 缓存两套。验证:
  分片B 的合成探针(左朝向正确镜像方向确认延续)入测试。
- **防复发**: 匹配器测试补"左右朝向对称"用例(与既有往返测试集同批)。
- **状态**: 未修。
