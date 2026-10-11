# -*- coding: utf-8 -*-
"""v3 侧特征构建器(v2全量回迁 2026-09-22):
威胁矢量网格 + 未来占据 + 卡牌感知 + 对手建模 + 势带 + 速度资源 = 308维核心。
由 train_tm 每决策拍调用, 替代原64维简化版。"""
import numpy as np

from threat import threat_predict, GAME_FPS, HITBOX_X, HITBOX_Y
from opp_model import (OpponentModel, A_ATTACK, A_BULLET, A_GUARD,
                       A_JUMP, A_DASH, A_ADVANCE, GUARD_ALL_IDS)
from skill_levels import hand_skill_availability, skill_levels_from_hand

HITBOX_X = 70.0
HITBOX_Y = 90.0

# R57(第十八轮2.5): 下段攻击ID表 — 段位是招式语义, 用权威ID表显式查表,
# 不用ID区间折半(2A=303与5A=300同//64桶, 区分只可能在语义层)。
# 语义源=docs/soku_action_ids.md(SokuLib Action.hpp权威枚举):
# 地面2系=蹲防必: 2A(303)/f2A(311)/2B(402)/2C(412)。
# 空中j2系(308/406/416)段位角色相关不纳入(保守); 3系(304/403)按中段。
LOW_ATTACK_IDS = frozenset((303, 311, 402, 412))

# R58(改进方案P1-a): f变体(远版A系)ID表 — 近/远A不可分是技法覆盖§2.4
# 盲区(300/301同//128桶)。语义源=docs/soku_action_ids.md: 小写f前缀=
# 射程外变体, 全集仅两个: f5A(301)/f2A(311)。(改进方案示例集含
# 321=5AAA/331=诹访子专属 — 按数据纪律"空表优于错表"只取权威两枚。)
# 自版位用于确认自身whiff射程; 对手版位=遠A警戒(帧数据与近A不同)。
F_VARIANT_IDS = frozenset((301, 311))

# 势函数参数(v2验证值)
VALLEY_MELEE = 110.0
VALLEY_SHOOT = 230.0

# 受击动作ID集(实证: _archive/train_rl.py:153 抓屏时代校准集) —
# "对手倒地"的正判据(P1-4a), 血量启发式只能表示"掉过血"
# R28修正(权威源SokuLib Action.hpp, docs/soku_action_ids.md):
# 受击/倒地/被投集 — 旧集混入214(=FLY飞行!)/404(j5B)/414(j5C)/416(j2C)/
# 503(技能空中B), 全是攻击/弹/飞非受击态(会把对手出弹当"倒地"误判起身窗)
HIT_ACT_IDS = {
    50, 51, 52, 53,             # 站立受击 小/中/大/特大
    56, 57, 58,                 # 站立受击第二套
    62, 63, 64,                 # 蹲姿受击
    70, 71, 72, 73, 74, 75, 76, 77, 78,   # 空中受击全级(含撞墙/击落)
    88, 89,                     # 将被砸地/已被砸地
    97, 98,                     # 倒地(弹跳/静止)
    100,                        # 被投技抓住
    143, 145,                   # 地面/空中被压溃
}

# 天气ID(v2实测表 hud_sensor.py WEATHER_NAMES; 与mod SokuLib/Weather.hpp枚举同源)
WEATHER_SEIRAN = 11   # 晴岚(Mountain Vapor)
WEATHER_AURORA = 19   # 极光
# 信息对称裁定(用户2026-09-22): 非想天则信息对称, 唯二例外=
#   晴岚: 双方卡牌内容不可识别 / 极光: 实际天气效果随机且隐藏。
# 2026-09-22第四轮审计事故修正: 原引ov_main.cpp(属SokuAIOfflinePlayer.dll血统,
# 非部署产物) — 实际部署的SokuAITrainer.dll(TrainingMod血统)当时无遮蔽。
# 已移植遮蔽进TrainingMod并重编部署(MD5 0BD2A843, build_tm.bat):
#   state.cpp: 晴岚时hand全0xFF+cardGauge=0xFFFF哨兵(unsigned short, 勿用-1)
#   network.cpp: 极光时activeWeather抹成极光本身
# 客户端纵深(哨兵判定, 兼容mod版本): gauge>=0xFF00或天气id=晴岚→视为遮蔽。


def gauge_feat(g):
    """卡槽归一(0~1); 晴岚哨兵0xFFFF(unsigned short线上值)→0"""
    return 0.0 if g >= 0xFF00 else min(1.0, max(0, g) / 500.0)


def fair_weather_id(weather):
    """信息公平天气id: displayed==极光时实际效果隐藏 → 以displayed为准"""
    if weather.get("displayed") == WEATHER_AURORA:
        return WEATHER_AURORA
    return weather["active"]


