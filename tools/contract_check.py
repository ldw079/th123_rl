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


def fn_has(f, fn_name, needle):
    """F2(从零#2起批): AST锚定断言 — needle必须出现在**函数fn_name体内**
    (替代全文件裸子串钉: 不受无害移动/注释/文档字符串误伤, 断言可证伪
    性更强)。找不到函数=FAIL。
    F2批5修正: 同名函数(如多类的__init__)时**任一**体内含needle即通过
    — 原版只查walk序第一个同名函数(soku双类__init__当场翻车)。"""
    try:
        tree = ast.parse(src(f))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == fn_name:
            seg = ast.get_source_segment(src(f), node)
            if seg and needle in seg:
                return True
    return False


# ============ C1 62fps教义 ============
print("=== C1 62fps教义(用户2026-09-21明令; R10只管逻辑帧率, tps协议参数豁免) ===")
import threat
import config
chk(threat.GAME_FPS == 62, "threat.GAME_FPS==62", "got %r" % threat.GAME_FPS)
chk(config.FPS == 62, "config.FPS==62", "got %r" % config.FPS)
_div60 = re.compile(r"/\s*60(?:\.0)?\b")
for f in ["threat.py", "feat_builder.py", "train_tm.py", "macros/__init__.py",
          "opp_model.py", "standard_tree.py"]:
    bad = [l.strip() for l in lines(f) if _div60.search(l)]
    chk(not bad, "无/60帧转秒残留@%s" % f, "; ".join(bad[:2]))
# AST级60字面量扫描: 时敏文件零容忍; 结构文件按行白名单(网格60×80/重试range/tps默认)
_STRICT60 = ["threat.py", "feat_builder.py", "macros/__init__.py", "macros/marisa.py",
             "macros/suika.py", "opp_model.py", "standard_tree.py"]
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
import macros.marisa as macros_marisa
import macros.suika as macros_suika
# P2(2026-10-15): 343硬编码改**区间下界+段账本** — JZ-1迁移(343→358)
# 时此处漏更致基线9项FAIL("锚是活的"第三次复发: 维度字面量跟不了活常量)
chk(feat_builder.FeatureBuilder.CORE_DIMS >= 343,
    "CORE_DIMS>=343(S-2段330+13; JZ-1后358)",
    "got %r" % feat_builder.FeatureBuilder.CORE_DIMS)
# 全量sweep抓漏(R150): 原>=343区间界对358→357漂移放行, 靠活性段的
# IndexError崩溃拦截(非干净FAIL=D12口径漏网) — 增段账本精确锚:
# feat_builder尾部fill_jz1(s, 343, ...)写[343..343+15), CORE_DIMS
# 必须==343+jz1宽(单源: N_DIMS=15)
import jz1_features as _jz1
_core_exp = ((343 + _jz1.N_DIMS) + (24 if getattr(
    feat_builder.FeatureBuilder, 'FEAT_SPACE', True) else 0))
chk(feat_builder.FeatureBuilder.CORE_DIMS == _core_exp,
    "CORE_DIMS==343+JZ-1段账本(+task-21 空间24; env开关)",
    "got %r != %d" % (feat_builder.FeatureBuilder.CORE_DIMS, _core_exp))
chk(opp_model.OpponentModel.N_FEATS == 75,
    "opp_model.N_FEATS==75(基础27+历史40+资源8)",
    "got %r" % opp_model.OpponentModel.N_FEATS)
_n_by_mod = (macros.N_MACROS, macros_marisa.N_MACROS_MARISA,
             macros_suika.N_MACROS_SUIKA)
