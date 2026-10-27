# C79-8 严格 lab 可验证 manifest（2026-10-27，host 20:15）

## 示例 attempt（真实 strict 运行结果，非 proxy）
| 字段 | 值 |
|---|---|
| combo | reimu `TM·2a连` scene0 |
| planned_steps | 4 |
| executed_steps | 12 |
| segments | 3 |
| hits | 6 |
| dmg | **550** |
| target_damage | **495**（来源：历史 `combo_replay_p4` max×0.9，容差 10%） |
| truncated | false |
| pass | **true** |
| 证据 | `D:\temp\combo_lab_strict_v2_20261027.json` 对应行；可见 demo log `D:\temp\combo_lab_visible_20261027.log` 中同 combo：dmg 550×3、acts `[209,303,307]`、frames 165（sha1 前缀 `8ff65ec8…`） |

## 原版回放兼容性结论（如实）
- **lab attempt 未生成 `.rep`**：`EvalEnv(COM)` 训练 lab 未开启游戏录像；原版 `th123.exe <rep>` 无法回放不存在的 rep。
- **未伪造**：不给假 rep/假 hash；`verify_manifest_example.json` 标 `rep=null`。
- **替代验证**（用户可核）：
  1) `docs/_audit/combo_lab_strict_v2_20261027.md` 逐 scene planned/executed/segments/hits/dmg/target/pass/reason；
  2) 可见 demo log（原始窗口执行，用户当场可见）；
  3) 宏脚本 + EvalEnv 确定性重跑（同输入同结果；伤害/act/frame 可复算）。
- **后续补 .rep**：在游戏设置开启录像/用原版窗口执行宏（P1 驱动脚本已可用），生成真实 rep 后再做原版回放测试；当前不宣称通过。

## 一键方式（rep 就绪后）
```powershell
# 方式1: 原版 exe 直接带 rep
& 'D:\touhou\hisoutensoku2026-06-15\th123\th123.exe' '<rep路径>'
# 方式2: 游戏内 Replay 菜单选择 rep
```
