# -*- coding: utf-8 -*-
"""train_start 清理自杀修复(R64/教训×3) 配对测试 — 真进程级.

复现模型(2026-10-11实弹): train_start带 --exploiter 启动 → 自身命令行
含特征串'exploiter' → pre_flight清理把它taskkill /T /F连树自杀,
日志止于"[前置] 残留进程清理"行, 什么都没启动。

断言(真powershell×真进程, 非字符串检查):
  1. 特征串命中者被杀(decoy_a: cmdline含exploiter)
  2. **同特征串但被排除的PID存活**(decoy_b=exclude_pid — 正是train_start
     自身的处境; 修复前它会死)
  3. 无特征串进程不受连坐(decoy_c)

⚠ 教训×4(2026-10-12, R64后每次"fleet运行中跑门禁"都灭队——含昨夜与
今晨各一次, 曾被误判为主机停机): 本测试执行**真实清理命令**, 排除的
只有测试自身PID → 活fleet(supervisor/learner/actor/exploiter全命中
特征串)被整树taskkill。守卫: 检测到活训练进程时**跳过破坏性阶段**
(留待停机窗口/无fleet环境执行), 门禁与活fleet共存是宪法工作流的前提。
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.stdout.reconfigure(encoding='utf8')

from tools.train_start import _cleanup_ps_cmd

SLEEPER = 'import time; time.sleep(120)'


def alive(p):
    return p.poll() is None


def live_fleet_present():
    """活训练进程在场? WMI按清理同款特征串计数(探测失败按在场=保守)."""
    try:
        out = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
             "| Where-Object {$_.CommandLine -match "
             "'fleet_supervisor|run_parallel|learner_hub|actor_worker"
             "|exploiter'} | Measure-Object | "
             "Select-Object -ExpandProperty Count"],
            capture_output=True, text=True, timeout=30)
        return int((out.stdout or '0').strip() or 0) > 0
    except Exception:
        return True


def main():
    # 审计#3 P1-6静态断言(不依赖进程, fleet在场也跑): 游戏清理必须按
    # th123_train路径精确匹配 — 裸 taskkill /IM th123.exe /F 会误杀
    # 用户原版游戏与rl_game离线重放实例
    _cmd = ' '.join(_cleanup_ps_cmd(0))
    _ok = ("Name='th123.exe'" in _cmd
           and "th123_train" in _cmd
           and "/IM th123.exe /F" not in _cmd)
    print("[%s] 游戏清理只碰th123_train族(路径精确匹配, 无裸/IM)"
          % ('PASS' if _ok else 'FAIL'))
    if not _ok:
        print("==== 0 PASS / 1 FAIL ====")
        sys.exit(1)
    if live_fleet_present():
        print("[SKIP] 活fleet在场 — 破坏性清理断言跳过(教训×4: 本测试"
              "曾四次灭掉活fleet; 完整断言留待停机窗口执行)")
        print("==== SKIP(活fleet保护) / 0 FAIL ====")
        return
    # decoy_a: 命中特征串 → 该死
    a = subprocess.Popen([sys.executable, '-c', SLEEPER, '--exploiter=reimu'])
    # decoy_b: 同样命中特征串, 但作为exclude_pid(=train_start自身处境) → 该活
    b = subprocess.Popen([sys.executable, '-c', SLEEPER, '--exploiter=reimu'])
    # decoy_c: 干净命令行 → 该活(不连坐)
    c = subprocess.Popen([sys.executable, '-c', SLEEPER])
    time.sleep(1.0)           # 让进程都进入任务列表(命令行可见)
    assert alive(a) and alive(b) and alive(c), "诱饵进程未全部启动"

    r = subprocess.run(_cleanup_ps_cmd(b.pid), capture_output=True,
                       timeout=60)
    # powershell自身退出码可能是taskkill的最后一条(/IM th123.exe无实例
    # 时非零) — 判据看进程生死, 不看退出码
    deadline = time.time() + 10
    while alive(a) and time.time() < deadline:
        time.sleep(0.5)
    try:
        assert not alive(a), "FAIL: 特征串命中进程应被清理"
        print("[PASS] 特征串命中者被杀 (pid=%d)" % a.pid)
        assert alive(b), "FAIL: exclude_pid自身被自杀(修复无效!)"
        print("[PASS] 同特征串但exclude_pid存活 — 自杀修复生效 (pid=%d)" % b.pid)
        assert alive(c), "FAIL: 无特征串进程被连坐"
        print("[PASS] 无特征串进程不受连坐 (pid=%d)" % c.pid)
        print("[PASS] 清理powershell返回(无挂死) rc=%s" % r.returncode)
    finally:
        for p in (b, c):
            if alive(p):
                p.kill()
    print("==== 4 PASS / 0 FAIL ====")


if __name__ == "__main__":
    main()