class FeatureBuilder:
    """每次决策调用build(); 每帧调用track_bullets()更新弹速。"""

    CORE_DIMS = 330  # R61t(F5): 308+8扩展one-hot(20角色全覆盖)
    #                # B(用户2026-10-07"开工B"): 316+14 = 对手风格感知段
    #                # [316..327]=对手已出技能卡槽位flag×12(100-111映射,
    #                #  跨角色统一槽位语义, 角色身份由one-hot消歧)
    #                # [328]=对手已出SC张数(/5)  [329]=对手已出系统卡张数(/10)
    #                # 仅"对手已打出过的卡"=对人类同样可见的合法信息

    def __init__(self, n_macros):
        self.n_macros = n_macros
        self.n_side = 2 * n_macros + self.CORE_DIMS
        self.opp = OpponentModel()
        self._prev_bullets = []      # [(x,y,img,act),...] 上帧弹表(最近邻差分)
        self._graze_events = 0
        # R14: 逐帧差分状态(own_vy/opp_vy) + guard/evasion计数
        self._prev_own_y = None
        self._prev_opp_y = None
        self._own_vy_ema = 0.0
        self._opp_vy_ema = 0.0
        self._guard_frames = 0
        self._evasion_count = 0       # 擦弹计数(奖励用)
        self._last_tti = None
        self._own_x_prev = None
        self._evasion_armed = False  # 规避奖励触发态
        # R16§0.1: 生产环境弹匹配计数(频率结论必须来自生产计数,非离线语料)
        self._um_frames = 0     # track_bullets调用帧数
        self._um_obs = 0        # 弹观测总数
        self._um_un = 0         # 未匹配弹数(速度记0的)
        self._um_zbox = 0       # 零速弹落入受击盒的(帧,弹)对数
        # R16§3: 尾部19维新段状态(动量EMA/滞空计数/动作历史/密度梯度)
        self._own_vx_m = self._dx_m = self._adx_m = 0.0
        self._mom_x_prev = self._mom_dx_prev = self._mom_adx_prev = None
        self._own_air_f = 0
        # R59-N2: _opp_air_f已删(R57后只更新不读取的新死变量)
        self._prev_my_cls = 0
        self._prev_my_cls2 = 0
        self._prev_grid = None
        # R17①: 技能等级追踪(从手牌卡ID推导, 检测消耗升级)
        self._skill_levels = [0, 0, 0, 0]   # [236系, 623系, 214系, 22系] 各0-2
        self._prev_hand = None                # 上一帧手牌(检测卡消耗)
        # B(风格估计器): 对手已出卡追踪初始
        self._opp_hand_prev = None
        self._opp_revealed_skill = np.zeros(12, dtype=np.float32)
        self._opp_revealed_sc = 0
        self._opp_revealed_sys = 0
        # R63(P2): 超出12槽位表的技能卡id计数(如patchouli 112-114) —
        # 不写特征但可诊断(原直接IndexError炸局)
        self._opp_skill_overflow = 0
        self._combo_chain = 0                 # 连续伤害帧计数(③连段组合子)
        self._char_name = None                # 角色名(skill_levels查表用)

    def reset_match(self):
        """局开始重置对手模型和弹速缓存。"""
        self.opp = OpponentModel()
        self._prev_bullets = []
        self._graze_events = 0
        # R14: 逐帧差分状态(own_vy/opp_vy) + guard/evasion计数
        self._prev_own_y = None
        self._prev_opp_y = None
        self._own_vy_ema = 0.0
        self._opp_vy_ema = 0.0
        self._guard_frames = 0
        self._evasion_count = 0
        self._last_tti = None
        self._opp_vx_ema = 0.0   # 第四轮审计: 对手速度EMA跨局泄漏修复
        self._own_x_prev = None
        self._evasion_armed = False
        # R16§0.1: 弹匹配计数跨局累积(全局频率统计, 不随局重置)
        # R16§3: 新增段状态(动量EMA/滞空计数) + R14遗留(_prev_my_cls/_prev_grid)
        # 原漏reset → 跨局泄漏
        self._own_vx_m = self._dx_m = self._adx_m = 0.0
        self._mom_x_prev = self._mom_dx_prev = self._mom_adx_prev = None
        self._own_air_f = 0
        self._prev_my_cls = 0
        self._prev_my_cls2 = 0
        self._prev_grid = None
        # R17①: 技能等级随局重置(每局从Lv1重新开始)
        self._skill_levels = [0, 0, 0, 0]
        self._prev_hand = None
        # B(风格估计器): 对手已出卡追踪 — 局内累积, 跨局清零
        self._opp_hand_prev = None
        self._opp_revealed_skill = np.zeros(12, dtype=np.float32)
        self._opp_revealed_sc = 0
        self._opp_revealed_sys = 0
        self._opp_skill_overflow = 0   # R63(P2): 超槽位技能id计数随局重置
        self._combo_chain = 0
        self._chain_gap = 0    # R17③: 连段间隔容忍计数

    def track_bullets(self, objs, own=None):
        """每帧调用: 差分弹速 → 返回 [(dir_,x,y,vx,vy), ...]
        R15: 去掉direction键过滤(R14审计§1: direction只有2值, 49%弹未匹配
        → 速度记0 → TTI=0伪威胁)。改为纯最近邻+距离门限(40px/帧)+单射约束。
        输出元组第0位保持direction(调用方已兼容)。
        own=我方数据包(可选): R16§0.1生产计数用(未匹配率+零速入盒频率)。
        R25(用户2026-10-02"复杂弹幕理解"): 并行表 self.bullet_kin[i] 与
        返回列表逐下标对齐(前缀切片保持对齐) = (ax, ay, turn, age, imgid):
        加速度/转向率(弧度每帧)/驻留帧数/弹型imageID — 供二次外推/
        地雷威胁/追踪判定。阈值类(地雷speed<0.5·age≥10, 追踪turn≥0.08)
        是传感器定义而非游戏常数, 标定后在此注明。"""
        out = []
        kin = []
        cur = []
        for o in objs[:48]:
            dir_, x, y = o[0], o[1], o[2]
            cur.append((x, y, o[6], dir_))
        _pv = getattr(self, "_bt_vel", None) or [None] * len(
            self._prev_bullets)
        _pa = getattr(self, "_bt_age", None) or [0] * len(
            self._prev_bullets)
        used_prev = set()
        um_un = 0
        vel_now = [None] * len(cur)
        for i, (cx, cy, cimg, cdir) in enumerate(cur):
            best_j, best_d = None, None
            for j, (px, py, _pimg, _pdir) in enumerate(self._prev_bullets):
                if j in used_prev:
                    continue
                d = (cx - px) ** 2 + (cy - py) ** 2
                if best_d is None or d < best_d:
                    best_d, best_j = d, j
            ax = ay = turn = 0.0
            age = 1
            if best_j is not None and best_d <= 1600.0:
                px, py = self._prev_bullets[best_j][0], \
                    self._prev_bullets[best_j][1]
                used_prev.add(best_j)
                vx, vy = cx - px, cy - py
                pv = _pv[best_j]
                age = _pa[best_j] + 1
                if pv is not None and (pv[0] or pv[1]) and (vx or vy):
                    ax, ay = vx - pv[0], vy - pv[1]
                    import math as _m
                    cross = pv[0] * vy - pv[1] * vx
                    dot = pv[0] * vx + pv[1] * vy
                    turn = abs(_m.atan2(cross, dot))
            else:
                vx, vy = 0.0, 0.0   # 新弹/无匹配(不参与威胁判定, R15)
                um_un += 1
                if own is not None and (
                        abs(cx - own["position.x"]) < HITBOX_X
                        and abs(cy - own["position.y"]) < HITBOX_Y):
                    self._um_zbox += 1
            vel_now[i] = (vx, vy)
            out.append((cdir, cx, cy, float(vx), float(vy)))
            kin.append((float(ax), float(ay), float(turn), int(age),
                        int(cimg or 0)))
        self.bullet_kin = kin
        self._bt_vel = vel_now
        self._bt_age = [age for (_ax, _ay, _t, age, _i) in kin]
        # R16§0.1生产计数(频率结论来自生产环境, 非离线分片)
        self._um_frames += 1
        self._um_obs += len(cur)
        self._um_un += um_un
        self._prev_bullets = cur
        return out

    def unmatched_stats(self):
        """R16§0.1: 返回并清零弹匹配统计 → (未匹配率, 零速入盒颗/帧, 帧数)。"""
        fr, ob, un, zb = self._um_frames, self._um_obs, self._um_un, self._um_zbox
        self._um_frames = self._um_obs = self._um_un = self._um_zbox = 0
        if fr == 0 or ob == 0:
            return 0.0, 0.0, 0
        return un / ob, zb / fr, fr

    def update_opp(self, dt_s, left, right, weather, opp_vx=0.0):
        """决策拍更新对手模型。P1-4修复:
        - opp_down 用对手受击动作ID集(原版传的自己的HP)
        - opp_vx 由外部差分传入(train_tm逐帧EMA; 原版硬编码0)
        B(风格估计器): 对手已出卡差分检测(与self._prev_hand己方先例
        同构 — 晴岚遮蔽期跳过, 防哨兵误报)。"""
        # B: 对手手牌差分 → 已出卡统计(合法信息: 打出过的卡可见)
        rh = right["hand"]
        gauge_sent = right["cardGauge"] >= 0xFF00
        seiran_b = weather.get("active") == WEATHER_SEIRAN or gauge_sent
        if self._opp_hand_prev is not None and not seiran_b:
            prev_set = self._opp_hand_prev
            cur_set = rh
            # 消失的卡id(每槽独立): prev有值且cur同槽变为0xFF或不同id
            for slot in range(5):
                pid = prev_set[slot * 2]
                cid = cur_set[slot * 2]
                if pid != 0xFF and pid != cid:
                    # R63(P2): 技能卡槽位表宽12 → 只覆盖id 100..111。
                    # 角色4(patchouli)的技能id为112/113/114(card_tables.py:7),
                    # 原 `self._opp_revealed_skill[pid - 100]` 直接
                    # IndexError(index 12/13/14 out of bounds) → 被 train_tm
                    # 的 except Exception 吞成"重建环境×5→退出码1"。
                    # 现: 超界不写(该槽位无法表示)并计数+首次告警 —
                    # 训练不中断, 缺口也不被静默隐藏。
                    if 100 <= pid < 100 + len(self._opp_revealed_skill):
                        self._opp_revealed_skill[pid - 100] = 1.0
                    elif 100 <= pid < 200:
                        self._opp_skill_overflow += 1
                        if self._opp_skill_overflow == 1:
                            print("[特征] 对手技能id=%d超出槽位表(width=%d)"
                                  " — 该卡不可表示(需扩表, R63P2)"
                                  % (pid, len(self._opp_revealed_skill)))
                    elif pid >= 200:
                        self._opp_revealed_sc += 1
                    else:
                        self._opp_revealed_sys += 1
        if not seiran_b:
            self._opp_hand_prev = rh

        # P1-4b修复(真): EMA存侧特征用(build的s[o+1]读这里)
        # R19 NaN防护: 非有限vx跳过(防递归EMA永久污染)
        if np.isfinite(opp_vx):
            self._opp_vx_ema = 0.8 * getattr(self, "_opp_vx_ema", 0.0) + 0.2 * opp_vx
        dx = abs(right["position.x"] - left["position.x"])
        # R20: hitlab实测防御ID集(5/8/151/158+旧估兼容) — 原{110-115}
        # 使真实防御全落"怠"桶, "情境:防"维恒0
        guard_ids = GUARD_ALL_IDS
        # 信息对称(P1-4e真接线): 遮蔽判定=天气id OR gauge哨兵(0xFFFF, mod
        # 0BD2A843起晴岚真发哨兵; 旧mod靠天气id兜底)。传None让EMA保持
        # 而非追0污染囤牌估计
        gauge_sent = right["cardGauge"] >= 0xFF00
        seiran = weather.get("active") == WEATHER_SEIRAN or gauge_sent
        rh = right["hand"]
        opp_cards = None if seiran else sum(
            1 for i in range(5) if rh[i * 2] != 0xFF)
        opp_gauge = None if seiran else right["cardGauge"]
        self.opp.update(dt_s,
                        bool(right["airBorne"]),
                        right["action"],
                        dx,
                        opp_vx,
                        right["spirit"],
                        opp_cards,
                        opp_gauge,
                        right["position.x"],   # P0-L: 绝对x(9情境+6段占据)
                        guard_ids,
                        bool(left["airBorne"]),
                        # P1-4a修复(真): 对手倒地=受击动作ID命中(HIT_ACT_IDS),
                        # 血量启发式只能表示"掉过血"≠"倒地"
                        right["action"] in HIT_ACT_IDS,
                        # R21: 对手角色名(train_tm接线) — classify查表分桶
                        getattr(self, '_opp_char', None))

    def check_graze(self, left, bullets, d_take):
        """擦弹检测: TTI<0.3秒(帧→秒转换) + 零承伤 + 有弹近身 + **非防御态** → +1。
        R19(审查2026-10-02): 窗口原18帧=0.29s, 使"<0.3s"恒真退化为
        incoming>0 — 窗口改GAME_FPS让TTI条件真正参与判定。
        R33(用户2026-10-02"防御刷分"): 原版不区分擦弹(主动位移穿过弹)与
        格挡(站不动挡弹) — 防御态HP不掉+d_take=0+弹接近=每颗被挡弹都
        误触graze(+0.40/颗, 上限20/局) — 远距站防对手射击=稳定刷分通道,
        与旧"空防刷分"同类。修复: 防御态(action 150-167)不触发graze。"""
        if d_take > 0:
            return 0
        if left.get("action", 0) in GUARD_ALL_IDS:
            return 0                 # 格挡≠擦弹(防刷分)
        tti, incoming = threat_predict(
            left["position.x"], left["position.y"], bullets, GAME_FPS)
        # P0-3修复: tti已是帧, 除以GAME_FPS(62)转秒再比较
        if tti is not None and tti / GAME_FPS < 0.3 and incoming > 0:
            self._graze_events += 1
            return 1
        return 0

    def check_evasion(self, left, d_take):
        """规避奖励: TTI触发 + 零承伤 + 位移脱离。"""
        # P0-3修复: tti已是帧, 除以GAME_FPS(62)转秒
        if self._last_tti is not None and self._last_tti / GAME_FPS < 0.3:
            self._evasion_armed = True
            self._own_x_prev = left["position.x"]
        if self._evasion_armed:
            if d_take > 0:
                self._evasion_armed = False
                return 0
            if self._own_x_prev is not None:
                disp = abs(left["position.x"] - self._own_x_prev)
                if disp > 80:
                    self._evasion_armed = False
                    # R19(审查2026-10-02): 观测维dim[o+2]读_evasion_count
                    # 但原版从不自增 → 恒0(奖励通道活, 观测维死)
                    self._evasion_count = getattr(self, '_evasion_count', 0) + 1
                    return 1
        self._last_tti = None
        return 0

    def build(self, left, right, weather, bullets):
        """构建侧特征向量(308维核心)。bullets = track_bullets返回的带速度弹表。"""
        s = np.zeros(self.CORE_DIMS, dtype=np.float32)
        o = 0

        # === 1. 核心标量 (16) ===
        dx = right["position.x"] - left["position.x"]
        dy = right["position.y"] - left["position.y"]
        adx = abs(dx)
        facing = 1.0 if left["direction"] > 0 else -1.0
        back_turned = 1.0 if (facing > 0) != (right["position.x"]
                                                > left["position.x"]) else 0.0
        vals16 = [
            left["spirit"] / 2000.0, right["spirit"] / 2000.0,
            # R17位置放大(用户2026-09-29): 原dx/1200, dy/600, adx/1200,
            # position/1240 — "万金油招式"根因=位置信号弱于动作偏好信号,
            # 放大2倍让网络"感受"位置差异足以改变决策
            np.clip(dx / 600.0, -1, 1), np.clip(dy / 300.0, -1, 1),
            np.clip(adx / 600.0, 0, 1),
            np.clip(left["position.x"] / 620.0, 0, 1),
            np.clip(1.0 - left["position.x"] / 620.0, 0, 1),
            left["hp"] / 10000.0, right["hp"] / 10000.0,
            facing, float(left["airBorne"]), float(right["airBorne"]),
            gauge_feat(left["cardGauge"]),
            min(left["score"], 2) / 2.0, min(right["score"], 2) / 2.0,
            fair_weather_id(weather) / 21.0,   # 极光时以displayed为准(信息公平)
        ]
        s[o:o + 16] = vals16
        # R57(第十八轮2.5): 删R49死变量 — _my_pose等四局部量计算后从未
        # 写入任何维度(真实写入在尾部pose区:705-712), 纯误导性死代码。
        o += 16

        # === 2. 动作类one-hot (16: 我8+敌8) ===
        # R57(第十八轮2.5): 删R49"//64低/高半区0.5标记" — 三重失效:
        # (a)门控128<=action<256覆盖的是受击/倒地段, 攻击区(300-598)
        #    从未命中过标记(注释宣称"攻击区"从未为真);
        # (b)(action//64)%2区分不了2A(303)与5A(300)(同//64=4);
        # (c)段位是招式语义(2系=下段), 不在ID区间折半里。
        # 段位感知改显式查表位(见LOW_ATTACK_IDS + 尾部_pp_off-2)。
        # 桶语义(//128): 0-127=待机/移动, 128-255=受击/倒地/防御,
        # 256-383=A系攻击, 384-511=B/C系+弹幕, 512-639=必杀/SC
        my_cls = min(left["action"] // 128, 7)
        s[o + my_cls] = 1.0
        opp_cls = min(right["action"] // 128, 7)
        s[o + 8 + opp_cls] = 1.0
        o += 16

        # === 3. 朝向 (2) ===
        s[o] = back_turned
        s[o + 1] = 0.0  # turn_recency由外部填
        o += 2

        # === 4. 位置带one-hot (14) — R17: 值从1.0提到1.5(位置信号放大) ===
        # R16§3修正: 原三段循环在i=0即break, 中段/高段永远不写(死区门禁抓出)
        s[o + (0 if left["position.x"] < 350
               else (1 if left["position.x"] < 850 else 2))] = 1.5
        s[o + 3] = 1.5 if left["airBorne"] and left["position.y"] > 150 else 0.0
        s[o + 4] = 1.5 if left["airBorne"] and left["position.y"] <= 150 else 0.0
        for i, (lo, hi) in enumerate([(0, 130), (130, 250), (250, 450), (450, 1300)]):
            if lo <= adx < hi:
                s[o + 5 + i] = 1.5
                break
        for i, (lo, hi) in enumerate([(-600, -200), (-200, -50), (50, 200), (200, 600)]):
            if lo <= dy < hi:
                s[o + 9 + i] = 1.5
                break
        # R16§3: [47]原为off-by-one死维(写13维却o+=14) — 填dy同高带
        # (|dy|<=50: 格斗最常见状态, 原四带漏掉[-50,50]区间)
        s[o + 13] = 1.5 if -50 <= dy <= 50 else 0.0
        o += 14

        # === 5. 速度资源 (4) ===
        # R14: own_vy/opp_vy 由逐帧差分计算(与opp_vx同源)
        # R19 NaN防护(审查2026-10-02): 递归EMA遇一帧坏数据(如position.y
        # 为NaN)会永久污染 — 非有限差分跳过更新(保留旧EMA)
        own_y = left["position.y"]
        opp_y = right["position.y"]
        if self._prev_own_y is not None:
            _dy_o = own_y - self._prev_own_y
            _dy_r = opp_y - self._prev_opp_y
            if np.isfinite(_dy_o):
                self._own_vy_ema = 0.8 * self._own_vy_ema + 0.2 * _dy_o
            if np.isfinite(_dy_r):
                self._opp_vy_ema = 0.8 * self._opp_vy_ema + 0.2 * _dy_r
        self._prev_own_y = own_y
        self._prev_opp_y = opp_y
        s[o] = float(np.clip(self._own_vy_ema / 10.0, -1, 1))
        s[o + 1] = float(np.clip(getattr(self, "_opp_vx_ema", 0.0) / 10.0, -1, 1))
        s[o + 2] = float(np.clip(self._opp_vy_ema / 10.0, -1, 1))
        s[o + 3] = right["spirit"] / 2000.0
        o += 4

        # === 6. 弹幕威胁: 近弹3+密度1+TTI 1+来袭1 (6) ===
        # R19: 近弹3按|Δx|真排序取最近(原按包序bullets[0:3], 注释与代码不符)
        # R25: bullet_kin并行表(段6/8共用; 前缀切片与bullets下标对齐)
        _kin = getattr(self, "bullet_kin", None) or [None] * len(bullets)
        tti, incoming = threat_predict(
            left["position.x"], left["position.y"], bullets, GAME_FPS)
        for i, b in enumerate(sorted(
                bullets, key=lambda bb: abs(bb[1] - left["position.x"]))[:3]):
            bd = abs(b[1] - left["position.x"])
            s[o + i] = np.clip(1.0 - bd / 400.0, 0, 1)
        s[o + 3] = min(1.0, len(bullets) / 20.0)
        s[o + 4] = (tti / GAME_FPS) if tti is not None else 1.0
        s[o + 5] = min(1.0, (incoming or 0) / 5.0)
        # R25: 地雷/追踪修正(用户"复杂弹幕理解") —
        # 地雷(近零速+驻留≥10帧=延迟弹): 线性TTI恒∞威胁全盲 → 近距雷
        # 按悲观短TTI(0.1s)计入s[o+4]并+1来袭;
        # 追踪弹(turn≥0.08弧/帧): 直线TTI高估 → 按dist/|v|悲观化
        _mine_tti = None
        _hom_tti = None
        for _bi, (_a, bx, by, bvx, bvy) in enumerate(bullets[:20]):
            _k = _kin[_bi] if _bi < len(_kin) else None
            if _k is None:
                continue
            _spd = (bvx * bvx + bvy * bvy) ** 0.5
            _dist = ((bx - left["position.x"]) ** 2
                     + (by - left["position.y"]) ** 2) ** 0.5
            if _spd < 0.5 and _k[3] >= 10 and _dist < 200:
                _mine_tti = 0.1 if _mine_tti is None else min(_mine_tti, 0.1)
            elif _k[2] >= 0.08 and _spd > 1.0:
                _t = (_dist / _spd / GAME_FPS) if _spd > 1e-6 else 1.0
                _hom_tti = _t if _hom_tti is None else min(_hom_tti, _t)
        if _mine_tti is not None:
            s[o + 4] = min(s[o + 4], _mine_tti)
            s[o + 5] = min(1.0, s[o + 5] + 1.0 / 5.0)
        if _hom_tti is not None:
            s[o + 4] = min(s[o + 4], _hom_tti)
        self._last_tti = tti
        o += 6

        # === 7. 威胁矢量网格 6×6=36 (P2-4修复: 密度30格+逼近度6格, 不重叠) ===
        gx_off = o
        close_speed = [0.0] * 6  # 每列的逼近度(独立6格)
        for _a, bx, by, bvx, bvy in bullets[:30]:
            rdx = bx - left["position.x"]
            rdy = by - left["position.y"]
            gx = int(np.clip((rdx + 600) / 200, 0, 5))
            gy = int(np.clip((rdy + 450) / 150, 0, 5))
            idx = gy * 6 + gx
            s[gx_off + idx] += 1.0
            # R19符号修正(审查2026-10-02): sign(rdx)是玩家→弹方向,
            # 弹沿该方向速度为负才是逼近 — 原版无负号, 把"飞离"当"逼近"
            # 计入(逼近弹恒0), 威胁特征整体反向
            closing = -(bvx * (1 if rdx > 0 else -1)
                        + bvy * (1 if rdy > 0 else -1))
            close_speed[gx] += max(0.0, closing)
        for i in range(30):
            s[gx_off + i] = min(1.0, s[gx_off + i])
        for i in range(6):
            s[gx_off + 30 + i] = min(1.0, close_speed[i] / 10.0)
        o += 36

        # === 8. 未来占据 t+15/t+30 (36: 2×18) ===
        # R19死区修复(审查2026-10-02): 外层守卫abs(fdy)<150下, 除数100使
        # (fdy+150)/100∈(0,3) → gy只达2, 行3/4/5共18维永不写入。
        # 除数100→50后(fdy+150)/50∈(0,6), 6行全可达。
        # R25: 二次外推(变速弹) — x+vt+½at², 加速度来自bullet_kin;
        # 弹幕判定二维(用户提醒: 勿忘纵向), fdy/gy全流程双轴。
        for horizon, base in [(15, 0), (30, 18)]:
            for _bi, (_a, bx, by, bvx, bvy) in enumerate(bullets[:20]):
                _k = _kin[_bi] if _bi < len(_kin) else None
                _ax, _ay = (_k[0], _k[1]) if _k else (0.0, 0.0)
                fx = bx + bvx * horizon + 0.5 * _ax * horizon * horizon
                fy = by + bvy * horizon + 0.5 * _ay * horizon * horizon
                fdx = fx - left["position.x"]
                fdy = fy - left["position.y"]
                if abs(fdx) < 200 and abs(fdy) < 150:
                    gx = int(np.clip((fdx + 200) / 67, 0, 2)
                             if abs(fdx) < 200 else 0)
                    gy = int(np.clip((fdy + 150) / 50, 0, 5)
                             if abs(fdy) < 150 else 0)
                    s[o + base + gy * 3 + gx] += 1.0
        for i in range(36):
            s[o + i] = min(1.0, s[o + i])
        o += 36

        # === 9. 卡牌感知 (22) ===
        hb = left["hand"]
        ids = [hb[i * 2] for i in range(5) if hb[i * 2] != 0xFF]
        sel = hb[0] if hb[0] != 0xFF else None
        s[o] = gauge_feat(left["cardGauge"])   # 晴岚哨兵0xFFFF→0
        s[o + 1] = len(ids) / 5.0
        # 选中卡one-hot 9(R38第九轮审计P2-5: 原`sel<8`按原始卡ID截断 —
        # 系统卡8~20/技能卡100+/符卡200+全落"空"桶, 与空手不可区分。
        # 改类型桶: [空|系统≤20|技能100+|符卡200+] + 5维保留位)
        if sel is None:
            s[o + 2] = 1.0
        elif sel <= 20:
            s[o + 3] = 1.0
        elif sel < 200:
            s[o + 4] = 1.0
        else:
            s[o + 5] = 1.0
        # 手牌构成one-hot 8(按系统/技能/SC类型桶)
        for cid in ids:
            if cid <= 20:
                s[o + 11] += 1.0
            elif 100 <= cid < 200:
                s[o + 12] += 1.0
            elif cid >= 200:
                s[o + 13] += 1.0
        s[o + 11] = min(1.0, s[o + 11] / 3.0)
        s[o + 12] = min(1.0, s[o + 12] / 3.0)
        s[o + 13] = min(1.0, s[o + 13] / 3.0)
        # 选中存在标志(未校验耗费 — 耗费表在训练层) + 敌公开量3
        s[o + 14] = 1.0 if sel is not None else 0.0
        s[o + 15] = gauge_feat(right["cardGauge"])  # 敌充能(晴岚哨兵→0)
        # R16§3: "16~21保留"6维死区 — 填对手空间感知(与P0-L场地三段同语义:
        # 350/850分界同段4, 角<120/>1120同旧opp_corner口径)
        # R17: 值从1.0提到1.5(位置信号放大, 与段4同步)
        s[o + 16 + (0 if right["position.x"] < 350
                    else (1 if right["position.x"] < 850 else 2))] = 1.5
        s[o + 19] = 1.5 if (right["position.x"] < 120
                            or right["position.x"] > 1120) else 0.0   # 对手贴角
        s[o + 20] = 1.5 if (left["position.x"] < 120
                            or left["position.x"] > 1120) else 0.0     # 我方贴角
        s[o + 21] = 1.5 if right["position.x"] < left["position.x"] else 0.0
        o += 22

        # === 10. 对手建模 (75: 基础27 + 历史40 + 资源8) ===
        opp_feats = self.opp.features()
        s[o:o + len(opp_feats)] = opp_feats
        o += len(opp_feats)

        # === 11. 对局适应: 角色one-hot 22 + 属性4 (26) ===
        # 对手角色ID从包里拿不到(同角色镜像) → 由外部注入
        s[o:o + 22] = 0.0  # opp_char_onehot(外部填)
        # R17①技能等级特征(用户2026-09-30): 利用one-hot保留位中的死维
        # [o+3..o+6] = 当前各技能槽等级/2 (0=Lv1, 0.5=Lv2, 1=Lv3)
        # [o+7..o+10] = 手牌中各槽升级卡可用性(0~1, 每张+0.5)
        # 槽位: 0=236系, 1=623系, 2=214系, 3=22系
        # R19注入契约(审查2026-10-02): 外部one-hot只允许[o..o+2](池序
        # 0/1/2), 严禁≥o+3 — 曾用角色id 9(suika)写[o+9]覆盖技能特征;
        # [o+11..o+19]留作角色池扩展(R51已占, 池序0-19=全20角色封顶
        # — 用户裁定: 非想天则有且仅有20角色, 22槽与roster恰好重合,
        # 零余量是有意设计); [o+20..o+21]=f变体位(R58)
        if self._char_name:
            # 更新技能等级(检测手牌卡消耗)
            hand = left.get("hand", b'\xff' * 10)
            if isinstance(hand, bytes):
                self._skill_levels = skill_levels_from_hand(
                    hand, self._skill_levels, self._prev_hand,
                    char=self._char_name)
                self._prev_hand = hand
                # 编码等级
                for _si in range(4):
                    s[o + 3 + _si] = self._skill_levels[_si] / 2.0
                # 编码手牌可用性
                avail = hand_skill_availability(hand, self._char_name)
                for _si in range(4):
                    s[o + 7 + _si] = avail[_si]
        # R16§3: 原4维硬编码0.5 proxy(恒定) — 改为对手风格份额(来自
        # 对手建模层的全局行为聚合, 随对局演化, 直接可用)
        _ot = 0.0
        _shares = [0.0] * 8
        for _ci in range(self.opp.N_CTX):
            for _bi in range(self.opp.N_ACT):
                _shares[_bi] += self.opp.ctx[_ci][_bi]
        _ot = sum(_shares)
        if _ot > 1e-6:
            s[o + 22] = min(1.0, (_shares[A_ATTACK] + _shares[A_BULLET]) / _ot)  # 攻击性
            s[o + 23] = min(1.0, _shares[A_GUARD] / _ot)                          # 防御倾向
            s[o + 24] = min(1.0, (_shares[A_JUMP] + _shares[A_DASH]) / _ot)       # 机动性
            s[o + 25] = min(1.0, _shares[A_ADVANCE] / _ot)                        # 压迫推进
        # R58(P1-a): f变体位(近/远A可分) — 段11原[o+11..o+21]留池扩展,
        # R51池序占[o+11..o+19], [o+20..o+21]空闲恰纳两枚(改进方案1.2
        # 原拟扩维316 — R57已在308内交付pose×4+下段位, 此处补齐fvariant
        # 即P1-a全量, 零迁移成本)
        s[o + 20] = 1.0 if left["action"] in F_VARIANT_IDS else 0.0
        s[o + 21] = 1.0 if right["action"] in F_VARIANT_IDS else 0.0
        o += 26

        # === 12. 势函数值 (4) ===
        # 双谷势: 近战谷110 + 射击谷230
        v_m = max(0.0, 1.0 - abs(adx - VALLEY_MELEE) / VALLEY_MELEE)
        v_s = max(0.0, 1.0 - abs(adx - VALLEY_SHOOT) / VALLEY_SHOOT)
        s[o] = v_m
        s[o + 1] = v_s
        s[o + 2] = v_m - v_s  # 谷差(择时信号)
        # 舞台控制势(telescoping: 离自己墙越远越好)
        # R19: clip防x越界(1240-x可为负)
        wall_dist = float(np.clip(
            min(left["position.x"], 1240.0 - left["position.x"]) / 620.0, 0, 1))
        s[o + 3] = wall_dist
        o += 4

        # === 13. 擦弹/防守/时间 (10) ===
        s[o] = min(1.0, self._graze_events / 10.0)
        # R14: guard/evasion计数(由update_opp中的检测状态累计)
        # R20: 实测防御ID集(原{110-115}恒不命中 → dim258死维)
        if left["action"] in GUARD_ALL_IDS:
            self._guard_frames += 1
        s[o + 1] = min(1.0, self._guard_frames / GAME_FPS)
        s[o + 2] = min(1.0, self._evasion_count / 10.0)
        s[o + 3] = min(1.0, left["comboDamage"] / 3000.0) if left["comboDamage"] else 0
        s[o + 4] = min(1.0, right["comboDamage"] / 3000.0) if right["comboDamage"] else 0
        s[o + 5] = min(1.0, left["untech"] / GAME_FPS) if left["untech"] else 0
        s[o + 6] = min(1.0, right["untech"] / GAME_FPS) if right["untech"] else 0
        s[o + 7] = float(left["timeStop"] > 0)
        s[o + 8] = float(left["hitStop"] > 0)
        s[o + 9] = min(1.0, (weather.get("timer") or 0) / 999.0)
        o += 10

        # === 14. 扩展特征 (R14: 填充之前全零的44维) ===
        # 14a. 弹幕速度矢量统计 (8): 平均速度+方向分布
        # R19: 未匹配弹(速度记0)速度未知 — 不计入均值/方向直方图
        # (原版被arctan2(0,0)=0伪造成"向右"计入bin0)
        _mb = [b for b in bullets[:20] if b[3] != 0.0 or b[4] != 0.0]
        if _mb:
            avg_bvx = sum(b[3] for b in _mb) / len(_mb)
            avg_bvy = sum(b[4] for b in _mb) / len(_mb)
            s[o] = np.clip(avg_bvx / 10.0, -1, 1)
            s[o + 1] = np.clip(avg_bvy / 10.0, -1, 1)
            # 弹幕方向分布(6方向one-hot)
            for b in _mb:
                ang = int(np.arctan2(b[4], b[3]) / np.pi * 3 + 3)  # -3..3→0..6
                ang = max(0, min(5, ang))
                s[o + 2 + ang] += 1.0
            for i in range(6):
                s[o + 2 + i] = min(1.0, s[o + 2 + i] / 5.0)
        o += 8
        # 14b. 己方动作历史 (8): 最近2次动作类one-hot(4+4)
        my_cls_now = min(left["action"] // 128, 7)
        prev1 = getattr(self, '_prev_my_cls', 0)
        prev2 = getattr(self, '_prev_my_cls2', 0)
        s[o + min(prev2 // 2, 3)] = 1.0  # 简化: 压缩到4档
        s[o + 4 + min(prev1 // 2, 3)] = 1.0
        self._prev_my_cls2 = prev1
        self._prev_my_cls = my_cls_now
        o += 8
        # 14c. 弹幕密度梯度 (6): 6列(左右方向)的密度变化趋势
        # R16§3修正: 原读s[gx_off+i]即网格第0行(玩家下方300~450px带, 生产罕见
        # → 段恒零, 由死区门禁行为测试抓出) — 改为真正的按列聚合
        cols = [0.0] * 6
        for _gy in range(6):
            for _gx in range(6):
                cols[_gx] += float(s[gx_off + _gy * 6 + _gx])
        if getattr(self, '_prev_grid', None) is not None:
            for i in range(6):
                delta = cols[i] - self._prev_grid[i]
                s[o + i] = np.clip(delta * 2.0, -1, 1)
        # 保存当前列密度
        self._prev_grid = cols
        o += 6
        # === 14e-i. R16§3: 尾部19维原为结构性死区(全零填充) — 填真实信号 ===
        # 14e. 位置交互(R17替换: 原自身三段one-hot与段4重复, 换成交互特征
        # — 用户2026-09-29: 放大位置组合的战术含义)
        own_corner = 1.0 if (left["position.x"] < 120
                             or left["position.x"] > 1120) else 0.0
        opp_corner = 1.0 if (right["position.x"] < 120
                              or right["position.x"] > 1120) else 0.0
        s[o] = own_corner * np.clip(1.0 - adx / 500.0, 0, 1)     # 我角+近=逃生紧迫
        s[o + 1] = opp_corner * np.clip(1.0 - adx / 500.0, 0, 1)  # 敌角+近=压制机会
        s[o + 2] = np.clip(dx / 300.0, -1, 1) * float(right["airBorne"])  # 对空方向距离
        o += 3
        # 14f. 动量 (3): own_vx EMA + dx EMA + |dx| EMA(逼近/拉开趋势)
        # R17③: combo_chain(连续伤害帧)作为属性暴露, 由train_tm在
        # 决策点读取→给攻击宏加bias(连段中偏好继续攻击而非重置)
        if getattr(self, '_mom_x_prev', None) is not None:
            # R19 NaN防护: 非有限差分跳过(同段5)
            _dx_o = left["position.x"] - self._mom_x_prev
            _dx_d = dx - self._mom_dx_prev
            _dx_a = adx - self._mom_adx_prev
            if np.isfinite(_dx_o):
                self._own_vx_m = 0.8 * getattr(self, '_own_vx_m', 0.0) \
                    + 0.2 * _dx_o
            if np.isfinite(_dx_d):
                self._dx_m = 0.8 * getattr(self, '_dx_m', 0.0) + 0.2 * _dx_d
            if np.isfinite(_dx_a):
                self._adx_m = 0.8 * getattr(self, '_adx_m', 0.0) + 0.2 * _dx_a
        self._mom_x_prev = left["position.x"]
        self._mom_dx_prev = dx
        self._mom_adx_prev = adx
        s[o] = float(np.clip(getattr(self, '_own_vx_m', 0.0) / 10.0, -1, 1))
        s[o + 1] = float(np.clip(getattr(self, '_dx_m', 0.0) / 10.0, -1, 1))
        s[o + 2] = float(np.clip(getattr(self, '_adx_m', 0.0) / 10.0, -1, 1))
        o += 3
        # 14g. 资源差 (3): 血差/灵差/gauge差(相对量, 核心标量只有绝对值)
        s[o] = float(np.clip((left["hp"] - right["hp"]) / 10000.0, -1, 1))
        s[o + 1] = float(np.clip((left["spirit"] - right["spirit"]) / 2000.0, -1, 1))
        s[o + 2] = float(np.clip(
            (gauge_feat(left["cardGauge"]) - gauge_feat(right["cardGauge"])), -1, 1))
        o += 3
        # 14h. 威胁补充 (4): 最大逼近速度/平均弹速模/最近弹距/高密度警报
        if bullets:
            _maxc = 0.0
            _mind = None
            _vmag = 0.0
            for _a, bx, by, bvx, bvy in bullets[:30]:
                _rdx = bx - left["position.x"]
                _rdy = by - left["position.y"]
                # R19符号修正: 同段7 — 逼近为正(原版反向)
                _cl = -(bvx * (1 if _rdx > 0 else -1)
                        + bvy * (1 if _rdy > 0 else -1))
                _maxc = max(_maxc, _cl)
                _bd = abs(_rdx)
                if _mind is None or _bd < _mind:
                    _mind = _bd
                _vmag += (bvx * bvx + bvy * bvy) ** 0.5
            s[o] = float(np.clip(_maxc / 10.0, 0, 1))
            s[o + 1] = float(np.clip(_vmag / len(bullets[:30]) / 10.0, 0, 1))
            s[o + 2] = float(np.clip(1.0 - (_mind or 0.0) / 400.0, 0, 1))
        s[o + 3] = 1.0 if len(bullets) > 10 else 0.0
        o += 4
        # 14i. 状态计时 (2) — R57(第十八轮2.5)重组:
        # 原14i宽6[302..307]=双方滞空+hitStop+低血警报, 但R49的pose尾部
        # 写入(固定304-307)自落地起一直在静默覆盖后4维 — hitStop/低血
        # 警报特征实际已死(值=pose)。本轮诚实化: 删除死写点, pose显式
        # 入账(14j), [303]改下段位(原对手滞空时长 — airBorne one-hot
        # 已在段2, 时长是次级信息; 段位盲区是技法覆盖L2核心缺口, 价值更高)。
        self._own_air_f = self._own_air_f + 1 if left["airBorne"] else 0
        s[o] = min(1.0, self._own_air_f / GAME_FPS)
        # R57(2.5): 对手下段攻击位 — 显式查表(段位是招式语义, 不在ID
        # 区间折半: 2A=303与5A=300同//64桶)。语义源=docs/soku_action_ids.md
        # (SokuLib权威): 地面2系=蹲防必(2A/f2A/2B/2C)。空中j2系段位角色
        # 相关不纳入(保守); 3系按中段。
        s[o + 1] = 1.0 if right["action"] in LOW_ATTACK_IDS else 0.0
        o += 2
        # 14j. R49 pose块 (4): [my_pose, opp_pose, my_poseFrame, opp_poseFrame]
        # (蓄力/段内进度可见; 原R49写尾静默覆盖14i后4维, R57移入账内)
        s[o] = min(left.get("pose", 0) or 0, 30) / 30.0
        s[o + 1] = min(right.get("pose", 0) or 0, 30) / 30.0
        s[o + 2] = min(left.get("poseFrame", 0) or 0, 100) / 100.0
        s[o + 3] = min(right.get("poseFrame", 0) or 0, 100) / 100.0
        o += 4
        # 14k. 剩余填充到旧core边界316(B前的CORE_DIMS — 保证B段
        # 固定起始316, 不受上方段宽调整漂移)
        assert o <= 316, \
            "侧特征溢出: o=%d > 旧core边界316" % o
        while o < 316:
            s[o] = 0.0
            o += 1

        # 14l. B(风格估计器) 对手已出卡段 (14): 固定[316..329]
        # [316..327]=技能卡槽位flag(100-111→0-11, 跨角色槽位统一)
        # [328]=SC已出/5  [329]=系统卡已出/10 — 仅"已打出过的卡"(合法)
        s[316:328] = self._opp_revealed_skill
        s[328] = min(1.0, self._opp_revealed_sc / 5.0)
        s[329] = min(1.0, self._opp_revealed_sys / 10.0)
        o = 330

        assert o <= self.CORE_DIMS

        return s

    def update_combo_chain(self, d_deal, opp_untech=0):
        """R17③修正(超长连段): 用对手untech判定连段持续, 而非仅看伤害帧.
        原版每帧无伤害即清零 — 5A命中→收招5帧→清零→6A命中又从1数起,
        跨宏连段链永远建不起来. 修正:
        - 伤害>0 → chain+1, gap清零
        - untech>0(对手在受击/浮空) → 链维持(不增不断)
        - untech=0 且 gap>10帧 → 链断(对手恢复行动)
        opp_untech: 包的right["untech"]字段(游戏帧数)"""
        if d_deal > 0:
            self._combo_chain = getattr(self, '_combo_chain', 0) + 1
            self._chain_gap = 0
        elif opp_untech and opp_untech > 0:
            pass   # 对手还在受击 — 链维持(收招帧/gap帧不断链)
        else:
            self._chain_gap = getattr(self, '_chain_gap', 0) + 1
            if self._chain_gap > 10:   # 10帧容忍(收招+决策延迟)
                self._combo_chain = 0
                self._chain_gap = 0
