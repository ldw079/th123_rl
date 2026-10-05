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
         "macros.py",
         "macros_marisa.py",
         "macros_suika.py",
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
         "oracle_batch2.py",
         "macros_sakuya.py",
         "macros_patchouli.py",
         "macros_yuyuko.py",
         "macros_reisen.py",
         "macros_komachi.py",
         "macros_tenshi.py",
         "macros_alice.py",
         "macros_youmu.py",
         "macros_remilia.py",
         "macros_yukari.py",
         "macros_aya.py",
         "macros_iku.py",
         "macros_sanae.py",
         "macros_cirno.py",
         "macros_meiling.py",
         "macros_utsuho.py",
         "macros_suwako.py",
         "deck_sampler.py",
         "league.py",
         "teach.py",
         "ppo_gpu.py",
         "frame_events.py",
         "frame_macros.py",
         "episode_core.py",
         "actor_worker.py",
         "learner_hub.py",
         "fleet_supervisor.py"]

# (文件, 原文, 变异文, 防的回归)
MUTATIONS = [
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
    ("threat.py", "t0 = max(0.0, t0)", "",
     "P0-4b 负TTI钳位回归 → 威胁负例必须红"),
    ("threat.py", "GAME_FPS = 62", "GAME_FPS = 60",
     "62教义回退 → C1必须红"),
    ("macros.py", "return f / 62.0", "return f / 60.0",
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
    ("feat_builder.py", "CORE_DIMS = 308", "CORE_DIMS = 307",
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
    ("tools/mod_provenance.json", "\"deployed_md5\": \"386737DE01ACFDECE70A27F7F6842A26\"", "\"deployed_md5\": \"0000000000000000000000000000000\"",
     "血统档案被篡改/回滚旧DLL → C9必须红"),
    ("modroot\\Training\\TrainingMod\\state.cpp", "WEATHER_MOUNTAIN_VAPOR", "WEATHER_RIVER_MIST",
     "晴岚遮蔽从编译输入消失 → C9必须红"),
    ("modroot\\Training\\TrainingMod\\network.cpp", "WEATHER_AURORA", "WEATHER_TWILIGHT",
     "极光遮蔽从编译输入消失 → C9必须红"),
    ("modroot\\Training\\TrainingMod\\sokuData.cpp", "//", "///",
     "源码改动未重编(哈希漂移) → C9必须红"),
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
    ("macros.py", "[((\"down\",), 6), ((\"down\", \"A\"), 10)]", "[((\"down\", \"A\"), 10)]",
     "死招回归: 2A方向预置被删 → C11必须红"),
    ("portmap.py", "\"train_rebuild\": (20850, 20899),", "\"train_rebuild\": (20895, 20905),",
     "端口段重叠回归 → C12必须红"),
    ("train_tm.py", "rebuild_port(self.slot, ep)", "self.env.base_port + 100 + ep",
     "异常重建回退跨段公式 → C12必须红"),
    ("side_driver.py", "if isinstance(keys, str) and keys.startswith(\"sc:\"):", "if isinstance(keys, str):",
     "对手侧门步回退丢弃(开环对赌复活) → C12必须红"),
    ("tm_env.py", "except ProtocolError as e:", "except RuntimeError as e:",
     "回退子串匹配错误分支(D8) → C12必须红"),
    ("feat_builder.py", "CORE_DIMS = 308", "CORE_DIMS = 309",
     "R17侧维回退 → C2布局断言必须红"),
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
    ("reach_maps.py", "'jA': (306,), 'j6A': (307,), 'j2A': (308,), 'j8A': (309,),", "'jA': (306,), 'j6A': (307,), 'j2A': (308,),",
     "R29显式表丢j8A(空中四招残缺) → C13空中断言必须红"),
    ("feat_builder.py", "if left.get(\"action\", 0) in GUARD_ALL_IDS:\n            return 0", "if False:\n            return 0",
     "R33格挡graze排除移除(防御态刷graze通道复活) → C13源断言必须红"),
    ("train_tm.py", "_opp_a >= 300 and _opp_a < 600", "_opp_a >= 999",
     "R34帧级防御中断失效(硬直中对手攻击不交还控制) → C13源断言必须红"),
    ("train_tm.py", "left[\"spirit\"] < 100", "left[\"spirit\"] < 0",
     "R34灵力门控失效(空灵力仍出攻击) → C13源断言必须红"),
    ("train_tm.py", "if macro_queue:\n                    keys, fl = macro_queue[0]", "else:\n                    keys, fl = macro_queue[0]",
     "R38 P0-1回退: 受击中止清队后空取[0] → IndexError炸整局 → 队列守卫断言必须红"),
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
    ("macros_suika.py", "201: 2,", "",
     "R39§4-6回退: suika的sc:201耗费项被删 → sc∈SC_COST断言必须红"),
    ("reach_maps.py", "'TM·对空连': (308,),", "",
     "R39§4-7回退: TM宏射程登记条目被删 → TM登记率断言必须红(注: 变异须删条目而非改空元组 — 断言查表成员性, 空元组仍算已登记)"),
    ("oracle_batch2.py", "'SOKUAI_INPUTLOG': '1'", "'SOKUAI_INPUTLOG': '0'",
     "R40回退: 精确对齐通道关闭 → INPUTLOG接线断言必须红"),
    ("bc_build.py", "arr[:, 0].astype(np.uint16), arr[:, 2].astype(np.uint16)", "arr[:, 1].astype(np.uint16), arr[:, 3].astype(np.uint16)",
     "R40回退: ilog取outKeys列(非inKeys) → 精确对齐分支断言必须红"),
    ("modroot\\Training\\TrainingMod\\state.cpp", "destination.hitStop = 0;", ";",
     "R40 M-1回退: 对象hitStop回到未初始化 → mod源断言必须红"),
    ("modroot\\Training\\TrainingMod\\network.cpp", "size_t cap = 255;", "size_t cap = 99999;",
     "R40 M-2回退: 对象截断失效(u8回绕流错位复活) → mod源断言必须红"),
    ("tools/mod_provenance.json", "\"built_md5\": \"B7E8C8052EF062783FC1131FA8F37DF6\"", "\"built_md5\": \"0000000000000000000000000000000\"",
     "R41§2-1回退: oracle血统漂移(档案与构建物不符) → C9-oracle断言必须红"),
    ("oraclemod\\TrainingMod\\state.cpp", "destination.hitStop = 0;", ";",
     "R41§2-2回退: oracle侧源码hitStop未初始化 → oracle源断言必须红"),
    ("run_parallel.py", "正常完成(%s局", "正常完成(%d局",
     "R42回退: eps按%d格式化(字符串首触TypeError炸监督器) → R42断言必须红"),
    ("train_tm.py", "POOL_SNAPSHOT_EVERY = 50", "POOL_SNAPSHOT_EVERY = 99999",
     "R43-A回退: 池快照事实上停摆(等于10-02冻结态) → 池刷新断言必须红"),
    ("train_tm.py", "COM_CLIMB_N = 20", "COM_CLIMB_N = 99999",
     "R43-B回退: COM阶梯永不升级(课程失效) → 阶梯断言必须红"),
    ("macros_sakuya.py", "(\"5A确认\", [((\"A\",), 10), ((), 2), (\"confirm\", 0)]),", "(\"5X确认\", [((\"A\",), 10), ((), 2), (\"confirm\", 0)]),",
     "R44回退: 宏定义改名但类别集合不变→幽灵名断言必须红(原全局替换宏定义与集合同变=无幽灵)"),
    ("tm_env.py", "\"reisen\": 10, \"komachi\": 12,", "\"reisen\": 10,",
     "R46§3-1回退: CHAR表缩回旧版(新角色KeyError) → CHAR20断言必须红"),
    ("macros_sakuya.py", "MACROS_SAKUYA = [(n, _norm_presteps(sc)) for n, sc in _RAW_SAKUYA]", "MACROS_SAKUYA = _RAW_SAKUYA",
     "R46§3-2回退: 规范化重绑定丢失(14宏跑原始脚本) → 规范化断言必须红"),
    ("tm_env.py", "\"reisen\": 10, \"komachi\": 12,", "\"reisen\": 10,",
     "R46§3-1回退: CHAR表缩回旧版(新角色KeyError) → CHAR20断言必须红"),
    ("frame_events.py", "159 <= my_a <= 167", "150 <= my_a <= 167",
     "R51§F1回退: GUARDSTUN含持防姿态(策略持防时误触发DD) → 检测断言必须红"),
    ("frame_events.py", "_DOWN_ACTS = frozenset(range(50, 99))", "_DOWN_ACTS = frozenset(range(200, 299))",
     "R51§F2回退: WAKEUP含冲刺系(每次冲刺误触起身) → 检测断言必须红"),
    ("train_tm.py", "if not macro_queue and not getattr(self, '_in_frame_reaction',\n                                               False):", "if not macro_queue:",
     "R51§F3回退: 守式检查整段移除(反应期间产生决策点=信用错配) → 守式断言必须红(原'not False and'变异是no-op)"),
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
    ("learner_hub.py", "temp=gpu_tr._temp, stored_logp=logps)", "temp=gpu_tr._temp)",
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
    ("feat_builder.py", "s[o + 1] = 1.0 if right[\"action\"] in LOW_ATTACK_IDS else 0.0", "s[o + 1] = 0.0",
     "R57-2.5回退: 下段位恒0(段位又全盲) → test_guard_height行为测试必须红"),
    ("episode_core.py", "data[\"schema\"] = np.array(EP_SCHEMA)", "data[\"schema\"] = np.array(99)",
     "R57-2.6回退: schema标错版本(消费端拒收) → schema断言必须红"),
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
    ("ppo_gpu.py", "logp_e = F.log_softmax", "logp_e = torch.zeros(len(Ye_t)).numpy() + F.log_softmax",
     "R60-F7回退: 专家行logp虚高(KL钉LR下限) → 专家行logp断言必须红"),
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
]


def build_sandbox(sb):
    for f in FILES:
        shutil.copy2(os.path.join(ROOT, f), os.path.join(sb, f))
    os.makedirs(os.path.join(sb, "tools"), exist_ok=True)
    for tf in sorted(os.listdir(os.path.join(ROOT, "tools"))):
        if tf.endswith(".py") or tf.endswith(".json"):
            shutil.copy2(os.path.join(ROOT, "tools", tf),
                         os.path.join(sb, "tools", tf))
    # 行为测试随沙箱(沙箱门禁从自身目录运行它们)
    for t in sorted(os.listdir(ROOT)):
        if t.startswith("test_") and t.endswith(".py"):
            shutil.copy2(os.path.join(ROOT, t), os.path.join(sb, t))
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
    if os.path.isdir(_msrc_root):
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
    r = subprocess.run(
        [PY, "-X", "utf8", os.path.join(sb, "tools", "contract_check.py")],
        capture_output=True, text=True, env=env, timeout=1500)
    return r.returncode, r.stdout


def main():
    fails = []
    base = tempfile.mkdtemp(prefix="gate_selftest_")
    try:
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
            ok = rc != 0 and ("  FAIL" in out or "FAIL项" in out)
            print("变异[%s | %s]: exit=%d %s"
                  % (f, why, rc, "✓红" if ok else "✗漏网"))
            if not ok:
                fails.append(why)
            shutil.rmtree(sb, ignore_errors=True)
    finally:
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
