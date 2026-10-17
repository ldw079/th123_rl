# -*- coding: utf-8 -*-
"""权威常量层 —— 本项目所有领域常量都必须在此登记，并注明来源。

原则（与调试助手系统提示词一致）：
  * 任何内存偏移 / API / 数值，若不能在仓库内找到来源，一律标注 TO_VERIFY，禁止编造。
  * 常量只在这里定义一次，其它模块 import，避免"手抄魔数"漂移（前序项目第六轮审计 §7g 的教训）。

来源清单：
  [W] C:\\Users\\96120\\Desktop\\workplace\\th123_rl\\  以及
      D:\\temp\\build\\SokuAI-master\\Training\\AITrainerScriptPYTorch\\Soku\\weathers.py
  [S] D:\\temp\\build\\SokuAI-master\\SokuLib\\src\\*.hpp
  [M] C:\\Users\\96120\\Desktop\\workplace\\th123_rl\\macros.py
  [D] C:\\Users\\96120\\Desktop\\workplace\\th123_rl\\distill.py
"""
from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------
# 帧率
# --------------------------------------------------------------------------
# 前序项目 threat.py / feat_builder.py 以 62 作为"帧→秒"换算常数（GAME_FPS）。
# 非想天则官方为 60fps；62 是该项目实测口径。
# TO_VERIFY: 60 vs 62 必须以一次锁步帧计数实验裁定，否则所有"秒"级阈值会偏 3%。
GAME_FPS: Final[float] = 62.0
FRAME_BUDGET_MS_60FPS: Final[float] = 1000.0 / 60.0  # 16.667ms 实时预算

# --------------------------------------------------------------------------
# 天气（来源 [W] weathers.py，0..21 共 22 项）
# --------------------------------------------------------------------------
WEATHER_NAMES: Final[tuple[str, ...]] = (
    "SUNNY",          # 0
    "DRIZZLE",        # 1
    "CLOUDY",         # 2
    "BLUE_SKY",       # 3
    "HAIL",           # 4
    "SPRING_HAZE",    # 5
    "HEAVY_FOG",      # 6
    "SNOW",           # 7
    "SUN_SHOWER",     # 8
    "SPRINKLE",       # 9
    "TEMPEST",        # 10
    "MOUNTAIN_VAPOR", # 11  晴岚
    "RIVER_MIST",     # 12
    "TYPHOON",        # 13
    "CALM",           # 14
    "DIAMOND_DUST",   # 15
    "DUST_STORM",     # 16
    "SCORCHING_SUN",  # 17
    "MONSOON",        # 18
    "AURORA",         # 19  极光
    "TWILIGHT",       # 20
    "CLEAR",          # 21  无天气哨兵
)
N_WEATHER: Final[int] = len(WEATHER_NAMES)  # 22

WEATHER_MOUNTAIN_VAPOR: Final[int] = 11  # 晴岚：双方手牌不可识别（feat_builder.py:24）
WEATHER_AURORA: Final[int] = 19          # 极光：实际天气效果随机且隐藏（feat_builder.py:25）
WEATHER_CLEAR: Final[int] = 21           # 无天气

# --------------------------------------------------------------------------
# 角色（来源 [S] SokuLib/src/Character.hpp，0..36）
# --------------------------------------------------------------------------
CHARACTER_NAMES: Final[tuple[str, ...]] = (
    "REIMU", "MARISA", "SAKUYA", "ALICE", "PATCHOULI", "YOUMU", "REMILIA", "YUYUKO",
    "YUKARI", "SUIKA", "REISEN", "AYA", "KOMACHI", "IKU", "TENSHI", "SANAE",
    "CIRNO", "MEILING", "UTSUHO", "SUWAKO", "RANDOM", "NAMAZU",
    # --- Soku2 追加角色 ---
    "MOMIJI", "CLOWNPIECE", "FLANDRE", "ORIN", "YUUKA", "KAGUYA", "MOKOU", "MIMA",
    "SHOU", "MURASA", "SEKIBANKI", "SATORI", "RAN", "TEWI", "MAMIZOU",
)
N_CHARACTER: Final[int] = len(CHARACTER_NAMES)  # 37
CHARACTER_RANDOM: Final[int] = 20  # 非法/随机哨兵，训练时应排除

# --------------------------------------------------------------------------
# 宏动作空间（来源 [M] macros.py + 产物实测）
# --------------------------------------------------------------------------
# 证据：th123_models/model_ppo_{reimu,marisa,suika}.npz 的 W2 输出维 = 55 / 61 / 62；
#       distill_data_*.npz 的 Y.max() = 54 / 60 / 61（0-based）；
#       第六轮审计 §6「宏数 55/61/62 与宪法一致」。
MACRO_COUNT: Final[dict[str, int]] = {"reimu": 55, "marisa": 61, "suika": 62}
DEFAULT_CHARACTER: Final[str] = "reimu"

# 宏脚本步类型（来源 macros.py:11-99）
#   tuple(按键名...)  -> 普通按键步
#   "confirm" / "cconfirm" / "sc:ID" -> 控制步（门 / 符卡选择）
MACRO_STEP_GATE_HIT: Final[str] = "confirm"     # 命中才继续
MACRO_STEP_GATE_CONTACT: Final[str] = "cconfirm"  # 命中或被防才继续
MACRO_STEP_SC_PREFIX: Final[str] = "sc:"

