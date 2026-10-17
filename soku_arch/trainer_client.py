# -*- coding: utf-8 -*-
"""SokuAITrainer(TrainingMod) 最小客户端 —— 本项目自建，只依赖已读清的协议事实。

协议事实来源（只读引用，均已核对）：
  C:\\Users\\96120\\Desktop\\workplace\\th123_rl\\soku_client2.py
    * 握手: 发送 b"\\x00\\x2A\\x9D\\x6E\\xF5"（op=0 + magic 0xF56E9D2A 小端），期待**原样回显**
    * 启动: 客户端先 bind(127.0.0.1, port) 再 `th123.exe <port>`；mod 主动连回
    * 帧:  op(1) + left(105) + right(105) + weather(<bbH> displayed,active,timer)
           + objects(objectCountL+objectCountR 个 × <b2f4H> 17B)
    * op 12 (OK) 会混入帧流 —— 必须透明跳过（前序项目 hitlab 事故教训）
    * op 11 = GAME_ENDED(winner, leftScore, rightScore)；op 7 = ERROR(code)
    * op 2 = SPEED(<BI> tps)；op 9 = GAME_INPUTS(<BHH> 左右输入)
    * 开局 op 17 = VS_COM，包体 117B: <BBBI20sB32sI20sB32s>
      应答 OK 或 ERROR(err)；err=12 表示未就绪 → CANCEL(10) 后重试

本模块只做**只读探测**：开局 → 注入若干帧固定输入 → 记录真实状态字节 → 干净退出。
产物写在项目内，用于离线校验 packet_schema 的 105 字节解析。

用法：
  python run.py soku-probe --port 20700 --frames 120 --exe <th123.exe> --gamedir <dir> --out data/probe
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import select
import socket
import struct
import subprocess
import time

from .packet_schema import CS_FIELDS, CS_FMT, CS_SIZE, FRAME_HEAD, unpack_player

OPCODE_HELLO = 0
OPCODE_GOODBYE = 1
OPCODE_SPEED = 2
OPCODE_DISPLAY = 3
OPCODE_START_GAME_VS_PLAYER = 5
OPCODE_FAULT = 6
OPCODE_ERROR = 7
OPCODE_GAME_FRAME = 8
OPCODE_GAME_INPUTS = 9
OPCODE_GAME_CANCEL = 10
OPCODE_GAME_ENDED = 11
OPCODE_OK = 12
OPCODE_START_GAME_VS_COM = 17

# packet.hpp:35-54 的 Errors 枚举（用于把 err 号翻译成可读原因，避免只看数字瞎猜）
ERROR_NAMES = {
    0: "INVALID_OPCODE", 1: "INVALID_PACKET", 2: "INVALID_LEFT_DECK",
    3: "INVALID_LEFT_CHARACTER", 4: "INVALID_LEFT_PALETTE", 5: "INVALID_RIGHT_DECK",
    6: "INVALID_RIGHT_CHARACTER", 7: "INVALID_RIGHT_PALETTE", 8: "INVALID_MUSIC",
    9: "INVALID_STAGE", 10: "INVALID_MAGIC", 11: "HELLO_NOT_SENT",
    12: "STILL_PLAYING", 13: "POSITION_OUT_OF_BOUND", 14: "INVALID_HEALTH",
    15: "INVALID_WEATHER", 16: "INVALID_WEATHER_TIME", 17: "NOT_IN_GAME",
}
# 这些错误码表示"还没就绪"，属于可重试的时序问题，不是配置错误
RETRYABLE_ERRORS = {12, 17}

HELLO = b"\x00\x2A\x9D\x6E\xF5"
# 哨兵开局包：全部填非法值（char=0xFFFFFFFF, palette=255, stage=255, 空名）。
# 用途见 wait_for_ready —— 参考 GameInstance.py:250-255。
SENTINEL_START = struct.pack(
    "<BBBI20sB32sI20sB32s", OPCODE_START_GAME_VS_COM, 255, 255,
    0xFFFFFFFF, b"\0" * 20, 255, b"\0" * 32,
    0xFFFFFFFF, b"\0" * 20, 255, b"\0" * 32)
OBJ_FMT = "<b2f4H"      # direction, relPos(2f), 4×u16
OBJ_SIZE = struct.calcsize(OBJ_FMT)


class TrainerError(RuntimeError):
    pass


class GameEnded(Exception):
    def __init__(self, winner: int, ls: int, rs: int):
        super().__init__(f"winner={winner} {ls}-{rs}")
        self.winner, self.ls, self.rs = winner, ls, rs


class TrainerClient:
    def __init__(self, port: int, exe: str, game_dir: str, launch: bool = True,
                 accept_timeout: float = 120.0, log=print,
                 extra_args: list[str] | None = None, extra_after_port: bool = False,
                 raw_argv: list[str] | None = None, cwd_override: str | None = None,
                 env: dict[str, str] | None = None, on_launched=None):
        """extra_args 插入命令行；raw_argv 则**原样使用**（用于"单参数同时充当端口与 rep 路径"）。

        背景（实测）：训练 mod 与 ReplayDnD **都读最后一个参数**——
          `th123.exe "<rep>" <port>` -> mod 连上（读到端口），但 ReplayDnD 读到 "20700" 不播；
          `th123.exe "<rep>"`        -> ReplayDnD 正常驱动（scene 走到选人），但 mod 无端口；
          `th123.exe <port> "<rep>"` -> mod **完全连不上**（证明它不回退 argv[1]），
                                        而 ReplayDnD 播了并在 AutoShutdown 后关掉游戏。
        因此试第三种：cwd=暂存目录、argv=[\"<port>.rep\"] —— 同一个参数
        既能被 strtol 读成端口，又能被 ReplayDnD 当成 .rep 路径。
        """
        self.port = port
        self.log = log
        self.proc = None
        self.lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind(("127.0.0.1", port))
        self.lsock.listen(1)
        if launch:
            extra = list(extra_args or [])
            if raw_argv is not None:
                argv = [exe] + list(raw_argv)      # raw_argv 只替换"exe 之后"的参数
            else:
                argv = ([exe, str(port)] + extra) if extra_after_port \
                    else ([exe] + extra + [str(port)])
            self.proc = subprocess.Popen(
                argv, cwd=(cwd_override or game_dir),
                env=({**os.environ, **env} if env else None),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            if env:
                log(f"[环境] {env}")
            log(f"[启动] cwd={cwd_override or game_dir}  argv={argv}  (pid={self.proc.pid})")
            # 启动后、accept 前的回调。被动观测模式需要它：**游戏未聚焦就不推进**，
            # 而"等到 mod 连上再置前台"会死锁（游戏不推进 → mod 不连 → 永远不置前台）。
            if on_launched is not None:
                on_launched(self.proc.pid)
        self.lsock.settimeout(accept_timeout)
        try:
            self.sock, peer = self.lsock.accept()
        except socket.timeout:
            self.close()
            raise TrainerError(f"mod 在 {accept_timeout:.0f}s 内未连接（启动崩溃？）")
        log(f"[连接] {peer[0]}:{peer[1]} 已接入")

    # ---------------- 传输 ----------------
    def _send(self, d: bytes) -> None:
        self.sock.sendall(d)

    def _recv_exact(self, n: int, timeout: float = 10.0) -> bytes:
        """deadline 制（首字节后共享同一预算，避免半包永久挂起）。"""
        buf = b""
        deadline = time.time() + timeout
        while len(buf) < n:
            remain = deadline - time.time()
            if remain <= 0:
                raise TimeoutError(f"读取 {n} 字节超时（已得 {len(buf)}）")
            r, _, _ = select.select([self.sock], [], [], remain)
            if not r:
                raise TimeoutError(f"读取 {n} 字节超时（已得 {len(buf)}）")
            c = self.sock.recv(n - len(buf))
            if not c:
                raise ConnectionError("连接被对端关闭（半包途中）")
            buf += c
        return buf

    def handshake(self) -> None:
        self._send(HELLO)
        echo = self._recv_exact(len(HELLO), 15.0)
        if echo != HELLO:
            raise TrainerError(f"握手失败：回显 {echo.hex()} != {HELLO.hex()}")
        self.log("[握手] OK（magic 0xF56E9D2A 回显一致）")

    # ---------------- 控制 ----------------
    def set_speed(self, tps: int) -> None:
        self._send(struct.pack("<BI", OPCODE_SPEED, tps))
        self._recv_exact(1, 5.0)

    def set_display(self, enabled: bool = False) -> None:
        self._send(struct.pack("<B?", OPCODE_DISPLAY, bool(enabled)))
        self._recv_exact(1, 5.0)

    def start_game(self, left_char: int, right_char: int, left_deck=None,
                   right_deck=None, left_palette: int = 0, right_palette: int = 1,
                   stage: int = 0, music: int = 0, opcode: int = OPCODE_START_GAME_VS_COM,
                   retries: int = 20, hook=None) -> dict:
        """开局；成功后**立即读首帧**（参考 GameInstance.start_game:346 的 recv_game_frame(False)）。

        返回首帧 —— 不要在这里发输入：开局成功后 mod 会直接推一帧过来。

        `hook`：**发包之后、收帧之前**调用的回调（无参）。用于"钉种子"——
        种子必须早于游戏消费它（洗牌/天气调度）写入，这个时机正好在窗口内。
        """
        ld = list(left_deck if left_deck is not None else range(1, 21))[:20]
        rd = list(right_deck if right_deck is not None else ld)[:20]
        ld += [0] * (20 - len(ld))
        rd += [0] * (20 - len(rd))
        pkt = struct.pack(
            "<BBBI20sB32sI20sB32s", opcode, stage, music,
            left_char, bytes(ld), left_palette, b"EXP-LEFT".ljust(32, b"\0"),
            right_char, bytes(rd), right_palette, b"EXP-RIGHT".ljust(32, b"\0"))
        if len(pkt) != 117:
            raise AssertionError(f"开局包长度 {len(pkt)} != 117")
        self._send(pkt)
        if hook is not None:
            try:
                hook()
            except Exception as exc:  # noqa: BLE001
                self.log(f"  开局 hook 失败（继续）: {exc}")
        # 实测：mod 可能先回一个 ack(op=12) 且其后暂无数据 → poll 会超时。
        # 这**不是**开局失败，必须重试而不是把整局判失败（批量驱动时曾因此丢掉一局）。
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                kind, payload = self.poll(timeout=30.0)
            except TimeoutError as exc:
                last_exc = exc
                self.log(f"  开局等待首帧超时（第 {attempt}/{retries} 次），重试")
                continue
            if kind == "error":
                raise TrainerError(
                    f"开局被拒 err={payload} ({ERROR_NAMES.get(payload, '未知')})")
            if kind == "fault":
                raise TrainerError(f"开局期间游戏崩溃 fault={payload}")
            if kind != "frame":
                raise TrainerError(f"开局后应收到帧，实际 {kind}={payload}")
            self.log(f"  开局 OK（已收到首帧，第 {attempt} 次尝试）")
            return payload
        raise TrainerError(f"开局 {retries} 次均未收到首帧：{last_exc}")

    def wait_for_ready(self, max_wait: float = 60.0) -> int:
        """等待游戏"不在战斗中"（即可以开局）。

        参考 GameInstance.wait_for_ready:248-274 —— 用一个**非法哨兵开局包**当探针：
          * 回 ERROR 且 err != 12 → 不在战斗中 → 就绪，返回该 err
          * 回 ERROR 且 err == 12 (STILL_PLAYING) → 标题 demo 战斗在跑 → CANCEL → 重试
          * CANCEL 后若回 ERROR 且 err != 17 → 就绪；err == 17 则继续
        """
        t0, attempt = time.time(), 0
        while time.time() - t0 < max_wait:
            attempt += 1
            self._send(SENTINEL_START)
            kind, payload = self.poll(timeout=20.0)
            if kind != "error":
                raise TrainerError(f"哨兵探针异常应答 {kind}={payload}")
            if payload != 12:
                self.log(f"[就绪] 哨兵探针返回 err={payload} "
                         f"({ERROR_NAMES.get(payload, '?')}) → 不在战斗中（{attempt} 次，"
                         f"{time.time() - t0:.1f}s）")
                return int(payload)
            # err == 12：仍在（demo）战斗中
            self._send(bytes([OPCODE_GAME_CANCEL]))
            kind2, payload2 = self.poll(timeout=5.0)
            if kind2 == "error":
                if payload2 != 17:
                    self.log(f"[就绪] CANCEL 后 err={payload2} → 就绪（{attempt} 次）")
                    return int(payload2)
                time.sleep(0.2)
                continue
            # CANCEL 换来一帧 → 已排干，继续下一轮探针
            continue
        raise TrainerError(f"wait_for_ready 超时（{max_wait:.0f}s, {attempt} 次探针）")

    def _read_frame_body(self) -> dict:
        head = self._recv_exact(FRAME_HEAD - 1)
        lb, rb = head[:CS_SIZE], head[CS_SIZE:CS_SIZE * 2]
        wdisp, wact, wt = struct.unpack("<bbH", head[CS_SIZE * 2:CS_SIZE * 2 + 4])
        left_raw, right_raw = unpack_player(lb), unpack_player(rb)
        n = left_raw["objectCount"] + right_raw["objectCount"]
        objs = []
        if n:
            raw = self._recv_exact(OBJ_SIZE * n)
            objs = [struct.unpack(OBJ_FMT, raw[i * OBJ_SIZE:(i + 1) * OBJ_SIZE])
                    for i in range(n)]
        return {"left": left_raw, "right": right_raw,
                "weather": {"displayed": wdisp, "active": wact, "timer": wt},
                "objects": objs, "left_raw_bytes": lb, "right_raw_bytes": rb}

    def poll(self, timeout: float = 2.0) -> tuple[str, object]:
        """读一条消息：('frame', dict) / ('error', code) / ('ended', (w,ls,rs))。

        op=12 (OK) 会混入帧流，必须**透明跳过**（前序项目 hitlab 事故教训：
        不跳过则上层把 op=12 当协议错误重开会话，摆位/回血全部被重置）。
        """
        r, _, _ = select.select([self.sock], [], [], timeout)
        if not r:
            raise TimeoutError(f"poll 超时（{timeout}s）")
        op = self._recv_exact(1)[0]
        while op == OPCODE_OK:
            # op=12 是纯 ack，可能单独到达（其后暂无数据）。此时按**超时**处理即可，
            # 让调用方重试；绝不能当成协议错误（否则一局刚开始就被判失败）。
            r, _, _ = select.select([self.sock], [], [], timeout)
            if not r:
                raise TimeoutError(f"收到 ack(op=12) 后 {timeout}s 内无后续数据")
            op = self._recv_exact(1)[0]
        if op == OPCODE_GAME_FRAME:
            return "frame", self._read_frame_body()
        if op == OPCODE_GAME_ENDED:
            w, ls, rs = self._recv_exact(3)
            return "ended", (w, ls, rs)
        if op == OPCODE_ERROR:
            code = self._recv_exact(1)[0]
            return "error", code
        if op == OPCODE_FAULT:
            # FaultPacket{ Opcode op; void *faultAddress; unsigned faultExceptionCode; }
            # x86：地址 4 字节在前、异常码 4 字节在后（共 8 字节负载）。
            # op=6 是**游戏崩溃**上报（mod 的 UnhandledExFilter），不是结果包。
            body = self._recv_exact(8)
            addr, code = struct.unpack("<II", body)
            return "fault", (addr, code)
        raise TrainerError(f"帧流中出现未知 op={op}")

    def recv_frame(self, timeout: float = 2.0) -> dict:
        kind, payload = self.poll(timeout)
        if kind == "frame":
            return payload
        if kind == "ended":
            raise GameEnded(*payload)
        raise TrainerError(
            f"mod 报错 err={payload} ({ERROR_NAMES.get(payload, '未知')})")

    def send_inputs(self, left: dict, right: dict) -> None:
        self._send(struct.pack("<BHH", OPCODE_GAME_INPUTS,
                               pack_input(left), pack_input(right)))

    def settle(self, max_wait: float = 45.0, poll: float = 1.0) -> dict:
        """开局后等待**真正进入战斗**。

        协议是锁步的：必须发输入才会出帧。但开局指令刚被接受时游戏还在场景切换
        （实测会回 err=17 NOT_IN_GAME）。因此这里反复发中立输入并尝试收帧，
        把 err=12/17 与超时都视为"还没就绪"。
        """
        t0 = time.time()
        attempt = 0
        while time.time() - t0 < max_wait:
            attempt += 1
            try:
                self.send_inputs(NEUTRAL, NEUTRAL)
                f = self.recv_frame(timeout=poll)
                self.log(f"[就绪] 第 {attempt} 次尝试收到首帧，"
                         f"用时 {time.time() - t0:.1f}s")
                return f
            except TrainerError as e:
                code = _err_code(str(e))
                if code in RETRYABLE_ERRORS:
                    time.sleep(0.3)
                    continue
                raise
            except TimeoutError:
                time.sleep(0.2)
                continue
        raise TrainerError(f"等待进入战斗超时（{max_wait:.0f}s, {attempt} 次尝试）")

    def close(self) -> None:
        try:
            if getattr(self, "sock", None):
                try:
                    self._send(bytes([OPCODE_GOODBYE]))
                except Exception:
                    pass
                self.sock.close()
        except Exception:
            pass
        try:
            self.lsock.close()
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.log(f"[退出] 游戏进程已结束 (pid={self.proc.pid})")


def _err_code(msg: str) -> int | None:
    for tok in msg.replace("(", " ").replace(")", " ").split():
        if tok.startswith("err="):
            try:
                return int(tok[4:])
            except ValueError:
                return None
    return None


def pack_input(i: dict) -> int:
    v = 0
    v |= bool(i.get("A")) << 0
    v |= bool(i.get("B")) << 1
    v |= bool(i.get("C")) << 2
    v |= bool(i.get("D")) << 3
    v |= bool(i.get("SC")) << 4
    v |= bool(i.get("SW")) << 5
    v |= (i.get("H", 0) & 3) << 6
    v |= (i.get("V", 0) & 3) << 8
    return v


NEUTRAL = {"A": False, "B": False, "C": False, "D": False, "SC": False, "SW": False,
           "H": 0, "V": 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SokuAITrainer 只读探测")
    ap.add_argument("--port", type=int, default=20700)
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--exe", required=True)
    ap.add_argument("--gamedir", required=True)
    ap.add_argument("--left-char", type=int, default=0)
    ap.add_argument("--right-char", type=int, default=1)
    ap.add_argument("--tps", type=int, default=0, help=">0 则设置游戏速度")
    ap.add_argument("--hide", action="store_true", help="请求关闭渲染")
    ap.add_argument("--settle", type=float, default=45.0,
                    help="开局后等待真正进入战斗的最长秒数（场景切换需要时间）")
    ap.add_argument("--focus", action="store_true",
                    help="把游戏窗口程序化置前台（未聚焦时游戏不推进，见 test_focus.py）")
    ap.add_argument("--observe-scene", action="store_true",
                    help="只读观察场景字节（不做任何内存写；地址常量未证实）")
    ap.add_argument("--fill-input-table", action="store_true",
                    help="填输入管理器表（TBL←2×MGR）。这是**游戏进程内存写**；"
                         "先读后写并打印原值，仅在本机调试用")
    ap.add_argument("--out", default=os.path.join("data", "probe"))
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    cli = TrainerClient(args.port, args.exe, args.gamedir, launch=True, log=print)
    report: dict = {"port": args.port, "frames_requested": args.frames, "ok": False}
    frames = []
    try:
        cli.handshake()
        if args.hide:
            cli.set_display(False)
            print("[显示] 已请求关闭渲染")
        if args.tps > 0:
            cli.set_speed(args.tps)
            print(f"[速度] tps={args.tps}")
        # 必须先置前台：未聚焦时游戏不推进（test_focus.py 的核心发现）
        if args.focus:
            from . import win_probe
            hwnd = win_probe.find_window(cli.proc.pid)
            print(f"[窗口] pid={cli.proc.pid} hwnd={hex(hwnd) if hwnd else None}")
            if hwnd:
                ok = win_probe.force_foreground(hwnd)
                print(f"[置前台] {'成功' if ok else '失败（前台锁？）'}")
            time.sleep(1.0)

        # 输入管理器表填充：参考 test_focus.py:64-65。
        # 采用**先读后写**：打印原值（便于回滚），已是目标值则跳过，写完再读回校验。
        if args.fill_input_table:
            from . import win_probe
            h = win_probe.open_for_write(cli.proc.pid)
            if not h:
                print("[输入表] OpenProcess(写) 失败，跳过")
            else:
                before = win_probe.read_bytes(h, win_probe.TBL_ADDR, 8)
                print(f"[输入表] 写前 0x{win_probe.TBL_ADDR:X} = {before.hex() if before else None}")
                target = struct.pack("<II", win_probe.MGR_ADDR, win_probe.MGR_ADDR)
                if before == target:
                    print("[输入表] 已是目标值，跳过写入")
                else:
                    ok = win_probe.write_bytes(h, win_probe.TBL_ADDR, target)
                    after = win_probe.read_bytes(h, win_probe.TBL_ADDR, 8)
                    print(f"[输入表] 写入={'成功' if ok else '失败'}  写后 = "
                          f"{after.hex() if after else None}  （原值已记录，可回滚）")
                win_probe.k32.CloseHandle(ctypes.c_void_p(h))

        cli.wait_for_ready(max_wait=args.settle)
        first = cli.start_game(args.left_char, args.right_char,
                               opcode=OPCODE_START_GAME_VS_COM)
        print(f"[开局] char {args.left_char} vs {args.right_char}")

        scene_log = []
        if args.focus or args.observe_scene:
            from . import win_probe
            hwnd = win_probe.find_window(cli.proc.pid)
            print(f"[窗口] pid={cli.proc.pid} hwnd={hex(hwnd) if hwnd else None}")
            if args.focus and hwnd:
                ok = win_probe.force_foreground(hwnd)
                print(f"[置前台] {'成功' if ok else '失败（可能被前台锁拦下）'}")
            if args.observe_scene:
                h = win_probe.open_for_read(cli.proc.pid)
                if not h:
                    print("[只读观察] OpenProcess 失败（权限不足？）")
                else:
                    for k in range(12):
                        sc = win_probe.read_u8(h, win_probe.SCENE_ADDR)
                        mh = win_probe.read_i32(h, win_probe.MGR_ADDR + 0x38)
                        scene_log.append({"t": round(k * 0.5, 1), "scene": sc, "mgr_h": mh})
                        print(f"   [只读 {k*0.5:4.1f}s] SCENE=0x{win_probe.SCENE_ADDR:X} -> "
                              f"{sc}   MGR+0x38={mh}")
                        time.sleep(0.5)
                    win_probe.k32.CloseHandle(ctypes.c_void_p(h))
        report["scene_observation"] = scene_log

        # start_game 已阻塞读到首帧（参考实现 start_game:346），无需再 settle
        frames.append(first)
        print("[进入战斗] 开始注入输入")

        for i in range(1, args.frames):
            # 前半中立，后半持续按右方向 + A（制造可判读的行为差异）
            inp = dict(NEUTRAL)
            if i >= args.frames // 2:
                inp = {"A": True, "B": False, "C": False, "D": False, "SC": False,
                       "SW": False, "H": 1, "V": 0}
            cli.send_inputs(inp, NEUTRAL)
            f = cli.recv_frame(timeout=3.0)
            frames.append(f)
            if i in (0, 1, args.frames // 2, args.frames - 1):
                L = f["left"]
                print(f"  f{i:4d} hp={L['hp']:5d} spirit={L['spirit']:4d} "
                      f"pos=({L['position.x']:7.1f},{L['position.y']:6.1f}) "
                      f"act={L['action']:5d} pose={L['pose']:5d} air={int(L['airBorne'])} "
                      f"gauge={L['cardGauge']:4d} objs={L['objectCount']}+{f['right']['objectCount']} "
                      f"weather={f['weather']['active']}")
        report["ok"] = True
        report["n_frames"] = len(frames)
        report["characters"] = {"left": args.left_char, "right": args.right_char}

        # 落盘原始 105 字节（离线校验 packet_schema 与真实字节的一致性）
        import numpy as np
        lb = np.frombuffer(b"".join(f["left_raw_bytes"] for f in frames),
                           dtype=np.uint8).reshape(-1, CS_SIZE)
        rb = np.frombuffer(b"".join(f["right_raw_bytes"] for f in frames),
                           dtype=np.uint8).reshape(-1, CS_SIZE)
        np.savez(os.path.join(args.out, "frame_raw.npz"), left=lb, right=rb)
        print(f"[落盘] frame_raw.npz  left={lb.shape} right={rb.shape}")

        # 用本项目自己的解析器做一次自洽性报告
        L = frames[-1]["left"]
        checks = {
            "hp_in_range": 0 <= L["hp"] <= 10000,
            "action_in_range": 0 <= L["action"] <= 799,
            "position_plausible": -900 <= L["position.x"] <= 2200,
            "cardGauge_in_range": 0 <= L["cardGauge"] <= 900,
            "hand_has_5": len(L["hand"]) == 5,
            "skills_has_15": len(L["skills"]) == 15,
            "csd_20_bytes": len(L["csd"]) == 20,
            "object_count_matches_list": True,
        }
        report["self_consistency"] = checks
        print("[自洽性] " + " ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()))
        print(f"[csd 前 8 字节] {L['csd'][:8].hex()}")
        print(f"[手牌] {L['hand']}")
        print(f"[技能前 5] {L['skills'][:5]}")

    except GameEnded as e:
        report["game_ended"] = {"winner": e.winner, "ls": e.ls, "rs": e.rs}
        print(f"[局终] winner={e.winner} 比分={e.ls}-{e.rs}")
        report["ok"] = True
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[失败] {report['error']}")
    finally:
        cli.close()

    with open(os.path.join(args.out, "probe_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[产物] {os.path.join(args.out, 'probe_report.json')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
