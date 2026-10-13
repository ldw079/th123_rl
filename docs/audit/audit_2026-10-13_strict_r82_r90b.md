# 审计报告: ac8ba8b..f45620b0 新代码从严审查(2026-10-13)

- **基线**: commit `f456210`(R90b)。审查范围 `ac8ba8b..HEAD`(R82~R90b,
  23 py 文件 +1932 行) + 工作区在途状态。**工作区有并发会话进行中的
  文档重组(docs/ 迁往 _plans/_reviews, 未提交)与 rpm_offsets_raw.json
  修改 — 本审计按只读对待, 不评判半成品**。
- **审计时刻**: 2026-10-13 16:50~17:10; fleet 运行中(10 进程, learner
  16:56 在写), 全程未受干扰。
- **方法**: 门禁实测 + 运行时三面 + 修复验证分片(R80 六 P1 与 R84 十一
  P2 逐项核验) + 亲审最高风险面(B-1/B-2 内存通道)+ 静态 AST×FILES
  沙箱漂移比对。
- **与上一份归档差异**(audit_2026-10-13_rep_harvest): 上份 P2×2 已由
  R82 清偿; 本报告主对象是 R80~R90b。

## 总判定: 主干修复质量高(五项 P1 根因修复), 但**一项假修复 + 两项
## 治理防线失效**; 新立/重开 3.5 份 bug 档

**通过项**:
- 门禁 HEAD 实测 **597/0/0**; 59 模块 import 面(含全部新模块)随门禁绿。
- R80 五项 P1 干净根因修复(分片核验): 其中 **ppo 双实现梯度等价修复
  质量最高** — 混代 W1v 前移 + _cap_backward 完整 zmax 项(分片独立
  推导公式核对无误), 测试达全参数符号级+中心有限差分(rel<1e-6)+
  变异红。TAB 路径/habits_retract/trainstart 误杀/threshold 均验证。
- R84 十一 P2 抽验三项(ratio 钳制/平局三态/BC 原子落盘)均根因修复,
  六项带理由推迟(合规)。
- B-1/B-2 人测通道建设扎实: 校准实证链(spirit 98.5%/position.x 99.7%
  交叉验证)、对象链、生产通道 human_match_v2 **有完整 try/finally+
  180s 窗+结束复原纪律**(亲验, 正式模式自动禁 mod 亦带复原);
  rpm_offsets 策展表+校准器输出分流在位。
- value_curve(W4 落地)符合方案验收: 降级响亮(文档与代码一致),
  learner 挂点对齐 series_meter 现行模式, 配对测试入 C15。

## P1 发现(三项, 均亲验/静态实证)

| # | 发现 | 证据 | bug 档 |
|---|---|---|---|
| 1 | **P1-2(dec_name)假修复 — bug 重开**: R80 只接了"传参/回传"半环, side_driver 决策入队处(:277 enqueue_script)从未赋 `self._dec_name`, 恒 None → R34 守备豁免**依旧恒失效**; 配对测试的 grep 断言恰好被死接线满足(绿灯但根因未除) | 亲验 grep: _dec_name 仅 :60/:125 初始化、:394 回传、:400 传参, 入队处无赋值; macro_executor 对 dec_name 只清不设 | 重开 bug_2026-10-12_side_driver_dec_name |
| 2 | **门禁恒真死锚**: contract_check.py:1906 心跳锚尾接 `or True` — 永真, 防线是假的(修复真、锚假) | 亲验 grep 定位 | 新立 bug_2026-10-13_gate_anchor_or_true |
| 3 | **沙箱 FILES 二次漂移**: test_research_w_wave.py(入 C15)依赖 value_curve.py, FILES 未收录 → 自检沙箱必炸, **P1-1 同型复发**(R80 刚修的类, "入库同步 FILES"制度未落地) | 静态 AST×FILES 比对实证: 缺失 [('test_research_w_wave.py','value_curve')] | 新立 bug_2026-10-13_sandbox_files_drift2 |

## P2 发现

- **mem_input_experiment 无 try/finally**(亲验): phase2 异常时
  readInKeys=1 残留用户原版进程, 真人输入被夺权直到重启 —
  新立 bug_2026-10-13_memexp_no_finally。
- 观察: find_game 取首个非训练 th123.exe(多实例时任选), 建议 WMO 语义
  待多实例场景出现时再议。

## 建议(待用户指令, 审计不修)

1. 三项 P1 修复量极小(一行赋值+贯通断言/删 or True/FILES 补一行)+
   根治项: AST×FILES 比对做成常驻断言(结构性堵住 P1-1 类复发)。
2. memexp 的 finally 复原随下个顺手波。
3. 文档重组(docs→_plans/_reviews)由施工会话完成后, 注意 HANDOVER/
   AGENTS 索引路径同步与审计/bug 档去向。
