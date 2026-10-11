# -*- coding: utf-8 -*-
"""R56(fleet P1): actor_worker — 独立采集进程(组合复用TMTrainer)。

设计(scenario_b §3.1, 实施修订): actor**不重写**episode循环 — 直接
构造生产TMTrainer整体(奖励/掩码/frame_events/deck/league/COM阶梯全部
原样), 通过四个注入点接入fleet协议:

  1. 局边界快照注入: 包装_run_episode, 每局把learner发布的采样快照
     载入tr.ppo(train_tm内部的_ppo_act=deepcopy(self.ppo)自然承接,
     与现行"每局冻结"语义完全一致 — 红线②);
  2. logP记录: tr._fleet_logp_rec钩子(R56), 每决策点记录
     log π_snapshot(a_final|mask,bias) — 红线①采样侧;
  3. episode序列化: 覆盖_submit_update → 写ep npz(原子)而非本地更新;
  4. 单写者纪律: macro_counts/模型/蒸馏/池快照全部改道scratch或禁写
     (learner是这些档的唯一写者), actor只写自己的episode npz+stats。

红线③(环境独立): 每actor独立rng — ppo.load不还原rng且种子固定0,
同快照多actor会同流, 故按(actor_id, ver)重播种; deck/league rng按
actor_id独立播种。

用法: python actor_worker.py --char reimu --actor 0 [--port 21000]
"""
from __future__ import annotations

import argparse
import json
import os
import random as _rnd
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf8')

import portmap  # noqa: E402
from portmap import fleet_lane, fleet_port  # noqa: E402
from episode_core import (episode_meta, save_episode_npz,  # noqa: E402
                          read_version)

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
FLEET_DIR = os.path.join(STORE, 'fleet')
EP_DIR = os.path.join(FLEET_DIR, 'episodes')
# R63(P1-5): 快照目录从 episode_core 取**同一份**实现(actor与learner
# 必须一致, 否则actor读不到learner发布的快照=快照死链)。
from episode_core import fleet_snap_dir  # noqa: E402

SNAP_WAIT_S = 300   # 首版快照最长等待


def load_snapshot_weights(snap_dir, ver, tr):
    """把v{ver}快照载入tr.ppo(原子: 文件存在才动)。"""
    pi = os.path.join(snap_dir, 'v%d.npz' % ver)
    vv = os.path.join(snap_dir, 'v%d_v.npz' % ver)
    if not (os.path.exists(pi) and os.path.exists(vv)):
        return False
    tr.ppo.load(pi, vv)
    return True


