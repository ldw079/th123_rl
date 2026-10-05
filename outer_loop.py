# -*- coding: utf-8 -*-
"""外环(轮换环) v1 — METHODOLOGY §6.0 阶段2的第一块: 对局调度与战报。

组成:
  MatchRunner  VS_PLAYER双模型对局(无学习): SideDriver×2复用训练侧全套
               视觉/特征/掩码/宏队列/确认门(sc宏除外, 见注), 输出局结果
  OpponentPool 检查点快照(pool/{char}/{ts}.npz), 只读加载(§6.0纪律)
  战报          reports/matchup_{ts}.md: 6 matchup胜率矩阵+毕业门读数

用法:
  python outer_loop.py match reimu marisa --games 3     # 单matchup评估
  python outer_loop.py snapshot                          # 三角色当前模型入池
  python outer_loop.py report --games 2                  # 全矩阵战报(6 matchup)
  python outer_loop.py comeval reimu --games 3           # COM检验探针(无学习)
  python outer_loop.py cycle --games 2 --interval 3600   # 周期: 快照+战报+COM检验

注: eval期sc符卡宏掩死(状态机未移植) — 行为分布与训练略有差异, v1已知局限。
镜像规则(实测推导): mirror = 朝向<0, P1/P2通用(宏"前进"语义=朝向对手)。
"""
import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

from side_driver import SideDriver, EvalEnv  # noqa: E402  (2026-09-22抽取共享)
from train_tm import STORE_DIR  # noqa: E402

CHARS = ("reimu", "marisa", "suika")
POOL_DIR = os.path.join(STORE_DIR, "pool")
REPORT_DIR = os.path.join(STORE_DIR, "reports")
EVAL_PORT = 20900


def run_match(char_l, pi_l, char_r, pi_r, games=2, port=EVAL_PORT, tps=480):
    """VS_PLAYER双模型对局games局。输入与训练同拍(上帧队列状态→本帧输入),
    队列推进用返回帧(语义与train_tm一致, 含门步 — 第六轮审计§4修复)。"""
    dl = SideDriver(char_l, "L")
    dl.load(pi_l)
    dr = SideDriver(char_r, "R")
    dr.load(pi_r)
    env = EvalEnv(port, char_left=char_l, char_right=char_r,
                  vs_com=False, tps=tps)
    res = {"l_wins": 0, "r_wins": 0, "aborted": 0,
           "decis_l": 0, "decis_r": 0, "raw": []}
    played = 0
    inp_l, inp_r = {}, {}
    t0 = time.time()
    try:
        while played < games and time.time() - t0 < games * 300:
            r = env.step(inp_l, inp_r)
            if r is None:      # 局边界(env已续局/重启) — 结算+重置
                if env.last_match:
                    w, ls, rs = env.last_match
                    res["raw"].append((w, ls, rs))
                    if ls > rs:
                        res["l_wins"] += 1
                    elif rs > ls:
                        res["r_wins"] += 1
                    played += 1
                    env.last_match = None
                    print("  [match] 局%d: w=%s %d-%d (墙%.0fs)"
                          % (played, w, ls, rs, time.time() - t0))
                else:
                    # 第六轮审计§7d: 崩溃/超时局不再静默丢弃
                    res["aborted"] += 1
                    print("  [match] 局中断(无结果)#%d" % res["aborted"])
                dl.reset_match()
                dr.reset_match()
                inp_l, inp_r = {}, {}
                continue
            left, right, weather, objs = r
            bul_l = dl.feat_builder.track_bullets(objs)
            bul_r = dr.feat_builder.track_bullets(objs)
            inp_l = dl.frame_input(left, right, weather, objs, bul_l)
            inp_r = dr.frame_input(right, left, weather, objs, bul_r)
    finally:
        # 第六轮审计§7a: 必须走env.close()(置位watch停+CloseHandle),
        # 原版只关socket会泄漏OpenProcess句柄+永不退出的daemon线程
        try:
            env.close()
        except Exception:
            pass
    res["decis_l"] = dl.decisions
    res["decis_r"] = dr.decisions
    return res


