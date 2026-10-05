# 隔离区(第八轮审查§7)

移入日期: 2026-09-24。原因与去向:

- **死工具**(consistency_audit / determinism_check / input_loss_analysis /
  pairing_test / rep_observe_session / rep_distill):
  对不存在的API编写、空样本即PASS、零门禁零调用者; rep_distill 另有
  R1(重放对手输入)/R4(编造常量列)/Y≡-1 schema 问题。
  **正统替代 = 神谕管线**(oracle_batch.py: 游戏原生自播+被动状态流,
  2026-09-24 用户批准, 191局全量验证 67/67 比分一致)。
  在 R1/R7 裁定正式落档前, 本区任何脚本不得运行、不得并入 live 产物。
- **一次性诊断脚本**(diag_* / oracle_drive / oracle_tps_test / oracle_validate):
  同步问题调查期的取证工具, 已完成使命, 留档备查。

保留在 tools/ 的活跃工具: contract_check, gate_selftest, hitlab_probe,
reseed_macro_counts, runtime_masking_probe, update_provenance, rep_observer。
