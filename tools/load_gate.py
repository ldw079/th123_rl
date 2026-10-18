# -*- coding: utf-8 -*-
"""L2 重负载闸门 CPU-H (P-A, 2026-10-18 用户令「CPU 红线要立住」).

背景(2026-10-18 12:00 用户报卡顿): 变异 sweep(2 workers)在沙箱内并发跑
`contract_check` + 行为测试(`test_r17_ppo` 单进程≈5 核), 把**整机** CPU 拉到
85-100%; 而 R14 看门狗只量**训练族进程树**(当时 20-30%)故红线未触发。
R14 语义不变(75/65/6 窗一行不改), 本模块补的是**旁路重负载**的单一入口闸门:

  - 单实例锁 `STORE/heavy.lock` (json: pid/kind/start/workers/log;
    stale = PID 已死 或 超 HEAVY_LOCK_MAX_H=8h, 二次 acquire 拒绝并打印持锁者)
  - 注册表 `STORE/heavy_jobs.json` (退出清理, supervisor/dashboard/审计可读)
  - preflight: 整机 CPU 3×1s 均值 > 55% 拒绝 / 空闲 RAM < 6GB 拒绝 /
    训练族 CPU > 70% 拒绝; **夜间窗 20:00-08:00 自动放行**(窗外需 --allow-day)
  - worker cap: `max(1, min(requested, cores//8))` 硬上限 4
  - 子进程优先级: 本进程降为 BELOW_NORMAL(0x4000) → 子进程继承
  - 运行时监控线程每 5s: 整机>90%×3 窗 / 训练族>75%×3 窗 / RAM<3GB →
    中止自身子进程树(回调) + 清沙箱(回调) + 写报告 + 释放锁
  - 协作停止: `STORE/heavy.stop`(json reason/ts, supervisor/Lead 写) → ≤10s 中止
  - 轨迹: `STORE/heavy_runs/<ts>_<kind>.json` (每 5s 整机/族 CPU 采样, 供审计)
  - 闸门默认**失败=关闭**(拒绝启动), 绝不静默放行; psutil 不可用 →
    整机 CPU 用 ctypes `GetSystemTimes`, 空闲 RAM 用 `GlobalMemoryStatusEx`。

用法(重任务入口):
    from load_gate import acquire
    h = acquire('sweep', workers=2, log='D:\\\\temp\\\\sweep.log')
    if h is None:
        sys.exit(2)             # 拒绝启动
    h.set_abort_callback(_kill_children_and_clean)   # 监控/协作停止时回调
    try:
        ...
        if h.poll_abort(): break
    finally:
        h.release()

环境变量(阈值可调, 不改语义): `TH123_STORE` / `TH123_LOAD_GATE=0`(仅回滚旁路) /
`TH123_HEAVY_MACHINE_MAX` / `TH123_HEAVY_RAM_MIN_GB` / `TH123_HEAVY_FAMILY_MAX` /
`TH123_HEAVY_ALLOW_DAY=1`(等价 --allow-day).
"""
from __future__ import annotations

import atexit
import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:          # 供 `python tools/load_gate.py` 直跑时
    sys.path.insert(0, _ROOT)      # import kit_config(STORE 单源)

# ---- 常量(阈值; 用户可经环境变量调整, 计划书 §2 用户裁定项) ----
HEAVY_LOCK_MAX_H = 8.0
PREFLIGHT_MACHINE_MAX = 55.0    # 整机 3×1s 均值上限
PREFLIGHT_RAM_MIN_GB = 6.0      # 空闲 RAM 下限
PREFLIGHT_FAMILY_MAX = 70.0     # 训练族上限(让路训练)
ABORT_MACHINE_MAX = 90.0        # 运行时整机中止线
ABORT_FAMILY_MAX = 75.0         # 运行时族中止线(R14 红线同值)
ABORT_RAM_MIN_GB = 3.0          # 运行时 RAM 中止线
ABORT_CONSEC = 3                # 连续窗(15s)
MONITOR_INTERVAL_S = 5.0
WORKER_HARD_CAP = 4
NIGHT_START_H, NIGHT_END_H = 20, 8
STOP_STALE_S = 120.0            # heavy.stop 超过 2min 视为上一任务残留