def current_model(char):
    return os.path.join(STORE_DIR, "model_ppo_%s.npz" % char)


def com_eval(char, games=2, port=20910, tps=480, com_difficulty=3):
    """COM检验探针(2026-09-23用户令: 主线转自对弈后定期和COM对战检验):
    模型P1 vs 游戏内置COM, 无学习, 返回胜率。COM作外部标尺不作门。
    R16修复: com_difficulty必须传(原漏传→打默认难度, 与训练内
    --com-difficulty 3的战绩不可比; 实测训练内3-0/评估0-2矛盾)。"""
    d = SideDriver(char, "L")
    d.load(current_model(char))
    env = EvalEnv(port, char_left=char, char_right=char,
                  vs_com=True, tps=tps, com_difficulty=com_difficulty)
    res = {"char": char, "wins": 0, "losses": 0, "raw": []}
    played = 0
    inp = {}
    t0 = time.time()
    try:
        while played < games and time.time() - t0 < games * 300:
            r = env.step(inp)          # VS_COM: right侧留空, COM自走
            if r is None:
                if env.last_match:
                    _w, ls, rs = env.last_match
                    res["raw"].append((ls, rs))
                    if ls > rs:
                        res["wins"] += 1
                    elif rs > ls:
                        res["losses"] += 1
                    played += 1
                    env.last_match = None
                    print("  [com] %s 局%d: %d-%d" % (char, played, ls, rs))
                d.reset_match()
                inp = {}
                continue
            left, right, weather, objs = r
            bul = d.feat_builder.track_bullets(objs)
            inp = d.frame_input(left, right, weather, objs, bul)
    finally:
        env.close()
    return res


