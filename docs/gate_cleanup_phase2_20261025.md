# 门禁清理 phase-2 清单（2026-10-25，R15 红线分组）

## 规则
- 每条按 R15: ①可转行为(优先) ②账本类保留需写理由 ③建议删除需 Lead 批；
- 不擅自删覆盖；转换须附行为基座证据（真实帧/手动基准/合成状态行为断言）。

## 纯 src 断言（无行为基座）: 106 条

| # | 断言消息 | src 文件 | 建议 |
|---|---|---|---|
| 1 | _build_side", "core[33] = "),
    "turn_recency写core[33](P0-2修复在位) [_build_side体内]")
fb_src_nospace = src("fea | feat_builder.py | 待 auditor 分级 |
| 2 |  | soku_client2.py | 待 auditor 分级 |
| 3 |  | tm_env.py | 可转行为(env 解析/启动行行为) |
| 4 |  | ppo.py | 待 auditor 分级 |
| 5 | classify攻击区间=枚举精确(R28)")
# R56(fleet F4): distill逻辑抽出至episode_core.save_distill_rows
# (train_tm._save_distill | episode_core.py,opp_model.py | 待 auditor 分级 |
| 6 |  | feat_builder.py | 待 auditor 分级 |
| 7 | mod_provenance.json存在(重编mod后跑tools/update_provenance.py)")
if os.path.exists(prov_path):
    with io.open(prov | outer_loop.py,side_driver.py | 待 auditor 分级 |
| 8 | D14回归哨兵")
# 三库源始字面断言(非规范化产物 — 变异真正打得到的地方)
mc_src = src("macros/__init__.py")
mm_src = src("macros/marisa.py")
 | macros/__init__.py,macros/marisa.py,macros/suika.py | 待 auditor 分级 |
| 9 | G2(R77): tm_env渲染/变速用命名opcode(裸2/3字面量退役) | tm_env.py | 可转行为(env 解析/启动行行为) |
| 10 | G2(R77): branch_demo局面控制opcode收编soku_client2 | tools/branch_demo.py | 可转行为(执行器/gate 帧序) |
| 11 | hitlab端口在段内(20920-20939) | tools/hitlab_probe.py | 待 auditor 分级 |
| 12 | __init__",
           "self.lsock.settimeout(accept_timeout)")
    and fn_has("soku_client2.py", "__init__", " | outer_loop.py | 待 auditor 分级 |
| 13 |  | run_parallel.py | 待 auditor 分级 |
| 14 | _run_episode",
           "mask = mask & ~self.air_combo_idx"),
    "空连门控操作行在位(R23) [_run_episode体内]")
sd_src  | side_driver.py | 账本类(保留需理由) |
| 15 | _build_side",
           "(_adx - self.macro_reach) / 200.0"),
    "射程差特征块在位(R24) [_build_side体内]")
sd2 = src( | side_driver.py | 待 auditor 分级 |
| 16 | 脚本签名推导已删(R29: 状态依赖招无法区分, 受身/4A同签名)")
# R25(用户2026-10-02: 弹幕复杂化+判定二维): 运动学/地雷/追踪/纵向 — F2批2锚定
fb_src = src("feat | feat_builder.py,reach_maps.py | 待 auditor 分级 |
| 17 |  | ppo.py | 待 auditor 分级 |
| 18 | SKILL_MAP三处错位修复在位(R39§4-4: 102亜空穴=22系/106 Torch=22系/108踏鞴=214系)")
# ============ R40(第十一轮): INPUTLOG精确对齐通道 + m | oracle_batch2.py | 待 auditor 分级 |
| 19 | run_one",
           "'SOKUAI_INPUTLOG_PATH': ilog_path"),
    "inputlog路径按shard隔离(R40: 并行车道不互写) [run_one体内]") | bc_build.py | 账本类(保留需理由) |