_K32 = ctypes.windll.kernel32


class _FILETIME(ctypes.Structure):
    _fields_ = [('dwLowDateTime', ctypes.c_uint32),
                ('dwHighDateTime', ctypes.c_uint32)]


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [('dwLength', ctypes.c_uint32),
                ('dwMemoryLoad', ctypes.c_uint32),
                ('ullTotalPhys', ctypes.c_uint64),
                ('ullAvailPhys', ctypes.c_uint64),
                ('ullTotalPageFile', ctypes.c_uint64),
                ('ullAvailPageFile', ctypes.c_uint64),
                ('ullTotalVirtual', ctypes.c_uint64),
                ('ullAvailVirtual', ctypes.c_uint64),
                ('ullAvailExtendedVirtual', ctypes.c_uint64)]


def _setup_kernel32():
    """x64 ctypes 签名(必须: 默认 c_int 会把 64 位 HANDLE 截断!).

    审计教训(本文件自测首跑): 未声明 restype/argtypes 时
    `GetCurrentProcess()/OpenProcess()` 的 HANDLE 被截成 32 位 → 优先级
    设置/进程CPU读取静默失效(BELOW_NORMAL 测试假红)。显式声明后固定。
    """
    _K32.GetCurrentProcess.restype = ctypes.c_void_p
    _K32.GetCurrentProcess.argtypes = []
    _K32.OpenProcess.restype = ctypes.c_void_p
    _K32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int,
                                 ctypes.c_uint32]
    _K32.CloseHandle.restype = ctypes.c_int
    _K32.CloseHandle.argtypes = [ctypes.c_void_p]
    _K32.GetExitCodeProcess.argtypes = [ctypes.c_void_p,
                                        ctypes.POINTER(ctypes.c_ulong)]
    _K32.GetExitCodeProcess.restype = ctypes.c_int
    _K32.GetPriorityClass.argtypes = [ctypes.c_void_p]
    _K32.GetPriorityClass.restype = ctypes.c_uint32
    _K32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _K32.SetPriorityClass.restype = ctypes.c_int
    _K32.GetSystemTimes.argtypes = [ctypes.POINTER(_FILETIME),
                                    ctypes.POINTER(_FILETIME),
                                    ctypes.POINTER(_FILETIME)]
    _K32.GetSystemTimes.restype = ctypes.c_int
    _K32.GetProcessTimes.argtypes = [ctypes.c_void_p,
                                     ctypes.POINTER(_FILETIME),
                                     ctypes.POINTER(_FILETIME),
                                     ctypes.POINTER(_FILETIME),
                                     ctypes.POINTER(_FILETIME)]
    _K32.GetProcessTimes.restype = ctypes.c_int
    _K32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMORYSTATUSEX)]
    _K32.GlobalMemoryStatusEx.restype = ctypes.c_int


_setup_kernel32()


# ============================================================ 基础指标
def machine_raw():
    """(idle_100ns, total_100ns) — ctypes GetSystemTimes; None=失败."""
    idle, kern, user = _FILETIME(), _FILETIME(), _FILETIME()
    ok = _K32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern),
                             ctypes.byref(user))
    if not ok:
        return None

    def _v(ft):
        return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)

    total = _v(kern) + _v(user)
    idle_v = _v(idle)
    if total <= 0:
        return None
    return idle_v, total


def machine_pct_from(prev, cur):
    """两次 raw 采样 → 整机 CPU%(busy/total); None=不可判."""
    if prev is None or cur is None:
        return None
    didle = cur[0] - prev[0]
    dtot = cur[1] - prev[1]
    if dtot <= 0:
        return None
    pct = 100.0 * (dtot - didle) / dtot
    return max(0.0, min(100.0, pct))


def free_ram_gb():
    """空闲物理内存 GiB; None=查询失败."""
    st = _MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    if not _K32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return None
    return float(st.ullAvailPhys) / (1024.0 ** 3)


