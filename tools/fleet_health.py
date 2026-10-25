# -*- coding: utf-8 -*-
"""Fleet 健康探针（外部看门狗，只读/告警；可循环运行）.

用法:
  python tools/fleet_health.py --check            # 一次性检查, 失败退出码1
  python tools/fleet_health.py --loop 30           # 每30s检查, 缺失→alert文件
  python tools/fleet_health.py --clear             # 清除 alert
检查项: supervisor>=1, main learner==3, main actor==3, control py>=2,
        games>=4, heartbeat age<=120s。
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

STORE = r'D:\temp\th123_models'
HB = os.path.join(STORE, 'fleet_heartbeat')
ALERT = HB + '.machine_alert'


def _ps_json(script):
    import base64
    enc = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    r = subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', enc],
                       capture_output=True, text=True, timeout=120)
    return (r.stdout or '').strip()


def snapshot():
    script = (
        "$py=Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "
        "'python.exe' }; "
        "$g=Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "
        "'th123.exe' }; "
        "[pscustomobject]@{"
        "sup=@($py|Where-Object{$_.CommandLine -match 'fleet_supervisor'}).Count;"
        "learners=@($py|Where-Object{$_.CommandLine -match 'learner_hub' -and "
        "$_.CommandLine -notmatch 'th123_rl_control'}).Count;"
        "actors=@($py|Where-Object{$_.CommandLine -match 'actor_worker' -and "
        "$_.CommandLine -notmatch 'th123_rl_control'}).Count;"
        "ctl=@($py|Where-Object{$_.CommandLine -match 'th123_rl_control'}).Count;"
        "games=@($g).Count"
        "} | ConvertTo-Json -Compress")
    out = _ps_json(script)
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
    exp = {'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 2, 'games': 4}
    bad = []
    for k, v in exp.items():
        got = int(s.get(k, -1))
        if got < v:
            bad.append('%s %d<%d' % (k, got, v))
    if hb_age > 120:
        bad.append('hb_age %.0fs>120s' % hb_age)
    return (not bad), {'snap': s, 'hb_age': round(hb_age, 1), 'bad': bad}


def write_alert(msg):
    io.open(ALERT, 'w', encoding='utf-8').write(
        json.dumps({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'msg': msg},
                   ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--loop', type=int, default=0)
    ap.add_argument('--clear', action='store_true')
    a = ap.parse_args()
    if a.clear:
        try:
            os.remove(ALERT)
        except OSError:
            pass
        print('[health] alert cleared')
        return 0
    if a.check:
        ok, d = check()
        print('[health]', 'PASS' if ok else 'FAIL', json.dumps(d,
                                                               ensure_ascii=False))
        return 0 if ok else 1
    if a.loop:
        misses = 0
        while True:
            ok, d = check()
            if not ok:
                misses += 1
                print('[health] FAIL', json.dumps(d, ensure_ascii=False))
                if misses >= 2:
                    write_alert('fleet_health: ' + '; '.join(d['bad']))
            else:
                misses = 0
                if os.path.exists(ALERT):
                    try:
                        os.remove(ALERT)
                    except OSError:
                        pass
            time.sleep(a.loop)
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
