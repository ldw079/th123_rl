# -*- coding: utf-8 -*-
"""三实例并行训练启动器(2026-09-23主线转自对弈, 用户令):
每角色对手=另两角色的池快照轮换(外环训练半环), COM降级为定期外部检验
(outer_loop cycle内com_eval)。

第八轮审查§3: 增加子进程监督 — 训练器死亡(如启动期崩溃)时自动重启并记录,
不再出现"1h47m无人发现"的带病运行。冷却30s, 每角色重启上限20次(防疯狂循环)。
"""
import os
import subprocess
import sys
import time

DIR = r"%USERPROFILE%\Desktop\workplace\th123_rl"
PY = r"D:\temp\pyenv\python.exe"

CHARS = [
    # R22(2026-10-02): 首位=镜像对局(己方角色) — 同角色对局占真实对战
    # 一半空间, 且"输给自己旧版"是最干净的学习信号; 池深k=3由train_tm
    # main()的POOL_K实现(历史快照对抗防策略循环/遗忘)。
    ("reimu", 20800, 0, ["reimu", "marisa", "suika", "COM"]),
    ("marisa", 20810, 1, ["marisa", "reimu", "suika", "COM"]),
    ("suika", 20820, 2, ["suika", "reimu", "marisa", "COM"]),
]

MAX_RESTARTS = 20
COOLDOWN_S = 30
# R17(§3.6): 注释与行为对齐 — 上限20配合"存活>600s衰减1次": 长期健康
# 运行会持续偿还重启额度, 上限只拦真正的疯狂循环(20连死且无一存活10min)。
# R16: trainer错峰启动(秒)。tm_env已加boot互斥锁兜底, 这里再错峰
# 避免三个2.7GB级模型加载的磁盘风暴 + 首局游戏同时boot。
STAGGER_S = 30
# R17(I12): 单实例锁 — METHODOLOGY:239"单份run_parallel"曾无实现;
# 双启动器会让两个同名trainer绑同一端口(SO_REUSEADDR静默双绑串流)。
LOCK = r"D:\temp\run_parallel.lock"

SUPERVISION_LOG = r"D:\temp\train_supervision.log"


def log(msg):
    line = "[%s] %s" % (time.strftime("%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    with open(SUPERVISION_LOG, "a", encoding="utf8") as f:
        f.write(line + "\n")


def build_cmd(char, port, slot, opps, eps):
    cmd = [PY, "-X", "utf8", "-u", "train_tm.py",
           "--char", char, "--port", str(port), "--slot", str(slot),
           "--tps", "480", "--episodes", eps, "--ep-timeout", "240",
           # R43方案B: COM难度阶梯起点Easy — 课程学习(近20局胜率≥50%
           # 升一级/近40局<20%降一级, train_tm._com_ladder动态调整),
           # 原固定Lunatic=零有效学习信号(本批3W-122L的根因之一)
           "--com-difficulty", "0"]
    for o in opps:
        cmd += ["--opp", o]
    return cmd


def _main():
    eps = sys.argv[1] if len(sys.argv) > 1 else "100"
    # 每角色状态: (proc, restarts, last_start_time)
    state = {}
    logs = {}
    for char, port, slot, opps in CHARS:
        logs[char] = open(r"D:\temp\train_%s.log" % char, "a", encoding="utf-8")
        cmd = build_cmd(char, port, slot, opps, eps)
        p = subprocess.Popen(cmd, cwd=DIR, stdout=logs[char],
                             stderr=subprocess.STDOUT)
        state[char] = [p, 0, time.time()]
        log("启动 %s PID=%d 端口%d 槽%d tps480 自对弈对手=%s"
            % (char, p.pid, port, slot, "+".join(opps)))
        if STAGGER_S:
            time.sleep(STAGGER_S)   # R16: 错峰 — 下个trainer的模型加载/首局boot错开
    log("全部启动 — 监督模式(死亡自动重启, 上限%d次/角色)" % MAX_RESTARTS)
    while state:
        time.sleep(10)
        for char in list(state):
            p, restarts, t0 = state[char]
            if p.poll() is None:
                continue
            # 已存活超过10分钟视为一次"正常服役", 重启计数衰减
            served = time.time() - t0
            if served > 600 and restarts > 0:
                restarts -= 1
            if restarts >= MAX_RESTARTS:
                log("%s 重启次数耗尽(%d) — 放弃, 人工介入" % (char, restarts))
                del state[char]
                continue
            if p.returncode in (0, 130):
                # R19(审查2026-10-02): 0=跑满局数; 130=train_tm人为中断
                # (KeyboardInterrupt, 原版exit 0被误记"正常完成"); 其余码
                # (含环境系统性故障exit 1)照常重启
                # R42: eps是str(argv) — 原%d格式在首个训练器跑满局数时
                # TypeError炸掉监督器(2026-10-04 suika 500局首次触达)
                log("%s PID=%d 正常完成(%s局, code=%d) — 不重启"
                    % (char, p.pid, eps, p.returncode))
                del state[char]
                continue
            log("%s PID=%d 退出(code=%s, 存活%.0f分钟) — %ds后重启(第%d次)"
                % (char, p.pid, p.returncode, served / 60, COOLDOWN_S,
                   restarts + 1))
            time.sleep(COOLDOWN_S)
            char, port, slot, opps = next(
                c for c in CHARS if c[0] == char)
            cmd = build_cmd(char, port, slot, opps, eps)
            p2 = subprocess.Popen(cmd, cwd=DIR, stdout=logs[char],
                                  stderr=subprocess.STDOUT)
            state[char] = [p2, restarts + 1, time.time()]
            log("%s 已重启 PID=%d" % (char, p2.pid))
        if not state:
            break
    log("全部结束(或全部耗尽重启额度)")


if __name__ == "__main__":
    # R17(I12): 单实例锁(PID存活检测, 陈旧锁自动接管 — outer_loop.lock同款)
    import ctypes
    _k32 = ctypes.windll.kernel32
    if os.path.exists(LOCK):
        try:
            _old = open(LOCK).read().strip()
            _h = _k32.OpenProcess(0x1000, False, int(_old))
            if _h:
                _k32.CloseHandle(_h)
                print("已有run_parallel在跑(PID=%s) — 拒绝双开" % _old)
                sys.exit(1)
        except (ValueError, OSError):
            pass
        os.remove(LOCK)   # 陈旧锁 — 接管
    fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        _main()
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass
