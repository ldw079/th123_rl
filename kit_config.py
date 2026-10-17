# -*- coding: utf-8 -*-
"""路径集中化(可迁移化Phase1) — 全部路径的单一事实源。

三层回落: config.json > 环境变量 > 本机默认(仅开发机)。

收件人: 运行kit根目录setup.bat生成config.json即可, kit模式下
未配置直接明确报错(绝不回落开发机路径 — 那会在收件机上变幽灵路径)。
本机: 不需要 config.json — 默认值即本机路径, 一切照旧。
"""
from __future__ import annotations

import json
import os
import time

_HERE = os.path.dirname(os.path.abspath(__file__))

# kit判定: kit_config同级存在带npz的models/ → 采集包内(收件机)
# 开发机kit_config在仓库根(无models同级)
_kit_models = os.path.join(_HERE, 'models')
IS_KIT = os.path.isdir(_kit_models) and \
    any(f.endswith('.npz') for f in os.listdir(_kit_models))


# 仓库根 — 由本文件位置派生, 是"仓库内路径"的唯一来源。
# P0-2(从零#5): 全库曾用"用户家目录宏 + Desktop/workplace/th123_rl"字面量
# (PR-5 历史重写引入), 包 expandvars 只在本机成立 — 访客克隆到别处仍失败。
# 纪律: 仓库内路径一律 repo_path(...); expand() 只给真正的用户家目录输入档。
REPO_ROOT = _HERE


def repo_path(*parts):
    """仓库根下的绝对路径(跨机器可复现)。

    消费纪律: 仓库内路径**不要**再手写用户家目录宏; 需要绝对路径时用它,
    或按同一口径 `dirname(abspath(__file__))` 就地派生(单文件工具首选,
    免 import 耦合)。真正属于"用户家目录输入档"的件才用 expanduser。
    """
    return os.path.join(REPO_ROOT, *parts)


def live_model_path(char, store=None):
    """评估/部署用的**活档**路径: 优先 fleet 生产档(_fleet), 回落单机档。

    P1-1(从零#5): 评估工具原一律读 model_ppo_<char>.npz — 该档 mtime 停在
    10-15, 而活 fleet 写 model_ppo_<char>_fleet.npz → 报告静默过期
    (eval_matrix_quick 于 10-17 被重写, 内容仍是旧档)。
    """
    d = store or STORE_DIR
    p = os.path.join(d, 'model_ppo_%s_fleet.npz' % char)
    return p if os.path.exists(p) else os.path.join(
        d, 'model_ppo_%s.npz' % char)


def model_meta(path):
    """读模型档内嵌 meta(温度/宏数/更新数) — 报告披露口径用。

    P1-2(从零#5): 20 角色矩阵里 17 个 league 种子是**同一份权重**且
    temp=2.0, 三主模型 temp=0.5 → 温度/宏库差异会被读成"角色强度"。
    披露口径: 报告带上每个模型的 temp, 跨模型比较前必须先看这列。
    """
    try:
        with np_load(path) as _d:
            if 'meta' not in getattr(_d, 'files', ()):
                return {}
            _m = _d['meta']
            # ppo.save 的 meta 是**数值数组**(顺序见 ppo.py:478):
            # [temp, beta, bcw, updates, rstd, adaptive_lr_scale]
            if getattr(_m, 'ndim', 0) == 1 and len(_m) >= 4:
                return {'temp': float(_m[0]), 'beta': float(_m[1]),
                        'bcw': float(_m[2]), 'updates': int(_m[3]),
                        'rstd': float(_m[4]) if len(_m) > 4 else None,
                        'adaptive_lr_scale': (float(_m[5])
                                              if len(_m) > 5 else None)}
            import json as _j
            return _j.loads(str(_m))     # 兼容 JSON 形态(gpu 档等)
    except (OSError, ValueError, TypeError):
        pass
    return {}