# 方向+攻击键同帧会被姿态转换吞掉：方向必须预置 ≥5 控制帧（macros.py:104-126 hitlab 标定）
MACRO_PRESTEP_FRAMES: Final[int] = 6
MACRO_PRESTEP_THRESHOLD: Final[int] = 5

# --------------------------------------------------------------------------
# 决策级观测：11 维（来源 [D] distill.py:23 FEAT_NAMES，顺序即 X 的列序）
# --------------------------------------------------------------------------
# 注意：该 11 维是"宏选择特征"，与 feat_builder.py 的 260 维核心侧特征不是同一套。
#       260 维只在训练进程内使用，未落盘；因此可训练的真实数据只有这份 11 维。
FEATURE_NAMES: Final[tuple[str, ...]] = (
    "adx",      # 0 距离（像素绝对值）          有效行 >= 0；无效行 = -1
    "spirit",   # 1 灵力
    "close",    # 2 贴身标志
    "prev_macro",  # 3 上一拍宏 ID
    "game_frame",  # 4 游戏帧
    "dy",       # 5 高度差
    "opp_air",  # 6 对手空中
    "bullet_near",  # 7 弹幕接近
    "i_am_left",    # 8 我在左侧
    "tti",      # 9 威胁命中时间（帧）
    "opp_corner",   # 10 对手在版边
)
N_FEATURES: Final[int] = len(FEATURE_NAMES)  # 11

# 官方有效性掩码（distill.py:36  use = X[:, 0] >= 0）
FEATURE_INVALID_SENTINEL: Final[float] = -1.0

# 归一化尺度。来源与置信度：
#   adx  : feat_builder.py:183 clip(dx/1200)；实测 X[:,0].max()≈1200 -> 已归一
#   spirit: feat_builder.py:182 left["spirit"]/2000 -> 已归一（注意与非想天则常识的 1000 上限不同，TO_VERIFY）
#   dy   : feat_builder.py:184 clip(dy/600)      -> 已归一
#   game_frame: 非归一，用 log1p 压缩后标准化（帧数无上界）
# 结论：11 维数据里 adx/spirit/dy 已归一；其余为 0/1 标志或 ID。
FEATURE_SCALES: Final[dict[str, float]] = {
    "adx": 1200.0,
    "spirit": 2000.0,
    "dy": 600.0,
    "game_frame": 1.0,
    "tti": 1.0,
}

# 第 3 列的真相（重要，勿被文档误导）：
#   train_tm.py:838-840 —— 生产端把 mid 写进第 3 列，随即取 X[:,3] 作为标签 Y，
#   再把该列原地清成 -1.0（注释："与旧格式一致: X为态势,Y为动作"）。
#   所以第 3 列是【标签载体】而非特征；磁盘上恒为 -1 是设计结果，不是 bug。
#   但 distill.py:23 "上宏ID"、standard_tree.py:26 "macro_id"、train_tm.py:499
#   三处文档都把它描述为特征 —— 文档与代码相反，属数据契约缺陷。
LABEL_CARRIER_COLUMN: Final[int] = 3

# tti 的"无威胁"哨兵：三个角色文件 tti.max() 均恰为 9.9（唯一上界），
# 说明生产端做了截断。>= 该值视为"当前无威胁弹幕"。
TTI_NO_THREAT: Final[float] = 9.9

# 合法性规则：只使用 11 维里真实存在的判据，且用【宏名语义子串】匹配，
# 以便同一份规则同时适配灵梦/魔理沙/萃香三套宏库（不硬编码各库的 ID）。
# 形式: (宏名子串, 列号, 要求取值)
LEGALITY_RULES: Final[dict[str, list]] = {
    "require": [
        ("版边", 10, 1.0),   # 版边连A 需要 opp_corner=1
        ("空连", 6, 1.0),    # 空连A   需要 opp_air=1
    ],
    "note": "符卡类/空中自身状态/结界类无法判定 —— 11 维缺少 cardGauge、手牌、自身 airBorne",
}

# --------------------------------------------------------------------------
# 部署/性能目标
# --------------------------------------------------------------------------
LATENCY_BUDGET_MS: Final[float] = 16.667  # 60fps 单帧预算
TARGET_P95_MS: Final[float] = 5.0         # 本项目自设：P95 必须 < 预算的 30%

__all__ = [
    "GAME_FPS", "FRAME_BUDGET_MS_60FPS",
    "WEATHER_NAMES", "N_WEATHER", "WEATHER_MOUNTAIN_VAPOR", "WEATHER_AURORA", "WEATHER_CLEAR",
    "CHARACTER_NAMES", "N_CHARACTER", "CHARACTER_RANDOM",
    "MACRO_COUNT", "DEFAULT_CHARACTER", "MACRO_STEP_GATE_HIT", "MACRO_STEP_GATE_CONTACT",
    "MACRO_STEP_SC_PREFIX", "MACRO_PRESTEP_FRAMES", "MACRO_PRESTEP_THRESHOLD",
    "FEATURE_NAMES", "N_FEATURES", "FEATURE_INVALID_SENTINEL", "FEATURE_SCALES",
    "LABEL_CARRIER_COLUMN", "TTI_NO_THREAT", "LEGALITY_RULES",
    "LATENCY_BUDGET_MS", "TARGET_P95_MS",
]
