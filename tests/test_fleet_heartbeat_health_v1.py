# -*- coding: utf-8 -*-
"""P0 预防 b: 心跳健康字段 + 告警写入/清除 行为测试（真实文件/数据）."""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import fleet_supervisor as FS  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def _tmp_ctx():
    d = tempfile.mkdtemp(prefix='hb_health_')
    hb = os.path.join(d, 'fleet_heartbeat')
    FS.HEARTBEAT = hb
    FS.FLEET_ALERT = hb + '.fleet_alert'
    FS.WD_STATUS = hb + '.wd'
    return d, hb


def test_bad_health_alert():
    _d, hb = _tmp_ctx()
    bad = {'ts': 1.0, 'sup': 1, 'learners': 2, 'actors': 3, 'ctl': 2,
           'games': 4, 'max_log_age': 10.0, 'bad': ['learners 2<3']}
    FS.write_heartbeat(alert=None, health=bad)
    check('bad health: 写 sidecar', os.path.exists(hb + '.health'))
    h = json.load(io.open(hb + '.health', encoding='utf-8'))
    check('sidecar: learners 字段', h.get('learners') == 2)
    check('bad health: 写 fleet_alert', os.path.exists(hb + '.fleet_alert'))
    check('主心跳文件仍是时间戳',
          float(io.open(hb).read().split()[0]) > 0)


def test_good_health_clear():
    _d, hb = _tmp_ctx()
    bad = {'ts': 1.0, 'sup': 1, 'learners': 2, 'actors': 3, 'ctl': 2,
           'games': 4, 'max_log_age': 10.0, 'bad': ['learners 2<3']}
    FS.write_heartbeat(alert=None, health=bad)
    good = {'ts': 2.0, 'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 2,
            'games': 4, 'max_log_age': 5.0, 'bad': []}
    FS.write_heartbeat(alert=None, health=good)
    check('good health: 清除 fleet_alert',
          not os.path.exists(hb + '.fleet_alert'))
    h = json.load(io.open(hb + '.health', encoding='utf-8'))
    check('good health: sidecar 更新', h.get('bad') == [])


def test_watchdog_status_fields():
    _d, hb = _tmp_ctx()
    good = {'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 2, 'games': 4,
            'max_log_age': 5.0, 'bad': []}
    FS.write_watchdog_status(12.3, health=good)
    txt = io.open(hb + '.wd').read()
    check('wd 主文件: 5 字段契约不变(旧读者 split()[1])',
          len(txt.split()) == 5 and txt.split()[1] == '12.30',
          str(txt.split()[:6]))
    hp = io.open(hb + '.wd.health', encoding='utf-8').read()
    check('wd 健康 sidecar: learners/actors/games 字段',
          'learners' in hp and '3' in hp and 'games' in hp, hp[:120])


def test_health_now_detect():
    orig = FS.fleet_process_snapshot
    try:
        FS.fleet_process_snapshot = lambda: {
            'sup': 1, 'learners': 2, 'actors': 3, 'ctl': 2, 'games': 4}
        h = FS.fleet_health_now()
        check('health_now: 缺 learner→bad', any('learners' in x
                                               for x in h['bad']))
        FS.fleet_process_snapshot = lambda: {
            'sup': 1, 'learners': 3, 'actors': 3, 'ctl': 2, 'games': 4}
        h2 = FS.fleet_health_now()
        check('health_now: 全在位→bad 空', h2['bad'] == [])
    finally:
        FS.fleet_process_snapshot = orig


def main():
    test_bad_health_alert()
    test_good_health_clear()
    test_watchdog_status_fields()
    test_health_now_detect()
    print('\n==== heartbeat_health: %d PASS / %d FAIL ===='
          % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
