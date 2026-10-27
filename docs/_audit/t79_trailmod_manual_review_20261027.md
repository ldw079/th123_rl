# trailmod 不可表达/人工复核清单（2026-10-27）

- 88 trial，**57 条含不可静态解析步骤**（复合语义/无方向键/多名记谱）；31 条可全静态转写。
- 复核口径：`hj9/j66/d623b/[N]/:N` 等复合符号；parser v2 已拆 1289 步，**88.98%** 可表达；剩余为复合语义（如 `j66` 的 66 dash 方向、`d623b` 的 623 输入）需人工/帧级核实。
- 输出：`D:\temp\t79_trailmod_manual_review_20261027.json`（逐条 bad_steps）。
- 8 条 explicit-input 候选仍待隔离 lab 严格 replay（不宣称通过）。
- 后续：人工复核 57 条 → 补 notation→宏映射；不可转写者标"notation-only"，不硬塞语料。
