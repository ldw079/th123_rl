# Bug: B3 报告空窗 KeyError(未修)

- **发现**: 2026-10-12 上午, 验证 R67c 列号修复时实跑
  `python tools/remote_usage_report.py`(真实 episode 目录,
  marisa 2 / reimu 4 / suika 1 局)即崩溃。
- **症状**(实录):
  ```
  File "tools/remote_usage_report.py", line 157, in report
      and win_reports[0]['far_bullet_share'] is not None)
  KeyError: 'far_bullet_share'
  ```
- **根因**: `report()` 的空窗分支只写 `{'range': [lo,hi], 'decisions': 0}`,
  不含 `far_bullet_share` 键; 而 `far_share_delta` 对
  `win_reports[0]`/`win_reports[-1]` 无守卫下标该键
  (remote_usage_report.py:155-158)。
- **触发条件**: 单角色 episode 数 < windows(当前 suika 1 局,
  windows=2 → 首窗 [0:0] 为空)。崩溃型非静默型, 无数据污染。
- **引入**: f2fe368(2.65, B3 工具初版)既有缺陷 — **非** R67c 列号
  修复引入(该提交未触碰窗口切分逻辑)。此前未暴露: 10-11 运行时
  三角色各有 ≥2 局, 空窗不出现; 10/10 配对测试的合成数据同样每窗非空
  (测试盲区: 未覆盖空窗路径)。
- **影响面**: 奇数/少量局角色上工具不可用; **新 B3 基线在修复前无法
  生成**(R67c 已作废旧基线, 见 bug_2026-10-12_b3_adx_column);
  无既有结论被污染(此前运行均未触发)。
- **修复与验证**: 未修(待用户指令)。建议修法: 空窗分支补齐键
  (`far_bullet_share: None` 等)或 far_share_delta 用
  `w.get('far_bullet_share')`; 验证: 当前真实目录实跑通过 +
  配对测试补"单局角色"用例(空窗路径入断言)。
- **防复发**: 配对测试增加 episode 数 < windows 的空窗用例;
  `print_report` 已有空窗分支('窗[..] 空')说明打印路径考虑过空窗,
  计算路径漏了 — 属"防御不对称"型, 测试应同时钉两条路径。
- **状态**: 未修。
