# -*- coding: utf-8 -*-
"""`.rep` 事件驱动解析器 —— 严格依据 SokuLib 的权威 schema，不猜。

权威来源（只读引用）：
  D:\\temp\\build\\SokuAI-master\\SokuLib\\src\\Packet.hpp / Packet.cpp
    enum GameType  : GAME_LOADED=0x01, GAME_LOADED_ACK, GAME_INPUT=0x03, GAME_MATCH=0x04,
                     GAME_MATCH_ACK=0x05, GAME_MATCH_REQUEST=0x08, GAME_REPLAY=0x09,
                     GAME_REPLAY_REQUEST=0x0B
    enum CharacterPacked : 0..19，与 SokuLib::Character 同序（REIMU=0 … SUWAKO=19）
    struct PlayerMatchData { uint8 character; uint8 skinId; uint8 deckId; uint8 deckSize;
                             uint16 cards[deckSize]; uint8 disabledSimultaneousButton; }
      （`&cards[deckSize]` 处即 disabledSimultaneousButton，见 Packet.hpp:220）
    struct GameMatchEvent { GameType type; PlayerMatchData host;  // 变长
                            PlayerMatchData &client = host.getEndPtr();
                            uint8 &stageId = client_end[0];   uint8 &musicId = [1];
                            uint32 &randomSeed = [2..5];      uint8 &matchId = [6]; }
    struct GameInputEvent { GameType type; uint32 frameId; uint8 sceneId;
                            uint8 inputCount; Inputs inputs[inputCount]; }
    struct GameReplayEvent { GameType type; uint8 replaySize; uint8 compressedData[0]; }
    struct GameReplayRequestEvent { GameType type; uint32 frameId; uint8 matchId; }
    union Inputs  = unsigned short（BattleKeys 位域）→ 复用 soku_arch.input_codec
  D:\\temp\\build\\SokuAI-master\\SokuLib\\src\\InputManager.hpp:66-86
    BattleKeys: up,down,left,right,A,B,C,dash,AandB,BandC,pause,select（u16 位域）

**为什么是事件驱动**：`GameType` 标签决定负载长度，且 `PlayerMatchData` 是变长的
（长度由 `deckSize` 决定）。因此不存在"固定步长"，此前的等距搜索假设是错的。

**流起点如何确定（自证而非猜）**：文件开头有若干字节的文件级头（magic `0xD2`、
月/日、模式等）。解析器在 `0..head_probe` 内枚举候选起点，对每个候选尝试**严格解析
到文件末尾**，只有"完整消费 + 全部字段合法"的候选才被接受；若多个候选都成立则报歧义。
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

from .input_codec import BATTLE_BITS, BattleInput

# GameType（Packet.hpp:80-89）
GAME_LOADED = 0x01
GAME_LOADED_ACK = 0x02
GAME_INPUT = 0x03
GAME_MATCH = 0x04
GAME_MATCH_ACK = 0x05
GAME_MATCH_REQUEST = 0x08
GAME_REPLAY = 0x09
GAME_REPLAY_REQUEST = 0x0B

GAME_TYPE_NAMES = {
    GAME_LOADED: "GAME_LOADED", GAME_LOADED_ACK: "GAME_LOADED_ACK",
    GAME_INPUT: "GAME_INPUT", GAME_MATCH: "GAME_MATCH",
    GAME_MATCH_ACK: "GAME_MATCH_ACK", GAME_MATCH_REQUEST: "GAME_MATCH_REQUEST",
    GAME_REPLAY: "GAME_REPLAY", GAME_REPLAY_REQUEST: "GAME_REPLAY_REQUEST",
}

# CharacterPacked（0..19，与 SokuLib::Character 同序）
PACKED_CHARACTER_NAMES: tuple[str, ...] = (
    "REIMU", "MARISA", "SAKUYA", "ALICE", "PATCHOULI", "YOUMU", "REMILIA", "YUYUKO",
    "YUKARI", "SUIKA", "REISEN", "AYA", "KOMACHI", "IKU", "TENSHI", "SANAE",
    "CIRNO", "MEILING", "UTSUHO", "SUWAKO",
)

SCENE_CHARACTER_SELECT = 0x03
SCENE_BATTLE = 0x05


class RepFormatError(ValueError):
    """格式不符合权威 schema —— 必须大声失败，不能返回部分结果。"""


@dataclass
class PlayerMatch:
    character: int
    skin_id: int
    deck_id: int
    deck_size: int
    cards: tuple[int, ...]
    disabled_simultaneous_button: int

    @property
    def character_name(self) -> str:
        return (PACKED_CHARACTER_NAMES[self.character]
                if 0 <= self.character < len(PACKED_CHARACTER_NAMES)
                else f"UNKNOWN({self.character})")

    def sane(self) -> bool:
        return (0 <= self.character < len(PACKED_CHARACTER_NAMES)
                and 1 <= self.deck_size <= 40
                and all(0 <= c <= 0xFFFF for c in self.cards))


@dataclass
class MatchEvent:
    host: PlayerMatch
    client: PlayerMatch
    stage_id: int
    music_id: int
    random_seed: int
    match_id: int


@dataclass
class InputEvent:
    frame_id: int
    scene_id: int
    inputs: list[int]        # 原始 u16（BattleKeys 位域）


@dataclass
class ReplayBlock:
    """GAME_REPLAY 的负载，若是压缩数据则解压后按 ReplayData 解析。

    ReplayData（Packet.hpp:203-209）:
        uint32 frameId; uint32 endFrameId; uint8 matchId; uint8 length; Inputs replayInputs[length];
    """
    replay_size: int
    compressed: bytes
    decompressed: bytes | None = None
    frame_id: int | None = None
    end_frame_id: int | None = None
    match_id: int | None = None
    length: int | None = None
    inputs: list[int] = field(default_factory=list)


@dataclass
class ParsedRep:
    stream_start: int
    header: bytes
    match: MatchEvent | None = None
    input_events: list[InputEvent] = field(default_factory=list)
    replay_blocks: list[ReplayBlock] = field(default_factory=list)
    scene_ids: list[int] = field(default_factory=list)
    n_events: int = 0
    tail_bytes: int = 0


# --------------------------------------------------------------------------
def _read_player_match(buf: bytes, off: int) -> tuple[PlayerMatch, int]:
    need = off + 5
    if need > len(buf):
        raise RepFormatError(f"PlayerMatchData 头越界 off={off} size={len(buf)}")
    character, skin, deck_id, deck_size = buf[off], buf[off + 1], buf[off + 2], buf[off + 3]
    if not (1 <= deck_size <= 40):
        raise RepFormatError(f"deckSize 不合理: {deck_size} (off={off})")
    end_cards = off + 4 + 2 * deck_size
    if end_cards + 1 > len(buf):
        raise RepFormatError(f"cards 越界 off={off} deckSize={deck_size}")
    cards = struct.unpack_from(f"<{deck_size}H", buf, off + 4)
    dis = buf[end_cards]
    pm = PlayerMatch(character, skin, deck_id, deck_size, cards, dis)
    if not pm.sane():
        raise RepFormatError(f"PlayerMatchData 字段不合法: {pm}")
    return pm, end_cards + 1


def _read_match_event(buf: bytes, off: int) -> tuple[MatchEvent, int]:
    host, p = _read_player_match(buf, off)
    client, p = _read_player_match(buf, p)
    if p + 7 > len(buf):
        raise RepFormatError("GameMatchEvent 尾部越界")
    stage_id = buf[p]
    music_id = buf[p + 1]
    seed = struct.unpack_from("<I", buf, p + 2)[0]
    match_id = buf[p + 6]
    return MatchEvent(host, client, stage_id, music_id, seed, match_id), p + 7


def _try_decompress(payload: bytes) -> bytes | None:
    """GAME_REPLAY 的负载字段名就是 `compressedData`，试 zlib/raw-deflate 两种。"""
    for wbits in (15, -15, 47):
        try:
            out = zlib.decompress(payload, wbits)
            if out:
                return out
        except zlib.error:
            continue
    return None


def _read_replay_data(blob: bytes) -> tuple[int, int, int, int, list[int]]:
    if len(blob) < 10:
        raise RepFormatError(f"ReplayData 过短: {len(blob)}")
    frame_id, end_frame_id = struct.unpack_from("<II", blob, 0)
    match_id, length = blob[8], blob[9]
    need = 10 + 2 * length
    if need > len(blob):
        # length 可能不是输入帧数而是别的量；交给调用方判断
        raise RepFormatError(f"ReplayData 输入数越界: length={length} 需 {need} 实 {len(blob)}")
    inputs = list(struct.unpack_from(f"<{length}H", blob, 10))
    return frame_id, end_frame_id, match_id, length, inputs


def parse_stream(buf: bytes, start: int) -> ParsedRep:
    """从 start 起严格解析事件流到文件末尾；任何不一致都抛 RepFormatError。"""
    rep = ParsedRep(stream_start=start, header=buf[:start])
    off, n = start, 0
    while off < len(buf):
        t = buf[off]
        if t == GAME_LOADED or t == GAME_LOADED_ACK:
            if off + 2 > len(buf):
                raise RepFormatError("GameLoadedEvent 越界")
            rep.scene_ids.append(buf[off + 1])
            off += 2
        elif t == GAME_INPUT:
            if off + 7 > len(buf):
                raise RepFormatError("GameInputEvent 越界")
            frame_id = struct.unpack_from("<I", buf, off + 1)[0]
            scene_id = buf[off + 5]
            cnt = buf[off + 6]
            end = off + 7 + 2 * cnt
            if end > len(buf):
                raise RepFormatError(f"GameInputEvent.inputs 越界 cnt={cnt}")
            rep.input_events.append(InputEvent(
                frame_id, scene_id, list(struct.unpack_from(f"<{cnt}H", buf, off + 7))))
            rep.scene_ids.append(scene_id)
            off = end
        elif t == GAME_MATCH:
            ev, off = _read_match_event(buf, off + 1)
            if rep.match is not None:
                raise RepFormatError("出现多个 GameMatchEvent（本解析器只支持单局）")
            rep.match = ev
        elif t == GAME_REPLAY:
            if off + 2 > len(buf):
                raise RepFormatError("GameReplayEvent 越界")
            size = buf[off + 1]
            end = off + 2 + size
            if end > len(buf):
                raise RepFormatError(f"GameReplayEvent 负载越界 size={size}")
            payload = buf[off + 2:end]
            blk = ReplayBlock(replay_size=size, compressed=payload)
            dec = _try_decompress(payload)
            if dec is not None:
                blk.decompressed = dec
                try:
                    (blk.frame_id, blk.end_frame_id, blk.match_id,
                     blk.length, blk.inputs) = _read_replay_data(dec)
                except RepFormatError:
                    pass
            rep.replay_blocks.append(blk)
            off = end
        elif t == GAME_REPLAY_REQUEST:
            if off + 6 > len(buf):
                raise RepFormatError("GameReplayRequestEvent 越界")
            off += 6
        elif t in (GAME_MATCH_ACK, GAME_MATCH_REQUEST):
            # 空负载事件：仅类型字节
            off += 1
        else:
            raise RepFormatError(f"未知 GameType 0x{t:02X} @ {off}")
        n += 1
    rep.n_events = n
    return rep


def find_stream_start(buf: bytes, head_probe: int = 96) -> tuple[int, ParsedRep]:
    """在 0..head_probe 内枚举候选起点，取"能严格解析到末尾"的那个。

    自证逻辑：错误的起点几乎必然在某个变长字段处越界或得到非法 deckSize。
    若多个候选同时成立 -> 报歧义（不静默取第一个）。
    """
    ok: list[tuple[int, ParsedRep]] = []
    for s in range(0, min(head_probe, len(buf)) + 1):
        try:
            rep = parse_stream(buf, s)
        except RepFormatError:
            continue
        if rep.match is not None or rep.replay_blocks or rep.input_events:
            ok.append((s, rep))
    if not ok:
        raise RepFormatError("在候选起点范围内无任何可完整解析的流")
    if len(ok) > 1:
        # 偏好"含 GameMatchEvent 且事件数最多"的候选；仍不唯一则报歧义
        best_n = max(r.n_events for _, r in ok)
        best = [(s, r) for s, r in ok if r.n_events == best_n and r.match is not None]
        if len(best) != 1:
            raise RepFormatError(
                f"流起点歧义：{len(ok)} 个候选可解析（事件数 {[r.n_events for _, r in ok]}）")
        return best[0]
    return ok[0]


def parse_rep(path: str) -> ParsedRep:
    with open(path, "rb") as f:
        buf = f.read()
    start, rep = find_stream_start(buf)
    rep.tail_bytes = 0
    return rep


def inputs_as_battle(rep: ParsedRep) -> list[list[BattleInput]]:
    """把各 replay 块的输入转成 BattleInput（复用权威位域定义）。"""
    out = []
    for blk in rep.replay_blocks:
        if blk.inputs:
            out.append([BattleInput(v) for v in blk.inputs])
    return out


__all__ = [
    "GAME_LOADED", "GAME_INPUT", "GAME_MATCH", "GAME_REPLAY", "GAME_REPLAY_REQUEST",
    "GAME_TYPE_NAMES", "PACKED_CHARACTER_NAMES", "SCENE_BATTLE", "SCENE_CHARACTER_SELECT",
    "BATTLE_BITS", "RepFormatError", "PlayerMatch", "MatchEvent", "InputEvent",
    "ReplayBlock", "ParsedRep", "parse_stream", "find_stream_start", "parse_rep",
    "inputs_as_battle",
]
