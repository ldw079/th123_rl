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
EP_SCHEMA = 2   # R63: v1→v2 增contract块(尺寸/布局指纹); 旧v1文件拒收
# Gen-1(2026-10-20): schema v3 = v2 + 可选 hist (N,8,3) int8 决策历史
# (env TH123_MEM_DECISIONS>0 时写; 旧 v2 读入 hist=None, learner 补零)
try:
    from mem_v1 import MEM_DECISIONS as _MEM_DEC
except Exception:
    _MEM_DEC = 0
EP_SCHEMA_MEM = 3
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
# meta       json str          {char,actor,ep,snap_ver,seed,decisions,ts,contract}
# schema     int               模式版本(当前2)

FEAT_DIMS = 14400   # 3×60×80 视觉栈(与ppo.CONV_H/W同源; 此处硬编码以
#                     避免episode_core↔ppo循环import; 变更须同步ppo并跑门禁)


class EpisodeContractError(ValueError):
    """episode 契约违规(尺寸/布局/角色不符) — **不可就地吞掉**。

    R63(P0-2, 2026-10-07架构审查): 生产事故实证 — CORE_DIMS 316→330 与
    宏数 63→70 的代码改动落在运行中的进程边界上时: actor(旧码)继续按其
    尺寸产 episode, learner(新码)按模型档推断尺寸 → `np.concatenate` 抛
    ValueError → 整批进 failed/ 永久丢弃 + learner 无限 continue, 而两侧
    进程"都活着"。实测 learner_reimu.log 13次启动拒绝 + 5次批隔离 +
    failed/ 26个文件(~300MB)。
    本异常让调用方能把"契约不符"与"单批数据坏"区分开: 前者必须重启
    (代码/产物已不同代), 后者可隔离后继续。
    """


def code_macro_count(char):
    """**代码侧**宏库大小(learner侧唯一真值源, 与actor/train_tm同源)。

    与 train_tm._load_char_libs 同约定: reimu→macros.MACROS,
    其余→macros.<char>.MACROS_<CHAR>。取不到返回None(调用方降级)。
    """
    try:
        if char == "reimu":
            import macros as _m
            return len(_m.MACROS)
        _m = __import__('macros.%s' % char, fromlist=['*'])
        return len(getattr(_m, 'MACROS_%s' % char.upper()))
    except Exception:
        return None


def _ppo_feat_dims():
    """视觉特征宽度(单真值源: ppo 的 3×CONV_H×CONV_W)。取不到→FEAT_DIMS。

    生产必须与 ppo 实际卷积输入一致; 测试用合成小特征时由写者显式覆盖
    (见 build_contract(feat_dim=...)), 避免"真实常量"对合成数据误报。
    """
    try:
        import ppo as _ppo
        return int(3 * _ppo.CONV_H * _ppo.CONV_W)
    except Exception:
        return int(FEAT_DIMS)


def build_contract(char, n_out, n_side, n_macros, feat_dim=None):
    """构造 episode 契约块(写者声明 + 读者校验的共同格式)。

    n_out    策略网络宏数(宏库大小)
    n_side   侧向量宽度(应为 5*n_out + CORE_DIMS)
    n_macros 掩码宽度(应等于 n_out)
    feat_dim 视觉特征宽度; None=取ppo真值。**save_episode_npz会按数组
             实际形状覆盖它** — 契约的价值在"宏数/布局代际", 不在像素宽度
             (feat_dim只作诊断, 合成测试用合成宽度不误报)。
    """
    _code_n = code_macro_count(char)
    return {
        "char": str(char),
        "n_out": int(n_out),
        "n_side": int(n_side),
        "n_macros": int(n_macros),
        "feat_dim": int(_ppo_feat_dims() if feat_dim is None else feat_dim),
        # 代码侧宏数: 与n_out不符=本进程代码早于/晚于模型档 → 契约自带
        # 判据, 读者无需猜(旧版靠np.concatenate抛形状错, 报错点远离根因)
        "code_n_macros": (int(_code_n) if _code_n is not None else -1),
    }


