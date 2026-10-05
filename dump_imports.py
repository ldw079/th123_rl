# -*- coding: utf-8 -*-
"""只读转储目标进程中模块的PE导入表(不写任何内存)。
用于确定th123到底通过哪个API读键盘:
  user32!GetKeyboardState / GetAsyncKeyState / GetKeyState
  dinput8!GetDeviceState (DirectInput)
64位Python读32位游戏进程: ReadProcessMemory跨位数安全。"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

k32 = ctypes.windll.kernel32

TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("th32ModuleID", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("GlblcntUsage", wt.DWORD),
        ("ProccntUsage", wt.DWORD),
        ("modBaseAddr", ctypes.POINTER(wt.BYTE)),
        ("modBaseSize", wt.DWORD),
        ("hModule", wt.HMODULE),
        ("szModule", ctypes.c_wchar * 256),
        ("szExePath", ctypes.c_wchar * 260),
    ]


def list_modules(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == -1 or snap == 0xFFFFFFFF:
        raise OSError("CreateToolhelp32Snapshot失败")
    me = MODULEENTRY32W()
    me.dwSize = ctypes.sizeof(MODULEENTRY32W)
    mods = []
    ok = k32.Module32FirstW(snap, ctypes.byref(me))
    while ok:
        mods.append((me.szModule, ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value or 0,
                     me.modBaseSize))
        ok = k32.Module32NextW(snap, ctypes.byref(me))
    k32.CloseHandle(snap)
    return mods


def rpm(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def cstr(raw):
    i = raw.find(b"\x00")
    return raw[:i if i >= 0 else len(raw)].decode("ascii", "replace")


def dump_imports(h, base):
    """解析PE32导入目录, 返回 {dll_name: [func_name, ...]}。只读。"""
    hdr = rpm(h, base, 0x400)
    if not hdr:
        return {}
    e_lfanew = struct.unpack_from("<I", hdr, 0x3C)[0]
    if hdr[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        return {}
    machine = struct.unpack_from("<H", hdr, e_lfanew + 4)[0]
    opt_off = e_lfanew + 24
    magic = struct.unpack_from("<H", hdr, opt_off)[0]
    if magic != 0x10B:  # PE32
        return {"<err>": ["machine=0x%X magic=0x%X" % (machine, magic)]}
    imp_rva = struct.unpack_from("<I", hdr, opt_off + 96 + 8)[0]  # DataDirectory[1]
    if not imp_rva:
        return {}

    out = {}
    desc = rpm(h, base + imp_rva, 20 * 64)
    if not desc:
        return {}
    for i in range(64):
        off = i * 20
        oft, ts, fwd, name_rva, ft = struct.unpack_from("<IIIII", desc, off)
        if name_rva == 0 and (oft == 0 and ft == 0):
            break
        dll_raw = rpm(h, base + name_rva, 64)
        if not dll_raw:
            continue
        dll = cstr(dll_raw).lower()
        thunk_rva = oft or ft
        funcs = []
        j = 0
        while True:
            t = rpm(h, base + thunk_rva + j * 4, 4)
            if not t:
                break
            val = struct.unpack("<I", t)[0]
            if val == 0:
                break
            if val & 0x80000000:
                funcs.append("#ord%d" % (val & 0xFFFF))
            else:
                nb = rpm(h, base + val, 64)
                if nb:
                    funcs.append(cstr(nb[2:]))
            j += 1
            if j > 2048:
                break
        out[dll] = funcs
    return out


INTEREST = ("keyboard", "async", "getkey", "device", "input", "directinput",
            "getkeystate")


def main():
    from capture import find_windows
    u32 = ctypes.windll.user32
    seen = set()
    for hwnd, title in find_windows("非想天"):
        pid = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in seen or not pid.value:
            continue
        seen.add(pid.value)
        print("=== PID=%d  %s" % (pid.value, title))

        h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid.value)
        if not h:
            print("  OpenProcess失败")
            continue
        mods = list_modules(pid.value)
        print("  模块数=%d" % len(mods))
        for name, base, size in mods:
            if name.lower() not in ("th123.exe", "th105.exe", "dinput8.dll", "dinput.dll"):
                continue
            if name.lower() in seen:
                pass
            imps = dump_imports(h, base)
            print("  -- %s base=0x%X size=0x%X 导入%d个DLL" % (name, base, size, len(imps)))
            for dll, funcs in sorted(imps.items()):
                print("     %-16s %3d项" % (dll, len(funcs)))
                for f in funcs:
                    print("        %s" % f)
        k32.CloseHandle(h)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