def pid_alive(pid):
    """PID 存活判定(OpenProcess + GetExitCodeProcess==STILL_ACTIVE)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    h = _K32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong(0)
        if not _K32.GetExitCodeProcess(h, ctypes.byref(code)):
            return False
        return code.value == 259           # STILL_ACTIVE
    finally:
        _K32.CloseHandle(h)


_PROC_QUERY = ("Get-CimInstance Win32_Process -Filter "
               "\"Name='python.exe' OR Name='th123.exe'\" | Select-Object "
               "ProcessId,ParentProcessId,KernelModeTime,UserModeTime,"
               "CommandLine | ConvertTo-Json -Compress")


def proc_table(ps_out=None):
    """[(pid, ppid, cpu_s, cmdline)] — CIM 采样; None=失败(不伪造0)."""
    if ps_out is None:
        try:
            out = subprocess.run(
                ['powershell', '-NoProfile', '-Command', _PROC_QUERY],
                capture_output=True, text=True, timeout=25,
                encoding='utf-8', errors='replace')
        except Exception:
            return None
        txt = (out.stdout or '').strip()
    else:
        txt = str(ps_out).strip()
    if not txt:
        return []
    try:
        data = json.loads(txt)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = [data]
    rows = []
    for d in data:
        if not isinstance(d, dict):
            continue
        try:
            cpu = (float(d.get('KernelModeTime') or 0)
                   + float(d.get('UserModeTime') or 0)) / 1e7
            rows.append((int(d['ProcessId']), int(d['ParentProcessId']),
                         cpu, d.get('CommandLine') or ''))
        except (KeyError, TypeError, ValueError):
            continue
    return rows


_FAMILY_CACHE = {'ts': 0.0, 'pids': None}


def family_pids(rows=None, now=None, refresh_s=30.0):
    """训练族进程 pid 集(= 所有 fleet_supervisor.py 进程的整棵进程树)."""
    now = time.time() if now is None else now
    if (rows is None and _FAMILY_CACHE['pids'] is not None
            and now - _FAMILY_CACHE['ts'] < refresh_s):
        return _FAMILY_CACHE['pids']
    if rows is None:
        rows = proc_table()
    if rows is None:
        return None                       # 采样失败 → 哨兵
    roots = [p for p, _pp, _c, cmd in rows
             if 'fleet_supervisor.py' in (cmd or '')
             and 'load_gate' not in (cmd or '')]
    kids = {}
    for p, pp, _c, _cmd in rows:
        kids.setdefault(pp, []).append(p)
    seen, stack = set(), list(roots)
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        stack.extend(kids.get(p, ()))
    _FAMILY_CACHE['ts'], _FAMILY_CACHE['pids'] = now, set(seen)
    return _FAMILY_CACHE['pids']


_PROC_CPU = {}


def proc_cpu_seconds(pid):
    """单进程累计 CPU 秒(GetProcessTimes); None=不可读(进程已退等)."""
    h = _K32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return None
    try:
        created, exited = _FILETIME(), _FILETIME()
        kern, user = _FILETIME(), _FILETIME()
        ok = _K32.GetProcessTimes(h, ctypes.byref(created),
                                  ctypes.byref(exited), ctypes.byref(kern),
                                  ctypes.byref(user))
        if not ok:
            return None

        def _v(ft):
            return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)

        return (_v(kern) + _v(user)) / 1e7
    finally:
        _K32.CloseHandle(h)


def _proc_cpu_map(pids):
    out = {}
    for pid in pids:
        c = proc_cpu_seconds(pid)
        if c is not None:
            out[pid] = c
    return out


class CpuRatio:
    """Δ累计CPU /(Δ墙钟×逻辑核数) 通用比率器(整机/族同构; 首调用 None)."""

    def __init__(self, cores=None):
        self.cores = cores or (os.cpu_count() or 1)
        self.prev = None

    def pct(self, cur_cpu, now=None):
        now = time.time() if now is None else now
        prev = self.prev
        self.prev = (now, cur_cpu)
        if cur_cpu is None:
            return None
        if prev is None or now <= prev[0]:
            return None
        dcpu = cur_cpu - prev[1]
        if dcpu < 0:
            return None
        return max(0.0, min(100.0,
                            100.0 * dcpu / ((now - prev[0]) * self.cores)))


class MachineCpu:
    def __init__(self):
        self.prev = None

    def pct(self):
        cur = machine_raw()
        if cur is None:
            return None
        prev, self.prev = self.prev, cur
        return machine_pct_from(prev, cur)


_FAMILY_RATIO = CpuRatio()
_MACHINE = MachineCpu()


def family_pct(now=None, rows=None):
    """训练族 CPU%(与 R14 同口径); None=采样失败哨兵."""
    pids = family_pids(rows=rows, now=now)
    if pids is None:
        return None
    cur = sum(_proc_cpu_map(pids).values()) if pids else 0.0
    return _FAMILY_RATIO.pct(cur, now=now)


def sample_metrics(now=None):
    """(整机%, 族%, 空闲RAM GiB) — monitor/预检共用; 单项失败=None."""
    return (_MACHINE.pct(),
            family_pct(now=now),
            free_ram_gb())


# ============================================================ 阈值 / 窗口
def _thr():
    def _e(k, d):
        try:
            return float(os.environ.get(k, d))
        except ValueError:
            return float(d)
    return {
        'machine_max': _e('TH123_HEAVY_MACHINE_MAX', PREFLIGHT_MACHINE_MAX),
        'ram_min': _e('TH123_HEAVY_RAM_MIN_GB', PREFLIGHT_RAM_MIN_GB),
        'family_max': _e('TH123_HEAVY_FAMILY_MAX', PREFLIGHT_FAMILY_MAX),
    }


def in_night_window(now=None):
    now = time.time() if now is None else now
    h = time.localtime(now).tm_hour
    return h >= NIGHT_START_H or h < NIGHT_END_H


def worker_cap(requested, cores=None):
    """max(1, min(requested, cores//8)) 且硬上限 4 (18核→2)."""
    cores = cores or (os.cpu_count() or 1)
    try:
        req = int(requested)
    except (TypeError, ValueError):
        req = 1
    req = max(1, req)
    derived = max(1, min(req, max(1, cores // 8)))
    return max(1, min(derived, WORKER_HARD_CAP))


class AbortJudge:
    """运行时中止判定(纯函数式, 可注入测试): 连续 3 窗 / RAM 立即."""

    def __init__(self, machine_max=ABORT_MACHINE_MAX,
                 family_max=ABORT_FAMILY_MAX, ram_min=ABORT_RAM_MIN_GB,
                 consec=ABORT_CONSEC):
        self.machine_max = machine_max
        self.family_max = family_max
        self.ram_min = ram_min
        self.consec = max(1, int(consec))
        self._m = 0
        self._f = 0

    def feed(self, machine, family, ram_gb):
        """返回中止原因(str) 或 None。family=None=采样失败(不据此中止)。"""
        if ram_gb is not None and ram_gb < self.ram_min:
            return '空闲RAM<%.1fGB(%.2fGB)' % (self.ram_min, ram_gb)
        self._m = self._m + 1 if (machine is not None
                                  and machine > self.machine_max) else 0
        self._f = self._f + 1 if (family is not None
                                  and family > self.family_max) else 0
        if self._m >= self.consec:
            return '整机CPU>%.0f%%×%d窗(%.1f%%)' % (
                self.machine_max, self.consec, machine)
        if self._f >= self.consec:
            return '训练族CPU>%.0f%%×%d窗(%.1f%%)' % (
                self.family_max, self.consec, family)
        return None


# ============================================================ 锁 / 注册表
def store_dir(store=None):
    if store:
        return store
    if os.environ.get('TH123_STORE'):
        return os.environ['TH123_STORE']
    try:
        import kit_config
        return kit_config.STORE_DIR
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'data', 'models')


def paths(store=None):
    st = store_dir(store)
    return {
        'store': st,
        'lock': os.path.join(st, 'heavy.lock'),
        'jobs': os.path.join(st, 'heavy_jobs.json'),
        'stop': os.path.join(st, 'heavy.stop'),
        'runs': os.path.join(st, 'heavy_runs'),
    }


def _read_json(p, default=None):
    try:
        with open(p, encoding='utf8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json_atomic(p, obj):
    tmp = p + '.tmp.%d' % os.getpid()
    with open(tmp, 'w', encoding='utf8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _pid_of(rec):
    try:
        return int(rec.get('pid'))
    except (TypeError, ValueError, AttributeError):
        return -1


def lock_is_stale(rec, now, max_h=HEAVY_LOCK_MAX_H, alive_fn=None):
    """锁 stale: 缺 pid / PID 已死 / 超 8h."""
    if not isinstance(rec, dict):
        return True, '锁档损坏'
    alive = alive_fn or pid_alive
    pid = _pid_of(rec)
    if pid <= 0 or not alive(pid):
        return True, 'PID %s 已不存在' % (pid,)
    try:
        started = float(rec.get('start') or 0)
    except (TypeError, ValueError):
        started = 0.0
    if started <= 0 or now - started > max_h * 3600.0:
        return True, '持锁%.1fh>上限%.0fh' % (
            (now - started) / 3600.0 if started else -1, max_h)
    return False, ''


def registry_add(store, rec):
    p = paths(store)['jobs']
    jobs = _read_json(p, {'jobs': []}) or {'jobs': []}
    lst = [j for j in jobs.get('jobs', []) if pid_alive(_pid_of(j))]
    lst.append(rec)
    _write_json_atomic(p, {'jobs': lst})


def registry_remove(store, pid):
    p = paths(store)['jobs']
    cur = _read_json(p, None)
    if cur is None:
        return
    lst = [j for j in cur.get('jobs', [])
           if _pid_of(j) != int(pid) and pid_alive(_pid_of(j))]
    if lst:
        _write_json_atomic(p, {'jobs': lst})
    else:
        try:
            os.remove(p)
        except OSError:
            pass


# ============================================================ 进程优先级
PRIORITY_BELOW_NORMAL = 0x4000
PRIORITY_NORMAL = 0x0020


def get_priority():
    return int(_K32.GetPriorityClass(_K32.GetCurrentProcess()))


def set_priority(cls):
    return bool(_K32.SetPriorityClass(_K32.GetCurrentProcess(), int(cls)))


# ============================================================ preflight
def preflight(store=None, allow_day=False, now=None, gap=1.0,
              inject=None, quiet=False):
    """启动前检查 → (ok, reason, readings)。inject 仅测试注入。"""
    inject = inject or {}
    now = float(inject['now']) if 'now' in inject else (
        time.time() if now is None else now)
    readings = {'time': time.strftime('%Y-%m-%d %H:%M:%S',
                                       time.localtime(now)),
                'night_window': in_night_window(now)}
    thr = _thr()
    # ① 夜间窗(20:00-08:00 自动放行; 窗外需 --allow-day)
    if not readings['night_window'] and not (
            allow_day or os.environ.get('TH123_HEAVY_ALLOW_DAY') == '1'):
        reason = ('窗外(%s, 夜间窗 %02d:00-%02d:00)需 --allow-day 显式放行'
                  % (readings['time'], NIGHT_START_H, NIGHT_END_H))
        if not quiet:
            print('[load_gate] !! 拒绝: ' + reason)
        return False, reason, readings
    # ② 整机 CPU 3×1s 均值
    if 'machine_series' in inject:
        series = [float(x) for x in inject['machine_series']]
    else:
        series = []
        prev = machine_raw()
        for _i in range(3):
            if gap:
                time.sleep(gap)
            cur = machine_raw()
            p = machine_pct_from(prev, cur)
            if p is not None:
                series.append(p)
            prev = cur
    if not series:
        reason = '整机CPU采样失败(保守拒绝)'
        if not quiet:
            print('[load_gate] !! 拒绝: ' + reason)
        return False, reason, readings
    machine = sum(series) / len(series)
    readings['machine_pct'] = round(machine, 2)
    readings['machine_series'] = [round(x, 2) for x in series]
    # ③ 空闲 RAM
    ram = (float(inject['ram_gb']) if 'ram_gb' in inject else free_ram_gb())
    readings['free_ram_gb'] = None if ram is None else round(ram, 2)
    # ④ 训练族 CPU (用真实墙钟采样 — 不可传注入 now: 夜间窗的"未来"时点会
    #    让比率器时间回退 → 恒 None; 本文件自测/首次夜窗预检实弹抓到)
    if 'family_pct' in inject:
        fam = inject['family_pct']
        fam = None if fam is None else float(fam)
    else:
        _p1 = family_pct()
        if gap:
            time.sleep(gap)
        fam = family_pct()
        if fam is None:
            fam = _p1
    readings['family_pct'] = None if fam is None else round(fam, 2)
    if machine > thr['machine_max']:
        reason = ('整机CPU均值%.1f%% > %.0f%%' % (machine,
                                                  thr['machine_max']))
    elif ram is None:
        reason = '空闲RAM查询失败(保守拒绝)'
    elif ram < thr['ram_min']:
        reason = '空闲RAM %.2fGB < %.0fGB' % (ram, thr['ram_min'])
    elif fam is None:
        reason = '训练族CPU采样失败(保守拒绝)'
    elif fam > thr['family_max']:
        reason = '训练族CPU %.1f%% > %.0f%%(让路训练)' % (fam,
                                                     thr['family_max'])
    else:
        reason = None
    if reason:
        if not quiet:
            print('[load_gate] !! 拒绝: ' + reason)
            print('[load_gate]    读数: %s' % json.dumps(
                readings, ensure_ascii=False))
        return False, reason, readings
    if not quiet:
        print('[load_gate] preflight OK: %s' % json.dumps(
            readings, ensure_ascii=False))
    return True, None, readings


# ============================================================ handle
class HeavyHandle:
    """acquire() 返回的句柄: 监控线程/协作停止/轨迹/释放. 可幂等释放."""

    def __init__(self, kind, workers, store, log=None, log_info=None,
                 monitor_interval=MONITOR_INTERVAL_S, sampler=None,
                 traj_tag=None):
        self.kind = kind
        self.workers = workers
        self.store = store_dir(store)
        self.p = paths(self.store)
        self.log = log
        self.start = time.time()
        self.monitor_interval = float(monitor_interval)
        self.sampler = sampler or (lambda: sample_metrics())
        self.abort_reason = None
        self.abort_ts = None
        self.traj = []
        self._cb = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._released = False
        self._thread = None
        self._prev_priority = get_priority()
        self._traj_path = os.path.join(
            self.p['runs'], '%s_%s.json' % (
                time.strftime('%Y%m%d_%H%M%S', time.localtime(self.start)),
                traj_tag or kind))
        if log_info is not None:
            self.log_info = log_info
        else:
            self.log_info = {}

    # ---- 生命周期
    @property
    def traj_path(self):
        return self._traj_path

    def start_monitor(self):
        self._thread = threading.Thread(target=self._monitor, name='heavy-mon',
                                        daemon=True)
        self._thread.start()

    def release(self, ok=True, note=None):
        with self._lock:
            if self._released:
                return
            self._released = True
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2.0)
        self._write_traj(final=True, ok=ok, note=note)
        self._del_lock()
        set_priority(self._prev_priority)

    # ---- 协作停止/监控外部接口
    def set_abort_callback(self, cb):
        self._cb = cb

    def poll_abort(self):
        """轮询: heavy.stop 文件 / 监控已判定的中止 → 原因(str)或None."""
        self._check_stop_file()
        with self._lock:
            return self.abort_reason

    @property
    def aborted(self):
        with self._lock:
            return self.abort_reason is not None

    # ---- 内部
    def _check_stop_file(self):
        sp = self.p['stop']
        if not os.path.exists(sp):
            return
        rec = _read_json(sp, None) or {}
        ts = rec.get('ts') if isinstance(rec, dict) else None
        if ts and (time.time() - float(ts) > STOP_STALE_S):
            return
        reason = '协作停止(heavy.stop): %s' % (
            (rec.get('reason') if isinstance(rec, dict) else '') or '未注明')
        self._do_abort(reason)

    def _do_abort(self, reason):
        with self._lock:
            if self.abort_reason is not None:
                return
            self.abort_reason = reason
            self.abort_ts = time.time()
        try:
            self._write_traj(final=False)
        except Exception:
            pass
        self._del_lock()                 # 先释放锁, 别的重任务可接
        cb = self._cb
        if cb is not None:
            try:
                cb(reason)
            except Exception as e:
                print('[load_gate] abort回调异常: %r' % (e,))
        try:
            self._write_traj(final=True, ok=False, note='aborted')
        except Exception:
            pass
        print('[load_gate] !! 已中止: %s' % reason)

    def _monitor(self):
        judge = AbortJudge()
        while not self._stop.is_set():
            if self._stop.wait(self.monitor_interval):
                break
            try:
                self._check_stop_file()
                if self.abort_reason is not None:
                    break
                m, f, r = self.sampler() or (None, None, None)
                self.traj.append({
                    't': round(time.time() - self.start, 2),
                    'machine_pct': None if m is None else round(m, 2),
                    'family_pct': None if f is None else round(f, 2),
                    'free_ram_gb': None if r is None else round(r, 2),
                })
                if len(self.traj) % 12 == 1:
                    self._write_traj(final=False)
                reason = judge.feed(m, f, r)
                if reason:
                    self._do_abort(reason)
                    break
            except Exception as e:
                print('[load_gate] 监控线程异常(继续): %r' % (e,))

    # ---- 落盘
    def _write_traj(self, final=False, ok=True, note=None):
        try:
            os.makedirs(self.p['runs'], exist_ok=True)
            doc = {
                'kind': self.kind, 'pid': os.getpid(),
                'workers': self.workers, 'start': self.start,
                'start_human': time.strftime(
                    '%Y-%m-%d %H:%M:%S', time.localtime(self.start)),
                'log': self.log, 'info': self.log_info,
                'machine_max': ABORT_MACHINE_MAX,
                'family_max': ABORT_FAMILY_MAX,
                'samples': self.traj,
                'abort_reason': self.abort_reason,
                'aborted': self.abort_reason is not None,
                'final': bool(final), 'ok': bool(ok), 'note': note,
            }
            if final:
                doc['end'] = time.time()
                doc['end_human'] = time.strftime(
                    '%Y-%m-%d %H:%M:%S')
                doc['duration_s'] = round(time.time() - self.start, 1)
            _write_json_atomic(self._traj_path, doc)
        except Exception as e:
            print('[load_gate] 轨迹写入失败: %r' % (e,))

    def _del_lock(self):
        try:
            rec = _read_json(self.p['lock'], None)
            if isinstance(rec, dict) and _pid_of(rec) == os.getpid():
                os.remove(self.p['lock'])
        except OSError:
            pass
        registry_remove(self.store, os.getpid())


class NoopHandle:
    """TH123_LOAD_GATE=0 回滚旁路: 无锁/无监控, 仅 worker cap."""

    def __init__(self, workers):
        self.kind = 'bypass'
        self.workers = workers
        self.abort_reason = None

    def set_abort_callback(self, cb):
        pass

    def poll_abort(self):
        return None

    def release(self, ok=True, note=None):
        pass


# ============================================================ acquire
def acquire(kind, workers=1, store=None, allow_day=False, log=None,
            now=None, preflight_gap=1.0, inject=None,
            monitor_interval=MONITOR_INTERVAL_S, sampler=None):
    """申请重负载窗口 → HeavyHandle; 拒绝返回 None(原因已打印).

    inject/sampler/monitor_interval 仅测试注入(生产不传).
    """
    if os.environ.get('TH123_LOAD_GATE') == '0':
        print('[load_gate] !! TH123_LOAD_GATE=0 回滚旁路: 跳过硬闸门'
              '(仅 worker cap)')
        return NoopHandle(worker_cap(workers))
    st = store_dir(store)
    p = paths(st)
    os.makedirs(st, exist_ok=True)
    os.makedirs(p['runs'], exist_ok=True)
    now = time.time() if now is None else float(now)

    # 0) 上一任务残留的 heavy.stop(>2min) 清理; 新鲜 stop → 拒绝(别继承中止)
    if os.path.exists(p['stop']):
        rec = _read_json(p['stop'], None) or {}
        ts = rec.get('ts') if isinstance(rec, dict) else None
        if ts and now - float(ts) <= STOP_STALE_S:
            print('[load_gate] !! 拒绝: 存在新鲜 heavy.stop(2min内): %s'
                  % (rec.get('reason') if isinstance(rec, dict) else rec))
            return None
        try:
            os.remove(p['stop'])
            print('[load_gate] 清理过期 heavy.stop(>2min 残留)')
        except OSError:
            pass

    # 1) 单实例锁
    if os.path.exists(p['lock']):
        rec = _read_json(p['lock'], None)
        stale, why = lock_is_stale(rec, now)
        if not stale:
            print('[load_gate] !! 拒绝: 已有重任务持锁 %s (pid=%s kind=%s '
                  'start=%s workers=%s)'
                  % (p['lock'], _pid_of(rec), rec.get('kind'),
                     rec.get('start'), rec.get('workers')))
            return None
        print('[load_gate] 回收 stale 锁(pid=%s): %s' % (_pid_of(rec), why))
        try:
            os.remove(p['lock'])
        except OSError:
            pass

    # 2) preflight(失败=关闭)
    ok, reason, readings = preflight(store=st, allow_day=allow_day, now=now,
                                     gap=preflight_gap, inject=inject)
    if not ok:
        return None

    # 3) worker cap
    capped = worker_cap(workers)
    if capped != max(1, int(workers)):
        print('[load_gate] worker cap: 请求%d → %d (cores//8, 硬上限%d)'
              % (max(1, int(workers)), capped, WORKER_HARD_CAP))

    # 4) 落锁 + 注册表 + 优先级 + 监控线程
    rec = {'pid': os.getpid(), 'kind': kind, 'start': now,
           'workers': capped, 'log': log,
           'preflight': readings}
    _write_json_atomic(p['lock'], rec)
    try:
        registry_add(st, rec)
    except Exception as e:
        print('[load_gate] 注册表写入失败(继续): %r' % (e,))
    set_priority(PRIORITY_BELOW_NORMAL)
    h = HeavyHandle(kind, capped, store=st, log=log, log_info={
        'preflight': readings, 'priority': PRIORITY_BELOW_NORMAL},
        monitor_interval=monitor_interval, sampler=sampler)
    h.start_monitor()
    print('[load_gate] acquire OK: kind=%s workers=%d pid=%d 轨迹=%s'
          % (kind, capped, os.getpid(), h.traj_path))
    return h


def _atexit_guard():
    """兜底: 进程退出时释放本 pid 持有的锁/注册项(防stale锁)."""
    try:
        p = paths()
        rec = _read_json(p['lock'], None)
        if isinstance(rec, dict) and _pid_of(rec) == os.getpid():
            os.remove(p['lock'])
        registry_remove(p['store'], os.getpid())
    except Exception:
        pass


atexit.register(_atexit_guard)


# ============================================================ CLI(运维自查)
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='L2 重负载闸门(CPU-H)')
    ap.add_argument('--preflight', action='store_true',
                    help='只跑启动前检查并打印读数(自查用)')
    ap.add_argument('--allow-day', action='store_true',
                    help='显式允许窗外启动')
    ap.add_argument('--store', default=None)
    a = ap.parse_args(argv)
    if a.preflight:
        ok, reason, readings = preflight(store=a.store, allow_day=a.allow_day)
        print(json.dumps({'ok': ok, 'reason': reason, 'readings': readings},
                         ensure_ascii=False, indent=1))
        return 0 if ok else 1
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
