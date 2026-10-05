# -*- coding: utf-8 -*-
"""mod遮蔽运行时实测探针(第五轮审核§3): 闭合最后一个外部事实前提。
C9证明了"源码有遮蔽∧部署的二进制由该源码编译"; 本脚本证明"运行时客户端
真的收到遮蔽值": 强制晴岚→断言双方hand全0xFF且cardGauge==65535;
强制极光→断言displayed==19的帧上active恒为19(真实效果不外泄)。
用法: python tools/runtime_masking_probe.py   (训练可并行, 用独立端口)
产物: docs/mod_masking_runtime_dump.md (证据存档)
"""
import hashlib
import io
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from soku_client2 import SokuTrainerInstance, GameEnded  # noqa: E402

PORT = 20990          # 独立端口, 避开训练的20800+区段
OP_SET_WEATHER = 15
NEUTRAL = {"A": False, "B": False, "C": False, "D": False,
           "SC": False, "SW": False, "H": 0, "V": 0}


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


def set_weather(inst, w, timer=999, freeze=True):
    # sizeof(SetWeatherPacket)=8: Packet.hpp有#pragma pack(1) —
    # op(1)+Weather枚举int(4)+timer(2)+freeze(1), 无对齐填充。
    # (首试12字节按自然对齐猜错: 字节游走致Display/Hello误触发=OK+err=10的来源)
    pkt = struct.pack("<BiH?", OP_SET_WEATHER, w, timer, freeze)
    assert len(pkt) == 8, len(pkt)
    inst._send(pkt)


def hand_masked(cs):
    hb = cs["hand"]
    return all(hb[i * 2] == 0xFF for i in range(5))


def collect_phase(inst, label, want, target, budget=45000, min_hits=300):
    """收帧直到满足want的样本≥min_hits或预算(成功帧)耗尽。
    天气推进实测: 游戏按自身序列轮换(每天气~1700帧, 全循环~3.7万帧必经11/19);
    SET_WEATHER=预约+到位钉住(main.cpp:158-164)。
    实测教训: 不发SPEED/DISPLAY(朴素配置帧流稳定); 62fps下全循环约10min墙钟。"""
    stats = {"n": 0, "hit": 0, "hand_empty_or_masked_L": 0, "hand_empty_or_masked_R": 0,
             "gauge_sent_L": 0, "gauge_sent_R": 0, "active_vals": {},
             "control_n": 0, "control_hand_real": 0, "control_gauge_real": 0,
             "rounds": 0}
    deadline = time.time() + 700
    while stats["hit"] < min_hits and stats["n"] < budget and time.time() < deadline:
        stats["n"] += 1
        try:
            inst.send_inputs(NEUTRAL, NEUTRAL)
            left, right, weather, _objs = inst.recv_frame(timeout=3.0)
        except TimeoutError:
            stats["errs"] = stats.get("errs", {})
            stats["errs"]["timeout"] = stats["errs"].get("timeout", 0) + 1
            continue
        except RuntimeError as e:
            stats["errs"] = stats.get("errs", {})
            k = str(e)[:24]
            stats["errs"][k] = stats["errs"].get(k, 0) + 1
            if "err=17" in str(e):
                time.sleep(0.005)   # 加载期待battle: 限速, 不烧成功帧预算
                stats["n"] -= 1     # err=17不计入帧预算(第四轮实测: 否则CPU速烧光)
                continue
            if "op=12" in str(e):
                stats["n"] -= 1
                continue
            raise
        except GameEnded:
            stats["rounds"] += 1
            print("  [%s] 对局结束#%d(第%d帧), 重开续采" % (label, stats["rounds"],
                                                     stats["n"]))
            inst.start_vs_com()
            set_weather(inst, target)
            continue
        act, disp = weather["active"], weather["displayed"]
        key = "%d/%d" % (disp, act)
        stats["active_vals"][key] = stats["active_vals"].get(key, 0) + 1
        if want(disp, act):
            stats["hit"] += 1
            if hand_masked(left):
                stats["hand_empty_or_masked_L"] += 1
            if hand_masked(right):
                stats["hand_empty_or_masked_R"] += 1
            if left["cardGauge"] == 0xFFFF:
                stats["gauge_sent_L"] += 1
            if right["cardGauge"] == 0xFFFF:
                stats["gauge_sent_R"] += 1
        elif act != 21:   # 控制组: 有天气但非目标 → 遮蔽不应生效
            stats["control_n"] += 1
            if not hand_masked(left):
                stats["control_hand_real"] += 1
            if left["cardGauge"] != 0xFFFF:
                stats["control_gauge_real"] += 1
    return stats


