# -*- coding: utf-8 -*-
"""CPU-H P-A 行为自测: `tools/load_gate.py` 轻载闸门 (2026-10-18 用户令).

覆盖(方案 §3-1 ≥10 项): 锁互斥/持锁者拒绝、stale 回收(死PID/超8h)、
worker cap(cores//8+硬上限4)、preflight 三类拒绝(整机/RAM/族)与夜间窗/
--allow-day、协作停止 heavy.stop、监控中止(注入 90%×3)、优先级 BELOW_NORMAL
继承、注册表登记/清理、轨迹落盘、env 回滚旁路、AbortJudge 纯判定。
**全部注入采样值 + 临时 STORE(gap=0), 空跑不压负载, 不碰真 STORE/fleet。**
"""
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.stdout.reconfigure(encoding='utf8')

import load_gate as lg  # noqa: E402

N = 0
BAD = 0


def ck(cond, name):
    global N, BAD
    N += 1
    if cond:
        print('  PASS  %s' % name)
    else:
        BAD += 1
        print('  FAIL  %s' % name)


NIGHT = time.mktime((2026, 10, 18, 22, 0, 0, 0, 0, -1))
DAY = time.mktime((2026, 10, 18, 12, 0, 0, 0, 0, -1))


def INJ(now=NIGHT, m=40.0, r=10.0, f=20.0):
    """注入 preflight 读数(夜间窗+各项正常)."""
    return {'now': now, 'machine_series': [m], 'ram_gb': r, 'family_pct': f}


def store():
    return tempfile.mkdtemp(prefix='lg_test_')


def acq(st, kind='selftest', **kw):
    params = dict(workers=1, store=st, preflight_gap=0.0,
                  inject=INJ(), monitor_interval=60.0)
    params.update(kw)
    return lg.acquire(kind, **params)


def clean(st):
    shutil.rmtree(st, ignore_errors=True)


def _runs_docs(st):
    d = os.path.join(st, 'heavy_runs')
    if not os.path.isdir(d):
        return []
    out = []
    for f in os.listdir(d):
        if f.endswith('.json'):
            try:
                out.append(json.load(open(os.path.join(d, f),
                                          encoding='utf8')))
            except (OSError, ValueError):
                pass
    return out


# ---------------- 1) 锁生命周期 ----------------
st = store()
h = acq(st)
ck(h is not None, 'acquire 成功返回句柄')
lock = os.path.join(st, 'heavy.lock')
ck(os.path.exists(lock), '锁文件 heavy.lock 已落盘')
_rec = json.load(open(lock, encoding='utf8'))
ck(_rec.get('pid') == os.getpid() and _rec.get('kind') == 'selftest',
   '锁内容 pid/kind 正确')
ck(_rec.get('workers') == 1, '锁内容 workers 记录(cap 后)')
h.release()
ck((not os.path.exists(lock))
   and (not os.path.exists(os.path.join(st, 'heavy_jobs.json'))),
   'release 后锁与注册表都已清')
clean(st)

# ---------------- 2) 二次 acquire 拒绝(持锁者打印) ----------------
st = store()
h1 = acq(st)
h2 = acq(st)
ck(h1 is not None and h2 is None, '持锁期间二次 acquire 被拒绝(单实例互斥)')
h1.release()
short = acq(st, preflight_gap=0.0, inject=INJ())
ck(short is not None, '前一个 release 后可再次 acquire')
short.release()
clean(st)

# ---------------- 3) worker cap ----------------
ck(lg.worker_cap(8, cores=18) == 2, 'worker cap: 18核 req8 → 2 (cores//8)')
ck(lg.worker_cap(8, cores=64) == 4, 'worker cap: 硬上限 4')
ck(lg.worker_cap(0, cores=18) == 1, 'worker cap: req0 → 1')
ck(lg.worker_cap(3, cores=18) == 2, 'worker cap: 18核 req3 → 2')

# ---------------- 4) stale 锁回收(死 PID / 超 8h) ----------------
st = store()
lg._write_json_atomic(os.path.join(st, 'heavy.lock'),
                      {'pid': 999999, 'kind': 'dead', 'start': time.time(),
                       'workers': 2})
