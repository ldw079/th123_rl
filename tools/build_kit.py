# -*- coding: utf-8 -*-
r"""可迁移化Phase2: 轻量采集包构建器.

用法: python tools/build_kit.py [--chars reimu,suika] [--zip]
产出: dist/th123rl_kit/ 目录(或 dist/th123rl_kit_v{date}.zip)
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, 'dist')
sys.path.insert(0, ROOT)   # kit_config在仓库根
ENTRY = 'human_match_v2.py'
EXTRA = {
    'kit_config.py', 'portmap.py', 'series_manager.py',
    'habit_detector.py', 'passivity_meter.py', 'series_meter.py',
    'value_curve.py', 'league.py', 'teach.py',
}

# ============================================================
# 生成的收件人脚本(纯文本模板, 无嵌套引号问题)
# ============================================================

SETUP_HELPER = '''import os, sys, json, hashlib
print("=== TH123RL Kit Setup ===")
print()
game_dir = input("Enter your th123 game folder path: ").strip()
exe = os.path.join(game_dir, "th123.exe")
if not os.path.exists(exe):
    print("ERROR: th123.exe not found at", exe)
    sys.exit(1)
md5 = hashlib.md5(open(exe, "rb").read()).hexdigest().upper()
print("exe md5:", md5)
base = os.path.dirname(os.path.abspath(__file__))
json.dump({"game_dir": game_dir, "exe_md5": md5},
          open(os.path.join(base, "config.json"), "w"))
print("config.json created!")
print("Setup complete. Run start.bat to begin.")
'''

SETUP_BAT = '''@echo off
chcp 65001 >nul
cd /d %~dp0
echo === TH123RL Kit Setup ===
echo.
set PY=%~dp0python\python.exe
"%PY%" setup_helper.py
pause
'''

START_BAT = '''@echo off
chcp 65001 >nul
cd /d %~dp0
set PYTHONPATH=%~dp0th123rl;%~dp0
echo === TH123RL Match Runner ===
echo.
set /p CHAR="Character (reimu/marisa/suika): "
set /p SECONDS="Session length in seconds (default 1800): "
if "%SECONDS%"=="" set SECONDS=1800
echo.
echo Starting runner...
echo 1. Launch your th123 game
echo 2. Go to VS PLAYER mode
echo 3. P2 profile: RL-AI
echo 4. The model will auto-takeover P2
echo.
"%~dp0python\python.exe" th123rl/tools/human_match_v2.py --char %CHAR% --seconds %SECONDS%
pause
'''

EXPORT_HELPER = '''import zipfile, glob, os, time
fn = time.strftime("match_data_%Y%m%d_%H%M%S.zip")
with zipfile.ZipFile(fn, "w", zipfile.ZIP_DEFLATED) as z:
    for d in ("th123rl/tools/human_match_sessions",
              "th123rl/tools/habit_demos"):
        if os.path.isdir(d):
            for f in glob.glob(os.path.join(d, "*.json")):
                z.write(f, os.path.relpath(f))
    rep_dir = os.path.join("th123rl", "reps")
    if os.path.isdir(rep_dir):
        for f in glob.glob(os.path.join(rep_dir, "*.rep")):
            z.write(f, os.path.relpath(f))
print("Exported:", fn)
print("Please send this file back!")
'''

EXPORT_BAT = '''@echo off
chcp 65001 >nul
cd /d %~dp0
"%~dp0python\python.exe" export_helper.py
pause
'''

README = '''TH123RL 人机对战采集套件
==========================

使用步骤:
  1. 解压本文件夹到任意位置
  2. 双击 setup.bat (首次配置: 设置游戏路径, 自带Python无需安装)
  3. 双击 start.bat 开始对战
     - 启动你的东方非想天则
     - 进入 VS PLAYER 模式
     - P2 侧选择 RL-AI 档案
     - 选好角色后开始对局, AI自动接管P2
  4. 打完后双击 export.bat 导出数据
  5. 把导出的 match_data_*.zip 发回给研究者

要求:
  - Windows 10/11
  - 东方非想天则 (整合包或原版均可)
  - 游戏exe版本需兼容 (setup会自动检查)
  (Python和依赖已内置, 无需额外安装)

注意事项:
  - 对战期间请不要切换窗口 (AI需要读取游戏内存)
  - rep文件请在对局结束后的结算画面保存
  - 如遇问题请联系研究者
'''


def trace_imports(entry_file, root):
    needed = set()
    queue = [entry_file]
    while queue:
        fn = queue.pop()
        if fn in needed:
            continue
        needed.add(fn)
        for base in (root, os.path.join(root, 'tools')):
            path = os.path.join(base, fn)
            if os.path.exists(path):
                try:
                    tree = ast.parse(
                        open(path, encoding='utf8').read())
                except (OSError, SyntaxError):
                    continue
                for node in ast.walk(tree):
                    mods = []
                    if isinstance(node, ast.Import):
                        mods = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        mods = [node.module]
                    for mod in mods:
                        mf = mod.replace('.', os.sep) + '.py'
                        if os.path.exists(os.path.join(root, mf)):
                            queue.append(mf)
                        if os.path.exists(
                                os.path.join(root, 'tools', mf)):
                            queue.append(os.path.join('tools', mf))
                        mac = os.path.join(
                            root, 'macros', mod.split('.')[-1] + '.py')
                        if os.path.exists(mac):
                            needed.add(os.path.join(
                                'macros', mod.split('.')[-1] + '.py'))
                break
    return needed




def _bundle_python(kit_dir):
    """K1便携化: embed Python + numpy → kit/python/."""
    import urllib.request
    import zipfile
    py_dir = os.path.join(kit_dir, 'python')
    os.makedirs(py_dir, exist_ok=True)
    ver = '3.12.8'
    url = ('https://www.python.org/ftp/python/%s/'
           'python-%s-embed-amd64.zip' % (ver, ver))
    cache = os.path.join(DIST, 'cache')
    os.makedirs(cache, exist_ok=True)
    embed_zip = os.path.join(cache, 'python-%s-embed.zip' % ver)
    if not os.path.exists(embed_zip):
        print('[kit] downloading Python %s embed...' % ver)
        urllib.request.urlretrieve(url, embed_zip)
    with zipfile.ZipFile(embed_zip) as zf:
        zf.extractall(py_dir)
    # numpy wheel
    numpy_whl = os.path.join(cache, 'numpy.whl')
    if not os.path.exists(numpy_whl):
        print('[kit] downloading numpy wheel...')
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'download',
                        'numpy', '--only-binary', ':all:',
                        '-d', cache, '--no-deps'],
                       check=True)
        # pip saves as numpy-*.whl, rename for stability
        for f in os.listdir(cache):
            if f.startswith('numpy-') and f.endswith('.whl'):
                os.rename(os.path.join(cache, f), numpy_whl)
                break
    sp_dir = os.path.join(py_dir, 'Lib', 'site-packages')
    os.makedirs(sp_dir, exist_ok=True)
    with zipfile.ZipFile(numpy_whl) as zf:
        zf.extractall(sp_dir)
    # ._pth: 启用site-packages(embed默认禁用import路径)
    pth = os.path.join(py_dir, 'python312._pth')
    open(pth, 'w').write(
        'python312.zip' + chr(10) + '.' + chr(10)
        + 'Lib' + chr(92) + 'site-packages' + chr(10))
    print('[kit] Python bundled: %s (%.1f MB)' % (
        py_dir,
        sum(os.path.getsize(os.path.join(dp, f))
            for dp, _, fs in os.walk(py_dir) for f in fs) / 1048576))



def build(chars, make_zip):
    kit_dir = os.path.join(DIST, 'th123rl_kit')
    if os.path.exists(kit_dir):
        shutil.rmtree(kit_dir)
    os.makedirs(kit_dir)

    # Python文件
    files = trace_imports(ENTRY, ROOT)
    files.update(EXTRA)
    macros_dir = os.path.join(ROOT, 'macros')
    for fn in os.listdir(macros_dir):
        if fn.endswith('.py'):
            files.add(os.path.join('macros', fn))

    pkg = os.path.join(kit_dir, 'th123rl')
    n_py = 0
    for fn in sorted(files):
        src = os.path.join(ROOT, fn)
        if not os.path.exists(src):
            src = os.path.join(ROOT, 'tools', fn)
        if not os.path.exists(src):
            continue
        dst = os.path.join(pkg, fn)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        n_py += 1
    print('[kit] .py files: %d' % n_py)

    # 模型
    from kit_config import STORE_DIR
    models_dir = os.path.join(pkg, 'models')
    os.makedirs(models_dir)
    n_model = 0
    for ch in chars:
        for suf in ('', '_v'):
            src = os.path.join(STORE_DIR,
                               'model_ppo_%s%s.npz' % (ch, suf))
            if os.path.exists(src):
                shutil.copy2(src, models_dir)
                n_model += 1
    print('[kit] models: %d' % n_model)

    # K1: 便携Python
    _bundle_python(kit_dir)

    # 附产物
    open(os.path.join(kit_dir, 'requirements.txt'), 'w').write(
        'numpy>=1.26\ntorch>=2.0\n')
    open(os.path.join(kit_dir, 'config.json.template'), 'w',
         encoding='utf8').write(
        '{\n  "game_dir": "C:\\\\Games\\\\th123"\n}\n')

    # 收件人脚本
    for fn, content in [
            ('setup_helper.py', SETUP_HELPER),
            ('setup.bat', SETUP_BAT),
            ('start.bat', START_BAT),
            ('export_helper.py', EXPORT_HELPER),
            ('export.bat', EXPORT_BAT),
            ('README.txt', README)]:
        open(os.path.join(kit_dir, fn), 'w', encoding='utf8').write(content)

    # zip
    if make_zip:
        zn = os.path.join(
            DIST, 'th123rl_kit_v%s.zip' % time.strftime('%Y%m%d'))
        with zipfile.ZipFile(zn, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rd, _ds, fns in os.walk(kit_dir):
                for fn in fns:
                    fp = os.path.join(rd, fn)
                    zf.write(fp, os.path.relpath(fp, DIST))
        print('[kit] zip: %s (%.0f MB)' % (
            zn, os.path.getsize(zn) / 1048576))

    print('[kit] done: %d py + %d models' % (n_py, n_model))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chars', default='reimu,marisa,suika')
    ap.add_argument('--zip', action='store_true')
    a = ap.parse_args()
    build([c.strip() for c in a.chars.split(',')], a.zip)


if __name__ == '__main__':
    main()
