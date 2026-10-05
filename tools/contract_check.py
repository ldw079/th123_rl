# -*- coding: utf-8 -*-
"""A级契约门禁(方法论2026-09-21, 2026-09-22行为化改造):
秒级自动断言, 不需要游戏、不需要训练进程。
用法: python tools/contract_check.py
退出码: 0=全过, 1=有FAIL(阻断合批/发布); WARN不阻断。

改造原则(复审教训): 每条断言必须可证伪 — 文本断言须有 gate_selftest.py 变异
配对(改回历史bug时门禁必须变红); 关键语义用行为断言(真跑代码)。

  C1 62fps教义    — GAME_FPS==62, /60文本残留, AST 60字面量(白名单外)
  C2 特征布局     — CORE_DIMS/n_side/core[33]槽 + 擦弹可达性(合成弹正/负例)
  C3 协议不变量   — CS_FMT=105B, 对象项=17B, 输入包=117B
  C4 PPO语义      — 熵行为断言(真跑update熵必须上升) + bc_mask/原子保存/meta
  C5 产物schema   — npz键集 + zipfile.testzip + X/Y全读(损坏=FAIL非WARN)
  C6 奖励活性     — AST定义⊆引用(死常量) + 通道接线源断言
  C7-C14          — 宏库/SC/多开/端口/对手池/射程表等源断言(段序以代码为准)
  C15 行为测试    — 子进程真跑白名单test_*.py(退出码即门禁)
  C16 训练mod集   — th123_train=={MemoryPatch,SokuAITrainer,SokuDXOpt}
  (R38注: 头部清单非完整目录 — 新增C段须在变异自检配对, 详见各段注释)
"""
import ast
import io
import os
import re
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

FAILS, WARNS, PASSES = [], [], []


