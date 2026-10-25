# P0-C3 重构验收判据（Gate 状态 resolver；草案）

> **状态**：草案（2026-10-25 22:2x）；基线 HEAD `e09730d`；只读审计，不实施。用户红线（2026-10-25"禁止添加无意义自检与门禁"）+ R15：每条验收必须行为基座/独立真值；纯串/装饰断言不计通过。
> **通用通过规则**：AC 必须绑定证据（命令+原始输出/文件/日志）、自动化门禁、可回滚；未列证据=未通过；任何豁免需 Lead 书面批。

## 目标
把 `game_gates.apply_state_gates` 单体 allow 叠加拆为**声明式状态 resolver + allow 表生成器**；真实帧 golden 覆盖各状态×env 组合；重构前后 mask 逐位等价；R15 行为基座。

## 验收判据（AC）
| ID | 判据 | 证据/测试 | 通过标准 |
|---|---|---|---|
| C3-1 | **resolver+allow 表生成器（声明式）**：DOWN/HIT/GUARD/AIRDEF/MISGUARD 等状态与 allow 由表/纯函数产生，不再散落 if 叠加 | resolver 源码/表+调用图 | 单函数 allow 叠加=0；状态/allow 可枚举 |
| C3-2 | **真实帧 golden**：每状态 frozen/hit/blocked/whiff/guard/misguard 至少 1 条真实帧轨迹；期望允许集合/最终 mask | fixture 帧+golden+测试 | 每状态 golden PASS；fixture 可追溯帧日志 |
| C3-3 | **env 组合矩阵**：ACT_MASK/AIR_GATE/IMMOBILE_GATE/DD_GUARD_ONLY/BUFFER/UKEMI_DIR/GUARD_CANCEL 组合覆盖（正交/边界） | 矩阵表+参数化测试 | 覆盖表 PASS；未覆盖组合=0（或登记豁免） |
| C3-4 | **等价性（前后 mask 逐位一致）**：同帧/同 env 下旧 vs 新 mask bitwise 相等；差异清单逐条解释 | 对拍脚本+diff 报告 | 差异=0（或全部书面豁免+Lead 批） |
| C3-5 | **事故回归**：_buf_cnt actor 崩-loop（a8d23cb）、confirm gate 语义、UKEMI/buffer/DD 边界；变异→行为红 | 回归测试+变异记录 | 回归全绿；变异红；仅串红不算 |
| C3-6 | **R15 禁字符串断言**：状态/allow 测试必须有行为基座（帧/mask），无 src() 装饰断言 | 测试审查+门禁 | 新/改测试纯串断言=0 |
| C3-7 | **模糊/鲁棒**：随机合法/非法状态×动作×mask 属性测试；masked 动作绝不采样；无异常/崩溃 | 属性测试+日志 | 属性 PASS；崩溃=0 |

## 分批
M1 resolver/表+golden → M2 env 矩阵+等价对拍 → M3 事故回归/变异 → M4 模糊/门禁接入。
