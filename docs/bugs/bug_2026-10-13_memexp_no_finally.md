# Bug: mem_input_experiment无try/finally — 已修

- **发现**: 2026-10-13 从严审计#4 P2。
- **症状**: phase2异常时readInKeys=1残留用户进程(输入被夺权直到重启)。
- **修复**: try/finally包裹, finally复原inKeys+readInKeys。
- **状态**: 已修(2026-10-13)。