h = acq(st)
ck(h is not None, 'stale 回收: 死 PID 的锁被回收后 acquire 成功')
h.release()
clean(st)
st = store()
lg._write_json_atomic(os.path.join(st, 'heavy.lock'),
                      {'pid': os.getpid(), 'kind': 'old',
                       'start': time.time() - 9 * 3600, 'workers': 2})
h = acq(st)
ck(h is not None, 'stale 回收: 存活但 >8h 的锁被回收')
h.release()
clean(st)
ck(lg.lock_is_stale({'pid': os.getpid(), 'start': time.time()},
                    time.time())[0] is False, 'lock_is_stale: 新鲜锁不回收')

# ---------------- 5) preflight 三类拒绝 + 夜间窗 ----------------
st = store()
ok, reason, _rd = lg.preflight(store=st, now=NIGHT, gap=0.0,
                               inject=INJ(m=80.0))
ck((not ok) and ('整机CPU' in reason), 'preflight: 整机80% → 拒绝')
ok, reason, _ = lg.preflight(store=st, now=NIGHT, gap=0.0, inject=INJ(r=2.0))
ck((not ok) and ('RAM' in reason), 'preflight: 空闲RAM 2GB → 拒绝')
ok, reason, _ = lg.preflight(store=st, now=NIGHT, gap=0.0, inject=INJ(f=78.0))
ck((not ok) and ('训练族' in reason), 'preflight: 训练族78% → 拒绝')
_ok, _r, _ = lg.preflight(store=st, now=NIGHT, gap=0.0,
                          inject={'now': NIGHT, 'machine_series': [40.0],
                                  'ram_gb': 10.0, 'family_pct': None})
ck((not _ok) and ('采样失败' in _r), 'preflight: 族口径采样失败 → 保守拒绝')
ok, reason, _ = lg.preflight(store=st, now=DAY, gap=0.0, inject=INJ(now=DAY))
ck((not ok) and ('窗外' in reason), 'preflight: 窗外(DAY)未 --allow-day → 拒绝')
ok, _r, _ = lg.preflight(store=st, now=DAY, allow_day=True, gap=0.0,
                         inject=INJ(now=DAY))
ck(ok, 'preflight: --allow-day 时窗外放行')
ok, _r, _ = lg.preflight(store=st, now=NIGHT, gap=0.0, inject=INJ(now=NIGHT))
ck(ok, 'preflight: 夜间窗自动放行(负载正常)')
ck(lg.in_night_window(NIGHT) and lg.in_night_window(time.mktime(
    (2026, 10, 18, 3, 0, 0, 0, 0, -1))), '夜间窗: 22:00/03:00 判为夜间')
ck((not lg.in_night_window(DAY))
   and (not lg.in_night_window(time.mktime(
       (2026, 10, 18, 19, 59, 0, 0, 0, -1))))
   and (not lg.in_night_window(time.mktime(
       (2026, 10, 18, 8, 0, 0, 0, 0, -1)))),
   '夜间窗: 12:00/19:59/08:00 判为窗外')

# ---------------- 6) preflight 拒绝时 acquire 失败=关闭且无残留 ----------------
st = store()
h = acq(st, inject=INJ(m=80.0))
ck(h is None, 'acquire: preflight 拒绝 → 返回 None(不静默放行)')
ck(not os.path.exists(os.path.join(st, 'heavy.lock')),
   'acquire: 拒绝后无锁残留')
clean(st)

# ---------------- 7) 协作停止 heavy.stop ----------------
st = store()
h = acq(st)
with open(os.path.join(st, 'heavy.stop'), 'w', encoding='utf8') as f:
    json.dump({'reason': 'lead-test', 'ts': time.time()}, f)
r = h.poll_abort()
ck(bool(r) and ('协作停止' in r), '协作停止: heavy.stop → poll_abort 返回原因')
ck(not os.path.exists(os.path.join(st, 'heavy.lock')),
   '协作停止: 中止时锁已释放')
h.release()
clean(st)
st = store()
with open(os.path.join(st, 'heavy.stop'), 'w', encoding='utf8') as f:
    json.dump({'reason': 'fresh', 'ts': time.time()}, f)
h = acq(st)
ck(h is None, '协作停止: 新鲜 heavy.stop 残留时 acquire 拒绝(不继承中止)')
clean(st)

