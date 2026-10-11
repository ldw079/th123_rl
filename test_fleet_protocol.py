# -*- coding: utf-8 -*-
"""R56(fleet P1)协议冒烟测试 — 不boot游戏, 验证fleet数据链端到端:

A. episode npz模式往返(episode_core契约: 写→读→逐键相等+meta解析);
B. 快照发布→actor加载(learner.publish_snapshot → numpy PPOTrainer前向
   与GPU前向等价 — 双向格式的fleet路径);
C. 摸批+GPU更新(learner.update_from_episodes): 逐局GAE边界/宏计数合并/
   stored_logp消费;
D. 红线①行为验证: 篡改stored logp → 更新后参数必须不同(logp真的被用了);
E. 红线③机制验证: 同快照不同种子 → 采样序列必须不同;
F. collect_episodes按角色过滤+最新k个;
G. 版本文件原子语义(read_version/write_version轮转)。

数据: 生产reimu模型的真实维度 + 合成episode(动作从快照真实采样,
logP用与actor_worker.rec_logp相同的前向记录)。
"""
import glob
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf8')
except Exception:
    pass

from ppo import PPOTrainer, CONV_H, CONV_W  # noqa: E402
from episode_core import (episode_meta, save_episode_npz,  # noqa: E402
                          load_episode_npz, read_version, write_version,
                          build_contract, EpisodeContractError,
                          code_macro_count)
from feat_builder import FeatureBuilder  # noqa: E402


def test_contract(tr):
    """R63(P0-2): 合成episode的尺寸契约(与生产同构 — actor序列化时写)。"""
    return build_contract('reimu', tr.N_OUT, tr.N_SIDE, tr.N_OUT,
                          feat_dim=3 * CONV_H * CONV_W)


def synth_episode_dims(snap_ver, ep_idx, n_dec, rng, n_out, n_side):
    """同synth_episode但**可指定尺寸** — 用于生成他角色(marisa)的局,
    使契约与其真实宏数一致(伪造宽度会被写者自检正确拒写)。"""
    feats, sides, acts, rews, masks = [], [], [], [], []
    bc_t, opp_next, logps = [], [], []
    for i in range(n_dec):
        feat = rng.integers(0, 255, CONV_H * CONV_W * 3).astype(np.uint8)
        side = rng.standard_normal(n_side).astype(np.float32)
        mask = np.ones(n_out, dtype=bool)
        mid = int(rng.integers(0, n_out))
        feats.append(feat)
        sides.append(side)
        acts.append(mid)
        rews.append(float(rng.standard_normal()))
        masks.append(mask)
        bc_t.append(mid)
        opp_next.append(int(rng.integers(0, 8)) if i < n_dec - 1 else -1)
        logps.append(float(np.log(1.0 / n_out)))
    return dict(
        feats=np.stack(feats), sides=np.stack(sides),
        acts=np.array(acts, dtype=np.int64),
        rews=np.array(rews, dtype=np.float32),
        masks=np.stack(masks),
        bc_targets=np.array(bc_t, dtype=np.int64),
        opp_next=np.array(opp_next, dtype=np.int64),
        logps=np.array(logps, dtype=np.float32),
        ep_terms=np.array([True]),
        distill=np.zeros((0, 11), dtype=np.float32),
    )

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')
MODEL_PI = os.path.join(STORE, 'model_ppo_reimu.npz')
MODEL_V = os.path.join(STORE, 'model_ppo_reimu_v.npz')

