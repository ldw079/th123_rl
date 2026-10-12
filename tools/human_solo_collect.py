# -*- coding: utf-8 -*-
r"""B2'/I(用户裁定2026-10-12): 人测采集走原版游戏, 特化版专供训练.

背景: 训练mod路径(TCP锁步+场景拉扯)在人测会话反复异常(渲染/帧率爬行),
用户裁定改走**原版游戏采集** — 特化版(D:\...\th123_train, D:\temp\rl_game)
专供训练, 两者彻底隔离。

流程:
  1. 用户在原版整合包(D:\\touhou\\hisoutensoku2026-06-15\\th123)正常游玩
     (自带全部日常mod+渲染; SokuAIOfflinePlayer无端口参数时休眠不挂钩);
  2. 对局结束在游戏内保存rep(整合包SaveRep mod支持);
  3. 本工具监视replay目录, 新rep自动归档到 STORE\\human_reps\\;
  4. **会话结束(Ctrl-C)或--process时**: 经oracle被动观测环境
     (D:\\temp\\rl_game, SOKUAI_OBSERVE=1, 高tps离线重放)解算逐帧状态
     → habit_detector → 习惯报告(教学产品化第一闭环, I项);
  5. 结果追加 tools/human_solo_report.json。

vs模型的标尺对局不在本工具范围(需训练侧mod — 后续另行方案)。

用法:
  python tools/human_solo_collect.py             # 启动原版游戏+监视
  python tools/human_solo_collect.py --watch     # 只监视(游戏已自行启动)
  python tools/human_solo_collect.py --process   # 立即处理所有未处理归档rep
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')

GAME = r'D:\touhou\hisoutensoku2026-06-15\th123'      # 原版整合包(用户日常)
EXE = os.path.join(GAME, 'th123.exe')
REPLAY_DIR = os.path.join(GAME, 'replay')

RL_GAME = r'D:\temp\rl_game'                          # oracle被动观测环境(特化)
RL_EXE = os.path.join(RL_GAME, 'th123.exe')
ML = os.path.join(RL_GAME, 'ModLoaderSettings.json')
ORACLE_SET = ['MemoryPatch', 'ReplayDnD-old', 'SokuAITrainerEnv',
              'ChainCFix', 'FixMeiling236']

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
ARCHIVE = os.path.join(STORE, 'human_reps')
REPORT = os.path.join(HERE, 'human_solo_report.json')
PORT = 20970          # probe段(oracle约定20960-20999)
TPS = 480             # 离线重放速度(非交互, 越快越省墙钟)
k32 = ctypes.windll.kernel32


def _md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def _set_priority_below_normal(pid):
    """R14延伸: 离线重放不与fleet抢CPU — BELOW_NORMAL优先级。"""
    h = k32.OpenProcess(0x0200 | 0x0100, False, pid)   # SET_LIMITED_INFORMATION
    if h:
        k32.SetPriorityClass(h, 0x4000)                # BELOW_NORMAL
        k32.CloseHandle(ctypes.c_void_p(h))


def _snapshot():
    """replay树下全部.rep的(路径, size, mtime) — 新文件检测基线。"""
    out = {}
    for dirpath, _dirs, files in os.walk(REPLAY_DIR):
        for fn in files:
            if not fn.lower().endswith('.rep'):
                continue
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
                out[p] = (st.st_size, st.st_mtime)
            except OSError:
                continue
    return out


def watch(session_archives):
    print('[solo] 监视rep目录: %s' % REPLAY_DIR)
    print('[solo] 正常游玩即可; 每局结束请在游戏内保存rep(SaveRep)')
    print('[solo] 结束采集: Ctrl-C (退出时自动批处理本会话rep)')
    base = _snapshot()
    print('[solo] 基线rep %d 个(不算新)' % len(base))
    try:
        while True:
            time.sleep(2)
            cur = _snapshot()
            for p, key in cur.items():
                if p in base:
                    if base[p] != key:
                        base[p] = key   # 变更中(SaveRep写入) — 等稳定
                    continue
                # 新文件: 二次确认稳定(3s后size/mtime不变才收)
                time.sleep(3)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if (st.st_size, st.st_mtime) != key:
                    base[p] = (st.st_size, st.st_mtime)
                    continue
                dst = _archive(p)
                if dst:
                    session_archives.append(dst)
                    base[p] = key
    except KeyboardInterrupt:
        print('\n[solo] 结束监视 — 本会话归档 %d 个rep' % len(session_archives))


def _archive(src):
    os.makedirs(ARCHIVE, exist_ok=True)
    try:
        h = _md5(src)
    except OSError as e:
        print('[solo] 归档失败(读取) %s: %s' % (src, e))
        return None
    dst = os.path.join(ARCHIVE, '%s_%s' % (
        time.strftime('%Y%m%d_%H%M%S'), os.path.basename(src)))
    try:
        shutil.copy2(src, dst)
        print('[solo] 归档: %s (md5=%s)' % (os.path.basename(src), h[:8]))
        return dst
    except OSError as e:
        print('[solo] 归档失败 %s: %s' % (src, e))
        return None


def _processed_hashes():
    done = set()
    if os.path.exists(REPORT):
        try:
            for entry in json.load(open(REPORT, encoding='utf8')):
                done.add(entry.get('md5'))
        except (OSError, ValueError):
            pass
    return done


def _switch_mods():
    """切rl_game的ModLoaderSettings到oracle观测集, 返回原内容(用于恢复)。"""
    orig = None
    if os.path.exists(ML):
        with open(ML, 'rb') as f:
            orig = f.read()
    d = {'modules': {'modules/%s/%s.dll' % (m, m): {'enabled': True}
                     for m in ORACLE_SET}}
    with open(ML, 'w', encoding='utf8', newline='') as f:
        json.dump(d, f, indent=4)
    return orig


def _restore_mods(orig):
    if orig is not None:
        with open(ML, 'wb') as f:
            f.write(orig)


def resolve_rep(path):
    """oracle被动观测重放一个rep → (meta, action_seq, final_score, err)。

    action_seq元素: (帧号, left.action, left.spirit, right.action)
    — 与habit_detector契约同构(human_match.py同源)。
    """
    from soku_arch.trainer_client import TrainerClient
    from soku_arch.rep_file import parse_rep_file
    from tm_env import CHAR
    inv_char = {v: k for k, v in CHAR.items()}

    rep = parse_rep_file(path)
    staged = 'hs_%d.rep' % int(time.time())
    shutil.copy(path, os.path.join(RL_GAME, staged))
    cli = TrainerClient(
        PORT, RL_EXE, RL_GAME, launch=True, accept_timeout=90,
        raw_argv=[staged],
        env={'SOKUAI_PORT': str(PORT), 'SOKUAI_OBSERVE': '1'})
    action_seq = []
    final = (0, 0)
    err = None
    t0 = time.time()
    try:
        if cli.proc and cli.proc.poll() is None:
            _set_priority_below_normal(cli.proc.pid)
        cli.handshake()
        cli.set_speed(TPS)
        while time.time() - t0 < 420:
            if cli.proc and cli.proc.poll() is not None:
                break
            try:
                kind, payload = cli.poll(timeout=3.0)
            except TimeoutError:
                if time.time() - t0 > 20 and not action_seq:
                    err = 'idle-noframe'
                    break
                continue
            except Exception as e:
                err = str(e)[:80]
                break
            if kind == 'fault':
                err = 'fault:%s' % str(payload)[:60]
                break
            if kind in ('error', 'ended'):
                continue
            if kind == 'frame':
                left, right = payload['left'], payload['right']
                action_seq.append((len(action_seq), left.get('action', 0),
                                   left.get('spirit', 0),
                                   right.get('action', 0)))
                final = (left.get('score', 0), right.get('score', 0))
                if 2 in final:
                    pass   # BO2/BO3小局分, 继续到流结束(可能续场)
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            os.remove(os.path.join(RL_GAME, staged))
        except OSError:
            pass
    meta = {
        'char': inv_char.get(rep.char_x, 'char%d' % rep.char_x),
        'opp_char': inv_char.get(rep.char_y, 'char%d' % rep.char_y),
        'mode': rep.mode, 'date': '%02d-%02d' % (rep.month, rep.day),
        'n_frames_rep': rep.n_frames,
    }
    return meta, action_seq, final, err


def process_archive(path):
    """处理单个归档rep: 解算→习惯检测→报告落盘。"""
    md5 = _md5(path)
    print('[solo] 处理 %s ...' % os.path.basename(path))
    meta, action_seq, final, err = resolve_rep(path)
    entry = {
        'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
        'rep': os.path.basename(path), 'md5': md5,
        'resolved_frames': len(action_seq), 'err': err,
        'final_score_left_right': list(final), **meta,
    }
    habit_txt = ''
    if action_seq and err is None:
        try:
            from habit_detector import detect_habits, habit_report
            habits = detect_habits(action_seq)
            habit_txt = habit_report(habits, meta['char'])
            entry['habits'] = [k for k, _h, _r in habits]
            entry['habit_report'] = habit_txt
        except Exception as e:
            entry['habit_err'] = str(e)[:120]
    entries = []
    if os.path.exists(REPORT):
        try:
            entries = json.load(open(REPORT, encoding='utf8'))
        except (OSError, ValueError):
            entries = []
    entries.append(entry)
    tmp = REPORT + '.tmp'
    with open(tmp, 'w', encoding='utf8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
    os.replace(tmp, REPORT)
    print('[solo] %s: 帧数%d 比分%d-%d %s%s' % (
        meta['char'], len(action_seq), final[0], final[1],
        'err=%s ' % err if err else '',
        '习惯:%s' % ','.join(entry.get('habits', [])) or '无'))
    if habit_txt:
        print(habit_txt)
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--watch', action='store_true', help='不启动游戏只监视')
    ap.add_argument('--process', action='store_true',
                    help='立即处理全部未处理归档rep(不启动游戏)')
    args = ap.parse_args()

    if args.process:
        done = _processed_hashes()
        todo = []
        for fn in sorted(os.listdir(ARCHIVE)) if os.path.isdir(ARCHIVE) else []:
            if not fn.lower().endswith('.rep'):
                continue
            p = os.path.join(ARCHIVE, fn)
            if _md5(p) not in done:
                todo.append(p)
        print('[solo] 待处理 %d 个归档rep' % len(todo))
        orig = _switch_mods()
        try:
            for p in todo:
                process_archive(p)
        finally:
            _restore_mods(orig)
        return

    if not args.watch:
        print('[solo] 启动原版游戏(无端口参数 — SokuAI mod休眠): %s' % EXE)
        subprocess.Popen([EXE], cwd=GAME)
        time.sleep(2)

    session_archives = []
    watch(session_archives)
    if session_archives:
        print('[solo] 批处理本会话rep(%d个) — oracle离线重放...' %
              len(session_archives))
        orig = _switch_mods()
        try:
            for p in session_archives:
                if _md5(p) in _processed_hashes():
                    continue
                process_archive(p)
        finally:
            _restore_mods(orig)
    print('[solo] 报告: %s' % REPORT)


if __name__ == '__main__':
    main()
