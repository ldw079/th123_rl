# Bug 归档制度(用户 2026-10-12 指令固化)

> **每个 bug 一律整理为文档**(用户明令)。归档目录: `docs/bugs/`。
> 与宪法 §10"事故→制度清单"的关系: §10 保留单行索引, 本目录是展开层
> (完整可追溯档案); 每个入册教训应能链到对应 bug 档。

## 规则

1. **发现即立档**: bug 确认当场创建 `docs/bugs/bug_YYYY-MM-DD_<slug>.md`
   (slug 短横线英文)。未修复也立档, 状态标"未修", 修复后回填。
2. **必含七字段**:
   | 字段 | 要求 |
   |---|---|
   | 发现 | 时刻 + 场景(谁在做什么时发现, 含触发数据/命令) |
   | 症状 | 报错原文/错误行为实录, 不转述 |
   | 根因 | 定位到代码行; 是设计错/集成缝/共享常量错要分型 |
   | 引入 | 定位到 commit/波次(新债还是历史潜伏) |
   | 影响面 | **受污染的量化结论与产物逐一点名并显式作废**, 指向更正处 |
   | 修复与验证 | 修法 + 独立验证方式(实测输出/测试结果) |
   | 防复发 | 配对测试/门禁锚/变异钉; 说明盲区(如"断言与实现同错变异测不出") |
3. **结论作废纪律**: bug 波及的历史结论(基线/报告/文档记载)必须在影响面
   字段点名作废; 被作废结论所在的归档档(如 docs/audit/)不改写原文, 补
   更正注指向 bug 档。
4. **互链**: 审计报告(docs/audit/)挖出的 bug 链到本目录; bug 修复后的
   验证若构成一次审计, 链回。
5. **防复发优先用独立标定**: 涉及"工具解读数据"类 bug, 修复测试不得与
   实现共享常量(共享常量错 = 变异盲区), 应走真实生产路径标定
   (参照 bug_2026-10-12_b3_adx_column 的 feat_builder 标定测试)。

## 索引(按时间序)

- `bug_2026-10-12_b3_adx_column.md` — B3 距离列号误用站位(R67c 修复, 溯及归档)
- `bug_2026-10-12_b3_empty_window_keyerror.md` — B3 报告空窗 KeyError(R67d 已修, 顺带修出delta-0.0误报None)
- `bug_2026-10-12_far_passive_zero_far_fallback.md` — 远距被动零远距帧 or-seq 兜底静默退旧口径(未修, 低; R79 遗留边界)
- 从零审查#3(2026-10-12)六项 P1 批量立档(详见 docs/audit/audit_2026-10-12_from_zero_3.md):
- `bug_2026-10-12_selftest_sandbox_stale.md` — 变异自检失效:沙箱FILES缺series_manager+死变异×2(未修)
- `bug_2026-10-12_side_driver_dec_name.md` — 对手侧R34守备豁免恒失效(未修)
- `bug_2026-10-12_throughput_tab_path.md` — 吞吐报告路径TAB字节→fleet合计恒0(未修)
- `bug_2026-10-12_habits_retract_nowriter.md` — habits_retracted无代码写入点,提交宣称与实现不符(未修)
- `bug_2026-10-12_ppo_dual_impl_grad.md` — 双实现梯度接合点不等价(vf_adam混代+cap反向不完整)(未修)
- `bug_2026-10-12_trainstart_killall_th123.md` — train_start无差别杀th123误伤原版局/离线重放(未修)
- `bug_2026-10-13_gate_anchor_or_true.md` — 门禁恒真死锚or True(R84引入, 未修)
- `bug_2026-10-13_sandbox_files_drift2.md` — 沙箱FILES二次漂移: value_curve未收录, P1-1同型复发(未修)
- `bug_2026-10-13_memexp_no_finally.md` — mem_input_experiment无finally, 异常残留夺权用户游戏(未修, P2)
- 重开: bug_2026-10-12_side_driver_dec_name — R80为假修复(入队处漏赋宏名, 恒None)
- dist专项(2026-10-13): `bug_2026-10-13_kit_store_hardcode.md` — kit硬编码本机store, 打包模型从未被使用(未修, P1)
- `bug_2026-10-13_kit_export_strftime.md` — 导出文件名恒定互相覆盖(未修, P2)
- `bug_2026-10-13_hm2_opp_char_blind.md` — 人测通道对手角色不识别, opp_char_id恒None特征失配, R91盲打(未修, P1)
- rep→宏专项(2026-10-14): `bug_2026-10-14_matcher_mask_polarity.md` — v3方向轴掩码极性反转, 前进/后退不可区分(P0, 在途未提交, 合入前截获)
- `bug_2026-10-14_matcher_neutral_absorption.md` — 纯按钮宏吞方向变体, 平局缺特异性优先(P1, 在途)
- `bug_2026-10-14_bc_trio_swap_lock.md` — BC trio换装无停机硬门禁+mmap句柄锁+集合非原子=混代际库风险(P1, 在途)
