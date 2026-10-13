# -*- coding: utf-8 -*-
"""路径集中化(可迁移化Phase1) — 全部路径的单一事实源。

三层回落: config.json > 环境变量 > 本机默认(向后兼容, 不影响现有使用)。

收件人: 把 config.json 放在本文件同目录, 填入自己的游戏路径即可。
本机: 不需要 config.json — 默认值即本机路径, 一切照旧。
"""
from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    """config.json > 环境变量 > 默认值."""
    p = os.environ.get(
        'TH123RL_CONFIG',
        os.path.join(_HERE, 'config.json'))
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding='utf8'))
        except (OSError, ValueError):
            pass
    return {}


_cfg = _load()

# 原版整合包(人测用, 用户日常机)
GAME_DIR = (_cfg.get('game_dir')
            or os.environ.get('TH123_GAME_DIR')
            or r'D:\touhou\hisoutensoku2026-06-15\th123')

# 训练游戏副本(舰队训练用)
TRAIN_GAME_DIR = (_cfg.get('train_game_dir')
                  or os.environ.get('TH123_TRAIN_GAME_DIR')
                  or r'D:\touhou\hisoutensoku2026-06-15\th123_train')

# 模型存储
STORE_DIR = (_cfg.get('store_dir')
             or os.environ.get('TH123_STORE')
             or r'D:\temp\th123_models')

# 原版exe MD5(版本兼容性守卫)
EXE_MD5 = (_cfg.get('exe_md5')
           or 'DF35D1FBC7B583317ADABE8CD9F53B2E')

# 会话数据目录(kit模式下用本地, 本机模式用原路径)
SESSION_DIR = (_cfg.get('session_dir')
               or os.path.join(_HERE, 'tools', 'human_match_sessions'))

# rep归档目录
REP_DIR = (_cfg.get('rep_dir')
           or os.path.join(STORE_DIR, 'human_reps'))
