# -*- coding: utf-8 -*-
"""task-43: train_detach 工具 C15(-dry/环境合并/breakaway 回退标志/日志路径)."""
import importlib.util
import os
import subprocess
import sys

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
chk('固定日志路径', TD.DEFAULT_LOG == r'D:\temp\main_detached.log')
pid, brk, line = TD.launch(TD.build_cmd(), WT, env, TD.DEFAULT_LOG, dry=True)
chk('dry 返回不启动', pid is None and brk is True and 'train_start.py' in line)
r = subprocess.run([PY, '-X', 'utf8', TOOL, '--dry', '--env',
                    'TH123_MEM_DECISIONS=8'], capture_output=True, text=True)
chk('CLI --dry 输出标志与 env', r.returncode == 0
    and 'breakaway' in r.stdout and 'TH123_MEM_DECISIONS' in r.stdout)
src = open(TOOL, encoding='utf8').read()
chk('breakaway 失败回退带响亮告警',
    'breakaway 被 Job 限制' in src
    and 'for use_break in (True, False)' in src)
chk('显式清理 BATCH/BCW 残留 env',
    "env.pop(k, None)" in src and 'TH123_BATCH_MIN_GAMES' in src)
print('==== train_detach: %d PASS / %d FAIL ====' % (10 - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
