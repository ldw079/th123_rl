# C79-8 严格 lab v2（逐 scene; 2026-10-27）

- target_damage = 历史 p4 最大伤害 ×0.9（容差 10%，来源逐条标注）；无历史目标 → target_undefined 不判 pass。

| 角色 | combo | scene | planned | executed | segments | hits | dmg | target | pass | reason |
|---|---|---|---|---|---|---|---|---|---|---|
| reimu | TM·2a连 | 0 | 4 | 12 | 3 | 6 | 550.0 | 495.0 | True | ok |
| reimu | TM·4a连 | 0 | 4 | 10 | 2 | 3 | 1579.0 | 1421.1 | True | ok |
| reimu | 压起身·即 | 0 | 4 | 4 | 1 | 6 | 550.0 | 495.0 | True | ok |
| reimu | 压起身·延迟 | 0 | 5 | 5 | 4 | 4 | 1555.0 | 1399.5 | True | ok |
| reimu | 压起身·空 | 0 | 3 | 3 | 1 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| reimu | 压起身·空 | 1 | 3 | 3 | 1 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| reimu | 压起身·穿 | 0 | 3 | 3 | 1 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| reimu | 原子·地面链 | 0 | 7 | 7 | 4 | 8 | 1223.0 | 1100.7 | True | ok |
| reimu | 原子·收尾 | 0 | 5 | 5 | 3 | 6 | 550.0 | 495.0 | True | ok |
| reimu | 原子·确认5A | 0 | 3 | 4 | 3 | 3 | 821.0 | 738.9 | True | ok |
| reimu | 原子·空链 | 0 | 7 | 7 | 2 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| reimu | 原子·空链 | 1 | 7 | 7 | 2 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| reimu | 择·下段 | 0 | 5 | 5 | 3 | 6 | 550.0 | 495.0 | True | ok |
| reimu | 择·中段 | 0 | 4 | 4 | 2 | 1 | 600.0 | 540.0 | True | ok |
| reimu | 择·投 | 0 | 4 | 4 | 2 | 1 | 200.0 | 180.0 | True | ok |
| reimu | 版边连A | 0 | 18 | 18 | 6 | 7 | 1663.0 | 1496.7 | True | ok |
| reimu | 连段A | 0 | 16 | 16 | 5 | 4 | 1510.0 | 1359.0 | True | ok |
| reimu | 连段B | 0 | 16 | 16 | 5 | 4 | 1510.0 | 1359.0 | True | ok |
| reimu | 连段C | 0 | 14 | 14 | 5 | 4 | 1406.0 | 1265.4 | True | ok |
| marisa | B6C连 | 0 | 9 | 9 | 2 | 15 | 2549.0 | 2294.1 | True | ok |
| marisa | TM·6a终结 | 0 | 6 | 6 | 1 | 1 | 900.0 | 810.0 | True | ok |
| marisa | TM·必杀SC连 | 0 | 10 | 10 | 1 | 1 | 1250.0 | 1125.0 | True | ok |
| marisa | 压起身·即 | 0 | 4 | 4 | 1 | 1 | 450.0 | 405.0 | True | ok |
| marisa | 压起身·延迟 | 0 | 5 | 5 | 3 | 3 | 937.0 | 1566.9 | False | ok;dmg<target |
| marisa | 压起身·空 | 0 | 3 | 3 | 1 | 1 | 900.0 | 810.0 | True | ok |
| marisa | 压起身·空 | 1 | 3 | 3 | 1 | 0 | 0.0 | 810.0 | False | no_hit;dmg<=0;dmg<target |
| marisa | 压起身·穿 | 0 | 3 | 3 | 1 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| marisa | 原子·地面链 | 0 | 12 | 12 | 5 | 16 | 2920.0 | 2628.0 | True | ok |
| marisa | 原子·收尾 | 0 | 5 | 5 | 3 | 1 | 450.0 | 405.0 | True | ok |
| marisa | 原子·确认5A | 0 | 3 | 3 | 1 | 1 | 200.0 | 180.0 | True | ok |
| marisa | 原子·空链 | 0 | 10 | 10 | 3 | 0 | 0.0 | 900.0 | False | no_hit;dmg<=0;dmg<target |
| marisa | 原子·空链 | 1 | 10 | 10 | 3 | 0 | 0.0 | 900.0 | False | no_hit;dmg<=0;dmg<target |
| marisa | 择·下段 | 0 | 5 | 5 | 3 | 1 | 1000.0 | 900.0 | True | ok |
| marisa | 择·中段 | 0 | 4 | 4 | 2 | 1 | 550.0 | 495.0 | True | ok |
| marisa | 择·投 | 0 | 4 | 4 | 2 | 1 | 200.0 | 180.0 | True | ok |
| marisa | 连段A | 0 | 13 | 13 | 4 | 4 | 2151.0 | 1935.9 | True | ok |
| marisa | 连段B | 0 | 15 | 15 | 7 | 14 | 2340.0 | 2106.0 | True | ok |
| marisa | 连段C | 0 | 14 | 14 | 5 | 4 | 1277.0 | 2129.4 | False | ok;dmg<target |
| suika | TM·对空连 | 0 | 15 | 15 | 3 | 5 | 1975.0 | 1777.5 | True | ok |
| suika | TM·对空连 | 1 | 15 | 5 | 1 | 0 | 0.0 | 1777.5 | False | no_hit;dmg<=0;dmg<target |
| suika | TM·空连终结 | 0 | 16 | 6 | 2 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| suika | TM·空连终结 | 1 | 16 | 6 | 2 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| suika | 压起身·即 | 0 | 4 | 4 | 1 | 1 | 550.0 | 495.0 | True | ok |
| suika | 压起身·延迟 | 0 | 5 | 5 | 3 | 3 | 1766.0 | 1589.4 | True | ok |
| suika | 压起身·空 | 0 | 3 | 3 | 1 | 2 | 1289.0 | 1160.1 | True | ok |
| suika | 压起身·空 | 1 | 3 | 3 | 1 | 0 | 0.0 | 1160.1 | False | no_hit;dmg<=0;dmg<target |
| suika | 压起身·穿 | 0 | 3 | 3 | 2 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| suika | 原子·地面链 | 0 | 8 | 8 | 3 | 4 | 1751.0 | 1575.9 | True | ok |
| suika | 原子·收尾 | 0 | 5 | 5 | 3 | 1 | 550.0 | 659.7 | False | ok;dmg<target |
| suika | 原子·确认5A | 0 | 3 | 3 | 1 | 1 | 500.0 | 450.0 | True | ok |
| suika | 原子·空链 | 0 | 7 | 7 | 2 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| suika | 原子·空链 | 1 | 7 | 7 | 2 | 0 | 0.0 | 0.0 | False | no_hit;dmg<=0;dmg<target |
| suika | 择·下段 | 0 | 5 | 5 | 3 | 1 | 550.0 | 495.0 | True | ok |
| suika | 择·中段 | 0 | 4 | 4 | 2 | 2 | 1071.0 | 963.9 | True | ok |
| suika | 择·投 | 0 | 4 | 4 | 2 | 1 | 500.0 | 900.0 | False | ok;dmg<target |
| suika | 连段A | 0 | 13 | 13 | 3 | 3 | 1766.0 | 981.9 | True | ok |
| suika | 连段B | 0 | 14 | 14 | 4 | 4 | 1860.0 | 1674.0 | True | ok |
| suika | 连段C | 0 | 13 | 13 | 2 | 1 | 1000.0 | 1690.2 | False | ok;dmg<target |

**合计: 37/58 行 pass（含 target_undefined 未判）**