def run_actor(char, actor_id, port, tps=480, episodes=1000,
              ep_timeout=240.0, opps=None):
    import train_tm
    from train_tm import TMTrainer

    # TypeError恢复路径在train()内`from portmap import rebuild_port` —
    # 打补丁于模块属性(导入时取当前属性值), 恢复端口改走fleet车道
    portmap.rebuild_port = (lambda slot, ep: fleet_port(actor_id, ep))
    portmap.rebuild_lane = lambda slot: fleet_lane(actor_id)

    # 对手池与run_parallel同构: 镜像首位+其余角色+COM(league动态解析)
    if opps is None:
        others = [c for c in ('reimu', 'marisa', 'suika') if c != char]
        opps = [char] + others + ['COM']

    # R63(P1-5): 与learner同源(默认_fleet后缀=历史路径)
    snap_dir = fleet_snap_dir(FLEET_DIR, char, '_fleet')
    scratch = os.path.join(FLEET_DIR, 'scratch_actor%02d' % actor_id)
    os.makedirs(scratch, exist_ok=True)

    tr = TMTrainer(char, port, tps=tps, episodes=episodes,
                   ep_timeout=ep_timeout, slot=actor_id,
                   opp=train_tm.build_opp_cycle(opps), com_difficulty=0)

    # ---- 注入点4: 单写者纪律(actor不写任何共享档) ----
    tr.macro_counts_path = os.path.join(scratch, 'macro_counts.npy')
    tr.pi_path = os.path.join(scratch, 'model_pi_unused.npz')
    tr.v_path = os.path.join(scratch, 'model_v_unused.npz')
    # 从零#2(fleet P2): league对手池根注入 — 原恒读生产POOL_DIR,
    # fleet learner的池快照(FLEET_DIR/pool)actor读不到=对手冻结
    tr._pool_root = os.path.join(FLEET_DIR, 'pool')
    # 从零#2(fleet P2): COM难度档按actor隔离(原共享文件多写者互踩)
    tr._com_diff_path = os.path.join(scratch, 'com_difficulty.json')
    tr._snapshot_pool = lambda: None      # 池快照=learner职责
    tr._save_distill = lambda rows: None  # 蒸馏行随episode npz走

    # ---- 注入点2: logP记录(红线①) ----
    # 在mid最终确定后记录(newbie探针/采样/价值引导重选三路统一);
    # 与采样同temp/mask/bias(行为策略=快照, PPO比率语义干净)
    # 注意: 闭包列表名fleet_logps — 不得叫logps(submit的logps参数
    # 会遮蔽它; A2点火首局实测: 断言读参数恒0, 红线①防线拦截了序列化)
    fleet_logps = []

    def rec_logp(mid, feat, side, mask, nbias):
        P = tr._ppo_act._pi_forward(
            feat.reshape(1, -1), side.reshape(1, -1),
            temp=tr._ppo_act._temp,
            mask=mask.reshape(1, -1) if mask is not None else None,
            bias=nbias)[2][0]
        fleet_logps.append(float(np.log(max(P[mid], 1e-10))))

    tr._fleet_logp_rec = rec_logp

    # ---- 注入点3: episode序列化(替代_submit_update) ----
    state = {'snap_ver': 0, 'ep': 0, 'events': 0}
    seed_base = actor_id * 1_000_003

    def report_stats():
        try:
            with open(os.path.join(scratch, 'stats.json'), 'w',
                      encoding='utf8') as f:
                json.dump({'opp_stats': {k: list(v) for k, v
                                         in tr._opp_stats.items()},
                           'com_difficulty': tr.com_difficulty,
                           'snap_ver': state['snap_ver'],
                           'ep': state['ep']}, f)
        except OSError:
            pass

    def submit(feats, acts, rews, sides, distill_rows, frames,
               masks_hist=None, bc_targets=None, truncated=False,
               opp_acts=None, logps=None):
        # logps参数(本地路径的ep_logps)忽略 — actor真源=fleet_logps闭包
        # (R60-F11后train_tm恒传此kwarg, 参数名须保留logps)
        if not feats:
            return
        assert len(fleet_logps) == len(acts), (
            "logP记录数%d != 决策数%d (红线①断链!)" % (len(fleet_logps),
                                                     len(acts)))
        assert masks_hist, "masks_hist为空 — 掩码缺失=更新比率污染, 拒绝序列化"
        # R63(P0-2): 写者声明的尺寸契约 — 读者据此判读代际, 不再靠
        # np.concatenate抛形状错定位根因。契约取自本actor**自己**的
        # 网络/宏库(train_tm构造时按同一CORE_DIMS派生)。
        from episode_core import build_contract
        _contract = build_contract(char, tr.n_macros, int(tr.ppo.N_SIDE), tr.n_macros)
        arrays = dict(
            feats=np.stack(feats).astype(np.uint8),
            sides=np.stack(sides).astype(np.float32),
            acts=np.asarray(acts, dtype=np.int64),
            rews=np.asarray(rews, dtype=np.float32),
            masks=np.stack(masks_hist),
            bc_targets=(np.asarray(bc_targets, dtype=np.int64)
                        if bc_targets is not None else
                        np.asarray(acts, dtype=np.int64)),
            opp_next=(np.asarray(opp_acts[1:] + [-1], dtype=np.int64)
                      if opp_acts else
                      np.full(len(acts), -1, dtype=np.int64)),
            logps=np.asarray(fleet_logps, dtype=np.float32),
            ep_terms=np.array([not truncated]),
            distill=(np.asarray(distill_rows, dtype=np.float32)
                     if distill_rows else
                     np.zeros((0, 11), dtype=np.float32)),
        )
        meta = episode_meta(char, actor_id, state['ep'],
                            state['snap_ver'],
                            seed_base + state['snap_ver'],
                            len(acts), contract=_contract)
        dst = save_episode_npz(EP_DIR, char, actor_id, state['ep'],
                               arrays, meta)
        print('[actor%d] %s ep%d %d决策 v%d 帧%.0f → %s' % (
            actor_id, time.strftime('%H:%M:%S'), state['ep'], len(acts),
            state['snap_ver'], frames, os.path.basename(dst)))
        fleet_logps.clear()
        state['ep'] += 1
        report_stats()

    tr._submit_update = submit

    # ---- 注入点1: 局边界快照注入(红线②) ----
    orig_run = tr._run_episode

    def run_with_snapshot():
        ver = read_version(snap_dir)
        if ver > 0 and ver != state['snap_ver']:
            if load_snapshot_weights(snap_dir, ver, tr):
                state['snap_ver'] = ver
                # R57(2.4): 宏计数下行 — 用learner合并档替换本地值
                # (配额探索基于全fleet真实计数; 缺档时保留本地累计)
                _cnt = os.path.join(snap_dir, 'counts.npy')
                if os.path.exists(_cnt):
                    try:
                        _c = np.load(_cnt).astype(np.int64)
                        if len(_c) == tr.n_macros:
                            tr.macro_counts = _c
                    except (OSError, ValueError):
                        pass
                print('[actor%d] 快照 → v%d' % (actor_id, ver))
        # R57(2.3): 每局重播种 — ppo.load不还原rng且tr.ppo在本actor永不
        # 更新, 同版本内每局deepcopy从同一rng状态出发 → 探针掷点/采样
        # 噪声的随机结构逐局同构(跨局相关性=红线③所防)。
        # R61f(F3): 线性式(actor*1e6+ver*1e6+ep)理论可碰撞(从零审计)
        # — SplitMix32终混消解
        _s = (seed_base + state['snap_ver'] * 1_000_001 + state['ep']) \
            & 0xFFFFFFFF
        _s ^= _s >> 16
        _s = (_s * 0x85EBCA6B) & 0xFFFFFFFF
        _s ^= _s >> 13
        _s = (_s * 0xC2B2AE35) & 0xFFFFFFFF
        _s ^= _s >> 16
        tr.ppo.rng = np.random.default_rng(_s)
        # deck/league rng独立(原种子=hash(char), 同角色actor会同步)
        tr._deck_rng = _rnd.Random(seed_base + state['ep'])
        fleet_logps.clear()   # 上一局异常中断的残记录清零
        return orig_run()

    tr._run_episode = run_with_snapshot

    # 首版快照等待(learner启动后数秒内发布v1)
    t0 = time.time()
    while read_version(snap_dir) == 0:
        if time.time() - t0 > SNAP_WAIT_S:
            print('[actor%d] %ds无首版快照 — 用盘上模型继续(v0)'
                  % (actor_id, SNAP_WAIT_S))
            break
        time.sleep(5)

    print('[actor%d] %s 开始(port=%d tps=%d 对手=%s)'
          % (actor_id, char, port, tps, '+'.join(opps)))
    try:
        tr.train()
    finally:
        try:
            tr.env.close()
        except Exception:
            pass
        report_stats()
    print('[actor%d] 完成%d局' % (actor_id, state['ep']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', required=True)
    ap.add_argument('--actor', type=int, required=True)
    ap.add_argument('--port', type=int, default=None)
    ap.add_argument('--tps', type=int, default=480)
    ap.add_argument('--episodes', type=int, default=1000)
    ap.add_argument('--ep-timeout', type=float, default=240.0)
    ap.add_argument('--opp', action='append', default=None,
                    help='对手规格(默认: 镜像+其余角色+COM)')
    args = ap.parse_args()

    port = args.port or fleet_port(args.actor)
    run_actor(args.char, args.actor, port, args.tps, args.episodes,
              args.ep_timeout, args.opp)


if __name__ == '__main__':
    main()
