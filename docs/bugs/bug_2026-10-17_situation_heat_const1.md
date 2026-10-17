# Bug: 情境库热度恒 1.0 — heat_weighted 查询返回空集(未修, P0)

- **发现**: 2026-10-17 从严审计分片(动态实证)+审查者亲验。
- **症状**: tools/situation_library.py:91 `d.get('hit_rate', 0.0)` 读的是
  behavior_health.aggregate 的 **raw combo_by_opp 条目**(四 fate 计数
  字典), `hit_rate` 仅 `rates()` 产物 — 键不存在恒取 0 → heat 恒 1.0。
  实测: reimu meta heat 全 1.0 而 raw 真实 vs-reimu hit_rate=0.038
  (应 0.962)。后果: `query(heat_weighted=True, matchup=<有热度对位>)`
  keep=rng<1-h=0 → **返回 0 行**(无热度对位正常) — LE-1b 注入入口对
  热点对位将拿到空集。
- **根因**: R153"排错②"只修了分母(sum(d.values())), 未修分子 —
  半修复(同 hit_rate 依赖未核)。
- **影响面**: 情境库 v1 的热度维度全部失真; LE-1b 未注入故尚未污染
  训练, 但注入入口已就位(踩雷前置)。
- **修复与验证**: 未修。修法: 先 d=rates(d) 再取 hit_rate(或直接由
  fate 计数算 hit/(hit+miss))。验证: vs-reimu heat≈0.96; heat_weighted
  查询非空。防复发: 情境库测试加"heat 不恒 1"断言(用合成 raw 数据)。
- **状态**: ✅**已修(2026-10-17 R154, 当日清偿)**: 分子改由fate计数
  直接算 hit/(sum(fates)) — vs-reimu heat=0.962(实测, 与raw hit_rate
  0.038对账✓); 防复发=测试加合成raw数据断言(heat≈0.97非恒1)+产物
  热度<1断言; 三库索引已重建。教训: **半修复之鉴 — 改了分母必须核
  分子的同源键依赖**(同函数内两个键读法, 一个修了一个漏)。
