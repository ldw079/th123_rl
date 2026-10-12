# Bug: 吞吐报告路径常量含真实 TAB 字节(未修, P1)

- **发现**: 2026-10-12 从零审查#3 分片C(AST 求值复现+审查者 cat -A 亲验)。
- **症状**: tools/throughput_report.py:182 `r'D:^Iemp'`(D: 后是 TAB 非
  反斜杠)→ os.path.join 结果指向不存在的 `D:<TAB>emp\...` → getmtime 恒
  OSError → 所有 actor 段恒"[陈旧档不计入合计]" → **fleet 合计恒 0.0 局/h**,
  即使 D:/temp 下有活跃 actor 日志。
- **根因**: 源码字节级笔误(TAB 代替 `\t` 转义或 `\`), raw string 下无转义
  兜底。
- **引入**: throughput_report.py 落地波(F 项, 2.8x)。
- **影响面**: 控制台口径的 fleet 吞吐读数全失真(运维决策数); JSON 输出
  不含该合计故存档未污染; 其余口径(actor 段内数值)不受影响。
- **修复与验证**: 未修。修法: 改 `r'D:\temp'`。验证: 实跑后活跃 actor 计入
  合计; 配对测试加"路径常量不含控制字符"断言(可编程扫 chr(9) in path)。
- **防复发**: 路径常量 lint 类断言; 或所有 D:\ 前缀统一走 STORE 常量。
- **状态**: 已修(2026-10-12 P1波, 从零#3)。TAB字节→r"D:	emp"; 控制字符可编程扫入test_throughput_f(5 PASS)
