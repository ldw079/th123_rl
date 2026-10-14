# 从零全盘审查 #4(2026-10-14 晚)

> **基线**: HEAD `db5b6dd` + 在途工作区(diff 哈希 `753ac73`, 30 文件
> +1912 行, 快照时点 18:32; 施工会话持续活跃, 本审查只读未扰)。
> 方法: 4 零先验分片(A 训练主链/B 数据与BC链/C fleet治理/D 文档对账)
> + 审查者亲验全部 P0 与关键 P1 + 中央五项(门禁/编译/import/纪律横扫/
> 三面)。距 #3(10-12)约 20+ 波, 含 330→343 维度扩与 S 系心理博弈波。

## 总判定

**主干工程与数据链质量高, 但 S-2 波引入一项 P0 级特征大屠杀; fleet
治理在代际迁移期暴露两项 P0(日志实证的容量事故); 文档入口层集体
落后于实盘。** 共 P0×3 / P1×6 立档。

## P0(三项)

| # | 发现 | 证据 | bug 档 |
|---|---|---|---|
| 1 | **note_decision 吞并局级重置块** — 每决策点执行"跨局重置": 技能等级[230..233]/B风格段[316..329]/动量/动作历史等大片特征在训练+评估+BC三侧恒死, 自 S-2 波起 | 分片A动态复现(两次决策后 dim328/skill/动量归零)+审查者亲验源码(重置块注释自称"随局重置") | bug_2026-10-14_note_decision_reset_swallow |
| 2 | **fleet 重启耗尽=静默永久减员** — MAX_RESTARTS 耗尽仅 del, 无告警 | 日志实证: marisa actor 缺席 1.6h 无显眼告警 | bug_2026-10-14_restart_exhaust_silent |
| 3 | **BC 宽度失败不对称** — actor 硬 assert 崩溃 vs learner 响亮跳过; 迁移期 BC 未重建=连环崩→耗尽(与#2 构成根因链) | 日志实证(16:12-16:13 连环崩)+两侧代码对照 | bug_2026-10-14_bc_width_asymmetry |

## P1(六项)

| # | 发现 | 档 |
|---|---|---|
| 4 | 宏门截断清 dec_name → 空挥罚对 12 branch 宏+confirm 族系统性豁免 | bug_2026-10-14_gate_whiff_exempt |
| 5 | 探针决策 stored_logp 记 π 而非混合分布 — ratio 系统性有偏(红线①债, 代码自知) | bug_2026-10-14_probe_logp_mixture |
| 6 | 门后延续 families 硬编码 mirror=False — 左朝向段系统性错标(动态+亲验) | bug_2026-10-14_continuation_mirror_hardcode |
| 7 | S-2 离线注入未来信息泄漏(sidecar 在 end 后快照)+在线离线 build/note 顺序分歧(维336/338 标签泄漏) | bug_2026-10-14_s2_offline_leakage |
| 8 | W4 价值曲线自上线即死(2D 未 reshape, 日志 114/147 次异常, 恒空) | bug_2026-10-14_value_curve_dead_on_arrival |
| 9 | danger_reveal 真实模式 KeyError(RESERVED 缺键, 测试只盖 mock) | bug_2026-10-14_danger_reveal_port_key |

## P2(择要; 详见分片结论)

- CPU watchdog 震荡(32min 内降容-恢复往返 8 次, 滞后带/窗口参数偏紧);
  attribution_probe 死计数器; danger_reveal run_real 无 finally;
  ppo.py:145 类默认 N_SIDE 残留 308 公式(兜底路径); ppo_gpu.sample
  无 return_pred(潜伏); 评估侧无事件掩码(与训练分布不对称, 设计性);
  bc_io verify 未查 S 行数/npz 回退无校验; data/bc 旧 330 库误用风险;
  bc_swap 宽度 assert 硬编码 {70,76,77}; K5 角色识别未接线(dim342
  恒0, 已知档); 跨局 _punish_active 残留一拍。

## 中央五项

| 项 | 结果 |
|---|---|
| 门禁 | 618 PASS/2 WARN/**1 FAIL**(FAIL=沙箱 FILES 结构防线拦截在途测试注册缺口 — 防线正常工作, 提交前须清) |
| 编译+import | 70 模块 0 失败 |
| 纪律横扫 | 330 字面量合法; 原子落盘/单写者抽验过; 62fps 无违例 |
| 三面对账 | fleet 运行(12 进程, 18:32); CPU 看门狗活跃(90%→降容→恢复); harvest 768 TR 局/861 万帧/err=0 健康 |
| 文档对账 | 见分片D: HANDOVER 门禁数字失真(600 vs 618/2/1)、AGENTS 整份停在 10-11(330/568)、README(330/37档 vs 70)、INDEX 三失链+计数错、matcher_mask_polarity 档状态未回填(实际已修) |

## 与 #3 的对照

#3 病根"单元测试过、集成缝断"仍成立, 本轮新增两个变体:
**"重置块搬家"(状态机重构时语义块被错并)** 与 **"单源表的两半不同步"
(RESERVED/门禁注册)**。另: #3 后修复质量普遍高(ppo 梯度/trio 锁/镜像
双侧), 但 S-2 大波的特征活性回归没有任何测试/仪表拦截 — 重申
"特征活性巡检"仪表建议(与 #3 的 FILES 完备性根治断言同级的结构防线)。

## 建议(待用户指令, 审计不修)

1. P0-1 优先(一行级修复但影响全部在训数据语义; 修复后 S-2 的 A/B
   需重开基线)。2. P0-2/3 与部署序列硬门禁一起修(点火预检加 BC 宽度)。
3. P1 批随下波。4. 文档入口层(HANDOVER/AGENTS/README/INDEX)在
   343 波合入时一次性对齐。5. 特征活性巡检仪表立项(防复发级)。
