# -*- coding: utf-8 -*-
"""门禁变异自检(R61d事故重建版, 2026-10-05): 沙箱逐条变异 → contract_check
必须红。沙箱机制: FILES+测试+contract_check复制到%TEMP%沙箱;
D12元修复: 非零退出≠拦截(崩溃也非零) — 认定标准=门禁输出含具体FAIL行。
R61: SELFTEST_TAGS增量过滤(未命中标签跳过, 上轮已验证项不重复消耗)。
本文件由tools/_rebuild_gs.py从pyc提取的MUTATIONS数据重建(源文件在
2026-10-05环境事故中跨盘丢失, 见METHODOLOGY 2.51事故记录)。
"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

FILES = [
         "threat.py",
         "config.py",
         "feat_builder.py",
         "soku_client2.py",
         "ppo.py",
         "macros/__init__.py",
         "macros/marisa.py",
         "macros/suika.py",
         "opp_model.py",
         "standard_tree.py",
         "train_tm.py",
         "tm_env.py",
         "outer_loop.py",
         "side_driver.py",
         "portmap.py",
         "perception.py",
         "skill_levels.py",
         "level_macros.py",
         "action_tables.py",
         "run_parallel.py",
         "reach_maps.py",
         "bc_build.py",
         "bc_align.py",
         "bc_io.py",
         "my_punish_tracker.py",
         "style_embedding.py",
         "style_lingo.py",
         "opp_gru.py",
         "frame_adv.py",
         "jz1_features.py",
         "forward_head.py",    # CE-4前向头(纯设计件)     # JZ-1预制件(test_jz1_prep消费者)
         "macros_branch.py",     # R4分支宏升级 — 落地时漏注册致沙箱基线假红
         "macros/wave_ext.py",   # CH-3/JZ-4扩展波组合器(与macros_branch同教训当日注册)
         "oracle_batch2.py",
         "macros/sakuya.py",
         "macros/patchouli.py",
         "macros/yuyuko.py",
         "macros/reisen.py",
         "macros/komachi.py",
         "macros/tenshi.py",
         "macros/alice.py",
         "macros/youmu.py",
         "macros/remilia.py",
         "macros/yukari.py",
         "macros/aya.py",
         "macros/iku.py",
         "macros/sanae.py",
         "macros/cirno.py",
         "macros/meiling.py",
         "macros/utsuho.py",
         "macros/suwako.py",
         "deck_sampler.py",
         "league.py",
         "teach.py",
         "ppo_gpu.py",
         "frame_events.py",
         # R61g(B1): SC词汇断言的载体
         "bc_match.py", "bc_build.py", "card_tables.py",
         # 从零#2(治理): side_driver导入macro_executor即崩
         # (沙箱缺件=全部变异失效 — "治理工具本身失效"病根)
         "macro_executor.py",
         "difficulty.py",
         "habit_detector.py",
         "exploiter.py",   # D4: 剥削者位测试载体
         "episode_core.py",
         "actor_worker.py",
         "learner_hub.py",
         "fleet_supervisor.py",
         "series_meter.py",
         "passivity_meter.py",
         # 审计#3 P1-1: d672c2d入库时FILES未同步 — test_series_stage1_e1
         # 沙箱内import即炸, 基线不绿, 变异自检整体瘫痪
         "series_manager.py",
         "distill.py",
         # 审计2026-10-13 P1-3二次漂移: test_research_w_wave依赖
         "value_curve.py",
         # BH-1(R142): 行为健康计数器(test_behavior_health_bh1依赖)
         "behavior_health.py",
         # LE-1a(R153): 情境库(test依赖; 在tools/目录, 非根级 —
         # build_sandbox自动拷tools/*.py, 此条是错放, 已移除)
         "kit_config.py"]   # 可迁移化: soku_client2/train_tm等import

# (文件, 原文, 变异文, 防的回归)
MUTATIONS = [
    # 审计#3 P1-5②: 封顶zmax反向项 — 关掉修正=回到旧"只补1/cap"行为
    # → onestep有限差分数值直钉必须红(权重增量符号级对此项不敏感,
    # 曾漏网; 数值直钉敏感度~3e-9)
    ("ppo.py", "    _r = np.flatnonzero(cap[:, 0] > 1.0)",
     "    _r = np.zeros(0, dtype=int)",
     "P1-5: 封顶zmax反向项缺失 → onestep数值直钉必须红"),
    ("train_tm.py", "'opp_hp': 0.005,", "'opp_hp': 0.0044,",
     "A1-2: 势函数伤害/承伤不对称回归(防御占优) → 对称断言必须红"),
    ("series_meter.py", "r >= ROUND_WIN", "rews >= 3000.0",
     "S0仪表: 胜负解码阈值废(全解码L) → 胜率曲线断言必须红"),
    ("series_meter.py", "% SERIES_LEN + 1", "% SERIES_LEN + 2",
     "S0仪表: 系列位置整体偏移 → 位置/分桶断言必须红"),
    ("ppo.py", "ent_grad = -P *", "ent_grad = P *",
     "P0-1 熵梯度符号反 → 熵行为断言必须红"),
    ("ppo.py", "os.replace", "shutil.move",
     "P0-5 非原子保存 → 原子性断言必须红"),
    ("train_tm.py", "core[33] = ", "core[145] = ",
     "P0-2 错下标污染特征 → 源断言必须红"),
    ("feat_builder.py", "tti / GAME_FPS < 0.3", "tti < 0.3",
     "P0-3 TTI量纲混用 → 擦弹可达性必须红"),
    ("threat.py", "and t_end > 0", "and True",
     "P0-4 过界弹计入来袭 → 威胁负例必须红"),
    ("threat.py", "t0 = max(0.0, t0)", "t0 = t0",
     "P0-4b 负TTI钳位回归(删钳位致负值入威胁) → 威胁负例必须红"),
    ("threat.py", "GAME_FPS = 62", "GAME_FPS = 60",
     "62教义回退 → C1必须红"),
    ("macros/__init__.py", "return f / 62.0", "return f / 60.0",
     "62教义回退(除法形) → C1必须红"),
    ("train_tm.py", "rews[-1] += seg_rew", "pass",
     "终局KO奖励丢失回归 → C6必须红"),
    ("train_tm.py", "or (score_l_prev + score_r_prev) < 2)", "or False)",
     "R39(P2-6): 崩溃局当终止回归(异常结束尾部负偏优势) → 截断断言必须红"),
    ("feat_builder.py", "right[\"action\"] in HIT_ACT_IDS", "right[\"hp\"] < 9500 and right[\"hp\"] > 0",
     "P1-4a opp_down血量启发式回归 → C6必须红"),
    ("train_tm.py", "opp_vx=opp_vx_ema", "opp_vx=0.0",
     "P1-4b opp_vx假接线回归 → C6必须红"),
    ("train_tm.py", "distill_data_%s%s.npz\" % (self.char, self.suffix)", "distill_data_DIR%s%s.npz\" % (self.char, self.suffix)",
     "P3-4 写读异径回归 → 同径计数必须红"),
    ("train_tm.py", "POT_W = {", "R_WALL = -0.004\nPOT_W = {",
     "死奖励常量回归(墙罚在R35势函数外复活) → AST活性必须红"),
    # 从零#2迁移(R61t F5); 审计#3 P1-1: 316锚已漂移为死变异(B段
    # 扩维→330) — C2维度防线假绿, 迁锚现值
    # P1根治(2026-10-14晚): 该锚已改由_rederive_dim_anchors()从
    # FeatureBuilder.CORE_DIMS运行时派生(此处占位串仅为可读性);
    # R138: 330→358(JZ-1扩维后锚漂移, 干跑校验抓出 — 模式不命中
    # =死变异, 自检会报"变异定义失效"而非静默)
    ("feat_builder.py", "CORE_DIMS = 358", "CORE_DIMS = 357",
     "特征布局漂移 → C2必须红"),
    ("feat_builder.py", "for i in range(5) if rh[i * 2] != 0xFF", "for i in range(5) if False",
     "P1-4e opp_cards_n回退恒0 → C7必须红"),
    ("feat_builder.py", "0.0 if g >= 0xFF00", "0.0 if g >= 0xFF000000",
     "卡槽哨兵0xFFFF失明(65535泄漏为131) → C7必须红"),
    ("feat_builder.py", "if weather.get(\"displayed\") == WEATHER_AURORA:", "if False:",
     "极光displayed优先回退(实际效果泄漏) → C7必须红"),
    ("feat_builder.py", "WEATHER_SEIRAN = 11", "WEATHER_SEIRAN = 12",
     "晴岚ID错位(天气id路径失效) → C7必须红"),
    ("standard_tree.py", "(\"6C\", \"主力弹幕远压", "(\"6X\", \"主力弹幕远压",
     "教义树幻影宏名 → C8必须红"),
    ("standard_tree.py", "STANDARD_TREE_SUIKA = [", "STANDARD_TREE_SUIKA = [] and [",
     "萃香教义树清空 → C8节点数必须红"),
    ("train_tm.py", "TREES[self.char]", "STANDARD_TREE",
     "audit回退灵梦树近似 → C8路由必须红"),
    ("tools/mod_provenance.json", "\"deployed_md5\": \"1725B97CB6F16A2D19655C1034D218DF\"", "\"deployed_md5\": \"0000000000000000000000000000000\"",
     "血统档案被篡改/回滚旧DLL → C9必须红"),
    ("tools/mod_provenance.json", "\"Training\\\\TrainingMod\\\\main.cpp\"", "\"Training\\\\TrainingMod\\\\mainX.cpp\"",
     "编译清单手抄漂移(≠bat现算) → C9必须红"),
    ("side_driver.py", "_self.last_match = (e.winner, e.ls, e.rs)", "_self.last_match = None",
     "胜者记录失效(战报全平) → C10必须红"),
    ("outer_loop.py", "vs_com=False, tps=tps", "vs_com=True, tps=tps",
     "评估回退打COM(非模型对模型) → C10必须红"),
    ("side_driver.py", "self.decisions += 1", "pass",
     "决策计数失效 → C10必须红"),
    ("train_tm.py", "self.env.step(inp, self._opp_inp)", "self.env.step(inp)",
     "对手输入接线断开(P2不动) → C10必须红"),
    ("train_tm.py", "self.opp.frame_input(right, left, weather,", "self.opp.frame_input(right, right, weather,",
     "P2视角错接(对手看着自己打) → C10必须红"),
    ("macros/__init__.py", "[((\"down\",), 6), ((\"down\", \"A\"), 10)]", "[((\"down\", \"A\"), 10)]",
     "死招回归: 2A方向预置被删 → C11必须红"),
    ("portmap.py", "\"train_rebuild\": (20850, 20899),", "\"train_rebuild\": (20895, 20905),",
     "端口段重叠回归 → C12必须红"),
    ("train_tm.py", "rebuild_port(self.slot, ep)", "self.env.base_port + 100 + ep",
     "异常重建回退跨段公式 → C12必须红"),
    ("side_driver.py", "if isinstance(keys, str) and keys.startswith(\"sc:\"):", "if isinstance(keys, str):",
     "对手侧门步回退丢弃(开环对赌复活) → C12必须红"),
    ("tm_env.py", "except ProtocolError as e:", "except RuntimeError as e:",
     "回退子串匹配错误分支(D8) → C12必须红"),
    ("opp_model.py", "N_FEATS = 27 + 40 + 8", "N_FEATS = 27",
     "R17特征收缩(历史/资源被砍) → C2维数断言必须红"),
    ("ppo.py", "OPP_CORE_OFF = 152", "OPP_CORE_OFF = 179",
     "R17子网络切片错位(读错特征且静默) → C2对齐断言必须红"),
    ("opp_model.py", "self._hist.append(b)", "self._hist.append(0)",
     "R17历史冻结(恒为怠类) → C2段10活性断言必须红"),
    ("opp_model.py", "self._res_full[_res_group] += w", "pass",
     "R17灵满统计假接线 → C2活性断言必须红"),
    ("opp_model.py", "self._res_low[_res_group] += w", "pass",
     "R17灵空统计假接线 → C2活性断言必须红"),
    ("train_tm.py", "core[227 + opp_id] = 1.0", "core[226 + opp_id] = 1.0",
     "R17段偏移回退(角色one-hot污染对手特征) → C2源/F8守卫断言必须红(原'min(opp_id,20)'靶式随R60-F8合法槽化退役)"),
    ("ppo.py", "-dWq1, -dbq1, -dWq2, -dbq2", "dWq1, dbq1, dWq2, dbq2",
     "R17辅助梯度符号回退(下降当上升) → test_opp_subnet FD必须红"),
    ("ppo.py", "self._opp_fwd(S)[1] @ self.W_opp", "0.0",
     "R17子网络断线(W_opp乘积被绕过) → test_opp_subnet接线必须红"),
    ("ppo.py", "mask=M[_kidx] if M is not None else None", "None",
     "R18 KL复检失掩码(禁宏质量回流伪影) → C4同掩码断言必须红"),
    ("ppo.py", "mask=M[_fidx] if M is not None else None", "None",
     "R18熵诊断失掩码(读未掩码策略熵) → C4熵断言必须红"),
    ("feat_builder.py", "closing = -(bvx * (1 if rdx > 0 else -1)", "closing = (bvx * (1 if rdx > 0 else -1)",
     "R19闭合速度符号回退(飞离当逼近) → C2行为断言必须红"),
    ("feat_builder.py", "(fdy + 150) / 50, 0, 5)", "(fdy + 150) / 100, 0, 5)",
     "R19段8除数回退(18维死区复活) → C2行为断言必须红"),
    ("feat_builder.py", "key=lambda bb: abs(bb[1] - left[\"position.x\"]))[:3]", "key=lambda bb: 0)[:3]",
     "R19近弹排序退化回包序 → C2行为断言必须红"),
    ("feat_builder.py", "self._evasion_count = getattr(self, '_evasion_count', 0) + 1", "pass",
     "R19规避观测维自增移除(恒0) → C2活性断言必须红"),
    ("portmap.py", "LANE_W = 12", "LANE_W = 15",
     "R19重建车道加宽越段(域校验须枚举真实绑定集) → C12必须红"),
    ("soku_client2.py", "if self.proc:\n                self.proc.terminate()\n            raise RuntimeError(\"握手失败: %s\"", "if False:\n                pass\n            raise RuntimeError(\"握手失败: %s\"",
     "R19回声不匹配分支清理移除 → C3源断言必须红"),
    ("soku_client2.py", "if _ok_n > 8:", "if _ok_n > 800:",
     "R19 OK跳过上限失效(洪流挂死) → C3源断言必须红"),
    ("tm_env.py", "if self._monitor_stop:\n                self._monitor_stop.set()", "if False:\n                pass",
     "R19失败路径监视线程泄漏(闸门失效) → C3源断言必须红"),
    ("side_driver.py", "return np.concatenate([f2, d1, d2])", "return np.concatenate([f2, f1, f0])",
     "R19 P2视觉栈回退原始3帧(分布外) → test_visual_stack必须红"),
    ("skill_levels.py", "return CHAR_SKILL_MAPS.get(char, {}).get(cid)", "return None",
     "R19 cid_to_slot回退恒None桩(技能等级/等级宏失效) → test_visual_stack必须红"),
    ("opp_model.py", "GUARD_ALL_IDS = GUARD_STANCE_IDS | GUARD_RECOIL_IDS", "GUARD_ALL_IDS = GUARD_STANCE_IDS",
     "R21防御ID集丢失防御受击段(159-167) → C2权威表断言必须红"),
    ("opp_model.py", "_ATTACK_ACT_LO, _ATTACK_ACT_HI = 300, 598", "_ATTACK_ACT_LO, _ATTACK_ACT_HI = 200, 598",
     "R28攻击区间回退LO=200(冲刺误入攻击桶) → C2断言必须红"),
    ("train_tm.py", "POOL_K = 3", "POOL_K = 1",
     "R22池深回退1(无历史对抗, 策略循环风险) → C13断言必须红"),
    ("run_parallel.py", "(\"reimu\", 20800, 0, [\"reimu\", \"marisa\", \"suika\", \"COM\"])", "(\"reimu\", 20800, 0, [\"marisa\", \"suika\", \"COM\"])",
     "R22镜像对局移除(reimu不再打reimu) → C13断言必须红"),
    ("train_tm.py", "if not (_ox < 120 or _ox > 1120):\n                        mask = mask & ~self.corner_combo_idx", "if False:\n                        pass",
     "R23版边连门控移除(中场可采) → C13源断言必须红"),
    ("train_tm.py", "if not right[\"airBorne\"]:\n                        mask = mask & ~self.air_combo_idx", "if False:\n                        pass",
     "R23空连门控移除(对地可采) → C13源断言必须红"),
    ("train_tm.py", "dx_abs > self.macro_reach + REACH_MARGIN", "dx_abs > 99999",
     "R24射程门控失效(超射程可采) → C13源断言必须红"),
    ("train_tm.py", "(_adx - self.macro_reach) / 200.0", "(_adx - 0) / 200.0",
     "R24射程差特征退化(全零=理解通道断) → C13源断言必须红"),
    ("feat_builder.py", "_spd < 0.5 and _k[3] >= 10", "_spd < 0.0",
     "R25地雷威胁判定失效(延迟弹全盲) → C13源断言必须红"),
    ("feat_builder.py", "0.5 * _ax * horizon * horizon", "0.0",
     "R25二次外推退化回线性(变速弹失真) → C13源断言必须红"),
    ("train_tm.py", "_ady > self.macro_reach_v + REACH_MARGIN", "_ady > 99999",
     "R25纵向门控失效(高度错配可采) → C13源断言必须红"),
    ("reach_maps.py", "'jA': (306,), 'j6A': (307,), 'j2A': (308,), 'j8A': (309,),", "'jA': (306,), 'j6A': (307,), 'j2A': (308,),",
     "R29显式表丢j8A(空中四招残缺) → C13空中断言必须红"),
    ("reach_maps.py", "'2A': (303, 311), '2A确认': (303, 311),", "'2A': (309, 311), '2A确认': (309, 311),",
     "R27回退2A=309误标(j8A的id冒充2A) → C13地面表断言必须红"),
    ("reach_maps.py", "'DA': (305, 302),", "'DA': (302,),",
     "R29 DA回退6A签名(66A冲刺A丢失) → C13显式表断言必须红"),
    ("feat_builder.py", "if left.get(\"action\", 0) in GUARD_ALL_IDS:\n            return 0", "if False:\n            return 0",
     "R33格挡graze排除移除(防御态刷graze通道复活) → C13源断言必须红"),
    # 从零#2迁移: R34中断/灵力门随C1执行器抽取迁至macro_executor
    ("macro_executor.py", "300 <= opp_a < 600 and my_a < 100",
     "300 <= opp_a < 600 and my_a < -100",
     "R34帧级防御中断失效 → C1行为测试R34中断必须红"),
    ("macro_executor.py", "and spirit < 100):", "and spirit < -1):",
     "R34灵力门控失效(空灵力仍出攻击) → C1行为测试灵力门必须红"),
    # R38 P0-1队列守卫变异退役: 执行器化后清队路径全部立即return
    # (结构性守卫 — C1空队安全测试钉住语义)
    ("side_driver.py", "from opp_model import GUARD_ALL_IDS", "from opp_model import GUARD_STANCE_IDS",
     "R38 P0-2回退: GUARD_ALL_IDS遗漏导入 → R34中断NameError炸局 → 导入断言必须红"),
    ("train_tm.py", "_V = self._ppo_act._v_forward(", "_V, = self._ppo_act._v_forward(",
     "R38 P0-3回退: 元组解包ValueError被吞 → 价值引导变死特性 → 解包断言必须红"),
    ("ppo.py", "np.argsort(-np.abs(adv[_hi_idx]))[:_cap]", "np.argsort(-np.abs(adv[_hi_idx]))[_cap:]",
     "R38 P0-4a回退: 池切片方向反 → 回放池恒空 → 切片断言必须红"),
    ("ppo.py", "logp_old[N0:N0 + _rp_n] = _rows[7]", "pass  # logp_old splice removed",
     "R38 P0-4c回退: 回放行logp_old取当前策略 → ratio恒1 → logp拼接断言必须红"),
    ("ppo.py", "M = np.concatenate([M, _rows[6]])", "M = M",
     "R38 P0-4b回退: 回放行不拼mask → 前向广播爆炸静默丢更新 → mask拼接断言必须红"),
    ("bc_build.py", "from bc_align import estimate_lag_map, realign, post_validate", "from bc_align import estimate_lag_map",
     "R38 P0-5回退: BC构建不走对齐器 → 状态/输入错位复活 → 对齐断言必须红"),
    ("soku_client2.py", "== 117", "== 118",
     "输入包117B协议常量漂移 → C3断言必须红"),
    ("ModLoaderSettings.json", "MemoryPatch.dll\": {\n            \"enabled\": true", "MemoryPatch.dll\": {\n            \"enabled\": false",
     "C16训练mod集漂移(MemoryPatch被禁→多开摧毁) → C16断言必须红"),
    ("skill_levels.py", "102: 3,", "102: 0,",
     "R39§4-4回退: 灵梦102亜空穴槽位错位复活 → SKILL_MAP锚点断言必须红"),
    ("macros/suika.py", "201: 2,", "",
     "R39§4-6回退: suika的sc:201耗费项被删 → sc∈SC_COST断言必须红"),
    ("reach_maps.py", "'TM·对空连': (308,),", "",
     "R39§4-7回退: TM宏射程登记条目被删 → TM登记率断言必须红(注: 变异须删条目而非改空元组 — 断言查表成员性, 空元组仍算已登记)"),
    ("oracle_batch2.py", "'SOKUAI_INPUTLOG': '1'", "'SOKUAI_INPUTLOG': '0'",
     "R40回退: 精确对齐通道关闭 → INPUTLOG接线断言必须红"),
    ("bc_build.py", "arr[:, 0].astype(np.uint16), arr[:, 2].astype(np.uint16)", "arr[:, 1].astype(np.uint16), arr[:, 3].astype(np.uint16)",
     "R40回退: ilog取outKeys列(非inKeys) → 精确对齐分支断言必须红"),
    ("tools/mod_provenance.json", "\"built_md5\": \"B7E8C8052EF062783FC1131FA8F37DF6\"", "\"built_md5\": \"0000000000000000000000000000000\"",
     "R41§2-1回退: oracle血统漂移(档案与构建物不符) → C9-oracle断言必须红"),
    ("run_parallel.py", "正常完成(%s局", "正常完成(%d局",
     "R42回退: eps按%d格式化(字符串首触TypeError炸监督器) → R42断言必须红"),
    ("train_tm.py", "POOL_SNAPSHOT_EVERY = 50", "POOL_SNAPSHOT_EVERY = 99999",
     "R43-A回退: 池快照事实上停摆(等于10-02冻结态) → 池刷新断言必须红"),
    ("train_tm.py", "COM_CLIMB_N = 20", "COM_CLIMB_N = 99999",
     "R43-B回退: COM阶梯永不升级(课程失效) → 阶梯断言必须红"),
    ("macros/sakuya.py", "(\"5A确认\", [((\"A\",), 10), ((), 2), (\"confirm\", 0)]),", "(\"5X确认\", [((\"A\",), 10), ((), 2), (\"confirm\", 0)]),",
     "R44回退: 宏定义改名但类别集合不变→幽灵名断言必须红(原全局替换宏定义与集合同变=无幽灵)"),
    ("tm_env.py", "\"reisen\": 10, \"komachi\": 12,", "\"reisen\": 10,",
     "R46§3-1回退: CHAR表缩回旧版(新角色KeyError) → CHAR20断言必须红"),
    ("macros/sakuya.py", "MACROS_SAKUYA = [(n, _norm_presteps(sc)) for n, sc in _RAW_SAKUYA]", "MACROS_SAKUYA = _RAW_SAKUYA",
     "R46§3-2回退: 规范化重绑定丢失(14宏跑原始脚本) → 规范化断言必须红"),
    # 从零#2迁移: R61d(A3)裁决后ID集已换(旧159-167/50-98失效)
    ("frame_events.py", "frozenset(range(150, 167)) - {158}",
     "frozenset(range(150, 167))",
     "R61d回退: 158空防误入GUARDSTUN沿 → 检测断言必须红"),
    ("frame_events.py",
     "_TRUE_DOWN_ACTS = frozenset({88, 89, 97, 98, 100, 143, 145})",
     "_TRUE_DOWN_ACTS = frozenset({88, 89})",
     "R61d回退: 真倒地集缩水 → 检测断言必须红"),
    # R51§F3守式检查变异退役: B2(R61l)按设计让事件反应产生
    # 策略决策点(学习化取代守式隔离) — 守卫移除是特性非回归
    ("train_tm.py", "\"remilia\": 19", "\"remilia\": 5",
     "R60-F8回退: 池序落入技能特征槽3-10(R19契约) → 合法槽断言必须红"),
    ("ppo.py", "elif kl < self.TARGET_KL:", "elif kl < self.TARGET_KL / 99:",
     "R50§A1回退: LR回升条件重新钉死(KL死区) → LR断言必须红"),
    ("train_tm.py", "1000 if self.macros[i][0].startswith('原子')", "150 if self.macros[i][0].startswith('原子')",
     "R50§A4回退: 原子宏配额缩短(零logit鸡生蛋) → 配额断言必须红"),
    ("train_tm.py", "from deck_sampler import sample_deck", "from deck_sampler import sample_deck as _unused",
     "R47回退: deck采样断开(恒系统卡) → deck断言必须红"),
    ("train_tm.py", "self._fleet_logp_rec = None", "self._fleet_logp_rec = 1",
     "R56①回退: logP钩子默认非None(生产路径被改) → 钩子断言必须红"),
    ("train_tm.py", "if self._fleet_logp_rec is not None:", "if True:",
     "R56①回退: 决策点守卫解除文本变化(钩子语义漂移) → 守卫断言必须红"),
    ("ppo_gpu.py", "stored_logp = kw.get('stored_logp')", "stored_logp = None",
     "R56①回退: learner忽略stored_logp(ratio恒=1近似) → 消费断言必须红"),
    ("actor_worker.py", "tr.ppo.rng = np.random.default_rng(", "tr.ppo.rng = _NO_RESEED  # np.random.default_rng(",
     "R56③回退: rng重播种移除(同快照actor同流) → 种子断言必须红"),
    ("actor_worker.py", "tr._snapshot_pool = lambda: None", "tr._snapshot_pool = lambda: 1",
     "R56单写者回退: actor写池快照(多写者竞争) → 单写者断言必须红"),
    ("ppo_gpu.py", "for i, L in enumerate(ep_lens):", "for i, L in enumerate(ep_lens[:1]):",
     "R56回退: _gae只算首局(多局批GAE截断丢) → 按局索引断言必须红"),
    ("learner_hub.py", "stored_logp=logps, gru_reprs=gru_reprs)", "stored_logp=None, gru_reprs=gru_reprs)",
     "R56①回退: learner不传stored_logp(update忽略行为logp) → 传递断言必须红"),
    ("episode_core.py", "fname + \".tmp.npz\"", "fname + \".tmp\"",
     "R56契约回退: tmp名无.npz后缀(np.savez自动补→replace找不到) → 原子写断言必须红"),
    ("train_tm.py", "opp = build_opp_cycle(args.opp)", "opp = None",
     "R56-F4回退: main不走共享构造(单点漂移 reopen) → 单一实现断言必须红"),
    ("learner_hub.py", "files.sort(key=lambda p: (os.path.getmtime(p), p))", "files.sort()",
     "R57-2.1回退: 按文件名排序(低编号actor经验被饿死) → mtime断言必须红"),
    ("learner_hub.py", "10_000 + int(gpu_tr._updates)).choice(", "0).choice(",
     "R57-2.2回退: BC锚回到固定采样(过拟合定点) → 重采样断言必须红"),
    ("actor_worker.py", "state['snap_ver'] * 1_000_001 + state['ep']", "state['snap_ver'] * 1_000_001 + 0",
     "R57-2.3回退: 局因子消失(同版本内逐局rng复位) → 每局重播种断言必须红"),
    ("actor_worker.py", "tr.macro_counts = _c", "tr.macro_counts = _KEEP_STALE",
     "R57-2.4回退: actor不载下行计数(配额基于陈旧值) → counts下行断言必须红(原变异'pass # ...'注释保留子串=自我逃逸, 第十九轮自检抓出)"),
    ("feat_builder.py", "s[o + 1] = 1.0 if right[\"action\"] in self._low_ids() else 0.0", "s[o + 1] = 0.0",
     "R57-2.5回退: 下段位恒0(段位又全盲) → test_guard_height行为测试必须红 [R141迁锚: BH-3.2改self._low_ids(), 原LOW_ATTACK_IDS直引锚漂移]"),
    ("episode_core.py", "data[\"schema\"] = np.array(EP_SCHEMA)", "data[\"schema\"] = np.array(99)",
     "R57-2.6回退: schema标错版本(消费端拒收) → schema断言必须红"),
    # ---- R63(2026-10-07架构审查: 镜像轴 + episode代际契约) ----
    ("train_tm.py", "if axis == \"H\" and mirror:", "if axis in (\"H\", \"V\") and mirror:",
     "R63(P0-1)回退: 镜像连V一起翻(约一半决策执行纵向镜像动作) → 镜像轴断言必须红"),
    ("episode_core.py", "EP_SCHEMA = 2   # R63", "EP_SCHEMA = 1   # R63",
     "R63(P0-2)回退: schema退回v1(contract块失效) → 契约断言必须红"),
    ("episode_core.py", "return [\"%s: %s\" % (where, b) for b in bad]",
     "return []  # 恒空",
     "R63(P0-2)回退: check_contract恒返回空(契约代际校验失效) → 契约断言必须红"),
    ("episode_core.py", "        if _bad:\n            raise EpisodeContractError(\"; \".join(_bad))",
     "        if False:\n            raise EpisodeContractError(\"; \".join(_bad))",
     "R63(P0-2)回退: 读者契约不符不再抛(旧代际被当正常数据消费) → 契约断言必须红"),
    ("actor_worker.py", "build_contract(char, tr.n_macros, int(tr.ppo.N_SIDE), tr.n_macros)",
     "build_contract('reimu', 3, 3, 3)",
     "R63(P0-2)回退: actor写死/写错契约(不与自身网络尺寸同源) → 写者契约断言必须红"),
    ("learner_hub.py", "check_model_generation(char, n_out)",
     "None  # 代际校验移除",
     "R63(P0-2)回退: learner不校验模型档代际(旧档续训) → 代际断言必须红"),
    ("episode_core.py", "    if int(model_n_out) != int(_cn):",
     "    if False:",
     "R63(P0-2)回退: 模型代际判据恒真(旧档续训不被拒) → 代际判据断言必须红"),
    # ---- R63(F6): 超人距离占位口径 ----
    ("tools/eval_matrix.py", "'metric': d['worst_lower']",
     "'metric': 1.0",
     "R63(F6)回退: 超人距离回到常量占位读数 → 度量断言必须红"),
    ("tools/superhuman_gauge.py", "    if k <= 0:\n        lo = 0.0",
     "    if False:\n        lo = 0.0",
     "R63(F6)回退: Wilson端点钳制移除(残差4.87e-17 → 与0比较失效) → 断言必须红"),
    ("tools/superhuman_gauge.py", "            per[cb]['pairs'][ca] = rate(bw, n)",
     "            pass",
     "R63(F6)回退: 对位退回单边(a视角) → 恒在b侧角色空手(F6测试必须红)"),
    ("tools/superhuman_gauge.py", "'comparable': comparable,",
     "'comparable': True,",
     "R63(F6)回退: 非同口径也标可比(伪造距离) → F6测试必须红"),
    ("tools/superhuman_gauge.py", "'discriminates_at_top': False,",
     "'discriminates_at_top': True,",
     "R63(F6)回退: COM标尺谎称顶端可分辨(真人打COM=100%已饱和) → 断言必须红"),
    ("tools/superhuman_gauge.py", "    elif lo >= hw - near:",
     "    elif False:",
     "R63(F6)回退: 饱和达顶分支变死代码 → F6测试必须红"),
    # 注: gate_selftest.py **自身**的沙箱生命周期不做变异 —— 变异体若破坏
    # 自清逻辑, 每条变异会泄漏 ~1.5GB 沙箱并压满系统盘(本轮真实事故),
    # 属于"变异工具自伤", 收益为负。该处仅保留 contract_check 的文本断言。
    ("feat_builder.py", "s[o + 21] = 1.0 if right[\"action\"] in F_VARIANT_IDS else 0.0", "s[o + 21] = 0.0",
     "R58回退: 对手f变体位恒0(遠A警戒盲区复活) → test_guard_height必须红"),
    ("train_tm.py", "elif getattr(self, \"_fleet_logp_rec\", None) is not None:", "elif False:",
     "R60-F1回退: actor快照刷新门重关(采样冻结启动权重) → 死链断言必须红"),
    ("learner_hub.py", "key=lambda p: int(''.join(c for c in os.path.basename(p)", "key=lambda p: p",
     "R60-F3回退: 快照清理回字典序(v10被删) → 数值排序断言必须红"),
    ("learner_hub.py", "not f.endswith('.tmp.npz')", "not f.endswith('.ZZZ')",
     "R60-F4回退: collect吞在途tmp件(活actor数据丢失) → tmp排除断言必须红(原'True or ...'变异残留子串=自我逃逸, 自检抓出)"),
    ("ppo_gpu.py", "ret = adv + V_np", "ret = adv * 0.0 + V_np",
     "R60-F6回退: critic目标脱离回报(学z分数+V) → ret序断言必须红"),
    ("ppo_gpu.py", "logp_e = F.log_softmax", "logp_e = F.softmax",
     "R60-F7回退: 专家行logp虚高(丢log=概率冒充对数, KL钉LR下限) → 专家行logp断言必须红(原zeros+log_softmax变异=加零空操作, 2026-10-14自检抓出重写)"),
    ("train_tm.py", "mask = mask & ~self.near_idx", "mask = mask & ~self.melee_idx",
     "R60-F9回退: 330门禁全攻击(远程立回不可学) → 近战子集断言必须红"),
    ("train_tm.py", "self._last_ret = float(np.sum(rews))", "self._last_ret = 0.0",
     "R60-F10回退: 看门狗又断粮(恒0永不报警) → 看门狗断言必须红"),
    ("train_tm.py", "stored_logp=LOGPS)", "stored_logp=None)",
     "R60-F11回退: 本地不传行为logp(ratio失真) → stored_logp断言必须红"),
    ("train_tm.py", "else graze_low_rate(frames)", "else GRAZE_LOW_RATE",
     "R61-d回退: 低段恒定费率(拖时间收割复活) → 衰减接入断言必须红"),
    ("train_tm.py", "_fw = fastwin_bonus(frames - round_f0, d_sl)", "_fw = 0.0 * fastwin_bonus(frames - round_f0, d_sl)",
     "R61回退: 快胜奖金归零(果断终结失去经济价值) → 快胜断言必须红"),
    ("train_tm.py", "ko_round_reward(left[\"hp\"], right[\"hp\"],\n                                      True) * d_sl", "R_KO_ROUND * d_sl * (0.3 + left[\"hp\"] / 10000.0)",
     "R61b回退: 胜侧退回只看自身血量(顶时胜血量差盲区复活) → 血量差断言必须红"),
    ("train_tm.py", "GAMMA_POT * _pot - self._prev_pot", "_pot - self._prev_pot",
     "R61c回退: γ因子消失(驻高势态零漂移) → γ断言必须红"),
    ("train_tm.py", "card_gauge_val=_cg", "card_gauge_val=None",
     "R61c回退: 晴岚哨兵断开(伪势跳±2.0复活) → 哨兵断言必须红"),
    ("train_tm.py", "os.replace(_t, _p)", "pass",
     "R61e-B6回退: COM难度不落盘(重启回Easy反复爬梯) → 持久化断言必须红"
     "(变异不得带注释残留子串 — 第六型教训)"),
    ("ppo_gpu.py", "os.replace(_tp, pi_path)", "pass  # os.replace_x(_tp, pi_path)",
     "R61e回退: GPU save裸写(中断=半档损坏) → 原子落盘断言必须红"),
    ("learner_hub.py", "'learner_%s%s.lock' % (char, suffix)", "'no_lock_unused'",
     "R61e-D5回退: learner双实例锁移除(双写者竞争复活) → 单实例锁断言必须红"),
    # ---- R61f(F3尾巴第二批, 2026-10-05) ----
    ("ppo_gpu.py", "logits = logits + b / t",
     "logits = logits + b",
     "R61f回退: 采样bias回到/temp后(×T系数失真) → bias语义断言必须红"),
    ("ppo_gpu.py", "if len(m) >= 6 else 1.0",
     "if True else m[5]",
     "R61f回退: 旧档meta无len守卫(5元素越界) → meta守卫断言必须红"),
    ("skill_levels.py", "or char is None:",
     "or False:",
     "R61f回退: cid合并路径复活(cid102歧义错表) → 合并删除断言必须红"),
    ("deck_sampler.py", "if len(deck) > 20:",
     "if False:",
     "R61f回退: deck边界截断移除(32张溢出) → deck边界断言必须红"),
    # ---- R61g(B1): SC词汇 ----
    ("bc_match.py", "SC_PRESS_F = 3",
     "SC_PRESS_F = 0",
     "R61g回退: sc:步零时长展开(SC标签回0%) → SC词汇断言必须红"),
    ("bc_build.py", "def resolve_sc_label(",
     "def resolve_sc_label_disabled(",
     "R61g回退: 具体卡解析改名断链(SC标签全是首个SC宏) → 解析断言必须红"),
    # ---- R61l(B2): 反应表学习化 ----
    ("train_tm.py", "frame_events.reaction_mask(",
     "frame_events.pick_reaction(",
     "R61l-B2回退: 事件回退到固定权重随机(策略失去事件约束) → B2断言必须红"),
    ("train_tm.py", "if _ev_mask is not None:",
     "if False:",
     "R61l-B2回退: 事件掩码交集断开(策略失去事件约束) → B2断言必须红"),
    # ==== 从零#2新增: 本轮修复的回归钉 ====
    ("macro_executor.py", "queue.append((ks, fr))",
     "queue.append((ks, 0))",
     "P0-B入队丢载荷回归(branch/link/ender训练侧炸) → 贯通集成测试必须红"),
    ("macro_executor.py", "if d_deal > 0 or opp_a in HITSTUN_IDS:",
     "if d_deal > 0:",
     "P0-B分支门结算窗回退(纯瞬时d_deal→命中后误判whiff) → 贯通集成测试必须红"),
    ("ppo_gpu.py", "param is not None and param.shape == a.shape:",
     "param is not None and (True or param.shape == a.shape):",
     "P0-A共犯回退: 形状不符静默混入随机权重 → fleet协议B5拒载断言必须红"),
    ("learner_hub.py", "5 * n_out + FeatureBuilder.CORE_DIMS",
     "5 * n_out + 308",
     "P0-A维度推断过期回归(hardcode 308) → fleet协议B6派生断言必须红"),
    ("ppo_gpu.py", "pi_loss = -torch.min(surr1, surr2).sum()",
     "pi_loss = -torch.min(surr1, surr2).mean()",
     "等价修复1回归: sum-vs-mean归约 → 一步等价探针必须红"),
    ("ppo_gpu.py", "sd = float(np.asarray(rewards).std())",
     "sd = 0.0",
     "等价修复2回归: rstd先除后更 → 一步等价探针必须红"),
    ("train_tm.py", "return 0.0 if round_won else MICRO_TAX_LOSS * micro_bank",
     "return 0.0",
     "R62胜负挂钩回退(败不追扣=负相关复活) → 奖励经济学测试必须红"),
    ("train_tm.py", "ok = int(d['W2'].shape[1]) == int(n_macros)",
     "ok = True",
     "fleet缺陷③回归: 池快照维度守卫失效(陈旧快照=木桩对手) → fleet协议J2必须红"),
    ("train_tm.py", "ts = 'exploit_' + ts",
     "ts = ts",
     "D4回归: 剥削者快照失去前缀(仪表/保留分流双盲) → D4测试必须红"),
    # ==== R138(2026-10-15晚): CE新组件变异 ====
    # CE-3.4位置路由门(tag: CE-3.4)
    ("macro_executor.py", "if _dist - _hint < _thr:",
     "if _dist + _hint < _thr:",
     "CE-3.4外推方向反(推板量加而非减=永不入角) → pos_gate测试必须红"),
    ("macro_executor.py", "        if \"corner\" in payload:\n            return payload.get(\"corner\")\n        return payload.get(\"mid\")",
     "        return payload.get(\"mid\")\n        if \"corner\" in payload:\n            return payload.get(\"corner\")",
     "CE-3.4回落语义反(corner缺省截断已确认连段) → pos_gate测试必须红"),
    ("macro_executor.py", "POS_GATE_THRESHOLD = 120.0",
     "POS_GATE_THRESHOLD = 1200.0",
     "CE-3.4阈值漂移(全场判贴角=版中收尾不可达) → pos_gate测试必须红"),
    # CE-7推板进度势(tag: CE-7)
    ("train_tm.py", "'corner_progress': 0.0144,",
     "'corner_progress': 0.008,",
     "CE-7标定回退(1.39倍<方案2-3倍下界) → ce7量级测试必须红"),
    ("train_tm.py", "if os.environ.get('TH123_CE7_POT', '0') == '1':",
     "if True:",
     "CE-7门控失效(默认开=污染A1-2观察窗, 时点红线) → ce7门控测试必须红"),
    ("train_tm.py", "        p -= POT_W['corner_progress'] * (1.0 - _own_to_corner)",
     "        p += POT_W['corner_progress'] * (1.0 - _own_to_corner)",
     "CE-7 own侧符号反(被关角变好事) → ce7 own对称测试必须红"),
    # R137漏改调用点(tag: CE-4调用面)
    ("series_meter.py", "_logits, _v, q, _fwd = net(x, s, temp, m)",
     "_logits, _v, q = net(x, s, temp, m)",
     "CE-4四元组调用面回退(第7处再漏=ValueError) → S0系列仪表测试必须红"),
    # R138b: CE-4目标提取索引(tag: CE-4目标)
    ("forward_head.py", "        float(s_next_core[150]) / 1.5,",
     "        float(s_next_core[34]) / 1.5,",
     "CE-4目标索引回退fictional([34]位置带≠own贴角, 目标成常数) → CE-4测试必须红"),
    ("forward_head.py", "        float(s_next_core[4]),",
     "        float(s_next_core[5]),",
     "CE-4 adx索引错([5]=own_x/620非adx/600) → CE-4测试必须红"),
    # R139: CE-5反事实手术(tag: CE-5手术)
    ("tools/counterfactual_probe.py",
     "    dx2 = float(np.clip(dx + sign * push_opp - sign * move_self,\n                        -600.0, 600.0))",
     "    dx2 = float(np.clip(dx - sign * push_opp - sign * move_self,\n                        -600.0, 600.0))",
     "CE-5推板方向反(拉向自己) → cf_probe手术测试必须红"),
    ("tools/counterfactual_probe.py",
     "    s[c + C_OPPCORNER] = 1.5 if (opp_x2 < 120 or opp_x2 > 1120) else 0.0",
     "    s[c + C_OPPCORNER] = 0.0",
     "CE-5贴角标志不重算(距离位手术残缺) → cf_probe手术测试必须红"),
    # BH-4.2(R140): untech语义门(tag: BH-4.2)
    ("feat_builder.py",
     "    return ((side.get(\"untech\", 0) or 0)\n            if side.get(\"action\", 0) in HIT_ACT_IDS else 0)",
     "    return side.get(\"untech\", 0) or 0",
     "BH-4.2语义门拆除(残留读数污染复活, 51.7%帧假锁定) → untech门测试必须红"),
    ("train_tm.py",
     "    return ((300 <= left.get(\"action\", 0) < 600)\n            or eff_untech(left) > 0)",
     "    return ((300 <= left.get(\"action\", 0) < 600)\n            or (left.get(\"untech\", 0) or 0) > 0)",
     "BH-4.2空中被动豁免回退(飞翔逃逸被错误豁免) → untech门测试必须红"),
    ("macro_executor.py",
     "                opp_untech = eff_untech(right)",
     "                opp_untech = right.get(\"untech\", 0) or 0",
     "BH-4.2 link门回退(残留读数空等目押) → link门测试必须红"),
    # BH-3.2(R141): 守备段位逐角色表(tag: BH-3.2)
    ("feat_builder.py",
     "        _tab = LOW_ATTACK_IDS_BY_CHAR.get(_ch) if _ch else None\n        return LOW_ATTACK_IDS if _tab is None else _tab",
     "        return LOW_ATTACK_IDS",
     "BH-3.2逐角色段位表旁路(回退全局假设表, 2B/2C虚报复活) → guard_bh32测试必须红"),
    ("feat_builder.py", "LOW_ATTACK_IDS = frozenset((303, 311))", "LOW_ATTACK_IDS = frozenset((303,))",
     "BH-3.2回落表残缺(未注入角色f2A下段信号丢失) → guard_bh32测试必须红"),
    # BH-1(R142): 行为健康计数器(tag: BH-1)
    ("behavior_health.py",
     "            elif prev_dmg > 0:\n                fate = 'hit'",
     "            elif True:\n                fate = 'hit'",
     "BH-1连段fate判定废(全记hit, 完成率虚高) → behavior_health测试必须红"),
    ("behavior_health.py",
     "            if _hit:\n                self.follow['hit_atk' if _atk else 'hit_n'] += 1",
     "            if _hit:\n                self.follow['hit_n' if _atk else 'hit_atk'] += 1",
     "BH-1续打率键反(hit_atk/hit_n互换=指标反转) → behavior_health测试必须红"),
    # BH-4.3(R143): 对位先验表(tag: BH-4.3)
    ("data/guide_tables/matchup_combo_prior.json",
     '"chars": ["cirno", "iku", "sanae", "youmu", "yuyuko"]',
     '"chars": ["cirno", "iku", "sanae", "youmu", "yuyuko", "bogus_char"]',
     "BH-4.3先验表混入非法角色名(污染对位掩码集) → matchup_prior测试必须红"),
    # BH-4.1(R144): matcher连段语境(tag: BH-4.1) — 用户裁定(2026-10-16):
    # 连段中的等待(放帧)与位移是极其重要的一等技术, 移动/等待标签
    # 不抑制; 变异守卫=抑制机制复活时保留测试必须红
    ("bc_match.py",
     "            next_free = f + L\n            if idx in fam:",
     "            if (combo_ctx is not None and f < len(combo_ctx)\n                    and combo_ctx[f] and self.macros[idx][0]\n                    in ('待机', '前进', '后退')):\n                continue\n            next_free = f + L\n            if idx in fam:",
     "BH-4.1抑制机制复活(违反用户裁定: 连段等待/位移一等教学不删) → matcher_ctx保留测试必须红"),
    # S-6(R147): BC序列感知采样(tag: S-6)
    ("bc_io.py",
     "    st = int(starts[gi]) + (int(rng.integers(0, max(1, L - k + 1)))\n                            if L > k else 0)\n    return np.arange(st, st + min(k, L))",
     "    st = int(starts[gi])\n    return np.arange(st, st + min(k, L))",
     "S-6窗口起点恒组首(样本偏置+假跨组风险) → bc_seq测试必须红"),
    # 从零#5(2026-10-17): P0-2 路径可复现 + P0-3 看门狗口径
    ("run_parallel.py",
     "DIR = os.path.dirname(os.path.abspath(__file__))",
     "DIR = r'%USERPROFILE%\\Desktop\\workplace\\th123_rl'",
     "路径钉死用户家目录(访客克隆到别处import/glob全废, bc分片glob=0) → P0-2零字面量断言必须红"),
    ("fleet_supervisor.py",
     "    rows = _wd_proc_rows(ps_out)\n    if rows is None:\n        return None\n    root = os.getpid() if root_pid is None else root_pid",
     "    rows = _wd_proc_rows(ps_out)\n    if rows is None:\n        return None\n    return sum(r[2] for r in rows)   # 变异: 全机口径(旁路/对照臂混入)\n    root = os.getpid() if root_pid is None else root_pid",
     "训练族口径退化为全机(旁路/对照臂混入训练负载) → cpu_family测试必须红"),
    ("tools/train_start.py",
     "-and $_.CommandLine -notmatch 'th123_rl_control'}; \"",
     "}; \"",
     "前置清理回退为脚本名匹配(主臂重启静默杀对照臂) → control臂豁免断言必须红"),
    ("bc_build.py",
     "        if keys:                        # 非空按键元组 = 有实际动作\n            return False",
     "        if keys:\n            return True",
     "裸SC判据失效(复合终结宏被当裸卡宏二次解析=标签覆盖) → sc_label测试必须红"),
    ("tools/seed_league_pool.py",
     "        while (os.path.exists(os.path.join(d, 'seed_%s.npz' % _ts))\n               or os.path.exists(os.path.join(d, 'seed_%s_v.npz' % _ts))):",
     "        while False and (os.path.exists(os.path.join(d, 'seed_%s.npz' % _ts))\n               or os.path.exists(os.path.join(d, 'seed_%s_v.npz' % _ts))):",
     "种子时间戳去重失效(同秒refresh同名覆盖=--refresh静默无效) → league20 refresh断言必须红"),
    ("tools/eval_matrix.py",
     "    driver_a.load(live_model_path(char_a, STORE))",
     "    driver_a.load(os.path.join(STORE, 'model_ppo_%s.npz' % char_a))",
     "评估回退读单机旧档(报告静默过期=活档未被评估) → P1-1活档断言必须红"),
    ("train_tm.py",
     "                _fld = os.path.join(STORE_DIR, 'frame_logs', self.char)",
     "                _fld = os.path.join(STORE_DIR, 'frame_logs')",
     "帧日志回退共享目录(三角色互删日志) → P1-5隔离断言必须红"),
    ("episode_core.py",
     "        for _k, _n in check_row_counts(arrays):",
     "        for _k, _n in []:",
     "读者行数对账失效(半截episode被消费后删除) → P1-4行数断言必须红"),
    ("tools/situation_library.py",
     "            keep = np.random.default_rng(7).random(len(idx)) < float(h)",
     "            keep = np.random.default_rng(7).random(len(idx)) < (1.0 - float(h))",
     "热度极性反转(弱点对位h=1.0保留0行=注入全空) → le1b测试必须红"),
    ("tools/le1b_inject.py",
     "    eff = min(INJECT_RATIO, INJECT_CAP)",
     "    eff = INJECT_RATIO",
     "20%注入上限失效(半批被回放行挤占) → le1b测试必须红"),
    ("fleet_supervisor.py",
     "                _dec = restart_budget({key: rk}, _last_restart)[key]",
     "                _dec = rk",
     "重启预算衰减断线(终身累计=偶发崩溃永久减员) → watchdog测试必须红"),
    ("fleet_supervisor.py",
     "                write_heartbeat(alert=_alert_txt)\n                time.sleep(COOLDOWN_S)",
     "                write_heartbeat()\n                time.sleep(COOLDOWN_S)",
     "重启路径心跳丢 alert(减员告警被自己清掉) → watchdog测试必须红"),
    ("tools/status_dashboard.py",
     "        rows2.append(kv('特征维度', 'CORE_DIMS=%d (真值)' % _cd, 'good'))",
     "        rows2.append(kv('活性巡检', '通过(358维, 29+8段)', 'good'))",
     "仪表写死\"通过\"(假绿: 巡检从未执行/维度硬编码) → P1-9断言必须红"),
    ("learner_hub.py",
     "    for _b in _bhs[:max(0, len(_bhs) - 1000)]:",
     "    for _b in []:",
     "BH旁车保留策略失效(旁车无界增长) → P2旁车断言必须红"),
    ("tools/audit_all.py",
     "        _paths += _acts[:1]",
     "        _paths += []",
     "奖励面板回退只读learner日志(结构性空) → P2仪表断言必须红"),
    ("ppo.py",
     "                dflat = dh @ self.W1.T - (dH1v @ _W1v_pre.T)[:, :TRUNK_FLAT]",
     "                dflat = dh @ self.W1.T - (dH1v @ self.W1v.T)[:, :TRUNK_FLAT]",
     "主干反传混用已更新的W1v(numpy与torch单步不等价) → P1-11断言必须红"),
    ("tools/fangyu_extract.py",
     "    if any(w in s for w in ('的', '会', '是', '在', '和', '被', '也', '都',",
     "    if any(w in s for w in ('zzz_none',):",
     "叙述句虚词判据拆除(句子重新冒充招名) → P1-12断言必须红"),
    ("tools/eval_matrix.py",
     "        report['model_temp'] = _temps",
     "        pass",
     "温度披露缺失(种子temp2.0与主模型0.5混比) → P1-2断言必须红"),
    ("episode_core.py",
     "        if _key not in _VERSION_WARNED:",
     "        if False:",
     "版本损坏恢复静默(actor永久用旧权重且无提示) → P2版本断言必须红"),
    ("bc_build.py",
     "        _rng_low = np.random.default_rng(20261018 + n_sh * 7 + int(n_low))",
     "        _rng_low = None",
     "降采样回退取前N(低信息样本偏置到最早对位槽) → P1-13断言必须红"),
    ("train_tm.py",
     "            except OSError as _e_load:",
     "            except KeyError as _e_load:",
     "池快照装载失败不捕获(FileNotFound→空权重进局崩) → P0池回退断言必须红"),
]


def _rederive_dim_anchors():
    """P1根治(2026-10-14晚审计, 维度锚漂移第三次复发): CORE_DIMS变异锚
    从FeatureBuilder活常量**运行时派生** — 静态字面量跟不了每次特征迁移
    (R80两轮修沙箱清单漂移后, 本轮证明锚串漂移是独立复发面; 变异执行器
    的n<1活性检查只能事后报警, 派生让锚永不漂移)。
    泛化: 凡目标串匹配 r'^CORE_DIMS = \\d+$' 的锚一律重写为现值,
    未来同类维度常量锚在MUTATIONS用同格式书写即自动纳入。"""
    import re as _re
    import sys as _sys
    if ROOT not in _sys.path:
        _sys.path.insert(0, ROOT)
    from feat_builder import FeatureBuilder as _FB
    live = _FB.CORE_DIMS
    hits = 0
    for i, (f, old, new, why) in enumerate(MUTATIONS):
        if _re.match(r'^CORE_DIMS = \d+$', old):
            MUTATIONS[i] = (f, 'CORE_DIMS = %d' % live,
                            'CORE_DIMS = %d' % (live - 1),
                            why + '(锚活派生@%d)' % live)
            hits += 1
    return hits


_DERIVED = _rederive_dim_anchors()


def check_anchor_liveness():
    """防复发(bug_2026-10-14_dim_mutation_anchor_drift3.md):

    派生只覆盖CORE_DIMS族; 本断言是**通用保险** — 凡变异锚串含
    `NAME = 数字`且目标文件存在同名模块级常量赋值但值不同 →
    响亮失败(锚串与活常量漂移, 变异永不生效)。与FILES完备性
    根治断言并列。返回错误清单(空=通过)。"""
    import re as _re
    errs = []
    for f, old, _new, why in MUTATIONS:
        src_path = os.path.join(ROOT, f)
        if not os.path.exists(src_path):
            continue
        src = open(src_path, encoding='utf8', errors='replace').read()
        for m in _re.finditer(r'([A-Z_][A-Z0-9_]*) = (\d+)', old):
            name, lit = m.group(1), m.group(2)
            # \s*: 常量可能是类内缩进属性(如FeatureBuilder.CORE_DIMS)
            fm = _re.search(r'^\s*%s = (\d+)' % _re.escape(name), src, _re.M)
            if fm and fm.group(1) != lit:
                errs.append(
                    '锚串漂移: %s 锚钉%s 而文件实际%s = %s — 变异永不生效'
                    ' [%s]' % (f, lit, name, fm.group(1), why[:40]))
    return errs


_ANCHOR_LIVENESS = check_anchor_liveness()
if _ANCHOR_LIVENESS:        # 导入期即响亮(与FILES完备性同拍), 不等跑完
    print('[gate_selftest] !! 维度锚活性自检失败:')
    for _e in _ANCHOR_LIVENESS:
        print('   ', _e)
    raise SystemExit(2)


def _free_gb(path):
    """给沙箱盘留多少空间(GB)。查询失败 → None(不拦)。"""
    try:
        import ctypes
        n = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            str(path), None, None, ctypes.byref(n))
        return n.value / 1024 / 1024 / 1024
    except Exception:
        return None


def _clean_stale_sandboxes(root, max_age_h=2.0):
    """宪法R13"按时清理": 回收超过max_age_h的gate_selftest_*沙箱
    (被杀进程/断电的残留)。活跃运行安全: base目录随mut_*子目录创建
    持续刷新mtime, 不会误删并发运行中的沙箱。"""
    import time as _t
    now = _t.time()
    try:
        entries = os.listdir(root)
    except OSError:
        return 0
    # P2(2026-10-15): 清理前缀扩展到全部测试残留(gate_selftest_/
    # fleet_proto_/w3_/d4_/gpu_*/_r63_等) — 原只扫gate_selftest_,
    # 其他测试的mkdtemp残留(如st/旧目录10天5.7GB)永不被回收
    _PREFIXES = ("gate_selftest_", "fleet_proto_", "w3_", "d4_",
                 "gpu_equiv_", "gpu_upd_", "b_test_", "hs_b2_",
                 "hd_i_", "_r63_")   # 不含宽泛'tmp'(防误伤)
    n = 0
    for e in entries:
        if not any(e.startswith(x) for x in _PREFIXES):
            continue
        p = os.path.join(root, e)
        try:
            if now - os.path.getmtime(p) > max_age_h * 3600:
                shutil.rmtree(p, ignore_errors=True)
                n += 1
        except OSError:
            pass
    return n


def _sandbox_tmpdir():
    """沙箱根目录。**宪法R13(用户2026-10-11明令): 所有沙箱一律落D盘,
    禁用系统盘** — 默认 D:/temp/gate_sandbox; SELFTEST_TMPDIR 仅作
    无D盘机器的覆盖口。

    事故血统: R63(F6)首例(%TEMP%在C:, 失败不自清, 残留1.5GB×2把系统盘
    压满)于2026-10-11原样复发(C:100%仅剩526MB, 自检WinError 112假死)
    → 用户裁定升格红线: D盘+按时清理(启动自动回收>2h过期沙箱, 含
    系统盘遗留清扫; 正常/异常退出由finally自清, 机制在位)。
    """
    d = os.environ.get("SELFTEST_TMPDIR") or r"D:\temp\gate_sandbox"
    os.makedirs(d, exist_ok=True)
    n = _clean_stale_sandboxes(d)
    # P2: 父目录(D:	emp)历史残留也扫(旧默认位置留下的沙箱)
    _parent = os.path.dirname(d)
    if _parent and os.path.isdir(_parent):
        n += _clean_stale_sandboxes(_parent)
    import tempfile as _tf
    _sys = _tf.gettempdir()
    if os.path.realpath(_sys) != os.path.realpath(d):
        n += _clean_stale_sandboxes(_sys)
    if n:
        print("[sandbox] R13按时清理: 回收%d个过期沙箱" % n)
    return d


def build_sandbox(sb):
    # R63: 大件(mod源码树)拷贝前先看盘 — 空间不足则跳过该件而不是
    # 中途抛WinError 112(半建沙箱 + 裸traceback, 无法判断是门禁坏了
    # 还是盘满了)。modroot缺席时C9相关项按AGENTS.md降级为WARN。
    _need_gb = 0.4
    _free = _free_gb(sb)
    _skip_big = (_free is not None and _free < _need_gb)
    if _skip_big:
        print("[sandbox] 沙箱盘仅剩%.2fGB(<%.1fGB) — 跳过大件拷贝"
              "(mod源码树; C9降WARN)。可用 SELFTEST_TMPDIR 指到大盘。"
              % (_free, _need_gb))
    for f in FILES:
        _d = os.path.dirname(os.path.join(sb, f))
        if _d:
            os.makedirs(_d, exist_ok=True)
        shutil.copy2(os.path.join(ROOT, f), os.path.join(sb, f))
    os.makedirs(os.path.join(sb, "tools"), exist_ok=True)
    for tf in sorted(os.listdir(os.path.join(ROOT, "tools"))):
        if tf.endswith(".py") or tf.endswith(".json"):
            shutil.copy2(os.path.join(ROOT, "tools", tf),
                         os.path.join(sb, "tools", tf))
    # JZ-2(2026-10-14): 数据表副本 — frame_adv等表驱动模块在模块级
    # 严格加载guide_tables, 沙箱缺数据=基线假红(与style_pca同批同步)
    _gt_src = os.path.join(ROOT, "data", "guide_tables")
    if os.path.isdir(_gt_src):
        _gt_dst = os.path.join(sb, "data", "guide_tables")
        os.makedirs(_gt_dst, exist_ok=True)
        for tf in sorted(os.listdir(_gt_src)):
            if tf.endswith(".json"):
                shutil.copy2(os.path.join(_gt_src, tf),
                             os.path.join(_gt_dst, tf))
    # macros数据件(wave_ext模块级加载charge_table.json — 沙箱缺件=
    # import即FileNotFoundError, guide_tables同类第二例)
    _ct = os.path.join(ROOT, "macros", "charge_table.json")
    if os.path.exists(_ct):
        os.makedirs(os.path.join(sb, "macros"), exist_ok=True)
        shutil.copy2(_ct, os.path.join(sb, "macros",
                                       "charge_table.json"))
    _pca = os.path.join(ROOT, "data", "style_pca.npz")
    if os.path.exists(_pca):
        os.makedirs(os.path.join(sb, "data"), exist_ok=True)
        shutil.copy2(_pca, os.path.join(sb, "data", "style_pca.npz"))
    # 行为测试随沙箱(沙箱门禁从自身目录运行它们)
    _tdir = os.path.join(sb, "tests")
    os.makedirs(_tdir, exist_ok=True)
    for t in sorted(os.listdir(os.path.join(ROOT, "tests"))):
        if t.startswith("test_") and t.endswith(".py"):
            shutil.copy2(os.path.join(ROOT, "tests", t),
                         os.path.join(_tdir, t))
    # BC库副本(C12断言指向沙箱)
    bcdir = os.path.join(sb, "bc")
    os.makedirs(bcdir, exist_ok=True)
    for ch in ("reimu", "marisa", "suika"):
        p = os.path.join(ROOT, "data", "bc", "bc_%s.npz" % ch)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(bcdir, "bc_%s.npz" % ch))
    # store副本(distill+全角色模型档+宏计数 — C5/R44断言数据源)
    store = os.path.join(sb, "store")
    os.makedirs(store, exist_ok=True)
    _msdir = r"D:\temp\th123_models"
    for fn in sorted(os.listdir(_msdir)):
        if (fn.startswith(("distill_data_", "model_ppo_",
                           "macro_counts_"))
                and (fn.endswith(".npz") or fn.endswith(".npy"))):
            shutil.copy2(os.path.join(_msdir, fn),
                         os.path.join(store, fn))
    # mod血统档(C9断言数据源)
    _prov = os.path.join(ROOT, "mod_provenance.json")
    if os.path.exists(_prov):
        shutil.copy2(_prov, os.path.join(sb, "mod_provenance.json"))
    # R63(F6): 人类基线的**派生档**随沙箱(2KB; 191份重放原文约200MB不适合拷)。
    # F6测试的锚断言因此在沙箱内也成立; 重放原文仍是唯一真值源。
    _hb = os.path.join(ROOT, "data", "human_baseline.json")
    if os.path.exists(_hb):
        os.makedirs(os.path.join(sb, "data"), exist_ok=True)
        shutil.copy2(_hb, os.path.join(sb, "data", "human_baseline.json"))
    # oracle侧源码树(C9-oracle源断言的变异载体)
    oroot = os.path.join(sb, "oraclemod")
    for rel in ("TrainingMod\\state.cpp", "TrainingMod\\network.cpp"):
        dst = os.path.join(oroot, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        srcf = os.path.join(r"D:\temp\soku_arch\build\src", rel)
        if os.path.exists(srcf):
            shutil.copy2(srcf, dst)
    # mod源码树完整拷贝(C9血统哈希覆盖全树+变异载体; 只拷源/头文件)
    _msrc_root = r"D:\temp\build\SokuAI-master"
    if os.path.isdir(_msrc_root) and not _skip_big:
        shutil.copytree(
            _msrc_root, os.path.join(sb, "modroot"),
            ignore=shutil.ignore_patterns(
                "*.obj", "*.lib", "*.pdb", "*.ipdb", "*.iobj",
                "*.dll", "*.exp", "x64", ".vs", "Release", "Debug",
                "*.log", "*.tlog"))
    # 沙箱mod配置(C16断言可变异化)
    ml_real = os.path.join(
        r"D:\touhou\hisoutensoku2026-06-15\th123_train",
        "ModLoaderSettings.json")
    if os.path.exists(ml_real):
        shutil.copy2(ml_real, os.path.join(sb, "ModLoaderSettings.json"))


def run_gate(sb, store, env_extra=None):
    env = dict(os.environ)
    env["TH123_STORE"] = store
    env["TH123_MODROOT"] = os.path.join(sb, "modroot")
    env["TH123_BC_DIR"] = os.path.join(sb, "bc")
    _ml = os.path.join(sb, "ModLoaderSettings.json")
    if os.path.exists(_ml):
        env["TH123_ML"] = _ml
    env["TH123_ORACLE_MODROOT"] = os.path.join(sb, "oraclemod")
    if env_extra:
        env.update(env_extra)
    # R63: 超时从1500→5400。实测裸跑门禁93s, 但沙箱内跑**全部**行为测试
    # (含torch更新)且与活训练抢CPU时, 1500s会被突破 → TimeoutExpired
    # 直接把自检打断(本轮真实事故: 报出负超时, 疑似期间墙钟跳变/系统挂起),
    # 表现为"治理工具崩了"而不是"某条变异漏网"。可经 SELFTEST_GATE_TIMEOUT
    # 覆盖。
    _to = int(os.environ.get("SELFTEST_GATE_TIMEOUT", "5400"))
    try:
        r = subprocess.run(
            [PY, "-X", "utf8", os.path.join(sb, "tools", "contract_check.py")],
            capture_output=True, text=True, env=env, timeout=_to)
    except subprocess.TimeoutExpired as e:
        # 明确区分"沙箱门禁超时"与"断言变红/漏网" — 否则会被误读成门禁坏了
        print("[sandbox] 门禁超时(>%ds) — 该变异无法判定(非漏网)。"
              "可用 SELFTEST_GATE_TIMEOUT 调大, 或空闲时重跑。" % _to)
        return 124, (e.stdout or "") if isinstance(e.stdout, str) else ""
    return r.returncode, r.stdout


def main():
    fails = []
    # R63: base必须在try**之内**创建 — 原在try之前, build_sandbox抛错时
    # finally不执行 → 半建沙箱(~1.5GB)永久残留在%TEMP%(实测残留两份,
    # 把系统盘从数GB压到1.4GB, 后续断言全部因磁盘满而假死)。
    _tmp = _sandbox_tmpdir()
    base = None
    try:
        base = tempfile.mkdtemp(prefix="gate_selftest_", dir=_tmp)
        print("[self-test] 沙箱: %s (剩余%.2fGB)"
              % (base, _free_gb(base) or -1))
        # ---- 基线: 未变异沙箱必须绿 ----
        sb = os.path.join(base, "baseline")
        os.makedirs(sb)
        build_sandbox(sb)
        store = os.path.join(sb, "store")
        rc, out = run_gate(sb, store)
        print("基线(未变异): exit=%d" % rc)
        if rc != 0:
            print(out[-2000:])
            print("[自检失败] 基线不绿 — 先修门禁本身")
            return 1

        # ---- 损坏产物检出: 截断distill → C5必须红 ----
        victim = os.path.join(store, "distill_data_reimu.npz")
        if os.path.exists(victim):
            size = os.path.getsize(victim)
            with open(victim, "r+b") as fh:
                fh.truncate(size // 2)
            rc2, out2 = run_gate(sb, store)
            ok = rc2 != 0 and ("  FAIL" in out2 or "FAIL项" in out2)
            print("变异[distill截断损坏]: exit=%d %s"
                  % (rc2, "✓红" if ok else "✗漏网"))
            if not ok:
                fails.append("C5损坏文件检出(空断言)")
            shutil.copy2(os.path.join(r"D:\temp\th123_models",
                                      "distill_data_reimu.npz"), victim)

        # ---- Y≡常数列占位必须红 ----
        victim2 = os.path.join(store, "distill_data_marisa.npz")
        real2 = os.path.join(r"D:\temp\th123_models",
                             "distill_data_marisa.npz")
        had_real = os.path.exists(real2)
        if had_real:
            shutil.copy2(real2, victim2)
        n_rows = 8
        np.savez(victim2, X=np.zeros((n_rows, 4)),
                 Y=np.full(n_rows, -1))
        rc3, out3 = run_gate(sb, store)
        ok3 = rc3 != 0 and ("  FAIL" in out3 or "FAIL项" in out3)
        print("变异[distill Y≡-1占位]: exit=%d %s"
              % (rc3, "✓红" if ok3 else "✗漏网"))
        if not ok3:
            fails.append("A组Y非常数列断言(空断言)")
        if had_real:
            shutil.copy2(real2, victim2)
        else:
            os.remove(victim2)

        # ---- 逐条源码变异(R61: SELFTEST_TAGS增量过滤) ----
        _tags = [t.strip() for t in
                 os.environ.get("SELFTEST_TAGS", "").split(",") if t.strip()]
        for f, old, new, why in MUTATIONS:
            if _tags and not any(t in why for t in _tags):
                print("变异[%s]: ○跳过(增量模式未命中标签)" % why[:50])
                continue
            sb = os.path.join(base, "mut_%s_%d" % (f, abs(hash(old)) % 9999))
            os.makedirs(sb)
            build_sandbox(sb)
            store = os.path.join(sb, "store")
            target = os.path.join(sb, f)
            if not os.path.exists(target):
                print("变异[%s | %s]: ○跳过(沙箱无此文件)" % (f, why))
                shutil.rmtree(sb, ignore_errors=True)
                continue
            txt = open(target, encoding="utf-8").read()
            n = txt.count(old)
            if n < 1:
                print("变异[%s | %s]: ✗模式未命中 — 变异定义失效" % (f, why))
                fails.append("变异定义失效: " + why)
                continue
            open(target, "w", encoding="utf-8").write(txt.replace(old, new))
            rc, out = run_gate(sb, store)
            if rc == 124:
                # R63: 沙箱门禁超时(环境问题) ≠ 变异被拦截。若当"红"处理,
                # 一条永不触发的断言会在忙时假通过 — 那是"空断言"的另一种
                # 伪装。如实标为无法判定并计入失败。
                print("变异[%s | %s]: ○无法判定(沙箱门禁超时, 非漏网)"
                      % (f, why))
                fails.append("超时未判定: " + why)
                shutil.rmtree(sb, ignore_errors=True)
                continue
            ok = rc != 0 and ("  FAIL" in out or "FAIL项" in out)
            print("变异[%s | %s]: exit=%d %s"
                  % (f, why, rc, "✓红" if ok else "✗漏网"))
            if not ok:
                fails.append(why)
            shutil.rmtree(sb, ignore_errors=True)
    finally:
        if base:
            shutil.rmtree(base, ignore_errors=True)

    print()
    if fails:
        print("==== 变异自检: %d条漏网 — 对应断言是空的, 需重写为行为断言 ===="
              % len(fails))
        for x in fails:
            print("  ✗", x)
        return 1
    print("==== 变异自检: 全部%d+1条变异均被门禁拦截 ====" % len(MUTATIONS))
    print("(边界: 变异测试只保证断言可证伪, 不保证前提为真 — "
          "外部事实前提靠C9血统/R6溯源守护)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
