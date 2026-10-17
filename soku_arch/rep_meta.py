# -*- coding: utf-8 -*-
"""replay 文件名解析：两套命名规范 + 中文昵称 → 角色枚举 + 比分。

实测两种命名（同一批归档里混用）：

  A（英文代号，16,021 条）:
     会话目录: (yuyuko)_好想吃大嘴安格斯.(youmu)251203_2026-01-03-12-26-48
     文件名:   2025-12-03_12-05-46_神奇屁股.(yuyuko)_好想吃大嘴安格斯.(youmu).rep
  B（中文昵称，7,092 条）—— **带胜负**:
     会话目录: 123(铃仙)_zoe(黑白)_2025-07-06-11-50-14
     文件名:   25-07-03_21-12-23_123__(铃仙)_zoe(魔理沙)_(0︰2_负).rep

中文昵称 → 角色的映射**不是猜的**：同一目录下的 chm 攻略文件名本身就是权威对照表
（`01-伊吹萃香-西瓜.chm` / `05-魂魄妖梦-YM.chm` / `09-雾雨魔理沙-黑白.chm` /
`10-博丽灵梦-红白.chm` / `14-灵乌路空-高达.chm` / `15-泄矢诹访子-青蛙.chm` /
`16-铃仙 优昙华院 因番-兔子.chm` / `19-永江衣玖-19.chm` …）。
本模块把其中可证实的条目登记为 `source="chm"`，其余常用昵称登记为 `source="inferred"`，
未识别的返回 None 并由调用方统计比例 —— **不允许把猜出来的映射当已知**。

**比分/胜负的语义未证实**：`(0︰2_负)` 与 `(1︰2_胜)` 无法用"我方:对方"一致解释
（前者像"我 0 对方 2 负"，后者 1:2 却标"胜"）。因此本模块只**抽取原文**，
不把它当已验证标签；必须用回放内容（局终包/头部比分）交叉校验后再用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .constants import CHARACTER_NAMES

# --------------------------------------------------------------------------
# 中文昵称 → 角色（source="chm" 的条目由 chm 文件名直接证实）
# --------------------------------------------------------------------------
NICKNAME_TABLE: dict[str, tuple[str, str]] = {
    # chm 文件名证实
    "伊吹萃香": ("suika", "chm"), "西瓜": ("suika", "chm"),
    "八云紫": ("yukari", "chm"),
    "西行寺幽幽子": ("yuyuko", "chm"), "幽幽子": ("yuyuko", "chm"), "UU": ("yuyuko", "chm"),
    "蕾米丽亚": ("remilia", "chm"), "蕾米莉亚": ("remilia", "chm"), "蝙蝠": ("remilia", "chm"),
    "魂魄妖梦": ("youmu", "chm"), "YM": ("youmu", "chm"),
    "帕秋莉": ("patchouli", "chm"), "图书": ("patchouli", "chm"),
    "爱丽丝": ("alice", "chm"), "小爱": ("alice", "chm"),
    "十六夜咲夜": ("sakuya", "chm"), "16": ("sakuya", "chm"),
    "雾雨魔理沙": ("marisa", "chm"), "黑白": ("marisa", "chm"),
    "博丽灵梦": ("reimu", "chm"), "红白": ("reimu", "chm"),
    "东风谷早苗": ("sanae", "chm"), "早苗": ("sanae", "chm"),
    "琪露诺": ("cirno", "chm"), "⑨": ("cirno", "chm"),
    "红美铃": ("meiling", "chm"), "中国": ("meiling", "chm"),
    "灵乌路空": ("utsuho", "chm"), "高达": ("utsuho", "chm"),
    "泄矢诹访子": ("suwako", "chm"), "青蛙": ("suwako", "chm"),
    "铃仙": ("reisen", "chm"), "兔子": ("reisen", "chm"),
    "射命丸文": ("aya", "chm"), "文": ("aya", "chm"),
    "小野冢小町": ("komachi", "chm"), "小町": ("komachi", "chm"),
    "永江衣玖": ("iku", "chm"), "19": ("iku", "chm"),
    "比那名居天子": ("tenshi", "chm"), "天子": ("tenshi", "chm"),
    # 常用昵称（inferred：语料中高频出现，但不在 chm 文件名里直接证实）
    "幽幽": ("yuyuko", "inferred"),
    "蕾咪": ("remilia", "inferred"), "蕾米": ("remilia", "inferred"),
    "咲夜": ("sakuya", "inferred"),
    "魔理沙": ("marisa", "inferred"),
    "灵梦": ("reimu", "inferred"), "红白灵梦": ("reimu", "inferred"),
    "妖梦": ("youmu", "inferred"),
    "萃香": ("suika", "inferred"),
    "芙兰": ("flandre", "inferred"), "芙兰朵露": ("flandre", "inferred"),
    "觉": ("satori", "inferred"), "古明地觉": ("satori", "inferred"),
    "阿燐": ("orin", "inferred"), "燐": ("orin", "inferred"),
    "妹红": ("mokou", "inferred"), "辉夜": ("kaguya", "inferred"),
    "幽香": ("yuuka", "inferred"), "风见幽香": ("yuuka", "inferred"),
    "蓝": ("ran", "inferred"), "八云蓝": ("ran", "inferred"),
    "帝": ("tewi", "inferred"), "因幡帝": ("tewi", "inferred"),
    "魅魔": ("mima", "inferred"), "星": ("shou", "inferred"),
    "村纱": ("murasa", "inferred"), "赤蛮奇": ("sekibanki", "inferred"),
    "麻美藏": ("mamizou", "inferred"), "椛": ("momiji", "inferred"),
    "小丑": ("clownpiece", "inferred"), "克劳恩皮丝": ("clownpiece", "inferred"),
    "娜兹琳": ("nazrin", "inferred"), "老鼠": ("nazrin", "inferred"),
    "空": ("utsuho", "inferred"), "诹访子": ("suwako", "inferred"),
    "帕琪": ("patchouli", "inferred"),
}

# 英文代号（规范 A 用的小写名）→ 角色枚举
EN_TABLE: dict[str, str] = {n.lower(): n.lower() for n in CHARACTER_NAMES}
EN_TABLE.update({"udonge": "reisen", "chirno": "cirno", "meirin": "meiling"})

RE_A_FILE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>[\d\-]+)_(?P<opp_name>.+?)\."
    r"\((?P<opp_char>[a-z_]+)\)_(?P<my_name>.+?)\.\((?P<my_char>[a-z_]+)\)$")
RE_B_FILE = re.compile(
    r"^(?P<yy>\d{2})-(?P<mm>\d{2})-(?P<dd>\d{2})_(?P<time>[\d\-]+)_"
    r"(?P<opp_name>.*?)\((?P<opp_char>[^()]+)\)(?P<my_name>[^()]*?)\((?P<my_char>[^()]+)\)"
    r"(?:_?\((?P<score>[^()]*)\))?$")
RE_SCORE = re.compile(r"(?P<left>\d+)\s*[：:︰]\s*(?P<right>\d+)(?:_(?P<result>[胜负无平]))?")
RE_A_DIR = re.compile(r"^\((?P<opp_char>[a-z_]+)\)_(?P<opp_name>.+?)\."
                      r"\((?P<my_char>[a-z_]+)\)(?P<sid>\d*)_(?P<stamp>[\d\-]+)$")
RE_B_DIR = re.compile(r"^(?P<opp_name>.*?)\((?P<opp_char>[^()]+)\)"
                      r"(?P<my_name>[^()]*?)\((?P<my_char>[^()]+)\)_?(?P<stamp>[\d\-]+)$")


def resolve_char(token: str | None) -> tuple[str | None, str | None]:
    """角色 token（中文昵称或英文代号）→ (角色枚举小写名, 来源)。"""
    if not token:
        return None, None
    t = token.strip()
    if not t:
        return None, None
    if t in NICKNAME_TABLE:
        return NICKNAME_TABLE[t]
    low = t.lower()
    if low in EN_TABLE:
        return EN_TABLE[low], "enum"
    # 昵称里带括号/后缀时做一次包含匹配（例如"幽幽子(妖梦)"这类混写）
    for k, (v, src) in NICKNAME_TABLE.items():
        if k and k in t:
            return v, src + "+substr"
    return None, None


@dataclass
class RepMeta:
    pattern: str | None = None
    date: str | None = None
    time: str | None = None
    opp_name: str | None = None
    my_name: str | None = None
    my_char: str | None = None
    my_char_source: str | None = None
    opp_char: str | None = None
    opp_char_source: str | None = None
    # rep_stack缺口2(2026-10-13实证, n=18 oracle真值交叉验证):
    # score = 左侧得分:右侧得分(P1:P2), 18/18=100%;
    # 胜/负 = **存档者视角**(同一比分两标签并存=不同存档者) —
    # 不可当左右胜负标签使用, 仅原文保留。
    score_raw: str | None = None
    score_left: int | None = None
    score_right: int | None = None
    result_raw: str | None = None


def parse_rep_name(stem: str, parent_dir: str = "") -> RepMeta:
    """解析文件名（必要时回退到父目录名）。"""
    m = RE_A_FILE.match(stem)
    if m:
        g = m.groupdict()
        my, mys = resolve_char(g["my_char"])
        op, ops = resolve_char(g["opp_char"])
        return RepMeta("A", g["date"], g["time"], g["opp_name"], g["my_name"],
                       my, mys, op, ops)
    m = RE_B_FILE.match(stem)
    if m:
        g = m.groupdict()
        my, mys = resolve_char(g["my_char"])
        op, ops = resolve_char(g["opp_char"])
        date = f"20{g['yy']}-{g['mm']}-{g['dd']}"
        meta = RepMeta("B", date, g["time"], g["opp_name"], (g["my_name"] or "").strip("_ "),
                       my, mys, op, ops)
        sc = RE_SCORE.search(g.get("score") or "")
        if sc:
            meta.score_raw = g["score"]
            meta.score_left = int(sc.group("left"))
            meta.score_right = int(sc.group("right"))
            meta.result_raw = sc.group("result")
        return meta
    # 回退：用父目录名解析对阵（文件名叫法异常时仍能拿到角色）
    for rx, pat in ((RE_A_DIR, "A_dir"), (RE_B_DIR, "B_dir")):
        m = rx.match(parent_dir)
        if m:
            g = m.groupdict()
            my, mys = resolve_char(g["my_char"])
            op, ops = resolve_char(g["opp_char"])
            date = None
            if pat == "B_dir":
                pass
            return RepMeta(pat, date, None, g["opp_name"], g.get("my_name"),
                           my, mys, op, ops)
    return RepMeta()


__all__ = ["NICKNAME_TABLE", "EN_TABLE", "RepMeta", "parse_rep_name", "resolve_char"]
