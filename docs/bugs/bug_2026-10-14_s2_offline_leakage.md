# Bug: S-2 离线注入的未来信息泄漏 + 在线/离线顺序分歧(未修, P1)

- **发现**: 2026-10-14 从零#4 分片B(动态核)。
- **症状**: ①expert_punish_track.py:75-79 — sidecar 的 rows_rate 快照
  取在 `tracker.end()` **之后** → 帧 f 的特征已含宏 f 自身的被反制结局
  (未来信息); ②bc_build.py:350 `note_decision` 在 `fb.build`(:360)
  之前, 而在线 train_tm 先 build(:1623)后 note(:1805) → 维336(含当前
  streak)/338(换类) 离线含当前标签、在线不含 — **标签经维度泄漏给
  BC 锚** + 在线离线分布分歧。
- **影响面**: BC 锚的 S-2 行特征带未来信息(bcw 拉力方向性偏差);
  离线/在线同维不同义。
- **修复与验证**: **已修(2026-10-14晚)**: ①expert_punish_track快照移到
  tracker.begin前(先验率, 不含本宏结局)+旧761份sidecar挪punish_post_rate_bak
  三路并行全量再生(--part i/k); ②bc_build改先build后note(对齐在线
  :1623/:1805时序, 维336/338不再含当前标签)。验证: 混合边际同型
  断言在test_probe_logp_p1(分布侧); BC行级逐位比对随三库重建验收。
- **状态**: ✅已修(2026-10-14晚; sidecar再生+BC三库重建随本波落地)。
