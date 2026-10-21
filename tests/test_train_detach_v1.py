# -*- coding: utf-8 -*-
"""task-43b: train_detach 工具 C15(dry/env/标志/bat/schtasks 实现/真实哑进程 spawn).

注: 真实 schtasks 建任务与 --stop 不在 C15 内执行(会干扰环境/训练); 由窗内
"用工具重启主臂"集成验证覆盖. 真实 Popen 哑进程 spawn 覆盖"存活+日志重定向"。
"""
import ctypes
import importlib.util
import os
import sys
import tempfile
import time

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
PY = sys.executable
TOOL = os.path.join(WT, 'tools', 'train_detach.py')
FAIL = []


def chk(name, cond):
    if cond:
        print('  PASS ', name)
    else:
        FAIL.append(name)
        print('  FAIL ', name)


spec = importlib.util.spec_from_file_location('train_detach', TOOL)
TD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TD)
print('== train_detach ==')
chk('breakaway/detached 标志常量',
    TD.CREATE_BREAKAWAY_FROM_JOB == 0x01000000
    and TD.DETACHED_PROCESS == 0x8 and TD.CREATE_NEW_PROCESS_GROUP == 0x200)
env = TD.build_env({'A': '1'}, ['TH123_MEM_DECISIONS=8', 'B=2'])
chk('env 合并(K=V)', env['A'] == '1' and env['TH123_MEM_DECISIONS'] == '8'
    and env['B'] == '2')
try:
    TD.build_env({}, ['BAD'])
    chk('env 非法格式报错', False)
except ValueError:
    chk('env 非法格式报错', True)
cmd = TD.build_cmd('fleet', 3, 360)
chk('fleet cmd 含 train_start', any('train_start.py' in c for c in cmd)
    and '--actors' in cmd and '--tps' in cmd)
chk('固定日志/任务名', TD.DEFAULT_LOG == r'D:\temp\main_detached.log'
    and TD.TASK_NAME.startswith('th123_'))
chk('--stop 命令模板', TD.stop_cmd()[-1] == '--stop'
    and any('train_start.py' in c for c in TD.stop_cmd()))
bat = os.path.join(tempfile.gettempdir(), 'detach_test.bat')
TD.write_launcher_bat(bat, {'TH123_MEM_DECISIONS': '8'},
                      TD.build_cmd('fleet', 3, 360), r'D:\temp\x.log')
src_bat = open(bat, encoding='utf8').read()
chk('bat 含 env/cd/日志重定向',
    'set TH123_MEM_DECISIONS=8' in src_bat and 'cd /d' in src_bat
    and 'train_start.py' in src_bat and 'D:\\temp\\x.log' in src_bat)
res = TD.launch(TD.build_cmd(), WT, env, TD.DEFAULT_LOG, dry=True)
chk('dry 返回不启动(mode=dry)', res['mode'] == 'dry' and res['pid'] is None)
tool_src = open(TOOL, encoding='utf8').read()
chk('schtasks 实现(create/run)', 'launch_schtasks' in tool_src
    and "'/run'" in tool_src and 'schtasks' in tool_src)
dlog = os.path.join(tempfile.gettempdir(), 'detach_spawn_test.log')
try:
    os.remove(dlog)
except OSError:
    pass
spawn_cmd = [PY, '-c',
             'import time,sys;sys.stdout.write("SPAWN_OK");'
             'sys.stdout.flush();time.sleep(6)']
res2 = TD.launch(spawn_cmd, WT, dict(os.environ), dlog, via='popen')
pid = res2.get('pid')
alive = False
if pid:
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)
    alive = bool(h)
    if h:
        k32.CloseHandle(h)
time.sleep(1.0)
chk('真实 spawn 存活', alive and res2['mode'] in
    ('popen_breakaway', 'popen_fallback'))
txt = open(dlog, encoding='utf8', errors='replace').read() \
    if os.path.exists(dlog) else ''
chk('真实 spawn 日志重定向', 'SPAWN_OK' in txt)
print('==== train_detach: %d PASS / %d FAIL ====' % (12 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