class OpponentPool:
    """检查点快照池(§6.0纪律: 只读加载, 防对手强弱漂移)。"""

    def __init__(self, root=POOL_DIR):
        self.root = root

    def snapshot(self, chars=CHARS):
        os.makedirs(self.root, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = []
        for ch in chars:
            src = current_model(ch)
            if not os.path.exists(src):
                print("[pool] 缺模型:", src)
                continue
            d = os.path.join(self.root, ch)
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, "%s.npz" % ts)
            # 第六轮审计§7f: 先copy v再copy pi(pi后落=配对提交标记, 防N的pi配N-1的v)
            vsrc = src.replace(".npz", "_v.npz")
            if os.path.exists(vsrc):
                shutil.copy2(vsrc, dst.replace(".npz", "_v.npz"))
            shutil.copy2(src, dst)
            out.append(dst)
        if out:
            meta = os.path.join(self.root, "meta.json")
            try:
                m = json.load(open(meta, encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                # 第六轮审计§7c: 撕裂写入自愈 + 原子落盘
                m = []
            m.append({"ts": ts, "models": out})
            tmp = meta + ".tmp"
            json.dump(m[-200:], open(tmp, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            os.replace(tmp, meta)
        return out

    def latest(self, char, k=1):
        d = os.path.join(self.root, char)
        if not os.path.isdir(d):
            return []
        # 排除_v价值网快照(否则排序后[-1]会取到它 — 2026-09-22实测踩坑)
        snaps = sorted(f for f in os.listdir(d)
                       if f.endswith(".npz") and not f.endswith("_v.npz"))
        return [os.path.join(d, f) for f in snaps[-k:]]


def matchup_report(games_per=2, port=EVAL_PORT):
    """6 matchup全矩阵战报 + 毕业门读数(§6.0: 外环门=交叉胜率≥40%)。
    第六轮审计§7e: 逐matchup隔离(一个坏的不全灭)。"""
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    matrix = {}
    lines = ["# matchup战报 %s" % time.strftime("%Y-%m-%d %H:%M"),
             "", "每matchup %d局, VS_PLAYER双控, eval期sc宏掩死(v1局限)。" % games_per,
             ""]
    for a in CHARS:
        for b in CHARS:
            if a == b:
                continue
            pa, pb = current_model(a), current_model(b)
            if not (os.path.exists(pa) and os.path.exists(pb)):
                continue
            print("[report] %s vs %s ..." % (a, b))
            try:
                r = run_match(a, pa, b, pb, games=games_per, port=port)
            except Exception as e:
                print("  [report] %s vs %s 失败: %s" % (a, b, e))
                matrix["%s>%s" % (a, b)] = {"winrate": None, "error": str(e)[:80]}
                lines.append("- **%s vs %s**: 失败(%s)" % (a, b, str(e)[:40]))
                continue
            n = r["l_wins"] + r["r_wins"]
            wr = (r["l_wins"] / n) if n > 0 else None   # §7d: 0局=None非0.0
            matrix["%s>%s" % (a, b)] = {"winrate": wr, **r}
            if wr is None:
                lines.append("- **%s vs %s**: 无有效局(中断%d)"
                             % (a, b, r["aborted"]))
            else:
                lines.append("- **%s vs %s**: %d-%d (胜率%.0f%%, 决策%d/%d, 中断%d)"
                             % (a, b, r["l_wins"], r["r_wins"], 100 * wr,
                                r["decis_l"], r["decis_r"], r["aborted"]))
    lines += ["", "## 毕业门读数(§6.0, 2.4版注: 单阈值不适配matchup不对称 — "
              "重构待干净读数, 下行仅作参考读数非判定)", ""]
    for a in CHARS:
        wrs = [matrix["%s>%s" % (a, b)]["winrate"] for b in CHARS
               if b != a and "%s>%s" % (a, b) in matrix
               and matrix["%s>%s" % (a, b)]["winrate"] is not None]
        if wrs:
            lo = min(wrs)
            lines.append("- %s: 交叉最低胜率%.0f%% (参考线55%%: %s)"
                         % (a, 100 * lo, "过" if lo >= 0.55 else "未过"))
    path = os.path.join(REPORT_DIR, "matchup_%s.md" % ts)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    json.dump(matrix, open(path.replace(".md", ".json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[report] 已写:", path)
    return path

def cycle(games_per=2, interval=3600, port=EVAL_PORT):
    """周期调度: 快照→战报→COM检验→休眠(与内环训练并行, 独立端口)。
    第六轮审计§7e: 单实例锁 + 逐周期异常隔离(一次异常不再永久结束外环)。
    2026-09-23用户令: 主线转自对弈后COM降级为定期外部检验(非门)。"""
    lock = os.path.join(STORE_DIR, "outer_loop.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        # 第八轮审查: 持有者已死的陈旧锁会永久挡住周期器(实测PID46756死后
        # 周期器停摆整天)。检查持有PID存活 — 死锁窃取, 活锁拒绝。
        old = ""
        try:
            old = open(lock, encoding="ascii", errors="replace").read().strip()
        except OSError:
            pass
        alive = False
        if old.isdigit():
            import ctypes
            alive = bool(ctypes.windll.kernel32.OpenProcess(0x1000, 0, int(old)))
        if not alive:
            print("[cycle] 陈旧锁(PID=%s 已死) — 窃取并接管" % (old or "?"))
            try:
                os.remove(lock)
            except OSError:
                pass
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        else:
            print("[cycle] 已有实例在跑(PID=%s) — 单实例锁拒绝" % old)
            return 1
    pool = OpponentPool()
    n = 0
    try:
        while True:
            n += 1
            try:
                print("[cycle] #%d 快照..." % n)
                pool.snapshot()
                matchup_report(games_per=games_per, port=port)
                # COM检验(用户令: 定期和COM对战看成果, 追加写入战报目录)
                ce_path = os.path.join(REPORT_DIR, "com_eval_log.md")
                with open(ce_path, "a", encoding="utf-8") as fh:
                    fh.write("\n## %s\n" % time.strftime("%Y-%m-%d %H:%M"))
                    for ch in CHARS:
                        try:
                            r = com_eval(ch, games=games_per)
                            m = r["wins"] + r["losses"]
                            wr = (100.0 * r["wins"] / m) if m else 0.0
                            line = "- %s: %dW-%dL (%.0f%%)" % (
                                ch, r["wins"], r["losses"], wr)
                        except Exception as e:
                            line = "- %s: 失败(%s)" % (ch, str(e)[:50])
                        print("[cycle] [com]" + line)
                        fh.write(line + "\n")
                # 策略树诊断(用户令2026-09-23: 定期 surfaced, 不埋训练日志)
                da_path = os.path.join(REPORT_DIR, "doctrine_audit_log.md")
                import subprocess as _sp
                with open(da_path, "a", encoding="utf-8") as fh:
                    fh.write("\n## %s\n" % time.strftime("%Y-%m-%d %H:%M"))
                    for ch in CHARS:
                        try:
                            r = _sp.run(
                                [sys.executable, "-X", "utf8",
                                 os.path.join(os.path.dirname(
                                     os.path.abspath(__file__)),
                                     "standard_tree.py"), "audit", ch],
                                capture_output=True, text=True, timeout=120)
                            # R12-P0H: 空输出≠通过 + returncode检查
                            if r.returncode != 0:
                                warns = ["⚠ AUDIT_FAILED rc=%d" % r.returncode]
                            elif not r.stdout.strip():
                                warns = ["⚠ AUDIT_EMPTY_OUTPUT"]
                            else:
                                warns = [l.strip() for l in r.stdout.splitlines()
                                         if l.strip().startswith("⚠")]
                            fh.write("### %s\n" % ch)
                            for w in warns[:6]:
                                fh.write(w + "\n")
                                print("[cycle] [audit][%s] %s" % (ch, w[:80]))
                            if not warns:
                                fh.write("(无高危偏离)\n")
                        except Exception as e:
                            fh.write("### %s 失败: %s\n" % (ch, e))
            except Exception as e:
                print("[cycle] #%d 异常(隔离继续): %s: %s"
                      % (n, type(e).__name__, e))
            print("[cycle] #%d 完成, 休眠%ds" % (n, interval))
            time.sleep(interval)
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description="外环: matchup评估/快照/战报/COM检验")
    ap.add_argument("cmd",
                    choices=["match", "snapshot", "report", "comeval", "cycle"])
    ap.add_argument("chars", nargs="*", help="match/comeval用角色")
    ap.add_argument("--games", type=int, default=2)
    ap.add_argument("--interval", type=int, default=3600)
    ap.add_argument("--port", type=int, default=EVAL_PORT)
    a = ap.parse_args()
    if a.cmd == "match":
        if len(a.chars) != 2:
            print("用法: match <charL> <charR>")
            return 1
        r = run_match(a.chars[0], current_model(a.chars[0]),
                      a.chars[1], current_model(a.chars[1]),
                      games=a.games, port=a.port)
        print("结果:", json.dumps({k: v for k, v in r.items() if k != "raw"},
                                  ensure_ascii=False))
        print("原始(w,ls,rs):", r["raw"])
        return 0
    if a.cmd == "snapshot":
        print("入池:", OpponentPool().snapshot())
        return 0
    if a.cmd == "report":
        matchup_report(games_per=a.games, port=a.port)
        return 0
    if a.cmd == "comeval":
        chars = a.chars or list(CHARS)
        out = []
        for ch in chars:
            print("[comeval] %s vs COM ..." % ch)
            try:
                out.append(com_eval(ch, games=a.games))
            except Exception as e:
                print("  失败:", e)
        for r in out:
            n = r["wins"] + r["losses"]
            wr = (r["wins"] / n * 100) if n else 0.0
            print("[comeval] %s: %dW-%dL (%.0f%%)" % (r["char"], r["wins"],
                                                      r["losses"], wr))
        return 0
    cycle(games_per=a.games, interval=a.interval, port=a.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
