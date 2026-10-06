# -*- coding: utf-8 -*-
"""R56(F4/P1): fleet共享库 — actor_worker与learner_hub的共同契约。

设计原则(scenario_b §3.1): 不复制粘贴episode循环(macros/side_driver双拷贝
漂移是本项目最大事故源)。实施修订: actor不重写循环, 而是**组合复用**
TMTrainer整体(见actor_worker.py)——比函数级抽取更强的防漂移(现行
train_tm的任何改进自动进入fleet)。本模块只放双方**共同引用**的契约:

1. episode npz模式(键名/含义/读写) — actor写, learner读;
2. 蒸馏数据合并(从train_tm._save_distill原文抽出, train_tm委托调用
   — 生产路径即本函数的回归测试);
3. 快照版本文件IO(原子递增/读取) — learner写, actor读。

不抽取train_tm._run_episode的内部(奖励/掩码/队列推进): 那些已经
通过TMTrainer组合被actor原样使用, 函数化反而制造第二份需同步的拷贝。
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

# ---- episode npz模式(单一事实源 — actor/learner/gate三方引用) ----
EP_KEYS = ("feats", "sides", "acts", "rews", "masks", "bc_targets",
           "opp_next", "logps", "ep_terms", "distill", "meta")
EP_SCHEMA = 1   # R57(2.6): 模式版本 — 格式演化时旧文件可判读/拒收
# feats      (N,14400) uint8   视觉特征(3帧: 今帧+2差分)
# sides      (N,n_side) f32    侧向量(宏one-hot×2+core+射程/untech块)
# acts       (N,) i64          实际执行宏ID(最终动作 — 含探针/价值引导重选)
# rews       (N,) f32          区间奖励(r_{k-1}记于rews[k-1], 尾段已入账)
# masks      (N,n_macros) bool 决策掩码(更新同掩码 — PPO比率干净)
# bc_targets (N,) i64          BC目标(自模仿)
# opp_next   (N,) i64          对手下一拍动作类(action//128), 末拍-1
# logps      (N,) f32          行为策略logP(a) — 采样时记录(红线①)
# ep_terms   (1,) bool         [not truncated](超时/比分未满=True→GAE尾零)
# distill    (D,11) f32        基准树诊断行(可空D=0)
# meta       json str          {char,actor,ep,snap_ver,seed,decisions,ts}
# schema     int               模式版本(当前1)


def episode_meta(char, actor_id, ep, snap_ver, seed, decisions):
    """构造episode meta(json str — npz内以0-d str数组存)。"""
    return json.dumps({
        "char": char, "actor": int(actor_id), "ep": int(ep),
        "snap_ver": int(snap_ver), "seed": int(seed),
        "decisions": int(decisions), "ts": time.strftime("%H:%M:%S"),
    })


def save_episode_npz(ep_dir, char, actor_id, ep_idx, arrays, meta_str):
    """原子写episode npz(tmp+rename, 项目惯例)。arrays须含EP_KEYS除meta。"""
    os.makedirs(ep_dir, exist_ok=True)
    fname = "ep_%s_%02d_%05d_%s.npz" % (char, actor_id, ep_idx,
                                        time.strftime("%Y%m%d_%H%M%S"))
    # 注意: np.savez对不以.npz结尾的名字会自动补.npz — tmp名必须以
    # .npz结尾, 否则os.replace找不到落盘文件
    tmp = os.path.join(ep_dir, fname + ".tmp.npz")
    dst = os.path.join(ep_dir, fname)
    data = dict(arrays)
    data["meta"] = np.array(meta_str)
    data["schema"] = np.array(EP_SCHEMA)
    np.savez(tmp, **data)
    os.replace(tmp, dst)
    return dst


def load_episode_npz(path):
    """读episode npz → (arrays dict, meta dict)。缺键=协议违规(响亮失败);
    schema不符(未来版本)=拒收并提示(旧版本无schema字段按v0放行 —
    fleet未上线前无存量文件, 此分支仅为格式演化预留)。"""
    d = np.load(path, allow_pickle=True)
    arrays = {k: d[k] for k in EP_KEYS if k != "meta"}
    if "schema" in d.files and int(d["schema"]) != EP_SCHEMA:
        d.close()
        raise ValueError("episode schema v%d≠当前v%d — 格式已演化, "
                         "旧文件需迁移工具" % (int(d["schema"]), EP_SCHEMA))
    meta = json.loads(str(d["meta"]))
    d.close()
    return arrays, meta


def save_distill_rows(store_dir, char, suffix, rows):
    """蒸馏数据增量合并(train_tm._save_distill原文抽出 — 双方共用)。
    rows: (D,11)行[dx,spirit,近身,macro_id,frame,dy,空中,近弹,朝向,tti,版边]。
    单写者纪律: 每角色一个档, 只由单实例trainer或fleet learner调用。"""
    if rows is None or len(rows) == 0:
        return
    path = os.path.join(store_dir,
                        "distill_data_%s%s.npz" % (char, suffix))
    X_new = np.array(rows, dtype=np.float32)
    Y_new = X_new[:, 3].astype(int)
    X_new[:, 3] = -1.0   # macro_id列在行内置-1(与旧格式一致: X为态势,Y为动作)
    if os.path.exists(path):
        try:
            d = np.load(path)
            X = np.concatenate([d["X"], X_new])
            Y = np.concatenate([d["Y"], Y_new])
            d.close()
        except Exception as e:
            # P0-5修复(真, 2026-09-21教训): 原静默except+覆盖, reimu档
            # 13.6万行样本无告警丢失 → 损坏时保留.corrupt供人工处置+大声报错
            print("[严重] distill档损坏(%s) → 保留%s.corrupt, 本批从新数据重建"
                  % (e, os.path.basename(path)))
            try:
                os.replace(path, path + ".corrupt")
            except OSError:
                pass
            X, Y = X_new, Y_new
    else:
        X, Y = X_new, Y_new
    if len(X) > 200000:   # 上限裁剪
        X, Y = X[-200000:], Y[-200000:]
    # P0-5修复(真): 临时文件+os.replace原子落盘(原裸np.savez中断=半档损坏源)
    # 诊断2026-10-06: 外部进程(疑360/索引)瞬时锁目标档 → os.replace
    # WinError 5 → 训练器重建环境(丢局churn)。短重试(3次×1s)消化瞬时锁。
    tmp = path + ".tmp.npz"
    np.savez(tmp, X=X, Y=Y)
    for _try in range(3):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if _try == 2:
                print("[distill] 目标档被锁3次 — 放弃本批合并(数据在"
                      "%s, 下批重试)" % os.path.basename(tmp))
                return
            time.sleep(1.0)


# ---- 快照版本文件IO(红线②: 局边界同步读version) ----

def write_version(snap_dir, ver):
    """原子写版本号(tmp+rename)。learner发布快照后调用。"""
    tmp = os.path.join(snap_dir, "version.tmp")
    with open(tmp, "w") as f:
        f.write(str(int(ver)))
    os.replace(tmp, os.path.join(snap_dir, "version"))


def read_version(snap_dir):
    """读当前版本号。无/损坏 → 0。actor每局边界调用(文件stat廉价)。"""
    vfile = os.path.join(snap_dir, "version")
    if not os.path.exists(vfile):
        return 0
    try:
        with open(vfile) as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return 0
