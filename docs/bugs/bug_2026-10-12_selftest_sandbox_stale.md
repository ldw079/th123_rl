# Bug: 变异自检基础设施失效 — 沙箱清单过期+死变异(未修, P1)

- **发现**: 2026-10-12 从零审查#3 中央项(实测)。
- **症状**: `SELFTEST_TAGS=S0仪表,A1-2` 跑 gate_selftest → "[自检失败] 基线
  不绿 — 先修门禁本身", 沙箱内门禁 569/4/**1 FAIL**(test_series_stage1_e1),
  一条变异都没执行。直跑门禁 583/0/0 正常。
- **根因**: ①gate_selftest 沙箱 FILES 清单未收录 `series_manager.py`
  (d672c2d 入库时未同步), 而 test_series_stage1_e1 已入 _BEHAVIOR_TESTS
  且 import 它 → 沙箱内必炸; ②死变异×2: `("feat_builder.py",
  "CORE_DIMS = 316", ...)` 目标串已漂移为 330(B 段扩维后未迁);
  mod_provenance 的 md5 变异串与现档失配。
- **引入**: d672c2d(2.83, series_manager 入库)与 B 段扩维(2.82 前)。
- **影响面**: 变异自检自 10-12 起完全不可用(此前抽查声称的 ✓红 需重估);
  C2 维度漂移防线(死变异)假绿。
- **修复与验证**: 未修。修法: FILES 补 series_manager.py(+distill.py 顺手);
  死变异改锚 `CORE_DIMS = 330` 与现行 md5。验证: SELFTEST_TAGS 抽查
  跑通且变异红。
- **防复发**: 新模块入库检查单加"同步 gate_selftest FILES"(已在从零#3
  报告建议)。
- **状态**: 已修(2026-10-12 P1波, 从零#3)。FILES补series_manager+distill; 死变异迁CORE_DIMS=330与现行md5(1725B97C); 实跑基线绿+变异红(含新增P1-5变异)
