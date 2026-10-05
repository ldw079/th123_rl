# -*- coding: utf-8 -*-
"""命中实验室(hitlab): 双控校准三分支信号表 — 打康/错防/(板边免校准)。
方法: VS_PLAYER双控(P1=打手脚本, P2=木桩脚本) + SET_POSITION精确摆位 +
SET_HEALTH回血 → 一局内跑完整试验矩阵, 逐帧dump原始字段。
产物: docs/hitlab_tables.md + tools/hitlab_data.json(分支执行器的查表源)

试验矩阵:
  G(守备): 攻击高度(5A中段/2A下段) × 木桩姿态(立防/蹲防) → action子ID分类+削灵
  U(受身): 攻击招 × 木桩状态(站桩/出招中) → 命中瞬间untech(普通vs被康)
R4/R5: 全部结论来自实测dump, 不从先验编表。
"""
import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from soku_client2 import GameEnded  # noqa: E402
from side_driver import EvalEnv  # noqa: E402

PORT = 20930
NEUTRAL = {"A": False, "B": False, "C": False, "D": False,
           "SC": False, "SW": False, "H": 0, "V": 0}
OP_SET_HEALTH = 13
OP_SET_POSITION = 14


def ctrl_health(inst, l, r):
    # SetHealthPacket pack(1): op(1)+ushort+ushort = 5B
    inst._send(struct.pack("<BHH", OP_SET_HEALTH, l, r))


def ctrl_pos(inst, lx, ly, rx, ry):
    # SetPositionPacket pack(1): op(1)+Vector2f(x,y)*2 = 17B
    inst._send(struct.pack("<B4f", OP_SET_POSITION, lx, ly, rx, ry))


# 木桩脚本(P2侧, 输入为绝对方向: P2的"后方"=H+1)
DUMMY = {
    "stand_guard": lambda f: {"H": 1},
    "crouch_guard": lambda f: {"H": 1, "V": -1},
    "idle": lambda f: {},
    "crouch_noguard": lambda f: {"V": -1},   # 无防纯蹲(接触判定用)
    "attack_at": lambda f0: (lambda f: {"A": True} if f >= f0 else {}),
    # 慢招靶(5C发生30F+): 我方快招命中时木桩必在发生帧内 → 被康语境
    "slow_attack_at": lambda f0: (lambda f: {"C": True} if f >= f0 else {}),
    "walk_fwd": lambda f: {"H": -1},   # 朝P1走(找被康的第二种语境)
}
# 打手脚本(P1侧)
STRIKE = {
    "5A": lambda f0: (lambda f: {"A": True} if f >= f0 else {}),
    "2A": lambda f0: (lambda f: ({"V": -1} if f >= f0 else {})
                                  | ({"A": True} if f >= f0 + 6 else {})),
    # v9终版: 预置6帧(hitlab标定阈值5, 6留余量) — 与宏库修复版一致
    "2A_long": lambda f0: (lambda f: ({"V": -1} if f >= f0 else {})
                                       | ({"A": True} if f >= f0 + 10 else {})),
    "2B": lambda f0: (lambda f: ({"V": -1} if f >= f0 else {})
                                  | ({"B": True} if f >= f0 + 5 else {})),
    "2C": lambda f0: (lambda f: ({"V": -1} if f >= f0 else {})
                                  | ({"C": True} if f >= f0 + 5 else {})),
    # v7决定性测试: 宏库原样时序(down+A同帧按) — 训练宏2A是否真出2A
    "2A_sim": lambda f0: (lambda f: {"A": True, "V": -1} if f >= f0 else {}),
    "2B_sim": lambda f0: (lambda f: {"B": True, "V": -1} if f >= f0 else {}),
    "5B": lambda f0: (lambda f: {"B": True} if f >= f0 else {}),
    # 判别实验(2026-09-23): 正确的3A斜键脚本(攻方P1朝右→前=H+1)
    "3A_diag": lambda f0: (lambda f: ({"V": -1, "H": 1} if f >= f0 else {})
                                     | ({"A": True} if f >= f0 + 8 else {})),
}


def spirit_dip(traj, lo=5, hi=45):
    """守备瞬间灵力凹陷(即时最小值, regen会回填 — 取窗口谷底而非末值)"""
    if len(traj) <= hi:
        hi = len(traj) - 1
    if hi <= lo:
        return None
    base = max(t[4] for t in traj[lo:hi])   # 窗口内高水位(回填后)
    return base - min(t[4] for t in traj[lo:hi])