for n in _n_by_mod:
    fb = feat_builder.FeatureBuilder(n)
    chk(fb.n_side == 2 * n + feat_builder.FeatureBuilder.CORE_DIMS,
        "n_side==2N+CORE_DIMS@N=%d(S-2段)" % n,
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
_legal60 = {0, 1, 2} | set(range(11, 28))
chk(_m60 is not None and len(_vals60) == len(set(_vals60)) == 20
    and set(_vals60) <= _legal60,
    "池序映射: 20角色全唯一无重复(R61t F5: 前12走段11+后8走扩展区)",
    str(sorted(_vals60)))
# F2批1(从零#2): 裸子串→AST锚定(needle限定函数体内)
chk(fn_has("train_tm.py", "_build_side", "core[227 + opp_id] = 1.0")
    and fn_has("train_tm.py", "_build_side",
               "core[self._EXT_OPP_OFF + (opp_id - 20)] = 1.0"),
    "对手one-hot双区写入(R61t F5: 段11+扩展区) [_build_side体内]")
chk('_CHAR_POOL_IDX' in tt,
    "20角色池序映射在位(R47: 原R19三角色池序已扩容)")
chk(tt.count('GUARD_ALL_IDS') >= 2,
    "train_tm防御判定用GUARD_ALL_IDS(R34中断/空挥)")
# R39(P3-8): 原第三处断言钉已删的L2奖励代码 — 随死通道删除
chk(fn_has("train_tm.py", "_build_side", "core[33] = "),
    "turn_recency写core[33](P0-2修复在位) [_build_side体内]")
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
chk(fn_has("soku_client2.py", "recv_frame", "if _ok_n > 8:"),
    "OK跳过循环8次上限(R19) [recv_frame体内]")
chk(fn_has("soku_client2.py", "recv_frame",
           "_ok_n > 8:\n                raise ProtocolError"),
    "OK洪流按协议错处理(R19) [recv_frame体内]")
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
# F2批1(从零#2): 裸子串→AST锚定(needle限定在函数体内, 免无害重构误伤)
chk(fn_has("ppo.py", "update", "ent_grad = -P *"),
    "熵梯度源码形: -P(logP+H)=+dH/dz(配maximize=True) [update体内]")
chk(fn_has("ppo.py", "update", "maximize=True"),
    "策略Adam为ascent(maximize=True) [update调用点]")
chk(fn_has("ppo.py", "update", "bc_mask[idx]"),
    "bc_mask小批索引(P1-2) [update体内]")
chk(fn_has("ppo.py", "save", "os.replace"),
    "原子保存(P0-5) [save体内]")
chk(fn_has("ppo.py", "save", "meta=np.array([self._temp"),
    "退火/meta状态持久化 [save体内]")
chk(fn_has("ppo.py", "save", "W1v=self.W1v"),
    "价值网键名W1v(断裂修复在位) [save体内]")

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
chk(fn_has("train_tm.py", "_run_episode", "_whiff_cost(dec_name)"),
    "空挥惩罚接线(P2-1, W_WHIFF) [_run_episode体内]")
chk(not re.search(r"^WHIFF_[BCS]", tt, re.M), "死常量WHIFF_B/C/SKILL已清")
chk(fn_has("train_tm.py", "_run_episode", "rews[-1] += seg_rew"),
    "终局段奖励入账(KO不丢) [_run_episode体内]")
chk(fn_has("train_tm.py", "_run_episode", "opp_vx=opp_vx_ema"),
    "opp_vx真接线(P1-4b, 差分EMA) [_run_episode体内]")
chk(fn_has("feat_builder.py", "update_opp",
           'right["action"] in HIT_ACT_IDS'),
    "opp_down=受击动作集(P1-4a真) [update_opp体内]")
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
chk(fn_has("train_tm.py", "_run_episode",
           "or (score_l_prev + score_r_prev) < 2)"),
    "truncated终止位(R39: 超时+比分<2的异常结束局均按截断bootstrap) [_run_episode体内]")

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
import macros.marisa as macros_marisa, macros.suika as macros_suika
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
chk(fn_has("train_tm.py", "audit_tree", "TREES[self.char]"),
    "audit_tree按角色路由(不再灵梦树打折) [audit_tree体内]")

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
chk(fn_has("side_driver.py", "_rec",
           "_self.last_match = (e.winner, e.ls, e.rs)"),
    "GameEnded胜者被记录(父类step会吞掉) [EvalEnv._rec体内]")
chk(fn_has("outer_loop.py", "run_match", "vs_com=False, tps=tps"),
    "对局走VS_PLAYER双控通道 [run_match体内]")
chk('matrix["%s>%s" % (a, b)]' in ol and "参考线55%" in ol,
    "战报含胜率矩阵+毕业门读数(2.4: 55%参考线, 重构待干净读数)")
# R17(§3.1): 原文本断言"temp=1.0"在评估侧改为温度跟随模型meta后假红 —
# 改由C15的test_side_driver_semantics.py行为断言(温度==_temp, 决策计数)
chk(fn_has("outer_loop.py", "latest", 'not f.endswith("_v.npz")'),
    "池latest排除价值网快照(实测踩坑) [latest体内]")
# 训练半环集成
chk(fn_has("train_tm.py", "_run_episode",
           "self.env.step(inp, self._opp_inp)"),
    "双输入步进(对手侧输入接线) [_run_episode体内]")
chk(fn_has("train_tm.py", "_run_episode",
           "self.opp.frame_input(right, left, weather,"),
    "P2对手驱动用(右,左)视角 [_run_episode体内]")
chk(fn_has("train_tm.py", "_make_env", "vs_com=False,"),
    "对手模式=VS_PLAYER(_make_env体内)")
chk(fn_has("train_tm.py", "train", "_settle_match()")
    and fn_has("train_tm.py", "train", "_rotate_opp(ep)"),
    "胜率结算+对手轮换入训练循环 [train体内]")
chk('"macro_counts_%s%s.npy" % (char, suffix)' in tt,
    "suffix产物隔离(双训练器互斥)")
# 行为: 三角色SideDriver构建+模型加载(维度链正确性)
import side_driver as sd_mod
for _ch in ("reimu", "marisa", "suika"):
    _d = sd_mod.SideDriver(_ch, "L")
    chk(_d.n_side == 5 * _d.n_macros
        + feat_builder.FeatureBuilder.CORE_DIMS,
        "SideDriver维度@%s(R61t F5含扩展one-hot)" % _ch,
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
import macros.marisa as _mm
import macros.suika as _ms
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
mc_src = src("macros/__init__.py")
mm_src = src("macros/marisa.py")
ms_src = src("macros/suika.py")
chk('[(("down",), 6), (("down", "A"), 10)]' in mc_src,
    "reimu 2A源始预置步=down×6(hitlab v9标定阈值5)")
chk('[(("down",), 6), (("down", "A"), 10)]' in mm_src,
    "marisa 2A源始预置步=down×6")
chk('[(("down",), 6), (("down", "A"), 10)]' in ms_src,
    "suika 2A源始预置步=down×6")

# ============ C12 端口段(第六轮审计§3: 显式划分防跨实例串流) ============
print("=== C12 端口段(portmap静态校验) ===")
from portmap import SEGMENTS, check_disjoint, check_rebuild_domain, check_reserved
_ok, _det = check_disjoint()
chk(_ok, "端口段两两不重叠", _det)
_okr, _detr = check_reserved()
chk(_okr, "G2工具端口RESERVED落段(branch/habit/human_*)", _detr)
_ok2, _det2 = check_rebuild_domain()
chk(_ok2, "rebuild取值域枚举(slot0-5×ep200)全在段内(D4)", _det2)
# P1-9防复发(从零#4): 单源表完备性 — 全仓reserved_port('X')调用×
# RESERVED键对账(新工具只改调用方不改表=启动即KeyError的根因拦截)
import re as _re_port
import portmap as _pm
_calls = set()
_all_port_src = []   # R150: 动态格式串豁免用全源汇总
for _root, _dirs, _fs in os.walk('.'):
    if any(s in _root for s in ('_archive', '.zcode', 'gate_sandbox')):
        continue
    for _fn in _fs:
        # 排除本断言自身(docstring占位符'X'与正则字面量)
        if not _fn.endswith('.py') or _fn == 'contract_check.py':
            continue
        try:
            _src = open(os.path.join(_root, _fn), encoding='utf8',
                        errors='replace').read()
        except OSError:
            continue
        _all_port_src.append(_src)
        for _m in _re_port.finditer(
                r'reserved_port\(\s*["\']([^"\']+)["\']\s*\)', _src):
            _calls.add((_fn, _m.group(1)))
_all_port_blob = '\n'.join(_all_port_src)
_missing = sorted((f, n) for f, n in _calls if n not in _pm.RESERVED)
chk(not _missing, "P1-9: reserved_port调用×RESERVED键完备对账",
    '缺键: %s' % (_missing[:4],))
# 动态格式化调用豁免(R150): expert_harvest_w0-3经
# reserved_port('expert_harvest_w%s' % _wtag)派生(采集并行worker),
# 静态字面量扫描天然不可见 — 前缀模板在源汇总中命中即算被调用
_unused = sorted(
    n for n in _pm.RESERVED
    if not any(n == c[1] for c in _calls)
    and ('%s%%s' % n[:-1]) not in _all_port_blob)
chk(not _unused, "RESERVED无僵尸键(有键无调用)", '僵尸: %s' % (_unused,))
chk('OPCODE_SPEED, OPCODE_DISPLAY' in src("tm_env.py")
    and '("<BB", 3, 0)' not in src("tm_env.py"),
    "G2(R77): tm_env渲染/变速用命名opcode(裸2/3字面量退役)")
chk('OPCODE_SET_POSITION' in src("tools/branch_demo.py"),
    "G2(R77): branch_demo局面控制opcode收编soku_client2")
chk(SEGMENTS["train_rebuild"] == (20850, 20899)
    and SEGMENTS["eval"][0] == 20900 and SEGMENTS["hitlab"][0] == 20920
    and SEGMENTS["exp"][0] == 20940, "段定义与文档一致",
    str({k: v for k, v in SEGMENTS.items()})[:90])
chk(fn_has("train_tm.py", "train", "rebuild_port(self.slot, ep)"),
    "train_tm异常重建走portmap(原版base+100+ep跨段撞) [train体内]")
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
chk(fn_has("soku_client2.py", "__init__",
           "self.lsock.settimeout(accept_timeout)")
    and fn_has("soku_client2.py", "__init__", "accept_timeout=120.0"),
    "accept有超时(R16参数化: 默认120s, tm_env持锁期传90s) [__init__体内]")
# 外环加固(第六轮§7) — F2批2: run_match体内锚定
ol2 = src("outer_loop.py")
chk(fn_has("outer_loop.py", "run_match", "env.close()"),
    "外环finally走env.close()(句柄/线程不泄漏) [run_match体内]")
chk('"aborted" += 1' in ol2 or 'res["aborted"] += 1' in ol2,
    "中断局计数(不静默丢弃)")
chk(fn_has("outer_loop.py", "cycle", "outer_loop.lock")
    and fn_has("outer_loop.py", "cycle", "O_EXCL"),
    "外环单实例锁 [cycle体内]")
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
# 自检实测漏网教训); F2批2: fn_has限定决策函数体内
chk(fn_has("train_tm.py", "_run_episode",
           "mask = mask & ~self.corner_combo_idx"),
    "版边连门控操作行在位(R23) [_run_episode体内]")
chk(fn_has("train_tm.py", "_run_episode",
           "mask = mask & ~self.air_combo_idx"),
    "空连门控操作行在位(R23) [_run_episode体内]")
sd_src = src("side_driver.py")
chk(fn_has("side_driver.py", "decide",
           "mask = mask & ~self.corner_combo_idx")
    and fn_has("side_driver.py", "decide",
               "mask = mask & ~self.air_combo_idx"),
    "SideDriver同款位置门控(R23) [decide体内]")
# 新宏末位追加契约(本次差点中插错位全部下游)
chk("新宏必须追加在列表末尾" in src("macros/suika.py")
    or "新宏必须追加在列表末尾" in src("macros/__init__.py"),
    "宏库末位追加契约注记在位(R23)")
import macros.suika as _MS
_suika_last = [m[0] for m in _MS.MACROS_SUIKA][-4:]
# P2修(从零#4晚, 宏库扩展波88/93/91后): 计数硬编码改**区间下限+
# 原子在位**(扩展波只许尾增 — R23末位追加契约); C4压起身"末位"改
# "扩展波前末位"(wave_ext追加段之前)
chk(_MS.N_MACROS_SUIKA >= 77
    and "原子·确认5A" in [m[0] for m in _MS.MACROS_SUIKA],
    "suika原子在位+宏数≥77(R35+R61n底数; 扩展波尾增合法)")
# R38(第九轮审计§2.1): 原死表达式`STORE if False else 硬编码路径` —
# 门禁成为单PC仪器。改环境变量可覆盖, 默认仓库data/bc(bc_build产物位)。
# P1-2b(从零#5): 断言对象改成**活档** — 原读 data/bc/*.npz(330代 legacy 镜像,
# 仅在仓内 gitignore 区), 活库是 STORE/bc_<ch>_{X,S,Y}.npy + _meta.json。
# 「量错了对象」与 P1-1(评估读旧模型)同族: 断言绿/红都不代表生产实况。
_bc_dir = os.environ.get(
    "TH123_BC_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 'data', 'bc'))
_liveS = os.path.join(STORE, 'bc_suika_S.npy')
if os.path.exists(_liveS):
    _bc_s = np.load(_liveS, mmap_mode='r')
    try:
        import json as _json0
        _bc_meta0 = _json0.load(io.open(
            os.path.join(STORE, 'bc_suika_meta.json'), encoding='utf8'))
    except (OSError, ValueError):
        _bc_meta0 = {}
    _bc_npz = {'S': _bc_s, 'meta': _json0.dumps(_bc_meta0)}
    _bc_src_note = '活档trio'
else:
    _bc_npz = np.load(os.path.join(_bc_dir, 'bc_suika.npz'),
                      allow_pickle=True)
    _bc_s = _bc_npz['S']
    _bc_src_note = 'data/bc(legacy镜像)'
_bc_want = 5 * _MS.N_MACROS_SUIKA + _FB.FeatureBuilder.CORE_DIMS
if _bc_s.shape[1] != _bc_want:
    warn(_bc_s.shape[1] == _bc_want,
         "suika BC库宽度迁移期(R61n C4 +7宏: BC=%d≠模型%d — 下批重建)",
         "S=%d want=%d" % (_bc_s.shape[1], _bc_want))
else:
    chk(True, "suika BC库宽度与五块布局对齐(R23-30)",
        "S=%d src=%s" % (_bc_s.shape[1], _bc_src_note))
# R38: 重建后的库必须带布局版本且gap/untech块有真实数据(非零填充)
try:
    import json as _json
    _bc_meta = _json.loads(str(_bc_npz['meta']))
except Exception:
    _bc_meta = {}
_b0 = 2 * _MS.N_MACROS_SUIKA + _FB.FeatureBuilder.CORE_DIMS
# layout标签: 正确='5N+CORE_DIMS:v2'; 旧'5N+308:v2'=R61g重建时bc_build
# LAYOUT常量未动态化的误写(宽度本就正确; 训练器持锁无法即时迁移 —
# 接受legacy但WARN, 停机窗口跑tools/bc_label_migrate.py)
_layout = _bc_meta.get('layout') if isinstance(_bc_meta, dict) else None
if _layout == '5N+%d:v2' % _FB.FeatureBuilder.CORE_DIMS:
    chk(True, "suika BC库带布局版本(标签=实际宽度)", "layout=%s" % _layout)
else:
    warn(False, "suika BC库layout标签待迁移(误写308, 宽度正确)",
         "layout=%s → 停机窗口跑tools/bc_label_migrate.py" % _layout)
chk(abs(_bc_s[:, _b0:_b0 + _MS.N_MACROS_SUIKA]).sum() > 0,
    "suika BC库gap_x块非全零(R38: repad零填充事故不复存在)")
# R24: 射程双通道(掩码栅栏+特征理解)断言 — F2批2: fn_has锚定
chk(fn_has("train_tm.py", "__init__",
           "self.macro_reach, self.macro_reach_v = resolve_reach"),
    "train_tm二维射程解析在位(R24/R25) [__init__体内]")
chk(fn_has("train_tm.py", "_run_episode",
           "dx_abs > self.macro_reach + REACH_MARGIN"),
    "射程门控操作行在位(R24) [_run_episode体内]")
chk(fn_has("train_tm.py", "_build_side",
           "(_adx - self.macro_reach) / 200.0"),
    "射程差特征块在位(R24) [_build_side体内]")
sd2 = src("side_driver.py")
chk(fn_has("side_driver.py", "_side_feat",
           "(_adx - self.macro_reach) / 200.0")
    and fn_has("side_driver.py", "decide",
               "dx_abs > self.macro_reach"),
    "SideDriver射程双通道同构(R24) [_side_feat+decide体内]")
import reach_maps as _RM
chk(_RM.CHAR_MACRO_MOVES['reimu']['5A'] == (300, 301)
    and _RM.CHAR_MACRO_MOVES['reimu']['2A'] == (303, 311)
    and _RM.CHAR_MACRO_MOVES['reimu']['DA'] == (305, 302),
    "显式move表=SokuLib枚举(5A含f5A/DA=66A, R29)")
chk("_starter_button" not in src("reach_maps.py"),
    "脚本签名推导已删(R29: 状态依赖招无法区分, 受身/4A同签名)")
# R25(用户2026-10-02: 弹幕复杂化+判定二维): 运动学/地雷/追踪/纵向 — F2批2锚定
fb_src = src("feat_builder.py")
chk(fn_has("feat_builder.py", "track_bullets", "self.bullet_kin = kin"),
    "bullet_kin并行表在位(加速度/转向/驻留/弹型, R25) [track_bullets体内]")
chk(fn_has("feat_builder.py", "build", "0.5 * _ax * horizon * horizon"),
    "未来占据二次外推(变速弹, R25) [build体内]")
chk(fn_has("feat_builder.py", "build", "_spd < 0.5 and _k[3] >= 10"),
    "地雷威胁判定(近零速+驻留, R25) [build体内]")
chk(fn_has("feat_builder.py", "build", "_k[2] >= 0.08 and _spd > 1.0"),
    "追踪弹悲观TTI(转向率阈值, R25) [build体内]")
chk(fn_has("train_tm.py", "_run_episode",
           "_ady > self.macro_reach_v + REACH_MARGIN"),
    "纵向射程门控在位(R25) [_run_episode体内]")
chk(fn_has("train_tm.py", "_build_side",
           "(_ady - self.macro_reach_v) / 200.0"),
    "纵向射程差特征块在位(R25) [_build_side体内]")
# R33(用户2026-10-02"防御刷分"): 格挡≠擦弹+防御递减+L1距离门
chk(fn_has("feat_builder.py", "check_graze",
           'left.get("action", 0) in GUARD_ALL_IDS'),
    "check_graze排除防御态(R33: 格挡≠擦弹, 防刷分) [check_graze体内]")
# R39(P3-8): R_GUARD/R_GUARD_PREP死通道断言已随死代码删除
# (R35势函数化后tracker零调用者, 门禁保护死代码=噪声)
# R34(架构阶段1): 帧级防御中断+灵力门控+原子宏 — R61u(C1)已移至macro_executor
chk(fn_has("macro_executor.py", "advance_queue", "300 <= opp_a < 600"),
    "帧级防御中断在位(R34, R61u C1移至macro_executor) [advance_queue体内]")
chk(fn_has("macro_executor.py", "advance_queue", "spirit < 100"),
    "灵力门控在位(R34, R61u C1移至macro_executor) [advance_queue体内]")
import macros.marisa as _MM
def _c4_before_wave(names, floor):
    """C4压起身四连在位且位于**扩展波起点之前**(R61n末位+wave尾增)。"""
    c4 = ["压起身·即", "压起身·延迟", "压起身·空", "压起身·穿"]
    idx = [names.index(n) for n in c4 if n in names]
    if len(idx) != 4 or idx != sorted(idx):
        return False
    return len(names) >= floor and idx[-1] < len(names) - 13  # 扩展区≥13宏

chk(_MM.N_MACROS_MARISA >= 76
    and "原子·确认5A" in [m[0] for m in _MM.MACROS_MARISA]
    and _c4_before_wave([m[0] for m in _MM.MACROS_MARISA], 76),
    "marisa四原子在位+C4压起身位于扩展波前(R34+R61n底数76; 尾增合法)")
# R35(六大差距方案实施)
import macros as _MR
import macros.suika as _MS2
chk(_MR.N_MACROS >= 70
    and "原子·确认5A" in [m[0] for m in _MR.MACROS]
    and _c4_before_wave([m[0] for m in _MR.MACROS], 70),
    "reimu四原子在位+C4压起身位于扩展波前(R35+R61n底数70; 尾增合法)")
chk(_MS2.N_MACROS_SUIKA >= 77
    and "原子·确认5A" in [m[0] for m in _MS2.MACROS_SUIKA]
    and _c4_before_wave([m[0] for m in _MS2.MACROS_SUIKA], 77),
    "suika四原子在位+C4压起身位于扩展波前(R61n底数77; 尾增合法)")
chk(fn_has("train_tm.py", "state_potential", "POT_W"),
    "势函数奖励塑形在位(R35: 状态势差, 消灭刷分) [state_potential体内]")
chk(fn_has("ppo.py", "update", "_replay_buf"),
    "经验回放在位(R35: 高优势样本跨批重用) [update体内]")
chk("_Xn, side.reshape(1, -1)" in tt,
    "价值引导宏选择在位(R35: critic评估Top-5) [兼容双写形态]")
# R38(第九轮审计P0-1..4): 三个现行bug+一个死特性的修复断言
chk("from opp_model import GUARD_ALL_IDS" in sd_src,
    "side_driver导入GUARD_ALL_IDS(R38 P0-2: 原遗漏→对手攻击+我方硬直时NameError) [模块级导入, 合理文本钉]")
chk("_V, = self._ppo_act._v_forward" not in tt
    and fn_has("train_tm.py", "_run_episode",
               "_best, _best_v = mid, _base_v"),
    "价值引导解包修复+基准阈值参与(R38 P0-3: 原元组解包ValueError=特性从未执行) [_run_episode体内]")
ppo_src = src("ppo.py")
# F2批3: ppo回放族AST锚定(needle限定update体内)
chk(fn_has("ppo.py", "update",
           "np.argsort(-np.abs(adv[_hi_idx]))[:_cap]"),
    "回放池切片[:_cap](R38 P0-4a: 原[_cap:]方向反→池恒空) [update体内]")
chk(fn_has("ppo.py", "update",
           "logp_old[N0:N0 + _rp_n] = _rows[7]"),
    "回放行logp_old=保存时策略(R38 P0-4c: 原取当前策略→ratio恒1) [update体内]")
chk(fn_has("ppo.py", "update", "M = np.concatenate([M, _rows[6]])"),
    "回放行mask拼接(R38 P0-4b: 原缺→前向广播爆炸被异步线程吞) [update体内]")
chk(fn_has("train_tm.py", "_run_episode",
           "_Xn, side.reshape(1, -1)"),
    "价值引导宏选择在位(R35: critic评估Top-5) [_run_episode体内]")
# R38(P0-5/P0-6): BC对齐+原生布局 — F2批4: AST锚定(import在模块顶层
# L30, 钉的是build_rows体内的**消费点**而非import行)
chk(fn_has("bc_build.py", "build_rows", "estimate_lag_map(frames"),
    "BC构建走对齐器(R38 P0-5: 状态↔输入错位+70~240帧, 原原始下标配对) [build_rows体内消费]")
chk(fn_has("bc_build.py", "build_rows", "5 * n_macros + fb.CORE_DIMS"),
    "BC侧向量5N+CORE_DIMS原生构建(R38 P0-6: 原4N+308+repad零填充) [build_rows体内]")
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
chk(fn_has("oracle_batch2.py", "run_one", "'SOKUAI_INPUTLOG': '1'"),
    "oracle录制启用INPUTLOG通道(R40§6-1: mod同帧输入日志, 实测rep↔ilog匹配率1.0000) [run_one体内]")
chk(fn_has("oracle_batch2.py", "run_one",
           "'SOKUAI_INPUTLOG_PATH': ilog_path"),
    "inputlog路径按shard隔离(R40: 并行车道不互写) [run_one体内]")
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
chk("POOL_SNAPSHOT_EVERY = 50" in tt43
    and fn_has("train_tm.py", "train", "(ep + 1) % POOL_SNAPSHOT_EVERY == 0")
    and "def _snapshot_pool" in tt43,
    "池刷新制度在位(R43-A: 每50局快照入池+滚动清理 — 原28h打旧对手; "
    "消费点[train体内]锚定)")
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
    _np = os.path.join(ROOT, 'macros', '%s.py' % _nc)
    chk(os.path.exists(_np), "宏库存在@macros/%s.py(R44/45)" % _nc)
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
_n46 = all(getattr(__import__('macros.%s' % c, fromlist=['*']),
                    'NORMALIZED_AFFECTED_%s' % c.upper()) is not None
           and isinstance(getattr(__import__('macros.%s' % c, fromlist=['*']),
                                  'NORMALIZED_AFFECTED_%s' % c.upper()), set)
           and len(getattr(__import__('macros.%s' % c, fromlist=['*']),
                           'NORMALIZED_AFFECTED_%s' % c.upper())) > 0
           for c in _nc17)
chk(_n46, "17库hitlab规范化重绑定为set且非空(R46§3-2)")
chk(all('236B' in getattr(__import__('macros.%s' % c, fromlist=['*']),
                          '%s_SKILL_MACROS' % c.upper())
        and '236B' not in getattr(__import__('macros.%s' % c, fromlist=['*']),
                                  '%s_BULLET_MACROS' % c.upper())
        for c in _nc17),
    "17库指令必杀归SKILL非BULLET(R46§3-3: 贴身禁令修正)")
# ============ R47(2026-10-04): 可行性报告六天花板处置 ============
tt47 = src("train_tm.py")
chk(fn_has("train_tm.py", "_make_env",
           "from deck_sampler import sample_deck, curriculum_ratio"),
    "deck采样器接入训练(R47天花板2: 原恒系统卡→技能/SC入池) [_make_env体内]")
chk(fn_has("train_tm.py", "_make_env", "env.deck_left = _my_deck"),
    "P1侧独立deck采样(R47: 技能卡/SC入手激活等级特征) [_make_env体内]")
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
chk(fn_has("train_tm.py", "__init__", "_ret_win_hist")
    and fn_has("train_tm.py", "_settle_match", "corrcoef"),
    "回报-胜率相关性仪表在位(R47天花板6: 输局赚正回报的预警) [__init__+_settle_match体内]")
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
chk(fn_has("tm_env.py", "_restart_same_process",
           "dl = self.deck_left if self.deck_left else self.deck"),
    "续局包双deck源(R53§S1: 原恒self.deck=系统卡, 90%局失效) [_restart_same_process体内]")
chk(fn_has("tm_env.py", "_start_first",
           "dl = self.deck_left if self.deck_left else self.deck"),
    "首局包双deck源(R53§S1对齐) [_start_first体内]")
chk('bytes(dl)' in te53 and 'bytes(dr)' in te53
    and 'bytes(self.deck)' not in te53.split('_restart_same_process')[1][:500]
    if '_restart_same_process' in te53 else False,
    "续局不含单deck(R53§S1: bytes(self.deck)应全部替换)")
gp53 = src("ppo_gpu.py")
chk("等价性验证" in gp53[:600]
    or "P_max_diff=0.000000" in gp53,
    "ppo_gpu等价性已验证(R54: 六缺陷修复, P/V diff=0.000000) [文档串, 合理文本钉]")
chk("TRUNK_FLAT = CONV3_F * 5 * 8" in gp53
    and "CONV1_F, CONV2_F, CONV3_F = 32, 64, 64" in gp53,
    "ppo_gpu维度对齐numpy版(R54: 32/64/64+2560) [模块常量, 合理文本钉]")
chk(fn_has("ppo_gpu.py", "__init__",
           "self.opp_off = 2 * n_out + OPP_CORE_OFF"),
    "ppo_gpu对手切片偏移正确(R54: 2*N_OUT+152) [__init__体内]")
chk(fn_has("ppo_gpu.py", "save", "v_out[r[0]] = r[1]")
    and fn_has("ppo_gpu.py", "save", "os.replace(_tv, v_path)"),
    "GPU save值头写v文件+原子落盘(R54b+R61e: 原裸savez已改tmp+replace) [save体内]")
# R55: 语义对齐 — F2收官: 函数体内锚定
chk(fn_has("ppo_gpu.py", "__init__", "_replay_buf")
    and fn_has("ppo_gpu.py", "update", "logp_old[_ord]"),
    "GPU回放缓冲在位(R55: 池8元组+真ratio) [__init__+update体内]")
chk(fn_has("ppo_gpu.py", "update", "bc_mask is not None")
    and fn_has("ppo_gpu.py", "update", "_bm"),
    "GPU bc_mask接线(R55: 逐行权重+回放行0/专家行1补齐) [update体内]")
chk(fn_has("ppo_gpu.py", "update", "Ve_t"),
    "GPU expert行ret=各自V(R55: P0-D自洽, 原首行V近似) [update体内]")
chk(fn_has("ppo_gpu.py", "save", "torch.isfinite"),
    "GPU save NaN守卫(R55: 与numpy版一致) [save体内]")
chk(os.path.exists(os.path.join(ROOT, "frame_events.py")),
    "frame_events.py存在(R49 L3: 帧级事件系统)")
chk("class FrameEventDetector" in src("frame_events.py")
    and "def pick_reaction" in src("frame_events.py"),
    "帧级事件检测+反应选择在位(R49: 攻略帧窗驱动)")
chk("FRAME_WINDOWS" in src("frame_events.py")
    and "E_GUARDSTUN" in src("frame_events.py"),
    "攻略帧窗表+事件枚举在位(R49: DD 15F/插动12F等)")
chk(fn_has("train_tm.py", "_run_episode", "_frame_detector")
    and fn_has("train_tm.py", "_run_episode", "frame_events.reaction_mask"),
    "帧级事件接入_run_episode(R61l B2: reaction_mask策略条件化, "
    "原pick_reaction固定权重随机已废) [_run_episode体内]")
chk(fn_has("train_tm.py", "_run_episode", "int(_fwin)")
    and "FRAME_WINDOWS" in src("frame_events.py"),
    "J裁定(2.72): 事件窗_fwin显式消费入日志 — 反应采B2即时掩码语义, "
    "不留'定义未接'第三态(仅锚定义会放过消费回归) [_run_episode体内]")
chk('s[o] = min(left.get("pose"' in src("feat_builder.py"),
    "pose/poseFrame入14j段(R57: 显式入账, 原尾写静默覆盖14i后4维)")
# R57(第十八轮2.5): 原"action细分//64下段可分"子串断言已删 — 特性是伪的
# (门控128-256从未命中攻击区; 2A/5A同//64桶), 改行为测试test_guard_height
chk("LOW_ATTACK_IDS = frozenset((303, 311))" in src("feat_builder.py"),
    "下段位=显式查表(R57 2.5; BH-3.2后回落表=303/311 — 2B/2C虚报按 "
    "cleista 20/20实测移除[P2清偿, 审计2026-10-16]; 真值=guard_height逐角色表)")
chk('right["action"] in self._low_ids()' in src("feat_builder.py"),
    "下段位接线: 对手当前招式查表(BH-3.2: 逐角色LOW表经_low_ids, "
    "原LOW_ATTACK_IDS直引锚已随R141迁self._low_ids)")
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
chk(fn_has("side_driver.py", "reset_match", "self._last_inp"),
    "门步保持上一拍输入(P2-7同款) [reset_match体内]")
# 从零审查D6-D8余项(2026-09-23) — F2收官: 函数体内锚定
sc2 = src("soku_client2.py")
chk("class ProtocolError(RuntimeError)" in sc2
    and fn_has("soku_client2.py", "__init__", "self.code = code"),
    "结构化协议错误码(D8: 分支不再子串匹配文案) [类定义模块级+__init__体内]")
chk("class CrashInfo(Exception)" in sc2,
    "FAULT独立异常(D7: 崩溃穿透容忍层带地址) [类定义, 合理文本钉]")
te = src("tm_env.py")
chk(fn_has("tm_env.py", "step", "except ProtocolError as e:")
    and fn_has("tm_env.py", "step", "e.code == 17"),
    "tm_env按.code分支+err17续喂(§9.2对齐) [step体内]")
chk("time.sleep(0.03)" in te and te.count("self._drain()") >= 3,
    "开局双排干(D6; R17: 计数≥3, 死代码_start已删, EOF行为由C15钉)")
chk(fn_has("tm_env.py", "__init__", "self.inst = None")
    and fn_has("tm_env.py", "close", 'getattr(self, "h", None)'),
    "close幂等+置None(D10) [__init__+close体内]")

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

# ============ C17 SC费用对表(U-3 round16: c6错CID表事故的行为化钉) ============
print("=== C17 生成库SC_COST ⊆ card_tables真值(tm_env.CHAR单源) ===")
import importlib as _il17
from card_tables import CHAR_CARD_TABLES as _CCT
from tm_env import CHAR as _CHAREN
_NEW17 = ['yukari', 'komachi', 'meiling', 'sanae', 'youmu', 'yuyuko',
          'tenshi', 'suwako', 'alice', 'cirno', 'aya', 'remilia',
          'utsuho', 'sakuya', 'iku', 'patchouli', 'reisen']
for _ch in _NEW17:
    _truth = {int(i): (int(c) if str(c).isdigit() else 1)
              for i, _n, c in _CCT[_CHAREN[_ch]]}
    _mod = _il17.import_module('macros.%s' % _ch)
    _cost = getattr(_mod, 'SC_COST_%s' % _ch.upper())
    # 只对≥100的角色卡严格对表(0/1=系统卡槽位, 不在CHAR_CARD_TABLES)
    _bad = {cid: (_cost[cid], _truth.get(cid))
            for cid in _cost
            if cid >= 100 and _truth.get(cid) != _cost[cid]}
    chk(not _bad, "SC费用=真值表@%s" % _ch,
        "错表: %s (c6曾因手抄CID错位取他角色费用)" % _bad if _bad
        else "%d项全对" % len(_cost))

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
    _modmap = {"reimu": "macros", "marisa": "macros.marisa",
               "suika": "macros.suika"}
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
# 红线①: logp采样时记录(actor钩子)+learner侧stored_logp消费 — F2批6 AST锚定
chk(fn_has("train_tm.py", "__init__", "_fleet_logp_rec = None")
    and fn_has("train_tm.py", "_run_episode",
               "if self._fleet_logp_rec is not None:")
    and fn_has("train_tm.py", "_run_episode",
               "self._fleet_logp_rec(mid, feat, side, mask, nbias,"),
    "R56红线①: train_tm决策点logP钩子(守卫+调用接线; P1-5加mix_p尾参)"
    " [__init__+_run_episode体内]")
chk(fn_has("actor_worker.py", "run_actor",
           "tr._fleet_logp_rec = rec_logp"),
    "R56红线①: actor记录logP(a)(与采样同temp/mask/bias) [run_actor体内]")
chk(fn_has("ppo_gpu.py", "update", "stored_logp = kw.get('stored_logp')")
    and fn_has("ppo_gpu.py", "update", "logp_old = np.asarray("),
    "R56红线①: ppo_gpu.update消费stored_logp(真ratio) [update体内]")
chk(fn_has("learner_hub.py", "update_from_episodes",
           "stored_logp=logps"),
    "R56红线①: learner把episode logps传入update [update_from_episodes体内]")
# 红线②: 局边界快照同步
chk(fn_has("actor_worker.py", "run_with_snapshot",
           "read_version(snap_dir)"),
    "R56红线②: actor局边界轮询version [run_with_snapshot体内]")
chk(fn_has("episode_core.py", "save_episode_npz", "os.replace"),
    "R56红线②: episode npz原子落盘 [save_episode_npz体内]")
chk("BATCH_TIMEOUT" in lh
    and fn_has("learner_hub.py", "run_learner", "batch_k"),
    "R56红线②: 摸批K局/超时上限(§6陈旧度) [run_learner体内锚batch_k]")
# 红线③: 环境独立
chk(fn_has("actor_worker.py", "run_actor",
           "tr.ppo.rng = np.random.default_rng")
    and fn_has("actor_worker.py", "run_actor", "seed_base"),
    "R56红线③: actor按(actor_id,ver)重播种ppo.rng(防同流) [run_actor体内]")
chk(fn_has("actor_worker.py", "run_actor",
           "tr._deck_rng = _rnd.Random(seed_base"),
    "R56红线③: deck/league rng按actor独立 [run_actor体内]")
# 单写者纪律(fleet的共享档全部归learner)
chk(fn_has("actor_worker.py", "run_actor",
           "tr._snapshot_pool = lambda: None")
    and fn_has("actor_worker.py", "run_actor",
               "tr._save_distill = lambda rows: None")
    and fn_has("actor_worker.py", "run_actor", "tr.macro_counts_path = "),
    "R56单写者: actor禁写池快照/蒸馏, 宏计数走scratch [run_actor体内]")
chk(fn_has("learner_hub.py", "update_from_episodes", "np.bincount(")
    and fn_has("learner_hub.py", "run_learner", "counts_path"),
    "R56单写者: learner从acts合并宏计数并原子落盘 "
    "[update_from_episodes+run_learner体内]")
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
# R65(D3')锚随语义演进: 签名加pool_root/strict(启动校验与运行时同池),
# actor侧锚定fleet池根注入 — 单一实现+同池双断言
chk("def build_opp_cycle(specs, pool_root=None, strict=True):" in tt
    and "opp = build_opp_cycle(args.opp)" in tt
    and "build_opp_cycle(" in aw
    and "pool_root=os.path.join(FLEET_DIR, 'pool')" in aw,
    "R56-F4: 对手池构造单一实现(train_tm/actor共用; R65: actor传fleet池根)")
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
chk(("EP_SCHEMA = 1" in ec or "EP_SCHEMA = 2" in ec) and 'data["schema"]' in ec,
    "R57-2.6: episode schema版本字段(格式演化可判读; R63→v2带contract块)")
# ---- R63(P0-2): episode尺寸代际契约(生产事故: 旧码actor×新码learner=批量丢数据) ----
chk("class EpisodeContractError" in ec,
    "R63(P0-2): 契约违规专用异常(与'单批数据坏'可区分)")
chk("def code_macro_count(" in ec and "def build_contract(" in ec
    and "def check_contract(" in ec,
    "R63(P0-2): 契约三件套(代码侧宏数真值/构造/自洽校验)")
chk("EP_SCHEMA = 2" in ec,
    "R63(P0-2): schema==2(contract块随v2落地; 退回v1即断言红)")
chk(fn_has("episode_core.py", "load_episode_npz",
           "if _bad:\n            raise EpisodeContractError"),
    "R63(P0-2): 读者在契约/形状不符时抛错(变异自检证明原'anchored字符串'"
    "可被绕过 → 改锚**判定+抛出**的毗邻结构) [load_episode_npz体内]")
chk(fn_has("episode_core.py", "check_model_generation", "code_macro_count(char)")
    and fn_has("episode_core.py", "check_model_generation", "!= int(_cn)"),
    "R63(P0-2): 模型代际判据=代码侧宏数比对(单一实现, 可行为测试) "
    "[check_model_generation体内]")
chk(fn_has("episode_core.py", "save_episode_npz", "拒绝落盘"),
    "R63(P0-2): 写者落盘前自检(声明与数组形状不符即拒写) "
    "[save_episode_npz体内]")
chk(fn_has("actor_worker.py", "submit",
           "build_contract(char, tr.n_macros, int(tr.ppo.N_SIDE), tr.n_macros)"),
    "R63(P0-2): actor以自身真实尺寸构造契约(宏数/N_SIDE取自本网络) "
    "[actor_worker.submit体内]")
chk(fn_has("learner_hub.py", "run_learner", "入队契约不符"),
    "R63(P0-2): learner启动前入队预检(拒绝消费旧代际队列) "
    "[run_learner体内]")
chk(fn_has("learner_hub.py", "run_learner", "check_model_generation(char, n_out)")
    and fn_has("learner_hub.py", "run_learner", "拒绝启动"),
    "R63(P0-2): learner启动前校验模型档代际(经单一判据+拒绝启动) "
    "[run_learner体内]")
# R63(P0-1): 镜像只翻水平轴(上下不是左右) — 见test_mirror_axis_r63.py
tt63 = src("train_tm.py")
chk('if axis == "H" and mirror:' in tt63,
    "R63(P0-1): keys_to_input镜像只翻H(原'H','V'同翻=约一半决策执行纵向镜像动作)")
chk('if axis in ("H", "V") and mirror:' not in tt63,
    "R63(P0-1): 旧的H+V同翻写法已从库中清除(防回退)")
# R63(P0-2): 生产macro_counts档宽度必须等于当前代码宏数
# (非现役17角色档仍为66宏=旧308代际残留; 该断言会把他们点出来)
from episode_core import code_macro_count as _rt_code_n   # noqa: E402
for _ch in ("reimu", "marisa", "suika"):
    # P1-2b(从零#5): 活档优先 — fleet 写 _fleet 后缀; 原查无后缀档(单机遗留,
    # 宽 70/76/77) → 三条 WARN 常驻且指向退役产物, 掩盖真实代际问题。
    _mc_f = os.path.join(STORE, "macro_counts_%s_fleet.npy" % _ch)
    _mc = _mc_f if os.path.exists(_mc_f) else os.path.join(
        STORE, "macro_counts_%s.npy" % _ch)
    _cn = _rt_code_n(_ch)
    _got = (int(len(np.load(_mc))) if os.path.exists(_mc) else None)
    warn(_got is not None and _cn is not None and _got == _cn,
         "R63(P0-2): macro_counts_%s宽度==代码宏数(%s)" % (_ch, _cn),
         "%s src=%s" % (_got if _got is not None else "缺档",
                        os.path.basename(_mc)))
chk("def aggregate_stats(" in src("fleet_supervisor.py"),
    "R57-2.6: supervisor聚合actor stats(league数据源)")

# ---- R63(F6): 超人距离从"占位口径"改为可证伪度量 ----
# 原 `metric = avg_wr - var` 是把胜率的均值减方差(无量纲意义, 无基准);
# 实测盘上矩阵: 每对2局的 marisa 拿到 metric=1.0 —— 占位读数会冒充满级。
_sg = src(os.path.join("tools", "superhuman_gauge.py"))
_em = src(os.path.join("tools", "eval_matrix.py"))
chk("def wilson(" in _sg and "def gauge_from_matrix(" in _sg
    and "def load_human_baseline(" in _sg,
    "R63(F6): 超人距离三件套(Wilson区间/主度量/人类锚)")
chk("if k <= 0:\n        lo = 0.0" in _sg,
    "R63(F6): Wilson端点按定义钳制(闭式解残差4.87e-17会让与0比较失效) "
    "[wilson体内]")
chk("per[cb]['pairs'][ca] = rate(bw, n)" in _sg,
    "R63(F6): 对位双边口径(原只写a视角 → 恒在b侧角色avg_wr=None覆盖洞) "
    "[matchup_rates体内]")
chk("'comparable': comparable" in _sg and "'distance': None" in _sg,
    "R63(F6): 非同口径只报不可相减原因, 不伪造'距离'")
chk("'oracle', 'shards'" in _sg,
    "R63(F6): 人类锚接真实重放数据(oracle shards, 191局) — 项目唯一真人数据")
# R63(F6): COM 标尺天花板饱和(用户实测: 真人打COM=100%) → 不可作分母
chk("COM_VS_HUMAN" in _sg and "'discriminates_at_top': False" in _sg,
    "R63(F6): COM标尺标注天花板饱和(真人打COM=100% → 不能当超人距离分母)")
chk("def com_ruler_verdict(" in _sg
    and "below_human_floor" in _sg
    and "at_or_above_human_on_saturated_ruler" in _sg,
    "R63(F6): COM标尺四档判定(低于人类下限/不可区分/饱和达顶/无数据)")
chk("lo >= hw - near" in _sg,
    "R63(F6): 饱和达顶分支可达(原 lo>=hw 在hw=1.0时是**死分支** — 自测抓出)")
chk("cannot_do" in _sg and "作为任何\"距离\"的分母" in _sg,
    "R63(F6): 报告显式写出COM标尺不能做什么(防误读)")
# R63: 变异沙箱自清 + 磁盘预检(治理工具自身事故)
_gs = src(os.path.join("tools", "gate_selftest.py"))
chk("if base:\n            shutil.rmtree(base, ignore_errors=True)" in _gs,
    "R63: 沙箱失败时也自清(base入try — 原崩溃残留1.5GB/份压满系统盘)")
chk("SELFTEST_TMPDIR" in _gs and "_skip_big" in _gs,
    "R63: 沙箱磁盘预检 + 可指大盘(原WinError 112伪装成门禁坏)")
chk("worst_lower" in _sg and "min_games" in _sg,
    "R63(F6): 最差对位Wilson下界 + 最小样本门(最弱对位不被平均值掩盖)")
chk("'metric': d['worst_lower']" in _em,
    "R63(F6): eval_matrix改调新度量")
# 防回退断言必须只看**可执行代码**: 旧公式在文档/注释里被引用是正常的
# (本模块自己的说明就引用了它) — 全文本子串匹配会把自己的注释判红。
# R63教训: 只遍历表达式节点(字符串常量不在其中)。
def _has_sub_name(node, name):
    """node 的表达式子树里是否有某个"以 name 为下标的取值"(如 x['avg_wr'])。"""
    for n in ast.walk(node):
        if isinstance(n, ast.Subscript):
            ix = n.slice
            if isinstance(ix, ast.Constant) and ix.value == name:
                return True
    return False


_em_stale = False
try:
    for _n in ast.walk(ast.parse(_em)):
        if isinstance(_n, ast.BinOp) and isinstance(_n.op, ast.Sub):
            if _has_sub_name(_n.left, 'avg_wr') and \
                    _has_sub_name(_n.right, 'var'):
                _em_stale = True
except SyntaxError:
    _em_stale = True
chk(not _em_stale,
    "R63(F6): 旧的'胜率减方差'占位公式已从**可执行代码**中清除"
    "(注释/文档引用不算 — 自测抓出全文本匹配会判红自身注释)")

# ---- R60(从零审计F-1..F-11) ----
tt60 = src("train_tm.py")
sd60 = src("side_driver.py")
gp60 = src("ppo_gpu.py")
pp60 = src("ppo.py")
chk('elif getattr(self, "_fleet_logp_rec", None) is not None:' in tt60,
    "R60-F1: actor模式每局刷新_ppo_act(原被_upd_thread门控=快照死链)")
# F2批1(从零#2): 裸子串→AST锚定
chk(fn_has("learner_hub.py", "publish_snapshot",
           "key=lambda p: int(''.join(c for c in os.path.basename(p)"),
    "R60-F3: 快照滚动按版本号数值排序(原字典序v10<v2删最新) [publish_snapshot体内]")
chk(fn_has("learner_hub.py", "collect_episodes",
           "not f.endswith('.tmp.npz')"),
    "R60-F4: collect排除在途tmp件(原子写被glob击穿) [collect_episodes体内;"
    "锚完整过滤式非裸子串 — 注释里也含.tmp.npz, 裸锚会被注释自我逃逸]")
chk(fn_has("ppo_gpu.py", "update", "-np.ones(_rp_n, dtype=np.int64)")
    and fn_has("ppo_gpu.py", "update",
               "-np.ones(len(Ye_t), dtype=np.int64)"),
    "R60-F5: opp_next回放/专家行补-1(原越界IndexError) [update体内]")
chk(fn_has("ppo_gpu.py", "update", "ret = adv + V_np")
    and gp60.index("ret = adv + V_np") < gp60.index(
        "adv = (adv - adv.mean())"),
    "R60-F6: ret在归一化前算(critic目标=λ回报, 原z分数+V) [update体内+顺序]")
chk(fn_has("ppo_gpu.py", "update", "logp_e = F.log_softmax"),
    "R60-F7: 专家行logp_old=当前策略(原硬0→KL虚高钉LR下限) [update体内]")
chk(fn_has("train_tm.py", "near_gate",
           "mask = mask & ~self.near_idx")
    and fn_has("train_tm.py", "_run_episode",
               "self.near_gate(mask, dx_abs)")
    and fn_has("side_driver.py", "decide",
               "mask = mask & ~self.near_idx"),
    "R60-F9: 330门只禁近战子集(原全攻击禁=远程立回不可学) "
    "[near_gate体内+_run_episode接线+decide体内(2026-10-14抽取)]")
chk(fn_has("train_tm.py", "_submit_update",
           "self._last_ret = float(np.sum(rews))"),
    "R60-F10: 回报-胜率看门狗喂活(原_last_ret从未赋值=死仪表) [_submit_update体内]")
chk(fn_has("train_tm.py", "_submit_update", "stored_logp=LOGPS")
    and fn_has("ppo.py", "update", "logp_old[:N0] = _sl"),
    "R60-F11: 行为策略logP入ratio(探针/bias/价值引导的实际分布) "
    "[_submit_update+update体内]")
chk(fn_has("train_tm.py", "near_gate", "elif dx_abs < 150"),
    "R60-F9: 150贴身禁弹幕不变 [near_gate体内(2026-10-14抽取自_run_episode)]")

# ---- R61e(F3尾巴快杀+B6, 2026-10-05) ----
chk(fn_has("train_tm.py", "__init__", '_c0 == "COM":')
    and fn_has("train_tm.py", "__init__",
               'self.feat_builder._opp_char = self.char'),
    "R61e: --opp COM首位不再SideDriver崩(启动COM分支) [__init__体内]")
chk(fn_has("ppo_gpu.py", "save", "os.replace(_tp, pi_path)")
    and fn_has("ppo_gpu.py", "save", "os.replace(_tv, v_path)"),
    "R61e: ppo_gpu save原子落盘(pi+v, 原裸savez中断=半档损坏) [save体内]")
chk(fn_has("learner_hub.py", "run_learner",
           "'learner_%s%s.lock' % (char, suffix)"),
    "R61e/D5: learner单实例锁(双learner双写者竞争防线) [run_learner体内]")
chk(fn_has("train_tm.py", "__init__",
           'com_difficulty_%s%s.json')
    and fn_has("train_tm.py", "_com_ladder", "os.replace(_t, _p)"),
    "R61e/B6: COM难度持久化(读侧__init__续档+写侧_com_ladder落盘双锚 — "
    "R61e变异教训: 只锚读侧时杀落盘的变异逃逸)")
import re as _re61e
_bs = _re61e.findall(r'_BULLET_MACROS = \{([^}]*)\}', src("macros/sakuya.py"))
chk(_bs and '"2C"' in _bs[0],
    "R61e: 生成库BULLET补2C(17库, 原宏存在但零分类) [常量集, 合理文本钉]")

# ---- R61f(F3尾巴清偿第二批, 2026-10-05) ----
chk(fn_has("ppo_gpu.py", "sample", "logits = logits + b / t"),
    "R61f: GPU采样bias/temp对齐numpy语义(原加在/temp后差×T系数) [sample体内]")
chk("(float(m[5])\n                                           if len(m) >= 6 else 1.0)" in gp60
    or "if len(m) >= 6 else 1.0" in gp60,
    "R61f: GPU旧档meta 5元素守卫(原m[5]越界IndexError) [load体内, 合理文本钉]")
chk("ep_first=None, bc_targets=None," in gp60,
    "R61f: GPU update签名对齐numpy参数序(原第7位语义不同=陷阱)")
# F2批1: AST锚定(disk_guard须真调_dg_cleanup=I1行为测试的接线前提)
chk(fn_has("learner_hub.py", "disk_guard", "_dg_cleanup"),
    "R61f/D5: learner磁盘满降级(真调清理路径 — I1行为测试钉清理语义)")
chk("def reap_orphans(" in src("fleet_supervisor.py"),
    "R61f/D5: supervisor孤儿回收(WMI父进程判定)")
chk(fn_has("actor_worker.py", "run_actor",
           "_s = (_s * 0x85EBCA6B) & 0xFFFFFFFF"),
    "R61f: actor种子SplitMix32终混(原线性式理论可碰撞) [run_actor体内]")
chk(fn_has("skill_levels.py", "cid_to_slot", "or char is None:"),
    "R61f: cid_to_slot合并路径已删(cid102/106/108三角色歧义)")
chk(fn_has("deck_sampler.py", "sample_deck", "if len(deck) > 20:"),
    "R61f: deck抽样32张边界截断(技能段保序在前) [sample_deck体内]")
chk("stats记的是**模型**对每个对手的胜率" in src("league.py"),
    "R61f: league docstring方向修正(原与实现相反)")

# ---- R61g(B1): BC匹配器SC词汇(M2组件) ---- F2收官锚定
chk("SC_PRESS_F = 3" in src("bc_match.py")
    and fn_has("bc_match.py", "sc_press_bits", "SC_PRESS_F"),
    "R61g: sc:步展开为SC按压词汇(原结构性排除=SC标签恒0%) [sc_press_bits体内+常量]")
chk(fn_has("bc_match.py", "inp_bits",
           'bool(inp.get("SC")), bool(inp.get("SW"))'),
    "R61g: 匹配器8元组含SC/SW位(AandB→SC经battle_to_trainer) [inp_bits体内]")
chk("def resolve_sc_label(" in src("bc_build.py"),
    "R61g: BC具体卡解析(手牌选中位→sc_target匹配宏, 无匹配丢行) [存在性, 合理文本钉]")

# ---- R61(用户2026-10-05"d+快速胜利")奖励经济学 ---- F2收官锚定
chk("def graze_low_rate(f):" in tt60
    and "GRAZE_SAT_F = 6000.0" in tt60,
    "R61-d: 擦弹低段费率按局时衰减(拖时间收割死亡, 硬上界≈30) [def+常量, 合理文本钉]")
chk(fn_has("train_tm.py", "_run_episode", "else graze_low_rate(frames)"),
    "R61-d: 衰减费率接入奖励点(原恒定GRAZE_LOW_RATE) [_run_episode体内]")
chk("def fastwin_bonus(" in tt60 and "R_FASTWIN = 6.0" in tt60
    and fn_has("train_tm.py", "_run_episode",
               "_fw = fastwin_bonus(frames - round_f0"),
    "R61: 快胜奖金接入回合胜(剩余时间比例, 速决+6) [def+常量+_run_episode体内]")
chk("def ko_round_reward(my_hp, opp_hp, win):" in tt60
    and fn_has("train_tm.py", "_run_episode", "True) * d_sl + _fw")
    and fn_has("train_tm.py", "_run_episode", "False) * d_sr"),
    "R61b: KO时双方血量差入奖励(胜margin分档+惜败半罚, 用户2026-10-05;"
    "断言锚胜/败两侧调用组合式 — 原子串被未变异侧满足=R61b变异漏网教训)")
chk("GAMMA_POT = 0.999" in tt60
    and fn_has("train_tm.py", "_run_episode",
               "GAMMA_POT * _pot - self._prev_pot"),
    "R61c(B5): 势函数γ因子(Ng式γΦ(s')−Φ(s), 原γ=1) [常量+_run_episode体内]")
chk("self._seiran_gauge" in tt60
    and "card_gauge_val=_cg" in tt60
    and "_cg = (left.get(\"cardGauge\", 0) if card_gauge_val is None" in tt60,
    "R61c(B5): cardGauge晴岚哨兵(晴岚期冻结gauge, 伪势跳±2.0防线) [多形态, 合理文本钉]")

_BEHAVIOR_TESTS = [
    # P0-3(从零#5): 看门狗必须用训练族进程树口径(树外旁路/对照臂不计入)
    ("test_cpu_family_metric_p0.py",
     "P0-3: CPU族口径(树内计入/树外排除/失败哨兵/比率clamp/整机口径退役)"),
    # P0-6(从零#5): SC标签不得覆盖复合连段终结宏(卡ID撞车实证)
    ("test_sc_label_p0.py",
     "P0-6: 裸SC宏按卡解析/复合终结宏保留身份/撞车前提实证"),
    # P1-3/14/15(从零#5): LE-1b 热度通道四重失效(不传matchup/极性反/键空间错位/上限未生效)
    ("test_le1b_inject_p1.py",
     "P1-3/14/15: LE-1b热度(池槽键+极性+20%钳+matchup传入+旧产物反查)"),
    ("test_threat.py", "P0-K: 全零速弹表→(None,0) + TTI语义"),
    ("test_opp_model.py", "P0-L: 9情境可达 + 6段占据无混叠"),
    ("test_feat_segments.py", "R16§3: 每特征段≥1非常数维"),
    # P2对账补(2026-10-14晚审计): 21个测试跨批积累未注册白名单 —
    # gru等价(复制漂移无闸)/macros_branch/bc四件/S系/JZ系全部只在
    # 手跑时绿, 门禁从不执行(与macros_branch漏注册FILES同类: 新件
    # 落地不带注册)。全量入账, 慢测试留给显式裁剪而非静默缺席。
    ("test_opp_gru_s4.py",
     "S-4预备: gru_cell与torch逐位等价(1.5e-07)+slice/replay确定性"
     " — 双实现复制漂移的唯一闸门(P2-3)"),
    ("test_gpu_equiv.py",
     "R54: ppo_gpu↔ppo numpy数值等价(1e-4)+save/load往返"),
    ("test_r17_ppo.py",
     "R17: 对手子网辅助梯度有限差分+回环"),
    ("test_macros_branch.py",
     "R4: 12宏branch四路升级(名/前缀不变/路由步归一)72项"),
    ("test_bc_match_v3.py",
     "A1-3③: v3匹配器掩码位/变长截断/镜像/SC词汇"),
    ("test_bc_align_r38.py",
     "R38: 对齐滞后映射/复检拒收"),
    ("test_bc_io.py",
     "P1: trio mmap读写/内容哈希/fleet_running fail-closed"),
    ("test_bc_roundtrip_audit.py",
     "审计#3: BC构建-消费往返一致性20项"),
    ("test_guard_refine_1e.py",
     "裁定一1e: 后退/立防按对手攻击态上下文区分"),
    ("test_danger_reveal_w2.py",
     "W2: 反事实危险显影卡(必败检出/退化作废/可复现)"),
    ("test_near_gate_f9.py",
     "R60-F9: 330门近战子集(远程弹幕放行)"),
    ("test_my_punish_s1.py",
     "S-1: MyPunishTracker类别EMA/PUNISHED语义/跨局携带"),
    ("test_style_embed_s7a.py",
     "S-7A: 16维风格嵌入(PCA投影/漂移/资源差分/卡组暴露)"),
    ("test_style_lingo_s7c.py",
     "S-7C: describe_style五轴短语+style_advice"),
    ("test_style_dim340_wiring.py",
     "P2: 维340/341接线(有语料非零/无语料归零/损坏首错响亮)"),
    ("test_frame_adv_jz2.py",
     "JZ-2: 攻击等级表驱动帧差(萃香锚+四算例+COUNTER升档)"),
    ("test_frame_events_lineB.py",
     "线B: OPP_GUARD/COMBO_DROP事件+掩码"),
    ("test_frame_events_jz3.py",
     "JZ-3.1: 正防/错防拆分+错防escape掩蔽(DD/铜钱/灵反)"),
    ("test_throw_gate_jz3.py",
     "JZ-3.2: 投技无敌窗四类+掩码门+三库throw集接线"),
    ("test_opp_jump_jz33.py",
     "JZ-3.3: E_OPP_JUMP边沿/窗21/对空反应掩码(无投技混入)"),
    ("test_jz1_prep.py",
     "JZ-1预制: 冷却分类/技能摘要/破珠/15维填充(未接线件随窗升级)"),
    ("test_decision_reset_p0.py",
     "P0(从零#4): note_decision不清局级状态(技能/B段/动量跨决策存活"
     "+reset_match才清+维230动态探针)"),
    ("test_value_curve_p1.py",
     "P1-8(从零#4): W4价值曲线reshape(-1,3,60,80)/255(2D直喂conv"
     "恒死回归)+汇总行"),
    ("test_decname_whiff_p1.py",
     "P1-4(从零#4): 门截断/confirm超时保dec_name(空挥可结算), 受击"
     "/R34中止仍豁免"),
    ("test_probe_logp_p1.py",
     "P1-5(从零#4): 探针/VG混合行为边际logp(红线①债清偿)"),
    ("test_wave_ext.py",
     "CH-3/JZ-4: 宏库扩展波(蓄力36F/系统卡sc接线/DD镜像/HJC组合"
     "/尾附索引稳定)"),
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
    # R61p(E2): 价值网络讲解
    ("test_teach_e2.py",
     "R61p(E2): value_rank排名+explain_with_value讲解+情境敏感"),
    # R61q(E3): 校准难度
    ("test_difficulty_e3.py",
     "R61q(E3): 四档难度+温度/掩码/牌组限制+阶梯+校准推荐"),
    # R61r(E5): 坏习惯检测
    ("test_habit_e5.py",
     "R61r(E5): 五种坏习惯检测+惩罚宏映射+教学报告"),
    # R61s(F6): 评估体系
    ("test_eval_f6.py",
     "R61s(F6): matchup矩阵分析+排名+超人距离度量(R63: Wilson下界/人类锚/同口径)"),
    # R61u(C1): 统一执行器+分支门
    ("test_executor_c1.py",
     "R61u(C1): 分支门评估(hit/blocked/jump/whiff/delay)+队列推进+拍子/压起身模板"),
    # R61v(C3): 目押link门
    ("test_link_c3.py",
     "R61v(C3): untech→0等待/最速出/超时截断/逐步恢复+目押宏模板"),
    # R61w(C5): ender菜单
    ("test_ender_c5.py",
     "R61w(C5): ender信号+清队+起手/菜单生成+无效过滤"),
    # R61z: 进攻积极性
    ("test_aggression_r61z.py",
     "R61z: 距离势差(engage)+空中被动惩罚+telescoping"),
    # 从零#2(方法论条款: 新模块+新调用方成对落地必附贯通测试)
    ("test_executor_integration.py",
     "从零#2: 入队载荷→执行器路由→ender拦截→决策消费全链贯通(P0-B/P1-A)"),
    # 从零#2(方法论§6-3): numpy↔GPU一步更新等价探针常驻门禁
    ("test_gpu_onestep.py",
     "从零#2: 同权重同批同种子各走一步→权重/统计/KL逐键等价(四语义差钉)"),
    # D4(主规划): 剥削者位行为测试
    ("test_exploiter_d4.py",
     "D4: exploit_前缀/滚动保留分流/胜率仪表聚合/弱点判定"),
    # C(对抗性卡组池): L1-L3逐卡加权
    ("test_deck_adversarial_c.py",
     "C: L1流派/L2必杀/L3逐SC+系统卡加权采样+归桶, 14项"),
    # B(风格估计器): 对手已出卡→风格特征段
    ("test_style_b.py",
     "B: CORE_DIMS 330+对手已出卡差分+晴岚防护+旧模型load迁移保持"),
    # R63(2026-10-07架构审查)
    ("test_mirror_axis_r63.py",
     "R63(P0-1): 镜像只翻水平轴(H翻/V不变)+高跳回归+跨实现镜像规则一致"),
    ("test_contract_r63.py",
     "R63(P0-2): episode尺寸代际契约(写者自检/读者拒收/旧代际不消费不删)"),
    # B3(F-9观察闭环): 远程弹幕使用分布报告工具
    ("test_remote_usage_b3.py",
     "B3: remote_usage_report×episode_core贯通(距离桶/弹幕份额/时间窗/坏档韧性)"),
    # R64(教训×3): train_start清理自杀修复
    ("test_trainstart_cleanup.py",
     "R64: 清理特征串'exploiter'匹配自身命令行→taskkill自杀; 排除自身PID后 命中者死/排除者活/无干者不连坐"),
    # D3'(R65): 20角色league对手生态
    ("test_league20_d3.py",
     "D3': league20_opps组成/league_alloc泛化回归/种子维度守卫幂等/build_opp_cycle池根注入+严格性"),
    # E阶段1(系列方案§3): SeriesManager
    ("test_series_stage1_e1.py",
     "E1: BO15语义(8胜早停/场数封顶/7-7决胜同拍)/系列边界/画像携带/meta字段/legacy默认"),
    # D1-2(未决方案§D): 剥削者定向对手
    ("test_exploiter_target_d12.py",
     "D1-2: --target定向(cycle=[目标])/镜像缺省兼容/specialist身份不变"),
    # D1-1(未决方案§D): league周报
    ("test_league_weekly_d11.py",
     "D1-1: league块解析(含marker同行首行)/固化指数/char聚合/末位保护线"),
    # B2(未决方案§B, 裁定③): 顶端标尺人测协议(应急路线)
    ("test_human_match_b2.py",
     "B2: 键盘轮询安全路径/VK表/协议键名/报告追加往返"),
    # B2'(裁定2026-10-12): 人测采集改道原版游戏(特化版专供训练)
    ("test_human_solo_b2.py",
     "B2': 归档/递归快照/报告条目(无游戏打桩)/mod切换逐字节往返"),
    # R75(2026-10-12全灭事故): CPU红线降容=可恢复暂停
    ("test_fleet_watchdog_r74.py",
     "R75: kill决策/窗口重置防连环杀/暂停簿记防抖/事故序列全回放/滞后带/接线锚定"),
    # I项(教学闭环产物2): 习惯→惩罚演示
    ("test_habit_demo_i.py",
     "I: 脚本循环补满/auto严重度选取/verdict双向数值(符号钉死)/模型惩罚者"),
    # W波(研究借鉴方案§W3/W4/W5)
    ("test_research_w_wave.py",
     "W3四口径/W4价值轨迹聚合+2σ/W5 exploit衰减分段与判读"),
    # W1延迟消融(研究借鉴方案§W1)
    ("test_attribution_w1.py",
     "W1: DelayedView透传/延迟/引用完整/曲线单调性验收"),
    # E阶段3前置: GRUCell
    ("test_gru_cell.py",
     "E3: GRUCell numpy↔torch等价/门控语义/序列展开/模式可分"),
    # F(未决方案§F): 吞吐标定
    ("test_throughput_f.py",
     "F: actor局/时(段切分+跨午夜)+批耗时分布+占空比(间隙阈值+尾部心跳判活)"),
    # H(未决方案§H): 纵向学习曲线
    ("test_learning_curve_h.py",
     "H: learner日志解析(批/系列/被动行)+tail斜率(平坦/上升/不足)+verdict"),
    # A1-1(未决方案§A): 被动性仪表
    ("test_passivity_a11.py",
     "A1-1: adx列feat_builder标定(符号消歧)/远弹份额分母/逼近率/开局攻击率/汇总行"),
    # CE-1(R131): 宏层punish画像
    ("test_my_punish_ce1.py",
     "CE-1: 宏层punish画像(双层独立/分层回退/慢EMA/快照过滤)"),
    # CE-4(R133): 前向头双实现
    ("test_forward_head.py",
     "CE-4: 一步位置前向头(形状/零初始化/梯度数值一致/目标提取/收敛)"),
    ("test_gpu_fwdhead_ce4.py",
     "CE-4: 前向头numpy/GPU等价+save/load往返(双实现纪律)"),
    # CE-7(R135): 推板进度势(连续角项+门控)
    ("test_ce7_pot.py",
     "CE-7: 门控默认关/on-off差值隔离/own对称/telescoping/量级2-3倍标定"),
    # CE-3.4(R136): 位置路由门
    ("test_pos_gate_ce34.py",
     "CE-3.4: pos_gate路由(贴角/版中两态同宏不同续段/外推/回落/P1-4保留名)"),
    # CE-5(R139): 反事实探针手术
    ("test_cf_probe_ce5.py",
     "CE-5: S'手术(仅改距离位逐位保真/方向规范/饱和守卫/射程块同式/入角路由)"),
    # BH-4.2(R140): untech语义门
    ("test_untech_gate_bh42.py",
     "BH-4.2: untech动作门(残留读数滤除/真受击透传/事件边沿/combo链/comboDamage入档)"),
    # BH-3.2(R141): 守备段位逐角色表
    ("test_guard_bh32.py",
     "BH-3.2: 逐角色LOW表(2B/2C虚报修正/3A分化/j2分化/空集真值/回落兼容)"),
    # BH-1(R142): 行为健康计数器
    ("test_behavior_health_bh1.py",
     "BH-1: 续打率/连段完成率/对位分解/宏转移/承诺占比记账+旁车往返"),
    # BH-4.3(R143): 对位连段先验表
    ("test_matchup_prior_bh43.py",
     "BH-4.3: 对位先验表(引文出处/昵称解码/角色宏名合法/未确认显式/消费设计)"),
    # BH-4.1(R144): matcher连段语境
    ("test_matcher_ctx_bh41.py",
     "BH-4.1: 连段语境matcher(按钮帧评分/攻击优先/中性抑制/无语境逐位兼容)"),
    # S-6(R147): BC序列感知采样
    ("test_bc_seq_s6.py",
     "S-6: shard组id/连续窗口(宁短勿跨)/保序/trio往返/旧库回落iid"),
    # LE-2(R152): fangyu警戒表深解析
    ("test_fangyu_counters_le2.py",
     "LE-2: fangyu警戒表(11角色/警戒/破防/空防不可/天气/行锚点/建议率)"),
    # LE-1a(R153): 情境库
    ("test_situation_lib_le1a.py",
     "LE-1a: 情境库(2n偏移标签派生/对位覆盖/贴角带/热度/查询语义)"),
    # 系列预测方案阶段0(R67): 系列位置分桶测量仪表
    ("test_series_meter_s0.py",
     "S0: 胜负解码(回合结算块)/系列位置/分桶/aux评分真前向50%构造/曲线行四桶"),
    # CPU-H P-A(R198): 轻载闸门空跑自测(43项) — 原漏注册(审计#6c "新测试
    # 漏注册"第3次复发) 本批补入 + 白名单对账断言永久钉死.
    ("test_load_gate.py",
     "CPU-H P-A: 轻载闸门(锁/注册表/preflight/worker cap/优先级/监控中止/"
     "协作停止/轨迹/env旁路) 43 项空跑自测"),
    ("test_pool_opp_name_map.py",
     "P1(审计#6): 池序→名映射20/20 + _side_feat 槽位/_opp_char/_jz1_ids 行为"),
    ("test_bcw_env.py",
     "D1(bcw=B1): BC_W_MIN 代码默认0.05(任意重启不带env也长期生效) + env=0回滚"),
    ("test_le0a_control_exemption.py",
     "LE-0a: 对照臂连续性 — 所有训练python WMI查询/清理逐处含 control 豁免(静态)"),
    ("test_wd_zero_reject.py",
     "H-1: wd 0.00 拒收(Δ族CPU≤0→None)+连续2次恢复门控+sidecar第3字段/审计日志"),
    ("test_gate_evidence.py",
     "task-18: 门禁证据命名gate_r<rev>_<commit7>_<ts>+O_EXCL一次写入不可复写"),
    ("test_humanmatch_detect.py",
     "task-15: 0x34C角色识别20/20+未知拒绝+活档链回退/全缺拒绝+probe只读"),
    ("test_space_feat_v1.py",
     "task-21: 空间24维/env开关382-358/归一化范围/旧前缀等价"),
    ("test_space_reward_v1.py",
     "task-21: Phase1 空间奖励 env/默认值/触发边界"),
    ("test_health_l0.py",
     "A1/A2: wd5字段/整机/旁路口径/L3告警不杀fleet/工具闸门接入"),
    ("test_behavior_deep_report.py",
     "task-16: 三表函数/JSON结构(main)"),
    ("test_rew_atk_v1.py",
     "task-20: 惩罚窗/空挥再平衡/窗口bias/成功才结算/红线①bias入stored"),
    ("test_dd_gate.py",
     "task-28: DD 仅正防门控(正/负例+env回滚)"),
    ("test_act_mask_v1.py",
     "task-29/30: 统一 mask 层(地空/不可动/DD 150-157)"),
    ("test_buffer_v1.py",
     "task-29/30 阶段1: BufferState/白名单/env=0/startup 行"),
    ("test_train_detach_v1.py",
     "task-43: train_detach 工具(dry/env/breakaway回退/日志路径)"),
    ("test_task39_v1.py",
     "task-39: 评估路径统一mask/config_error/指令技静态表/masked埋点/[mem]"),
    ("test_p1gen1_v1.py",
     "Gen-1: mem编码/ep v3 hist/迁移等价/env=0/批k4 env"),
]
# 审计#6c(2026-10-18): C15 白名单对账 — "新测试漏注册"第3次复发(21档/
# macros_branch/R198 test_load_gate 43项从未进门槛)的永久防线:
# tests/test_*.py 集合必须等于白名单集合(双向差集为空; 差集列出前6项).
_wl = set(t for t, _d in _BEHAVIOR_TESTS)
_have = set(t for t in os.listdir(os.path.join(ROOT, 'tests'))
            if t.startswith('test_') and t.endswith('.py'))
_diff = sorted(_have - _wl) + sorted(_wl - _have)
chk(not _diff, "C15白名单对账: tests/test_*.py 集合==白名单(禁漏注册/幽灵项)",
    str(_diff[:6]))
for _tname, _tdesc in _BEHAVIOR_TESTS:
    _tp = os.path.join(ROOT, 'tests', _tname)
    if not os.path.exists(_tp):
        chk(False, "行为测试存在@%s" % _tname, "文件缺失")
        continue
    _r = _sp.run([sys.executable, "-X", "utf8", _tp],
                 capture_output=True, text=True, timeout=600,
                 encoding="utf-8", errors="replace")
    if _r.returncode != 0:
        # 2026-10-18 B1: 行为测试失败时落盘**完整 stdout/stderr**(原只回末行,
        # case 级根因不可见) — 诊断用, 不改变判定。
        try:
            _lf = os.path.join(r'D:\temp',
                               'lg_fail_%s.log' % _tname[:-3])
            with open(_lf, 'w', encoding='utf8') as _fh:
                _fh.write((_r.stdout or '') + '\n--- STDERR ---\n'
                          + (_r.stderr or ''))
        except OSError:
            pass
    chk(_r.returncode == 0, "行为测试@%s" % _tname,
        ("%s | 末行: %s" % (_tdesc,
                            (_r.stdout or _r.stderr or "").strip().splitlines()[-1][:60])
         ) if _r.returncode == 0 else
        ("FAIL: %s" % ((_r.stderr or _r.stdout or "").strip().splitlines()[-1][:200])))

chk("TMTrainer._CHAR_POOL_IDX" in src("side_driver.py")
    and "{l['id']: n for n, l in CHAR_LIBS.items()}" not in src("side_driver.py"),
    "P1(审计#6): 池序→角色名映射由 _CHAR_POOL_IDX 反演(20/20, 非游戏ID)")
chk("TH123_BCW_MIN" in src("ppo_gpu.py")
    and "TH123_BCW_START" in src("ppo_gpu.py")
    and "max(self.BC_W_MIN, float(m[2]))" in src("ppo_gpu.py"),
    "D1(bcw=B1): BC权重env化(TH123_BCW_MIN/START)+load下限再挂载")
# LE-0a(2026-10-18 实弹): 对照臂连续性 — 所有"选择训练python的WMI查询"必须
# 带 th123_rl_control 豁免。事故: supervisor.reap_orphans 无豁免, 主臂重启把
# 手工launcher启动(父已退=孤儿)的对照臂连树杀掉(中断639s/游戏缺失~8.5min)。
# 逐处扫描(非串存在), 并覆盖 train_start._cleanup_ps_cmd(pre_flight/stop 共用)。
_sup_src = src("fleet_supervisor.py")
_le0a_ok = True
_le0a_seen = 0
for _m in re.finditer(r'Get-CimInstance Win32_Process', _sup_src):
    _seg = _sup_src[max(0, _m.start() - 500):_m.start() + 1500]
    if 'actor_worker|learner_hub|exploiter' not in _seg:
        continue
    _le0a_seen += 1
    if 'th123_rl_control' not in _seg:
        _le0a_ok = False
_ts_src = src("tools/train_start.py")
_i_ts = _ts_src.find('def _cleanup_ps_cmd')
_ts_seg = _ts_src[_i_ts:_i_ts + 3500] if _i_ts >= 0 else ''
_le0a_ok = (_le0a_ok and _i_ts >= 0 and 'taskkill' in _ts_seg
            and 'th123_rl_control' in _ts_seg)
chk(_le0a_ok and _le0a_seen >= 1,
    "LE-0a: 孤儿回收/前置清理查询逐处含对照臂豁免(禁误杀LE-0a)",
    "训练python查询数=%d" % _le0a_seen)
# H-1(2026-10-19 心跳实证): wd 夜内 8 次 0.00 — Δ族累计CPU≤0(CIM旧值/抖动)被
# clamp 成 0.0 入窗, 单次拉低 6 窗均值~6pp, 稀释75%红线。逐要素断言:
# 拒收条件(cur<=prev_cpu→None) + 拒收计数 + 恢复门控(_recover_need=2) +
# wd 第3字段 n_rej + 拒收审计日志。
_fs_h1 = src("fleet_supervisor.py")
chk("if cur <= prev_cpu:" in _fs_h1 and "_WD_ZERO_REJECT" in _fs_h1
    and "_recover_need = 2" in _fs_h1 and "n_rej" in _fs_h1
    and "watchdog_rejects.log" in _fs_h1,
    "H-1: wd 0.00 拒收守卫(Δ族CPU≤0→None哨兵)+连续2次恢复门控+第3字段计数")
# task-18(2026-10-19): 门禁证据产物一次写入不可复写 —
# 命名 gate_r<rev>_<commit7>_<ts> + O_EXCL 独占创建(RE 重跑不再覆盖已入账证据)。
_ge_src = src("tools/run_gate_evidence.py")
chk("def evidence_stem(" in _ge_src
    and "'gate_r%s_%s_%s'" in _ge_src
    and "O_EXCL" in _ge_src and "FileExistsError" in _ge_src,
    "task-18: 门禁证据命名含rev/commit/ts + O_EXCL一次写入(禁复写)")
# task-15(2026-10-19): 人测通路修正 — 0x34C 角色自动识别 + 活档链 +
# set_opponent(P1) 修 OOD(审计#6b 旧模型+OOD) + probe 只读。逐要素(检测偏移/
# 映射函数/活档链/注入点/probe CLI) —— 任一缺失=人测读数不可信。
_hm_src = src("tools/human_match_v2.py")
chk("CHARMGR_CHAR_IDX = 0x34C" in _hm_src
    and "CHARMGR_PLAYER_IDX = 0x350" in _hm_src
    and "def char_ids(" in _hm_src and "def map_char_id(" in _hm_src
    and "def resolve_model(" in _hm_src and "live_model_path" in _hm_src
    and "driver.set_opponent(p1c)" in _hm_src and "model_stamp" in _hm_src
    and "--probe-chars" in _hm_src and "PROBE " in _hm_src,
    "task-15: 人测通路(0x34C识别+活档链+set_opponent(P1)+probe只读)生效本体")
# task-21 v1(2026-10-19 用户批): 空间 24 维(2D 绝对+相对) + Phase1 空间奖励.
# 逐要素: env 开关/CORE_DIMS、24 维写点、归一化公式、奖励 env/默认值/调用点.
_fb21 = src("feat_builder.py")
chk("TH123_FEAT_SPACE" in _fb21
    and "CORE_DIMS = 382 if FEAT_SPACE else 358" in _fb21,
    "task-21: FEAT_SPACE env 开关(382/回滚358)")
chk("task-21 v1 空间 24 维" in _fb21
    and "if self.CORE_DIMS > self.LEGACY_CORE:" in _fb21
    and _fb21.count("s[o + 23] = float(np.clip(_ocd / 120.0, 0, 1))") == 1,
    "task-21: 24 维写点存在(0..23 全写)")
chk("s[o + 0] = float(np.clip(_my / _Y1, 0, 1))" in _fb21
    and "s[o + 9] = float(np.clip(_ad / 800.0, 0, 1))" in _fb21
    and "s[o + 20] = float(np.clip(_t2, 0, 1))" in _fb21,
    "task-21: 归一化公式(my_y/opp_dist/弹2TTI)")
_tm21 = src("train_tm.py")
chk("REW_SPACE = os.environ.get('TH123_REW_SPACE', '1') != '0'" in _tm21
    and "R_SPACE_EDGE = float(os.environ.get('TH123_REW_SPACE_EDGE'" in _tm21
    and "space_reward_step(self, left, right," in _tm21
    and "_sp_r = space_reward_step(self, left, right," in _tm21,
    "task-21: 奖励 env/默认值/调用点(space_reward_step)")
_bc21 = src("train_tm.py")
# env=1 时**允许磁盘旧宽 BC 库**(5N+358)+行级零填充, 不要求磁盘 5N+382;
# 新宽直通亦允许. 钉"旧宽分支+pad 标记+concatenate(非 np.insert)".
chk("bc_meta zero-fill v2" in _bc21 and "def _bc_pad_S(" in _bc21
    and "if S.shape[1] != self.n_side:" in _bc21
    and "self._bc_pad = (2 * _N" in _bc21
    and "Sb[:, :_ins]" in _bc21 and "np.concatenate(" in _bc21
    and "行级零填充到" in src("tools/train_start.py")
    and "行级零填充到" in src("learner_hub.py"),
    "task-21: BC env=1 允许旧宽(训练+点火+learner 三处 zero-fill v2)")
# A1/A2(CPU-H P-B/P-C, 2026-10-19 用户裁定): L0 整机/旁路口径 + wd 扩字段 +
# L3 告警(不杀 fleet) + 重型工具经闸门.
_fs12 = src("fleet_supervisor.py")
chk("def machine_cpu_pct(" in _fs12 and "def aux_cpu_pct(" in _fs12
    and "'%.3f %s %d %s %s\\n'" in _fs12,
    "A1/A2: wd 扩 `ts family n_rej machine aux`(旧读者 split()[1] 兼容)")
chk("def l3_check(" in _fs12 and "machine_alert" in _fs12
    and "heavy.stop" in _fs12 and _fs12.count("_kill_tree") >= 1,
    "A1/A2: L3 machine_alert+heavy.stop; 不杀 fleet")
_dash = src("tools/status_dashboard.py")
chk("整机" in _dash and "旁路" in _dash and "parts[3]" in _dash,
    "A1/A2: dashboard 三口径(族/整机/旁路)")
chk("def guard_tool(" in src("tools/load_gate.py")
    and "guard_tool(" in src("bc_build.py")
    and "guard_tool(" in src("tools/eval_matrix.py")
    and "guard_tool(" in src("tools/audit_all.py"),
    "A1/A2 P-C: 重型工具(bc_build/eval_matrix/audit_all)经 load_gate")
# task-16(2026-10-19): behavior_deep_report 三表工具入库(路径经 kit_config).
_bdr = src('tools/behavior_deep_report.py')
chk('def frame_tables(' in _bdr and 'def bh_table(' in _bdr
    and 'def parse_actor_games(' in _bdr
    and 'from kit_config import STORE_DIR as STORE' in _bdr,
    'task-16: behavior_deep_report 三表工具入库(kit_config 路径)')
# task-20(2026-10-19): 进攻类奖励 R-a/R-d/R-e(默认开, env 可关).
_atk = src('atk_v1.py')
_tt = src('train_tm.py')
chk('REW_ATK = os.environ.get(\'TH123_REW_ATK\', \'1\')' in _atk
    and 'def window_active(' in _atk and 'def step(' in _atk
    and 'def bias_for(' in _atk and 'def whiff_mult(' in _atk
    and 'BIAS_DECAY = int(os.environ.get(\'TH123_REW_ATK_BIAS_DECAY\', '
        '\'800\')' in _atk,
    'task-20: atk_v1 模块/env 默认(总开关+窗口/空挥/bias 函数)')
chk('import atk_v1 as _atk_v1' in _tt
    and '_atk_v1.step(' in _tt
    and '_atk_v1.bias_for(' in _tt
    and '_atk_v1.whiff_mult(' in _tt
    and 'startup_line()' in _tt,
    'task-20: train_tm 接线(逐帧step/决策bias/空挥乘子/启动打印)')
chk('r += R_PUNISH' in _atk
    and 'if in_window:' in _atk and 'return 1.0' in _atk,
    'task-20: 成功才结算(R-a)+窗口内空挥不加重(R-d)')
# task-28(2026-10-19): DD(回避结界)仅正防态可用 — 掩码门控.
_gg = src('game_gates.py')
_tt_dd = src('train_tm.py')
chk('DD_GUARD_ONLY = os.environ.get(\'TH123_DD_GUARD_ONLY\', \'1\')' in _gg
    and 'def is_guard_action(' in _gg and 'def dd_gate(' in _gg
    and 'm[i] = False' in _gg
    and '_dd_gate.apply_state_gates(' in _tt_dd,
    'task-28: DD 仅正防门控(150-167)+train_tm 接线')
# task-29/30(2026-10-20): 统一执行层 mask 层(地空/不可动/DD 150-157).
chk('def apply_state_gates(' in _gg
    and 'GUARD_STUN_LO, GUARD_STUN_HI = 150, 157' in _gg
    and 'AIR_DEF_STUN = 158' in _gg
    and 'MISGUARD_LO, MISGUARD_HI = 159, 166' in _gg
    and 'def _is_ground_only(' in _gg and "n == '待机'" in _gg,
    'task-29/30: mask 层(地空/不可动/DD收窄150-157/158·159-166 mask/空mask仅待机)')
chk('ACT_MASK = os.environ.get(\'TH123_ACT_MASK\', \'1\')' in _gg
    and 'AIR_GATE = os.environ.get(\'TH123_AIR_GATE\', \'1\')' in _gg
    and 'IMMOBILE_GATE = os.environ.get(\'TH123_IMMOBILE_GATE\', \'1\')' in _gg
    and '    if not ACT_MASK:' in _gg,
    'task-29/30: env 三开关 + env=0 逐位回滚分支')
# Gen-1(2026-10-20): 决策历史记忆 v1 + W_mem + ep v3 + 批环境.
_mv = src('mem_v1.py')
_pg = src('ppo_gpu.py')
_ep = src('episode_core.py')
_lh = src('learner_hub.py')
_aw = src('actor_worker.py')
chk('MEM_DECISIONS = int(os.environ.get(\'TH123_MEM_DECISIONS\', \'0\'))' in _mv
    and 'def hist_step(' in _mv and 'HIST_DIM = MEM_N * MEM_BYTES' in _mv
    and 'def window_hist(' in _mv
    and "_pre_env['TH123_MEM_DECISIONS'] = '0'" in src('tools/train_start.py')
    and 'window_hist(self._mem_steps)' in _tt
    and 'if (_mem_v1 is not None and _mem_v1.MEM_DECISIONS > 0):' in _tt
    and "mem_fc2'] = (rng.standard_normal" in src('tools/migrate_p1gen1.py')
    and 'H=H_full[idx_t]' in _pg and 'H=H_full[_kt]' in _pg
    and 'import mem_v1 as _mem_v1' in _tt,
    'Gen-1: mem_v1(hist编码/默认0) + train_tm 接线')
# task-29/30 阶段1: 缓冲原语(BufferState + stun 白名单并集 + env 开关)
chk('class BufferState' in src('buffer_primitives.py')
    and 'def register(' in src('buffer_primitives.py')
    and 'def resolve(' in src('buffer_primitives.py')
    and 'TH123_BUFFER' in _gg and 'BUFFER_NAMES' in _gg
    and 'BufferState(' in _tt and 'register(mid' in _tt
    and 'resolve(_buf_in_stun)' in _tt,
    'task-29/30: 缓冲原语(gate stun 白名单并集/env 开关/train_tm 登记执行)')
# task-43(task-41): train_detach 工具 + masked_choice 埋点
chk('CREATE_BREAKAWAY_FROM_JOB' in src('tools/train_detach.py')
    and 'DETACHED_PROCESS' in src('tools/train_detach.py')
    and 'breakaway 被 Job 限制' in src('tools/train_detach.py')
    and 'launch_schtasks' in src('tools/train_detach.py')
    and 'def masked_choice_line(' in _gg
    and 'def pref_on_removed_line(' in _gg
    and 'pref_removed_mass=' in _gg and 'pref_removed_top1=' in _gg
    and 'TH123_PREF_STAT' in src('side_driver.py')
    and 'note_choice(mid)' in _tt and 'note_choice(mid)' in src('side_driver.py')
    and 'note_pref(' in _tt and 'note_pref(' in src('side_driver.py'),
    'task-43b/44: train_detach(schtasks/回退告警) + masked_choice + pref_on_removed')
# task-39: 评估路径同 mask + config_error 回退 + masked 埋点 + [mem] 行
chk('_dd_gate.apply_state_gates(' in src('side_driver.py')
    and 'config_error' in src('side_driver.py')
    and '[act_mask] config_error -> gates disabled: ' in _tt
    and ('masked_line()' in _tt or 'masked_choice_line()' in _tt)
    and 'def masked_line(' in _gg
    and "'[mem] %s mem_dim=%d" in _lh,
    'task-39: 评估路径同 mask/config_error 回退/masked 埋点/[mem] 启动行')
chk('self.W_mem = nn.Linear(_MEM_OUT, n_out, bias=False)' in _pg
    and 'self.W_mem.weight.zero_()' in _pg
    and 'z = z + self.W_mem(_mo)' in _pg
    and "kw.get('hist')" in _pg,
    'Gen-1: W_mem(零初始化, 只进策略头) + update hist 入口')
chk('self.Wf1 = nn.Linear' not in _pg and 'self.Wf2 = nn.Linear' not in _pg
    and 'fwd_pred = torch.zeros((B, 4)' in _pg,
    'Gen-1: Wf1/Wf2 死重删除(fwd_pred零兼容)')
chk('EP_SCHEMA_MEM = 3' in _ep and 'hist' in _ep
    and "arrays['hist']" in _aw and 'hist=hist_all' in _lh
    and 'TH123_BATCH_MIN_GAMES' in _lh and 'TH123_K4_URGENCY' in src('feat_builder.py'),
    'Gen-1: ep schema v3 hist(写/读/补零) + 批env + k4 env')
# ============ P2波锚(审计#3十九项首波, 2026-10-13) ============
print("=== P2修复波锚(审计#3) ===")
# 审计2026-10-16 P1-1防复发: CE-1宏层画像的生产调用形态 — begin必须
# 传name=(测试曾走name=路径全绿而生产恒空, W4同型第三例)
chk("punish.begin(_dcls, name=" in src("train_tm.py")
    and "punish.begin(_dcls, name=" in src("side_driver.py"),
    "CE-1宏层画像生产接线(两调用点传name=宏名; 上线即自检制度化)")
chk("elif rs > ls" in src("tools/eval_matrix.py")
    and "elif rs > ls" in src("tools/human_match.py"),
    "P2: 平局三态(原平局记右方胜)")
chk("torch.clamp(logp_act - lpb, -20.0, 20.0)" in src("ppo_gpu.py"),
    "P2: GPU侧ratio差值±20钳制(与numpy对齐)")
chk("os.replace(_tmp, p)" in src("bc_build.py"),
    "P2: BC库savez原子落盘(宪法§5.2)")
chk('"truncated": len(traj) < frames' in src("tools/branch_demo.py"),
    "P2: branch_demo截断标记")
# ============ 审计2026-10-13根治项: 沙箱FILES完备性(AST×C15 imports) ============
print("=== FILES完备性(行为测试import面×沙箱清单) ===")
import ast as _ast
import os as _os
_gs = os.path.join(ROOT, "tools", "gate_selftest.py")
_gsrc = open(_gs, encoding="utf8").read()
_m = re.search(r"FILES = \[(.*?)\]", _gsrc, re.S)
_files_list = set(re.findall(r'"([^"]+)"', _m.group(1))) if _m else set()
_root_py = {f for f in _os.listdir(ROOT) if f.endswith(".py")}
_bad = []
for _t, _d in _BEHAVIOR_TESTS:
    _tp = os.path.join(ROOT, "tests", _t)
    if not _os.path.exists(_tp):
        continue
    try:
        _tree = _ast.parse(open(_tp, encoding="utf8").read())
    except SyntaxError:
        continue
    for _n in _ast.walk(_tree):
        _mods = []
        if isinstance(_n, _ast.Import):
            _mods = [a.name.split(".")[0] for a in _n.names]
        elif isinstance(_n, _ast.ImportFrom) and _n.module and _n.level == 0:
            _mods = [_n.module.split(".")[0]]
        for _mod in _mods:
            if _mod + ".py" in _root_py and _mod + ".py" not in _files_list:
                _bad.append((_t, _mod))
chk(not _bad,
    "沙箱FILES覆盖全部行为测试的根模块imports(P1-1类复发的结构防线)",
    str(sorted(set(_bad))[:6]))

_fs_src = src("fleet_supervisor.py")
chk(_fs_src.count("write_heartbeat()") >= 1
    and _fs_src.count("write_heartbeat(") >= 4
    and "冷却期照写心跳" in _fs_src,
    "P2: 重启冷却期心跳(防假离线账) [冷却裸调 + 周期/耗尽带alert参数化"
    "(P0-2), def+3调用=4处 — 原chk把def签名误计入裸调数, 已按实账修]")
chk("_lf.close()" in src("fleet_supervisor.py"),
    "P2: actor日志fd显式关闭(防句柄泄漏)")
chk("'actor_worker|learner_hub|exploiter'" in src("fleet_supervisor.py"),
    "P2: 孤儿回收含剥削者lane")
# ── 从零#5(2026-10-17)清偿: P0-2 路径可复现 + P0-3 看门狗口径 ──
# P0-2: PR-5 历史重写把绝对路径批量换成 %USERPROFILE% 字面量 — 即便包
# expandvars 也只在本机成立(访客克隆到别处 import/glob 全废; bc_build
# 分片 glob 字面量实测=0 → 下次重建静默产空库而 BC 是模仿梯度的唯一来源)。
# 防复发=常驻断言; 豁免: 退役归档/隔离区/自检沙箱。
_UP_HITS = []
for _r2, _ds2, _fs2 in os.walk(ROOT):
    _rel = os.path.relpath(_r2, ROOT).replace('\\', '/')
    if any(s in _rel for s in ('_archive', 'tools/quarantine', 'gate_sandbox',
                               '.git', '__pycache__')):
        continue
    for _f2 in _fs2:
        # 自检/变异台必须持有字面量原件(变异串要把它注入回去), 非生产路径
        if not _f2.endswith('.py') or _f2 in ('contract_check.py',
                                             'gate_selftest.py'):
            continue
        try:
            _s2 = io.open(os.path.join(_r2, _f2), encoding='utf8',
                          errors='replace').read()
        except OSError:
            continue
        if '%USERPROFILE%' in _s2:
            _UP_HITS.append(_f2 if _rel == '.' else '%s/%s' % (_rel, _f2))
chk(not _UP_HITS,
    "P0-2(从零#5): 活py零%USERPROFILE%字面量(路径由文件位置/kit_config派生)",
    '残留%d: %s' % (len(_UP_HITS), sorted(_UP_HITS)[:5]))
# P0-3: 看门狗口径=训练族进程树。整机处理器利用率会把旁路(ZCode会话/
# 变异sweep/BC重建)算成训练负载 → 误杀actor; 且恢复线在旁路不退时永不
# 满足 → 10-14 "降容↔恢复"震荡(32min/8次往返)的真因。
chk(fn_has("fleet_supervisor.py", "cpu_load_pct", "family_cpu_seconds")
    and "Get-CimInstance Win32_Processor" not in src("fleet_supervisor.py")
    and fn_has("fleet_supervisor.py", "family_cpu_seconds", "kids.get"),
    "P0-3(从零#5): CPU看门狗用训练族进程树口径(整机利用率口径退役)")
chk("write_watchdog_status" in src("fleet_supervisor.py")
    and "fleet_heartbeat.wd" in src("tools/status_dashboard.py"),
    "P0-3b(从零#5): 看门狗存活sidecar有写者(fleet)且有读者(仪表)")
# PR-6(2026-10-17用户裁定 D4=B): PII 防复发 — 历史事故的**类别**不得回库。
# needle 由片段拼接: 断言本体也不许含原文(否则门禁文件自己就是泄漏源)。
_PII_NEEDLES = ['阿求' + '的食堂', '国人' + '(爱丽丝)', 'Users' + '\\today']
_PII_HITS = []
for _r3, _d3, _f3s in os.walk(ROOT):
    _rel3 = os.path.relpath(_r3, ROOT).replace('\\', '/')
    if any(s in _rel3 for s in ('.git', 'gate_sandbox', '__pycache__',
                                '_archive')):
        continue
    for _f3 in _f3s:
        if not _f3.endswith(('.py', '.json', '.md', '.txt', '.bat')):
            continue
        try:
            _s3 = io.open(os.path.join(_r3, _f3), encoding='utf8',
                          errors='replace').read()
        except OSError:
            continue
        if any(n in _s3 for n in _PII_NEEDLES):
            _PII_HITS.append(_f3 if _rel3 == '.' else '%s/%s' % (_rel3, _f3))
chk(not _PII_HITS,
    "PR-6(D4=B): 库内零第三方昵称/他人机用户名(脱敏后不许回潮)",
    '残留%d: %s' % (len(_PII_HITS), sorted(_PII_HITS)[:5]))
# P1-1(从零#5): 评估工具必须读**活档**(_fleet 优先)并给报告盖模型版本戳 —
# 原一律读 model_ppo_<char>.npz(mtime 停在 10-15), 报告静默过期却无人察觉。
# 负锚: 单机旧档拼接式不得回潮(计数锚会被无害重构破坏 — 试过, 见R171)。
chk("model_ppo_%s.npz' % char" not in src("tools/eval_matrix.py")
    and "live_model_path" in src("tools/eval_matrix.py")
    and "model_stamp" in src("tools/eval_matrix.py")
    and "live_model_path" in src("tools/deck_matchup.py")
    and "live_model_path" in src("tools/attribution_probe.py"),
    "P1-1(从零#5): 评估工具读活档(_fleet优先)+报告带模型版本戳")
# P1-5(从零#5): 帧日志必须按角色子目录隔离 — 原共享目录 + glob('fl_*.pkl')
# 只留500 → 三角色互删对方日志(23文件三色交错实测), 观测面互相破坏。
chk(src("train_tm.py").count("'frame_logs', self.char") >= 2
    and "'frame_logs')" not in src("train_tm.py"),
    "P1-5(从零#5): 帧日志按角色子目录隔离(跨角色互删根治)")
# P1-4(从零#5): episode 逐决策数组必须做**行数**对账(原只比宽度) —
# 半截档(feats/sides 8行·acts/logps 4行)曾被接受、被消费、随后 os.remove。
chk(src("episode_core.py").count("check_row_counts(") >= 3,
    "P1-4(从零#5): episode行数对账(写者+读者双端, 半截档拒收)")
# P1-3/14/15(从零#5): LE-1b 热度注入通道 — 四重失效一次钉死:
# 不传 matchup(分支恒假)/极性反(h=1.0 保留0行)/heat 键 raw-id 与 mid 池槽错位/
# 20% 上限从未 clamp。assertion 用"正串在场 + 反串不在场"双向锁定。
# P1-9(从零#5): 仪表不许写死"通过"/把样本数当战绩 — 假绿比红灯更贵。
# 活性巡检行原恒为 '通过(358维, 29+8段)'(该行从不执行巡检, 维度也硬编码)。
# P2(从零#5): 两处"看不见增长/看不见数据"的清理面。
# P1-11(从零#5): ppo.py 卷积主干反传必须用 **step 前** 的 W1v。
# 原版在 vf_adam.step 之后用 self.W1v 反传价值路(旧dH1v×新W1v) — 与 torch
# 单步计算图不等价(审计实测 conv1/2/3 梯度 cos=0.396/0.637/0.564)。
# 权重范数差抓不到(Adam 首步 Δ 尺度过小), 故用源码锚 + 反串钉死。
# P1-6(从零#5): **评估侧**必须注入对手角色 — 训练侧由 train_tm 注入池序,
# 而评估工具此前从不设 → 对手 one-hot 段全零, 评估读数与训练分布不是同一输入。
chk("def set_opponent" in src("side_driver.py")
    and src("tools/eval_matrix.py").count("set_opponent(") >= 2
    and "set_opponent(" in src("tools/deck_matchup.py")
    and "set_opponent(" in src("tools/attribution_probe.py"),
    "P1-6(从零#5): 评估侧注入对手角色(A/B双方+镜像+归因)")
# P1-6(审计#6残余, 2026-10-18): 上一条只查"文件里出现过 set_opponent(" —
# attribution_probe 的 driver 注入已满足它, 于是漏掉 :69 的 opp 驱动;
# branch_demo / danger_reveal 完全未注入。收紧到**具体调用点/生效本体**
# (配对变异见 gate_selftest.py: 去掉任一注入 → 本条必红)。
chk("opp.set_opponent(char_a)" in src("tools/attribution_probe.py")
    and "opp_driver.set_opponent(args.char)" in src("tools/branch_demo.py")
    and "d.set_opponent(cfg['char'])" in src("tools/danger_reveal.py")
    and "me.set_opponent(_opp_char)" in src("tools/danger_reveal.py"),
    "P1-6(审计#6残余): 归因对手驱动/分支演示/危险显影三处注入生效本体")
# P0(2026-10-18 实弹): 对手池快照"resolve 后到 load 前被修剪"的竞态 —
# actor 报 FileNotFoundError 后驱动未装载 → 下一拍 NoneType.T 连环崩;
# R115 只覆盖"拒载→None", 未覆盖"文件消失"。修=装载失败回退生产模型。
chk("池快照装载失败" in src("train_tm.py")
    and fn_has("train_tm.py", "_rotate_opp", "live_model_path")
    and fn_has("train_tm.py", "_rotate_opp", "except OSError as _e_load"),
    "P0(2026-10-18): 池快照装载失败回退生产模型(不带空权重进局)")
# P1-13(从零#5): 低信息行降采样必须**随机**(原"取行序最前N"把保留样本
# 系统性偏置到最早的 shard/对手槽 — 在跑库 12-15% 行的移动先验被偏置)。
chk("_rng_low.choice(" in src("bc_build.py")
    and "np.where(low_mask)[0][:n_low]" not in src("bc_build.py"),
    "P1-13(从零#5): 低信息降采样随机(非取前N, 固定种子可复现)")
# P2(从零#5): 快照版本文件**损坏**必须响亮 — 原静默返回 0 而 actor 门是
# `if ver > 0` → "永久用旧权重且看起来健康"(与仪表假绿同族)。
# P1(审计#6, 2026-10-18): 原断言只查 `_VERSION_WARNED` 串 — 变异把门条件
# `if _key not in _VERSION_WARNED:` 改成 `if False:` 后, 定义(:431)/.add(:449)/
# print(:450) 文本仍在 → 变异不红(自证断言假绿)。收紧: 必须命中**门条件本体**
# (告警实际可达), 而非仅"变量名出现过"。
chk("if _key not in _VERSION_WARNED:" in src("episode_core.py")
    and "快照版本文件损坏" in src("episode_core.py")
    and "ver_corrupt" in src("actor_worker.py"),
    "P2(从零#5): 版本文件损坏=响亮(缺档仍静默0) + actor 侧计数")
# P1-2(从零#5): 20 角色矩阵里 league 种子 temp=2.0、三主模型 temp=0.5 —
# 温度/宏库差异会被读成"角色强度"。披露口径: 评估报告必须带 model_temp。
# P1(审计#6, 2026-10-18): 原断言只查 `model_temp` 串 — 变异删 :264 赋值后,
# :272 except 分支仍含同名串 → 变异不红(自证断言假绿)。收紧: 必须命中
# **try 正常路径的实际赋值**(report['model_temp'] = _temps), 仅 error 兜底不算披露。
chk("report['model_temp'] = _temps" in src("tools/eval_matrix.py")
    and "def model_meta" in src("kit_config.py"),
    "P1-2(从零#5): 评估报告披露模型温度(种子2.0/主模型0.5)")
# P1-12(从零#5): fangyu 警戒表的**叙述句伪条目** — 审计实测 71/255(28%) 是句子
# (含拉丁记号故绕过 has_latin 判定)。代码面: 虚词判据在; 数据面: 残留率 <15%。
chk("虚词判据" in src("tools/fangyu_extract.py")
    and "'的', '会', '是'" in src("tools/fangyu_extract.py"),
    "P1-12(从零#5): 警戒表叙述句过滤(长度+虚词双判据)")
try:
    import json as _json_fy
    _fy = _json_fy.load(io.open(os.path.join(
        ROOT, 'data', 'guide_tables', 'fangyu_counters.json'),
        encoding='utf8'))
    _fy_tot = 0
    _fy_bad = 0
    import re as _re_fy
    _pat_fy = _re_fy.compile(r'[，。！？；]|要注意|小心|如果|所以|对方|打不到')
    for _r in _fy.get('characters', {}).values():
        for _e in _r.get('warning_moves', []):
            _nm = _e.get('name', '')
            _fy_tot += 1
            if len(_nm) > 12 or _pat_fy.search(_nm):
                _fy_bad += 1
    _rate = (_fy_bad / _fy_tot) if _fy_tot else 1.0
    # 注: 阈值型断言**无单点变异钉**(单条 name 改成句子只动 0.5pp, 打不穿
    # 15% 门槛) — 其守卫为"生成器双判据"变异 + 重建后必须跑本断言。
    chk(_fy_tot >= 100 and _rate < 0.15,
        "P1-12(从零#5): 警戒表叙述句残留<15%(原28%)",
        '%.0f%%(%d/%d)' % (100 * _rate, _fy_bad, _fy_tot))
except (OSError, ValueError) as _e_fy:
    chk(False, "P1-12(从零#5): 警戒表可读", repr(_e_fy))
chk(fn_has("ppo.py", "update", "_W1v_pre")
    and "_W1v_pre = self.W1v.copy()" in src("ppo.py")
    and "dH1v @ self.W1v.T)[:, :TRUNK_FLAT]" not in src("ppo.py"),
    "P1-11(从零#5): numpy主干反传用step前W1v(与torch单步等价)")
chk("bh_%s_*.json" in src("learner_hub.py")
    and "len(_bhs) - 1000" in src("learner_hub.py"),
    "P2(从零#5): BH旁车保留策略有界(1000/角色, 原无清理方)")
chk("actor_%s_*.log" in src("tools/audit_all.py")
    and "_acts[:1]" in src("tools/audit_all.py"),
    "P2(从零#5): audit_all奖励面板补读actor日志(原结构性空)")
chk("通过(358维" not in src("tools/status_dashboard.py")
    and "CORE_DIMS=%d (真值)" in src("tools/status_dashboard.py"),
    "P1-9(从零#5): 仪表活性巡检不写死\"通过\"(真值+如实标注)")
chk("def raw_to_pool" in src("tools/situation_library.py")
    and "< float(h)" in src("tools/situation_library.py")
    and "< (1.0 - float(h))" not in src("tools/situation_library.py")
    and "INJECT_CAP" in src("tools/le1b_inject.py")
    and fn_has("tools/le1b_inject.py", "inject_indices", "matchup=matchup"),
    "P1-3/14/15(从零#5): LE-1b热度通道(池槽键+极性+20%钳+传matchup)")
# P0-5尾(从零#5): train_start 前置清理按**脚本名**匹配会误杀 LE-0a 对照臂
# (它跑同样的 learner_hub/actor_worker, 只是 worktree 不同) — 10-17 16:45
# 主臂重启把对照臂静默杀3h, 预注册A/B终点断流。修=按 worktree 路径判别。
chk(fn_has("tools/train_start.py", "_cleanup_ps_cmd",
           "-notmatch 'th123_rl_control'"),
    "P0-5尾(从零#5): 前置清理豁免对照臂worktree(按路径判别, 非脚本名)")
# P0-6(从零#5): SC二次解析只许作用于**裸SC宏**。复合连段终结宏
# (TM·6a终结/TM·必杀SC连/TM·空连终结)的卡ID与裸卡宏撞车, 对它们也解析
# = 正确标签被覆盖成同卡的另一个SC宏 → 三库中这三个宏 Y 恒 0(学不到)。
chk(fn_has("bc_build.py", "build_rows", "bare_sc_names")
    and "def bare_sc_names" in src("bc_build.py")
    and "_mname in _bare_sc" in src("bc_build.py"),
    "P0-6(从零#5): SC二次解析仅限裸SC宏(复合连段终结宏保留身份)")
chk("活性宽限" in src("learner_hub.py")
    and "*.tmp.npz" in src("learner_hub.py"),
    "P2: 低盘清理活性宽限+陈旧tmp清理方")
chk("系列统计解码异常" in src("learner_hub.py")
    and "被动曲线聚合异常" in src("learner_hub.py"),
    "P2: learner两处静默except响亮化(R67e同型)")
chk("分布外评估" in src("teach.py"),
    "P2: teach的V分布外评估披露")
chk("'blocks_n'" in src("tools/league_weekly.py"),
    "P2: league周报跨块聚合披露(blocks_n)")
chk("def exploit_decay" in src("tools/league_weekly.py")
    and "def four_lenses" in src("tools/eval_matrix.py"),
    "W3/W5: 四口径+exploit衰减在位(研究借鉴方案)")
chk("def value_line" in src("value_curve.py")
    and "value_recs" in src("learner_hub.py"),
    "W4: 价值轨迹模块+learner挂点(降级响亮)")

print()
print("==== 契约门禁: %d PASS / %d WARN / %d FAIL ====" %
      (len(PASSES), len(WARNS), len(FAILS)))
if FAILS:
    print("FAIL项:", ", ".join(FAILS))
    print("结论: 阻断。修完再合批/发布。")
    sys.exit(1)
print("结论: 通过(WARN不阻断)。变异覆盖见 tools/gate_selftest.py")
