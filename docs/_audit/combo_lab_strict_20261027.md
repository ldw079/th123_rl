# C79-8 严格 lab 表（2026-10-27）

- 判据: 队列执行完(无截断) AND 命中≥1 AND dmg>0 AND 段数≥1；目标伤害源未定义（target_source=undefined，不参与 pass）
- 端口 20967 / HITMEM=24；失败原因逐条列。

| 角色 | combo | planned | executed | segments | hits | dmg | truncated | pass | reason |
|---|---|---|---|---|---|---|---|---|---|
| reimu | TM·2a连 | 4 | 12 | 3 | 6 | 550.0 | False | True | ok |
| reimu | TM·4a连 | 4 | 10 | 2 | 3 | 1579.0 | False | True | ok |
| reimu | 压起身·即 | 4 | 4 | 1 | 6 | 550.0 | False | True | ok |
| reimu | 压起身·延迟 | 5 | 5 | 4 | 4 | 1555.0 | False | True | ok |
| reimu | 压起身·空 | 3 | 3 | 1 | 0 | 0.0 | False | False | no_hit;dmg<=0 |
| reimu | 压起身·穿 | 3 | 3 | 1 | 0 | 0.0 | False | False | no_hit;dmg<=0 |
| reimu | 原子·地面链 | 7 | 7 | 4 | 8 | 1223.0 | False | True | ok |
| reimu | 原子·收尾 | 5 | 5 | 3 | 6 | 550.0 | False | True | ok |
| reimu | 原子·确认5A | 3 | 4 | 3 | 3 | 821.0 | False | True | ok |
| reimu | 原子·空链 | 7 | 7 | 2 | 0 | 0.0 | False | False | no_hit;dmg<=0 |
| reimu | 择·下段 | 5 | 5 | 3 | 6 | 550.0 | False | True | ok |
| reimu | 择·中段 | 4 | 4 | 2 | 1 | 600.0 | False | True | ok |
| reimu | 择·投 | 4 | 4 | 2 | 1 | 200.0 | False | True | ok |
| reimu | 版边连A | 18 | 18 | 6 | 7 | 1663.0 | False | True | ok |
| reimu | 连段A | 16 | 16 | 5 | 4 | 1510.0 | False | True | ok |
| reimu | 连段B | 16 | 16 | 5 | 4 | 1510.0 | False | True | ok |
| reimu | 连段C | 14 | 14 | 5 | 4 | 1406.0 | False | True | ok |
| marisa | B6C连 | 9 | 9 | 2 | 15 | 2549.0 | False | True | ok |
| marisa | TM·6a终结 | 6 | 6 | 1 | 1 | 900.0 | False | True | ok |
| marisa | TM·必杀SC连 | 10 | 10 | 1 | 1 | 1250.0 | False | True | ok |
| marisa | 压起身·即 | 4 | 4 | 1 | 1 | 450.0 | False | True | ok |
| marisa | 压起身·延迟 | 5 | 5 | 3 | 3 | 937.0 | False | True | ok |
| marisa | 压起身·空 | 3 | 3 | 1 | 1 | 900.0 | False | False | no_hit;dmg<=0;ok |
| marisa | 压起身·穿 | 3 | 3 | 1 | 0 | 0.0 | False | False | no_hit;dmg<=0 |
| marisa | 原子·地面链 | 12 | 12 | 5 | 16 | 2920.0 | False | True | ok |
| marisa | 原子·收尾 | 5 | 5 | 3 | 1 | 450.0 | False | True | ok |
| marisa | 原子·确认5A | 3 | 3 | 1 | 1 | 200.0 | False | True | ok |
| marisa | 原子·空链 | 10 | 10 | 3 | 0 | 0.0 | False | False | no_hit;dmg<=0 |
| marisa | 择·下段 | 5 | 5 | 3 | 1 | 1000.0 | False | True | ok |
| marisa | 择·中段 | 4 | 4 | 2 | 1 | 550.0 | False | True | ok |
| marisa | 择·投 | 4 | 4 | 2 | 1 | 200.0 | False | True | ok |
| marisa | 连段A | 13 | 13 | 4 | 4 | 2151.0 | False | True | ok |
| marisa | 连段B | 15 | 15 | 7 | 14 | 2340.0 | False | True | ok |
| marisa | 连段C | 14 | 14 | 5 | 4 | 1277.0 | False | True | ok |
| suika | TM·对空连 | 15 | 15 | 3 | 5 | 1975.0 | False | False | no_hit;dmg<=0;ok |
| suika | TM·空连终结 | 16 | 6 | 2 | 0 | 0.0 | False | False | no_hit;dmg<=0 |
| suika | 压起身·即 | 4 | 4 | 1 | 1 | 550.0 | False | True | ok |
| suika | 压起身·延迟 | 5 | 5 | 3 | 3 | 1766.0 | False | True | ok |
| suika | 压起身·空 | 3 | 3 | 1 | 2 | 1289.0 | False | False | no_hit;dmg<=0;ok |
| suika | 压起身·穿 | 3 | 3 | 2 | 0 | 0.0 | False | False | no_hit;dmg<=0 |
| suika | 原子·地面链 | 8 | 8 | 3 | 4 | 1751.0 | False | True | ok |
| suika | 原子·收尾 | 5 | 5 | 3 | 1 | 550.0 | False | True | ok |
| suika | 原子·确认5A | 3 | 3 | 1 | 1 | 500.0 | False | True | ok |
| suika | 原子·空链 | 7 | 7 | 2 | 0 | 0.0 | False | False | no_hit;dmg<=0 |
| suika | 择·下段 | 5 | 5 | 3 | 1 | 550.0 | False | True | ok |
| suika | 择·中段 | 4 | 4 | 2 | 2 | 1071.0 | False | True | ok |
| suika | 择·投 | 4 | 4 | 2 | 1 | 500.0 | False | True | ok |
| suika | 连段A | 13 | 13 | 3 | 3 | 1766.0 | False | True | ok |
| suika | 连段B | 14 | 14 | 4 | 4 | 1860.0 | False | True | ok |
| suika | 连段C | 13 | 13 | 2 | 1 | 1000.0 | False | True | ok |

**合计: 39/50 PASS**（失败照实列；未用 proxy）
