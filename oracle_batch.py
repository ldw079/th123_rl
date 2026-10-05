# -*- coding: utf-8 -*-
"""神谕批量提取器: 游戏原生自播双边专家rep + 被动状态流 → (输入,状态)分片。

用法: oracle_batch.py <lane> <n_lanes> <port> [tps]
  lane/n_lanes: 把rep列表按 index%n_lanes 分车道并行
每局: rl_game(神谕集5mod) tps提速, 空闲15s停止, 比分与文件名核对,
原子分片 + manifest(jsonl) + resume(已有分片跳过)。
"""
import sys, os, time, json, shutil, hashlib, re
import numpy as np
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch import win_probe
from soku_arch.trainer_client import TrainerClient
from soku_arch.rep_file import parse_rep_file
from soku_arch.rep_meta import parse_rep_name

GAME = r'D:\temp\rl_game'
EXE = os.path.join(GAME, 'th123.exe')
ML = os.path.join(GAME, 'ModLoaderSettings.json')
ROOT = r'D:\temp\expert_reps'
OUT = r'%USERPROFILE%\Desktop\workplace\th123_rl\data\oracle'
ORACLE_SET = [r'modules\MemoryPatch\MemoryPatch.dll',
              r'modules\ReplayDnD-old\ReplayDnD-old.dll',
              r'modules\SokuAITrainerEnv\SokuAITrainerEnv.dll',
              r'modules\ChainCFix\ChainCFix.dll',
              r'modules\FixMeiling236\FixMeiling236.dll']
OURS = {0, 1, 9}   # reimu / marisa / suika
PROBE_SEGMENT = (20960, 20999)   # portmap 的 probe 段 — oracle 通道专用


def assert_probe_port(port):
    """第八轮审查§7.3: argv端口必须过段校验 — SO_REUSEADDR 下撞段会
    静默串流到 live 训练(20800-20859)。oracle 一律限定 probe 段。"""
    lo, hi = PROBE_SEGMENT
    assert lo <= port <= hi, \
        "oracle端口 %d 越出 probe 段 [%d,%d] — 拒绝(防串流live训练)" % (port, lo, hi)


def bilateral_reps():
    out = []
    for fn in sorted(os.listdir(ROOT)):
        if not fn.lower().endswith('.rep'):
            continue
        p = os.path.join(ROOT, fn)
        try:
            with open(p, 'rb') as f:
                b = f.read(64)
            if len(b) < 64 or b[0] != 0xD2 or b[14] not in OURS or b[63] not in OURS:
                continue
            out.append((fn, p))
        except OSError:
            continue
    return out


def run_one(path, port, tps, lane, log):
    rep = parse_rep_file(path)
    staged = 'oracle%d.rep' % lane
    shutil.copy(path, os.path.join(GAME, staged))
    cli = TrainerClient(port, EXE, GAME, launch=True, accept_timeout=90,
                        raw_argv=[staged],
                        env={'SOKUAI_PORT': str(port), 'SOKUAI_OBSERVE': '1'})
    rows, rounds = [], []
    prev = (0, 0)
    t0 = time.time()
    err = None
    last_frame = t0
    try:
        cli.handshake()
        cli.set_speed(tps)
        while time.time() - t0 < 420:
            if cli.proc and cli.proc.poll() is not None:
                break
            try:
                kind, payload = cli.poll(timeout=3.0)
            except TimeoutError:
                if time.time() - last_frame > 8:
                    if len(rows) < 100:
                        err = err or 'idle-noframe(%d帧)' % len(rows)
                    break
                continue
            except Exception as e:
                err = str(e)[:60]
                break
            if kind == 'fault':
                err = 'fault@%d:%s' % (len(rows), payload)
                break
            if kind in ('error', 'ended'):
                continue
            if kind == 'frame':
                last_frame = time.time()
                L, R, W = payload['left'], payload['right'], payload['weather']
                rows.append((L['hp'], R['hp'], int(L['position.x'] * 10),
                             int(R['position.x'] * 10), L['action'], R['action'],
                             L['score'], R['score'], W['displayed'], W['active'],
                             W['timer']))
                if (L['score'], R['score']) != prev:
                    rounds.append((len(rows), L['score'], R['score']))
                    prev = (L['score'], R['score'])
                if L['score'] == 2 or R['score'] == 2:
                    break   # 终局判定: 比分到2即收尾(与mod的gameFinished同判据), 省去空闲等待
    finally:
        cli.close()
    return rep, rows, rounds, err, time.time() - t0


