# -*- coding: utf-8 -*-
"""神谕全量包提取器 v2: 在v1(逐帧摘要)基础上保存完整原始包
(105B×2玩家 + 4B天气 + 17B×N对象) — 用于离线重建策略真实输入特征(BC数据)。

用法: oracle_batch2.py <port> [tps]
端口限probe段。产物: data/oracle_v2/shards/*.npz + manifest。
"""
import sys, os, time, json, shutil, hashlib, struct
import numpy as np
sys.path.insert(0, r'D:\temp\soku_arch')
sys.stdout.reconfigure(encoding='utf8')
from soku_arch.trainer_client import TrainerClient
from soku_arch.rep_file import parse_rep_file
from soku_arch.rep_meta import parse_rep_name

GAME = os.environ.get('SOKUAI_GAME_DIR', r'D:\temp\rl_game')
# ↑BH-4.2并行采集(2026-10-16): 游戏目录可按worker覆写 — 同目录多实例
# 的回放装载竞态(握手OK+零帧+秒退循环, mod中转文件互踩)用每worker
# 独立目录根治; 缺省单worker路径不变
EXE = os.path.join(GAME, 'th123.exe')
ML = os.path.join(GAME, 'ModLoaderSettings.json')
ROOT = r'D:\temp\expert_reps'
OUT = r'%USERPROFILE%\Desktop\workplace\th123_rl\data\oracle_v2'
ORACLE_SET = ['MemoryPatch', 'ReplayDnD-old', 'SokuAITrainerEnv', 'ChainCFix',
              'FixMeiling236']
OURS = {0, 1, 9}
OBJ_FMT = '<b2f4H'


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


def run_one(path, port, tps, staged, ilog_path=None):
    rep = parse_rep_file(path)
    shutil.copy(path, os.path.join(GAME, staged))
    cli = TrainerClient(port, EXE, GAME, launch=True, accept_timeout=90,
                        raw_argv=[staged],
                        env={'SOKUAI_PORT': str(port), 'SOKUAI_OBSERVE': '1',
                             # R40(第十一轮§6-1): 精确对齐通道 — mod逐逻辑帧
                             # 记录实际生效输入(inKeys), 与状态流同帧1:1,
                             # 取代rep文件输入流的互相关对齐(±24帧残余)
                             'SOKUAI_INPUTLOG': '1',
                             'SOKUAI_INPUTLOG_PATH': ilog_path or ''})
    pkts = bytearray()
    offsets = []
    scores = []
    prev = (0, 0)
    rounds = []
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
                    if len(offsets) < 100:
                        err = err or 'idle-noframe(%d)' % len(offsets)
                    break
                continue
            except Exception as e:
                err = str(e)[:60]
                break
            if kind == 'fault':
                err = 'fault@%d:%s' % (len(offsets), payload)
                break
            if kind in ('error', 'ended'):
                continue
            if kind == 'frame':
                last_frame = time.time()
                offsets.append(len(pkts))
                pkts += payload['left_raw_bytes']
                pkts += payload['right_raw_bytes']
                w = payload['weather']
                pkts += struct.pack('<bbH', w['displayed'], w['active'],
                                    w['timer'])
                objs = payload['objects']
                pkts.append(len(objs) & 0xFF)
                # R40(M-2双保险): mod侧已把对象总数截到255, 此处按计数字节
                # 再截一次 — 保证写入量与计数严格一致(防回绕流错位)
                for o in objs[:255]:
                    pkts += struct.pack(OBJ_FMT, *o)
                sl, sr = payload['left']['score'], payload['right']['score']
                scores.append((sl, sr))
                if (sl, sr) != prev:
                    rounds.append((len(offsets), sl, sr))
                    prev = (sl, sr)
                if sl == 2 or sr == 2:
                    break
    finally:
        cli.close()
    return rep, bytes(pkts), offsets, rounds, scores, err, time.time() - t0


