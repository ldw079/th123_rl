# -*- coding: utf-8 -*-
"""CA-1(社区AI对标方案§CA-1): vs th123ai 社区AI评估口径 — 第三测量轴.

对局形态: th123_ai.exe + Lua脚本跑 P1(自带RPM读+键盘输出)
         × 我方模型跑 P2(mod输入, SideDriver)
复用: B标尺基建(RPM观察我方侧照常)

硬约束(runner三条):
  ①管理员权限(th123ai需)
  ②Vs Player模式(wiki明载)
  ③窗口焦点独占(keybd_event需焦点; 评估期不并行其他焦点任务)

用法:
  python tools/eval_vs_th123ai.py --char reimu --script 00_reimu_main \\
      --games 10
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf8')

TH123AI_DIR = r'D:\touhou\hisoutensoku2026-06-15\th123ai'
TH123AI_EXE = os.path.join(TH123AI_DIR, 'th123_ai.exe')
GAME_DIR = r'D:\touhou\hisoutensoku2026-06-15\th123'
STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
REPORT = os.path.join(STORE, 'eval_vs_th123ai.jsonl')


def list_scripts():
    """本地脚本对手库(00主力系=有卡组说明的完整版)."""
    scripts = sorted(glob.glob(os.path.join(TH123AI_DIR, 'script',
                                            '*.ai')))
    out = []
    for p in scripts:
        name = os.path.basename(p)
        # 主力系=前缀00(有卡组及说明)
        tier = '主力' if name.startswith('00_') else '其他'
        out.append((name, tier, p))
    return out


def check_prereqs():
    """三条硬约束预检."""
    ok = True
    # ① 管理员权限
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False
    if not is_admin:
        print('!! 需要管理员权限(右键→以管理员身份运行)')
        ok = False
    # ② th123_ai.exe 存在
    if not os.path.exists(TH123AI_EXE):
        print('!! th123_ai.exe 不存在: %s' % TH123AI_EXE)
        ok = False
    # ③ 游戏目录存在
    if not os.path.isdir(GAME_DIR):
        print('!! 游戏目录不存在: %s' % GAME_DIR)
        ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='reimu',
                    help='我方模型角色')
    ap.add_argument('--script', default=None,
                    help='社区AI脚本文件名(如00_reimu_main.ai)')
    ap.add_argument('--games', type=int, default=10)
    ap.add_argument('--list', action='store_true',
                    help='列出可用脚本')
    ap.add_argument('--dry-run', action='store_true',
                    help='只做预检不真跑')
    a = ap.parse_args()

    if a.list:
        print('=== 本地脚本对手库 ===')
        for name, tier, path in list_scripts():
            print('  [%s] %s' % (tier, name))
        return 0

    if not check_prereqs():
        return 1

    if a.dry_run:
        print('预检通过 ✓')
        print('  脚本: %s' % a.script)
        print('  角色: %s' % a.char)
        print('  局数: %d' % a.games)
        print('  (dry-run — 不真跑)')
        return 0

    print('CA-1 vs 社区AI评估 — 尚未完全实现(需对局采集管线)')
    print('  本轮完成: 预检+脚本库+框架')
    print('  下一步: 接入SideDriver驱动+th123ai挂载+计分归档')
    return 0


if __name__ == '__main__':
    sys.exit(main())