def main():
    lane = int(sys.argv[1])
    n_lanes = int(sys.argv[2])
    port = int(sys.argv[3])
    tps = int(sys.argv[4]) if len(sys.argv) > 4 else 480
    assert_probe_port(port)

    # R38(第九轮审计§2.2): 原utf-8-sig(BOM)+反斜杠键违反加载器格式纪律
    # — 与oracle_batch2同款正确写法: utf-8无BOM+正斜杠键
    d = {'modules': {'modules/%s/%s.dll' % (m, m): {'enabled': True}
                     for m in ('MemoryPatch', 'ReplayDnD-old',
                               'SokuAITrainerEnv', 'ChainCFix',
                               'FixMeiling236')}}
    json.dump(d, open(ML, 'w', encoding='utf-8', newline=''), indent=4)
    os.makedirs(os.path.join(OUT, 'shards'), exist_ok=True)
    man_path = os.path.join(OUT, 'manifest_lane%d.jsonl' % lane)
    done = set()
    if os.path.exists(man_path):
        for ln in open(man_path, encoding='utf8'):
            try:
                done.add(json.loads(ln)['shard'])
            except Exception:
                pass

    files = bilateral_reps()
    mine = [(i, fn, p) for i, (fn, p) in enumerate(files) if i % n_lanes == lane]
    print('[车道%d/%d] 双边rep共%d, 本道%d个, 已完成%d' % (
        lane, n_lanes, len(files), len(mine), len(done)))

    for k, (idx, fn, path) in enumerate(mine):
        h = hashlib.md5(fn.encode('utf8')).hexdigest()[:8]
        shard = os.path.join(OUT, 'shards', '%03d_%s.npz' % (idx, h))
        if os.path.basename(shard) in done:
            continue
        meta_name = parse_rep_name(fn[:-4], '')
        for attempt in (1, 2):
            try:
                rep, rows, rounds, err, dur = run_one(path, port, tps, lane, print)
            except Exception as e:
                err, rows, rounds = 'exc:%s' % str(e)[:60], [], []
                rep = parse_rep_file(path)
                dur = 0
                try:
                    cli_close_hack = None
                except Exception:
                    pass
            if len(rows) > 100 and err is None:
                break
            print('  [重试%d] %s err=%s frames=%d' % (attempt, fn[:40], err, len(rows)))
            time.sleep(3)
        fin = (rows[-1][6], rows[-1][7]) if rows else (None, None)
        exp = (meta_name.score_left, meta_name.score_right)
        match = (fin == exp) if None not in exp and None not in fin else None
        meta = {'idx': idx, 'rep': fn, 'char_x': rep.char_x, 'char_y': rep.char_y,
                'pal_x': rep.pal_x, 'pal_y': rep.pal_y,
                'deck_x': list(rep.deck_x), 'deck_y': list(rep.deck_y),
                'seed': rep.seed, 'n_inputs': rep.n_frames,
                'frames': len(rows), 'rounds': rounds,
                'score_final': fin, 'score_filename': exp, 'match': match,
                'err': err, 'dur_s': round(dur, 1), 'shard': os.path.basename(shard)}
        tmp = shard + '.tmp.npz'
        np.savez(tmp,
                 x=np.array(rows, dtype=np.float64) if rows else np.zeros((0, 11)),
                 inputs=np.array([rep.inputs[2 * f:2 * f + 2]
                                  for f in range(min(rep.n_frames, len(rows)))],
                                 dtype=np.uint16),
                 rounds=np.array(rounds),
                 meta=np.array(json.dumps(meta, ensure_ascii=False)))
        os.replace(tmp, shard)
        with open(man_path, 'a', encoding='utf8') as f:
            f.write(json.dumps(meta, ensure_ascii=False) + '\n')
        print('[%d/%d] %s 帧%d 比分%s vs 文件名%s %s (%.0fs)' % (
            k + 1, len(mine), fn[:44], len(rows), fin, exp,
            {True: '✓', False: '✗', None: '?'}[match], dur))
    print('[车道%d 完成]' % lane)


if __name__ == '__main__':
    main()