def wait_idle(env, inp_l, inp_r, budget=90):
    """喂中性输入直到双方action稳定到idle(0)或预算耗尽。"""
    for _ in range(budget):
        try:
            env.step(inp_l, inp_r)
        except Exception:
            return False
        lm = getattr(env, "last_match", None)
        if lm:
            env.last_match = None
            return False
    return True


def sync_idle(env, want_lx, want_rx, budget=240):
    """摆位后等双方回到可控状态: action=idle且位置贴合请求值(±8)。
    每40帧重发SET_POSITION(击退漂移/起身走位会脱离一次设位的值)。"""
    ok_frames = 0
    for i in range(budget):
        if i % 40 == 0:
            ctrl_health(env.inst, 10000, 10000)
            ctrl_pos(env.inst, want_lx, 0.0, want_rx, 0.0)
        try:
            r = env.step(dict(NEUTRAL), dict(NEUTRAL))
        except Exception:
            return False
        if r is None:
            return False
        left, right = r[0], r[1]
        if (left["action"] == 0 and right["action"] == 0
                and abs(left["position.x"] - want_lx) <= 8
                and abs(right["position.x"] - want_rx) <= 8):
            ok_frames += 1
            if ok_frames >= 5:
                return True
        else:
            ok_frames = 0
    return False


def run_trial(env, strike, strike_f0, dummy, gap=100):
    """一次试验: 摆位同步 → 执行脚本 → 逐帧采集。返回(轨迹, synced)。"""
    lx, rx = 480.0, 480.0 + gap
    synced = sync_idle(env, lx, rx)
    traj = []
    for f in range(80):
        il = strike(f)
        ir = dummy(f)
        try:
            r = env.step(il or {}, ir or {})
        except Exception:
            break
        if r is None:
            break
        left, right, _w, _o = r
        traj.append((f, left["action"], right["action"], right["hp"],
                     right["spirit"], right["untech"], right["hitStop"],
                     left["position.x"], right["position.x"],
                     left["spirit"], right["comboDamage"],
                     right["comboLimit"], len(_o)))
    return traj, synced


def impact_frames(traj):
    """hp下降帧序号"""
    out = []
    for i in range(1, len(traj)):
        if traj[i][3] < traj[i - 1][3]:
            out.append(i)
    return out


