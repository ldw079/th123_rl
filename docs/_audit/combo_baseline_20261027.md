# 连段/断点 基线（proxy，2026-10-27）

- 数据: episodes_keep（120/char 裁剪后训练期新片段）
- **缺口**：完成率/confirm_timeout/gate_truncate/hit 打断 无逐决策遥测；需 task-62 仪表（下一步）
- lab 88 trailmod/50 lab 严格 replay：deferred（隔离 lab）

| 角色 | 局数 | 决策 | combo选择率 | 宏平均帧 | 类别分布 |
|---|---|---|---|---|---|
| reimu | 184 | 130887 | 0.012 | 1.85 | poke_misc=0.794, combo_pressure=0.012, defense=0.193, approach=0.001 |
| marisa | 196 | 110913 | 0.036 | 2.06 | poke_misc=0.738, combo_pressure=0.036, defense=0.224, approach=0.002 |
| suika | 155 | 181701 | 0.032 | 2.17 | poke_misc=0.773, approach=0.004, defense=0.191, combo_pressure=0.032 |

## top combo 宏（选择次数）
- reimu: [('压起身·延迟', 654), ('压起身·穿', 292), ('压起身·即', 235), ('TM·4a连', 232), ('TM·2a连', 93)]
- marisa: [('择·下段', 2376), ('压起身·延迟', 554), ('TM·必杀SC连', 535), ('压起身·即', 499), ('压起身·穿', 35)]
- suika: [('压起身·延迟', 3086), ('TM·空连终结', 1127), ('压起身·即', 909), ('择·投', 195), ('压起身·空', 192)]
