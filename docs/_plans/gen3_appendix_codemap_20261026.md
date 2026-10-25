# 附录 A：代码地图与事故映射（Gen-3 输入，只读）

## A.1 env 动物园（C2 证据）
- `TH123_*` 唯一名: **98**；跨文件重复名: **62**
- 重复示例（名 → 读取文件数）:
  - `TH123_STORE` ×44: actor_worker.py, bc_io.py, exploiter.py, fleet_supervisor.py
  - `TH123_MEM_DECISIONS` ×12: episode_core.py, learner_hub.py, mem_v1.py, ppo_gpu.py
  - `TH123_BATCH_K` ×6: learner_hub.py, tests\test_detach_v1.py, tests\test_task39_v1.py, tools\contract_check.py
  - `TH123_EXEC_HITMEM` ×6: macro_executor.py, side_driver.py, tests\test_executor_hitmem_v1.py, tools\combo_replay_check.py
  - `TH123_VAL_DEACT` ×6: mem_v1.py, ppo.py, ppo_gpu.py, tests\test_val_deact_v1.py
  - `TH123_BCW_MIN` ×6: ppo_gpu.py, tests\test_bcw_env.py, tests\test_detach_v1.py, tools\contract_check.py
  - `TH123_BUFFER` ×5: buffer_primitives.py, game_gates.py, tests\test_buffer_v1.py, tests\test_detach_v1.py
  - `TH123_FEAT_SPACE` ×5: feat_builder.py, tests\test_space_feat_v1.py, tools\contract_check.py, tools\gate_selftest.py
  - `TH123_BATCH_MIN_GAMES` ×5: learner_hub.py, tests\test_detach_v1.py, tests\test_p1gen1_v1.py, tools\contract_check.py
  - `TH123_ORACLE_SHARDS` ×4: bc_build.py, tools\combo_mine_positional.py, tools\mine_air_moves.py, tools\mine_input_moves.py
  - `TH123_BC_DIR` ×4: bc_build.py, tools\contract_check.py, tools\gate_selftest.py, tools\gate_selftest_parallel.py
  - `TH123_BC_HASH_CACHE` ×4: bc_io.py, tests\test_bc_io.py, tools\contract_check.py, tools\gate_selftest.py

## A.2 关键模块定位

**Gate/掩码**: frame_events.py:60; frame_events.py:223; frame_events.py:224; frame_events.py:236; frame_events.py:237; frame_events.py:304; frame_events.py:307; frame_events.py:308

**Episode schema**: bc_build.py:33; episode_core.py:26; episode_core.py:29; episode_core.py:47; episode_core.py:225; episode_core.py:279; episode_core.py:281; episode_core.py:291

**PPO 双实现（numpy/torch 漂移）**: actable_state.py:32; buffer_primitives.py:75; feat_builder.py:322; feat_builder.py:1071; learner_hub.py:220; opp_model.py:173; perception.py:176; ppo.py:127

**特征魔术索引/CORE**: actor_worker.py:162; bc_build.py:50; bc_build.py:53; bc_build.py:443; bc_build.py:447; bc_build.py:450; bc_io.py:182; episode_core.py:56

**奖励/env 开关**: atk_v1.py:5; atk_v1.py:6; atk_v1.py:7; atk_v1.py:8; atk_v1.py:9; atk_v1.py:10; atk_v1.py:11; atk_v1.py:12

**迁移脚本**: bc_label_migrate.py, bc_meta_resync.py, migrate_bc_b.py, migrate_feat_space_v1.py, migrate_gen2.py, migrate_macros_wave.py, migrate_p1gen1.py, migrate_s2_343.py, migrate_style_b.py

**launcher/启停**: launcher.py, train_detach.py, train_detach.py, train_start.py

- 行为测试档: **118**

## A.3 事故 → 债务映射
- **P1 plain 未同步（过招模型旧宽）** → `C1-2/C1-3/C1-7`：plain 模型 pre-GEN2 宽；用途矩阵未定义
- **822↔831 混代际（GEN2 迁移期）** → `C1-3/C1-4/C1-7`：BC/模型宽度多代并存，需注册表 gen
- **BC trio meta 哈希不一致（已修）** → `C1-4`：缺统一 verify；历史修复无强校验
- **窗口 env 变量混淆（C1/C2 窗口）** → `C2-1/C2-3/C2-6`：98 env/51 重复；无 manifest hash
- **`_buf_cnt` actor 崩-loop（a8d23cb）** → `C3-5`：gate/仪器接线无真实帧回归
- **confirm gate 语义（frozen 帧丢伤害）** → `C3-5`：gate 状态语义无 golden
- **episode schema 漂移（v1/v2/v3）** → `W4`：schema 契约散落；无显式 valid mask/registry hash
- **运维 launcher 手工（WMI/schtasks）** → `C2-6/ops`：无统一 launcher+manifest hash
