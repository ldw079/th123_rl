# -*- coding: utf-8 -*-
r"""B-3(顶端标尺v2§B-3): 人测会话runner v1 — RPM观察+内存写行动.

链路(全部已实证): 原版游戏(RPM读局面, 5帧公平垫片) → CS字典合成 →
SideDriver(特征构建+策略采样+宏执行, 与F6评估同构) → 协议输入dict
→ u16战斗位域 → P2 KeymapManager inKeys写入(readInKeys=1).

v1简化(非阻塞项): hand/cardGauge/weather默认值(特征部分降级);
airBorne/hitStop/timeStop默认(恒零区歧义, 待hand/weather专场同解).

用法:
  正式会话(人在场): python tools/human_match_v2.py --char suika
  无头集成测试(回放替代P2): python tools/human_match_v2.py --char suika --headless
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf8')

k32 = ctypes.windll.kernel32
SCENE = 0x8A0044
BM_P = 0x8985E4
OFF = {'hp': (388, '<h'), 'maxSpirit': (1184, '<H'),
       'spirit': (1182, '<H'), 'action': (316, '<H'),
       'sequence': (318, '<H'), 'pose': (320, '<H'),
       'poseFrame': (322, '<H'), 'x': (236, '<f'), 'y': (240, '<f'),
       'direction': (260, '<b'), 'score': (1395, '<B')}
OFF_INKEYS, OFF_READIN = 0x60, 0x64
DELAY_FRAMES = 5            # C'裁定: 80ms≈5帧观察延迟
BIT = {'up': 0, 'down': 1, 'left': 2, 'right': 3, 'A': 4, 'B': 5,
       'C': 6, 'D': 7, 'SC': 8, 'SW': 9, 'pause': 10, 'select': 11}
from kit_config import GAME_DIR as GAME
EXE_MD5 = 'DF35D1FBC7B583317ADABE8CD9F53B2E'   # exe哈希守卫(版本漂移即拒)
W_ACT, W_DISP, W_CNT = 0x8971C0, 0x8971C4, 0x8971CC   # SokuAddresses实证
WEATHER_SEIRAN, WEATHER_AURORA, WEATHER_CLEAR = 11, 19, 0


def keys_u16(d):
    """协议输入dict → BattleKeys u16。

    协议格式(宏执行器输出): H=-1左/+1右, V=-1上/+1下, A/B/C/D/SC/SW=bool
    BattleKeys位域: up/down/left/right是独立位(bits 0-3), 非轴值。
    首测事故(2026-10-13): H/V不在BIT表被静默丢弃 — 模型只会攻击不会动。
    """
    d = d or {}
    v = 0
    h = int(d.get('H', 0) or 0)
    v_ = int(d.get('V', 0) or 0)
    if h > 0:
        v |= 1 << BIT['right']
    elif h < 0:
        v |= 1 << BIT['left']
    if v_ > 0:
        v |= 1 << BIT['down']
    elif v_ < 0:
        v |= 1 << BIT['up']
    for k in ('A', 'B', 'C', 'D', 'SC', 'SW'):
        if d.get(k):
            v |= 1 << BIT[k]
    return v


def find_game():
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name='th123.exe'\" | "
         "Where-Object {$_.CommandLine -notlike '*th123_train*'} | "
         "Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True).stdout.strip().split()
    return int(out[0]) if out else None


class Observer:
    """RPM观察: CS字典合成 + 对象(动画活性) + 5帧公平垫片。"""

    def __init__(self, pid):
        self.h = k32.OpenProcess(0x10 | 0x20 | 0x8 | 0x400, False, pid)
        self.buf = []
        self._obj_prev = {}     # ptr → (x,y,poseFrame) 活性追踪
        import hashlib as _hl
        _md5 = _hl.md5(open(os.path.join(GAME, 'th123.exe'), 'rb')
                       .read()).hexdigest().upper()
        if _md5 != EXE_MD5:
            raise RuntimeError('th123.exe哈希漂移(%s≠%s)'
                               % (_md5[:8], EXE_MD5[:8]))

    def rd(self, a, n):
        b = ctypes.create_string_buffer(n)
        g = ctypes.c_size_t()
        ok = k32.ReadProcessMemory(ctypes.c_void_p(self.h),
                                   ctypes.c_void_p(a), b, n,
                                   ctypes.byref(g))
        return b.raw[:n] if ok and g.value == n else None

    def u32(self, a):
        return struct.unpack('<I', self.rd(a, 4))[0]

    def scene(self):
        r = self.rd(SCENE, 1)
        return r[0] if r else -1

    def _char_dict(self, cm):
        w = self.rd(cm, 0x800)
        if not w:
            return None
        d = {}
        for k, (off, fmt) in OFF.items():
            d[k] = struct.unpack_from(fmt, w, off)[0]
        d['position.x'] = d.pop('x')
        d['position.y'] = d.pop('y')
        # v1默认(非阻塞项)
        d['airBorne'] = False
        d['timeStop'] = 0
        d['hitStop'] = 0
        d['hand'] = self._hand(cm)
        d['cardGauge'] = 0
        d['skills'] = b'\x00' * 15
        d['frameCount'] = d['sequence'] * 60   # 近似(无全局计数器)
        # v1默认: CS字段全集覆盖(缺键即崩的教训)
        d['comboDamage'] = 0
        d['comboLimit'] = 0
        d['airDashCount'] = 0
        d['untech'] = 0
        d['healingCharm'] = 0
        d['confusion'] = 0
        d['swordOfRapture'] = 0
        d['fanLevel'] = d['rodsLevel'] = d['booksLevel'] = 0
        d['dollLevel'] = d['dropLevel'] = 0
        d['dropInvulTimeLeft'] = 0
        d['superArmorHp'] = 0
        d['imageID'] = 0
        d['csd'] = b'\x00' * 20
        d['objectCount'] = 0
        return d

    def _hand(self, cm):
        base = self.u32(cm + 0x5E8 + 4)
        if not 0x10000 < base < 0x80000000:
            return b'\xff' * 10
        nb = self.rd(cm + 0x5E8 + 0x20, 4)
        ncard = struct.unpack('<i', nb)[0] if nb else 0
        if not 0 <= ncard <= 5:
            return b'\xff' * 10
        out = bytearray()
        for i in range(5):
            if i < ncard:
                cpb = self.rd(base + i * 4, 4)
                if cpb:
                    cp = struct.unpack('<I', cpb)[0]
                    cb = self.rd(cp, 4) if 0x10000 < cp < 0x80000000 else None
                    if cb:
                        cid, ccost = struct.unpack('<HH', cb)
                        out += bytes((cid & 0xFF, ccost & 0xFF))
                        continue
            out += b'\xff\xff'
        return bytes(out)

    def _weather(self):
        a = struct.unpack('<i', self.rd(W_ACT, 4))[0]
        d_ = struct.unpack('<i', self.rd(W_DISP, 4))[0]
        c = struct.unpack('<H', self.rd(W_CNT, 2))[0]
        if d_ == WEATHER_AURORA and a != WEATHER_CLEAR:
            a = WEATHER_AURORA
        return {'displayed': d_, 'active': a, 'timer': c}

    def _objects(self, bm):
        """活性对象: 本帧 vs 上帧 position/poseFrame 变化(30帧滑窗)。"""
        out = []
        prev = self._obj_prev
        cur = {}
        for cm_off in (0x0C, 0x10):
            cm = self.u32(bm + cm_off)
            if not 0x10000 < cm < 0x80000000:
                continue
            ol = self.u32(cm + 0x6F8)
            if not 0x10000 < ol < 0x80000000:
                continue
            mf, ml = struct.unpack('<II', self.rd(ol + 0x10, 8))
            if not (0x10000 < mf < 0x80000000 and 0 < ml - mf <= 4096):
                continue
            arr = self.rd(mf, ml - mf)
            for i in range((ml - mf) // 4):
                op = struct.unpack_from('<I', arr, i * 4)[0]
                if not 0x10000 < op < 0x80000000:
                    continue
                ob = self.rd(op, 0x148)
                if not ob:
                    continue
                x, y = struct.unpack_from('<2f', ob, 0xEC)
                if not (0 <= x <= 1300 and 0 <= y <= 800):
                    continue
                pf = struct.unpack_from('<H', ob, 0x142)[0]
                act = struct.unpack_from('<H', ob, 0x13C)[0]
                dirc = struct.unpack_from('<b', ob, 0x104)[0]
                key = (cm_off, op)
                if key in prev and (prev[key][0] != x or prev[key][1] != y
                                    or prev[key][2] != pf):
                    # 活: 与上帧比有变化 → 30帧滑窗续命
                    cur[key] = (x, y, pf, 0)
                elif key in self._obj_live:
                    age = self._obj_live[key]
                    if age < 30:
                        cur[key] = (x, y, pf, age + 1)
                if key in cur:
                    out.append((dirc, round(x, 1), round(y, 1),
                                act, 0, 0, 0))
        self._obj_live = cur
        self._obj_prev = {k: (v[0], v[1], v[2]) for k, v in cur.items()}
        for k, v in prev.items():
            self._obj_prev.setdefault(k, v)
        return out[:48]

    _obj_live = {}

    def read_frame(self):
        """→ (left, right, weather, objs) | None(非战斗)。"""
        sc = self.scene()
        if sc != 5:
            return None
        bm = self.u32(BM_P)
        if not 0x10000 < bm < 0x80000000:
            return None
        left = self._char_dict(self.u32(bm + 0x0C))
        right = self._char_dict(self.u32(bm + 0x10))
        if not left or not right:
            return None
        objs = self._objects(bm)
        weather = self._weather()
        if weather['displayed'] == WEATHER_SEIRAN:
            left['hand'] = b'\xff' * 10
            right['hand'] = b'\xff' * 10
            left['cardGauge'] = 0xFFFF
            right['cardGauge'] = 0xFFFF
        self.buf.append((left, right, weather, objs))
        if len(self.buf) <= DELAY_FRAMES:
            return None
        return self.buf.pop(0)


class Actor:
    """内存写行动: P2 KeymapManager(经battle链解析)。"""

    def __init__(self, obs):
        self.obs = obs
        self.km2 = None

    def attach(self):
        try:   # 场景过渡时指针链瞬态无效 — 防御性try
            bm = self.obs.u32(BM_P)
            cm2 = self.obs.u32(bm + 0x10)
            kmgr = self.obs.u32(cm2 + 0x750)
        except (TypeError, struct.error):
            return False
        if not 0x10000 < kmgr < 0x80000000:
            return False
        self.km2 = self.obs.u32(kmgr)
        ok = 0x10000 < self.km2 < 0x80000000
        if ok:
            self.obs.rd(self.km2 + OFF_INKEYS, 2)   # 触发一次读
            self.orig_rd = self.obs.rd(self.km2 + OFF_READIN, 1)
            wr = ctypes.c_int()
            b = ctypes.create_string_buffer(b'\x01', 1)
            k32.WriteProcessMemory(ctypes.c_void_p(self.obs.h),
                                   ctypes.c_void_p(self.km2 + OFF_READIN),
                                   b, 1, ctypes.byref(wr))
        return ok

    def write(self, inp):
        if not self.km2:
            return
        data = struct.pack('<H', keys_u16(inp))
        wr = ctypes.c_int()
        k32.WriteProcessMemory(ctypes.c_void_p(self.obs.h),
                               ctypes.c_void_p(self.km2 + OFF_INKEYS),
                               ctypes.create_string_buffer(data), 2,
                               ctypes.byref(wr))

    def release(self):
        if self.km2:
            wr = ctypes.c_int()
            k32.WriteProcessMemory(
                ctypes.c_void_p(self.obs.h),
                ctypes.c_void_p(self.km2 + OFF_INKEYS),
                ctypes.create_string_buffer(b'\x00\x00'), 2,
                ctypes.byref(wr))
            k32.WriteProcessMemory(
                ctypes.c_void_p(self.obs.h),
                ctypes.c_void_p(self.km2 + OFF_READIN),
                ctypes.create_string_buffer(self.orig_rd or b'\x00'), 1,
                ctypes.byref(wr))


def headless_boot():
    """无头: 禁SokuAIOfflinePlayer(备份) + argv rep启动 + 置前。"""
    ml = os.path.join(GAME, 'ModLoaderSettings.json')
    bak = ml + '.bak_hmv2'
    import shutil
    shutil.copy2(ml, bak)
    import glob as g
    d = json.load(open(ml, encoding='utf8'))
    d['modules']['modules/SokuAIOfflinePlayer/SokuAIOfflinePlayer.dll']['enabled'] = False
    json.dump(d, open(ml, 'w', encoding='utf8'), ensure_ascii=False)
    rep = None
    for dirpath, _dd, files in os.walk(r'D:\TR丹尼尔棉咖啡等录像精选'):
        for fn in files:
            if fn.lower().endswith('.rep'):
                p = os.path.join(dirpath, fn)
                try:
                    b = open(p, 'rb').read(64)
                    if b[0] == 0xD2 and b[14] in (0, 1, 9) and b[63] in (0, 1, 9) \
                            and os.path.getsize(p) > 50000:
                        rep = p
                        break
                except OSError:
                    continue
        if rep:
            break
    shutil.copy(rep, os.path.join(GAME, 'hmv2_boot.rep'))
    proc = subprocess.Popen([os.path.join(GAME, 'th123.exe'), 'hmv2_boot.rep'],
                            cwd=GAME)
    time.sleep(9)
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
    res = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == proc.pid and user32.IsWindowVisible(h):
            res.append(h)
        return True
    user32.EnumWindows(cb, 0)
    if res:
        fg = user32.GetForegroundWindow()
        ft = user32.GetWindowThreadProcessId(fg, None)
        tt = user32.GetWindowThreadProcessId(res[0], None)
        user32.AttachThreadInput(ft, tt, True)
        user32.BringWindowToTop(res[0])
        user32.SetForegroundWindow(res[0])
        user32.AttachThreadInput(ft, tt, False)
    return proc.pid, bak


def headless_cleanup(pid, bak):
    subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                   capture_output=True)
    if bak and os.path.exists(bak):
        try:
            os.replace(bak, os.path.join(GAME, 'ModLoaderSettings.json'))
        except OSError:
            pass
    try:
        os.remove(os.path.join(GAME, 'hmv2_boot.rep'))
    except OSError:
        pass


def run(char, headless, seconds=90):
    from side_driver import SideDriver
    from kit_config import STORE_DIR   # K2: 四层回落(不绕过kit_config)
    driver = SideDriver(char, 'R')
    driver.load(os.path.join(STORE_DIR, 'model_ppo_%s.npz' % char))
    driver.reset_match()
    print('[hmv2] 模型加载: %s' % char, flush=True)

    bak = None
    if headless:
        pid, bak = headless_boot()
        print('[hmv2] 无头boot PID=%d' % pid, flush=True)
    else:
        # 正式模式: SokuAIOfflinePlayer冻结输入路径(实证) — 会话级
        # 禁用+结束复原(headless同款纪律), 用户无需手动处理
        import shutil
        ml = os.path.join(GAME, 'ModLoaderSettings.json')
        bak = ml + '.bak_hmv2'
        shutil.copy2(ml, bak)
        d = json.load(open(ml, encoding='utf8'))
        d['modules']['modules/SokuAIOfflinePlayer/SokuAIOfflinePlayer.dll']['enabled'] = False
        json.dump(d, open(ml, 'w', encoding='utf8'), ensure_ascii=False)
        print('[hmv2] 已禁SokuAIOfflinePlayer(结束自动复原) — 请(重)启动'
              '原版游戏, VS PLAYER, P2=RL-AI档案, 进对局后自动接管', flush=True)
        pid = find_game()
        if not pid:
            # 等用户启动(最多180s)
            t0 = time.time()
            while time.time() - t0 < 180 and not pid:
                pid = find_game()
                time.sleep(2)
        if not pid:
            os.replace(bak, ml)
            print('[hmv2] 180s无游戏进程 — 配置已复原, 退出', flush=True)
            return 1
    obs = Observer(pid)
    t0 = time.time()
    while time.time() - t0 < 300 and obs.scene() != 5:
        time.sleep(0.5)
    if obs.scene() != 5:
        print('[hmv2] 300s未进战斗 scene=%d' % obs.scene(), flush=True)
        if headless:
            headless_cleanup(pid, bak)
        return 1
    actor = Actor(obs)
    # 锚定阶段优雅等待: VS COM时P2无KeyManager(manager=0) — 观察模式
    # (锚定数据也入session), VS PLAYER进场后自动接管
    if not actor.attach():
        print('[hmv2] P2管理器暂无(VS COM锚定期正常) — 观察模式,'
              ' VS PLAYER进场后自动接管', flush=True)
    else:
        print('[hmv2] 战斗就绪 — P2管理器0x%X, 开始驱动(%ds)' %
              (actor.km2, seconds), flush=True)

    # 会话产物: 系列计分(比分字节)+rep归档+session JSON(B-4消费)
    import glob as _glob
    sess_dir = os.path.join(HERE, 'human_match_sessions')
    os.makedirs(sess_dir, exist_ok=True)
    rep_dir = os.path.join(GAME, 'replay')
    rep_base = set()
    for _dp, _dn, _fns in os.walk(rep_dir):
        for _fn in _fns:
            if _fn.lower().endswith('.rep'):
                rep_base.add(os.path.join(_dp, _fn))
    n = 0
    acts = []
    hp0 = None
    human_w = model_w = 0
    matches = []
    last_scores = (0, 0)
    t_end = time.time() + seconds
    def _end_scores():
        try:
            bm_ = obs.u32(BM_P)
            l_ = obs._char_dict(obs.u32(bm_ + 0x0C))
            r_ = obs._char_dict(obs.u32(bm_ + 0x10))
            if l_ and r_:
                return (l_['score'], r_['score'])
        except Exception:
            pass
        return None
    try:
        while time.time() < t_end:
            if not actor.km2:
                actor.attach()   # VS PLAYER进场后自动接管
            sc_now = obs.scene()
            if sc_now != 5:
                # 对局边界: 记录上一场比分
                if last_scores != (0, 0) and last_scores != (None, None):
                    matches.append(list(last_scores))
                    if last_scores[0] > last_scores[1]:
                        human_w += 1
                    else:
                        model_w += 1
                    print('[hmv2] 场终 %d-%d (系列 人%d-模型%d)' % (
                        last_scores[0], last_scores[1], human_w, model_w),
                        flush=True)
                    last_scores = (0, 0)
                time.sleep(1 / 60)
                continue
            fr = obs.read_frame()
            if fr is None:
                time.sleep(1 / 60)
                continue
            left, right, weather, objs = fr
            if hp0 is None:
                hp0 = (left['hp'], right['hp'])
            last_scores = (left['score'], right['score'])
            if actor.km2:
                try:
                    inp = driver.frame_input(right, left, weather, objs, []) or {}
                except Exception as e:
                    print('[hmv2] 驱动异常(%s) — 中止' % e, flush=True)
                    break
                actor.write(inp)
            acts.append(right.get('action', 0))
            n += 1
            time.sleep(1 / 60)
    finally:
        actor.release()
        if last_scores not in ((0, 0),) and last_scores[0] + last_scores[1] > 0:
            matches.append(list(last_scores))
            if last_scores[0] > last_scores[1]:
                human_w += 1
            else:
                model_w += 1
        # rep归档(会话期间新增)
        new_reps = []
        _hr = r'D:\temp\th123_models\human_reps'
        os.makedirs(_hr, exist_ok=True)
        for _dp, _dn, _fns in os.walk(rep_dir):
            for _fn in _fns:
                _p = os.path.join(_dp, _fn)
                if _fn.lower().endswith('.rep') and _p not in rep_base:
                    import shutil as _sh
                    _dst = os.path.join(_hr,
                                        time.strftime('%Y%m%d_%H%M%S_') + _fn)
                    try:
                        _sh.copy2(_p, _dst)
                        new_reps.append(_dst)
                    except OSError:
                        pass
        # session JSON
        sess = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
                'char': char, 'headless': headless,
                'frames': n, 'matches': matches,
                'human_wins': human_w, 'model_wins': model_w,
                'hp0': hp0, 'new_reps': new_reps,
                'exe_md5': EXE_MD5,
                'delay_frames': DELAY_FRAMES,
                'protocol': 'RPM观察+内存写inKeys(v2)'}
        _sp = os.path.join(sess_dir, 'sess_%s%s.json' % (
            time.strftime('%Y%m%d_%H%M%S'), '_hl' if headless else ''))
        json.dump(sess, open(_sp, 'w', encoding='utf8'),
                  ensure_ascii=False, indent=1)
        print('[hmv2] 会话JSON: %s' % _sp, flush=True)
        print('[hmv2] 完成: %d帧 系列 人%d-模型%d rep归档%d' % (
            n, human_w, model_w, len(new_reps)), flush=True)
        # 配置复原(两种模式统一)
        if bak and os.path.exists(bak):
            os.replace(bak, os.path.join(GAME, 'ModLoaderSettings.json'))
        if headless:
            headless_cleanup(pid, None)   # bak已在上方finally复原
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='suika')
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--seconds', type=int, default=90)
    a = ap.parse_args()
    rc = run(a.char, a.headless, a.seconds)
    sys.stdout.flush()
    os._exit(rc)


if __name__ == '__main__':
    main()
