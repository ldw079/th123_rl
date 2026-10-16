# Bug: untech 字段"锁定中"语义不成立 + comboDamage 方向语义未入档(✅已修 BH-4.2, 2026-10-15)

- **发现**: 2026-10-15 BH-4.1 BC 库对齐排查（用户指令"先排查一下bc库的问题"）。
- **症状/证据**:
  ① **untech>0 ≠ 对手被锁定**：萃香相关局 150 分片实测，"空中且
  untech≥9F"的 587,542 帧中，对手 action 属受击族(50-98)仅 **28.4%**；
  其余为自由行动——飞翔 214 占 16.0%、空中攻击 306/307/308/414 合计
  ~18%、大跳 208/209 ~6%、下落 9 占 4.5%。即该字段在对手自由空中
  行动时也有 >0 读数（残留值或非受击语义）。
  ② **comboDamage = 本角色造成的连段伤害(dealt)，非承受**：右方掉血
  （左方命中）的帧上 68:0 全部是 left.cd>0 ∧ right.cd==0。
- **影响面**(untech 污染，全部把 untech>0 当"对手不能动"用的消费方):
  - feat_builder untech 双侧特征（:685-686 附近）——模型 ~70% 的
    "对手空中untech>0"读数对应对手可自由行动，信号严重失真;
  - R30 untech-startup 逐宏块（train_tm:819-822，"正=来得及"目押
    判据）——同源污染;
  - update_combo_chain（train_tm:1525-1527，链维持判定）——对手已
    自由仍维持连段链;
  - train_tm:1599 门条件、E_COMBO_DROP 事件（"对手untech恢复"边沿）;
  - BC 库侧向量 untech 块（bc_build 同构）——锚同污染。
  comboDamage 方向本身对称暴露无害，但**任何当"被打指示"用的消费方
  都是反的**（本次排查的过滤用法即活例）；语义需入档防止再用错。
- **修复方向**: untech 消费一律加动作门（有效锁定 = untech>0 ∧
  action∈受击族 50-98；或等效的 action-untech 复合判据）。特征层
  改动零维度迁移；BC 库 untech 块值随之变化 → 与 matcher 连段语境
  标注改进（BH-4.3）合并进同一次重建。
- **验证**: ①合成：自由飞翔帧的"对手被锁"位=0、真受击帧=1；②oracle
  回放：受击族帧覆盖率与修复前一致性对照；③R30 块/combo chain 在
  known 连段窗口的行为测试。
- **状态**: ✅**已修（BH-4.2，2026-10-15 R140）**。实施与验证：
  - **单源门**: `feat_builder.eff_untech(side)` = untech>0 ∧ action∈
    HIT_ACT_IDS（R28权威集）。10处消费方全部过门：双侧untech特征/
    R30目押块(train_tm·bc_build·side_driver三拷贝)/update_combo_chain
    调用/E_COMBO_DROP与E_AIRTECH边沿/投技无敌tracker/空中被动豁免
    (抽为可测函数train_tm.air_passive_exempt)/macro_executor link门
    （后三者为bug档影响面之外的同型消费方，排查补齐）。
  - **comboDamage语义入档**: feat_builder特征位注释+测试断言
    （dealt非received，双侧对称透传）。
  - **验证①**: tests/test_untech_gate_bh42.py 35项全绿（门矩阵/
    特征位0与透传/事件边沿负正例/combo链维持与断链/豁免矩阵/
    comboDamage语义）；test_link_c3/lineB/throw_gate三套旧语义测试
    同步更新（受击族action基线+残留负例）。
  - **验证②**: oracle回放探针(tools/_untech_gate_probe.py, 12分片
    318,618对手帧): 原始untech>0占**51.7%**帧 → 门控后10.9%(残留
    滤除79%); **受击族帧38,049/38,049门控值=原始值(100%透传,
    纯过滤零失真)**。活性巡检(29+8段)通过。
  - **验证③**: combo chain行为测试在测试①内(真受击12帧链维持/
    自由行动12帧链断); link门目押窗口test_link_c3逐步恢复用例。
  - 门禁: 全量contract_check **630 PASS / 0 FAIL**; 3条BH-4.2变异
    登记tag实跑。
  - **生效时点**: fleet自然重启后生效(运行中进程用旧代码); BC库
    untech块保持旧值至BH-4.4重建(方案排期, 锚与策略特征的块级
    失配已裁定可容忍)。