def check_model_generation(char, model_n_out):
    """校验"模型档动作维 == 当前代码宏库"。

    返回 None=通过; 否则返回人类可读的原因字符串(**调用方必须据此拒绝启动**)。
    R63(P0-2): 抽成单一实现是有意的 — 它让"learner是否真的校验了代际"
    变成可**行为测试**的对象(而不是靠门禁文本钉: 变异自检证明
    `code_macro_count(char)` 这类子串锚定会被 `... or n_out` 绕过)。
    """
    _cn = code_macro_count(char)
    if _cn is None:
        return ("无法确定代码侧宏数(macros.%s不可导入)" % char)
    if int(model_n_out) != int(_cn):
        return ("模型档宏数%d≠当前代码宏数%d — 代际不符, 需迁移/重训模型, "
                "不要用旧档续训" % (int(model_n_out), int(_cn)))
    return None


# P1-4(从零#5): 逐决策数组(N,)对账 — 写者与读者共用。
# 事故形态: feats/sides 8 行、acts/logps 4 行的文件被 save_episode_npz 接受、
# 被 learner_hub 消费、随后 os.remove —— 无隔离无告警(宽度校验只比列数)。
_PER_DECISION = ("feats", "sides", "acts", "rews", "masks", "bc_targets",
                 "opp_next", "logps")


def check_row_counts(arrays):
    """返回 [(key, rows)] — 与**多数行数**不一致的逐决策数组(空=一致)。

    基准取多数而非"第一个可用数组": 单个数组被截断时它才是异常项
    (若拿 acts 当基准, 截断的 acts 反而会把其余 7 个正常数组报成异常)。
    """
    rows = {}
    for k in _PER_DECISION:
        a = arrays.get(k)
        if a is None or getattr(a, "ndim", 0) < 1:
            continue
        rows[k] = int(a.shape[0])
    if not rows:
        return []
    vals = list(rows.values())
    base = max(set(vals), key=vals.count)
    return [(k, n) for k, n in rows.items() if n != base]


def check_contract(contract, where=""):
    """校验契约块**自洽**(不依赖任何外部产物)。

    这是抓"代码在活进程脚下被改"的关键判据: actor声明的n_out/n_side若与
    **当前代码**算出的宏数不一致, 说明该进程跑的是旧代码 → 其episode必须
    被拒收(而不是靠下游形状错误被发现)。返回问题列表(空=通过)。
    """
    bad = []
    if not isinstance(contract, dict):
        return ["contract缺失或非dict: %r" % (contract,)]
    for k in ("char", "n_out", "n_side", "n_macros", "feat_dim",
              "code_n_macros"):
        if k not in contract:
            bad.append("contract缺键%s" % k)
    if bad:
        return bad
    if contract["n_macros"] != contract["n_out"]:
        bad.append("n_macros(%s)≠n_out(%s) — 掩码宽度与策略宽度不一致"
                   % (contract["n_macros"], contract["n_out"]))
    # 代码侧一致性: episode声明的n_out必须等于当前代码的宏数
    _cn = code_macro_count(contract["char"])
    if _cn is not None:
        if int(contract["n_out"]) != int(_cn):
            bad.append("episode声明n_out=%s≠当前代码宏数=%s(角色%s) — "
                       "写者跑的是旧/新代码, 拒收"
                       % (contract["n_out"], _cn, contract["char"]))
        if int(contract["code_n_macros"]) != int(_cn):
            bad.append("episode内code_n_macros=%s≠当前代码%s — 写者时代"
                       "不符" % (contract["code_n_macros"], _cn))
    # n_side必须与(宏数, CORE_DIMS)自洽 — CORE_DIMS由代码侧提供
    _core = None
    try:
        import feat_builder as _fb
        _core = int(_fb.FeatureBuilder.CORE_DIMS)
    except Exception:
        pass
    if _core is not None:
        _want = 5 * int(contract["n_out"]) + _core
        if int(contract["n_side"]) != _want:
            bad.append("n_side=%s≠5*n_out+CORE_DIMS=%s(代码CORE_DIMS=%s) — "
                       "布局代际不符" % (contract["n_side"], _want, _core))
    if where:
        return ["%s: %s" % (where, b) for b in bad]
    return bad


