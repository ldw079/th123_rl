# Bug: CE-1 宏层画像自上线即死 — begin 不传宏名(未修, P1)

- **发现**: 2026-10-16 从严审计分片A; 审查者亲验。
- **症状**: my_punish_tracker.py:84 `begin(cls, name=None)` 支持宏层 EMA
  (macro_rate/macro_n), 但生产路径两个调用点 train_tm.py:1929 与
  side_driver.py:302 均只传 `begin(_dcls)` — **宏层画像在线恒空**,
  仅测试传 name(测试全绿但覆盖无人走的路径)。W4"自上线即死"同型
  第三例(W4 价值曲线/维度接线无测)。
- **根因**: 接口设计先行, 调用方未跟上; 测试与生产走不同调用形态。
- **影响面**: CE-1 宏层画像零数据(类层画像正常)。
- **修复与验证**: 未修。修法: 两调用点补 name=宏名。验证: 实跑一批
  宏层读数非空; 防复发: 生产调用形态断言(源检查 begin(.*name= 或
  feature_liveness 扩宏层维度)。
- **状态**: ✅**已修(2026-10-16 R145, 审计P1-1当日清偿)**: 两调用点
  补name=train_tm:1929(name=dec_name)/side_driver:302(name=宏名);
  防复发=contract_check新增生产调用形态断言(begin(_dcls, name=);
  制度化=坑表"上线即自检"条目(部署验收含首批真数据非空)。
