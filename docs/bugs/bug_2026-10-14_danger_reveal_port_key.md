# Bug: danger_reveal 真实模式 KeyError — RESERVED 缺键(未修, P1)

- **发现**: 2026-10-14 从零#4 分片C(静态)。
- **症状**: tools/danger_reveal.py:233 `reserved_port('danger_reveal')`
  — portmap.RESERVED 无该键 → 真实模式启动即 KeyError。mock 模式可用,
  test_danger_reveal_w2 只覆盖 mock; contract_check 无对应断言(漏注册
  不红)。
- **根因**: RESERVED 单源表(R77)加了访问器, 但新工具注册端口时只改
  调用方未改表(单源表的两半不同步)。
- **修复与验证**: 未修。修法: RESERVED 补 danger_reveal 段键。验证:
  reserved_port('danger_reveal') 返回值+真实模式冒烟到游戏拉起前。
- **防复发**: 仓库 grep reserved_port 调用 × RESERVED 键对账断言入
  contract_check(单源完备性)。
- **状态**: 未修。
