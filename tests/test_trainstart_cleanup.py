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


def main():
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
