# -*- coding: utf-8 -*-
"""C盘Temp安全清理 — 保护活跃文件, 只清陈旧残留。

安全策略(多层保护):
  1. 跳过 th123_* (舰队运行期标记/日志/boot log — 正在用)
  2. 跳过最近1小时内修改的(可能在用)
  3. 跳过锁定文件(尝试独占打开失败=被占用)
  4. 跳过白名单目录(vscode-stable等当前会话可能在用)
  5. 默认 --dry-run 只报告不删; --apply 才真删

用法:
  python tools/clean_temp.py              # 预览(不删)
  python tools/clean_temp.py --apply      # 执行
  python tools/clean_temp.py --apply --min-age-h 24   # 只清1天以上
"""
import argparse
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding='utf8')

TEMP = os.path.expandvars(r'%LOCALAPPDATA%\Temp')
# 白名单: 当前会话/常用工具可能正在用
PROTECTED_PREFIX = ('th123_', 'vscode-stable', 'agent_runtime',
                    'playwright-artifacts')
# .ses = 桌面会话文件(勿动)


# ── D盘模式: 清测试残留(不碰现用BC/模型/游戏) ──────────────
DTEMP = r'D:\temp'
# D:	emp 下测试/工具残留前缀(超过min-age可清)
# 仅测试沙箱前缀(不加'st'/'build'/'clash'等 — 会误伤st*.txt等文件)
D_PREFIXES = ('gate_selftest_', 'fleet_proto_', 'w3_', 'd4_',
              'gpu_equiv_', 'gpu_upd_', 'b_test_', 'hs_b2_',
              'hd_i_', '_r63_')


def clean_d_temp(apply=False, min_age_h=24.0):
    """D:	emp 测试残留清理(白名单式: 只删已知前缀, 不碰其它)。"""
    now = time.time()
    cut = min_age_h * 3600
    freed = n = 0
    print('D盘测试残留: %s' % DTEMP)
    for name in os.listdir(DTEMP):
        if not any(name.startswith(x) for x in D_PREFIXES):
            continue
        p = os.path.join(DTEMP, name)
        try:
            if now - os.path.getmtime(p) < cut:
                continue
            sz = (os.path.getsize(p) if os.path.isfile(p)
                  else dir_size(p))
        except OSError:
            continue
        print('  %s %-30s %8.1f MB' % (
            '删' if apply else '可删', name[:30], sz / 2**20))
        if apply:
            try:
                if os.path.isfile(p):
                    os.remove(p)
                else:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                continue
        freed += sz
        n += 1
    print('  %s: %d项, %.2f GB' % ('已删' if apply else '可删',
                                   n, freed / 2**30))
    return freed


def is_locked_dir(path):
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                fh = open(os.path.join(root, f), 'r+b')
                fh.close()
            except (PermissionError, OSError):
                return True
    return False


def dir_size(path):
    sz = 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                sz += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return sz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='真删(默认预览)')
    ap.add_argument('--min-age-h', type=float, default=1.0,
                    help='只清N小时前的(默认1)')
    ap.add_argument('--d', action='store_true',
                    help='清D盘测试残留(≥24h, 白名单前缀)')
    a = ap.parse_args()
    if a.d:
        clean_d_temp(apply=a.apply, min_age_h=max(24.0, a.min_age_h))
        return 0

    now = time.time()
    cut = a.min_age_h * 3600
    freed = kept = 0
    n_del = n_keep = 0
    skipped = []
    for name in os.listdir(TEMP):
        if name.startswith(PROTECTED_PREFIX):
            skipped.append(name)
            continue
        p = os.path.join(TEMP, name)
        try:
            age = now - os.path.getmtime(p)
        except OSError:
            continue
        if age < cut:
            skipped.append(name)
            continue
        sz = (os.path.getsize(p) if os.path.isfile(p) else dir_size(p))
        # 锁定检查(目录抽查首文件)
        if os.path.isdir(p) and is_locked_dir(p):
            skipped.append(name)
            n_keep += 1
            kept += sz
            continue
        if a.apply:
            try:
                if os.path.isfile(p):
                    os.remove(p)
                else:
                    shutil.rmtree(p, ignore_errors=True)
                freed += sz
                n_del += 1
            except OSError:
                n_keep += 1
                kept += sz
        else:
            freed += sz
            n_del += 1
    print('Temp: %s' % TEMP)
    print('  %s: %d项, %.1f GB' % ('已删' if a.apply else '可删',
                                   n_del, freed / 2**30))
    print('  保留: %d项, %.1f GB (活跃/锁定/白名单/未到期)'
          % (n_keep + len(skipped), kept / 2**30))
    if skipped:
        prot = [s for s in skipped if s.startswith(PROTECTED_PREFIX)]
        print('  保护中(舰队/工具活跃): %d项%s'
              % (len(prot), ' 例: ' + ', '.join(prot[:3]) if prot else ''))
    if not a.apply:
        print('\n  (预览模式 — 加 --apply 执行)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
