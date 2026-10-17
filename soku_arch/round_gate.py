# -*- coding: utf-8 -*-
"""输入喂入闸门：把 `.rep` 的输入指针**重新锚定到游戏自己的战斗帧**上。

要解决的问题（来自 `run.py sync-audit` 的实测）：
    驱动把一条 10,349 条的输入流**全部喂完**，却只打出 1 次回合结束，而文件名记 2 回合。
    两种解释都指向同一个修补方向：
      H1 驱动在回合 1 内就已分叉（状态/RNG）；
      H2 `.rep` 的输入流**不含回合间的演出帧**，于是"一帧输入对一帧游戏"的喂法
         从第一次回合结束起就整体错位（演出段的帧把后面所有输入都推后了）。
    对 H2，修法就是本模块：**回合结束时停止推进输入指针**（改喂"保持上一次输入"），
    等新回合真正开始（血量单帧回升）再继续。这样 `inp[i]` 重新对应"进入 x[i] 的那一拍"。

设计要点：
  * **纯状态机、零依赖**——不碰 socket/内存，因此可以用合成分片单测（`tests/test_round_gate.py`）。
  * 进入暂停：**总分增加**（回合刚结束）的那一帧之后。
  * 退出暂停：双方血量都 > 0 且出现"单帧回升 ≥ hp_jump"（= 新回合开始），
    或用 soft_resume / max_pause 兜底 —— **每次退出都记原因**，不用猜。
  * 闸门关闭时行为与旧代码**逐字节一致**（`advance()` 恒 True）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

HP_RESET_JUMP = 3000.0        # 与 bc_data.HP_RESET_JUMP 同源（回合重置的判据）
MAX_PAUSE_FRAMES = 1500       # 硬上限：约 24 秒（62fps），超过必然放行，避免死等
SOFT_RESUME_FRAMES = 900      # 双方存活且停了这么久 → 也放行（超时回合的兜底）


@dataclass
class GateConfig:
    enabled: bool = False
    hp_jump: float = HP_RESET_JUMP
    max_pause: int = MAX_PAUSE_FRAMES
    soft_resume: int = SOFT_RESUME_FRAMES

    @classmethod
    def from_arg(cls, mode: str, **kw) -> "GateConfig":
        if mode not in ("off", "round"):
            raise ValueError(f"feed_gate 只能是 off/round，实际 {mode}")
        return cls(enabled=(mode == "round"), **kw)


def _hp(state: dict, side: str) -> float:
    return float(state[side].get("hp", 0))


def _score(state: dict) -> float:
    return float(state["left"].get("score", 0)) + float(state["right"].get("score", 0))


@dataclass
class RoundGate:
    """回答一个问题：**这一帧该不该推进原录像的输入指针？**"""

    cfg: GateConfig = field(default_factory=GateConfig)
    paused: bool = False
    pause_start: int | None = None
    paused_frames: int = 0
    pauses: list[dict] = field(default_factory=list)
    reasons: dict[str, int] = field(default_factory=dict)

    def _note(self, reason: str) -> None:
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def advance(self, prev: dict | None, cur: dict, frame: int = 0) -> tuple[bool, str]:
        """返回 (是否推进输入指针, 原因)。`frame` 仅用于记录暂停区间。"""
        if not self.cfg.enabled:
            return True, "gate_off"

        if not self.paused:
            if prev is not None and _score(cur) > _score(prev):
                self.paused = True
                self.pause_start = int(frame)
                self.paused_frames = 0
                self._note("hold_round_end")
                return False, "hold_round_end"
            return True, "replay"

        self.paused_frames += 1
        alive = _hp(cur, "left") > 0 and _hp(cur, "right") > 0
        jumped = prev is not None and alive and (
            _hp(cur, "left") - _hp(prev, "left") >= self.cfg.hp_jump
            or _hp(cur, "right") - _hp(prev, "right") >= self.cfg.hp_jump)
        reason = None
        if jumped:
            reason = "resume_new_round"
        elif self.paused_frames >= self.cfg.max_pause:
            reason = "resume_max_pause"
        elif alive and self.paused_frames >= self.cfg.soft_resume:
            reason = "resume_soft"
        if reason is None:
            self._note("hold_cutscene")
            return False, "hold_cutscene"

        self.pauses.append({"start_frame": self.pause_start, "end_frame": int(frame),
                            "frames": self.paused_frames, "reason": reason})
        self.paused = False
        self.pause_start = None
        self.paused_frames = 0
        self._note(reason)
        return True, reason

    def summary(self) -> dict:
        return {
            "enabled": self.cfg.enabled,
            "hp_jump": self.cfg.hp_jump, "max_pause": self.cfg.max_pause,
            "soft_resume": self.cfg.soft_resume,
            "n_pauses": len(self.pauses), "pauses": self.pauses,
            "paused_frames_total": int(sum(p["frames"] for p in self.pauses)),
            "reasons": dict(self.reasons),
            "still_paused_at_end": bool(self.paused),
        }


__all__ = ["GateConfig", "RoundGate", "HP_RESET_JUMP", "MAX_PAUSE_FRAMES",
           "SOFT_RESUME_FRAMES"]
