# Bug: 沙箱FILES二次漂移(value_curve.py未收录) — 已修+根治

- **发现**: 2026-10-13 从严审计#4 P1-3(P1-1同型复发)。
- **症状**: test_research_w_wave(C15注册)依赖value_curve, FILES未收
  → 自检沙箱必炸。
- **修复**: FILES补value_curve; **根治**: 门禁新增常驻断言
  "FILES完备性"(AST×C15 imports×沙箱清单 — 结构性堵死此类复发)。
- **状态**: 已修+根治(2026-10-13)。