def main():
    port = int(sys.argv[1])
    tps = int(sys.argv[2]) if len(sys.argv) > 2 else 480
    assert 20960 <= port <= 20999, 'oracle端口限probe段'

    d = {'modules': {'modules/%s/%s.dll' % (m, m): {'enabled': True}
                     for m in ORACLE_SET}}
    json.dump(d, open(ML, 'w', encoding='utf-8', newline=''), indent=4)
    os.makedirs(os.path.join(OUT, 'shards'), exist_ok=True)
    man = os.path.join(OUT, 'manifest.jsonl')
    done = set()
    if os.path.exists(man):
        for ln in open(man, encoding='utf8'):
            try:
                done.add(json.loads(ln)['shard'])
            except Exception:
                pass

    files = bilateral_reps()
    print('[v2] 双边rep %d, 已完成 %d' % (len(files), len(done)))
    for k, (fn, path) in enumerate(files):
        h = hashlib.md5(fn.encode('utf8')).hexdigest()[:8]
        shard = '%03d_%s.npz' % (k, h)
        if shard in done:
            continue
        for attempt in (1, 2):
            try:
                ilog_tmp = os.path.join(OUT, 'shards', shard + '.ilog.tmp')
                rep, pkts, offsets, rounds, scores, err, dur = run_one(
                    path, port, tps, 'oracleV2.rep', ilog_path=ilog_tmp)
            except Exception as e:
                # 审计2026-10-13采集链#1/#2: 兜底parse两宗罪 — ①截断rep
                # 再炸(R81b只修了harvest侧同型); ②死代码: err已置位+
                # offsets恒空 → 下方闸必拒 → 放弃continue, parse结果从不
                # 被消费。删。
                err, pkts, offsets, rounds, scores = 'exc:%s' % str(e)[:60], \
                    b'', [], [], []
                dur = 0
                rep = None
                ilog_tmp = None
            if len(offsets) > 100 and err is None:
                break
            print('  [重试%d] %s err=%s frames=%d' % (attempt, fn[:40], err,
                                                      len(offsets)))
            time.sleep(5)
        # R38(第九轮审计§2.2): 失败shard不写盘不记done — 原逻辑重试耗尽
        # 后照样落盘+记done → 永不复采, 坏数据静默入库(bc侧只能靠过滤兜底)
        if len(offsets) <= 100 or err is not None:
            print('  [放弃] %s err=%s frames=%d (不写盘, 下次重采)' % (
                fn[:40], err, len(offsets)))
            # R41(第十二轮§2-4): 清理重试残留的inputlog临时文件
            for _st in (locals().get('ilog_tmp', None), ):
                if _st and os.path.exists(_st):
                    os.remove(_st)
            continue
        meta = {'rep': fn, 'char_x': rep.char_x, 'char_y': rep.char_y,
                'pal_x': rep.pal_x, 'pal_y': rep.pal_y,
                'deck_x': list(rep.deck_x), 'deck_y': list(rep.deck_y),
                'seed': rep.seed, 'n_inputs': rep.n_frames,
                'frames': len(offsets), 'rounds': rounds,
                'score_final': list(scores[-1]) if scores else None,
                'err': err, 'dur_s': round(dur, 1), 'shard': shard,
                'fmt': 'L105R105W4N17'}
        # R40: 读取mod输入日志(每行 li lo ri ro, 与状态帧同序)
        # R41(第十二轮§2-3): ilog标记仅在真正入库时置True — 原无条件
        # 写True, 载入失败走回退时meta失真(未来消费者信任meta会埋雷)
        ilog_arr = None
        try:
            ilog_arr = np.loadtxt(ilog_tmp, dtype=np.uint16).reshape(-1, 4)
        except Exception:
            ilog_arr = None
        kw = {}
        if ilog_arr is not None and len(ilog_arr) >= len(offsets) >= 1:
            # 尾部可差1-2行(终局帧的日志先于客户端收帧结束) — 起始对齐截断
            kw['ilog'] = ilog_arr[:len(offsets)]
            meta['ilog'] = True
            print('  [inputlog] %d帧精确对齐' % len(offsets))
        elif ilog_arr is not None:
            print('  [inputlog] 行数%d<帧数%d — 不入库(走旧对齐)' % (
                len(ilog_arr), len(offsets)))
        tmp = os.path.join(OUT, 'shards', shard + '.tmp.npz')
        np.savez(tmp,
                 pkts=np.frombuffer(pkts, dtype=np.uint8),
                 offsets=np.array(offsets, dtype=np.int64),
                 inputs=np.array([rep.inputs[2 * f:2 * f + 2]
                                  for f in range(min(rep.n_frames,
                                                     len(offsets)))],
                                 dtype=np.uint16),
                 rounds=np.array(rounds),
                 meta=np.array(json.dumps(meta, ensure_ascii=False)), **kw)
        os.replace(tmp, os.path.join(OUT, 'shards', shard))
        if ilog_tmp and os.path.exists(ilog_tmp):
            os.remove(ilog_tmp)
        with open(man, 'a', encoding='utf8') as f:
            f.write(json.dumps(meta, ensure_ascii=False) + '\n')
        print('[%d/%d] %s 帧%d pkt=%dKB (%.0fs) err=%s' % (
            k + 1, len(files), fn[:40], len(offsets), len(pkts) // 1024, dur,
            err))
    print('[v2 完成]')


if __name__ == '__main__':
    main()
