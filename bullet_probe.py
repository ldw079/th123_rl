# -*- coding: utf-8 -*-
"""弹幕结构探测器(只读): 从 Player+0x6F8 的 IGameObjectList 扫描 std::list<GameObject*>,
dump 对象(vtable/动作ID/位置/速度/归属), 验证弹幕可枚举。
结构依据 SokuLib 源码(workplace/SokuLobbiesCN-git):
  Player+0x6F8 = objectList;  GameObject: vtable+0, pos+0xEC, speed+0xF4, dir+0x104,
  actionId+0x13C(AnimationObject.FrameState), parentPlayer+0x364, lifetime+0x34C
  std::list (MSVC 32位 release): {head哨兵节点指针, size}; 节点{next, prev, val}
"""
import ctypes
import struct
import sys
import time

sys.path.insert(0, r"%USERPROFILE%\Desktop\workplace\th123_rl")
from capture import find_windows
import config
from hud_sensor import HudSensor, k32
from ctypes import wintypes

OUT = None


def pr(*a):
    print(*a)
    print(*a, file=OUT)


class RawMem:
    """批量读内存(整块读, 减少syscall)。"""

    def __init__(self, pid):
        self.hp = k32.OpenProcess(0x0410, False, pid)  # VM_READ | QUERY_INFORMATION

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.hp, ctypes.c_void_p(addr), buf, n,
                                     ctypes.byref(got)) or got.value != n:
            return None
        return buf.raw


def u32(mem, addr):
    r = mem.read(addr, 4)
    return struct.unpack("<I", r)[0] if r else None


def is_ptr(v):
    return v is not None and 0x10000 <= v < 0x80000000


VT_LO, VT_HI = 0x857000, 0x882000   # RDATA 段: 合法 vtable 区间(SokuAddresses)


def obj_sane(mem, o):
    """GameObject 合法性: vtable 在 RDATA + 坐标/动作在合理范围。"""
    if not is_ptr(o):
        return False
    vt = u32(mem, o)
    if vt is None or not (VT_LO <= vt < VT_HI):
        return False
    r = mem.read(o + 0xEC, 16)
    if r is None:
        return False
    x, y, vx, vy = struct.unpack("<ffff", r)
    if not (-1000 < x < 4000 and -1000 < y < 2000):
        return False
    return True


def read_obj(mem, o):
    r = mem.read(o, 8) + mem.read(o + 0x104, 4)
    vt = struct.unpack("<I", r[:4])[0]
    body = mem.read(o + 0xEC, 24)          # x,y,vx,vy,gravity,dir... (取到0x104前)
    x, y, vx, vy = struct.unpack("<ffff", body[:16])
    dirb = struct.unpack("<b", mem.read(o + 0x104, 1))[0]
    act = struct.unpack("<H", mem.read(o + 0x13C, 2))[0]
    life, handle = struct.unpack("<iI", mem.read(o + 0x34C, 8))
    parent = u32(mem, o + 0x364)
    return dict(vt=vt, x=x, y=y, vx=vx, vy=vy, dir=dirb, act=act,
                life=life, parent=parent)


def find_list_offset(mem, base, lo=0x08, hi=0xC0):
    """在 GameObjectList 对象里扫 {head,size}(std::list) 偏移。
    判据: head 合法指针, 1<=size<=400, 且首个节点 val 是合法 GameObject。"""
    for off in range(lo, hi, 4):
        head = u32(mem, base + off)
        size = u32(mem, base + off + 4)
        if not is_ptr(head) or size is None or not (1 <= size <= 400):
            continue
        node = u32(mem, head)          # head->next = 第一个节点
        if not is_ptr(node) or node == head:
            continue
        val = u32(mem, node + 8)       # 节点{next,prev,val}
        if obj_sane(mem, val):
            return off
    return None


def walk_list(mem, base, off, limit=300):
    head = u32(mem, base + off)
    size = u32(mem, base + off + 4)
    if not is_ptr(head) or size is None:
        return []
    node = u32(mem, head)
    out = []
    for _ in range(min(size, limit)):
        if not is_ptr(node) or node == head:
            break
        val = u32(mem, node + 8)
        if is_ptr(val) and obj_sane(mem, val):
            out.append(val)
        node = u32(mem, node)
    return out


def main():
    global OUT
    OUT = open(r"%s\bullet_probe_out.txt" % __import__("os").environ["TEMP"],
               "w", encoding="utf-8")
    ws = None
    for sub in config.TITLE_CANDIDATES:
        ws = find_windows(sub)
        if ws:
            break
    if not ws:
        pr("NO_WINDOW")
        return
    hwnd, _ = ws[0]
    pid = ctypes.c_uint32()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    sen = HudSensor(pid.value)
    mem = RawMem(pid.value)

    d = sen.read()
    if not d or d["scene"] != 5 or d["battle"] is None:
        pr("不在对局(scene=%s), 退出" % (d["scene"] if d else "?"))
        return
    # 复用 HudSensor 的管理器探测
    bm = sen._bm_addr
    if bm is None:
        pr("battle mgr 未定位")
        return
    lp = u32(mem, bm + 0x0C)
    rp = u32(mem, bm + 0x10)
    pr("bm=0x%X  leftPlayer=0x%X  rightPlayer=0x%X" % (bm, lp or 0, rp or 0))
    for tag, player in (("L", lp), ("R", rp)):
        if not is_ptr(player):
            pr("%s: 无效" % tag)
            continue
        ci = struct.unpack("<i", mem.read(player + 0x34C, 4))[0]
        pr("%s: charIndex=%d  objectList=0x%X" %
           (tag, ci, u32(mem, player + 0x6F8) or 0))

    players = {"L": lp, "R": rp}
    for frame in range(6):
        d = sen.read()
        if not d or d["battle"] is None:
            pr("frame %d: 对局中断" % frame)
            break
        L, R = d["battle"]["left"], d["battle"]["right"]
        pr("\n== frame %d  我(%.0f,%.0f) 对手(%.0f,%.0f) dx=%.0f  对手灵力=%d 对手动作=%d"
           % (frame, L["x"] or 0, L["y"] or 0, R["x"] or 0, R["y"] or 0,
              abs((L["x"] or 0) - (R["x"] or 0)), R["spirit"], R["action"] or -1))
        for tag, player in players.items():
            if not is_ptr(player):
                continue
            ol = u32(mem, player + 0x6F8)
            if not is_ptr(ol):
                continue
            off = find_list_offset(mem, ol)
            if off is None:
                pr(" %s: 列表偏移未找到" % tag)
                continue
            objs = walk_list(mem, ol, off)
            pr(" %s: listOff=0x%X 对象数=%d" % (tag, off, len(objs)))
            for o in objs[:12]:
                ob = read_obj(mem, o)
                own = "L" if ob["parent"] == lp else "R" if ob["parent"] == rp else "?"
                pr("   [0x%X] vt=0x%X act=%-4d (%7.0f,%6.0f) v(%5.1f,%5.1f) dir=%d life=%d own=%s"
                   % (o, ob["vt"], ob["act"], ob["x"], ob["y"],
                      ob["vx"], ob["vy"], ob["dir"], ob["life"], own))
        time.sleep(0.25)
    pr("\n探测完成")
    OUT.close()


if __name__ == "__main__":
    main()
    print("done")