def main():
    env = EvalEnv(PORT, char_left="reimu", char_right="reimu",
                  vs_com=False, tps=None)
    # 开局排干intro(角色入场动画期间不可控)
    for _ in range(240):
        try:
            if env.step(dict(NEUTRAL), dict(NEUTRAL)) is None:
                break
        except Exception:
            break
    # D16(从零审查): --sweep模式 — 阈值曲线复现扫描落盘json
    if "--sweep" in sys.argv:
        print("== 预置阈值扫描(D16复现模式) ==")
        sv = sweep_presteps(env)
        out = os.path.join(HERE, "hitlab_data.json")
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"prestep_sweep": {str(k): v for k, v in sv.items()},
                       "meta": {"date": time.strftime("%Y-%m-%d %H:%M"),
                                "char": "reimu", "gap": 70}},
                      fh, ensure_ascii=False, indent=1)
        os.replace(tmp, out)
        print("sweep数据已存:", out)
        try:
            env.close()
        except Exception:
            pass
        return 0
    # 判别实验(2026-09-23撤回重立): 2A命中异常 — 攻击方hitStop峰值为
    # 接触信号(被防也有hitstop, 与hp无关), 5A为阳性对照验证仪器本身
    if "--diag2a" in sys.argv:
        print("== 判别实验第二轮: 灵梦2A(用户确认=真攻击) ==")
        # 上游编码已核对一致(Input位域+(-1)&3); 位域排除 → 测输入形态/侧/对空
        def tap_a(f0):
            def s(f):
                d = {"V": -1} if f >= f0 else {}
                if f0 + 6 <= f < f0 + 9:   # A只按3帧(点按)
                    d["A"] = True
                return d
            return s
        DUMMY_JUMP = lambda f: {"V": 1} if f >= 0 else {}
        tests = [
            ("2A长按(基线)", STRIKE["2A"](3), DUMMY["idle"], 60),
            ("2A点按A", tap_a(3), DUMMY["idle"], 60),
            ("2A长按vs跳跃木桩", STRIKE["2A"](3), DUMMY_JUMP, 60),
            ("2A长按gap30", STRIKE["2A"](3), DUMMY["idle"], 30),
        ]
        for label, strike, dum, g in tests:
            traj, s = run_trial(env, strike, 3, dum, gap=g)
            hs = max((t[6] for t in traj), default=0)
            nh = len(impact_frames(traj))
            print("  %s gap%d: hitStop峰=%d hp降=%d l_act=%s r_act尾=%s"
                  % (label, g, hs, nh,
                     sorted({t[1] for t in traj if t[1]})[:5],
                     [t[2] for t in traj[-8:]]))
        # 镜像测试: 右侧(P2)当攻击方打左侧站桩 — 排除P1侧混淆
        # (直接反转角色: 左=木桩, 右=打手; P2的"下"仍V=-1绝对向下)
        for g in (40, 70):
            traj = []
            ctrl_health(env.inst, 10000, 10000)
            ctrl_pos(env.inst, 480.0, 0.0, 480.0 + g, 0.0)
            for _ in range(20):
                try:
                    env.step(dict(NEUTRAL), dict(NEUTRAL))
                except Exception:
                    pass
            for f in range(80):
                il = {}
                ir = ({"V": -1} if f >= 3 else {}) \
                    | ({"A": True} if f >= 9 else {})
                try:
                    r = env.step(il, ir)
                except Exception:
                    break
                if r is None:
                    break
                left, right = r[0], r[1]
                traj.append((f, left["action"], right["action"],
                             left["hp"], right["hp"], left["hitStop"],
                             right["hitStop"], left["position.x"],
                             right["position.x"]))
            lhp = [t[0] for i in range(1, len(traj))
                   if traj[i][3] < traj[i - 1][3]]
            lhs = max((t[5] for t in traj), default=0)
            print("  镜像P2攻击 gap%d: 左受击hp降=%d 左hitStop峰=%d "
                  "r_act(P2攻方)=%s l_act(木桩)=%s"
                  % (g, len(lhp), lhs,
                     sorted({t[2] for t in traj if t[2]})[:5],
                     sorted({t[1] for t in traj if t[1]})[:5]))
        # 第三轮: 蹲姿目标 + 跨角色对照 — 判定框存在性
        for g in (40, 60, 90):
            traj, s = run_trial(env, STRIKE["2A"](3), 3,
                                DUMMY["crouch_noguard"], gap=g)
            hs = max((t[6] for t in traj), default=0)
            nh = len(impact_frames(traj))
            print("  2A vs 蹲姿无防 gap%d: hitStop峰=%d hp降=%d l_act=%s r_act集=%s"
                  % (g, hs, nh, sorted({t[1] for t in traj if t[1]})[:5],
                     sorted({t[2] for t in traj if t[2]})))
        envm = EvalEnv(PORT + 1, char_left="marisa", char_right="marisa",
                       vs_com=False, tps=None)
        try:
            for _ in range(240):
                try:
                    if envm.step(dict(NEUTRAL), dict(NEUTRAL)) is None:
                        break
                except Exception:
                    break
            for g in (60, 90):
                traj, s = run_trial(envm, STRIKE["2A"](3), 3,
                                    DUMMY["idle"], gap=g)
                hs = max((t[6] for t in traj), default=0)
                nh = len(impact_frames(traj))
                print("  [跨角色]marisa 2A vs idle gap%d: hitStop峰=%d hp降=%d "
                      "l_act=%s" % (g, hs, nh,
                                    sorted({t[1] for t in traj if t[1]})[:5]))
        finally:
            try:
                envm.close()
            except Exception:
                pass
        try:
            env.close()
        except Exception:
            pass
        return 0
    GAP = {"5A": 100, "5B": 100}
    # 焦点试验0(v8): 修复版2A(预置4帧)出招验证 + 出招则直接抓错防ID
    for label in ("2A",):
        traj, s = run_trial(env, STRIKE[label](3), 3, DUMMY["idle"], gap=70)
        hits = impact_frames(traj)
        atk = sorted({t[1] for t in traj if t[1] not in (0, 6)})[:4]
        print("  %s(6帧终版)→idle gap70 sync=%s hp降=%d 攻击l_act=%s" % (
            label, s, len(hits), atk))
        if atk:
            GAP["2A"] = 70
    if "2A" in GAP:
        # 错防狩猎: 2A(下段) vs 立防 → 防御崩坏应有独立action ID(立防正防=151)
        for g in (40, 55, 70):
            traj, s = run_trial(env, STRIKE["2A"](3), 3,
                                DUMMY["stand_guard"], gap=g)
            trace = [t[2] for t in traj[5:40] if t[2] != 0]
            hits = impact_frames(traj)
            print("  [错防狩猎] 2A vs 立防 gap%d: r_act轨迹=%s hp降=%d" % (
                g, trace[:16], len(hits)))
            if len(set(trace)) > 1 or hits:
                break
    # 焦点试验1: 5A打无防蹲姿(蹲受击ID) + 2A可执行则对守备
    for label, strike, gap in (
            ("5A→蹲姿无防", STRIKE["5A"](3), 100),):
        traj, s = run_trial(env, strike, 3,
                            DUMMY["crouch_noguard"]
                            if "蹲" in label else DUMMY["idle"], gap=gap)
        hits = impact_frames(traj)
        print("  %s gap=%d sync=%s hp降=%d l_act=%s 命中后r_act=%s" % (
            label, gap, s, len(hits),
            sorted({t[1] for t in traj if t[1] != 0})[:5],
            [t[2] for t in traj[hits[0]:hits[0] + 6]] if hits else "-"))
    # 2A距离扫描(修复版): 对守备木桩直到接触
    if "2A" not in GAP:
        for g in (40, 50, 60, 80):
            traj, s = run_trial(env, STRIKE["2A"](8), 8,
                                DUMMY["stand_guard"], gap=g)
            contact = bool(impact_frames(traj)) or any(
                t[2] not in (0, 5, 8) for t in traj[10:40])
            print("  2A gap=%d sync=%s 接触=%s r_act=%s" % (
                g, s, contact, sorted({t[2] for t in traj[10:40] if t[2]})))
            if contact or impact_frames(traj):
                GAP["2A"] = g
                break
        if "2A" not in GAP:
            print("  2A全距离未接触 — G组2A格跳过")
    data = {"guard": [], "untech": [], "focus": [], "meta": {
        "date": time.strftime("%Y-%m-%d %H:%M"), "gap": GAP}}
    print("== G组: 守备分类(高度×姿态) ==")
    for mv_name, height in (("5A", "mid"), ("2A", "low")):
        if mv_name not in GAP:
            continue
        for stance in ("stand_guard", "crouch_guard"):
            for attempt in range(3):
                traj, synced = run_trial(env, STRIKE[mv_name](8), 8,
                                         DUMMY[stance], gap=GAP[mv_name])
                trace = [t[2] for t in traj[5:40] if t[2] != 0]
                acts_all = sorted(set(trace))
                hits = impact_frames(traj)
                if len(acts_all) > 1 or hits:
                    break
            spirit_d = spirit_dip(traj)
            rec = {"move": mv_name, "height": height, "stance": stance,
                   "synced": synced, "r_act_all": acts_all,
                   "r_act_trace": trace[:24],
                   "spirit_dip": spirit_d, "hp_drops": len(hits)}
            data["guard"].append(rec)
            print("  %s(%s) vs %s [sync=%s]: r_act=%s 轨迹=%s hp降=%d" % (
                mv_name, height, stance, synced, acts_all, trace[:16],
                len(hits)))
    print("== U组: untech基准+受击轨迹(普通vs被康[慢招靶法]) ==")
    # 被康判据第二轮: v4/v5实证untech/伤害不变 — 本轮加受击后r_act轨迹
    # 与comboLimit对比(康特受击动画/修正可能不同)
    for mv_name in ("5A", "2A", "5B"):
        if mv_name not in GAP:
            continue
        for dum_name, dspec in (
                ("idle", lambda f: {}),
                ("attacking", DUMMY["slow_attack_at"](2))):
            got = None
            for attempt in range(3):
                traj, synced = run_trial(env, STRIKE[mv_name](3), 3,
                                         dspec, gap=GAP[mv_name])
                hits = impact_frames(traj)
                if hits:
                    got = (traj, hits, synced)
                    break
            if not got:
                data["untech"].append({"move": mv_name, "dummy": dum_name,
                                       "note": "no-impact×3",
                                       "l_acts": sorted({t[1] for t in traj
                                                         if t[1] != 0})[:6]})
                print("  %s vs %s: 未命中×3 (l_act=%s)" % (
                    mv_name, dum_name,
                    sorted({t[1] for t in traj if t[1] != 0})[:6]))
                continue
            traj, hits, synced = got
            h = hits[0]
            ut = max(traj[h][5], traj[h + 1][5] if h + 1 < len(traj) else 0)
            post = [t[2] for t in traj[h:h + 20] if t[2] != 0]
            # CH对象检查: 命中瞬间场上对象数(康特特效可能生成对象)
            objs_n = [t[12] for t in traj[max(0, h - 2):h + 6]] \
                if len(traj[h]) > 12 else None
            hs = [t[6] for t in traj[max(0, h - 2):h + 6]]
            rec = {"move": mv_name, "dummy": dum_name, "synced": synced,
                   "untech_at_impact": traj[h][5], "untech_max2": ut,
                   "r_act_at_impact": traj[h - 1][2] if h else None,
                   "post_hitstun_trace": post[:16],
                   "r_combo_limit": traj[h][11] if len(traj[h]) > 11 else None,
                   "objs_around": objs_n, "hitstop_around": hs,
                   "dmg": traj[h - 1][3] - traj[h][3]}
            data["untech"].append(rec)
            print("  %s vs %s [sync=%s]: untech=%s 伤害=%s 对象数=%s hitstop=%s\n"
                  "      受击后轨迹=%s" % (
                      mv_name, dum_name, synced, rec["untech_at_impact"],
                      rec["dmg"], objs_n, hs, post[:12]))
    try:
        env.close()
    except Exception:
        pass
    out = os.path.join(HERE, "hitlab_data.json")
    tmp = out + ".tmp"
    data["meta"]["char"] = "reimu"
    data["meta"]["attacker_acts"] = {"5A": 300, "2A": 309, "2B": 404,
                                     "5C": 410, "2C": 414}   # 控制台l_act实测
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, out)   # 第六轮审计§6-7: 原子写
    print("数据已存:", out)
    # ---- 错防狩猎(hitlab第三轮): 魔理沙3A(下段Rift) vs 立防 ----
    if "--wrongblock" in sys.argv:
        print("== 错防狩猎: marisa 3A(下段Rift) vs 立防 ==")
        env2 = EvalEnv(PORT + 1, char_left="marisa", char_right="marisa",
                       vs_com=False, tps=None)
        try:
            for _ in range(240):
                try:
                    if env2.step(dict(NEUTRAL), dict(NEUTRAL)) is None:
                        break
                except Exception:
                    break
            m3a = (lambda f: ({"V": -1} if f >= 3 else {})
                   | ({"A": True} if f >= 14 else {}))  # 3A=下右斜(近似下)
            for g in (90, 110, 130):
                traj, s = run_trial(env2, m3a, 3, DUMMY["stand_guard"], gap=g)
                trace = [t[2] for t in traj[5:50] if t[2] != 0]
                hits = impact_frames(traj)
                print("  3A vs 立防 gap%d sync=%s: r_act轨迹=%s hp降=%d"
                      % (g, s, trace[:18], len(hits)))
                if len(set(trace)) > 1 or hits:
                    break
        finally:
            try:
                env2.close()
            except Exception:
                pass
    return 0




def sweep_presteps(env):
    """阈值复现扫描(第六轮审计§6-2): 预置0/3/4/5/6/8帧 → 出招与否"""
    res = {}
    for off in (0, 3, 4, 5, 6, 8):
        def strike(f, o=off):
            d = {"V": -1} if f >= 3 else {}
            if f >= 3 + o:
                d["A"] = True
            return d
        traj, s = run_trial(env, strike, 3, DUMMY["idle"], gap=70)
        atk = sorted({t[1] for t in traj if t[1] not in (0, 6)})[:3]
        res[off] = {"attack_actions": atk, "executed": bool(atk)}
        print("  预置%d帧: 出招=%s %s" % (off, bool(atk), atk))
    return res

if __name__ == "__main__":
    sys.exit(main())