| 20 |  | reach_maps.py | 待 auditor 分级 |
| 21 | 监督器正常完成分支eps按str格式化(R42: 原%d首触即崩, 监督器裸奔)")
# ============ R43(2026-10-04): 池刷新制度 + COM难度阶梯 ============
tt43 = | run_parallel.py,train_tm.py | 待 auditor 分级 |
| 22 | COM难度阶梯在位(R43-B: 20局≥50%升/40局<20%降, 课程学习)")
rp43 = src("run_parallel.py | run_parallel.py | 待 auditor 分级 |
| 23 | %s_SKILL_MACROS' % c.upper())
        and '236B' not in getattr(__import__('macros.%s' % c, fromlist=['*']),
  | train_tm.py | 待 auditor 分级 |
| 24 | BC锚允许归零(R47天花板3: 原0.05永不归零→永久人类风格拉力) | ppo.py | 待 auditor 分级 |
| 25 | tm_env支持双deck(R47: P1/P2各自独立卡组) | tm_env.py | 可转行为(env 解析/启动行行为) |
| 26 |  | ppo_gpu.py | 待 auditor 分级 |
| 27 | League胜率加权选择在位(R48: fictitious play) | league.py | 待 auditor 分级 |
| 28 | 教学层局面讲解+批量反查在位(R48)")
# ============ R53(第十七轮§S1/S3): 行为断言升级 ============
te53 = src("tm_env.py | teach.py,tm_env.py | 可转行为(env 解析/启动行行为) |
| 29 | 续局不含单deck(R53§S1: bytes(self.deck)应全部替换)")
gp53 = src("ppo_gpu.py | ppo_gpu.py | 待 auditor 分级 |
| 30 | 帧级事件检测+反应选择在位(R49: 攻略帧窗驱动) | frame_events.py | 待 auditor 分级 |
| 31 | 攻略帧窗表+事件枚举在位(R49: DD 15F/插动12F等) | frame_events.py | 账本类(保留需理由) |
| 32 | _run_episode", "int(_fwin)")
    and "FRAME_WINDOWS" in src("frame_events.py"),
    "J裁定(2.72): 事件窗_fwin显式消费入日 | frame_events.py | 待 auditor 分级 |
| 33 |  | feat_builder.py | 待 auditor 分级 |
| 34 | 下段位=显式查表(R57 2.5; BH-3.2后回落表=303/311 — 2B/2C虚报按 "
    "cleista 20/20实测移除[P2清偿, 审计2026-10-16]; 真值=guard_height逐 | feat_builder.py | 账本类(保留需理由) |
| 35 | 下段位接线: 对手当前招式查表(BH-3.2: 逐角色LOW表经_low_ids, "
    "原LOW_ATTACK_IDS直引锚已随R141迁self._low_ids) | feat_builder.py | 账本类(保留需理由) |
| 36 | f变体位=显式查表(R58 P1-a: 近/远A可分; 权威全集仅f5A/f2A — "
    "改进方案示例集含321=5AAA/331=诹访子专属, 按空表优于错表只取两枚) | feat_builder.py | 账本类(保留需理由) |
| 37 | f变体位接线: 段11[o+20..o+21](R58 — 池扩展余位, 零扩维)")
# R61h(C2): frame_macros已删 — 其宏零消费者(反应表匹配角色库名,
# 非独立宏), DD与角色库重复/投 | feat_builder.py,ppo.py | 账本类(保留需理由) |
| 38 | 原子宏配额延长150→1000(R50 A4: 零logit鸡生蛋破解)")
fe50 = src("frame_events.py | frame_events.py,train_tm.py | 待 auditor 分级 |
| 39 | R61l(B2): 事件反应决策化(掩码交集→策略选→决策后清除; "
    "R51守式模式已废 — 反应决策入轨迹获信用) | train_tm.py | 待 auditor 分级 |
| 40 |  | side_driver.py | 待 auditor 分级 |
| 41 | reset_match", "self._last_inp"),
    "门步保持上一拍输入(P2-7同款) [reset_match体内]")
# 从零审查D6-D8余项(2026-09-23) — F2收官: 函数 | soku_client2.py | 待 auditor 分级 |
| 42 | FAULT独立异常(D7: 崩溃穿透容忍层带地址) [类定义, 合理文本钉]")
te = src("tm_env.py | tm_env.py | 可转行为(env 解析/启动行行为) |
| 43 |  | ppo_gpu.py | 待 auditor 分级 |
| 44 | run_learner", "check_model_generation(char, n_out)")
    and fn_has("learner_hub.py", "run_learner", "拒绝启动"),
 | train_tm.py | 可转行为(env 解析/启动行行为) |
| 45 |  | fleet_supervisor.py | 待 auditor 分级 |
| 46 | R63(F6): 旧的'胜率减方差'占位公式已从**可执行代码**中清除"
    "(注释/文档引用不算 — 自测抓出全文本匹配会判红自身注释)")

# ---- R60(从零审计F-1..F-11) ----
tt | ppo.py,ppo_gpu.py,side_driver.py,train_tm.py | 账本类(保留需理由) |
| 47 | R61f/D5: supervisor孤儿回收(WMI父进程判定) | fleet_supervisor.py | 待 auditor 分级 |
| 48 |  | league.py | 待 auditor 分级 |
| 49 | sc_press_bits", "SC_PRESS_F"),
    "R61g: sc:步展开为SC按压词汇(原结构性排除=SC标签恒0%) [sc_press_bits体内+常量] | bc_match.py | 待 auditor 分级 |
| 50 |  | bc_build.py | 待 auditor 分级 |
| 51 | P1(审计#6): 池序→角色名映射由 _CHAR_POOL_IDX 反演(20/20, 非游戏ID) | side_driver.py | 待 auditor 分级 |
| 52 |  | fleet_supervisor.py,ppo_gpu.py,tools/train_start.py | 待 auditor 分级 |
| 53 | LE-0a: 孤儿回收/前置清理查询逐处含对照臂豁免(禁误杀LE-0a)",
    "训练python查询数=%d" % _le0a_seen)
# H-1(2026-10-19 心跳实证): wd 夜内 8 次 0. | fleet_supervisor.py | 待 auditor 分级 |
| 54 | H-1: wd 0.00 拒收守卫(Δ族CPU≤0→None哨兵)+连续2次恢复门控+第3字段计数")
# task-18(2026-10-19): 门禁证据产物一次写入不可复写 —
# 命名 gate_r<rev>_< | tools/run_gate_evidence.py | 账本类(保留需理由) |
| 55 | task-18: 门禁证据命名含rev/commit/ts + O_EXCL一次写入(禁复写)")
# task-15(2026-10-19): 人测通路修正 — 0x34C 角色自动识别 + 活档链 +
# set_o | tools/human_match_v2.py | 待 auditor 分级 |
| 56 | task-15: 人测通路(0x34C识别+活档链+set_opponent(P1)+probe只读)生效本体")
# task-21 v1(2026-10-19 用户批): 空间 24 维(2D 绝对+相对) + Ph | feat_builder.py | 待 auditor 分级 |
| 57 | task-21: 归一化公式(my_y/opp_dist/弹2TTI)")
_tm21 = src("train_tm.py | train_tm.py | 待 auditor 分级 |
| 58 |  | train_tm.py | 待 auditor 分级 |
| 59 | task-21: BC env=1 允许旧宽(训练+点火+learner 三处 zero-fill v2)")
# A1/A2(CPU-H P-B/P-C, 2026-10-19 用户裁定): L0 整机/旁路口径 +  | fleet_supervisor.py,learner_hub.py,tools/train_start.py | 可转行为(env 解析/启动行行为) |
| 60 | A1/A2: L3 machine_alert+heavy.stop; 不杀 fleet")
_dash = src("tools/status_dashboard.py | tools/status_dashboard.py | 待 auditor 分级 |
| 61 | A1/A2 P-C: 重型工具(bc_build/eval_matrix/audit_all)经 load_gate")
# task-16(2026-10-19): behavior_deep_report 三表工具入 | bc_build.py,tools/audit_all.py,tools/behavior_deep_report.py | 账本类(保留需理由) |
| 62 | task-29/30: env 三开关 + env=0 逐位回滚分支')
# Gen-1(2026-10-20): 决策历史记忆 v1 + W_mem + ep v3 + 批环境.
_mv = src('mem_v1.p | actor_worker.py,episode_core.py,learner_hub.py,mem_v1.py,ppo | 可转行为(env 解析/启动行行为) |
| 63 |  | tools/combo_replay_check.py | 可转行为(执行器/gate 帧序) |
| 64 |  | macro_executor.py,side_driver.py,tools/combo_replay_check.py | 可转行为(执行器/gate 帧序) |
| 65 |  | tools/train_detach.py | 待 auditor 分级 |
| 66 |  | ppo_gpu.py | 待 auditor 分级 |
| 67 | task-53: preflight 挂起超时中止(启动不被挂起阻塞) | tools/train_start.py | 可转行为(env 解析/启动行行为) |
| 68 |  | tools/gate_selftest_parallel.py | 可转行为(执行器/gate 帧序) |
| 69 | task-53: 看门狗(日志停滞→重启 / games<4 告警) | fleet_supervisor.py | 待 auditor 分级 |
| 70 | task-54: BC trio 哈希缓存(mtime_ns+ctime_ns 戳) | bc_io.py | 待 auditor 分级 |
| 71 | task-54: stale match flag 清理 + boot 超时 env | tm_env.py | 可转行为(env 解析/启动行行为) |
| 72 | task-52: 方向受身 env(UKEMI_DIR)接线 | game_gates.py | 可转行为(env 解析/启动行行为) |
| 73 |  | tools/bc_meta_resync.py | 账本类(保留需理由) |
| 74 |  | learner_hub.py | 待 auditor 分级 |
| 75 |  | learner_hub.py,mem_v1.py,ppo.py | 待 auditor 分级 |
| 76 |  | feat_builder.py | 待 auditor 分级 |
| 77 | CE-1宏层画像生产接线(两调用点传name=宏名; 上线即自检制度化) | side_driver.py,train_tm.py | 待 auditor 分级 |
| 78 | P2: 平局三态(原平局记右方胜) | tools/eval_matrix.py,tools/human_match.py | 待 auditor 分级 |
| 79 | P2: GPU侧ratio差值±20钳制(与numpy对齐) | ppo_gpu.py | 待 auditor 分级 |
| 80 | P2: BC库savez原子落盘(宪法§5.2) | bc_build.py | 待 auditor 分级 |
| 81 | 沙箱FILES覆盖全部行为测试的根模块imports(P1-1类复发的结构防线)",
    str(sorted(set(_bad))[:6]))

_fs_src = src("fleet_supervisor.py | fleet_supervisor.py | 账本类(保留需理由) |
| 82 | P2: actor日志fd显式关闭(防句柄泄漏) | fleet_supervisor.py | 待 auditor 分级 |
| 83 |  | fleet_supervisor.py | 待 auditor 分级 |
| 84 | cpu_load_pct", "family_cpu_seconds")
    and "Get-CimInstance Win32_Processor" not in src("fleet_supervisor.py | fleet_supervisor.py | 待 auditor 分级 |
| 85 |  | fleet_supervisor.py,tools/status_dashboard.py | 待 auditor 分级 |
| 86 |  | tools/attribution_probe.py,tools/deck_matchup.py,tools/eval_ | 待 auditor 分级 |
| 87 |  | train_tm.py | 待 auditor 分级 |
| 88 |  | episode_core.py | 待 auditor 分级 |
| 89 |  | side_driver.py,tools/attribution_probe.py,tools/deck_matchup | 待 auditor 分级 |
| 90 |  | tools/attribution_probe.py,tools/branch_demo.py,tools/danger | 可转行为(执行器/gate 帧序) |
| 91 |  | train_tm.py | 待 auditor 分级 |
| 92 |  | bc_build.py | 待 auditor 分级 |
| 93 |  | actor_worker.py,episode_core.py | 待 auditor 分级 |
| 94 |  | kit_config.py,tools/eval_matrix.py | 待 auditor 分级 |
| 95 | update", "_W1v_pre")
    and "_W1v_pre = self.W1v.copy()" in src("ppo.py")
    and "dH1v @ self.W1v.T)[:, :TRU | ppo.py | 待 auditor 分级 |
| 96 | P2(从零#5): BH旁车保留策略有界(1000/角色, 原无清理方) | learner_hub.py | 待 auditor 分级 |
| 97 | P2(从零#5): audit_all奖励面板补读actor日志(原结构性空) | tools/audit_all.py | 待 auditor 分级 |
| 98 | P1-9(从零#5): 仪表活性巡检不写死\"通过\"(真值+如实标注) | tools/status_dashboard.py | 账本类(保留需理由) |
| 99 |  | tools/le1b_inject.py,tools/situation_library.py | 待 auditor 分级 |
| 100 | build_rows", "bare_sc_names")
    and "def bare_sc_names" in src("bc_build.py")
    and "_mname in _bare_sc" i | bc_build.py | 待 auditor 分级 |
| 101 | P2: 低盘清理活性宽限+陈旧tmp清理方 | learner_hub.py | 待 auditor 分级 |
| 102 | P2: learner两处静默except响亮化(R67e同型) | learner_hub.py | 待 auditor 分级 |
| 103 | P2: teach的V分布外评估披露 | teach.py | 待 auditor 分级 |
| 104 | P2: league周报跨块聚合披露(blocks_n) | tools/league_weekly.py | 待 auditor 分级 |
| 105 | W3/W5: 四口径+exploit衰减在位(研究借鉴方案) | tools/eval_matrix.py,tools/league_weekly.py | 待 auditor 分级 |
| 106 | W4: 价值轨迹模块+learner挂点(降级响亮)")

print()
print("==== 契约门禁: %d PASS / %d WARN / %d FAIL ====" %
      (len(PASSES) | learner_hub.py,value_curve.py | 待 auditor 分级 |

## 备注
- 本次已转换范例: task-33 串断言→行为断言（0bf98b5）。
- task-58 新增断言/测试均按 R15（真实帧 frozen 序列 + 严格 replay）。
