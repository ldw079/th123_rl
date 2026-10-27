# C79-8 §10 连段完成判据（limit≥100）与现场校准（2026-10-27 22:12）

## 判据（用户/Lead 22:11 定稿）
> **完成 = 计划宏步全部执行（无提前截断） AND comboLimit ≥ 100（出圈）**；
> comboDamage/comboCount 仅作过程量；此前的“伤害≥/命中≥/动作数≥”只是 proxy，**撤回“完成”说法**。
> 失败必须标：断连/被防/空挥/未出圈/不可实现 + 帧证据。

## RPM 字段（原版游戏 PID24260 连段A 现场采样）
| offset | 字段 | 实测 |
|---|---|---|
| 0x4B4 | comboCount | 1 → 4 |
| 0x4B6 | comboDamage | 190 → **1510** |
| **0x4B8** | **comboLimit** | 0 → **40**（重复循环 max 仍 40） |

- 其他变动：0x4A2（0–119，rei_stop 候选）、0x4AC、0x4B0（0x4B0 非 u16 语义，勿当 limit）。
- **连段A 实测 limit=40 < 100 → 不完成**；用户批评成立，visible macro demo 仅“宏执行/P1 驱动”证据。
- 校准局限：连续宏读到上一 combo 残留 max（1510/40），需 clean-state 等待后逐宏单次采样；明日补 limit 曲线。

## 后续
- strict lab / v2 表全部改标 **proxy**，不称完成；明日 BC/UKEMI 后按 limit 重跑逐条（含 clean-state 校准）。
- 训练环境字段一致性：0x4B8 在训练/lab/回放需同版本核验；可加入 actor 观测（env 可关）。
