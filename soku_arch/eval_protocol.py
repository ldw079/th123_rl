# -*- coding: utf-8 -*-
"""对战评估协议：离线可跑的部分 + 在线（需真机）的接口声明。

原则：**没有真机就不报胜率。** 本机没有可用的游戏+mod 通道，因此：
  * offline 评估：在留出集上算指标套件（可真跑，本节实测产物）
  * brk      分解：按天气 / 版边 / 弹幕接近 / 距离带 切片看行为，定位"哪类局面学不会"
  * online   评估：只声明协议与日志 schema，`NullAdapter` 会**明确报错**而不是编造结果

在线协议（AI vs 规则AI / AI vs 旧模型 / AI vs 人类）需要的日志字段列在 FIELD_SPEC：
每局一行，逐决策一拍一行，便于事后做胜率与延迟的联合分析。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from . import metrics

# --------------------------------------------------------------------------
# 离线评估
# --------------------------------------------------------------------------
# 11 维里可用于切片分析的列（见 constants.FEATURE_NAMES）
SLICE_AXES: dict[str, tuple[int, tuple[float, ...]]] = {
    "天气(timer低=刚变天)": (4, (0, 5, 15)),          # game_frame 代理不了天气 -> 仅作示例轴
    "距离带": (0, (0, 130, 250, 450)),
    "对手空中": (6, (0, 1)),
    "弹幕接近": (7, (0, 1)),
    "我在左侧": (8, (0, 1)),
    "对手在版边": (10, (0, 1)),
}


def offline_report(
    logits: np.ndarray, y: np.ndarray, raw_features: np.ndarray, n_macros: int,
    macro_names: list[str] | None = None,
) -> dict:
    """指标套件 + 分类切片 + 行为分布。

    logits/y/raw_features 必须行对齐（同一验证集、同一顺序）。
    """
    rep = {"overall": metrics.summarize(logits, y, n_macros)}
    pred = logits.argmax(axis=1)

    # 行为分布 vs 教师分布：模型是不是只在少数宏上打转
    teacher = np.bincount(y, minlength=n_macros).astype(np.float64)
    model = np.bincount(pred, minlength=n_macros).astype(np.float64)
    rep["distribution"] = {
        "js_divergence_vs_teacher": metrics.js_divergence(model, teacher),
        "teacher_top1_share": float(teacher.max() / teacher.sum()),
        "model_top1_share": float(model.max() / max(model.sum(), 1)),
        "teacher_classes_used": int((teacher > 0).sum()),
        "model_classes_used": int((model > 0).sum()),
        "classes_model_never_picks": [int(i) for i in np.flatnonzero((model == 0) & (teacher > 0))],
        "classes_model_hallucinates": [int(i) for i in np.flatnonzero((model > 0) & (teacher == 0))],
    }

    # 分类切片：定位"哪类局面学不会"
    slices = {}
    for name, (col, edges) in SLICE_AXES.items():
        if col >= raw_features.shape[1]:
            continue
        vals = raw_features[:, col]
        bins = np.digitize(vals, edges) - 1
        entry = []
        for b in np.unique(bins):
            m = bins == b
            if m.sum() < 30:
                continue
            entry.append({
                "bin": int(b), "n": int(m.sum()),
                "top1": metrics.top_k_accuracy(logits[m], y[m], 1),
                "macro_f1": metrics.macro_f1(logits[m], y[m], n_macros),
            })
        slices[name] = entry
    rep["slices"] = slices

    # 逐宏召回：区分"高频类尚可 / 低频类全灭"
    rec = metrics.per_class_recall(logits, y, n_macros)
    support = np.bincount(y, minlength=n_macros)
    rep["per_class_recall"] = [
        {"macro": int(i), "name": (macro_names[i] if macro_names and i < len(macro_names) else None),
         "support": int(support[i]), "recall": (None if np.isnan(rec[i]) else float(rec[i])),
         "selected": int((pred == i).sum())}
        for i in np.flatnonzero(support > 0)
    ]
    return rep


# --------------------------------------------------------------------------
# 在线协议（需真机）
# --------------------------------------------------------------------------
ONLINE_FIELD_SPEC: dict[str, str] = {
    "match_id": "局 ID（两 AI 各自唯一）",
    "ai_side": "left/right；模型坐哪边",
    "opponent_kind": "rule_ai / old_model:<hash> / human:<id>",
    "mod_hash": "mod 编译哈希（语义漂移检测）",
    "tick": "决策拍序号",
    "game_frame": "逻辑帧号",
    "wall_ms_decision": "本拍决策墙钟耗时（算 P50/P95/P99）",
    "macro_chosen": "本拍宏 ID",
    "macro_executed_frames": "该宏实际执行帧数（校验宏语义）",
    "dmg_dealt": "本拍造成的伤害",
    "dmg_taken": "本拍承受的伤害",
    "hp_l/hp_r": "双方血量",
    "weather_active": "当前天气 ID（0..21）",
    "corner_flag": "是否版边",
    "crashed": "是否崩溃/超时局（必须计入分母，禁止静默丢弃）",
    "round_winner": "1/0/2（胜/负/平）",
}


class GameAdapter(Protocol):
    """真机对战适配器。实现它即可接入在线评估，而评估代码无需改动。"""

    def reset(self, params: dict) -> dict: ...
    def step(self, inputs_left: dict, inputs_right: dict) -> dict: ...
    def close(self) -> None: ...


class NullAdapter:
    """占位适配器：明确拒绝，而不是返回假数据。"""

    def __init__(self, reason: str = "本机无可用游戏+mod 通道"):
        self.reason = reason

    def _fail(self):
        raise RuntimeError(
            "在线评估不可用：%s\n"
            "需要以下前置条件（任一缺失都无法得到真实胜率）：\n"
            "  1) 可运行的 th123.exe + 训练 mod（SokuAITrainer 血统），暴露逐帧状态与输入接口；\n"
            "  2) 锁步/固定 tps 的对局控制通道（soku_client 协议）；\n"
            "  3) 双方 AI 的输入注入点（左/右独立）；\n"
            "  4) 崩溃/超时局的可靠捕获（否则胜率分母失真）。\n"
            "在此之前，本项目**只报离线指标，不报胜率**。" % self.reason
        )

    def reset(self, params: dict) -> dict:
        self._fail()

    def step(self, inputs_left: dict, inputs_right: dict) -> dict:
        self._fail()

    def close(self) -> None:
        self._fail()


@dataclass
class MatchPlan:
    """一次在线评估的设计（变量/对照/样本量/停止条件）。"""

    name: str
    opponent_kind: str
    games: int
    tps: int = 480
    seed: int = 0
    stop_condition: str = "达到 games 局或连续 5 局崩溃（崩溃局计入分母）"
    record: dict = field(default_factory=lambda: dict(ONLINE_FIELD_SPEC))

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, indent=2)


DEFAULT_MATCH_PLANS: tuple[MatchPlan, ...] = (
    MatchPlan("AI vs 规则AI", "rule_ai", 200),
    MatchPlan("AI vs 旧模型", "old_model:<hash>", 200),
    MatchPlan("AI vs 人类", "human:<id>", 50),
)


__all__ = [
    "SLICE_AXES", "offline_report", "ONLINE_FIELD_SPEC", "GameAdapter",
    "NullAdapter", "MatchPlan", "DEFAULT_MATCH_PLANS",
]
