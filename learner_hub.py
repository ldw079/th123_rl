# -*- coding: utf-8 -*-
"""R56(fleet P1): learner_hub — 每角色中央Learner进程。

职责(scenario_b §3.2):
- 摸批: ≥K局或60s超时 → ppo_gpu.update(stored_logp=...) — 真重要性比;
- 保存: numpy双向格式(生产trainer/actor可读) → 快照发布(原子版本号);
- 单写者: 本进程是该角色唯一写者 — 模型/macro_counts/蒸馏/池快照;
- 仪表: 陈旧度(批内max版本滞后)/更新耗时/|KL|/熵/值损。

隔离纪律(A/B期): 默认suffix="_fleet" — 输出(model/macro_counts/蒸馏/池)
全走后缀路径, 不碰生产trainer正持有的无后缀档; 初始化权重从生产模型
载入(fleet=现训练的继续, 非重来)。全量迁移时--suffix ""接管主档。

用法: python learner_hub.py --char reimu [--batch-k 4] [--suffix _fleet]
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf8')

from ppo import PPOTrainer  # noqa: E402,F401 (结构推断用)
from episode_core import (load_episode_npz, save_distill_rows,  # noqa: E402
                          read_version, write_version)

try:
    from ppo_gpu import PPOTrainerGPU
except Exception as _e:            # torch缺失时响亮失败(fleet必须GPU更新)
    PPOTrainerGPU = None
    _GPU_ERR = _e

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
FLEET_DIR = os.path.join(STORE, 'fleet')
EP_DIR = os.path.join(FLEET_DIR, 'episodes')

BATCH_K = 4          # 默认摸批局数(上限8 — §6陈旧度论证)
BATCH_TIMEOUT = 60   # 超时秒数
SNAP_KEEP = 3        # 快照滚动保留版本数
POOL_EVERY = 50      # 池快照周期(聚合局数)


def load_bc_bank(char, n_side):
    """加载BC库**全量**(只读共享 — 与单实例trainer同一份锚, scenario_b §5:
    "bc_extra照常(BC库只读共享)"; 路径模式同train_tm._load_bc_bank)。
    R57(第十八轮2.2): 原启动时固定采64行终身复用 — bcw拉力会过拟合到
    固定64样本(单实例是每次update重采样)。改为返回全库, 每次update由
    update_from_episodes按updates序号派生rng重采样(可复现)。
    返回(X,S,Y)全量或None。"""
    pats = [os.path.join(STORE, 'bc_%s.npz' % char),
            os.path.join(HERE, 'data', 'bc', 'bc_%s.npz' % char)]
    p = next((q for q in pats if os.path.exists(q)), None)
    if p is None:
        return None
    d = np.load(p)
    if d['S'].shape[1] != n_side:
        print('[learner] BC库宽度不符(%d≠%d) — 跳过' % (
            d['S'].shape[1], n_side))
        return None
    return (d['X'], d['S'], d['Y'])


def publish_snapshot(snap_dir, trainer):
    """保存快照+原子递增版本号(actor在局边界轮询version)。"""
    os.makedirs(snap_dir, exist_ok=True)
    ver = read_version(snap_dir)
    pi = os.path.join(snap_dir, 'v%d.npz' % (ver + 1))
    vv = os.path.join(snap_dir, 'v%d_v.npz' % (ver + 1))
    trainer.save(pi, vv)
    write_version(snap_dir, ver + 1)
    # 滚动清理(保留最近SNAP_KEEP版; pi+v各一份)
    # R60(F-3): 原字典序 — v10排在v1与v2之间, 发布v10时刚发的最新版
    # 被自己删除(actor静默滞留旧版)。按文件名提取版本号数值排序。
    olds = sorted(
        glob.glob(os.path.join(snap_dir, 'v*.npz')),
        key=lambda p: int(''.join(c for c in os.path.basename(p)
                                  if c.isdigit()) or 0))
    for old in olds[:-SNAP_KEEP * 2]:
        try:
            os.remove(old)
        except OSError:
            pass
    return ver + 1


def collect_episodes(ep_dir, char, k):
    """该角色episode文件(按mtime排序, 取最新k个)。
    R57(第十八轮2.1): 原按文件名字典序 — 文件名主键是(actor_id, ep_idx),
    多actor时低编号actor的局恒排前部, [-k:]系统性饿死其经验(且残留文件
    使队列滞后仪表失真)。mtime即写入完成时刻(原子rename后), 与消费序
    一致。不足k返回全部(超时路径用), 空列表=无数据。
    R60(F-4): 排除在途.tmp.npz — glob模式会匹配半写tmp件, 入批判
    损坏即os.remove → 删掉活actor临时件 → 其os.replace抛异常, 整局
    数据静默丢失(原子写被消费者自己的glob击穿)。"""
    files = [f for f in glob.glob(
        os.path.join(ep_dir, 'ep_%s_*.npz' % char))
        if not f.endswith('.tmp.npz')]
    files.sort(key=lambda p: (os.path.getmtime(p), p))
    return files[-k:] if k else []


def update_from_episodes(gpu_tr, eps, char, suffix, n_macros,
                         macro_counts, bc_bank=None, snap_dir=None):
    """消费episode文件 → 合并批量 → GPU更新(stored_logp)。
    返回(stats, macro_counts, n_eps, max_ver, N); 无有效局n_eps=0。
    副作用: 蒸馏合并/宏计数增量/消费即删(单写者=调用方learner)。
    bc_bank: BC库全量(X,S,Y) — R57(2.2): 每次update按updates序号派生
    rng重采样64行(与单实例_sample_bc同语义, 可复现)。
    snap_dir: 提供时把宏计数随快照目录落盘counts.npy(R57 2.4下行通道)。"""
    all_feats, all_sides, all_acts = [], [], []
    all_rews, all_masks, all_bc_t = [], [], []
    all_opp, all_logp = [], []
    ep_lens, ep_terms = [], []
    max_ver = 0
    for ep_path in eps:
        try:
            arr, meta = load_episode_npz(ep_path)
        except Exception as e:
            print('[learner] %s 损坏(%s) — 丢弃' % (
                os.path.basename(ep_path), e))
            try:
                os.remove(ep_path)
            except OSError:
                pass
            continue
        n = len(arr['acts'])
        if n == 0:
            os.remove(ep_path)
            continue
        all_feats.append(arr['feats'])
        all_sides.append(arr['sides'])
        all_acts.append(arr['acts'])
        all_rews.append(arr['rews'])
        all_masks.append(arr['masks'])
        all_bc_t.append(arr['bc_targets'])
        all_opp.append(arr['opp_next'])
        all_logp.append(arr['logps'])
        ep_lens.append(n)
        ep_terms.append(bool(arr['ep_terms'][0]))
        max_ver = max(max_ver, int(meta.get('snap_ver', 0)))
        # 蒸馏行合并(episode_core共享函数=生产同源)
        if len(arr['distill']):
            save_distill_rows(STORE, char, suffix, arr['distill'])
        # 宏计数增量(acts即宏ID序列 — 单写者在本进程)
        macro_counts = macro_counts + np.bincount(
            arr['acts'], minlength=n_macros)[:n_macros]
        os.remove(ep_path)   # 消费即删(队列滞后=目录残留数, 天然仪表)
    if not all_acts:
        return None, macro_counts, 0, 0, 0

    feats = np.concatenate(all_feats)
    sides = np.concatenate(all_sides)
    acts = np.concatenate(all_acts)
    rews = np.concatenate(all_rews)
    masks = np.concatenate(all_masks)
    bc_t = np.concatenate(all_bc_t)
    opp_next = np.concatenate(all_opp)
    logps = np.concatenate(all_logp)

    # GPU更新(stored logp_old → 真ratio; temp=现行退火值,
    # 与单实例trainer的temp=self.ppo._temp同构)
    # R57(2.2): BC锚每update重采样(原终身固定64行 → bcw过拟合到定点)
    bc_use = None
    if bc_bank is not None:
        n_bc = len(bc_bank[2])
        m = min(64, n_bc)
        if m < n_bc:
            _bidx = np.random.default_rng(
                10_000 + int(gpu_tr._updates)).choice(
                n_bc, m, replace=False)
            bc_use = (bc_bank[0][_bidx], bc_bank[1][_bidx],
                      bc_bank[2][_bidx])
        else:
            bc_use = bc_bank
    stats = gpu_tr.update(
        feats, acts, rews, sides, ep_lens,
        ep_terms=ep_terms, masks=masks, bc_targets=bc_t,
        opp_next=opp_next, bc_extra=bc_use,
        temp=gpu_tr._temp, stored_logp=logps)
    # R57(2.4): 宏计数下行 — 随快照目录发布(actor换版时一并载入)
    if snap_dir is not None:
        _c_tmp = os.path.join(snap_dir, 'counts.npy.tmp.npy')
        np.save(_c_tmp, macro_counts)
        os.replace(_c_tmp, os.path.join(snap_dir, 'counts.npy'))
    return stats, macro_counts, len(all_acts), max_ver, len(acts)


def run_learner(char, batch_k=BATCH_K, suffix='_fleet'):
    if PPOTrainerGPU is None:
        print('[learner] ppo_gpu不可用: %r — fleet learner必须GPU更新'
              % (_GPU_ERR,))
        sys.exit(1)

    # R60(F-2): 初始权重优先读_fleet续档(learner重启续训) — 原恒读生产
    # 无后缀档 → 一崩即静默回滚全部权重/退火, 而version计数继续增(陈旧
    # 度仪表失义)+macro_counts却续档(不一致)。无_fleet档时(首次)才从
    # 生产模型初始化(fleet=现训练的继续)
    init_pi = os.path.join(STORE, 'model_ppo_%s%s.npz' % (char, suffix))
    init_v = os.path.join(STORE,
                          'model_ppo_%s%s_v.npz' % (char, suffix))
    if not (os.path.exists(init_pi) and suffix):
        init_pi = os.path.join(STORE, 'model_ppo_%s.npz' % char)
        init_v = os.path.join(STORE, 'model_ppo_%s_v.npz' % char)
    if not os.path.exists(init_pi):
        print('[learner] %s 无模型(%s) — 先跑现行trainer' % (
            char, init_pi))
        sys.exit(1)

    d = np.load(init_pi)
    n_out = int(d['W2'].shape[1])
    n_side = 5 * n_out + 308
    d.close()

    gpu_tr = PPOTrainerGPU(n_side=n_side, n_out=n_out)
    gpu_tr.load(init_pi, init_v)
    print('[learner] %s 初始化: n_out=%d meta(temp%.2f beta%.3f bcw%.2f '
          'updates%d)' % (char, n_out, gpu_tr._temp, gpu_tr._beta,
                          gpu_tr._bcw, gpu_tr._updates))

    snap_dir = os.path.join(FLEET_DIR, 'snap_%s' % char)
    os.makedirs(snap_dir, exist_ok=True)
    os.makedirs(EP_DIR, exist_ok=True)

    # 单写者输出路径
    pi_path = os.path.join(STORE, 'model_ppo_%s%s.npz' % (char, suffix))
    v_path = os.path.join(STORE, 'model_ppo_%s%s_v.npz' % (char, suffix))
    counts_path = os.path.join(
        STORE, 'macro_counts_%s%s.npy' % (char, suffix))
    pool_dir = (os.path.join(FLEET_DIR, 'pool', char) if suffix
                else os.path.join(STORE, 'pool', char))

    # 宏计数初始(生产档继承 — actor侧只读启动值, 增量由本进程合并)
    n_macros = n_out
    if os.path.exists(counts_path):
        macro_counts = np.load(counts_path).astype(np.int64)
    else:
        prod = os.path.join(STORE, 'macro_counts_%s.npy' % char)
        macro_counts = (np.load(prod).astype(np.int64)
                        if os.path.exists(prod) else
                        np.full(n_macros, 150, dtype=np.int64))
    if len(macro_counts) < n_macros:
        macro_counts = np.concatenate([
            macro_counts,
            np.zeros(n_macros - len(macro_counts), dtype=np.int64)])

    # 发布首版快照(actor可以开始) — counts.npy随发(R57 2.4下行通道)
    gpu_tr.save(pi_path, v_path)
    ver = publish_snapshot(snap_dir, gpu_tr)
    _c_tmp = os.path.join(snap_dir, 'counts.npy.tmp.npy')
    np.save(_c_tmp, macro_counts)
    os.replace(_c_tmp, os.path.join(snap_dir, 'counts.npy'))
    print('[learner] %s 初始快照 v%d' % (char, ver))

    bc_bank = load_bc_bank(char, n_side)
    last_update = time.time()
    agg_eps = 0    # 聚合局计数(池快照周期)

    while True:
        eps = collect_episodes(EP_DIR, char, batch_k)
        timeout = (time.time() - last_update) > BATCH_TIMEOUT
        if len(eps) < batch_k and not timeout:
            time.sleep(2)
            continue
        if not eps:
            time.sleep(5)
            continue

        # ---- 合并批量+GPU更新(逐局保边界 — GAE不许跨局泄漏) ----
        # R60(F-2): 主循环兜底 — 原一个畸形批即杀死learner(触发静默回滚
        # 链); 异常批丢弃并继续(权重档不动, supervisor重启是最后防线)
        try:
            t0 = time.time()
            stats, macro_counts, n_eps, max_ver, N = update_from_episodes(
                gpu_tr, eps, char, suffix, n_macros, macro_counts,
                bc_bank=bc_bank, snap_dir=snap_dir)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print('[learner] %s 批更新异常(%s: %s) — 丢弃该批继续'
                  % (char, type(e).__name__, e))
            last_update = time.time()
            continue
        if stats is None:
            continue
        dt = time.time() - t0
        last_update = time.time()
        agg_eps += n_eps

        # ---- 保存+发布(原子) ----
        gpu_tr.save(pi_path, v_path)
        ver = publish_snapshot(snap_dir, gpu_tr)
        print('[learner] %s 批%d局/%d决策 %.1fs v%d |KL|%.4f 熵%.2f '
              '值损%.4f 陈旧%d' % (
                  char, n_eps, N, dt, ver,
                  stats.get('kl', 0), stats.get('entropy', 0),
                  stats.get('value_loss', 0), ver - max_ver))

        # 宏计数原子落盘
        _mc_tmp = counts_path + '.tmp.npy'
        np.save(_mc_tmp, macro_counts)
        os.replace(_mc_tmp, counts_path)

        # 池快照(每POOL_EVERY聚合局 — 先v后pi=配对提交标记)
        if agg_eps % POOL_EVERY < batch_k:
            os.makedirs(pool_dir, exist_ok=True)
            ts = time.strftime('%Y%m%d_%H%M%S')
            shutil.copy2(v_path, os.path.join(pool_dir, ts + '_v.npz'))
            shutil.copy2(pi_path, os.path.join(pool_dir, ts + '.npz'))
            snaps = sorted(f for f in os.listdir(pool_dir)
                           if f.endswith('.npz')
                           and not f.endswith('_v.npz'))
            for f in snaps[:-3]:
                for _f in (f, f[:-4] + '_v.npz'):
                    try:
                        os.remove(os.path.join(pool_dir, _f))
                    except OSError:
                        pass
            print('[learner] %s 池快照 %s' % (char, ts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', required=True)
    ap.add_argument('--batch-k', type=int, default=BATCH_K)
    ap.add_argument('--suffix', default='_fleet',
                    help='输出档后缀(A/B隔离); 全量迁移用空串')
    args = ap.parse_args()
    run_learner(args.char, args.batch_k, args.suffix)


if __name__ == '__main__':
    main()