def episode_meta(char, actor_id, ep, snap_ver, seed, decisions,
                 contract=None):
    """构造episode meta(json str — npz内以0-d str数组存)。

    contract: build_contract()的产物; None=不写契约(仅离线工具用)。
    """
    m = {
        "char": char, "actor": int(actor_id), "ep": int(ep),
        "snap_ver": int(snap_ver), "seed": int(seed),
        "decisions": int(decisions), "ts": time.strftime("%H:%M:%S"),
    }
    if contract is not None:
        m["contract"] = contract
    return json.dumps(m)


def save_episode_npz(ep_dir, char, actor_id, ep_idx, arrays, meta_str):
    """原子写episode npz(tmp+rename, 项目惯例)。arrays须含EP_KEYS除meta。

    R63: 落盘前**写者自检** — 声明的契约必须与数组真实形状一致, 否则
    拒绝落盘(生产事故: 写者自己声明与数据不符时, 下游无法判读)。
    """
    data = dict(arrays)
    try:
        _meta = json.loads(meta_str if isinstance(meta_str, str)
                           else str(meta_str))
    except Exception:
        _meta = {}
    _c = _meta.get("contract")
    if isinstance(_c, dict):
        _sides = data.get("sides")
        _masks = data.get("masks")
        _feats = data.get("feats")
        # feat_dim以**数组实际形状**为准回写(契约只诊断像素宽; 宏数/布局
        # 才是代际判据 — 合成特征宽度不误报, 声明与实际不符仍被下面捕获)
        if _feats is not None and getattr(_feats, "ndim", 0) == 2:
            _c["feat_dim"] = int(_feats.shape[1])
        _bad = []
        if _sides is not None and int(_c.get("n_side", -1)) != int(_sides.shape[1]):
            _bad.append("n_side(%s)≠sides.shape[1](%s)"
                        % (_c.get("n_side"), _sides.shape[1]))
        if _masks is not None and int(_c.get("n_macros", -1)) != int(_masks.shape[1]):
            _bad.append("n_macros(%s)≠masks.shape[1](%s)"
                        % (_c.get("n_macros"), _masks.shape[1]))
        # P1-4(从零#5): 行数对账(原只比宽度 → 半截文件可落盘并被消费)
        _rows = check_row_counts(data)
        if _rows:
            _bad.append("行数不一致: %s" % (
                [(k, n) for k, n in _rows],))
        _cself = check_contract(_c, where="写者自检")
        if _bad or _cself:
            raise EpisodeContractError(
                "拒绝落盘 episode %s ep%s: %s" % (char, ep_idx,
                                                  "; ".join(_bad + _cself)))
        # 覆盖meta里的contract(回写feat_dim后的版本)
        _meta["contract"] = _c
        meta_str = json.dumps(_meta)
    os.makedirs(ep_dir, exist_ok=True)
    fname = "ep_%s_%02d_%05d_%s.npz" % (char, actor_id, ep_idx,
                                        time.strftime("%Y%m%d_%H%M%S"))
    # 注意: np.savez对不以.npz结尾的名字会自动补.npz — tmp名必须以
    # .npz结尾, 否则os.replace找不到落盘文件
    tmp = os.path.join(ep_dir, fname + ".tmp.npz")
    dst = os.path.join(ep_dir, fname)
    data["meta"] = np.array(meta_str)
    _hist = data.get("hist")
    if _MEM_DEC > 0 and _hist is not None:
        if tuple(getattr(_hist, "shape", ())) != (
                int(data["acts"].shape[0]), 8, 3):
            raise EpisodeContractError(
                "hist形状%s≠(N,8,3)" % (getattr(_hist, "shape", None),))
        data["schema"] = np.array(EP_SCHEMA_MEM)
    else:
        data["schema"] = np.array(EP_SCHEMA)
    np.savez(tmp, **data)
    os.replace(tmp, dst)
    return dst


