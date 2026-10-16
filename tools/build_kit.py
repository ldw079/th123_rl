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
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, 'dist')
sys.path.insert(0, ROOT)   # kit_config在仓库根
# 单一事实源: 入口落点(start.bat引用与包内位置必须同源, 由同一变量派生)
ENTRY_REL = 'tools/human_match_v2.py'
ENTRY = os.path.basename(ENTRY_REL)
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
# 写读契约自验: runner读kit_config.GAME_DIR, 必须等于刚写入的路径
# (2026-10-13事故: 写kit根/读包内两处错位, 收件机回落开发机幽灵路径)
sys.path.insert(0, os.path.join(base, "th123rl"))
import kit_config
if os.path.normcase(os.path.abspath(kit_config.GAME_DIR)) != \\
        os.path.normcase(os.path.abspath(game_dir)):
    print("ERROR: config.json写读位置不一致! runner会读到:",
          kit_config.GAME_DIR)
    sys.exit(1)
print("config verified: runner GAME_DIR =", kit_config.GAME_DIR)
# RL-AI profile → game profile dir
import shutil
prof_src = os.path.join(base, "RL-AI.pf")
prof_dst = os.path.join(game_dir, "profile", "RL-AI.pf")
if os.path.exists(prof_src):
    os.makedirs(os.path.dirname(prof_dst), exist_ok=True)
    shutil.copy2(prof_src, prof_dst)
    print("RL-AI profile installed:", prof_dst)
else:
    print("WARN: RL-AI.pf not found in kit")
print("Setup complete. Run start.bat to begin.")
'''

SETUP_BAT = '''@echo off
chcp 65001 >nul
cd /d %~dp0
echo === TH123RL Kit Setup ===
echo.
set PY=%~dp0python\\python.exe
"%PY%" setup_helper.py
pause
'''

START_BAT = '''@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist "%~dp0config.json" (
  echo [start] config.json not found — please run setup.bat first!
  pause
  exit /b 1
)
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
"%~dp0python\\python.exe" th123rl/__ENTRY_REL__ --char %CHAR% --seconds %SECONDS%
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
    # rep归档目录与kit_config.REP_DIR同源(包内models/human_reps)
    rep_dir = os.path.join("th123rl", "models", "human_reps")
    if os.path.isdir(rep_dir):
        for f in glob.glob(os.path.join(rep_dir, "*.rep")):
            z.write(f, os.path.relpath(f))
print("Exported:", fn)
print("Please send this file back!")
'''

EXPORT_BAT = '''@echo off
chcp 65001 >nul
cd /d %~dp0
"%~dp0python\\python.exe" export_helper.py
pause
'''

README = '''TH123RL 人机对战采集套件
==========================

【一、首次使用】
  1. 解压本文件夹到任意位置
  2. 双击 setup.bat — 首次配置:
     输入你的东方非想天则游戏目录(须含th123.exe),
     自动安装RL-AI档案并生成config.json
     (Python和依赖已内置, 无需额外安装)
  3. 双击 start.bat 开始对战:
     - 启动你的东方非想天则
     - 进入 VS PLAYER 模式
     - P2 侧选择 RL-AI 档案
     - 选好角色开始对局, AI自动接管P2

【二、结束一场采集 — 重要纪律】
  - 让start.bat黑窗口倒计时自然结束, 或在黑窗口里按 Ctrl+C
  - 不要直接点X强关窗口 — 那一场的比分记录和rep归档可能丢失
  - 每局打完在游戏结算画面记得保存rep
    (不保存的对局只有比分、没有回放)

【三、数据回传 — 打完之后做这三步】
  第一步: 确认数据已落盘
    - 按上面第二节的方式正常结束采集
  第二步: 双击 export.bat 导出
    - 窗口显示 "Exported: match_data_年月日_时分秒.zip" 即成功
    - 文件出现在kit文件夹里, 通常几百KB到几MB
    - 可以每天打完导一次, 也可以攒几天一起导
      (每次导出自动包含全部记录, 重复导出生成新文件名, 不会覆盖)
  第三步: 把zip发回给研究者
    - 直接微信/QQ发送 match_data_*.zip 即可
    - 发送成功后可删除旧的 match_data_*.zip, 避免下次混淆
    - 数据只含对局比分记录和回放文件, 不含其他个人信息