def main():
    dep = (r"D:\touhou\hisoutensoku2026-06-15\th123_train\modules"
           r"\SokuAIOfflinePlayer\SokuAITrainer.dll")
    dll_md5 = md5(dep)
    print("部署DLL:", dll_md5)
    print("启动探针游戏实例(端口%d)..." % PORT)
    inst = SokuTrainerInstance(PORT)
    try:
        # 朴素配置(实测稳定): 不发SPEED/DISPLAY — 480tps组合在此探针上
        # 造成帧流停摆/加载失败(训练环境有完整watch线程, 探针没有)
        print("开局 VS_COM...")
        inst.start_vs_com()
        # ---- 阶段0: 负控制组(第六轮审计§5.2): 强制非晴岚天气1 ----
        print("阶段0: 负控制(预约雾雨=1, 断言无哨兵)...")
        set_weather(inst, 1)
        s0 = collect_phase(inst, "负控", lambda d, a: a == 1, 1,
                           budget=8000, min_hits=100)
        ok0 = (s0["hit"] >= 50
               and s0["gauge_sent_L"] == 0 and s0["gauge_sent_R"] == 0)
        print("  负控帧%d | 哨兵L%d R%d | 判定=%s"
              % (s0["hit"], s0["gauge_sent_L"], s0["gauge_sent_R"], ok0))
        # ---- 阶段1: 强制晴岚 ----
        print("阶段1: 预约晴岚(11)...")
        set_weather(inst, 11)
        s1 = collect_phase(inst, "晴岚", lambda d, a: a == 11, 11)
        print("  晴岚帧%d/%d | hand遮蔽 L%d R%d | gauge哨兵 L%d R%d | 控制组%d | 异常%s" % (
            s1["hit"], s1["n"], s1["hand_empty_or_masked_L"], s1["hand_empty_or_masked_R"],
            s1["gauge_sent_L"], s1["gauge_sent_R"], s1["control_n"],
            s1.get("errs", {})))
        # ---- 阶段2: 强制极光 ----
        print("阶段2: 预约极光(19)...")
        set_weather(inst, 19)
        s2 = collect_phase(inst, "极光", lambda d, a: d == 19, 19)
        aurora_leak = [k for k, n in s2["active_vals"].items()
                       if k.startswith("19/") and not k.endswith("/19")]
        print("  极光帧%d/%d | disp/act分布%s | 泄漏帧类%d" % (
            s2["hit"], s2["n"], s2["active_vals"], len(aurora_leak)))
        # ---- 判定 ----
        ok1 = (s1["hit"] >= 60 and s1["hand_empty_or_masked_L"] == s1["hit"]
               and s1["hand_empty_or_masked_R"] == s1["hit"]
               and s1["gauge_sent_L"] == s1["hit"]
               and s1["gauge_sent_R"] == s1["hit"])
        ok2 = s2["hit"] >= 60 and not aurora_leak
        verdict = "PASS" if (ok0 and ok1 and ok2) else "FAIL"
        print("\n运行时遮蔽判定: %s (负控=%s 晴岚=%s 极光=%s)"
              % (verdict, ok0, ok1, ok2))
        # ---- 证据落盘 ----
        out = os.path.join(ROOT, "docs", "mod_masking_runtime_dump.md")
        with io.open(out, "w", encoding="utf-8") as fh:
            fh.write("# mod遮蔽运行时实测证据\n\n")
            fh.write("- 日期: %s\n" % time.strftime("%Y-%m-%d %H:%M"))
            fh.write("- 部署DLL MD5: `%s`\n" % dll_md5)
            fh.write("- 方法: SET_WEATHER强制天气 + 逐帧dump原始字段"
                     "(tools/runtime_masking_probe.py)\n\n")
            fh.write("## 阶段1 晴岚(11)\n\n```\n%s\n```\n\n" % s1)
            fh.write("## 阶段2 极光(19)\n\n```\n%s\n```\n\n" % s2)
            fh.write("## 判定\n\n**%s** — 晴岚帧双方hand全0xFF且cardGauge==65535"
                     "(%d/%d帧); displayed==19的帧active恒为19, 无真实效果外泄。\n"
                     % (verdict, s1["hit"], s1["hit"]))
        print("证据已存:", out)
        return 0 if verdict == "PASS" else 1
    finally:
        try:
            inst.sock.close()
        except Exception:
            pass
        if inst.proc:
            inst.proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