def load_episode_npz(path, expect_contract=None):
    """读episode npz → (arrays dict, meta dict)。

    校验(全部**响亮失败**, 不再进删除路径):
      1. 键齐全; 2. schema==EP_SCHEMA; 3. contract自洽(check_contract);
      4. arrays真实形状 == contract声明; 5. (可选)expect_contract逐项相等。
    R63: 原实现只查键与schema, 尺寸不符要等np.concatenate才爆(报错点远离
    根因)且爆了就走"删文件/隔离"路径 → 数据被当垃圾处理。现在契约不符
    抛EpisodeContractError, 由调用方按"代际不符"处置(隔离但不删,
    且learner退出让监督器重启)。
    """
    d = np.load(path, allow_pickle=True)
    try:
        arrays = {k: d[k] for k in EP_KEYS if k != "meta"}
        _miss = [k for k in EP_KEYS if k not in d.files or
                 (k != "meta" and k not in arrays)]
        if _miss:
            raise EpisodeContractError("episode缺键%s: %s"
                                       % (_miss, os.path.basename(path)))
        _sch = int(d["schema"]) if "schema" in d.files else -1
        if _sch not in (EP_SCHEMA, EP_SCHEMA_MEM):
            raise EpisodeContractError(
                "episode schema v%d∉{%d,%d} — 格式已演化(旧v1无contract块), "
                "该文件由旧代码产出, 需重新采集"
                % (_sch, EP_SCHEMA, EP_SCHEMA_MEM))
        arrays["hist"] = (d["hist"] if "hist" in d.files else None)
        meta = json.loads(str(d["meta"]))
        _c = meta.get("contract")
        if not isinstance(_c, dict):
            raise EpisodeContractError(
                "episode无contract块(schema=%s) — 无法判读尺寸代际: %s"
                % (d["schema"] if "schema" in d.files else "?",
                   os.path.basename(path)))
        _bad = check_contract(_c, where=os.path.basename(path))
        # 声明 vs 实际形状
        # P1-4(从零#5): 行数对账 — 半截 episode 必须**拒收**而不是被消费后删除
        for _k, _n in check_row_counts(arrays):
            _bad.append("%s行数%s≠主行数" % (_k, _n))
        if int(_c["n_side"]) != int(arrays["sides"].shape[1]):
            _bad.append("n_side声明%s≠sides实际%s"
                        % (_c["n_side"], arrays["sides"].shape[1]))
        if int(_c["n_macros"]) != int(arrays["masks"].shape[1]):
            _bad.append("n_macros声明%s≠masks实际%s"
                        % (_c["n_macros"], arrays["masks"].shape[1]))
        if int(_c["feat_dim"]) != int(arrays["feats"].shape[1]):
            _bad.append("feat_dim声明%s≠feats实际%s"
                        % (_c["feat_dim"], arrays["feats"].shape[1]))
        if int(_c["n_out"]) != int(arrays["bc_targets"].max()) + 1 and \
                len(arrays["bc_targets"]) and \
                int(arrays["bc_targets"].max()) >= int(_c["n_out"]):
            _bad.append("bc_targets含≥n_out的宏ID(%s≥%s)"
                        % (arrays["bc_targets"].max(), _c["n_out"]))
        if expect_contract:
            for k, v in expect_contract.items():
                if k in _c and _c[k] != v:
                    _bad.append("契约不符@%s: episode %s=%s ≠ 期望 %s"
                                % (k, k, _c[k], v))
        if _bad:
            raise EpisodeContractError("; ".join(_bad))
    finally:
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
            X_old = d["X"]
            # S-7B(2026-10-14): 列宽演进(11→13加风格pc1/pc2) — 旧行
            # 零填充到新宽(旧行风格未知=0, 语义一致), 不再误判损坏
            if X_old.shape[1] != X_new.shape[1]:
                if X_old.shape[1] < X_new.shape[1]:
                    X_old = np.concatenate(
                        [X_old, np.zeros((len(X_old),
                                          X_new.shape[1] - X_old.shape[1]),
                                         dtype=X_old.dtype)], axis=1)
                else:
                    raise ValueError(
                        "distill档宽%d>新行宽%d — 未来档混入?"
                        % (X_old.shape[1], X_new.shape[1]))
            X = np.concatenate([X_old, X_new])
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