【四、常见问题】
  Q: 找不到导出的文件?
  A: 在kit文件夹(有export.bat的那层)按时间排序,
     找 match_data_ 开头最新的zip
  Q: zip是空的/特别小?
  A: 说明之前采集没正常结束(黑窗口被强关过),
     下次按第二节方式结束即可
  Q: 换电脑/挪文件夹怎么办?
  A: 整个kit文件夹原样拷走就能继续用, 不用重新setup
  Q: 对战期间注意什么?
  A: 请不要切换窗口(AI需要读取游戏内存)

【环境要求】
  - Windows 10/11
  - 东方非想天则 (整合包或原版均可)
  - 游戏exe版本需兼容 (setup会自动检查)

  如遇问题请联系研究者
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



def _atomic_swap(staging, final_dir):
    """staging → final 原子交换; 任何失败下旧包保持完好."""
    old = final_dir + '_old'
    if os.path.exists(old):
        shutil.rmtree(old)
    if os.path.exists(final_dir):
        os.rename(final_dir, old)
    try:
        os.rename(staging, final_dir)
    except OSError:
        if os.path.exists(old) and not os.path.exists(final_dir):
            os.rename(old, final_dir)   # 换回, 保旧包
        raise
    if os.path.exists(old):
        shutil.rmtree(old)


def postcheck(zn, entry_rel):
    """zip内结构断言 — 验制品不验过程(2026-10-13教训)."""
    z = zipfile.ZipFile(zn)
    names = [n.replace(chr(92), '/') for n in z.namelist()]
    P = 'th123rl_kit/'
    entry = P + 'th123rl/' + entry_rel
    assert entry in names, '[postcheck] zip缺入口: %s' % entry
    stray = P + 'th123rl/' + os.path.basename(entry_rel)
    assert stray not in names, '[postcheck] 入口错位到包根: %s' % stray
    n_ok = 0
    for key in ('setup.bat', 'start.bat', 'export.bat',
                'README.txt', 'RL-AI.pf', 'config.json.template'):
        assert P + key in names, '[postcheck] zip缺 %s' % key
        n_ok += 1
    sb = z.read(P + 'start.bat').decode('utf8', 'replace')
    assert ('th123rl/' + entry_rel) in sb, \
        '[postcheck] start.bat引用与入口落点不同源'
    n_ok += 1
    npz = [n for n in names
           if n.startswith(P + 'th123rl/models/') and n.endswith('.npz')]
    assert npz, '[postcheck] 无模型npz'
    n_ok += 1
    print('[kit] postcheck: %d项断言全过 (npz=%d)' % (n_ok, len(npz)))


