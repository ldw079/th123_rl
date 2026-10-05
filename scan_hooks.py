# -*- coding: utf-8 -*-
"""重扫全部模块导入表: 谁导入了钩子/输入安装类API。只读。"""
import ctypes
import sys

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from dump_imports import list_modules, dump_imports  # noqa: E402
from bridge_inject import PROCESS_VM_READ, PROCESS_QUERY_INFORMATION  # noqa: E402

k32 = ctypes.windll.kernel32

HOOK_APIS = {"setwindowshookexw", "setwindowshookexa", "unhookwindowshookex",
             "callnexthookex", "getrawinputdata", "registerrawinputdevices",
             "sendinput", "keybd_event", "getasynckeystate", "getkeyboardstate"}


def main(pid):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    mods = list_modules(pid)
    for name, base, _sz in sorted(mods, key=lambda m: m[1]):
        imps = dump_imports(h, base)
        hits = {}
        for dll, funcs in imps.items():
            f = [x for x in funcs if x.lower() in HOOK_APIS]
            if f:
                hits[dll] = f
        if hits:
            print("%-28s base=0x%08X" % (name.lower(), base))
            for dll, f in sorted(hits.items()):
                print("   %-14s %s" % (dll, ", ".join(f)))
    k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 13916)
