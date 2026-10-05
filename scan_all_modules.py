# -*- coding: utf-8 -*-
"""列出目标进程全部模块(带路径), 转储游戏目录模块的导入表,
找谁导入了键盘/消息API — 定位真正的输入层。只读。"""
import ctypes
import ctypes.wintypes as wt
import sys

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from dump_imports import list_modules, dump_imports, rpm  # noqa: E402
from bridge_inject import PROCESS_VM_READ, PROCESS_QUERY_INFORMATION  # noqa: E402

k32 = ctypes.windll.kernel32

KEYBOARD_APIS = {
    "getkeyboardstate", "getasynckeystate", "getkeystate", "peekmessagea",
    "peekmessagew", "getmessagea", "getmessagew", "keybd_event", "sendinput",
    "tounicodeex", "toascii", "getrawinputdata", "registerrawinputdevices",
    "mapvirtualkeya", "mapvirtualkeyw", "getkeyboardlayout",
}


def main(pid):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        print("OpenProcess失败")
        return
    mods = list_modules(pid)
    print("PID=%d 模块数=%d" % (pid, len(mods)))
    game_dir_hits = []
    # Toolhelp的szExePath没保留, 用模块名推断 + 全部都转储(系统DLL导入这些API也标记)
    named = [(name.lower(), base) for name, base, _size in mods]
    for name, base in sorted(named, key=lambda kv: kv[1]):
        imps = dump_imports(h, base)
        hits = {}
        for dll, funcs in imps.items():
            f = [x for x in funcs if x.lower() in KEYBOARD_APIS]
            if f:
                hits[dll] = f
        if hits:
            game_dir_hits.append((name, base, hits))
    for name, base, hits in game_dir_hits:
        print("\n%-28s base=0x%08X" % (name, base))
        for dll, f in sorted(hits.items()):
            print("   %-14s %s" % (dll, ", ".join(f)))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
