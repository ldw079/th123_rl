# -*- coding: utf-8 -*-
"""弹幕传感器(只读): 枚举对局中双方 GameObject 列表, 输出运动对象(弹幕)聚合。

结构依据 SokuLib 源码(workplace/SokuLobbiesCN-git)与 bullet_probe.py 实测:
  Player+0x6F8 = IGameObjectList*; std::list<GameObject*> 偏移运行时扫描(实测 0x5C)
  GameObject: pos+0xEC(2f) speed+0xF4(2f) dir+0x104(c) actionId+0x13C(u16)
              parentPlayer+0x364(ptr)
坐标系: 与角色管理器同源, x 向右, y 正向下(地面=0, 早苗脚下UI物件 y≈375-422 实测)。
过滤: |v|>0.5 的"运动对象"=弹幕候选; 角色本体对象(位于角色坐标±60内)剔除;
      静止持久物件(gauge 等)自然被运动过滤排除。
边界: 只读屏幕可见数值(用户裁定弹幕位置可读); 严禁写入; 不读对手输入。
"""
import struct

VT_LO, VT_HI = 0x857000, 0x882000     # RDATA: 合法 vtable 区间
MOVE_EPS = 0.5                         # 运动阈值(world/frame)
CHAR_EXCL = 60.0                       # 与角色坐标距<此值视为角色本体对象
WALK_LIMIT = 300                       # 链表最大步数(防坏指针死循环)
OBJ_LIMIT = 60                         # 单边最多取多少对象


class BulletSensor:
    """attach 在 HudSensor 之上(复用其进程句柄与 battle manager 探测)。"""

    def __init__(self, sen):
        self.sen = sen
        self._lp = None       # 左 Player 指针(缓存, 失效自动重探)
        self._rp = None
        self._loff = {}       # objectList指针 -> list偏移(缓存)

    # ---- 基础读(走 HudSensor 的句柄) ----
    def _read(self, addr, n):
        return self.sen._read(addr, n)

    def _u32(self, addr):
        r = self._read(addr, 4)
        return struct.unpack("<I", r)[0] if r else None

    @staticmethod
    def _is_ptr(v):
        return v is not None and 0x10000 <= v < 0x80000000

    def _players(self):
        bm = self.sen._bm_addr or self.sen._battle_mgr()
        if bm is None:
            return None, None
        return self._u32(bm + 0x0C), self._u32(bm + 0x10)

    def _list_offset(self, ol):
        """扫描 GameObjectList 内 {head,size}(std::list) 偏移, 结果缓存。
        判据: head 合法, 1<=size<=400, 首节点 val 是合法 GameObject(vtable 在 RDATA, 坐标有限)。"""
        if ol in self._loff:
            return self._loff[ol]
        off_found = None
        for off in range(0x08, 0xC0, 4):
            head = self._u32(ol + off)
            size = self._u32(ol + off + 4)
            if not self._is_ptr(head) or size is None or not (1 <= size <= 400):
                continue
            node = self._u32(head)
            if not self._is_ptr(node) or node == head:
                continue
            val = self._u32(node + 8)
            if not self._is_ptr(val):
                continue
            vt = self._u32(val)
            if vt is None or not (VT_LO <= vt < VT_HI):
                continue
            r = self._read(val + 0xEC, 8)
            if r is None:
                continue
            x, y = struct.unpack("<ff", r)
            if -1000 < x < 4000 and -1000 < y < 2000:
                off_found = off
                break
        self._loff[ol] = off_found
        return off_found

    def _walk(self, ol):
        """遍历一侧对象列表 -> [(act,x,y,vx,vy,dir), ...](仅合法对象, 限 OBJ_LIMIT)。"""
        off = self._list_offset(ol)
        if off is None:
            return []
        head = self._u32(ol + off)
        size = self._u32(ol + off + 4)
        if not self._is_ptr(head) or not size:
            return []
        node = self._u32(head)
        out = []
        for _ in range(min(size, WALK_LIMIT)):
            if not self._is_ptr(node) or node == head or len(out) >= OBJ_LIMIT:
                break
            val = self._u32(node + 8)
            node = self._u32(node)
            if not self._is_ptr(val):
                continue
            # 一次读 0xEC..0x13E: pos, speed, gravity, dir, ..., actionId
            r = self._read(val + 0xEC, 0x52)
            if r is None:
                continue
            x, y, vx, vy = struct.unpack_from("<ffff", r, 0)
            # y约定修正(2026-09-08实测: 本构建y轴朝上, 地面=0腾空=正) —
            # 与HudSensor._char同步翻号归一为"负=空中", 保弹幕网格纵向分层
            y = -y
            vy = -vy
            if not (-1000 < x < 4000 and -1000 < y < 2000):
                continue
            dirb = struct.unpack_from("<b", r, 0x18)[0]
            act = struct.unpack_from("<H", r, 0x50)[0]
            out.append((act, x, y, vx, vy, dirb))
        return out

    def read(self, own_x, opp_x, own_y=0.0, opp_y=0.0):
        """返回 {'own': [...], 'opp': [...], 'nearest': d or None}
        列表元素: (act,x,y,vx,vy) — 运动中(弹幕候选), 已剔除角色本体。
        nearest: 对手运动对象到我方的最近距离(仅 y<200, 排除脚下UI层)。"""
        lp, rp = self._players()
        if not self._is_ptr(lp) or not self._is_ptr(rp):
            return None
        raw_l = self._walk(self._u32(lp + 0x6F8)) if self._is_ptr(self._u32(lp + 0x6F8)) else []
        olr = self._u32(rp + 0x6F8)
        raw_r = self._walk(olr) if self._is_ptr(olr) else []
        if not raw_l and not raw_r:
            # 双列表空: 指针可能过期, 强制下次重扫
            self._loff.clear()
            return None

        def filt(objs, cx, cy):
            res = []
            for act, x, y, vx, vy, _d in objs:
                if abs(vx) + abs(vy) <= MOVE_EPS:
                    continue
                if cx is not None and abs(x - cx) < CHAR_EXCL and abs(y - cy) < CHAR_EXCL:
                    continue     # 角色本体对象
                res.append((act, x, y, vx, vy))
            return res

        own = filt(raw_l, own_x, own_y)
        opp = filt(raw_r, opp_x, opp_y)
        nearest = None
        near_xy = None
        if own_x is not None:
            for _a, x, y, _vx, _vy in opp:
                if y > 200:
                    continue     # 脚下UI层(大妈槽等)
                d = ((x - own_x) ** 2 + (y - own_y) ** 2) ** 0.5
                if nearest is None or d < nearest:
                    nearest = d
                    near_xy = (x, y)
        return {"own": own, "opp": opp, "nearest": nearest, "near_obj": near_xy}
