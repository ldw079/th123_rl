# -*- coding: utf-8 -*-
"""统一维护锁（租约）— 窗脚本/手工停启/看门狗共用（AR-2）.

锁内容: owner/pid/reason/created/expires; 原子创建(tmp+rename); stale TTL 超时→
告警+可接管(不静默永久锁).

用法:
  python tools/fleet_lock.py --acquire ukemi-window "UKEMI env window" [--ttl 1800]
  python tools/fleet_lock.py --release [--force]
  python tools/fleet_lock.py --status
  python tools/fleet_lock.py --owner-ok ukemi-window   # 退出码0=持锁者可续约
"""
import argparse
import io
import json
import os
import sys
import time

STORE = r'D:\temp\th123_models'
LOCK = os.path.join(STORE, 'fleet_maintenance.lock')
TTL = 1800.0


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


def lock_active(now=None):
    """有效(未过期)锁 → True; 过期锁不算 active（可接管）."""
    lk = read_lock()
    return bool(lk) and not is_expired(lk, now)


def acquire(owner, reason='', ttl=TTL, pid=None, now=None):
    """原子创建租约锁; 返回 (ok, code, lock). code: acquired/renewed/locked/takeover."""
    now = _now(now)
    pid = os.getpid() if pid is None else pid
    cur = read_lock()
    code = 'acquired'
    if cur and not is_expired(cur, now):
        if cur.get('owner') == owner and int(cur.get('pid', -1)) == int(pid):
            code = 'renewed'
        else:
            return False, 'locked', cur
    elif cur:
        code = 'takeover'
    lk = {'owner': owner, 'pid': int(pid), 'reason': reason,
          'created': now, 'expires': now + ttl}
    tmp = LOCK + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf8') as f:
            json.dump(lk, f, ensure_ascii=False)
        os.replace(tmp, LOCK)
    except OSError as e:
        return False, repr(e), None
    return True, code, lk


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
    return {'active': not exp, 'stale': bool(exp), 'lock': lk,
            'remaining': round(float(lk.get('expires', 0)) - _now(now), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--acquire', nargs=2, metavar=('OWNER', 'REASON'))
    ap.add_argument('--release', action='store_true')
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
        ok, code = release(force=a.force)
        print(json.dumps({'ok': ok, 'code': code}, ensure_ascii=False))
        return 0 if ok else 1
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
