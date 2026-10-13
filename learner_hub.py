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
from feat_builder import FeatureBuilder  # noqa: E402 (P0-A: n_side唯一真值源)
from episode_core import (load_episode_npz, save_distill_rows,  # noqa: E402
                          read_version, write_version,
                          EpisodeContractError, check_contract,
                          code_macro_count, build_contract,
                          check_model_generation,
                          fleet_snap_dir, fleet_ep_dir)

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
SNAP_KEEP = 3        # 快照滚动保留版本数(批间隔~10-60min → 保留窗~45min,
                     # actor局边界轮询(~5min)远快于窗口, 无空窗)
POOL_EVERY = 50      # 池快照周期(聚合局数) — D3'(R65)重标定推导见
                     # train_tm.POOL_SNAPSHOT_EVERY注释(≈4.2h/快照@12局/h/角色)
DISK_MIN_GB = 2.0    # R61f(F3/D5): 磁盘满降级阈值(低于则清旧episode+告警)


def _dg_cleanup(ep_dir, snap_dir, char=None):
    """低盘清理动作(独立函数 — 行为测试直测; 触发由disk_guard阈值判定)。
    从零#2(fleet P2)两修: (a)episode按角色过滤(原跨角色删他局 —
    ep_dir是全角色共享, len-4保新删的是任意角色最新局);
    (b)快照按数值序删(原字典序v10<v2 → 刚发布的v10被自己删)。"""
    pat = 'ep_%s_*.npz' % char if char else 'ep_*.npz'
    import time as _t
    _now = _t.time()
    olds = sorted(glob.glob(os.path.join(ep_dir, pat)),
                  key=lambda p: (os.path.getmtime(p), p))
    # P2(审计#3): 活性宽限 — 刚落盘(<120s)的可能是活actor已完成的
    # 待消费局, 低盘清理不误删
    olds = [p for p in olds if _now - os.path.getmtime(p) > 120]
    for old in olds[:max(0, len(olds) - 4)]:   # 保留该角色最新4局
        try:
            os.remove(old)
        except OSError:
            pass
    # P2(审计#3): 降容硬杀残留的半写tmp(生产者已死, 原无清理方)
    for st in glob.glob(os.path.join(ep_dir, '*.tmp.npz')):
        try:
            if _now - os.path.getmtime(st) > 600:
                os.remove(st)
        except OSError:
            pass
    # 快照: 数值序(R60 F-3同款 — 字典序会把v10夹在v1与v2之间)
    olds = sorted(
        glob.glob(os.path.join(snap_dir, 'v*.npz')),
        key=lambda p: int(''.join(c for c in os.path.basename(p)
                                  if c.isdigit()) or 0))
    for v in olds[:-2]:
        try:
            os.remove(v)
        except OSError:
            pass