PASS = []
FAIL = []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def synth_episode(tr, snap_ver, ep_idx, n_dec, rng):
    """合成一局: 动作=快照真实采样, logP=与actor_worker.rec_logp同源
    (同temp/mask前向取P[a]). 返回arrays dict(episode_core模式)。"""
    n_out = tr.N_OUT
    n_side = tr.N_SIDE
    feats, sides, acts, rews = [], [], [], []
    masks, bc_t, opp_next, logps = [], [], [], []
    for _ in range(n_dec):
        feat = rng.integers(0, 255, CONV_H * CONV_W * 3).astype(np.uint8)
        side = rng.standard_normal(n_side).astype(np.float32)
        mask = rng.random(n_out) > 0.2
        mask[0] = True
        # 与actor相同的记录方式: 同temp/mask前向
        P = tr._pi_forward(feat.reshape(1, -1), side.reshape(1, -1),
                           temp=tr._temp,
                           mask=mask.reshape(1, -1))[2][0]
        mid = int(rng.choice(n_out, p=P / P.sum()))
        feats.append(feat)
        sides.append(side)
        acts.append(mid)
        rews.append(float(rng.standard_normal()))
        masks.append(mask)
        bc_t.append(mid)
        opp_next.append(int(rng.integers(0, 8)) if _ < n_dec - 1 else -1)
        logps.append(float(np.log(max(P[mid], 1e-10))))
    return dict(
        feats=np.stack(feats), sides=np.stack(sides),
        acts=np.array(acts, dtype=np.int64),
        rews=np.array(rews, dtype=np.float32),
        masks=np.stack(masks),
        bc_targets=np.array(bc_t, dtype=np.int64),
        opp_next=np.array(opp_next, dtype=np.int64),
        logps=np.array(logps, dtype=np.float32),
        ep_terms=np.array([ep_idx % 2 == 0]),   # 边界混合: 终局/截断
        distill=np.zeros((2, 11), dtype=np.float32),
    )


