# -*- coding: utf-8 -*-
"""角色注册表: ID/名称/机体属性(阈值角色化的数据源) + 分文件模型管理。

角色ID来自游戏内存(SWRS_ADDR_LCHARID=0x899D10/RCHARID=0x899D30, 神AI地址表)。
机体属性含义(相对灵梦=1.0标定, 供pmask距离带缩放与对手属性编码):
  reach   打击圈系数(贴身/近距离带按此缩放)
  dash    冲刺速度系数(逼近速度预期)
  flight  飞行类型: 0地面 1灵梦式飞行 2完全飞行(天子/紫等)
  zoner   弹幕倾路(0近战型 1混合 2弹幕型) — 对手编码用
"""

CHAR_NAMES = {
    0: "灵梦", 1: "魔理沙", 2: "咲夜", 3: "爱丽丝", 4: "帕秋莉",
    5: "妖梦", 6: "蕾米", 7: "幽幽子", 8: "紫", 9: "萃香",
    10: "铃仙", 11: "文", 12: "小町", 13: "衣玖", 14: "天子",
    15: "早苗", 16: "琪露诺", 17: "美铃", 18: "灵乌路", 19: "诹访子",
}

# 机体属性表(现阶段只标定灵梦=基准; 新角色开训时按攻略标定补充)
CHAR_STATS = {
    0: {"name": "灵梦", "reach": 1.0, "dash": 1.0, "flight": 1, "zoner": 1},
    1: {"name": "魔理沙", "reach": 1.05, "dash": 1.05, "flight": 0, "zoner": 2},
    9: {"name": "萃香", "reach": 1.2, "dash": 0.9, "flight": 0, "zoner": 0},
}

DEFAULT_STATS = {"reach": 1.0, "dash": 1.0, "flight": 0, "zoner": 1}


def stats_of(char_id):
    return CHAR_STATS.get(char_id, DEFAULT_STATS)


def model_paths(char_id, base_dir):
    """分文件模型路径: model_ppo_<角色名>.npz。"""
    name = CHAR_NAMES.get(char_id, "c%d" % char_id)
    import os
    return (os.path.join(base_dir, "model_ppo_%s.npz" % name),
            os.path.join(base_dir, "model_ppo_%s_v.npz" % name))
