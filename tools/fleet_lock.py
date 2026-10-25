# -*- coding: utf-8 -*-
"""fleet_lock v2: CAS 原子创建/stale 告警/owner 校验释放/续约."""
import argparse
import io
import json
import os
import sys
import time

STORE = r'D:\temp\th123_models'
LOCK = os.path.join(STORE, 'fleet_maintenance.lock')
TTL = 1800.0
ALERT = os.path.join(STORE, 'fleet_heartbeat.fleet_alert')


def _now(now=None):
    return time.time() if now is None else now


def read_lock():
    try:
        return json.load(io.open(LOCK, encoding='utf-8'))
    except Exception:
        return None


def is_expired(lock, now=None):
    if not lock:
        return False
    try:
        return _now(now) > float(lock.get('expires', 0))
    except (TypeError, ValueError):
        return True


def _stale_alert(lk):
    """stale 锁必须通知（不只 log）: 写 fleet_alert."""
    try:
        io.open(ALERT, 'w', encoding='utf-8').write(json.dumps(
            {'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
             'msg': 'stale maintenance lock takeover: %s' % json.dumps(
                 lk, ensure_ascii=False)[:200]}, ensure_ascii=False))
    except OSError:
        pass


def acquire(owner, reason='', ttl=TTL, pid=None, now=None):
    """CAS 原子创建(O_EXCL); 有效锁→locked; stale→告警+接管. 返回 (ok,code,lock)."""
    now = _now(now)
    pid = os.getpid() if pid is None else pid
    for _ in range(3):
        lk = {'owner': owner, 'pid': int(pid), 'reason': reason,
              'created': now, 'expires': now + ttl}
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, json.dumps(lk, ensure_ascii=False).encode('utf8'))
            finally:
                os.close(fd)
            return True, 'acquired', lk
        except FileExistsError:
            cur = read_lock()
            if cur and not is_expired(cur, now):
                if (cur.get('owner') == owner
                        and int(cur.get('pid', -1)) == int(pid)):
                    # 续约(原子重写)
                    try:
                        tmp = LOCK + '.renew.tmp'
                        with open(tmp, 'w', encoding='utf8') as f:
                            json.dump(lk, f, ensure_ascii=False)
                        os.replace(tmp, LOCK)
                        return True, 'renewed', lk
                    except OSError:
                        pass
                return False, 'locked', cur
            # stale → 告警+接管
            _stale_alert(cur)
            try:
                os.remove(LOCK)
            except OSError:
                pass
            continue
        except OSError as e:
            return False, repr(e), None
    return False, 'contended', read_lock()


def release(owner=None, pid=None, force=False):
    cur = read_lock()
    if not cur:
        return True, 'none'
    if force:
        try:
            os.remove(LOCK)
        except OSError:
            pass
        return True, 'forced'
    if owner is not None and cur.get('owner') != owner:
        return False, 'owner_mismatch'
    if pid is not None and int(cur.get('pid', -1)) != int(pid):
        return False, 'pid_mismatch'
    try:
        os.remove(LOCK)
    except OSError:
        pass
    return True, 'released'


def status(now=None):
    lk = read_lock()
    if not lk:
        return {'active': False, 'stale': False, 'lock': None}
    exp = is_expired(lk, now)
    if exp:
        _stale_alert(lk)
    return {'active': not exp, 'stale': bool(exp), 'lock': lk,
            'remaining': round(float(lk.get('expires', 0)) - _now(now), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--acquire', nargs=2, metavar=('OWNER', 'REASON'))
    ap.add_argument('--release', action='store_true')
    ap.add_argument('--owner')
    ap.add_argument('--pid', type=int, default=None)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--owner-ok', metavar='OWNER')
    ap.add_argument('--ttl', type=float, default=TTL)
    a = ap.parse_args()
    if a.status:
        print(json.dumps(status(), ensure_ascii=False))
        return 0
    if a.owner_ok:
        lk = read_lock()
        ok = bool(lk) and lk.get('owner') == a.owner_ok and not is_expired(lk)
        print('owner_ok' if ok else 'owner_no')
        return 0 if ok else 1
    if a.acquire:
        ok, code, lk = acquire(a.acquire[0], a.acquire[1], ttl=a.ttl)
        print(json.dumps({'ok': ok, 'code': code, 'lock': lk},
                         ensure_ascii=False))
        return 0 if ok else 1
    if a.release:
        ok, code = release(owner=a.owner, pid=a.pid, force=a.force)
        print(json.dumps({'ok': ok, 'code': code}, ensure_ascii=False))
        return 0 if ok else 1
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