def main():
    if not os.path.exists(MODEL_PI):
        print('跳过: 无生产模型 %s' % MODEL_PI)
        return
    from ppo_gpu import PPOTrainerGPU
    from learner_hub import (publish_snapshot, collect_episodes,
                             update_from_episodes, load_bc_bank)

    tmp = tempfile.mkdtemp(prefix='fleet_proto_')
    ep_dir = os.path.join(tmp, 'episodes')
    snap_dir = os.path.join(tmp, 'snap_reimu')
    os.makedirs(ep_dir, exist_ok=True)

    d = np.load(MODEL_PI)
    n_out = int(d['W2'].shape[1])
    # P0-A(从零#2): 原硬编码`5*n_out+308`与learner_hub同病 — R61t扩维
    # 316后此式过期658≠666, 严格加载当场拒载(测试抓的就是自己)。
    # 修: 与learner_hub同源从FeatureBuilder.CORE_DIMS派生。
    from feat_builder import FeatureBuilder
    n_side = 5 * n_out + FeatureBuilder.CORE_DIMS
    # 宽度与模型档一致(learner启动断言的同款检查)
    _f_side = int(d['W_side'].shape[0])
    d.close()
    assert _f_side == n_side, (
        '模型侧宽%d≠派生%d — 布局变更未同步' % (_f_side, n_side))
    print('模型维度: n_out=%d n_side=%d' % (n_out, n_side))

    # ---- B: 快照发布 → actor(numpy)加载 ----
    gpu_tr = PPOTrainerGPU(n_side=n_side, n_out=n_out)
    gpu_tr.load(MODEL_PI, MODEL_V)
    ver = publish_snapshot(snap_dir, gpu_tr)
    check('B1发布v1', ver == 1 and read_version(snap_dir) == 1)
    ver2 = publish_snapshot(snap_dir, gpu_tr)
    check('B2版本递增', ver2 == 2 and read_version(snap_dir) == 2)

    act_tr = PPOTrainer(n_side=n_side, n_out=n_out)
    act_tr.load(os.path.join(snap_dir, 'v2.npz'),
                os.path.join(snap_dir, 'v2_v.npz'))
    check('B3actor加载快照', act_tr.N_OUT == n_out
          and act_tr.N_SIDE == n_side)
    # 前向等价(numpy actor vs GPU learner): 同输入同掩码
    rng0 = np.random.default_rng(7)
    feat = rng0.integers(0, 255, CONV_H * CONV_W * 3).astype(np.uint8)
    side = rng0.standard_normal(n_side).astype(np.float32)
    mask = np.ones(n_out, dtype=bool)
    P_np = act_tr._pi_forward(feat.reshape(1, -1), side.reshape(1, -1),
                              temp=1.0, mask=mask.reshape(1, -1))[2][0]
    P_gpu = gpu_tr._pi_probs(feat, side, temp=1.0, mask=mask) \
        if hasattr(gpu_tr, '_pi_probs') else None
    if P_gpu is None:
        import torch
        import torch.nn.functional as F
        X = torch.from_numpy(feat.reshape(1, 3, CONV_H, CONV_W)
                             .astype(np.float32) / 255.0)
        S = torch.from_numpy(side.reshape(1, -1))
        with torch.no_grad():
            logits, _, _ = gpu_tr.net(X, S, 1.0,
                                      torch.from_numpy(
                                          mask.reshape(1, -1)))
            P_gpu = F.softmax(logits, dim=1).numpy()[0]
    diff = float(np.abs(P_np - P_gpu).max())
    check('B4前向等价', diff < 1e-3, '|ΔP|max=%.2e' % diff)

    # ---- B5: 严格加载(从零#2 P0-A共犯修复的行为钉) ----
    # 维度过期/错配时load必须响亮拒载 — 原只打印继续→随机权重被发布
    from ppo_gpu import PPOTrainerGPU as _G
    _bad = _G(n_side=n_side - 8, n_out=n_out)
    try:
        _bad.load(MODEL_PI, MODEL_V)
        check('B5严格加载拒错形', False, '错维度load未拒载!')
    except ValueError as e:
        check('B5严格加载拒错形', '形状不符' in str(e),
              'ValueError(形状不符)')

    # ---- B6: learner维度派生(从零#2 P0-A) — 不许回归hardcode 308 ----
    import inspect
    import learner_hub as _lh
    _lh_src = inspect.getsource(_lh.run_learner)
    check('B6learner CORE_DIMS派生',
          'FeatureBuilder.CORE_DIMS' in _lh_src and '+ 308' not in _lh_src,
          'n_side=5*n_out+CORE_DIMS')

    # ---- I: disk_guard清理行为(从零#2 fleet P2: 角色过滤+数值序) ----
    from learner_hub import _dg_cleanup
    _ep2 = os.path.join(tmp, 'ep_dg')
    os.makedirs(_ep2, exist_ok=True)
    for i in range(6):
        _p = os.path.join(_ep2, 'ep_reimu_0_%d.npz' % i)
        open(_p, 'wb').write(b'x')     # 清理只按文件名/mtime, 不解析
        os.utime(_p, (1000 + i, 1000 + i))
    _p_other = os.path.join(_ep2, 'ep_marisa_0_9.npz')
    open(_p_other, 'wb').write(b'x')
    _dg_cleanup(_ep2, snap_dir, char='reimu')
    _left_r = [f for f in os.listdir(_ep2) if 'reimu' in f]
    _left_m = [f for f in os.listdir(_ep2) if 'marisa' in f]
    check('I1 disk_guard角色过滤',
          len(_left_r) == 4 and len(_left_m) == 1,
          'reimu余%d marisa余%d(他角色局不动)' % (len(_left_r),
                                                  len(_left_m)))

    # ---- J: 池快照维度守卫(fleet首跑缺陷③: 木桩根因=陈旧宏数快照) ----
    from train_tm import _pool_snapshot_ok
    _d0 = np.load(MODEL_PI)
    _n0 = int(_d0['W2'].shape[1])
    _d0.close()
    check('J1维度守卫: 匹配宏数放行',
          _pool_snapshot_ok(MODEL_PI, _n0) is True)
    check('J2维度守卫: 陈旧宏数拒载',
          _pool_snapshot_ok(MODEL_PI, _n0 - 7) is False,
          '%d宏快照 vs %d宏库 → 拒(木桩防线)' % (_n0, _n0 - 7))
    check('J3维度守卫: 损坏/缺档拒载',
          _pool_snapshot_ok(os.path.join(tmp, 'nope.npz'), _n0) is False)

    # ---- A/F/C/D: episode往返+摸批+更新 ----
    ep_rng = np.random.default_rng(42)
    lens = [37, 51, 44]
    paths = []
    for i, L in enumerate(lens):
        arr = synth_episode(act_tr, snap_ver=2, ep_idx=i, n_dec=L,
                            rng=ep_rng)
        meta = episode_meta('reimu', 0, i, 2, 1003 + i, L,
                            contract=test_contract(act_tr))
        paths.append(save_episode_npz(ep_dir, 'reimu', 0, i, arr, meta))
        # F: 别的角色的局不误收(R63: 该局的契约必须用**真实marisa宏数** —
        # 用reimu宽度伪造他角色局会被写者自检正确拒写, 那是修复生效的证据)
        _m_n = code_macro_count('marisa')
        _m_side = 5 * _m_n + FeatureBuilder.CORE_DIMS
        arr2 = synth_episode_dims(2, 0, 5, ep_rng, _m_n, _m_side)
        save_episode_npz(ep_dir, 'marisa', 1, 0, arr2,
                         episode_meta('marisa', 1, 0, 2, 7, 5,
                                      contract=build_contract(
                                          'marisa', _m_n, _m_side, _m_n,
                                          feat_dim=3 * CONV_H * CONV_W)))

    got = collect_episodes(ep_dir, 'reimu', 3)
    check('F1角色过滤', all('reimu' in os.path.basename(p)
                          for p in got) and len(got) == 3)

    # ---- C5: 更新失败episode不丢(P1-C从零#2: 原消费即删=整批永久丢失) ----
    from learner_hub import quarantine as _quar
    _poison = save_episode_npz(
        ep_dir, 'reimu', 9, 9, synth_episode(act_tr, 2, 9, 8, ep_rng),
        episode_meta('reimu', 9, 9, 2, 99, 8, contract=test_contract(act_tr)))
    _bad_tr = _G(n_side=n_side - 8, n_out=n_out)   # 维度错配→update必炸
    try:
        update_from_episodes(_bad_tr, [_poison], 'reimu', '_t',
                             n_out, np.zeros(n_out, dtype=np.int64))
        check('C5失败批不删', False, '未抛异常?')
    except Exception:
        check('C5失败批不删', os.path.exists(_poison),
              '更新抛错后文件保留(%s)'
              % ('在' if os.path.exists(_poison) else '丢了!'))
    _qn = _quar([_poison])
    check('C5隔离区', _qn == 1
          and os.path.exists(os.path.join(ep_dir, 'failed',
                                          os.path.basename(_poison))),
          '移入failed/防无限崩溃循环')

    arr_b, meta_b = load_episode_npz(paths[0])
    check('A1键齐全', all(k in arr_b for k in
                        ('feats', 'sides', 'acts', 'rews', 'masks',
                         'bc_targets', 'opp_next', 'logps', 'ep_terms',
                         'distill')))
    check('A2 meta解析', meta_b['char'] == 'reimu'
          and meta_b['snap_ver'] == 2 and meta_b['decisions'] == 37)

    # C: 摸批更新(update_from_episodes = learner循环同一函数)
    counts0 = np.full(n_out, 150, dtype=np.int64)
    stats, counts1, n_eps, max_ver, N = update_from_episodes(
        gpu_tr, list(got), 'reimu', '_x', n_out, counts0)
    check('C1消费3局', n_eps == 3 and N == sum(lens)
          and max_ver == 2, 'N=%d' % N)
    check('C2宏计数增量', int(counts1.sum() - counts0.sum()) == N)
    check('C3消费即删', not any(os.path.exists(p) for p in got))
    check('C4 stats返回', isinstance(stats, dict)
          and 'kl' in stats and 'entropy' in stats)

    # D: 红线① — 篡改stored logp → 参数更新必须不同
    gpu_d1 = PPOTrainerGPU(n_side=n_side, n_out=n_out)
    gpu_d1.load(MODEL_PI, MODEL_V)
    gpu_d2 = PPOTrainerGPU(n_side=n_side, n_out=n_out)
    gpu_d2.load(MODEL_PI, MODEL_V)
    rng_t = np.random.default_rng(99)
    base_arrs = [synth_episode(act_tr, 2, i, 30, rng_t)
                 for i in range(2)]

    def _write_eps(arrs, tamper):
        paths = []
        for i, arr in enumerate(arrs):
            if tamper:
                arr = dict(arr)          # 不改原数组
                arr['logps'] = arr['logps'] + 0.5
            paths.append(save_episode_npz(
                ep_dir, 'reimu', 5, i, arr,
                episode_meta('reimu', 5, i, 2, 1, len(arr['acts']),
                             contract=test_contract(act_tr))))
        return paths

    update_from_episodes(gpu_d1, _write_eps(base_arrs, False),
                         'reimu', '_x', n_out, counts0)
    update_from_episodes(gpu_d2, _write_eps(base_arrs, True),
                         'reimu', '_x', n_out, counts0)
    w_diff = 0.0
    for (n1, p1), (n2, p2) in zip(gpu_d1.net.named_parameters(),
                                  gpu_d2.net.named_parameters()):
        if p1.requires_grad:
            w_diff = max(w_diff, float(
                (p1.detach() - p2.detach()).abs().max()))
    check('D1篡改logp→更新变红', w_diff > 1e-8,
          '|ΔW|max=%.2e' % w_diff)

    # H: 红线③补充(R57-2.1) — 多actor交错写入, 摸批不得饿死低编号actor
    #    (原文件名字典序恒取高编号actor文件; 用显式mtime构造交错序)
    for aid, ep_i, mt in ((0, 5, 1000), (1, 5, 2000),
                          (0, 6, 3000), (1, 6, 4000)):
        arr = synth_episode(act_tr, 2, ep_i, 10, ep_rng)
        p = save_episode_npz(
            ep_dir, 'reimu', aid, ep_i, arr,
            episode_meta('reimu', aid, ep_i, 2, 1, 10,
                         contract=test_contract(act_tr)))
        os.utime(p, (mt, mt))
    got2 = collect_episodes(ep_dir, 'reimu', 2)
    actors_in = sorted({int(os.path.basename(p).split('_')[2])
                        for p in got2})
    check('H1多actor覆盖(无饿死)', actors_in == [0, 1],
          '最新2局来自actor %s' % actors_in)
    for p in glob.glob(os.path.join(ep_dir, 'ep_reimu_*.npz')):
        os.remove(p)

    # E: 红线③ — 同快照不同种子 → 序列不同
    t_a = PPOTrainer(n_side=n_side, n_out=n_out)
    t_a.load(os.path.join(snap_dir, 'v2.npz'),
             os.path.join(snap_dir, 'v2_v.npz'))
    t_b = PPOTrainer(n_side=n_side, n_out=n_out)
    t_b.load(os.path.join(snap_dir, 'v2.npz'),
             os.path.join(snap_dir, 'v2_v.npz'))
    t_a.rng = np.random.default_rng(0 * 1_000_003 + 2)   # actor0
    t_b.rng = np.random.default_rng(1 * 1_000_003 + 2)   # actor1
    rng_e = np.random.default_rng(5)
    feat = rng_e.integers(0, 255, CONV_H * CONV_W * 3).astype(np.uint8)
    side = rng_e.standard_normal(n_side).astype(np.float32)
    seq_a = [t_a.sample(feat, side) for _ in range(60)]
    seq_b = [t_b.sample(feat, side) for _ in range(60)]
    check('E1种子独立性', seq_a != seq_b,
          '相同率%.0f%%' % (100 * sum(a == b for a, b in
                                      zip(seq_a, seq_b)) / 60))

    # G: 版本文件
    write_version(snap_dir, 7)
    check('G1版本写入', read_version(snap_dir) == 7)
    open(os.path.join(snap_dir, 'version'), 'w').write('garbage')
    check('G2损坏容错', read_version(snap_dir) == 0)

    # 清理: update_from_episodes的蒸馏副作用写了STORE/distill_*_x.npz
    for _p in (os.path.join(STORE, 'distill_data_reimu_x.npz'),):
        try:
            os.remove(_p)
        except OSError:
            pass

    shutil.rmtree(tmp, ignore_errors=True)
    print('\n==== %d PASS / %d FAIL ====' % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
