# Bug: danger_reveal 真实模式 KeyError — RESERVED 缺键(未修, P1)

- **发现**: 2026-10-14 从零#4 分片C(静态)。
- **症状**: tools/danger_reveal.py:233 `reserved_port('danger_reveal')`
  — portmap.RESERVED 无该键 → 真实模式启动即 KeyError。mock 模式可用,
  test_danger_reveal_w2 只覆盖 mock; contract_check 无对应断言(漏注册
  不红)。
- **根因**: RESERVED 单源表(R77)加了访问器, 但新工具注册端口时只改
  调用方未改表(单源表的两半不同步)。
- **修复与验证**: **已修(2026-10-14晚)**: RESERVED补danger_reveal
  ('probe', 20976), reserved_port()返回20976验证。
- **防复发**: contract_check新增**单源完备性对账断言**(全仓
  reserved_port调用[双引号兼容]×RESERVED键双向: 缺键红/僵尸键红;
  首版断言自身两bug已修: 单引号正则漏双引号调用/自docstring占位
  误报)。真实模式冒烟待舰队空闲窗。
- **状态**: ✅已修+验证(2026-10-14晚; 真实模式冒烟待窗)。
