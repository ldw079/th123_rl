# Bug: 沙箱 FILES 二次漂移 — value_curve 未收录(未修, P1)

- **发现**: 2026-10-13 从严审查, 审查者静态实证(AST 比对 C15 行为测试
  import 依赖 × gate_selftest FILES 清单)。
- **症状**: tests/test_research_w_wave.py(已入 C15,
  contract_check.py:1865)import `value_curve`, 而 gate_selftest 沙箱
  FILES(60 文件)未收录 `value_curve.py` → 沙箱内该行为测试必炸 →
  **自检基线又将不绿**, 变异自检一条都跑不了。
- **根因**: R86+ 波次落地 value_curve(W4)并入 C15 时, 未同步
  gate_selftest 的 FILES — 与 P1-1(selftest_sandbox_stale, R80 刚修)
  **完全同型**: "新模块入库未同步治理清单"的制度缺口未被堵住(从零#3
  报告的建议"入库检查单加同步 FILES"未落地)。
- **引入**: value_curve 入 C15 的波次(R8x, W4 执行)。
- **影响面**: 变异自检自该波起再次不可用; 无训练面影响。
- **修复与验证**: 未修。修法: FILES 补 `value_curve.py`; 验证: SELFTEST
  基线绿 + 任一标签变异红。根治: 入库检查单/SOP 落"同步 FILES"条款。
- **防复发**: 把本次用的静态比对(AST×FILES)做成常驻断言入
  contract_check — 行为测试依赖的根级模块必须 ⊆ FILES(结构性防复发,
  不再靠人记)。
- **状态**: 未修。
