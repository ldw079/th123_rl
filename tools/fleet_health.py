# -*- coding: utf-8 -*-
"""Fleet 健康探针 + 外部看门狗 + 限流自动恢复（WMI）+ 维护锁（AR-1..9）.

用法:
  python tools/fleet_health.py --check              # 一次性检查
  python tools/fleet_health.py --loop 60 --auto-recover
  python tools/fleet_health.py --status             # 锁/恢复状态
  python tools/fleet_health.py --parent-check       # watcher 父链证据(AR-7)
  python tools/fleet_health.py --lock OWNER REASON   # 维护锁(委托 fleet_lock)
  python tools/fleet_health.py --unlock
  python tools/fleet_health.py --clear

规则（Lead 02:22/02:25 + auditor AR-1..9）:
- 必需集合 = sup + 3 main learner + 3 main actor + 4 games（排除 control）；
- 单 learner/actor 缺 → 仅告警（交 supervisor 自身恢复）；supervisor 缺或必需缺失≥2 =
  关键缺员 → 连续 2 次检查(≥120s) 且维护锁无效 → WMI 恢复；
- 限流 1/10min；失败退避（30min 内 ≥3 次失败→只告警）；不 kill 任何进程；
- 维护锁(租约)有效→抑制；stale 锁→告警+可接管；恢复前二次确认锁；
- 恢复后 health 复核；恢复/失败写 fleet_recovery.json/.log + fleet_heartbeat.recovery；
- 告警去重（bad 集合变化才重写）。
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import fleet_lock  # noqa: E402

STORE = r'D:\temp\th123_models'
HB = os.path.join(STORE, 'fleet_heartbeat')
ALERT = HB + '.machine_alert'
RECOVERY = os.path.join(STORE, 'fleet_recovery.json')
RECOVERY_LOG = os.path.join(STORE, 'fleet_recovery.log')
WATCH_LOCK = os.path.join(STORE, 'fleet_watcher.lock')
REQUIRED = {'sup': 1, 'learners': 3, 'actors': 3, 'games': 4}
INFO_KEYS = ('ctl',)
RECOVERY_MAX_AGE = 600.0
FAIL_WINDOW = 1800.0
FAIL_MAX = 3


def _ps_json(script):
    import base64
    enc = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    r = subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', enc],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=120)
    return (r.stdout or '').strip()


def _snapshot_script(marker=None):
    cond = ''
    if marker:
        cond = (" -and $_.CommandLine -match '%s'" % marker.replace("'", ""))
    return (
        "$py=Get-CimInstance Win32_Process | ? {$_.Name -eq 'python.exe'}; "
        "$g=Get-CimInstance Win32_Process | ? {$_.Name -eq 'th123.exe'}; "
        "[pscustomobject]@{"
        "sup=@($py|?{$_.CommandLine -match 'fleet_supervisor'%s}).Count;"
        "learners=@($py|?{$_.CommandLine -match 'learner_hub' -and "
        "$_.CommandLine -notmatch 'th123_rl_control'%s}).Count;"
        "actors=@($py|?{$_.CommandLine -match 'actor_worker' -and "
        "$_.CommandLine -notmatch 'th123_rl_control'%s}).Count;"
        "ctl=@($py|?{$_.CommandLine -match 'th123_rl_control'}).Count;"
        "games=@($g%s).Count" "} | ConvertTo-Json -Compress"
        % (cond, cond, cond, cond))


def snapshot(marker=None):
    out = _ps_json(_snapshot_script(marker))
    try:
        return json.loads(out)
    except Exception:
        return {}


def check(snap=None, hb_age=None):
    s = snap if snap is not None else snapshot()
    if hb_age is None:
        try:
            hb_age = time.time() - os.path.getmtime(HB)
        except OSError:
            hb_age = 1e9
    bad = []
    for k, v in REQUIRED.items():
        got = int(s.get(k, -1))
        if got < v:
            bad.append('%s %d<%d' % (k, got, v))
    if hb_age > 120:
        bad.append('hb_age %.0fs>120s' % hb_age)
    return (not bad), {'snap': s, 'hb_age': round(hb_age, 1), 'bad': bad}


def missing_count(snap):
    n = 0
    for k, v in REQUIRED.items():
        got = int(snap.get(k, -1))
        if got < v:
            n += (v - got)
    return n


def critical_snapshot(snap):
    """关键缺员: supervisor 缺失 或 必需进程缺失数≥2（control 不计）."""
    return int(snap.get('sup', -1)) < 1 or missing_count(snap) >= 2


def write_alert(msg):
    try:
        io.open(ALERT, 'w', encoding='utf-8').write(
            json.dumps({'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'msg': msg}, ensure_ascii=False))
    except OSError:
        pass


def _log(msg):
    try:
        with open(RECOVERY_LOG, 'a', encoding='utf8') as f:
            f.write('[%s] %s\n' % (time.strftime('%m-%d %H:%M:%S'), msg))
    except OSError:
        pass


def _load_recovery():
    try:
        return json.load(io.open(RECOVERY, encoding='utf-8'))
    except Exception:
        return {}


def _save_recovery(d):
    try:
        tmp = RECOVERY + '.tmp'
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, RECOVERY)
    except OSError:
        pass


def _pid_alive(pid):
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def try_single_instance():
    try:
        cur = json.load(io.open(WATCH_LOCK, encoding='utf-8'))
        if cur and int(cur.get('pid', -1)) != os.getpid() and \
                _pid_alive(int(cur.get('pid', -1))):
            return False, cur
    except Exception:
        pass
    tmp = WATCH_LOCK + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump({'pid': os.getpid(), 'ts': time.time()}, f)
        os.replace(tmp, WATCH_LOCK)
    except OSError:
        return False, None
    return True, None


def release_single_instance():
    try:
        cur = json.load(io.open(WATCH_LOCK, encoding='utf-8'))
        if int(cur.get('pid', -1)) == os.getpid():
            os.remove(WATCH_LOCK)
    except Exception:
        pass


def do_recover(reason, snap_fn=None, launch_fn=None, now=None):
    """WMI 限流恢复（只 spawn，不 kill）；返回 dict 记录."""
    now = time.time() if now is None else now
    st = _load_recovery()
    if now - float(st.get('last_ts', 0)) < RECOVERY_MAX_AGE:
        _log('rate_limited reason=%s' % reason)
        return {'code': 'rate_limited'}
    # 失败退避
    fw = float(st.get('fail_window_start', 0))
    if now - fw > FAIL_WINDOW:
        st['fail_window_start'] = now
        st['fail_count'] = 0
    if int(st.get('fail_count', 0)) >= FAIL_MAX:
        _log('backoff: fail_count>=%d alert_only' % FAIL_MAX)
        return {'code': 'backoff'}
    old = (snap_fn or snapshot)()
    ok = False
    try:
        import fleet_launch_wmi as L
        ok = bool(launch_fn() if launch_fn else L.launch())
    except Exception as e:
        _log('recover exception: %r' % (e,))
    new = (snap_fn or snapshot)()
    entry = {'ts': now, 'reason': reason, 'old': old, 'new': new,
             'launch_ok': ok}
    st['last_ts'] = now
    st['last'] = entry
    if not ok:
        st['fail_count'] = int(st.get('fail_count', 0)) + 1
    _save_recovery(st)
    try:
        io.open(HB + '.recovery', 'w', encoding='utf-8').write(
            json.dumps(entry, ensure_ascii=False))
    except OSError:
        pass
    _log('recover reason=%s launch_ok=%s old=%s new=%s'
         % (reason, ok, json.dumps(old, ensure_ascii=False),
            json.dumps(new, ensure_ascii=False)))
    return {'code': 'recovered' if ok else 'failed', **entry}


def loop_tick(state, now=None, snap_fn=None, launch_fn=None, auto_recover=True):
    """看门狗单拍（可测试）: 返回 (ok, detail, actions)."""
    now = time.time() if now is None else now
    snap = (snap_fn or snapshot)()
    ok, d = check(snap=snap)
    acts = []
    if ok:
        state['critical_since'] = 0
        state['alert_sig'] = None
        try:
            if os.path.exists(ALERT):
                os.remove(ALERT)
        except OSError:
            pass
        return ok, d, acts
    sig = tuple(d['bad'])
    if state.get('alert_sig') != sig:
        write_alert('fleet_health: ' + '; '.join(d['bad']))
        state['alert_sig'] = sig
        acts.append('alert_written')
    lst = fleet_lock.status()
    if lst.get('active'):
        acts.append('maintenance')
        _log('maintenance lock present — skip')
        return ok, d, acts
    if lst.get('stale'):
        acts.append('stale_lock_takeover')
        _log('stale lock detected (expired) — takeover allowed')
    if not critical_snapshot(snap):
        state['critical_since'] = 0
        acts.append('alert_only')
        return ok, d, acts
    if not state.get('critical_since'):
        state['critical_since'] = now
        acts.append('critical_start')
        return ok, d, acts
    if now - float(state['critical_since']) < 120:
        acts.append('critical_wait')
        return ok, d, acts
    # 二次确认锁（防窗中途写锁）
    if fleet_lock.status().get('active'):
        acts.append('maintenance')
        _log('maintenance lock appeared — abort recovery')
        state['critical_since'] = 0
        return ok, d, acts
    # 二次快照: supervisor 可能已自行恢复(race)
    snap2 = (snap_fn or snapshot)()
    ok2, _d2 = check(snap=snap2)
    if ok2:
        acts.append('recovered_race')
        state['critical_since'] = 0
        return True, _d2, acts
    if not critical_snapshot(snap2):
        acts.append('already_recovered')
        state['critical_since'] = 0
        return ok, d, acts
    if not auto_recover:
        acts.append('recover_skipped_no_flag')
        state['critical_since'] = 0
        return ok, d, acts
    r = do_recover('critical_missing', snap_fn=snap_fn,
                   launch_fn=launch_fn, now=now)
    acts.append(r.get('code', 'recover'))
    state['critical_since'] = 0
    return ok, d, acts


def parent_check():
    """AR-7: watcher 父链证据（应 gone/WmiPrvSE，非工具 shell）."""
    pid = os.getpid()
    script = (
        "$cur=Get-CimInstance Win32_Process -Filter ('ProcessId=' + %d); "
        "$out=@(); "
        "for($i=0; $i -lt 8; $i++){ "
        "if(-not $cur){ break }; "
        "$pp=Get-CimInstance Win32_Process -Filter "
        "('ProcessId=' + $cur.ParentProcessId) -ErrorAction SilentlyContinue; "
        "$nm=$(if($pp){$pp.Name}else{'gone'}); "
        "$out += ($cur.ProcessId.ToString() + ':' + $cur.Name + '<-' + $nm); "
        "if($cur.ParentProcessId -eq $cur.ProcessId){ break }; "
        "$cur=$pp }; "
        "$out -join ' | '" % pid)
    out = _ps_json(script)
    print('[parent-check] pid=%d chain: %s' % (pid, out))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--loop', type=int, default=0)
    ap.add_argument('--auto-recover', action='store_true')
    ap.add_argument('--clear', action='store_true')
    ap.add_argument('--lock', nargs=2, metavar=('OWNER', 'REASON'))
    ap.add_argument('--unlock', action='store_true')
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--parent-check', action='store_true')
    a = ap.parse_args()
    if a.clear:
        try:
            os.remove(ALERT)
        except OSError:
            pass
        print('[health] alert cleared')
        return 0
    if a.status:
        print(json.dumps({'lock': fleet_lock.status(),
                          'recovery': _load_recovery()},
                         ensure_ascii=False))
        return 0
    if a.parent_check:
        parent_check()
        return 0
    if a.lock:
        ok, code, lk = fleet_lock.acquire(a.lock[0], a.lock[1])
        print(json.dumps({'ok': ok, 'code': code}, ensure_ascii=False))
        return 0 if ok else 1
    if a.unlock:
        ok, code = fleet_lock.release(force=True)
        print(json.dumps({'ok': ok, 'code': code}, ensure_ascii=False))
        return 0 if ok else 1
    if a.check:
        ok, d = check()
        print('[health]', 'PASS' if ok else 'FAIL',
              json.dumps(d, ensure_ascii=False))
        return 0 if ok else 1
    if a.loop:
        ok, cur = try_single_instance()
        if not ok:
            print('[health] another watcher alive:', cur, flush=True)
            return 2
        st = {}
        try:
            while True:
                try:
                    ok, d, acts = loop_tick(st, auto_recover=a.auto_recover)
                    if not a.auto_recover and 'recovered' in acts:
                        pass
                except Exception as e:
                    ok, d, acts = False, {'bad': ['exception:' +
                                                  repr(e)[:120]]}, []
                print('[health]', 'PASS' if ok else 'FAIL',
                      json.dumps(d, ensure_ascii=False),
                      ('acts=' + ','.join(acts)) if acts else '',
                      flush=True)
                time.sleep(a.loop)
        finally:
            release_single_instance()
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