def disk_guard(ep_dir, snap_dir, char=None):
    """R61f(F3/D5): 磁盘满降级 — 低于阈值时清旧episode/过期快照,
    仍不足则False(调用方跳过快照落盘只保主档)。零依赖实现。
    从零#2(fleet P2): 真False路径(原恒return True — docstring承诺的
    降级从未发生)。"""
    import ctypes
    free_kb = ctypes.c_ulonglong(0)
    try:
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            'D:\\', None, None, ctypes.byref(free_kb))
        free_gb = free_kb.value / 1024 / 1024 / 1024
    except Exception:
        return True   # 查询失败不阻塞(宁可继续写)
    if free_gb >= DISK_MIN_GB:
        return True
    print('[learner] 磁盘低 %.1fGB(<%.0f) — 清理旧episode' % (
        free_gb, DISK_MIN_GB))
    _dg_cleanup(ep_dir, snap_dir, char)
    # 清后复查 — 仍低于半阈值则False(调用方跳过快照发布)
    free_kb2 = ctypes.c_ulonglong(0)
    try:
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            'D:\\', None, None, ctypes.byref(free_kb2))
        still = free_kb2.value / 1024 / 1024 / 1024 < DISK_MIN_GB * 0.5
    except Exception:
        still = False
    if still:
        print('[learner] 磁盘仍低 — 本批跳过快照发布(只保主档)')
    return not still


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
    """保存快照+原子递增版本号(actor在局边界轮询version)。
    从零#2(fleet P2): 版本单调地板 — 取目录内最大vN为基线(version档
    损坏/丢失时原回卷v1 → v1.npz被重写覆盖, actor静默回滚古权重)。"""
    os.makedirs(snap_dir, exist_ok=True)
    ver = read_version(snap_dir)
    _existing = [int(''.join(c for c in os.path.basename(p) if c.isdigit())
                     or 0)
                 for p in glob.glob(os.path.join(snap_dir, 'v*.npz'))]
    ver = max(ver, max(_existing) if _existing else 0)
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
    P1-C(从零#2): 原在load循环内"消费即删" — update崩溃=整批永久丢失
    (P0-A腐坏批的放大器)。修: 副作用(蒸馏落盘+episode删除)全部推迟到
    update成功后提交; 失败时文件留在原地由调用方隔离(quarantine)。
    bc_bank: BC库全量(X,S,Y) — R57(2.2): 每次update按updates序号派生
    rng重采样64行(与单实例_sample_bc同语义, 可复现)。
    snap_dir: 提供时把宏计数随快照目录落盘counts.npy(R57 2.4下行通道)。"""
    all_feats, all_sides, all_acts = [], [], []
    all_rews, all_masks, all_bc_t = [], [], []
    all_opp, all_logp = [], []
    ep_lens, ep_terms = [], []
    distill_batches = []
    ok_paths = []
    # 阶段0仪表(系列预测方案§2): episode消费即删(P1-C) → 批路径是唯一
    # 可持续测量点; no_grad前向不改训练语义
    series_recs = []
    # A1-1(未决问题方案§A): 被动性仪表 — 同挂点
    passivity_recs = []
    max_ver = 0
    for ep_path in eps:
        try:
            arr, meta = load_episode_npz(ep_path)
        except EpisodeContractError:
            # R63(P0-2): 契约不符=代际问题, **不是坏数据** — 不移入删除
            # 路径(原实现把契约违规也删掉, 把可诊断的证据销毁了)。
            # 上抛交由调用方按"必须重启"处置。
            raise
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
        try:
            from series_meter import (decode_match_outcome, position_from_meta,
                                      score_episode_aux)
            _h, _n = score_episode_aux(gpu_tr.net, arr, gpu_tr._temp)
            series_recs.append((position_from_meta(meta),
                                (_h if _n else None), _n,
                                decode_match_outcome(arr['rews'])))
        except Exception as _e:
            # 仪表失败绝不阻断训练(胜负桶降级保留)
            print('[learner] 仪表评分异常(%s) — 只计胜负桶' % _e)
            try:
                from series_meter import (decode_match_outcome,
                                          position_from_meta)
                series_recs.append((position_from_meta(meta),
                                    None, 0,
                                    decode_match_outcome(arr['rews'])))
            except Exception as e:
                # P2(审计#3, R67e同型): 静默吞掉系列统计解码错=盲区
                print('[learner] 系列统计解码异常(%s) — 单条跳过' % e)
        try:
            from passivity_meter import episode_passivity
            passivity_recs.append(episode_passivity(char, arr))
        except Exception as _pe:
            # 静默吞异常=事故温床(本仓库前科) — 打印一次真实报错
            import traceback as _tb
            print('[learner] 被动仪表异常: %r' % (_pe,))
            _tb.print_exc()
        max_ver = max(max_ver, int(meta.get('snap_ver', 0)))
        distill_batches.append(arr['distill'])
        ok_paths.append(ep_path)
        # 宏计数增量(acts即宏ID序列 — 仅内存, update成功后随返回值提交)
        macro_counts = macro_counts + np.bincount(
            arr['acts'], minlength=n_macros)[:n_macros]
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
    # ---- update成功 → 提交副作用(P1-C: 删除/蒸馏/计数下行) ----
    for ep_path, dist in zip(ok_paths, distill_batches):
        if len(dist):
            save_distill_rows(STORE, char, suffix, dist)
        os.remove(ep_path)
    # R57(2.4): 宏计数下行 — 随快照目录发布(actor换版时一并载入)
    if snap_dir is not None:
        _c_tmp = os.path.join(snap_dir, 'counts.npy.tmp.npy')
        np.save(_c_tmp, macro_counts)
        os.replace(_c_tmp, os.path.join(snap_dir, 'counts.npy'))
    try:
        from series_meter import curve_line
        stats['series_curve'] = curve_line(series_recs)
        from passivity_meter import passivity_line
        # R67e修正: 原打印块在run_learner作用域引用本函数局部的
        # passivity_recs → NameError被静默吞(被动曲线0条的根因 —
        # 作用域错位型集成缝, 教训: 跨函数仪表一律走stats字典)
        if passivity_recs:
            stats['passivity_line'] = passivity_line(passivity_recs)
    except Exception as e:
        # P2(审计#3, R67e同型): 被动曲线整段静默吞=0行假象复发的温床
        print('[learner] 被动曲线聚合异常(%s) — 本批跳过' % e)
    return stats, macro_counts, len(all_acts), max_ver, len(acts)


def quarantine(eps):
    """P1-C(从零#2): 更新失败的批移入failed/隔离区 — 不删(数据可查),
    且防止同一毒批被collect再次拾起→无限崩溃循环。隔离区跟随episode
    文件自身目录(而非模块级EP_DIR — 测试/迁移场景下二者可不同)。"""
    import shutil
    n = 0
    for p in eps:
        qd = os.path.join(os.path.dirname(p), 'failed')
        os.makedirs(qd, exist_ok=True)
        try:
            shutil.move(p, os.path.join(qd, os.path.basename(p)))
            n += 1
        except OSError:
            pass
    return n


def run_learner(char, batch_k=BATCH_K, suffix='_fleet'):
    # R61e(F3/D5): 单实例锁 — 双learner同角色=双写者竞争(静默互踩
    # 模型档); 锁文件+PID查活, 崩溃残留自动失效
    lock = os.path.join(FLEET_DIR, 'learner_%s%s.lock' % (char, suffix))
    os.makedirs(FLEET_DIR, exist_ok=True)
    if os.path.exists(lock):
        try:
            _old = int(open(lock).read().strip())
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, _old)
            if h:
                k32.CloseHandle(h)
                # R67b(2026-10-12 PID复用防御): OpenProcess对**任何**占用
                # 该PID的进程都成功 — 旧learner被灭后PID被无关进程回收 →
                # 误判"已有实例" → 重启循环20次耗尽(实证: 10-12 reimu,
                # 上游灭队事故的次生伤害)。追加命令行校验: 真learner才拒双开。
                import subprocess as _sp
                _cmd = _sp.run(
                    ['powershell', '-NoProfile', '-Command',
                     "(Get-CimInstance Win32_Process -Filter "
                     "'ProcessId=%d').CommandLine" % _old],
                    capture_output=True, text=True, timeout=20)
                if 'learner_hub' in (_cmd.stdout or ''):
                    print('[learner] %s 已有实例(PID=%d) — 退出' % (
                        char, _old))
                    sys.exit(1)
                print('[learner] %s 锁PID%d已被无关进程复用 — 清锁续启'
                      % (char, _old))
        except (ValueError, OSError):
            pass
        os.remove(lock)
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
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
    # P0-A(从零#2): 原硬编码 `5*n_out+308` — R61t扩维316后learner以
    # 658构网, load形状不符只打印不拒 → side/值头保持随机 → 腐坏模型
    # 被发布为v1 → actor真数据更新抛形状错 → fleet静默零学习。
    # 修: n_side从feat_builder.CORE_DIMS派生(与train_tm/side_driver同源)。
    n_side = 5 * n_out + FeatureBuilder.CORE_DIMS
    # 宽度断言(响亮): 模型档侧向量宽度必须与本派生值一致 — 不一致即
    # 维度推断过期/档损坏, 拒绝启动(强失败优于静默腐坏发布)。
    _f_side = int(d['W_side'].shape[0]) if 'W_side' in d.files else -1
    d.close()
    if _f_side != n_side:
        print('[learner] %s 模型侧宽%d≠派生%d(5*%d+CORE_DIMS%d) — '
              '维度过期或档损坏, 拒绝启动' % (
                  char, _f_side, n_side, n_out,
                  FeatureBuilder.CORE_DIMS))
        sys.exit(1)
    # R63(P0-2): 模型档宏数必须等于**当前代码**宏数 — 否则本learner会用
    # 一个动作空间与数据不同的网络训练并发布(旧版只与"自己刚载入的档"
    # 自洽, 代码宏数变了却无从察觉)。宽断言只保证侧向量, 不保证动作维。
    # 判据抽在 episode_core.check_model_generation(单一实现, 可行为测试 —
    # 文本锚定已被变异自检证明可被 `or n_out` 之类绕过)。
    _gen_bad = check_model_generation(char, n_out)
    if _gen_bad is not None:
        print('[learner] %s %s — 拒绝启动' % (char, _gen_bad))
        sys.exit(1)

    gpu_tr = PPOTrainerGPU(n_side=n_side, n_out=n_out)
    gpu_tr.load(init_pi, init_v)
    print('[learner] %s 初始化: n_out=%d meta(temp%.2f beta%.3f bcw%.2f '
          'updates%d)' % (char, n_out, gpu_tr._temp, gpu_tr._beta,
                          gpu_tr._bcw, gpu_tr._updates))

    # R63(P1-5): 快照与episode队列按suffix隔离(原共享=fleet+迁移双开时
    # 两learner互踩版本号/互删队列)。本地绑定屏蔽模块级常量。
    snap_dir = fleet_snap_dir(FLEET_DIR, char, suffix)
    EP_DIR = fleet_ep_dir(FLEET_DIR, suffix)
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
    # R63(P0-2): 发布前**入队一致性检查** — 盘上待消费的最新一代episode
    # 必须与本learner同代。不同代时立刻响亮退出, 而不是启动后再逐批
    # 发现(np.concatenate抛形状错→整批进failed/→无限continue, 生产事故
    # 形态: 13次启动拒绝 + 5次批隔离 + 26个failed文件)。
    _pre = collect_episodes(EP_DIR, char, batch_k)
    if _pre:
        try:
            _a, _m = load_episode_npz(_pre[-1],
                                      expect_contract=build_contract(
                                          char, n_out, n_side, n_out))
        except EpisodeContractError as _e:
            print('[learner] %s 入队契约不符 — 拒绝启动(不消费、不删除): %s'
                  % (char, _e))
            # 关键: 隔离**整个**队列而非本批 — 只隔离本批则下次启动又捡到
            # 同代旧档, 形成"启动→拒绝→重启"循环(把fleet变成无进展的
            # 重启风暴, 与"静默零学习"是同一后果的另一形态)。
            _allq = collect_episodes(EP_DIR, char, 0)
            _q = quarantine(_allq)
            print('[learner] %s 已将%d个不符代际的episode移入failed/隔离区'
                  ' (人工核查后删除; 处置见 docs/fleet_ignition_runbook.md)'
                  % (char, _q))
            sys.exit(1)
        except Exception as _e:
            print('[learner] %s 入队预检异常(%s: %s) — 拒绝启动'
                  % (char, type(_e).__name__, _e))
            sys.exit(1)

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
        except EpisodeContractError as e:
            # R63(P0-2): 契约不符=代际问题 → 隔离整队 + **响亮退出**
            # (让监督器重启)。原实现: 任何异常都"批隔离N个继续" →
            # learner永远活着、永远学不到东西, 而日志只留下隔离计数。
            print('[learner] %s 批契约不符 — 退出(码1)等待监督器重启: %s'
                  % (char, e))
            _allq = collect_episodes(EP_DIR, char, 0)
            _q = quarantine(_allq)
            print('[learner] %s 已隔离%d个不符代际episode(不删除, 人工核查)'
                  % (char, _q))
            sys.exit(1)
        except Exception as e:
            import traceback
            traceback.print_exc()
            _qn = quarantine(eps)
            print('[learner] %s 批更新异常(%s: %s) — 批隔离%d个继续'
                  % (char, type(e).__name__, e, _qn))
            last_update = time.time()
            continue
        if stats is None:
            continue
        # R61f: 磁盘守卫(发布快照前 — 低盘时降级清理; 仍低则跳过发布)
        _disk_ok = disk_guard(EP_DIR, snap_dir, char)
        dt = time.time() - t0
        last_update = time.time()
        agg_eps += n_eps

        # ---- 保存+发布(原子) ----
        gpu_tr.save(pi_path, v_path)   # 主档=耐久锚, 始终保存
        if not _disk_ok:
            print('[learner] %s 磁盘低 — 跳过快照发布(v保持)' % char)
            _mc_tmp = counts_path + '.tmp.npy'
            np.save(_mc_tmp, macro_counts)
            os.replace(_mc_tmp, counts_path)
            continue
        ver = publish_snapshot(snap_dir, gpu_tr)
        # aux读数(诊断2026-10-06: 日志行原未带 — 统计字典有)
        _aux = stats.get('aux_acc')
        _aux_s = (' aux命中%.0f%%' % (_aux * 100)) if _aux else ''
        print('[learner] %s 批%d局/%d决策 %.1fs v%d |KL|%.4f 熵%.2f '
              '值损%.4f 陈旧%d%s'
              % (char, n_eps, N, dt, ver,
                  stats.get('kl', 0), stats.get('entropy', 0),
                  stats.get('value_loss', 0), ver - max_ver, _aux_s))
        # 阶段0仪表: 系列位置分桶曲线随批留档(grep口径: 系列曲线)
        if stats.get('series_curve'):
            print('[learner] %s 系列曲线 %s'
                  % (char, stats['series_curve']))
        # A1-1: 被动曲线(远弹/逼近/开局攻)随批留档(经stats传递)
        if stats.get('passivity_line'):
            print('[learner] %s 被动曲线 %s'
                  % (char, stats['passivity_line']))

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
                           and not f.endswith('_v.npz')
                           # R63(P1-5): 前缀分流 — 同目录下还有剥削者写入的
                           # exploit_* 快照(exploiter.py --fleet→FLEET_DIR/pool)。
                           # 原实现无过滤地"只留最新3个"→ learner周期性地把
                           # 剥削者的针对性对手快照删掉(D4对抗压力静默消失),
                           # 且与train_tm._snapshot_pool的前缀保留纪律冲突
                           # (跨写者越权删除)。这里只清理本learner自己写的。
                           and not f.startswith('exploit_'))
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
