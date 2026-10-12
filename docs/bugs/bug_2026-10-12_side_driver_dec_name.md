# Bug: 对手侧 R34 守备豁免恒失效(未修, P1)

- **发现**: 2026-10-12 从零审查#3 分片A(动态复现+审查者亲验)。
- **症状**: 训练对手(side_driver)的"立防/蹲防"宏启动窗在对手攻击+近距时
  永远被清队 — 训练侧豁免、对手侧不豁免, 行为系统性不对称。
- **根因**: side_driver.py:397 给 `advance_queue` 传 `dec_name=None`(全文件
  无赋值), 而执行器判据 `dec_name not in GUARD_PREP_SET`
  (macro_executor.py:118)对 None 恒真。注释(396-399)显示修复意图
  "与训练侧同集" — 只修了 SET 参数(GUARD_PREP_MACROS), 漏了前面的
  dec_name 位置参数(train_tm.py:1550 正确传名)。
- **引入**: 从零#2(10-06)执行器 P2 修复时 — 修一半。
- **影响面**: 自那时起全部训练对局的对手防御行为弱于训练侧 = 训练信号
  偏斜(方向: 主策略面对的对手防御偏弱, 可能高估压制力)。
- **修复与验证**: 未修。修法: side_driver 决策时同样记录 dec_name 并传入。
  验证: 配对测试 — 同队列两侧 dec_name="立防" 均存活、None 均被清。
- **防复发**: 两侧行为对称性断言(同一队列在 train_tm/side_driver 路径
  产生相同的清队决策)。
- **状态**: 已修(2026-10-12 P1波, 从零#3)。side_driver记录/回传_dec_name(与train_tm同型); 对称性测试入test_executor_c1(23 PASS)