def fleet_snap_dir(fleet_dir, char, suffix):
    """快照目录(actor与learner**必须**用同一份实现 — 目录不一致=actor
    读不到learner发布的快照, 表现为actor永远跑启动权重)。

    R63(P1-5): 原 learner 锁按 suffix 隔离而 snap_dir/EP_DIR 不隔离 →
    `--suffix ""`(迁移)与 `--suffix "_fleet"` 可同时对同一角色运行, 共用
    一个version计数器与一个episode队列(互相删除对方数据)。默认 `_fleet`
    保持历史路径(现网零变化), 其余suffix走独立子目录。
    """
    if suffix == '_fleet':
        return os.path.join(fleet_dir, 'snap_%s' % char)
    _tag = (suffix or 'main').lstrip('_')
    return os.path.join(fleet_dir, 'snap_%s_%s' % (char, _tag))


def fleet_ep_dir(fleet_dir, suffix):
    """episode队列目录(理由同fleet_snap_dir)。"""
    if suffix == '_fleet':
        return os.path.join(fleet_dir, 'episodes')
    _tag = (suffix or 'main').lstrip('_')
    return os.path.join(fleet_dir, 'episodes_%s' % _tag)


def write_version(snap_dir, ver):
    """原子写版本号(tmp+rename)。learner发布快照后调用。"""
    tmp = os.path.join(snap_dir, "version.tmp")
    with open(tmp, "w") as f:
        f.write(str(int(ver)))
    os.replace(tmp, os.path.join(snap_dir, "version"))


# P2(从零#5): 版本文件**损坏**必须响亮 — 原静默返回 0, 而 actor 的门是
# `if ver > 0`, 于是"永久用旧权重且无日志"(看起来健康)。首错打一次即止
# (每局都喊会刷屏; 同一文件损坏状态不重复)。
_VERSION_WARNED = set()


def read_version(snap_dir):
    """读当前版本号。**缺档=0(未发布, 正常)**; **损坏=0 但响亮告警一次**。

    actor 每局边界调用(文件 stat 廉价); 语义保持"0=无可用版本"不变。
    """
    vfile = os.path.join(snap_dir, "version")
    if not os.path.exists(vfile):
        return 0      # 未发布: 正常路径, 不告警
    try:
        with open(vfile) as f:
            _txt = f.read().strip()
        return int(_txt)
    except (ValueError, OSError) as _e:
        _key = (str(vfile), type(_e).__name__)
        if _key not in _VERSION_WARNED:
            _VERSION_WARNED.add(_key)
            print('[episode_core] !! 快照版本文件损坏(%s): %r — '
                  '回退版本0 = actor 会**永久用旧权重**且无其它提示; '
                  '请查该目录写入方(此后再出现不重复告警)'
                  % (vfile, _e), flush=True)
        return 0


def archive_episode(ep_path, keep_dir, keep_n):
    """消费后归档 episode(TH123_EP_KEEP): move 到 keep_dir 并保留最近 keep_n; 失败回退删除."""
    import glob
    import shutil
    import time
    try:
        os.makedirs(keep_dir, exist_ok=True)
        dst = os.path.join(keep_dir, os.path.basename(ep_path))
        try:
            os.replace(ep_path, dst)
        except OSError:
            shutil.copy2(ep_path, dst)
            try:
                os.remove(ep_path)
            except OSError:
                pass
        files = sorted(glob.glob(os.path.join(keep_dir, 'ep_*.npz')),
                       key=os.path.getmtime)
        for old in files[:-int(keep_n)]:
            try:
                os.remove(old)
            except OSError:
                pass
        return True
    except Exception:
        try:
            os.remove(ep_path)
        except OSError:
            pass
        return False
