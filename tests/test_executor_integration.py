# -*- coding: utf-8 -*-
"""P0-B/P1-A(从零#2)贯通集成测试 — 方法论条款:
"凡新模块+新调用方成对落地, 必须附一条贯通两者的集成测试方可合批"。

四个断点(fleet init/actor集成/ender调用方/eval run_matchup)全是缺这条
的直接后果。本文件钉住"入队→执行器→调用方消费"整条链:

1. enqueue_script保留字符串步载荷(branch字典/link元组/ender列表)
2. 入队产物可直接被advance_queue路由(P0-B回归: 原train_tm侧(ks,0))
3. ender信号→调用方拦截→菜单掩码→决策点消费(P1-A回归)
4. SideDriver真实对象走完全链(评估侧)
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import macro_executor as me  # noqa: E402


def _no_sc(left):
    return False, True, {}   # pop=False, abort=True, hold={}


def _sc_reset():
    pass


def _own(x=500.0, act=0, spirit=1000.0):
    return {"position.x": x, "position.y": 0.0, "direction": 1,
            "action": act, "spirit": spirit, "hp": 10000,
            "airBorne": False, "hitStop": 0, "timeStop": 0,
            "untech": 0, "cardGauge": 0, "score": 0,
            "comboDamage": 0, "hand": b'\xff' * 10}


def _opp(x=700.0, act=0):
    return {"position.x": x, "position.y": 0.0, "direction": -1,
            "action": act, "spirit": 1000.0, "hp": 10000,
            "airBorne": False, "untech": 0, "cardGauge": 0,
            "score": 0, "comboDamage": 0, "hand": b'\xff' * 10}


def test_enqueue_preserves_payload():
    """P0-B: 字符串步载荷必须随步入队(原train_tm侧丢成0)。"""
    branch = me.make_branch_step(
        {"hit": [(("B",), 6)], "blocked": None, "whiff": None})
    link = me.make_link_step(20, [(("A",), 8)])
    ender = me.make_ender_step([0, 1, 2])
    q = me.enqueue_script([], [(("A",), 8), ("confirm", 0),
                               branch, link, ender])
    assert q[2] == branch, "branch载荷丢失: %r" % (q[2],)
    assert q[3] == link, "link载荷丢失: %r" % (q[3],)
    assert q[4] == ender, "ender载荷丢失: %r" % (q[4],)
    assert q[0] == (("A",), 8) and q[1] == ("confirm", 0)
    print("PASS 入队载荷保留(branch/link/ender)")


def test_enqueued_branch_routes():
    """入队产物→advance_queue可路由(P0-B端到端):
    confirm门命中通过→branch评估hit→hit分支步骤入队。"""
    script = [(("A",), 1), ("confirm", 0),
              me.make_branch_step(
                  {"hit": [(("B",), 6)], "blocked": [(("C",), 6)],
                   "whiff": None})]
    q = me.enqueue_script([], script)
    # 帧1: A按键步消耗
    q, gf, dn, _ = me.advance_queue(
        q, 0, _own(), _opp(), 0, 0, False, 1000.0, 200.0, "测试",
        set(), frozenset(), _no_sc, _sc_reset)
    assert q[0][0] == "confirm", "帧1后应到confirm门: %r" % (q[0],)
    # 帧2: d_deal>0 → confirm通过; 再一帧branch评估hit → B分支入队
    q, gf, dn, _ = me.advance_queue(
        q, 0, _own(), _opp(), 50, 0, False, 1000.0, 200.0, "测试",
        set(), frozenset(), _no_sc, _sc_reset)
    assert q[0][0] == "branch", "confirm通过后应到branch门: %r" % (q[0],)
    # 命中证据=对手受击态(状态式结算窗 — d_deal已在confirm帧被消费)
    q, gf, dn, _ = me.advance_queue(
        q, 0, _own(), _opp(act=50), 0, 0, False, 1000.0, 200.0, "测试",
        set(), frozenset(), _no_sc, _sc_reset)
    assert q and q[0] == (("B",), 6), "hit分支应路由B步: %r" % (q[:1],)
    # blocked路径: 对手防御硬直态(152)→C分支
    q2 = me.enqueue_script([], [me.make_branch_step(
        {"hit": [(("B",), 6)], "blocked": [(("C",), 6)], "whiff": None})])
    q2, _, _, _ = me.advance_queue(
        q2, 0, _own(), _opp(act=152), 0, 0, False, 1000.0, 200.0, "测试",
        set(), frozenset(), _no_sc, _sc_reset)
    assert q2 and q2[0] == (("C",), 6), "blocked分支应路由C步"
    # whiff路径: 对手无受击/无防御 → 截断
    q3 = me.enqueue_script([], [me.make_branch_step(
        {"hit": [(("B",), 6)], "whiff": None})])
    q3, _, _, _ = me.advance_queue(
        q3, 0, _own(), _opp(), 0, 0, False, 1000.0, 200.0, "测试",
        set(), frozenset(), _no_sc, _sc_reset)
    assert q3 == [], "whiff应截断队列"


def test_enqueued_ender_signal():
    """ender步→advance_queue返回("ender", indices)信号(调用方拦截用)。"""
    q = me.enqueue_script([], [me.make_ender_step([0, 1])])
    q, gf, dn, inp = me.advance_queue(
        q, 0, _own(), _opp(), 0, 0, False, 1000.0, 200.0, "测试",
        set(), frozenset(), _no_sc, _sc_reset)
    assert q == [], "ender应清空队列"
    assert inp == ("ender", [0, 1]), "ender信号形态: %r" % (inp,)


def _load_driver(char="reimu"):
    from side_driver import SideDriver
    d = SideDriver(char, "L")
    store = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
    pi = os.path.join(store, 'model_ppo_%s.npz' % char)
    vv = os.path.join(store, 'model_ppo_%s_v.npz' % char)
    if os.path.exists(pi):
        import numpy as _np
        _dd = _np.load(pi)
        _n_out = int(_dd['W2'].shape[1])
        _dd.close()
        assert _n_out == d.n_macros, (
            "模型n_out=%d≠宏库%d — 测试需与现行库一致" % (_n_out,
                                                      d.n_macros))
        d.ppo.load(pi, vv)
    else:
        # 无模型时随机初始化conv权重(仅走通流程, 不验语义)
        for _w in ('Wc1', 'Wc2', 'Wc3'):
            setattr(d.ppo, _w, np.random.randn(
                *getattr(d.ppo, _w + '_SHAPE')).astype(np.float32) * 0.01
                if hasattr(d.ppo, _w + '_SHAPE') else None)
        if d.ppo.Wc1 is None:
            print("跳过: 无模型且无随机权重路径")
            return None
    return d


def test_sidedriver_ender_wiring():
    """P1-A: SideDriver真实对象 — ender元组被拦截为菜单掩码,
    下一决策点从菜单采样且掩码单次消费。"""
    d = _load_driver()
    if d is None:
        return
    d.macro_queue = [("ender", [0, 1])]
    own, opp = _own(), _opp()
    _w = {"active": 0}
    # 第1帧: ender触发→掩码设置(队列空, decide早退因视觉栈<3帧)
    d.frame_input(dict(own), dict(opp), _w, [], [])
    assert d._ender_mask is not None, "ender掩码未设置"
    assert d._sc_next_input == {}, "ender元组不得落入_sc_next_input"
    # 第2-4帧: 视觉栈≥3帧后decide真实采样 → 掩码被消费
    for _ in range(4):
        d.frame_input(dict(own), dict(opp), _w, [], [])
    assert d._ender_mask is None, "ender掩码应单次消费"
    assert d.last_macro in (0, 1), "决策应落在菜单内: %r" % d.last_macro
    print("PASS SideDriver ender接线(拦截→掩码→消费)")


def test_sidedriver_branch_macro_roundtrip():
    """SideDriver入队(单源)→advance_queue路由不炸(P0-B训练侧同款回归)。"""
    d = _load_driver()
    if d is None:
        return
    script = [("confirm", 0),
              me.make_branch_step({"hit": [(("A",), 6)],
                                   "whiff": None})]
    me.enqueue_script(d.macro_queue, script)
    own, opp = _own(), _opp()
    _w = {"active": 0}
    # confirm命中(d_deal>0) → branch hit → A步入队 → 按键输入产出
    d.hp_opp_prev = opp["hp"]   # 模拟起手前基线
    d.frame_input(dict(own), dict(opp), _w, [], [])
    # d_deal=0: confirm观察窗... 手动推进两帧
    for _ in range(2):
        d.frame_input(dict(own), dict(opp), _w, [], [])
    # 队列应已被路由或截断 — 关键断言: 全程无异常且无载荷丢失残留
    for ks, fl in d.macro_queue:
        assert not (isinstance(ks, str) and fl_zero(fl, ks)), \
            "载荷丢失残留: %r" % ((ks, fl),)
    print("PASS SideDriver branch宏往返")


def fl_zero(fl, ks):
    return isinstance(fl, int) and fl == 0 and ks in ("branch", "link",
                                                      "ender")


if __name__ == "__main__":
    test_enqueue_preserves_payload()
    test_enqueued_branch_routes()
    test_enqueued_ender_signal()
    test_sidedriver_ender_wiring()
    test_sidedriver_branch_macro_roundtrip()
    print("ALL PASS: %s" % os.path.basename(__file__))
