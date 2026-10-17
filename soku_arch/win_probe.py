# -*- coding: utf-8 -*-
"""Windows 侧最小探测原语：窗口置前台 + 只读内存观察。

来源（只读引用）：C:\\Users\\96120\\Desktop\\workplace\\th123_rl\\test_focus.py
  * 后台进程调用 SetForegroundWindow 会被 Windows 前台锁拦掉，
    参考实现用 AttachThreadInput 把当前线程挂到前台线程与目标线程上再设置，实测有效。
  * 该脚本还有"填输入管理器表"和"踢场景字节"两处**内存写**——
    本模块**刻意只实现只读部分**：先把状态看清楚，写操作另行决定（且写入的是
    游戏进程内存，必须先确认地址属于当前 build，不能沿用其他血统脚本里的常量）。

地址常量标注为 UNVERIFIED：`test_focus.py` 的 0x8A0044 / 0x8986A8 / 0x898680
来自 SokuAIOfflinePlayer 血统的脚本，**未必适用**于当前部署的 SokuAITrainer 血统，
因此只用于"读数观察并在报告里标注可疑"，不作为决策依据。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400

# UNVERIFIED（见模块 docstring）
SCENE_ADDR = 0x8A0044
MGR_ADDR = 0x8986A8
TBL_ADDR = 0x898680

# **已实测确认**（非 UNVERIFIED）：`GameStartParams.randomSeed` 的地址。
# 推导过程（`tools/gameparams_scan.py` 的实测输出）：
#   * 用已知指纹（角色 u32 + isRight + palette）在可写区反查，命中
#     `P_left=0x00899D10`、`P_right=0x00899D30` → `sizeof(PlayerInfo)=32`
#   * 于是 `randomSeed = P_right + 32 = 0x00899D50`（= ADDR_GAME_PARAMS + 0x48）
#   * 该处读到随机样值 `0x6AB374FB`；写入 790798525 后**回读一致** ✓
# 注：SokuAddresses.hpp:170 的 ADDR_GAME_PARAMS=0x00899D08 因此**在本 build 上成立**；
#     先前"查不到卡组指纹"是因为卡组在 Deque 的**堆缓冲**上，不在结构体内。
SEED_ADDR = 0x00899D50

# --------------------------------------------------------------------------
# 内存区域遍历 + 模式扫描（用于"用已知指纹定位结构体"）
# --------------------------------------------------------------------------
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_READONLY = 0x02
PAGE_READWRITE = 0x04
PAGE_WRITECOPY = 0x08
PAGE_EXECUTE = 0x10
PAGE_EXECUTE_READ = 0x20
PAGE_EXECUTE_READWRITE = 0x40
PAGE_EXECUTE_WRITECOPY = 0x80
PAGE_GUARD = 0x100
WRITABLE_PROTECTS = {PAGE_READWRITE, PAGE_WRITECOPY,
                     PAGE_EXECUTE_READWRITE, PAGE_EXECUTE_WRITECOPY}


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p),
                ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD),
                ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD),
                ("Protect", wt.DWORD),
                ("Type", wt.DWORD)]


k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.POINTER(MEMORY_BASIC_INFORMATION),
                               ctypes.c_size_t]


def iter_regions(h, writable_only: bool = True):
    """遍历目标进程内存区域，产出 (base, size, protect)。"""
    mbi = MEMORY_BASIC_INFORMATION()
    addr = 0
    limit = 0x7FFFFFFF if ctypes.sizeof(ctypes.c_void_p) == 4 else 0x7FFFFFFF0000
    while addr < limit:
        got = k32.VirtualQueryEx(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                                 ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not got:
            break
        base = mbi.BaseAddress or 0
        size = int(mbi.RegionSize)
        if size <= 0:
            break
        if (mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD)
                and (not writable_only or (mbi.Protect & 0xFF) in WRITABLE_PROTECTS)):
            yield base, size, int(mbi.Protect)
        addr = base + size
        if addr <= base:      # 防死循环
            break


def scan_pattern(h, pattern: bytes, *, writable_only: bool = True,
                 chunk: int = 1 << 20, max_bytes: int = 768 << 20,
                 max_hits: int = 64, overlap: int | None = None) -> list[int]:
    """在目标进程可写区域内搜索字节模式，返回命中地址列表。

    用**远超普通结构体的大模式**（例如 20 张卡的 u16 序列 = 40 字节）作为指纹，
    可把误报压到几乎为零；命中点即结构体内的真实偏移。
    """
    if not pattern:
        return []
    ov = len(pattern) - 1 if overlap is None else overlap
    hits: list[int] = []
    total = 0
    for base, size, _prot in iter_regions(h, writable_only=writable_only):
        off = 0
        while off < size:
            n = min(chunk, size - off)
            data = read_bytes(h, base + off, n)
            if data:
                total += len(data)
                start = 0
                while True:
                    j = data.find(pattern, start)
                    if j < 0:
                        break
                    hits.append(base + off + j)
                    if len(hits) >= max_hits:
                        return hits
                    start = j + 1
                if total > max_bytes:
                    return hits
            off += n - ov if n > ov else n
    return hits


def find_window(pid: int) -> int | None:
    """按 pid 找第一个可见顶层窗口。"""
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lparam):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def force_foreground(hwnd: int) -> bool:
    """把窗口置前（AttachThreadInput 绕过前台锁）。"""
    fg = u32.GetForegroundWindow()
    fg_tid = u32.GetWindowThreadProcessId(ctypes.c_void_p(fg), None)
    this_tid = k32.GetCurrentThreadId()
    tgt_tid = u32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), None)
    u32.AttachThreadInput(this_tid, fg_tid, True)
    u32.AttachThreadInput(this_tid, tgt_tid, True)
    ok = u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    u32.AttachThreadInput(this_tid, fg_tid, False)
    u32.AttachThreadInput(this_tid, tgt_tid, False)
    return bool(ok) and u32.GetForegroundWindow() == hwnd


def open_for_read(pid: int) -> int | None:
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    return h or None


def open_for_write(pid: int) -> int | None:
    """读写权限句柄（用于输入管理器表填充；调用方必须先读后写并记录原值）。"""
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
                        | PROCESS_QUERY_INFORMATION, False, pid)
    return h or None


def write_bytes(h, addr: int, data: bytes) -> bool:
    n = len(data)
    buf = ctypes.create_string_buffer(data, n)
    written = ctypes.c_size_t()
    ok = k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr), buf, n,
                                ctypes.byref(written))
    return bool(ok) and written.value == n


def read_bytes(h, addr: int, n: int) -> bytes | None:
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr), buf, n,
                                  ctypes.byref(got)):
        return None
    return buf.raw


def read_u8(h, addr: int) -> int | None:
    b = read_bytes(h, addr, 1)
    return b[0] if b else None


def read_i32(h, addr: int) -> int | None:
    b = read_bytes(h, addr, 4)
    if not b:
        return None
    return int.from_bytes(b, "little", signed=True)


# --------------------------------------------------------------------------
# 程序化拖放（用于 ReplayDnD mod 的"拖入 rep 即播放"）
# --------------------------------------------------------------------------
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04
WM_DROPFILES = 0x0233

k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                               ctypes.c_uint32, ctypes.c_uint32]


def find_all_windows(pid: int) -> list[int]:
    """该 pid 的所有可见顶层窗口（拖放目标可能不是第一个）。"""
    out: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lparam):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(hwnd):
            out.append(hwnd)
        return True

    u32.EnumWindows(cb, 0)
    return out


def _make_drop_blob(paths: list[str], wide: bool) -> bytes:
    if wide:
        blob = b"".join(p.encode("utf-16-le") + b"\x00\x00" for p in paths) + b"\x00\x00"
    else:
        blob = b"".join(p.encode("mbcs") + b"\x00" for p in paths) + b"\x00"
    return struct.pack("<IiiII", 20, 0, 0, 0, 1 if wide else 0) + blob


def _drop_with(h, hwnd: int, paths: list[str], poster: bool) -> bool:
    for wide in (True, False):
        data = _make_drop_blob(paths, wide)
        size = len(data)
        addr = k32.VirtualAllocEx(ctypes.c_void_p(h), None, size,
                                  MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        if not addr:
            return False
        try:
            buf = ctypes.create_string_buffer(data, size)
            written = ctypes.c_size_t()
            if not k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr),
                                          buf, size, ctypes.byref(written)):
                continue
            fn = u32.PostMessageW if poster else u32.SendMessageW
            fn(ctypes.c_void_p(hwnd), WM_DROPFILES, ctypes.c_void_p(addr), 0)
            return True
        finally:
            k32.VirtualFreeEx(ctypes.c_void_p(h), ctypes.c_void_p(addr), 0, MEM_RELEASE)
    return False


def send_drop(h, hwnd: int, paths: list[str]) -> bool:
    return _drop_with(h, hwnd, paths, poster=False)


def post_drop(h, hwnd: int, paths: list[str]) -> bool:
    return _drop_with(h, hwnd, paths, poster=True)


def drop_files(h, hwnd: int, paths: list[str], wide: bool = True) -> bool:
    """向目标窗口投递 WM_DROPFILES（在被投递进程内分配 DROPFILES 结构）。

    DROPFILES 布局（winuser.h）:
        DWORD pFiles(20); POINT pt; BOOL fNC; BOOL fWide;
    之后是文件列表（宽字符时 UTF-16LE，路径含中文必须用宽字符）。
    """
    data = _make_drop_blob(paths, wide)
    size = len(data)
    addr = k32.VirtualAllocEx(ctypes.c_void_p(h), None, size,
                              MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
    if not addr:
        return False
    try:
        buf = ctypes.create_string_buffer(data, size)
        written = ctypes.c_size_t()
        if not k32.WriteProcessMemory(ctypes.c_void_p(h), ctypes.c_void_p(addr), buf,
                                      size, ctypes.byref(written)):
            return False
        if written.value != size:
            return False
        u32.SendMessageW(ctypes.c_void_p(hwnd), WM_DROPFILES, ctypes.c_void_p(addr), 0)
        return True
    finally:
        k32.VirtualFreeEx(ctypes.c_void_p(h), ctypes.c_void_p(addr), 0, MEM_RELEASE)


__all__ = ["find_window", "find_all_windows", "force_foreground", "open_for_read",
           "open_for_write", "read_bytes", "write_bytes", "read_u8", "read_i32",
           "drop_files", "send_drop", "post_drop",
           "iter_regions", "scan_pattern", "SCENE_ADDR", "MGR_ADDR", "TBL_ADDR",
           "SEED_ADDR", "WM_DROPFILES"]