def recipient_sim(zn):
    """收件人模拟: 解压→仅包内Python→双向验证config行为. 不绿不出包.

    ① 未跑setup: 必须明确报错指向setup.bat(不许回落开发机幽灵路径)
    ② 跑过setup: config.json(写在kit根)必须被runner真正读到
    """
    import subprocess
    import tempfile
    from kit_config import GAME_DIR as _gd, EXE_MD5 as _md5   # 开发机真值
    tmp = tempfile.mkdtemp(prefix='kit_sim_')
    try:
        with zipfile.ZipFile(zn) as z:
            z.extractall(tmp)
        root = os.path.join(tmp, 'th123rl_kit')
        py = os.path.join(root, 'python', 'python.exe')
        entry = os.path.join(root, 'th123rl', *ENTRY_REL.split('/'))
        r = subprocess.run([py, entry, '--help'], capture_output=True,
                           text=True, timeout=180)
        assert r.returncode != 0 and 'setup' in (r.stdout + r.stderr), \
            '[sim] 无config时未明确报错: rc=%s tail=%s' % (
                r.returncode, (r.stdout + r.stderr)[-200:])
        json.dump({'game_dir': _gd, 'exe_md5': _md5},
                  open(os.path.join(root, 'config.json'), 'w'))
        r = subprocess.run([py, entry, '--help'], capture_output=True,
                           text=True, timeout=180)
        assert r.returncode == 0, \
            '[sim] 有config时入口失败: %s' % r.stderr[-300:]
        code = ('import sys;sys.path.insert(0,r"%s");import kit_config;'
                'assert kit_config.GAME_DIR==r"%s",kit_config.GAME_DIR;'
                'print("GAMEDIR_OK")' % (
                    os.path.join(root, 'th123rl'), _gd))
        chk = subprocess.run([py, '-c', code], capture_output=True,
                             text=True, timeout=180)
        assert 'GAMEDIR_OK' in chk.stdout, \
            '[sim] GAME_DIR未生效: %s' % (chk.stdout + chk.stderr)[-300:]
        print('[kit] recipient_sim: 无config明确报错 + 有config路径生效, 双向通过')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build(chars, make_zip):
    final_dir = os.path.join(DIST, 'th123rl_kit')
    kit_dir = os.path.join(DIST, 'th123rl_kit_staging')   # staging: 失败不伤旧包
    if os.path.exists(kit_dir):
        shutil.rmtree(kit_dir)
    os.makedirs(kit_dir)

    # Python文件
    files = trace_imports(ENTRY, ROOT)
    files.update(EXTRA)
    files.add(ENTRY_REL)   # 入口以带前缀路径入集合(与start.bat同源)
    macros_dir = os.path.join(ROOT, 'macros')
    for fn in os.listdir(macros_dir):
        if fn.endswith('.py'):
            files.add(os.path.join('macros', fn))

    pkg = os.path.join(kit_dir, 'th123rl')
    n_py = 0
    for fn in sorted(files):
        src = os.path.join(ROOT, fn)
        rel = fn
        if not os.path.exists(src):
            # tools/下的文件必须保留子目录前缀, 否则入口
            # (start.bat 引用 th123rl/tools/human_match_v2.py) 落错位置
            src = os.path.join(ROOT, 'tools', fn)
            rel = os.path.join('tools', fn)
        if not os.path.exists(src):
            continue
        dst = os.path.join(pkg, rel)
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
        'numpy>=1.26\n')   # K4: 仅numpy(内置Python无torch)
    open(os.path.join(kit_dir, 'config.json.template'), 'w',
         encoding='utf8').write(
        '{\n  "game_dir": "C:\\\\Games\\\\th123"\n}\n')

    # 收件人脚本(start.bat入口引用由ENTRY_REL派生 — 单一事实源)
    for fn, content in [
            ('setup_helper.py', SETUP_HELPER),
            ('setup.bat', SETUP_BAT),
            ('start.bat', START_BAT.replace('__ENTRY_REL__', ENTRY_REL)),
            ('export_helper.py', EXPORT_HELPER),
            ('export.bat', EXPORT_BAT),
            ('README.txt', README)]:
        open(os.path.join(kit_dir, fn), 'w', encoding='utf8').write(content)

    # RL-AI profile(setup时自动安装到对方游戏profile目录)
    from kit_config import GAME_DIR as _gdir
    _pf_src = os.path.join(_gdir, 'profile', 'RL-AI.pf')
    if os.path.exists(_pf_src):
        shutil.copy2(_pf_src, os.path.join(kit_dir, 'RL-AI.pf'))
        print('[kit] RL-AI.pf included')
    else:
        print('[kit] WARN: RL-AI.pf not found at %s' % _pf_src)

    # zip: 先写tmp → postcheck+收件人模拟全绿 → 才落正式名(不绿不出包)
    if make_zip:
        zn = os.path.join(
            DIST, 'th123rl_kit_v%s.zip' % time.strftime('%Y%m%d'))
        tmp_zn = zn + '.tmp'
        with zipfile.ZipFile(tmp_zn, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rd, _ds, fns in os.walk(kit_dir):
                for fn in fns:
                    fp = os.path.join(rd, fn)
                    arc = ('th123rl_kit/' + os.path.relpath(fp, kit_dir)
                           ).replace(os.sep, '/')
                    zf.write(fp, arc)
        postcheck(tmp_zn, ENTRY_REL)
        recipient_sim(tmp_zn)
        os.replace(tmp_zn, zn)
        print('[kit] zip: %s (%.0f MB)' % (
            zn, os.path.getsize(zn) / 1048576))

    # staging→正式目录原子交换(旧包在任何失败下保持完好)
    _atomic_swap(kit_dir, final_dir)
    print('[kit] done: %d py + %d models' % (n_py, n_model))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chars', default='reimu,marisa,suika')
    ap.add_argument('--zip', action='store_true')
    a = ap.parse_args()
    build([c.strip() for c in a.chars.split(',')], a.zip)


if __name__ == '__main__':
    main()
