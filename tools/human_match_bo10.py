# -*- coding: utf-8 -*-
"""task-69 Bo10 人测流程骨架（本机；R1 只写己方；真实游戏窗口只读检测）.

用法:
  python tools/human_match_bo10.py --mock --bo 10 --snapshot model_ppo_reimu_v0
  python tools/human_match_bo10.py --check-window   # 只读检测本机 Giuroll/th123 窗口
真实对战接入（写己方输入/录像）下一迭代；本脚本不注入任何输入、不读对手输入。
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from human_match_harness import HumanMatchHarness  # noqa: E402


def check_window():
    """只读检测: 列出 th123 进程(含 Giuroll 窗口); 不结束/不读取进程内数据."""
    script = ("Get-CimInstance Win32_Process | ? {$_.Name -eq 'th123.exe'} | "
              "Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Json")
    r = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                       capture_output=True, text=True, timeout=30)
    try:
        data = json.loads(r.stdout or '[]')
        if isinstance(data, dict):
            data = [data]
    except Exception:
        data = []
    print(json.dumps({'th123_processes': data,
                      'note': '只读; 不触碰用户进程'}, ensure_ascii=False,
                     indent=1))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--check-window', action='store_true')
    ap.add_argument('--bo', type=int, default=10)
    ap.add_argument('--snapshot', default='model_ppo_reimu_v0')
    ap.add_argument('--out-dir', default=r'D:\temp\human_match')
    a = ap.parse_args()
    if a.check_window:
        return check_window()
    if not a.mock:
        print('真实对战接入下一迭代; 本脚本不注入输入/不读对手; 先用 --check-window 只读检测')
        return 1
    h = HumanMatchHarness(bo=a.bo, seed=0, snapshot=a.snapshot,
                          out_dir=a.out_dir)
    summ, p, rp = h.run()
    # Bo10 session 摘要
    report = {'schema': 1, 'bo': summ['bo'], 'snapshot': summ['snapshot'],
              'snapshot_hash': summ['snapshot_hash'], 'wins': summ['wins'],
              'losses': summ['losses'], 'own_inputs': summ['own_inputs'],
              'r1': summ['r1'], 'summary_path': p, 'replay_path': rp,
              'created': time.strftime('%Y-%m-%d %H:%M:%S')}
    op = os.path.join(a.out_dir, 'bo10_session.json')
    json.dump(report, open(op, 'w', encoding='utf-8'), ensure_ascii=False,
              indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