def np_load(path):
    """延迟 import numpy(本模块被 kit/setup 等轻量路径复用)。"""
    import numpy as _np
    return _np.load(path, allow_pickle=True)


def model_stamp(path):
    """报告用模型版本戳 — 度量纪律: 无版本戳的报告不可比/不可引用。"""
    base = os.path.basename(path)
    try:
        st = os.stat(path)
        return {'path': base,
                'mtime': time.strftime('%Y-%m-%d %H:%M:%S',
                                       time.localtime(st.st_mtime)),
                'mtime_ts': int(st.st_mtime),
                'bytes': st.st_size}
    except OSError:
        return {'path': base, 'missing': True}


def _load():
    """config.json(两个候选位置) > 无。

    解析失败必须炸出来 — 静默吞掉会回落到开发机默认路径,
    在收件机上产生难以理解的幽灵路径报错(2026-10-13事故)。
    """
    cands = [
        os.environ.get('TH123RL_CONFIG'),
        os.path.join(_HERE, 'config.json'),                   # 开发机: 仓库根
        os.path.join(os.path.dirname(_HERE), 'config.json'),  # kit: 包根(setup_helper写这里)
    ]
    for p in cands:
        if p and os.path.exists(p):
            try:
                d = json.load(open(p, encoding='utf8'))
            except (OSError, ValueError) as e:
                raise RuntimeError(
                    '[kit_config] %s 解析失败: %s — 请重新运行setup.bat' % (p, e))
            if isinstance(d, dict):
                return d
    return {}


_cfg = _load()


def _resolve(name, cfg_key, env_key, dev_default, required_in_kit):
    v = _cfg.get(cfg_key) or os.environ.get(env_key)
    if v:
        return v
    if IS_KIT and required_in_kit:
        raise RuntimeError(
            '[kit_config] %s未配置 — 请先运行kit根目录的setup.bat'
            '(填写你的游戏路径, 生成config.json)' % name)
    return dev_default


# 原版整合包(人测用, 用户日常机)
GAME_DIR = _resolve('game_dir', 'game_dir', 'TH123_GAME_DIR',
                    r'D:\touhou\hisoutensoku2026-06-15\th123',
                    required_in_kit=True)

# 训练游戏副本(舰队训练用; kit采集用不到, 回落到GAME_DIR即可)
TRAIN_GAME_DIR = _resolve('train_game_dir', 'train_game_dir',
                          'TH123_TRAIN_GAME_DIR',
                          r'D:\touhou\hisoutensoku2026-06-15\th123_train',
                          required_in_kit=False)
if IS_KIT and TRAIN_GAME_DIR == \
        r'D:\touhou\hisoutensoku2026-06-15\th123_train':
    TRAIN_GAME_DIR = GAME_DIR   # kit内不残留开发机路径

# 模型存储 — 四层回落(K2便携化):
# config.json store_dir > TH123_STORE环境变量 > 包内models/
# (kit_config同级, 存在即用) > 本机默认D:\temp\th123_models
if _cfg.get('store_dir'):
    STORE_DIR = _cfg['store_dir']
elif os.environ.get('TH123_STORE'):
    STORE_DIR = os.environ.get('TH123_STORE')
elif IS_KIT:
    STORE_DIR = _kit_models     # 采集包内模型(收件机路径)
else:
    STORE_DIR = r'D:\temp\th123_models'   # 开发机默认

# 原版exe MD5(版本兼容性守卫; setup时写入收件机自己的exe哈希)
EXE_MD5 = (_cfg.get('exe_md5')
           or 'DF35D1FBC7B583317ADABE8CD9F53B2E')

# 会话数据目录(kit模式下用本地, 本机模式用原路径)
SESSION_DIR = (_cfg.get('session_dir')
               or os.path.join(_HERE, 'tools', 'human_match_sessions'))

# rep归档目录(收件机=包内models/human_reps, 开发机=D盘默认)
REP_DIR = (_cfg.get('rep_dir')
           or os.path.join(STORE_DIR, 'human_reps'))
