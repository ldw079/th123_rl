# Bug: 门后延续 families 硬编码 mirror=False — 左朝向段错标(未修, P1)

- **发现**: 2026-10-14 从零#4 分片B(动态复现)+审查者亲验。
- **症状**: bc_match.py:253 `families()` 内 `_script_continuation(
  macros[mi][1], False)` 硬编码 mirror=False, 而 walk 对 facings<0 段
  用 mirror=True 约束匹配。动态证实: 左朝向专家按正确镜像方向 → 延续
  无法确认; 按错误方向反而确认。影响所有左朝向段的带方向门后延续
  (连段 6A/66 系)系统性错标。
- **根因**: 门后延续(类甲门后窥视)是新功能, families 缓存未按朝向
  分套(主匹配路径 tl_facing/cons_facing 都分了, families 漏分)。
- **修复与验证**: 未修。修法: families 按 mirror 缓存两套。**已按此修(2026-10-14晚)** —
  并连带发现**修法首版自身引入的walk循环尾mirror残留**(families(mirror)
  取到最后一组迭代的值): 定版修法=**每个命中携带自己的朝向**, 消费循环
  按命中朝向取两套缓存表。验证: bc_match_v3新增6探针(连段B/C/空连A
  左朝向flip_h输入→自身 + 右朝向对称)全绿; roundtrip 20/macros_branch
  72回归绿。
- **防复发**: 匹配器测试已补"左右朝向对称"用例(入C15)。
- **状态**: ✅已修+验证(2026-10-14晚)。
