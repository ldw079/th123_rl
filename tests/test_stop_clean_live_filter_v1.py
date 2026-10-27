# -*- coding: utf-8 -*-
"""P1 行为测试: stop_clean live 只杀训练车道游戏, 非训练原版不杀(真实进程)."""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import train_stop_clean as T  # noqa: E402

GAME = r'D:\touhou\hisoutensoku2026-06-15\th123\th123.exe'
TRAIN = r'D:\touhou\hisoutensoku2026-06-15\th123_train\th123.exe'
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def main():
    procs = []
    try:
        # 非训练原版实例（无端口）
        p1 = subprocess.Popen([GAME], cwd=os.path.dirname(GAME))
        procs.append(p1)
        # 训练车道实例（路径含 th123_train + 车道端口 21005）
        p2 = subprocess.Popen([TRAIN, '21005'], cwd=os.path.dirname(TRAIN))
        procs.append(p2)
        time.sleep(4.0)
        got = set(int(x) for x in T.game_pids())
        check('训练实例被识别', p2.pid in got, str(got))
        check('非训练原版不被识别', p1.pid not in got, str(got))
        # 混合场景只杀训练: 断言过滤结果只含训练
        check('混合只返回训练', all(pid in got for pid in [p2.pid])
              and p1.pid not in got)
    finally:
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
    print('\n==== stop_clean_live_filter: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