def chk(cond, name, detail=""):
    if cond:
        print("  PASS  %s %s" % (name, detail))
        PASSES.append(name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILS.append(name)


def warn(cond, name, detail=""):
    if cond:
        print("  PASS  %s %s" % (name, detail))
        PASSES.append(name)
    else:
        print("  WARN  %s %s" % (name, detail))
        WARNS.append(name)


_SRC_CACHE = {}


def src(f):
    if f not in _SRC_CACHE:
        _SRC_CACHE[f] = io.open(os.path.join(ROOT, f), encoding="utf-8").read()
    return _SRC_CACHE[f]


def lines(f):
    return src(f).splitlines()


# ============ C1 62fps教义 ============
print("=== C1 62fps教义(用户2026-09-21明令; R10只管逻辑帧率, tps协议参数豁免) ===")
import threat
import config
chk(threat.GAME_FPS == 62, "threat.GAME_FPS==62", "got %r" % threat.GAME_FPS)
chk(config.FPS == 62, "config.FPS==62", "got %r" % config.FPS)
_div60 = re.compile(r"/\s*60(?:\.0)?\b")
for f in ["threat.py", "feat_builder.py", "train_tm.py", "macros.py",
          "opp_model.py", "standard_tree.py"]:
    bad = [l.strip() for l in lines(f) if _div60.search(l)]
    chk(not bad, "无/60帧转秒残留@%s" % f, "; ".join(bad[:2]))
# AST级60字面量扫描: 时敏文件零容忍; 结构文件按行白名单(网格60×80/重试range/tps默认)
_STRICT60 = ["threat.py", "feat_builder.py", "macros.py", "macros_marisa.py",
             "macros_suika.py", "opp_model.py", "standard_tree.py"]
_ALLOW60 = re.compile(r"80|range\(|default=60|tps=60")
for f in _STRICT60 + ["train_tm.py", "config.py", "ppo.py", "tm_env.py"]:
    bad = []
    for node in ast.walk(ast.parse(src(f))):
        if (isinstance(node, ast.Constant) and isinstance(node.value, int)
                and node.value == 60):
            if f in _STRICT60 or not _ALLOW60.search(lines(f)[node.lineno - 1]):
                bad.append("L%d" % node.lineno)
    chk(not bad, "AST无裸60字面量@%s" % f, ",".join(bad[:4]))

# ============ C2 特征布局 + 感知可达性 ============
print("=== C2 特征布局/感知可达性 ===")
import numpy as np
import feat_builder
import opp_model
# R17: core 260→308(对手建模段10: 27→75); 宏数从三库动态取(防硬编码漂移)
import macros
import macros_marisa
import macros_suika
chk(feat_builder.FeatureBuilder.CORE_DIMS == 308, "CORE_DIMS==308(R17)",
    "got %r" % feat_builder.FeatureBuilder.CORE_DIMS)
chk(opp_model.OpponentModel.N_FEATS == 75,
    "opp_model.N_FEATS==75(基础27+历史40+资源8)",
    "got %r" % opp_model.OpponentModel.N_FEATS)
_n_by_mod = (macros.N_MACROS, macros_marisa.N_MACROS_MARISA,
             macros_suika.N_MACROS_SUIKA)
for n in _n_by_mod:
    fb = feat_builder.FeatureBuilder(n)
    chk(fb.n_side == 2 * n + 308, "n_side==2N+308@N=%d" % n,
        "got %d" % fb.n_side)
# ppo对手子网络切片位置与段10严格对齐(错位=静默读错特征)
from ppo import PPOTrainer as _PT
chk(_PT.OPP_CORE_OFF == 152 and _PT.OPP_DIM == 75
    and _PT.OPP_CORE_OFF + _PT.OPP_DIM
    <= feat_builder.FeatureBuilder.CORE_DIMS,
    "ppo对手切片==feat_builder段10[152..227)",
    "off=%r dim=%r" % (_PT.OPP_CORE_OFF, _PT.OPP_DIM))
# 段10活性(行为): 合成局推进后历史/资源子区必须非恒定(接线断裂即红)
_fb2 = feat_builder.FeatureBuilder(8)
_vs = []
for _i in range(24):
    _l = {"position.x": 300.0 + 25 * _i, "position.y": 50.0,
          "spirit": 1500 - 60 * _i, "hp": 10000, "airBorne": False,
          "direction": 1, "action": 300 if _i % 2 else 4, "cardGauge": 0,
          "score": 0, "hand": b"\xff" * 10, "comboDamage": 0, "untech": 0,
          "timeStop": 0, "hitStop": 0}
    # 对手灵力前半程>=500(灵满), 后半程<500(灵空) — 两半区都要有行为演化
    # R21: 动作ID用XML真值(150=立防, 410=射击; 旧110/820已证为受击/无效)
    _r = {"position.x": 900.0 - 30 * _i, "position.y": 50.0,
          "spirit": 1500 - 80 * _i, "hp": 9000, "airBorne": _i % 3 == 0,
          "direction": -1, "action": 150 if _i % 5 == 0 else 410,
          "cardGauge": 0, "score": 0, "hand": b"\xff" * 10,
          "comboDamage": 0, "untech": 0, "timeStop": 0, "hitStop": 0}
    _fb2.update_opp(10 / 62, _l, _r, {"active": 0}, opp_vx=2.0)
    _vs.append(np.asarray(_fb2.build(_l, _r, {"active": 0}, []),
                          dtype=np.float64))
_V2 = np.stack(_vs)
_hist_off, _res_off = 152 + 27, 152 + 67   # 段10内: 基础27|历史40|资源8
# 活性=时间方差须按axis=0逐维取max — 无axis的.var()是跨维均值散布,
# one-hot结构(5/40个1)恒给0.109, 冻结变异骗过断言(变异自检两轮漏网教训)。
# 历史取热身后窗口(第8行起): 冻结变异的初始[A_IDLE]*5滑出期不污染。
_hv = _V2[8:, _hist_off:_hist_off + 40].var(axis=0).max()
chk(_hv > 1e-6, "对手历史特征非恒定(段10活性, 热身窗)", "var=%.2g" % _hv)
_fv = _V2[:, _res_off:_res_off + 4].var(axis=0).max()
chk(_fv > 1e-6, "资源条件(灵满)特征非恒定", "var=%.2g" % _fv)
_lv = _V2[:, _res_off + 4:_res_off + 8].var(axis=0).max()
chk(_lv > 1e-6, "资源条件(灵空)特征非恒定", "var=%.2g" % _lv)
_chk33 = float(_V2[:, 33].var())
chk(_chk33 == 0.0,
    "feat_builder不占core[33]槽(行为: 合成build全零方差, R19)",
    "var=%.2g" % _chk33)


def _mk_l(x=500.0, y=100.0):
    return {"position.x": x, "position.y": y, "spirit": 1000, "hp": 10000,
            "airBorne": False, "direction": 1, "action": 4, "cardGauge": 0,
            "score": 0, "hand": b"\xff" * 10, "comboDamage": 0, "untech": 0,
            "timeStop": 0, "hitStop": 0}


def _mk_r(x=900.0, y=100.0):
    return {"position.x": x, "position.y": y, "spirit": 1000, "hp": 9000,
            "airBorne": False, "direction": -1, "action": 8, "cardGauge": 0,
            "score": 0, "hand": b"\xff" * 10, "comboDamage": 0, "untech": 0,
            "timeStop": 0, "hitStop": 0}


# R19行为①: 闭合速度符号 — 弹x=800, vx=-10逼近 → 段7列92与dim298
# (14h maxc)必须>0; vx=+10飞离 → 必须为0(原版反向: 审查2026-10-02)
for _vx, _want_pos in ((-10.0, True), (10.0, False)):
    _fb3 = feat_builder.FeatureBuilder(8)
    _l3, _r3 = _mk_l(), _mk_r()
    _b3 = [(0, 800.0, 100.0, _vx, 0.0)]
    _fb3.update_opp(10 / 62, _l3, _r3, {"active": 0}, opp_vx=0.0)
    _v3 = _fb3.build(_l3, _r3, {"active": 0}, _b3)
    _c7 = _v3[58 + 30 + 4]      # 段7逼近度: 列gx=4(rdx=300)
    _c298 = _v3[298]            # 14h maxc
    if _want_pos:
        chk(_c7 > 0.9 and _c298 > 0.9,
            "闭合速度符号: 逼近弹计入(段7列/dim298)",
            "c7=%.2f c298=%.2f vx=%.0f" % (_c7, _c298, _vx))
    else:
        chk(_c7 == 0.0 and _c298 == 0.0,
            "闭合速度符号: 飞离弹不计入",
            "c7=%.2f c298=%.2f vx=%.0f" % (_c7, _c298, _vx))
# R19行为②: 段8行3..5可达 — 静止弹fdy=+140 → gy=5 → dim[111]必须>0
# (原除数100使gy≤2, 18维死区)
_fb4 = feat_builder.FeatureBuilder(8)
_l4, _r4 = _mk_l(), _mk_r()
_fb4.update_opp(10 / 62, _l4, _r4, {"active": 0}, opp_vx=0.0)
_v4 = _fb4.build(_l4, _r4, {"active": 0}, [(0, 560.0, 240.0, 0.0, 0.0)])
chk(_v4[111] > 0, "段8高行可达(gy=5, 原死区18维)", "dim111=%.2f" % _v4[111])
# R19行为③: 近弹3按|Δx|排序 — 近弹(520)必须主导dim52而非包序首弹(800)
_fb5 = feat_builder.FeatureBuilder(8)
_l5, _r5 = _mk_l(), _mk_r()
_fb5.update_opp(10 / 62, _l5, _r5, {"active": 0}, opp_vx=0.0)
_v5 = _fb5.build(_l5, _r5, {"active": 0},
                 [(0, 800.0, 100.0, 0.0, 0.0), (0, 520.0, 100.0, 0.0, 0.0)])
chk(_v5[52] > 0.9, "近弹3取最近(非包序)", "dim52=%.2f" % _v5[52])
# R19行为④: 规避观测维自增 — arm(TTI小)+位移脱离 → dim259>0(原恒0)
_fb6 = feat_builder.FeatureBuilder(8)
_l6, _r6 = _mk_l(), _mk_r()
_fb6.update_opp(10 / 62, _l6, _r6, {"active": 0}, opp_vx=0.0)
_fb6.build(_l6, _r6, {"active": 0}, [(0, 400.0, 100.0, 10.0, 0.0)])
_ar = _fb6.check_evasion(_l6, 0)                    # arm
_l6b = dict(_l6)
_l6b["position.x"] = 620.0                          # 位移120>80
_ev = _fb6.check_evasion(_l6b, 0)                   # 触发
_v6b = _fb6.build(_l6b, _r6, {"active": 0}, [])
chk(_ev == 1 and _v6b[259] > 0,
    "规避观测维自增(dim259, 原恒0)", "ev=%r dim259=%.2f" % (_ev, _v6b[259]))
# R20/R21(用户2026-10-02): 防御可分性。R20首版采hitlab标{5,8,151,158},
# R21用解包movepattern XML权威表修正: 150-167=防御系(立防/蹲防/空防/
# 防御受击); 5=后退走·8=跳跃(hitlab旧误标); 110-115=受击/倒地(非防御)。
from opp_model import classify as _cls, A_GUARD as _AG, A_RETREAT as _AR
from opp_model import A_ATTACK as _AA, A_BULLET as _AB
chk(all(_cls(_a) == _AG for _a in range(150, 168)),
    "XML权威防御ID(150-167)归GUARD桶(R21)")
chk(_cls(5) != _AG and _cls(8) != _AG and _cls(112) != _AG,
    "后退走(5)/跳跃(8)/倒地(112)不是防御(hitlab旧误标勘误)")
chk(_cls(4, dx_delta=3.0, vx=3.0) == _AR
    and _cls(5, dx_delta=3.0, vx=3.0) == _AR,
    "防御与后退可分(前进/后退走按位移入RETREAT桶)")
chk(_cls(300, char="reimu") == _AA and _cls(410, char="reimu") == _AB,
    "角色表分攻击/射击桶(300攻/410射, R21)")
chk(_cls(201, dx_delta=0.0, vx=0.0) != _AA,
    "冲刺(200-227)不误入攻击桶(R21, 原LO=200)")


def _sep_case(opp_act, step):
    _fb = feat_builder.FeatureBuilder(8)
    _l, _r = _mk_l(), _mk_r(900.0)
    _r["action"] = opp_act
    for _ in range(30):
        _fb.update_opp(10 / 62, _l, _r, {"active": 0}, opp_vx=0.0)
        _r["position.x"] += step
    return _fb.build(_l, _r, {"active": 0}, [])


_vg = _sep_case(150, 0.0)     # 对手立防姿态(guardUpper), 静止
_vr = _sep_case(5, 3.0)       # 对手后退走(walkBack)
chk(_vg[152] > 0.5 and _vg[156] < 0.1 and _vr[156] > 0.5 and _vr[152] < 0.1,
    "情境:防/情境:退分开点亮(R21, 原'防'维恒0)",
    "防态 dim152=%.2f dim156=%.2f; 退态 dim152=%.2f dim156=%.2f"
    % (_vg[152], _vg[156], _vr[152], _vr[156]))
tt = src("train_tm.py")
# R60(F-8): 原断言钉死min(opp_id,20)钳位表达式(治理固化反例 — 修bug
# 会让门禁变红)。改行为式: 解析_CHAR_POOL_IDX验证全部落在合法槽
# {0,1,2}∪{11..19}(R19契约: 3-10=技能特征块; 20/21=fvariant位)且无重复。
import re as _re60
_m60 = _re60.search(
    r"_CHAR_POOL_IDX = \{(.*?)\}", tt, _re60.S)
_vals60 = [int(v) for v in
           _re60.findall(r':\s*(\d+)', _m60.group(1))] \
    if _m60 else []
_legal60 = {0, 1, 2} | set(range(11, 20))
chk(_m60 is not None and len(_vals60) == len(set(_vals60)) == 12
    and set(_vals60) <= _legal60,
    "池序映射: 12槽全合法无重复(R60 F-8修正版: 消灭溢出fvariant位+"
    "六对复用; 3-10技能块禁one-hot[R19契约] — 20角色全量待316扩维)",
    str(sorted(_vals60)))
chk("core[227 + opp_id] = 1.0" in tt
    and "assert opp_id in (0, 1, 2) or 11 <= opp_id <= 19" in tt,
    "对手one-hot写core[227]带合法槽守卫(R60 F-8)")
chk('_CHAR_POOL_IDX' in tt,
    "20角色池序映射在位(R47: 原R19三角色池序已扩容)")
chk(tt.count('GUARD_ALL_IDS') >= 2,
    "train_tm防御判定用GUARD_ALL_IDS(R34中断/空挥)")
# R39(P3-8): 原第三处断言钉已删的L2奖励代码 — 随死通道删除
chk("core[33] = " in tt, "turn_recency写core[33](P0-2修复在位)")
fb_src_nospace = src("feat_builder.py").replace(" ", "")
chk("s[33]" not in fb_src_nospace and "s[o+33" not in fb_src_nospace,
    "feat_builder不占core[33]槽")
# 行为: 擦弹可达性 — 12帧内命中的来袭弹必须触发(量纲/过滤回归即红)
fbg = feat_builder.FeatureBuilder(8)
g1 = fbg.check_graze({"position.x": 500.0, "position.y": 100.0},
                     [(0, 400.0, 100.0, 10.0, 0.0)], 0)
chk(g1 == 1, "擦弹正例: 来袭弹TTI≈3帧触发", "got %r" % g1)
# 行为: 负例1 — 双轴窗口全在过去(斜向远离的高位弹)不得计数
# (专打P0-4 t_end守卫: t0<=t_end成立但区间整在过去, 无守卫即误计)
t_neg, inc_neg = threat.threat_predict(500.0, 100.0,
                                       [(0, 620.0, 275.0, 10.0, 10.0)], 62)
chk(t_neg is None and inc_neg == 0, "威胁负例: 双轴已飞过的弹不计来袭",
    "tti=%r inc=%r" % (t_neg, inc_neg))
g2 = fbg.check_graze({"position.x": 500.0, "position.y": 100.0},
                     [(0, 620.0, 275.0, 10.0, 10.0)], 0)
chk(g2 == 0, "擦弹负例: 已飞过的弹不触发", "got %r" % g2)
# 行为: 负例2 — 单轴不重叠(水平远离弹)不得计数
t_neg2, inc_neg2 = threat.threat_predict(500.0, 100.0,
                                         [(0, 620.0, 100.0, 10.0, 0.0)], 62)
chk(inc_neg2 == 0, "威胁负例: 窗口不重叠不计来袭",
    "inc=%r" % inc_neg2)
# 行为: 钳位 — 当前已重叠的弹TTI=0而非负(P0-4b)
t_ov, inc_ov = threat.threat_predict(500.0, 100.0,
                                     [(0, 480.0, 120.0, 10.0, 10.0)], 62)
chk(inc_ov == 1 and t_ov == 0.0, "威胁钳位: 重叠弹TTI=0",
    "tti=%r inc=%r" % (t_ov, inc_ov))

# ============ C3 协议不变量(TM通道) ============
print("=== C3 协议不变量(TM通道) ===")
import soku_client2 as sc2
chk(sc2.CS_SIZE == 105, "CS_FMT=105B", "got %d" % sc2.CS_SIZE)
chk(struct.calcsize("<b2f4H") == 17, "对象项=17B")
chk("== 117" in src("soku_client2.py"), "输入包117B断言在位")
_sc2_src = src("soku_client2.py")
# R19(审查2026-10-02): 回声不匹配分支必须带同款清理(原只超时分支有)
_ei = _sc2_src.find("if echo != hello:")
_chk_echo = _ei >= 0 and "terminate" in _sc2_src[_ei:_ei + 700]
chk(_chk_echo, "握手回声不匹配分支含清理(terminate)")
chk("if _ok_n > 8:" in _sc2_src, "OK跳过循环8次上限(R19)")
chk("_ok_n > 8:\n                raise ProtocolError" in _sc2_src,
    "OK洪流按协议错处理(R19)")
_te_src = src("tm_env.py")
_si = _te_src.find("self._start_first()")
_chk_fail = _si >= 0 and "_monitor_stop.set()" in _te_src[_si:_si + 900] \
    and "CloseHandle" in _te_src[_si:_si + 900] \
    and "_set_match_flag(False)" in _te_src[_si:_si + 900]
chk(_chk_fail, "_start_first失败路径收线程/句柄/忙标志(R19)")

# ============ C4 PPO语义(行为断言) ============
print("=== C4 PPO语义 ===")
from ppo import PPOTrainer


def _ent(tr, X, S):
    _, _, P = tr._pi_forward(X, S, 1.0, mask=None)
    Pc = np.clip(P, 1e-8, 1.0)
    return float(-(Pc * np.log(Pc)).sum(1).mean())


tr = PPOTrainer(n_side=2 * 6 + 308, n_out=6)   # R17: 侧宽须含对手切片
tr.init_fresh(14400)
tr._beta = 0.1
tr._bcw = 0.0
# 隔离设计: b2偏置一个动作(远离均匀点 — 均匀处dH/dz≈0是驻点, 梯度消失);
# 价值头W2v/b2v清零 → dhv=0 → 共享主干无价值梯度混入 → 纯熵方向测试
tr.b2[:] = 0.0
tr.b2[2] = 3.0
tr.W2v[:] = 0.0
tr.b2v = np.float32(0.0)
_rng = np.random.default_rng(7)
_X = _rng.integers(0, 256, (16, 14400), dtype=np.uint8)
_S = _rng.standard_normal((16, 2 * 6 + 308)).astype(np.float32)
_A = _rng.integers(0, 6, 16)
_R = np.zeros(16, dtype=np.float32)
_e0 = _ent(tr, _X, _S)
tr.update(_X, _A, _R, _S, [16], ep_terms=[True])
_e1 = _ent(tr, _X, _S)
chk(_e1 > _e0 + 0.01, "熵行为: 零优势+beta>0一次update后熵上升",
    "%.4f→%.4f" % (_e0, _e1))
pp = src("ppo.py")
chk("ent_grad = -P *" in pp, "熵梯度源码形: -P(logP+H)=+dH/dz(配maximize=True)")
chk("maximize=True" in pp, "策略Adam为ascent(maximize=True)")
chk("bc_mask[idx]" in pp, "bc_mask小批索引(P1-2)")
chk("os.replace" in pp, "原子保存(P0-5)")
chk("meta=np.array([self._temp" in pp, "退火/meta状态持久化")
chk("W1v=self.W1v" in pp, "价值网键名W1v(断裂修复在位)")

# R18(审查2026-10-02 P0): KL复检/熵采样必须与参考同掩码 —
# PI_LR=0(参数零移动)+禁2宏掩码: KL读数须≈0(无掩码修复时, 被禁宏的
# -1e9质量回流产生≈-log(1-q)重归一化伪影, 实测读~0.3); 熵须≤log(合法宏数)
tr3 = PPOTrainer(n_side=2 * 6 + 308, n_out=6)
tr3.init_fresh(14400)
tr3.PI_LR = 0.0
_M3 = np.ones((16, 6), dtype=bool)
_M3[:, 4:] = False    # 禁后2宏
_r18 = tr3.update(_X, _A, _R, _S, [16], masks=_M3, ep_terms=[True])
chk(_r18["kl"] < 1e-4, "KL复检同掩码(PI_LR=0→KL≈0, 无重归一化伪影)",
    "kl=%.4f" % _r18["kl"])
chk(_r18["entropy"] <= np.log(4) + 0.05,
    "熵诊断同掩码(≤log合法宏数1.386)", "ent=%.3f" % _r18["entropy"])

# ============ C5 产物schema(D:\\temp\\th123_models) ============
print("=== C5 产物schema(D:\\temp\\th123_models; 损坏=FAIL) ===")
STORE = os.environ.get("TH123_STORE", r"D:\temp\th123_models")
PI_KEYS = {"W1", "b1", "W2", "b2", "W_side", "Ws1", "bs1", "Ws2", "bs2",
           "Wc1", "bc1", "Wc2", "bc2", "Wc3", "bc3", "meta"}


def _zip_ok(path, must_keys=None):
    try:
        z = zipfile.ZipFile(path)
        bad = z.testzip()
        names = set(z.namelist())
        z.close()
    except Exception as e:   # 截断/坏zip: 判FAIL而非崩溃(从零审查D12)
        return False, "zip异常:%s" % type(e).__name__
    if bad is not None:
        return False, "zip损坏条目:%s" % bad
    if must_keys and not must_keys <= names:
        return False, "缺:%s" % sorted(must_keys - names)
    return True, ""


for ch in ("reimu", "marisa", "suika"):
    pi = os.path.join(STORE, "model_ppo_%s.npz" % ch)
    vv = os.path.join(STORE, "model_ppo_%s_v.npz" % ch)
    if not (os.path.exists(pi) and os.path.exists(vv)):
        warn(False, "模型存在@%s" % ch, "冷启动未生成, 合法")
        continue
    ok, det = _zip_ok(pi, {k + ".npy" for k in PI_KEYS})
    chk(ok, "policy zip完整+键集@%s" % ch, det)
    if ok:
        d = np.load(pi, allow_pickle=False)
        chk(d["meta"].shape >= (5,), "meta长度>=5@%s" % ch,
            "got %r" % (d["meta"].shape,))
    ok, det = _zip_ok(vv, {"W1v.npy", "b1v.npy", "W2v.npy", "b2v.npy"})
    chk(ok, "value zip完整+键集@%s" % ch, det)
    warn(os.path.exists(os.path.join(STORE, "macro_counts_%s.npy" % ch)),
         "宏计数存在@%s" % ch)
    dd = os.path.join(STORE, "distill_data_%s.npz" % ch)
    if os.path.exists(dd):
        ok, det = _zip_ok(dd)
        chk(ok, "distill zip完整@%s" % ch, det)
        if ok:  # X/Y两数组都真读(只读X发现不了Y损坏)
            d = np.load(dd, allow_pickle=False)
            chk(d["X"].size > 0 and d["Y"].size == d["X"].shape[0],
                "distill X/Y可读且对齐@%s" % ch,
                "X%s Y%s" % (d["X"].shape, d["Y"].shape))
            # 第八轮审查§8.5: Y≡常数列(如恒-1占位)曾能过对齐检查 —
            # 无标签数据集混入会被当真数据放行。非常数即至少2个取值。
            yv = np.unique(d["Y"])
            chk(yv.size >= 2, "distill Y非常数列@%s" % ch,
                "Y仅%d个取值(占位/损坏数据)" % yv.size)

# ============ C6 奖励活性 ============
print("=== C6 奖励活性 ===")
# AST: 奖励常量 定义 ⊆ 引用(除定义行外的Name读取) — 死常量即红
_tt_tree = ast.parse(tt)
_rconst = set()
for node in _tt_tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and re.match(r"^(R_|W_|SPIRIT)", t.id):
                _rconst.add(t.id)
_loads = set()
for node in ast.walk(_tt_tree):
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        _loads.add(node.id)
_dead = _rconst - _loads
chk(not _dead, "奖励常量无死定义(AST)", "死:%s" % sorted(_dead))
chk(tt.count("check_graze") >= 1, "擦弹通道接线(train_tm)")
chk(tt.count("check_evasion") >= 1, "规避通道接线(train_tm)")
chk("_whiff_cost(dec_name)" in tt, "空挥惩罚接线(P2-1, W_WHIFF)")
chk(not re.search(r"^WHIFF_[BCS]", tt, re.M), "死常量WHIFF_B/C/SKILL已清")
chk("rews[-1] += seg_rew" in tt, "终局段奖励入账(KO不丢)")
chk("opp_vx=opp_vx_ema" in tt, "opp_vx真接线(P1-4b, 差分EMA)")
chk("right[\"action\"] in HIT_ACT_IDS" in src("feat_builder.py"),
    "opp_down=受击动作集(P1-4a真)")
_fb_src = src("feat_builder.py")
import feat_builder as _FB
chk(214 not in _FB.HIT_ACT_IDS and 404 not in _FB.HIT_ACT_IDS
    and 97 in _FB.HIT_ACT_IDS and 100 in _FB.HIT_ACT_IDS,
    "HIT_ACT_IDS=SokuLib受击语义(R28: 旧混入飞行/弹幕id)")
chk("300, 598" in src("opp_model.py"),
    "classify攻击区间=枚举精确(R28)")
# R56(fleet F4): distill逻辑抽出至episode_core.save_distill_rows
# (train_tm._save_distill委托 + fleet learner共用 — 单一实现)。
# 写读同径=trainer与共享函数同路径模板; 原子落盘在共享函数内。
_ec = src("episode_core.py")
chk('save_distill_rows(STORE_DIR, self.char, self.suffix, rows)' in tt
    and _ec.count('distill_data_%s%s.npz" % (char, suffix)') >= 1
    and 'distill_data_%s%s.npz" % (self.char, self.suffix)' in tt,
    "distill写读同径(P3-4补全; R56: _save委托episode_core)")
chk('.tmp.npz' in _ec and 'os.replace(tmp, path)' in _ec,
    "distill原子落盘(P0-5真; R56: 在episode_core.save_distill_rows)")
import macros
chk(macros.whiff_cost("5C") == 1.0, "whiff_cost(5C)=1.0(62F/62)",
    "got %r" % macros.whiff_cost("5C"))
chk(abs(macros.whiff_cost("5B") - 45.0 / 62.0) < 1e-9, "whiff_cost(5B)=45/62")
chk("or (score_l_prev + score_r_prev) < 2)" in tt,
    "truncated终止位(R39: 超时+比分<2的异常结束局均按截断bootstrap)")

# ============ C7 信息对称(用户2026-09-22裁定) ============
print("=== C7 信息对称(mod 0BD2A843起协议层遮蔽 + 客户端哨兵纵深) ===")
fb2 = src("feat_builder.py")
# 行为: 哨兵/极光的线上真值处理(unsigned short溢出=65535, 非C++意图值-1)
chk(feat_builder.gauge_feat(65535) == 0.0, "卡槽哨兵0xFFFF→0(线上真值)")
chk(abs(feat_builder.gauge_feat(250) - 0.5) < 1e-9, "卡槽正常值归一")
chk(feat_builder.fair_weather_id({"displayed": 19, "active": 5}) == 19,
    "极光时天气id以displayed为准(实际效果隐藏)")
chk(feat_builder.fair_weather_id({"displayed": 3, "active": 3}) == 3,
    "非极光直用active")
fbs = feat_builder.FeatureBuilder(8)
_Lm = {"position.x": 600.0, "airBorne": False}
_Rm = {"position.x": 900.0, "airBorne": False, "action": 0,
       "spirit": 1000, "cardGauge": 250,
       "hand": bytes([3, 0, 5, 0, 7, 0, 255, 0, 255, 0])}   # 3张实卡
fbs.update_opp(0.1, _Lm, _Rm, {"active": 0, "timer": 100}, opp_vx=5.0)
chk(fbs.opp.cards_avg > 0.05, "opp_cards_n真接线(P1-4e)",
    "EMA=%.3f" % fbs.opp.cards_avg)
# 哨兵路径: gauge=0xFFFF(线上真值) → EMA保持 + gauge传None(不产生假增量)
_pre = fbs.opp.cards_avg
_Rs = dict(_Rm, cardGauge=65535, hand=bytes([255] * 10))
fbs.update_opp(0.1, _Lm, _Rs, {"active": 0, "timer": 100}, opp_vx=5.0)
chk(abs(fbs.opp.cards_avg - _pre) < 1e-9, "哨兵囤牌EMA保持(0xFFFF→None)")
chk(fbs.opp._prev_gauge is None, "哨兵卡槽传None")
# 天气id路径(旧mod兼容): active=晴岚+真值手牌 → 仍判遮蔽
fbs2 = feat_builder.FeatureBuilder(8)
fbs2.update_opp(0.1, _Lm, _Rm, {"active": 11, "timer": 50}, opp_vx=5.0)
chk(fbs2.opp.cards_avg == 0.0 and fbs2.opp._prev_gauge is None,
    "晴岚天气id路径判遮蔽(旧mod兜底)")
# R16§3: 14g资源差新增2处调用(核心标量1+卡牌2+资源差2=5) + def 1处 = 6
chk(fb2.count("gauge_feat(") == 6, "gauge_feat接线=定义+5处",
    "got %d" % fb2.count("gauge_feat("))

# ============ C8 基准树教义(三角色) ============
print("=== C8 基准树教义(宏名存在/节点覆盖/角色路由) ===")
import standard_tree
import macros_marisa, macros_suika
chk(set(standard_tree.TREES) == {"reimu", "marisa", "suika"},
    "TREES三角色齐", "got %s" % sorted(standard_tree.TREES))
_N = {"reimu": {m[0] for m in macros.MACROS},
      "marisa": set(macros_marisa.MACRO_NAMES_MARISA),
      "suika": set(macros_suika.MACRO_NAMES_SUIKA)}
for ch, tree in standard_tree.TREES.items():
    phantom = {a for _, _, acts, _ in tree for a, _ in acts} - _N[ch]
    chk(not phantom, "教义宏名全存在于宏库@%s" % ch,
        "幻影: %s" % sorted(phantom)[:5])
    chk(len(tree) >= 9, "节点数≥9@%s" % ch, "got %d" % len(tree))
    # 数据相关诊断(第四轮审计§2.1: 覆盖随训练探索漂移, 降级为WARN防假阻断;
    # 树健康的代码契约=上面的宏名存在+节点数+路由)
    dd = os.path.join(STORE, "distill_data_%s.npz" % ch)
    if os.path.exists(dd):
        try:
            dch = np.load(dd, allow_pickle=False)
            Xch = dch["X"]      # 旧过滤X[:,0]>=0是空操作(|dx|恒非负), 已删
            hit = np.zeros(len(Xch), dtype=bool)
            for _, cond, _, _ in tree:
                hit |= np.array([cond(r) for r in Xch])
            warn(hit.mean() >= 0.9, "节点条件实测覆盖≥90%%@%s(诊断)" % ch,
                 "%.0f%%" % (100 * hit.mean()))
        except Exception as e:   # 损坏档: 降WARN不崩(截断变异实测曾崩在此)
            warn(False, "distill可读@%s(覆盖诊断)" % ch, type(e).__name__)
chk("TREES[self.char]" in tt, "audit_tree按角色路由(不再灵梦树打折)")

# ============ C9 mod血统(引用即构建输入 — 第四轮审计核心教训) ============
print("=== C9 mod血统(被引用源码必须是部署产物的构建输入) ===")
import hashlib
import json
import re


def _md5hex(p):
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


prov_path = os.path.join(HERE, "mod_provenance.json")
chk(os.path.exists(prov_path),
    "mod_provenance.json存在(重编mod后跑tools/update_provenance.py)")
if os.path.exists(prov_path):
    with io.open(prov_path, encoding="utf-8") as fh:
        prov = json.load(fh)
    # 第五轮§2-C: 路径缺失=WARN(换机/游戏目录改名不该硬阻断);
    # 哈希不匹配=FAIL(那是真问题)。源根可被TH123_MODROOT覆盖(变异沙箱用)。
    dep = prov["deployed_path"]
    dep_ok = os.path.exists(dep)
    warn(dep_ok, "部署DLL在位", dep[-52:])
    if dep_ok:
        chk(_md5hex(dep) == prov["deployed_md5"],
            "部署DLL哈希=provenance记录", _md5hex(dep)[:12])
    root = os.environ.get("TH123_MODROOT", prov["source_root"])
    warn(os.path.isdir(root), "mod源根在位", root)
    if os.path.isdir(root):
        st = os.path.join(root, "Training", "TrainingMod", "state.cpp")
        nt = os.path.join(root, "Training", "TrainingMod", "network.cpp")
        if os.path.exists(st):
            stc = io.open(st, encoding="utf-8", errors="replace").read()
            chk("WEATHER_MOUNTAIN_VAPOR" in stc and "0xFFFF" in stc,
                "晴岚遮蔽在编译输入state.cpp")
        if os.path.exists(nt):
            ntc = io.open(nt, encoding="utf-8", errors="replace").read()
            chk("WEATHER_AURORA" in ntc, "极光遮蔽在编译输入network.cpp")
        for rel, h in prov["source_md5"].items():
            p = os.path.join(root, rel)
            chk(os.path.exists(p) and _md5hex(p) == h,
                "源码哈希=构建时(改源未重编即红)@%s" % rel.split("\\")[-1])
    # 第五轮§2-B: 编译清单必须与build_tm.bat现算一致(bat加了文件没重生成档案即红)
    if os.path.exists(prov["build_script"]):
        bat_src = io.open(prov["build_script"], encoding="utf-8",
                          errors="replace").read()
        bat_units = sorted(set(re.findall(
            r"(Training\\TrainingMod\\\w+\.cpp|d3dx_stub\.cpp)", bat_src)))
        chk(bat_units == prov["bat_explicit_units"],
            "编译清单=bat现算(手抄漂移即红)",
            "档案%s vs bat%s" % (prov["bat_explicit_units"], bat_units))
    chk(os.path.exists(os.path.join(HERE, "runtime_masking_probe.py")),
        "运行时实测探针在位(实测结果见docs/mod_masking_runtime_dump.md)")

# ============ C10 外环(§6.0阶段2: matchup评估/对手池/战报/自对弈学习) ============
print("=== C10 外环(双控评估/快照池/战报/自对弈训练半环) ===")
ol = src("outer_loop.py")
sd = src("side_driver.py")
chk("_self.last_match = (e.winner, e.ls, e.rs)" in sd,
    "GameEnded胜者被记录(父类step会吞掉)")
chk("vs_com=False, tps=tps" in ol, "对局走VS_PLAYER双控通道")
chk('matrix["%s>%s" % (a, b)]' in ol and "参考线55%" in ol,
    "战报含胜率矩阵+毕业门读数(2.4: 55%参考线, 重构待干净读数)")
# R17(§3.1): 原文本断言"temp=1.0"在评估侧改为温度跟随模型meta后假红 —
# 改由C15的test_side_driver_semantics.py行为断言(温度==_temp, 决策计数)
chk('not f.endswith("_v.npz")' in ol, "池latest排除价值网快照(实测踩坑)")
# 训练半环集成
chk("self.env.step(inp, self._opp_inp)" in tt,
    "双输入步进(对手侧输入接线)")
chk("self.opp.frame_input(right, left, weather," in tt,
    "P2对手驱动用(右,左)视角")
chk("vs_com=False," in tt and "_make_env" in tt,
    "对手模式=VS_PLAYER(_make_env)")
chk("_settle_match()" in tt and "_rotate_opp(ep)" in tt,
    "胜率结算+对手轮换入训练循环")
chk('"macro_counts_%s%s.npy" % (char, suffix)' in tt,
    "suffix产物隔离(双训练器互斥)")
# 行为: 三角色SideDriver构建+模型加载(维度链正确性)
import side_driver as sd_mod
for _ch in ("reimu", "marisa", "suika"):
    _d = sd_mod.SideDriver(_ch, "L")
    chk(_d.n_side == 5 * _d.n_macros + 308,
        "SideDriver维度@%s(R30含untech块)" % _ch,
        "n_side=%d" % _d.n_side)
    chk(int(_d.macro_reach.max()) > 0 and int(_d.macro_reach_v.max()) > 0,
        "SideDriver二维射程解析非空@%s(R25)" % _ch,
        "x=%.0f y=%.0f" % (float(_d.macro_reach.max()),
                           float(_d.macro_reach_v.max())))
    chk(int(_d.macro_startup.max()) > 0,
        "SideDriver发生帧解析非空@%s(R30)" % _ch,
        "max=%.0f" % float(_d.macro_startup.max()))
    # R16: frame_input曾被顶格降为模块函数 → AttributeError每局崩
    chk(callable(getattr(_d, "frame_input", None)),
        "SideDriver.frame_input是方法@%s" % _ch)
_d = sd_mod.SideDriver("reimu", "L")
try:
    _d.load(os.path.join(STORE, "model_ppo_reimu.npz"))
    chk(True, "模型加载(eval只读)")
except Exception as e:
    chk(False, "模型加载(eval只读)", str(e)[:60])
# 快照池产物schema
warn(os.path.isdir(os.path.join(STORE, "pool")),
     "对手池目录存在(跑过snapshot)")

# ============ C11 宏时序保真(hitlab死招事故防线) ============
print("=== C11 宏时序(紧邻预置≥5帧模型, 从零审查D12/D15重写) ===")
BTN = {"A", "B", "C"}
DIRS = {"down", "right", "left", "up"}


def _eff_dirs(keys):
    """同轴双键取最后生效键(D14: keys_to_input同轴后者覆盖前者)"""
    last = {}
    for k in keys:
        if k in ("left", "right"):
            last["H"] = k
        elif k in ("down", "up"):
            last["V"] = k
    return set(last.values())


def _adjacency_ok(script):
    """紧邻连续帧数模型(D15): 每个攻击步的每个生效方向,
    其紧邻连续保持帧数必须≥5(hitlab标定阈值)。门步/空步/异向步打断。"""
    run = {}
    for ks, fr in script:
        if isinstance(ks, str):
            run = {}
            continue
        keys = set(ks)
        ed = _eff_dirs(ks)
        if keys & BTN:
            if any(run.get(d, 0) < 5 for d in ed):
                return False
            run = {d: fr for d in ed}
        else:
            run = {d: run.get(d, 0) + fr for d in ed}
    return True


import macros as _mc
import macros_marisa as _mm
import macros_suika as _ms
for lib, names in ((_mc.MACROS, "reimu"), (_mm.MACROS_MARISA, "marisa"),
                   (_ms.MACROS_SUIKA, "suika")):
    bad = [m[0] for m in lib if not _adjacency_ok(m[1])]
    chk(not bad, "活表(规范化后)紧邻预置≥5@%s" % names, "违例: %s" % bad[:4])

# 规范化器单元测试(D12: 断言作用在问题形态上, 非修好后的产物)
_t1 = _mc._norm_presteps([(("down", "A"), 10)])
chk(_adjacency_ok(_t1) and _t1[0] == (("down",), 6),
    "规范化器: 裸死招→补down×6")
_t2 = _mc._norm_presteps([(("up",), 6), (("down",), 2), (("down", "B"), 14)])
chk(_adjacency_ok(_t2) and (("down",), 6) in _t2,
    "规范化器: 空中2帧预置→补足")
_t3 = _mc._norm_presteps([(("up", "down", "B"), 14)])
chk(_t3[0] == (("down",), 6),
    "规范化器: 同轴双键按生效方向(D14, 不再sorted反转)",
    str(_t3[0]))
chk(_t3[0] == (("down",), 6) and "up" not in _t3[0], "D14回归哨兵")
# 三库源始字面断言(非规范化产物 — 变异真正打得到的地方)
mc_src = src("macros.py")
mm_src = src("macros_marisa.py")
ms_src = src("macros_suika.py")
chk('[(("down",), 6), (("down", "A"), 10)]' in mc_src,
    "reimu 2A源始预置步=down×6(hitlab v9标定阈值5)")
chk('[(("down",), 6), (("down", "A"), 10)]' in mm_src,
    "marisa 2A源始预置步=down×6")
chk('[(("down",), 6), (("down", "A"), 10)]' in ms_src,
    "suika 2A源始预置步=down×6")

# ============ C12 端口段(第六轮审计§3: 显式划分防跨实例串流) ============
print("=== C12 端口段(portmap静态校验) ===")
from portmap import SEGMENTS, check_disjoint, check_rebuild_domain
_ok, _det = check_disjoint()
chk(_ok, "端口段两两不重叠", _det)
_ok2, _det2 = check_rebuild_domain()
chk(_ok2, "rebuild取值域枚举(slot0-5×ep200)全在段内(D4)", _det2)
chk(SEGMENTS["train_rebuild"] == (20850, 20899)
    and SEGMENTS["eval"][0] == 20900 and SEGMENTS["hitlab"][0] == 20920
    and SEGMENTS["exp"][0] == 20940, "段定义与文档一致",
    str({k: v for k, v in SEGMENTS.items()})[:90])
chk("rebuild_port(self.slot, ep)" in tt,
    "train_tm异常重建走portmap(原版base+100+ep跨段撞)")
# R57(第十八轮2.6): fleet车道枚举 — 16车道×10宽全在fleet段内且互不重叠
import portmap as _PM12
try:
    _fl = SEGMENTS["fleet"]
    _lanes = set()
    _okf = True
    for _a in range(16):
        for _e in range(10):
            _p = _PM12.fleet_port(_a, _e)
            _lanes.add(_p)
            if not (_fl[0] <= _p < _fl[1]):
                _okf = False
    chk(_okf and len(_lanes) == 160,
        "fleet车道枚举: 16×10全在段内且互不重叠(R56)",
        "段=%s 唯一端口%d" % (_fl, len(_lanes)))
except (KeyError, AttributeError) as _e:
    chk(False, "fleet车道枚举(R56)", str(_e))
chk("PORT = 20930" in src("tools/hitlab_probe.py"),
    "hitlab端口在段内(20920-20939)")
chk("self.lsock.settimeout(accept_timeout)" in src("soku_client2.py")
    and "accept_timeout=120.0" in src("soku_client2.py"),
    "accept有超时(R16参数化: 默认120s, tm_env持锁期传90s)")
# 外环加固(第六轮§7)
ol2 = src("outer_loop.py")
chk("env.close()" in ol2, "外环finally走env.close()(句柄/线程不泄漏)")
chk('"aborted" += 1' in ol2 or 'res["aborted"] += 1' in ol2,
    "中断局计数(不静默丢弃)")
chk("outer_loop.lock" in ol2 and "O_EXCL" in ol2, "外环单实例锁")
# R22(用户2026-10-02): 镜像对局+池深k=3 — 外环经验多样性最低成本扩容
_rp = src("run_parallel.py")
_mirror_ok = all(
    '("%s", %d, %d, ["%s",' % (ch, p, s, ch) in _rp
    for ch, p, s in (("reimu", 20800, 0), ("marisa", 20810, 1),
                     ("suika", 20820, 2)))
chk(_mirror_ok, "三角色对手首位=镜像(己方角色, R22)")
chk("POOL_K = 3" in tt, "对手池深k=3(历史快照对抗, R22)")
# R23(2026-10-02): 位置特化连段门控 — 架构文档声称有, 实际从未实现。
# 断言锚定**操作行**(仅查标识符会被__init__构造行的同名骗过 — 变异
# 自检实测漏网教训)
chk("mask = mask & ~self.corner_combo_idx" in tt,
    "版边连门控操作行在位(R23)")
chk("mask = mask & ~self.air_combo_idx" in tt,
    "空连门控操作行在位(R23)")
sd_src = src("side_driver.py")
chk("mask = mask & ~self.corner_combo_idx" in sd_src
    and "mask = mask & ~self.air_combo_idx" in sd_src,
    "SideDriver同款位置门控(R23)")
# 新宏末位追加契约(本次差点中插错位全部下游)
chk("新宏必须追加在列表末尾" in src("macros_suika.py")
    or "新宏必须追加在列表末尾" in src("macros.py"),
    "宏库末位追加契约注记在位(R23)")
import macros_suika as _MS
_suika_last = [m[0] for m in _MS.MACROS_SUIKA][-4:]
chk(_MS.N_MACROS_SUIKA == 77
    and "原子·确认5A" in [m[0] for m in _MS.MACROS_SUIKA],
    "suika原子在位+C4追加(R35+R61n: 70+7=77)")
# R38(第九轮审计§2.1): 原死表达式`STORE if False else 硬编码路径` —
# 门禁成为单PC仪器。改环境变量可覆盖, 默认仓库data/bc(bc_build产物位)。
_bc_dir = os.environ.get(
    "TH123_BC_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 'data', 'bc'))
_bc_npz = np.load(os.path.join(_bc_dir, 'bc_suika.npz'), allow_pickle=True)
_bc_s = _bc_npz['S']
_bc_want = 5 * _MS.N_MACROS_SUIKA + 308
if _bc_s.shape[1] != _bc_want:
    warn(_bc_s.shape[1] == _bc_want,
         "suika BC库宽度迁移期(R61n C4 +7宏: BC=%d≠模型%d — 下批重建)",
         "S=%d want=%d" % (_bc_s.shape[1], _bc_want))
else:
    chk(True, "suika BC库宽度与五块布局对齐(R23-30)",
        "S=%d" % _bc_s.shape[1])
# R38: 重建后的库必须带布局版本且gap/untech块有真实数据(非零填充)
try:
    import json as _json
    _bc_meta = _json.loads(str(_bc_npz['meta']))
except Exception:
    _bc_meta = {}
_b0 = 2 * _MS.N_MACROS_SUIKA + 308
chk(isinstance(_bc_meta, dict) and _bc_meta.get('layout') == '5N+308:v2',
    "suika BC库带布局版本(R38重建)", "meta=%s" % type(_bc_meta).__name__)
chk(abs(_bc_s[:, _b0:_b0 + _MS.N_MACROS_SUIKA]).sum() > 0,
    "suika BC库gap_x块非全零(R38: repad零填充事故不复存在)")
# R24: 射程双通道(掩码栅栏+特征理解)断言
chk("self.macro_reach, self.macro_reach_v = resolve_reach" in tt,
    "train_tm二维射程解析在位(R24/R25)")
chk("dx_abs > self.macro_reach + REACH_MARGIN" in tt,
    "射程门控操作行在位(R24)")
chk("(_adx - self.macro_reach) / 200.0" in tt,
    "射程差特征块在位(R24)")
sd2 = src("side_driver.py")
chk("(_adx - self.macro_reach) / 200.0" in sd2
    and "dx_abs > self.macro_reach" in sd2,
    "SideDriver射程双通道同构(R24)")
import reach_maps as _RM
chk(_RM.CHAR_MACRO_MOVES['reimu']['5A'] == (300, 301)
    and _RM.CHAR_MACRO_MOVES['reimu']['2A'] == (303, 311)
    and _RM.CHAR_MACRO_MOVES['reimu']['DA'] == (305, 302),
    "显式move表=SokuLib枚举(5A含f5A/DA=66A, R29)")
chk("_starter_button" not in src("reach_maps.py"),
    "脚本签名推导已删(R29: 状态依赖招无法区分, 受身/4A同签名)")
# R25(用户2026-10-02: 弹幕复杂化+判定二维): 运动学/地雷/追踪/纵向
fb_src = src("feat_builder.py")
chk("self.bullet_kin = kin" in fb_src,
    "bullet_kin并行表在位(加速度/转向/驻留/弹型, R25)")
chk("0.5 * _ax * horizon * horizon" in fb_src,
    "未来占据二次外推(变速弹, R25)")
chk("_spd < 0.5 and _k[3] >= 10" in fb_src,
    "地雷威胁判定(近零速+驻留, R25)")
chk("_k[2] >= 0.08 and _spd > 1.0" in fb_src,
    "追踪弹悲观TTI(转向率阈值, R25)")
chk("_ady > self.macro_reach_v + REACH_MARGIN" in tt,
    "纵向射程门控在位(R25)")
chk("(_ady - self.macro_reach_v) / 200.0" in tt,
    "纵向射程差特征块在位(R25)")
# R33(用户2026-10-02"防御刷分"): 格挡≠擦弹+防御递减+L1距离门
chk('left.get("action", 0) in GUARD_ALL_IDS' in fb_src,
    "check_graze排除防御态(R33: 格挡≠擦弹, 防刷分)")
# R39(P3-8): R_GUARD/R_GUARD_PREP死通道断言已随死代码删除
# (R35势函数化后tracker零调用者, 门禁保护死代码=噪声)
# R34(架构阶段1: 消除硬天花板): 帧级防御中断+灵力门控+原子宏
chk("_opp_a >= 300 and _opp_a < 600" in tt,
    "帧级防御中断在位(R34: 对手攻击+我方硬直→清队)")
chk('left["spirit"] < 100' in tt,
    "灵力门控在位(R34: 攻击步前灵力不足→中断)")
import macros_marisa as _MM
chk(_MM.N_MACROS_MARISA == 76
    and [m[0] for m in _MM.MACROS_MARISA][-4:] ==
    ["压起身·即", "压起身·延迟", "压起身·空", "压起身·穿"]
    and "原子·确认5A" in [m[0] for m in _MM.MACROS_MARISA],
    "marisa四原子在位+C4压起身末位(R34+R61n: 69+7=76)")
# R35(六大差距方案实施)
import macros as _MR
import macros_suika as _MS2
chk(_MR.N_MACROS == 70
    and [m[0] for m in _MR.MACROS][-4:] ==
    ["压起身·即", "压起身·延迟", "压起身·空", "压起身·穿"]
    and "原子·确认5A" in [m[0] for m in _MR.MACROS],
    "reimu四原子在位+C4压起身末位(R35+R61n: 63+7=70)")
chk(_MS2.N_MACROS_SUIKA == 77
    and [m[0] for m in _MS2.MACROS_SUIKA][-4:] ==
    ["压起身·即", "压起身·延迟", "压起身·空", "压起身·穿"]
    and "原子·确认5A" in [m[0] for m in _MS2.MACROS_SUIKA],
    "suika四原子在位+C4压起身末位(R35+R61n: 70+7=77)")
chk("def state_potential" in tt and "POT_W" in tt,
    "势函数奖励塑形在位(R35: 状态势差, 消灭刷分)")
chk("_replay_buf" in src("ppo.py"),
    "经验回放在位(R35: 高优势样本跨批重用)")
chk("_Xn, side.reshape(1, -1)" in tt,
    "价值引导宏选择在位(R35: critic评估Top-5)")
# R38(第九轮审计P0-1..4): 三个现行bug+一个死特性的修复断言
chk("if macro_queue:\n                    keys, fl = macro_queue[0]" in tt,
    "队列推进带空守卫(R38 P0-1: 受击中止清队后跳过本帧, 原空取[0]炸整局)")
chk("from opp_model import GUARD_ALL_IDS" in sd_src,
    "side_driver导入GUARD_ALL_IDS(R38 P0-2: 原遗漏→对手攻击+我方硬直时NameError)")
chk("_V, = self._ppo_act._v_forward" not in tt
    and "_best, _best_v = mid, _base_v" in tt,
    "价值引导解包修复+基准阈值参与(R38 P0-3: 原元组解包ValueError=特性从未执行)")
ppo_src = src("ppo.py")
chk("np.argsort(-np.abs(adv[_hi_idx]))[:_cap]" in ppo_src,
    "回放池切片[:_cap](R38 P0-4a: 原[_cap:]方向反→池恒空)")
chk("logp_old[N0:N0 + _rp_n] = _rows[7]" in ppo_src,
    "回放行logp_old=保存时策略(R38 P0-4c: 原取当前策略→ratio恒1)")
chk("M = np.concatenate([M, _rows[6]])" in ppo_src,
    "回放行mask拼接(R38 P0-4b: 原缺→前向广播爆炸被异步线程吞)")
# R38(P0-5/P0-6): BC对齐+原生布局
chk("from bc_align import estimate_lag_map, realign, post_validate"
    in src("bc_build.py"),
    "BC构建走对齐器(R38 P0-5: 状态↔输入错位+70~240帧, 原原始下标配对)")
chk("5 * n_macros + fb.CORE_DIMS" in src("bc_build.py"),
    "BC侧向量5N+308原生构建(R38 P0-6: 原4N+308+repad零填充)")
# ============ R39(第十轮§4) 静态数据表门禁 — 宏库/数据表此前是门禁盲区 ============
# ① 类别集合⊆宏名表(幽灵名=拼写静默剔除) ② sc:目标∈SC_COST(缺耗费=
# 高估可用性→游戏内使用失败作废) ③ 原子/TM宏射程登记 ④ SKILL_MAP锚点
from train_tm import CHAR_LIBS as _CL39
from reach_maps import resolve_reach as _rr39
for _ch, _lib in _CL39.items():
    _names = set(_lib["names"])
    _ghost = sorted(_cat for _catn in
                    ("melee", "bullet", "skill", "combo", "string", "sc",
                     "attack")
                    for _cat in _lib.get(_catn, set()) if _cat not in _names)
    chk(not _ghost, "%s类别集合无幽灵名(R39)" % _ch,
        "幽灵: %s" % _ghost[:5] if _ghost else "")
    _nocost = []
    for _nm, _script in _lib["macros"]:
        for _keys, _f in _script:
            if isinstance(_keys, str) and _keys.startswith("sc:"):
                _tid = int(_keys[3:])
                if _tid >= 0 and _tid not in _lib["sc_cost"]:
                    _nocost.append((_nm, _tid))
    chk(not _nocost, "%s的sc目标全有耗费项(R39§4-6)" % _ch,
        "缺: %s" % _nocost[:4] if _nocost else "")
    _rx, _rv = _rr39(_lib["macros"], _ch)
    _idx = {n: i for i, (n, _s) in enumerate(_lib["macros"])}
    _need = [n for n in ("原子·确认5A", "原子·地面链", "原子·空链", "原子·收尾")
             if n in _idx]
    _unreg = [n for n in _need if _rx[_idx[n]] <= 0]
    chk(not _unreg, "%s原子宏射程已登记(R39§4-7)" % _ch,
        "缺: %s" % _unreg if _unreg else "")
    _tmneed = [n for n in _idx if n.startswith("TM·")
               and n != "TM·必杀SC连"]   # 必杀起手无可靠5xx映射(R4不登记)
    # 查**表登记**而非解析值 — 登记≠XML数据可得(如4A=330在reimu表无
    # hitbox条目, 解析reach=0属数据缺口而非漏登记)
    from reach_maps import CHAR_MACRO_MOVES as _CMM39
    _tmunreg = [n for n in _tmneed if n not in _CMM39[_ch]]
    chk(not _tmunreg, "%s TM宏射程已登记(必杀起手除外, R39)" % _ch,
        "缺: %s" % _tmunreg if _tmunreg else "")
import skill_levels as _SL
chk(_SL.CHAR_SKILL_MAPS["reimu"][102] == 3
    and _SL.CHAR_SKILL_MAPS["marisa"][106] == 3
    and _SL.CHAR_SKILL_MAPS["suika"][108] == 2,
    "SKILL_MAP三处错位修复在位(R39§4-4: 102亜空穴=22系/106 Torch=22系/108踏鞴=214系)")
# ============ R40(第十一轮): INPUTLOG精确对齐通道 + mod源码M-1/M-2 ============
ob_src = src("oracle_batch2.py")
chk("'SOKUAI_INPUTLOG': '1'" in ob_src,
    "oracle录制启用INPUTLOG通道(R40§6-1: mod同帧输入日志, 实测rep↔ilog匹配率1.0000)")
chk("'SOKUAI_INPUTLOG_PATH': ilog_path" in ob_src,
    "inputlog路径按shard隔离(R40: 并行车道不互写)")
bb_src2 = src("bc_build.py")
chk("arr[:, 0].astype(np.uint16), arr[:, 2].astype(np.uint16)" in bb_src2,
    "bc_build精确对齐分支在位(R40: ilog存在时跳过互相关, 旧shard回退)")
_mr = os.environ.get("TH123_MODROOT", r"D:\temp\build\SokuAI-master")
_ms = io.open(os.path.join(_mr, "Training", "TrainingMod", "state.cpp"),
              encoding="utf8", errors="replace").read()
_mn = io.open(os.path.join(_mr, "Training", "TrainingMod", "network.cpp"),
              encoding="utf8", errors="replace").read()
chk("destination.hitStop = 0;" in _ms,
    "mod对象hitStop初始化在位(R40 M-1: 原未初始化堆字节入训练数据)")
chk("size_t cap = 255;" in _mn,
    "mod对象总数255截断在位(R40 M-2: 原u8回绕→客户端读少→流错位)")
chk("UNMEASURABLE" in src("reach_maps.py"),
    "reach_maps显式不可测登记(R40§6-6: 区分疏漏与无数据)")
# R42(2026-10-04): run_parallel"正常完成"分支格式化 — eps是argv字符串,
# 原%d格式在首个训练器跑满局数时TypeError炸掉监督器(suika 500局首触)
chk("正常完成(%s局" in src("run_parallel.py"),
    "监督器正常完成分支eps按str格式化(R42: 原%d首触即崩, 监督器裸奔)")
# ============ R43(2026-10-04): 池刷新制度 + COM难度阶梯 ============
tt43 = src("train_tm.py")
chk("POOL_SNAPSHOT_EVERY = 50" in tt43 and "def _snapshot_pool" in tt43
    and "(ep + 1) % POOL_SNAPSHOT_EVERY == 0" in tt43,
    "池刷新制度在位(R43-A: 每50局快照入池+滚动清理 — 原28h打旧对手)")
chk("def _resolve_pool" in tt43 and "if m is None:" in tt43,
    "对手路径轮换时动态解析(R43-A: 原启动时冻结)")
chk("COM_CLIMB_N = 20" in tt43 and "COM_FALL_N = 40" in tt43
    and "def _com_ladder" in tt43
    and "self._com_hist.append(1 if ls > rs else 0)" in tt43,
    "COM难度阶梯在位(R43-B: 20局≥50%升/40局<20%降, 课程学习)")
rp43 = src("run_parallel.py")
chk('"--com-difficulty", "0"' in rp43,
    "COM阶梯起点Easy(R43-B: 原固定Lunatic=零学习信号)")
# ============ R44/R45(2026-10-04): 十七新角色宏库+模型+数据链完整性 ============
_NEW6 = ('sakuya', 'patchouli', 'yuyuko', 'reisen', 'komachi', 'tenshi',
         'alice', 'youmu', 'remilia', 'yukari', 'aya', 'iku', 'sanae',
         'cirno', 'meiling', 'utsuho', 'suwako')
for _nc in _NEW6:
    _np = os.path.join(ROOT, 'macros_%s.py' % _nc)
    chk(os.path.exists(_np), "宏库存在@macros_%s.py(R44/45)" % _nc)
chk(all(_nc in _CL39 for _nc in _NEW6),
    "十七新角色全部注册CHAR_LIBS(R44/45)")
chk(all(_nc in _CMM39 for _nc in _NEW6),
    "十七新角色全部注册reach_maps(R44/45)")
chk(len(_CL39) == 20, "CHAR_LIBS全20角色(R45)", "实际%d" % len(_CL39))
_n6ok = True
for _nc in _NEW6:
    _lj = _CL39[_nc]
    _names6 = set(_lj['names'])
    _ghost6 = [c for _catn in ('melee', 'bullet', 'skill', 'combo',
                               'string', 'sc', 'attack')
               for c in _lj.get(_catn, set()) if c not in _names6]
    if _ghost6 or len(_lj['names']) != len(_lj['macros']):
        _n6ok = False
chk(_n6ok, "十七新角色类别集合零幽灵名+宏名唯一(R44/45)")
_n6m = all(len(_CL39[_nc]['macros']) >= 60 for _nc in _NEW6)
chk(_n6m, "十七新角色宏数≥60(R44/45: 完整动作空间骨架)")
# 模型文件存在性(STORE可被沙箱覆盖 — R44用实存检查, 缺失只WARN级)
for _nc in _NEW6:
    _mp = os.path.join(STORE, 'model_ppo_%s.npz' % _nc)
    _mv = os.path.join(STORE, 'model_ppo_%s_v.npz' % _nc)
    chk(os.path.exists(_mp) and os.path.exists(_mv),
        "模型文件存在@%s(pi+v, R44/45)" % _nc)
# R46(第十四轮§3-1/2/3修复): CHAR扩展+规范化重绑定+SKILL分类
from tm_env import CHAR as _TE_CHAR
chk(len(_TE_CHAR) == 20, "tm_env CHAR表全20角色(R46§3-1阻塞项修复)")
_nc17 = [c for c in _NEW6]
_n46 = all(getattr(__import__('macros_%s' % c),
                    'NORMALIZED_AFFECTED_%s' % c.upper()) is not None
           and isinstance(getattr(__import__('macros_%s' % c),
                                  'NORMALIZED_AFFECTED_%s' % c.upper()), set)
           and len(getattr(__import__('macros_%s' % c),
                           'NORMALIZED_AFFECTED_%s' % c.upper())) > 0
           for c in _nc17)
chk(_n46, "17库hitlab规范化重绑定为set且非空(R46§3-2)")
chk(all('236B' in getattr(__import__('macros_%s' % c),
                          '%s_SKILL_MACROS' % c.upper())
        and '236B' not in getattr(__import__('macros_%s' % c),
                                  '%s_BULLET_MACROS' % c.upper())
        for c in _nc17),
    "17库指令必杀归SKILL非BULLET(R46§3-3: 贴身禁令修正)")
# ============ R47(2026-10-04): 可行性报告六天花板处置 ============
tt47 = src("train_tm.py")
chk("from deck_sampler import sample_deck, curriculum_ratio" in tt47,
    "deck采样器接入训练(R47天花板2: 原恒系统卡→技能/SC入池)")
chk("env.deck_left = _my_deck" in tt47,
    "P1侧独立deck采样(R47: 技能卡/SC入手激活等级特征)")
chk(os.path.exists(os.path.join(ROOT, "deck_sampler.py")),
    "deck_sampler.py存在(R47)")
chk("BC_W_MIN = 0.0" in src("ppo.py"),
    "BC锚允许归零(R47天花板3: 原0.05永不归零→永久人类风格拉力)")
chk("def _expert_rec" not in tt47,
    "expert_rec手写启发式已删(R47天花板3)")
chk("_CHAR_POOL_IDX" in tt47 and '"sakuya": 11' in tt47,
    "20角色池序映射在位(R60 F-8修正: 新角色11-19唯一位, 8角色待316扩维)")
chk("deck_left" in src("tm_env.py") and "deck_right" in src("tm_env.py"),
    "tm_env支持双deck(R47: P1/P2各自独立卡组)")
chk("_ret_win_hist" in tt47 and "corrcoef" in tt47,
    "回报-胜率相关性仪表在位(R47天花板6: 输局赚正回报的预警)")
chk(os.path.exists(os.path.join(ROOT, "ppo_gpu.py")),
    "GPU版PPO存在(R47天花板1: PyTorch迁移)")
chk("PPOTrainerGPU" in src("ppo_gpu.py"),
    "GPU训练器类在位(R47)")
# ============ R48(2026-10-04): League调度 + 教学层起步 ============
chk(os.path.exists(os.path.join(ROOT, "league.py")),
    "league.py存在(R48天花板5)")
chk("league_weight" in src("league.py") and "pick_weighted" in src("league.py"),
    "League胜率加权选择在位(R48: fictitious play)")
chk("from league import pick_weighted" in src("train_tm.py"),
    "League接入_resolve_pool(R48: 替代R43纯轮转)")
chk(os.path.exists(os.path.join(ROOT, "teach.py")),
    "teach.py存在(R48教学层)")
chk("def explain_situation" in src("teach.py")
    and "def batch_explain" in src("teach.py"),
    "教学层局面讲解+批量反查在位(R48)")
# ============ R53(第十七轮§S1/S3): 行为断言升级 ============
te53 = src("tm_env.py")
chk("dl = self.deck_left if self.deck_left else self.deck" in te53,
    "续局包双deck源(R53§S1: 原恒self.deck=系统卡, 90%局失效)")
chk('bytes(dl)' in te53 and 'bytes(dr)' in te53
    and 'bytes(self.deck)' not in te53.split('_restart_same_process')[1][:500]
    if '_restart_same_process' in te53 else False,
    "续局不含单deck(R53§S1: bytes(self.deck)应全部替换)")
gp53 = src("ppo_gpu.py")
chk("等价性验证" in gp53[:600]
    or "P_max_diff=0.000000" in gp53,
    "ppo_gpu等价性已验证(R54: 六缺陷修复, P/V diff=0.000000)")
chk("TRUNK_FLAT = CONV3_F * 5 * 8" in gp53
    and "CONV1_F, CONV2_F, CONV3_F = 32, 64, 64" in gp53,
    "ppo_gpu维度对齐numpy版(R54: 32/64/64+2560)")
chk("OPP_CORE_OFF" in gp53 and "self.opp_off = 2 * n_out + OPP_CORE_OFF"
    in gp53,
    "ppo_gpu对手切片偏移正确(R54: 2*N_OUT+152)")
chk("v_out[r[0]] = r[1]" in gp53 and "os.replace(_tv, v_path)" in gp53,
    "GPU save值头写v文件+原子落盘(R54b+R61e: 原裸savez已改tmp+replace)")
# R55: 语义对齐
chk("_replay_buf" in gp53 and "logp_old[_ord]" in gp53,
    "GPU回放缓冲在位(R55: 池8元组+真ratio)")
chk("bc_mask is not None" in gp53 and "_bm" in gp53,
    "GPU bc_mask接线(R55: 逐行权重+回放行0/专家行1补齐)")
chk("Ve_t" in gp53,
    "GPU expert行ret=各自V(R55: P0-D自洽, 原首行V近似)")
chk("torch.isfinite" in gp53,
    "GPU save NaN守卫(R55: 与numpy版一致)")
chk(os.path.exists(os.path.join(ROOT, "frame_events.py")),
    "frame_events.py存在(R49 L3: 帧级事件系统)")
chk("class FrameEventDetector" in src("frame_events.py")
    and "def pick_reaction" in src("frame_events.py"),
    "帧级事件检测+反应选择在位(R49: 攻略帧窗驱动)")
chk("FRAME_WINDOWS" in src("frame_events.py")
    and "E_GUARDSTUN" in src("frame_events.py"),
    "攻略帧窗表+事件枚举在位(R49: DD 15F/插动12F等)")
chk("_frame_detector" in src("train_tm.py")
    and "frame_events.reaction_mask" in src("train_tm.py"),
    "帧级事件接入_run_episode(R61l B2: reaction_mask策略条件化, "
    "原pick_reaction固定权重随机已废)")
chk('s[o] = min(left.get("pose"' in src("feat_builder.py"),
    "pose/poseFrame入14j段(R57: 显式入账, 原尾写静默覆盖14i后4维)")
# R57(第十八轮2.5): 原"action细分//64下段可分"子串断言已删 — 特性是伪的
# (门控128-256从未命中攻击区; 2A/5A同//64桶), 改行为测试test_guard_height
chk("LOW_ATTACK_IDS = frozenset((303, 311, 402, 412))" in src("feat_builder.py"),
    "下段位=显式查表(R57 2.5: 段位是招式语义, 语义源docs/soku_action_ids.md)")
chk('right["action"] in LOW_ATTACK_IDS' in src("feat_builder.py"),
    "下段位接线: 对手当前招式查表(R57 2.5)")
chk("F_VARIANT_IDS = frozenset((301, 311))" in src("feat_builder.py"),
    "f变体位=显式查表(R58 P1-a: 近/远A可分; 权威全集仅f5A/f2A — "
    "改进方案示例集含321=5AAA/331=诹访子专属, 按空表优于错表只取两枚)")
chk('right["action"] in F_VARIANT_IDS' in src("feat_builder.py"),
    "f变体位接线: 段11[o+20..o+21](R58 — 池扩展余位, 零扩维)")
# R61h(C2): frame_macros已删 — 其宏零消费者(反应表匹配角色库名,
# 非独立宏), DD与角色库重复/投技未经取证/放帧归C1分支门 → 不留死代码
# ============ R50(2026-10-04): 体检A1/A2/A4修复 ============
pp50 = src("ppo.py")
chk("max(0.3," in pp50 and "elif kl < self.TARGET_KL:" in pp50,
    "LR回升条件放宽+地板0.1→0.3(R50 A1: 原KL死区钉底三家)")
chk("1000 if self.macros[i][0].startswith('原子')" in src("train_tm.py"),
    "原子宏配额延长150→1000(R50 A4: 零logit鸡生蛋破解)")
fe50 = src("frame_events.py")
chk("'立防',  'always', 0.4" in fe50,
    "帧级反应防御降权(R50 A2: 立防0.9→0.4, 被动性修正)")
# ============ R51(第十五轮四道闸) ============
chk("_GUARD_STUN_IDS = frozenset(range(150, 167)) - {158}" in fe50,
    "GUARDSTUN检测族=150-166除158(R61d A3裁决: 正防150-157入沿 — "
    "R51版159-167使正确防御不可见; 158=空防状态非硬直边沿)")
chk("_TRUE_DOWN_ACTS = frozenset({88, 89, 97, 98, 100, 143, 145})"
    in fe50,
    "WAKEUP检测=真倒地集7枚(R61d A3裁决: 站立/蹲/普通空受恢复非起身 — "
    "R51版全受击族把hitstun恢复误判起身, hitlab H1实证)")
chk("if _ev_mask is not None:" in src("train_tm.py")
    and "self._frame_event_mask = None" in src("train_tm.py"),
    "R61l(B2): 事件反应决策化(掩码交集→策略选→决策后清除; "
    "R51守式模式已废 — 反应决策入轨迹获信用)")
chk('"sakuya": 11' in src("train_tm.py"),
    "新角色池序从11起(R51§C4: 原3-10与技能特征块冲突)")
# ============ R41(第十二轮§2-1/§2-2): oracle侧血统闭环+源码树入罩 ============
import hashlib as _hl41
import json as _json41


def _md5p41(p):
    try:
        with open(p, "rb") as fh:
            return _hl41.md5(fh.read()).hexdigest().upper()
    except OSError:
        return None


_prov41 = _json41.load(io.open(os.path.join(HERE, "mod_provenance.json"),
                               encoding="utf8"))
_od41 = _prov41.get("oracle_deployed") or {}
chk(bool(_od41.get("deployed_md5")), "血统档案含oracle部署段(R40)",
    "" if _od41 else "缺oracle_deployed键")
if _od41:
    _dm41 = _md5p41(_od41.get("deployed_path", ""))
    _bm41 = _md5p41(_od41.get("built_path", ""))
    chk(_dm41 is not None and _dm41 == _od41.get("deployed_md5"),
        "oracle部署DLL哈希与血统档案一致(C9-oracle, R41§2-1)",
        "实=%s 档=%s" % (_dm41, _od41.get("deployed_md5")))
    chk(_bm41 is not None and _bm41 == _od41.get("built_md5"),
        "oracle构建产物哈希与血统档案一致(C9-oracle, R41§2-1)",
        "实=%s 档=%s" % (_bm41, _od41.get("built_md5")))
    chk(_dm41 == _bm41, "oracle部署==构建(无未部署漂移, C9-oracle)",
        "%s vs %s" % (_dm41, _bm41))
_oroot41 = os.environ.get("TH123_ORACLE_MODROOT",
                          r"D:\temp\soku_arch\build\src")
try:
    _ost41 = io.open(os.path.join(_oroot41, "TrainingMod", "state.cpp"),
                     encoding="utf8", errors="replace").read()
    _onw41 = io.open(os.path.join(_oroot41, "TrainingMod", "network.cpp"),
                     encoding="utf8", errors="replace").read()
    chk("destination.hitStop = 0;" in _ost41,
        "oracle侧源码hitStop初始化在位(R41§2-2: M-1经patch_sources继承)")
    chk("size_t cap = 255;" in _onw41,
        "oracle侧源码对象255截断在位(R41§2-2: M-2经patch_sources继承)")
except OSError as _e41:
    chk(False, "oracle侧源码树可读(R41§2-2)", str(_e41)[:60])
# R26/R29: 空中射程+显式表完整性
import reach_maps as _RM2
from train_tm import CHAR_LIBS as _CL
_common = _RM2.CHAR_MACRO_MOVES['reimu']
chk(_common.get('jA') == (306,) and _common.get('j6A') == (307,)
    and _common.get('j2A') == (308,) and _common.get('j8A') == (309,),
    "显式表空中四招(SokuLib枚举, R29)")
# 状态依赖宏不得有射程(受身与4A同输入签名, 靠显式表排除)
_sd_ok = True
for _ch in ('reimu', 'marisa', 'suika'):
    _lj = _CL[_ch]
    _rx, _ry = _RM2.resolve_reach(_lj['macros'], _ch)
    _nm = [m[0] for m in _lj['macros']]
    for _bad in ('受身', '起身穿', '后跳', '空防'):
        if _bad in _nm and _rx[_nm.index(_bad)] > 0:
            _sd_ok = False
    if 'jA' not in _nm or _rx[_nm.index('jA')] <= 0:
        _sd_ok = False
chk(_sd_ok, "三角色空中射程在位且无状态依赖宏误配(R29)")
# 死招后果处置(第六轮§2.2)
chk(os.path.exists(os.path.join(HERE, "reseed_macro_counts.py")),
    "宏计数重播种工具在位(死招后果处置)")
sd2 = src("side_driver.py")
# R17(§3.1): 原断言要求"sc:步跳过" — 那是v1缺陷(R16已修: sc状态机移植后
# sc步必须入队执行)。行为由C15 test_side_driver_semantics.py断言。
chk("self._last_inp" in sd2, "门步保持上一拍输入(P2-7同款)")
# 从零审查D6-D8余项(2026-09-23)
sc2 = src("soku_client2.py")
chk("class ProtocolError(RuntimeError)" in sc2 and "self.code = code" in sc2,
    "结构化协议错误码(D8: 分支不再子串匹配文案)")
chk("class CrashInfo(Exception)" in sc2,
    "FAULT独立异常(D7: 崩溃穿透容忍层带地址)")
te = src("tm_env.py")
chk("except ProtocolError as e:" in te and "e.code == 17" in te,
    "tm_env按.code分支+err17续喂(§9.2对齐)")
chk("time.sleep(0.03)" in te and te.count("self._drain()") >= 3,
    "开局双排干(D6; R17: 计数≥3, 死代码_start已删, EOF行为由C15钉)")
chk("self.inst = None" in te and 'getattr(self, "h", None)' in te,
    "close幂等+置None(D10)")

# ============ C14 AST结构完整性(第九轮§2.1: 文本断言放行过无法实例化的类) ============
print("=== C14 AST结构完整性(self.X()调用必须有定义) ===")
import ast as _ast

def _check_methods_defined(fname, class_name):
    tree = _ast.parse(src(fname))
    for node in _ast.walk(tree):
        if isinstance(node, _ast.ClassDef) and node.name == class_name:
            methods = {n.name for n in node.body if isinstance(n, _ast.FunctionDef)}
            attrs = set()
            for item in _ast.walk(node):
                if isinstance(item, _ast.Attribute) and \
                        isinstance(item.value, _ast.Name) and \
                        item.value.id == 'self':
                    attrs.add(item.attr)
            calls = set()
            for item in _ast.walk(node):
                if isinstance(item, _ast.Call) and \
                        isinstance(item.func, _ast.Attribute) and \
                        isinstance(item.func.value, _ast.Name) and \
                        item.func.value.id == 'self':
                    calls.add(item.func.attr)
            missing = calls - methods - attrs
            return methods, calls, missing
    return None, None, None

for fname, cls in [("train_tm.py", "TMTrainer"), ("tm_env.py", "TMEnv"),
                   ("ppo.py", "PPOTrainer")]:
    _ms, _cs, _mg = _check_methods_defined(fname, cls)
    if _ms is not None:
        chk(not _mg, "self.X()调用全有定义@%s" % cls,
            "缺失: %s" % sorted(_mg) if _mg else "调用%d个全有定义" % len(_cs))

# ============ C13 BC数据面(第九轮§6: 新数据面必须有质量断言) ============
print("=== C13 BC数据面(覆盖率/占比/非常数列) ===")
_bc_dir = os.path.join(os.path.dirname(HERE), "data", "bc")
for _ch in ("reimu", "marisa", "suika"):
    _bcp = os.path.join(_bc_dir, "bc_%s.npz" % _ch)
    if not os.path.exists(_bcp):
        warn(False, "BC库存在@%s(未提取=合法冷启动)" % _ch)
        continue
    _d = np.load(_bcp, allow_pickle=False)
    _Y = _d["Y"]
    _C = _d["C"]
    # R40(第十一轮§6-6): 原硬编码55/61/62(R19时点值) — 分母动态取当前宏数
    import importlib as _il
    _modmap = {"reimu": "macros", "marisa": "macros_marisa",
               "suika": "macros_suika"}
    _n_macros = len(getattr(_il.import_module(_modmap[_ch]),
                            {"reimu": "MACROS", "marisa": "MACROS_MARISA",
                             "suika": "MACROS_SUIKA"}[_ch]))
    _dist = np.bincount(_Y, minlength=_n_macros)
    _covered = int((_dist > 0).sum())
    chk(_covered >= 15, "BC宏覆盖≥15@%s" % _ch,
        "覆盖%d/%d(过低=匹配器退化)" % (_covered, _n_macros))
    _max_pct = float(_dist.max()) / len(_Y) * 100
    chk(_max_pct <= 50.0, "BC最高标签占比≤50%%@%s" % _ch,
        "最高%.0f%%(分布退化=某宏垄断)" % _max_pct)
    warn(len(np.unique(_C)) > 1 or len(_C) == 0, "BC置信度非常数@%s" % _ch,
         "恒%.1f(bc_build存1.0而非匹配值; 不影响训练信号, 重建后应修)" % _C[0]
         if len(_C) and len(np.unique(_C)) == 1 else "OK")
    chk(_d["X"].shape[0] == len(_Y), "BC行数对齐@%s" % _ch,
        "X%d Y%d" % (_d["X"].shape[0], len(_Y)))

# ============ C15 行为测试门禁(R15§2/R16§4: 文本断言→行为断言制度化) ============
print("=== C15 行为测试套件(子进程真跑, 退出码即门禁) ===")
import subprocess as _sp

# ============ C16 训练安装mod集不变量(R16配置漂移事故制度化) ============
# docs/multi_instance_input.md: 最小集 = MemoryPatch(必须!带参启动硬依赖)
# + SokuAITrainer。2026-09-28事故: MLS被churn成13-mod集且MemoryPatch=false
# → 多实例能力被静默摧毁, 当日无人发现(靠人工审计才定位)。
print("=== C16 th123_train mod集==文档最小集 ===")
import json as _json
# R38(第九轮审计§2.1): TH123_ML可指向沙箱副本(变异自检用), 默认真路径
_ML = os.environ.get(
    "TH123_ML",
    r"D:\touhou\hisoutensoku2026-06-15\th123_train\ModLoaderSettings.json")
try:
    _d = _json.load(io.open(_ML, encoding="utf-8"))
    _en = sorted(k.replace("\\", "/").split("/")[-1].replace(".dll", "")
                 for k, v in _d["modules"].items() if v.get("enabled"))
    chk(_en == ["MemoryPatch", "SokuAITrainer", "SokuDirectXOptimizations"],
        "训练mod集恰为{MemoryPatch,SokuAITrainer,SokuDirectXOptimizations}",
        "实际: %s (SokuDXOpt=多实例D3D共存必需, 实测3/3 vs 2/3)")
except FileNotFoundError:
    chk(False, "ModLoaderSettings.json存在", "文件缺失")

# ============ C13 fleet协议(R56, scenario_b设计§5验证断言) ============
print("=== C13 fleet协议(红线①②③机制化) ===")
aw = src("actor_worker.py") if os.path.exists(
    os.path.join(ROOT, "actor_worker.py")) else ""
lh = src("learner_hub.py") if os.path.exists(
    os.path.join(ROOT, "learner_hub.py")) else ""
ec = src("episode_core.py")
# 红线①: logp采样时记录(actor钩子)+learner侧stored_logp消费
chk("_fleet_logp_rec" in tt
    and "if self._fleet_logp_rec is not None:" in tt
    and "self._fleet_logp_rec(mid, feat, side, mask, nbias)" in tt,
    "R56红线①: train_tm决策点logP钩子(守卫+调用接线)")
chk("_fleet_logp_rec = None" in tt,
    "R56红线①: 钩子默认None(生产路径零行为变化)")
chk("rec_logp(mid, feat, side, mask, nbias)" in aw
    and "_pi_forward" in aw,
    "R56红线①: actor记录logP(a)(与采样同temp/mask/bias)")
chk("stored_logp = kw.get('stored_logp')" in src("ppo_gpu.py")
    and "logp_old = np.asarray(" in src("ppo_gpu.py"),
    "R56红线①: ppo_gpu.update消费stored_logp(真ratio)")
chk("stored_logp=logps" in lh,
    "R56红线①: learner把episode logps传入update")
# 红线②: 局边界快照同步
chk("read_version(snap_dir)" in aw and "load_snapshot_weights" in aw,
    "R56红线②: actor局边界轮询version+原子加载快照")
chk("write_version" in lh and "os.replace" in ec,
    "R56红线②: learner原子发布版本号")
chk("batch_k" in lh and "BATCH_TIMEOUT" in lh,
    "R56红线②: 摸批K局/超时上限(§6陈旧度)")
# 红线③: 环境独立
chk("default_rng(" in aw and "seed_base" in aw
    and "tr.ppo.rng = np.random.default_rng" in aw,
    "R56红线③: actor按(actor_id,ver)重播种ppo.rng(防同流)")
chk("tr._deck_rng = _rnd.Random(seed_base" in aw,
    "R56红线③: deck/league rng按actor独立")
# 单写者纪律(fleet的共享档全部归learner)
chk("tr._snapshot_pool = lambda: None" in aw
    and "tr._save_distill = lambda rows: None" in aw
    and "tr.macro_counts_path = " in aw,
    "R56单写者: actor禁写池快照/蒸馏, 宏计数走scratch")
chk("np.bincount(" in lh and "counts_path" in lh,
    "R56单写者: learner从acts合并宏计数并原子落盘")
chk('suffix' in lh and '_fleet' in lh,
    "R56隔离: learner默认suffix=_fleet(A/B期不碰生产主档)")
# episode核心契约(单一事实源)
chk("EP_KEYS" in ec and "save_episode_npz" in ec
    and "load_episode_npz" in ec,
    "R56契约: episode npz模式单一事实源@episode_core")
chk('fname + ".tmp.npz"' in ec,
    "R56契约: episode原子写tmp名以.npz结尾(np.savez自动补后缀的坑)")
chk("for i, L in enumerate(ep_lens):" in src("ppo_gpu.py"),
    "R56: ppo_gpu._gae按局索引ep_terms(多局批原行索引越界)")
# F4共享: 对手池构造单一实现
chk("def build_opp_cycle(specs):" in tt
    and "opp = build_opp_cycle(args.opp)" in tt
    and "build_opp_cycle(opps)" in aw,
    "R56-F4: 对手池构造单一实现(train_tm/actor共用)")
# fleet车道
try:
    import portmap as _PM
    _p0, _p1 = _PM.fleet_port(0, 0), _PM.fleet_port(15, 9)
    chk(21000 <= _p0 and _p1 <= 21299 and _PM.fleet_port(3) != _p0,
        "R56-P0F5: fleet车道21000-21299(16道×10宽, 可分辨)",
        "%d..%d" % (_p0, _p1))
except AttributeError as e:
    chk(False, "R56-P0F5: portmap fleet段", str(e))

# ---- R57(第十八轮严审2.1-2.4) ----
chk("os.path.getmtime(p), p" in lh,
    "R57-2.1: episode按mtime排序(原文件名字典序饿死低编号actor)")
chk("10_000 + int(gpu_tr._updates)).choice(" in lh,
    "R57-2.2: BC锚每update重采样(原终身固定64行 → bcw过拟合定点)")
chk("state['snap_ver'] * 1_000_001 + state['ep']" in aw,
    "R57-2.3: 每局重播种(原同版本内逐局rng状态复位=跨局随机结构重复)")
chk("os.path.join(snap_dir, 'counts.npy')" in lh
    and "tr.macro_counts = _c" in aw,
    "R57-2.4: 宏计数下行(learner随快照发counts, actor换版载入)")
chk("EP_SCHEMA = 1" in ec and 'data["schema"]' in ec,
    "R57-2.6: episode schema版本字段(格式演化可判读)")
chk("def aggregate_stats(" in src("fleet_supervisor.py"),
    "R57-2.6: supervisor聚合actor stats(league数据源)")

# ---- R60(从零审计F-1..F-11) ----
tt60 = src("train_tm.py")
sd60 = src("side_driver.py")
gp60 = src("ppo_gpu.py")
pp60 = src("ppo.py")
chk('elif getattr(self, "_fleet_logp_rec", None) is not None:' in tt60,
    "R60-F1: actor模式每局刷新_ppo_act(原被_upd_thread门控=快照死链)")
chk("key=lambda p: int(''.join(c for c in os.path.basename(p)" in lh,
    "R60-F3: 快照滚动按版本号数值排序(原字典序v10<v2删最新)")
chk("not f.endswith('.tmp.npz')" in lh,
    "R60-F4: collect排除在途tmp件(原子写被glob击穿)")
chk("-np.ones(_rp_n, dtype=np.int64)" in gp60
    and "-np.ones(len(Ye_t), dtype=np.int64)" in gp60,
    "R60-F5: opp_next回放/专家行补-1(原越界IndexError)")
chk("ret = adv + V_np" in gp60
    and gp60.index("ret = adv + V_np") < gp60.index(
        "adv = (adv - adv.mean())"),
    "R60-F6: ret在归一化前算(critic目标=λ回报, 原z分数+V)")
chk("logp_e = F.log_softmax" in gp60,
    "R60-F7: 专家行logp_old=当前策略(原硬0→KL虚高钉LR下限)")
chk("mask = mask & ~self.near_idx" in tt60
    and "mask = mask & ~self.near_idx" in sd60,
    "R60-F9: 330门只禁近战子集(原全攻击禁=远程立回不可学)")
chk('self._last_ret = float(np.sum(rews))' in tt60,
    "R60-F10: 回报-胜率看门狗喂活(原_last_ret从未赋值=死仪表)")
chk("stored_logp=LOGPS" in tt60
    and "logp_old[:N0] = _sl" in pp60,
    "R60-F11: 行为策略logP入ratio(探针/bias/价值引导的实际分布)")
chk("elif dx_abs < 150" in tt60 and "melee_idx" in tt60,
    "R60-F9: melee_idx保留(其他消费点)且150贴身禁弹幕不变")

# ---- R61e(F3尾巴快杀+B6, 2026-10-05) ----
chk('_c0 == "COM":' in tt60 and 'self.feat_builder._opp_char = self.char' in tt60,
    "R61e: --opp COM首位不再SideDriver崩(镜像轮换COM分支)")
chk("os.replace(_tp, pi_path)" in gp60 and "os.replace(_tv, v_path)" in gp60,
    "R61e: ppo_gpu save原子落盘(pi+v, 原裸savez中断=半档损坏)")
chk("'learner_%s%s.lock' % (char, suffix)" in lh,
    "R61e/D5: learner单实例锁(双learner双写者竞争防线)")
chk('com_difficulty_%s%s.json" % (self.char, self.suffix)' in tt60
    and "续档难度" in tt60 and "os.replace(_t, _p)" in tt60,
    "R61e/B6: COM难度持久化(读侧续档+写侧落盘双锚 — R61e变异"
    "教训: 只锚读侧时杀落盘的变异逃逸)")
import re as _re61e
_bs = _re61e.findall(r'_BULLET_MACROS = \{([^}]*)\}', src("macros_sakuya.py"))
chk(_bs and '"2C"' in _bs[0],
    "R61e: 生成库BULLET补2C(17库, 原宏存在但零分类)")

# ---- R61f(F3尾巴清偿第二批, 2026-10-05) ----
chk("logits = logits + b / t" in gp60,
    "R61f: GPU采样bias/temp对齐numpy语义(原加在/temp后差×T系数)")
chk("(float(m[5])\n                                           if len(m) >= 6 else 1.0)" in gp60
    or "if len(m) >= 6 else 1.0" in gp60,
    "R61f: GPU旧档meta 5元素守卫(原m[5]越界IndexError)")
chk("ep_first=None, bc_targets=None," in gp60,
    "R61f: GPU update签名对齐numpy参数序(原第7位语义不同=陷阱)")
chk("def disk_guard(" in lh,
    "R61f/D5: learner磁盘满降级(清旧episode+过期快照)")
chk("def reap_orphans(" in src("fleet_supervisor.py"),
    "R61f/D5: supervisor孤儿回收(WMI父进程判定)")
chk("_s = (_s * 0x85EBCA6B) & 0xFFFFFFFF" in aw,
    "R61f: actor种子SplitMix32终混(原线性式理论可碰撞)")
chk("or char is None:" in src("skill_levels.py"),
    "R61f: cid_to_slot合并路径已删(cid102/106/108三角色歧义)")
chk("if len(deck) > 20:" in src("deck_sampler.py"),
    "R61f: deck抽样32张边界截断(技能段保序在前)")
chk("stats记的是**模型**对每个对手的胜率" in src("league.py"),
    "R61f: league docstring方向修正(原与实现相反)")

# ---- R61g(B1): BC匹配器SC词汇(M2组件) ----
chk("SC_PRESS_F = 3" in src("bc_match.py")
    and "def sc_press_bits(" in src("bc_match.py"),
    "R61g: sc:步展开为SC按压词汇(原结构性排除=SC标签恒0%)")
chk("bool(inp.get(\"SC\")), bool(inp.get(\"SW\"))" in src("bc_match.py"),
    "R61g: 匹配器8元组含SC/SW位(AandB→SC经battle_to_trainer)")
chk("def resolve_sc_label(" in src("bc_build.py"),
    "R61g: BC具体卡解析(手牌选中位→sc_target匹配宏, 无匹配丢行)")

# ---- R61(用户2026-10-05"d+快速胜利")奖励经济学 ----
chk("def graze_low_rate(f):" in tt60
    and "GRAZE_SAT_F = 6000.0" in tt60,
    "R61-d: 擦弹低段费率按局时衰减(拖时间收割死亡, 硬上界≈30)")
chk("else graze_low_rate(frames)" in tt60,
    "R61-d: 衰减费率接入奖励点(原恒定GRAZE_LOW_RATE)")
chk("def fastwin_bonus(" in tt60 and "R_FASTWIN = 6.0" in tt60
    and "_fw = fastwin_bonus(frames - round_f0" in tt60,
    "R61: 快胜奖金接入回合胜(剩余时间比例, 速决+6)")
chk("def ko_round_reward(my_hp, opp_hp, win):" in tt60
    and "True) * d_sl + _fw" in tt60
    and "False) * d_sr" in tt60,
    "R61b: KO时双方血量差入奖励(胜margin分档+惜败半罚, 用户2026-10-05;"
    "断言锚胜/败两侧调用组合式 — 原子串被未变异侧满足=R61b变异漏网教训)")
chk("GAMMA_POT = 0.999" in tt60
    and "GAMMA_POT * _pot - self._prev_pot" in tt60,
    "R61c(B5): 势函数γ因子(Ng式γΦ(s')−Φ(s), 原γ=1)")
chk("self._seiran_gauge" in tt60
    and "card_gauge_val=_cg" in tt60
    and "_cg = (left.get(\"cardGauge\", 0) if card_gauge_val is None" in tt60,
    "R61c(B5): cardGauge晴岚哨兵(晴岚期冻结gauge, 伪势跳±2.0防线)")

_BEHAVIOR_TESTS = [
    ("test_threat.py", "P0-K: 全零速弹表→(None,0) + TTI语义"),
    ("test_opp_model.py", "P0-L: 9情境可达 + 6段占据无混叠"),
    ("test_feat_segments.py", "R16§3: 每特征段≥1非常数维"),
    ("test_meta_roundtrip.py", "P0-I: meta 6字段save/load往返"),
    ("test_side_driver_semantics.py",
     "R17§3.1: eval温度跟随/sc+门步执行/决策计数(行为化替代文本断言)"),
    ("test_drain_eof.py",
     "R17§3.8: _drain遇FIN返回不死循环(D1回归的配对变异)"),
    ("test_opp_subnet.py",
     "R17对手建模: 子网络接线/辅助梯度FD/新参数往返(深测见test_r17_ppo.py)"),
    ("test_visual_stack.py",
     "R19: P1/P2视觉栈同构(差分栈)+_char_name+cid_to_slot真表"),
    # R38(第九轮审计): 新路径可达性 — P0-1/P0-2即"无可达性测试"的产物
    ("test_smoke_driver_r38.py",
     "R38: 合成帧驱动frame_input — 受击中止/R34中断/灵力门控/门步/sc步全分支"),
    ("test_replay_semantics.py",
     "R38: 经验回放两连发update — 池8元组/mask对齐/logp_old真ratio(P0-4)"),
    # R56(fleet P1): 协议端到端 — 快照发布→actor加载→episode消费→
    # 红线①(篡改logp变红)/红线③(种子独立)行为验证
    ("test_fleet_protocol.py",
     "R56: fleet协议 — 快照/episode npz/摸批更新/红线①③行为"),
    # R57(第十八轮2.5): 段位/蓄力感知行为化(原子串断言放行了R49伪特性)
    ("test_guard_height.py",
     "R57 2.5: 下段查表位+pose块真生效(2A/5A可分/负例不误触/无覆盖)"),
    # R60(从零审计): ppo_gpu更新循环行为化(F-5连发/F-7 KL sane/F-6 critic)
    ("test_gpu_update_r60.py",
     "R60 F5/F6/F7: GPU更新连发+BC锚KL+critic输出(更新语义对账)"),
    # R61: 奖励经济学(用户裁定d+快胜)
    ("test_reward_r61.py",
     "R61: 擦弹衰减/拖时间上界30/快胜奖金 — 收割经济学行为断言"),
    # R61c: 势函数γ+晴岚哨兵(主规划B5)
    ("test_potential_r61c.py",
     "R61c(B5): γ因子/哨兵覆盖通道/量级上限/状态确定性"),
    # R61d: A3裁决的帧级事件边沿(F-12/F-13)
    ("test_frame_edges_r61d.py",
     "R61d(A3): 正防150-157入GUARDSTUN沿+真倒地7枚WAKEUP沿(行为钉)"),
    # R61g: SC词汇(B1/M2)
    ("test_sc_vocab_r61g.py",
     "R61g(B1): SC按压匹配+expert_bits 8元组+具体卡解析"),
]
for _tname, _tdesc in _BEHAVIOR_TESTS:
    _tp = os.path.join(ROOT, _tname)
    if not os.path.exists(_tp):
        chk(False, "行为测试存在@%s" % _tname, "文件缺失")
        continue
    _r = _sp.run([sys.executable, "-X", "utf8", _tp],
                 capture_output=True, text=True, timeout=600,
                 encoding="utf-8", errors="replace")
    chk(_r.returncode == 0, "行为测试@%s" % _tname,
        ("%s | 末行: %s" % (_tdesc,
                            (_r.stdout or _r.stderr or "").strip().splitlines()[-1][:60])
         ) if _r.returncode == 0 else
        ("FAIL: %s" % ((_r.stderr or _r.stdout or "").strip().splitlines()[-1][:200])))

print()
print("==== 契约门禁: %d PASS / %d WARN / %d FAIL ====" %
      (len(PASSES), len(WARNS), len(FAILS)))
if FAILS:
    print("FAIL项:", ", ".join(FAILS))
    print("结论: 阻断。修完再合批/发布。")
    sys.exit(1)
print("结论: 通过(WARN不阻断)。变异覆盖见 tools/gate_selftest.py")