# ---------------- 8) 监控中止(注入 95%×3 窗) ----------------
st = store()
h = acq(st, monitor_interval=0.02, sampler=lambda: (95.0, 10.0, 20.0))
t0 = time.time()
while time.time() - t0 < 2.0 and not h.aborted:
    time.sleep(0.01)
ck(h.aborted, '监控: 整机 95%×3 窗 → 触发中止')
ck('整机CPU' in (h.poll_abort() or ''), '监控: 中止原因=整机CPU超线')
# 中止序列在监控线程内完成: 等轨迹 final 落盘 + 锁释放(≤10s 规格, 测试等2s)
_doc, _deadline = None, time.time() + 2.0
while time.time() < _deadline:
    _docs = _runs_docs(st)
    if _docs and _docs[-1].get('aborted') is True \
            and bool(_docs[-1].get('abort_reason')):
        _doc = _docs[-1]
        break
    time.sleep(0.01)
ck(_doc is not None, '监控: 中止轨迹含 abort_reason')
while time.time() < _deadline and os.path.exists(os.path.join(st,
                                                              'heavy.lock')):
    time.sleep(0.01)
ck(not os.path.exists(os.path.join(st, 'heavy.lock')),
   '监控: 中止后锁已释放(接收新任务)')
h.release()
clean(st)

# ---------------- 9) 优先级 BELOW_NORMAL 与恢复 ----------------
st = store()
_before = lg.get_priority()
h = acq(st)
ck(lg.get_priority() == lg.PRIORITY_BELOW_NORMAL,
   '优先级: acquire 后自身=BELOW_NORMAL(子进程继承)')
h.release()
ck(lg.get_priority() == _before, '优先级: release 恢复原优先级')
clean(st)

# ---------------- 10) 注册表登记/清理 + 轨迹落盘 ----------------
st = store()
h = acq(st)
_jobs = json.load(open(os.path.join(st, 'heavy_jobs.json'),
                       encoding='utf8')).get('jobs', [])
ck(any(j.get('pid') == os.getpid() and j.get('kind') == 'selftest'
       for j in _jobs), '注册表: 持锁期间登记本任务')
_jpath = h.traj_path
h.release()
_doc = json.load(open(_jpath, encoding='utf8'))
ck(_doc.get('final') is True and _doc.get('ok') is True
   and _doc.get('kind') == 'selftest', '轨迹: 正常释放写 final/ok/kind')
ck('preflight' in _doc.get('info', {}), '轨迹: 含 preflight 读数')
clean(st)

# ---------------- 11) env 回滚旁路 TH123_LOAD_GATE=0 ----------------
st = store()
os.environ['TH123_LOAD_GATE'] = '0'
try:
    h = lg.acquire('selftest', workers=8, store=st, preflight_gap=0.0,
                   inject=INJ())
    ck(h is not None and getattr(h, 'kind', '') == 'bypass',
       'env 回滚: TH123_LOAD_GATE=0 → 旁路句柄')
    ck(h.workers == lg.worker_cap(8), 'env 回滚: worker cap 仍生效')
    h.release()
finally:
    os.environ.pop('TH123_LOAD_GATE', None)
clean(st)

# ---------------- 12) AbortJudge 纯判定 ----------------
for _m, _f, _r, _want in ((89.0, 10.0, 20.0, None),
                          (91.0, 10.0, 20.0, '整机CPU')):
    j = lg.AbortJudge()
    reasons = [j.feed(_m, _f, _r) for _ in range(3)]
    ck((reasons[0] is None and reasons[1] is None
        and ((reasons[2] is None) if _want is None
             else (_want in reasons[2]))),
       'AbortJudge: 整机%.0f%%×3 → %s' % (_m, _want or '不中止'))
j = lg.AbortJudge()
_rs = [j.feed(10.0, 76.0, 20.0) for _ in range(3)]
ck(_rs[2] and ('训练族' in _rs[2]), 'AbortJudge: 族76%×3 → 中止')
j = lg.AbortJudge()
ck(bool(j.feed(10.0, 10.0, 2.0)) and ('RAM' in j.feed(10.0, 10.0, 2.0)),
   'AbortJudge: RAM<3GB → 立即中止')

# ---------------- 汇总 ----------------
print('\n==== load_gate 自测: %d PASS / %d FAIL ====' % (N - BAD, BAD))
sys.exit(0 if BAD == 0 else 1)
