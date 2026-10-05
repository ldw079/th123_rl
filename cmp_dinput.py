# -*- coding: utf-8 -*-
"""对比dinput8加载: 训练实例(最小mod) vs 40024(全mod, detour可触发)。"""
import ctypes
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from soku_client import SokuInstance  # noqa: E402
from dump_imports import list_modules  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def mods_of(pid):
    try:
        ml = list_modules(pid)
        if isinstance(ml, dict):
            return set(ml.keys())
        return set(m[0].lower() for m in ml)
    except OSError:
        return set()


def main():
    inst = SokuInstance(20764)
    pid = inst.proc.pid
    time.sleep(2.0)
    tm = mods_of(pid)
    print("训练实例PID=%d 模块数=%d dinput8=%s" % (pid, len(tm),
                                                    "dinput8.dll" in tm))
    ref = mods_of(40024)
    print("对照40024 模块数=%d dinput8=%s" % (len(ref), "dinput8.dll" in ref))
    inst.close()


if __name__ == "__main__":
    main()
