# -*- coding: utf-8 -*-
"""演示 bot(时间轴状态机)。

M0 的决策器只是为了把闭环跑起来, 没有任何战术含量。
以后的强化学习策略只需替换 tick(): 输入观测(obs), 输出动作(按键)。
"""

from config import KEYMAP, ADVANCE_STEPS, RETREAT_STEPS
from macros import MACRO_NAMES


class ReactiveBot:
    """状态反射式专家(宏版): 输出宏 ID 而非按键。

    行为逻辑:
      远 → 前进(每~4s穿插跳跃/jB); 中距 → 5B 为主, 灵力满周期性 236B(必杀);
      贴身 → 5A/2A 交替; 被命中 → 后退; 对手丢失 → 前进(右侧探索)。
    """

    MELEE_DX = 150     # 世界坐标(≈2.2×屏标)
    SHOOT_DX = 280

    def __init__(self):
        self.t = 0.0
        self.next_jump = 5.0
        self.next_hj = 2.5       # 高跳周期: 远距掺入GRAZE位移
        self.next_shot = 2.2     # 远距弹幕周期: 灵梦弹幕全屏可达, 拆"前进洪流"先验(防熵塌缩)
        self.combo_i = 0         # 连段交替计数
        self.shot_i = 0          # 远距弹幕轮转计数

    def tick(self, dt, obs):
        """返回宏 ID(int)。obs: 攻略教学全集(立回/防御/擦弹/脱角/压制/连段/对空)。"""
        self.t += dt
        own = obs.get("own_x")
        opp = obs.get("opp_x")
        spr = obs.get("spirit", 1.0)
        opp_atk = obs.get("opp_attacking", False)
        name = lambda n: MACRO_NAMES.index(n)
        # 命中确认 → 民工连整套(攻略r1: 起手命中后伤害翻倍)
        if obs.get("hp_hit_recent"):
            self.combo_i += 1
            return name("连段A") if self.combo_i % 2 else name("连段B")
        # 对手在空中 → 对空教学(2026-09-08用户指正: 2B等优秀对空完全不用):
        # 主力=2B(地面斜上弹幕, 对空判定优), 近身=623B(升龙对空),
        # 辅以空对空jA(攻略r3立回分类) — 旧版只教jA/j6A是锚标签盲区
        if obs.get("opp_air"):
            if obs.get("close"):
                return name("623B") if int(self.t * 2.0) % 2 else name("2A")
            k = int(self.t * 2.0) % 3
            return [name("2B"), name("2B"), name("jA")][k]
        # 贴身且对手在出招 → 教防御(蹲防为主, 防2A/3A下段; 立防防中段)
        # (锚的防御侧: 无此标签时锚单边教进攻, 策略坍缩成无脑A)
        if obs.get("close") and opp_atk:
            return name("蹲防") if int(self.t * 2.5) % 3 else name("立防")
        # 被压墙区 → 教脱角(高跳跳出压制圈/后退走回中场), 不教"挂着挨磨"
        if obs.get("cornered"):
            return name("高跳") if int(self.t * 2.0) % 2 else name("后退")
        # 对手被压入角 → 教主动压制: 压制链/DA突进/体术链(少量防反击)
        if obs.get("opp_cornered"):
            if obs.get("close"):
                if opp_atk and int(self.t * 2.5) % 4 == 3:
                    return name("蹲防")            # 压制中留一手防对手反扑
                if int(self.t * 1.5) % 3 == 0:
                    return name("压制A")           # 2A-6A-2B-DA(攻略: 最强伪压)
                return name("2A") if int(self.t * 3.0) % 2 else name("5A")
            if own is not None and opp is not None and abs(opp - own) < 320:
                return name("DA") if int(self.t * 2.0) % 2 else name("5B")
            return name("前进")
        # 极近危险层 → 以防御为主(用户准则): TTI<18帧(弹速外推, 比距离更准)或弹距<110兜底
        # 此时唯一即时生效的应对是格挡, 禁止任何非无敌招式
        bn = obs.get("bullet_dist")
        tti = obs.get("tti")
        if (tti is not None and tti < 18) or (bn is not None and bn < 110):
            if obs.get("own_air"):
                return name("空防")
            # 墙区+弹幕地狱 → 穿墙逃逸(B案): 朝场地中心冲刺穿出弹幕墙 / 结界4交替,
            # 不教挂防(纯挂防=磨耗慢性死亡; 攻略: 角落擦弹逃逸是终极手段)
            if obs.get("cornered"):
                k = int(self.t * 2.0) % 3
                esc = name("后冲") if obs.get("corner_side", 1) > 0 else name("前冲")
                return [esc, name("结界4"), esc][k]
            return name("蹲防") if int(self.t * 2.5) % 3 else name("立防")
        # 空中+弹幕逼近 → 教空中擦弹(飞翔为主力, 空中冲刺为辅; 攻略g2/17: 空中GRAZE多用飞翔)
        if obs.get("own_air") and obs.get("bullet_near"):
            k = int(self.t * 2.0) % 3
            return [name("空翔前"), name("空翔后"), name("空冲后")][k]
        # 远弹 → 感知回避(TTI触发, 距离无关: 预测0.5秒内命中的弹无论远近都要让, 预警比弹距早)
        if tti is not None and tti < 45 and not obs.get("close"):
            return name("高跳") if int(self.t * 2.0) % 2 else name("后冲")
        if own is not None and opp is not None and abs(opp - own) >= self.SHOOT_DX:
            if self.t >= self.next_jump:
                self.next_jump = self.t + 4.0
                return name("jB")
            if self.t >= self.next_hj:
                self.next_hj = self.t + 3.0
                return name("高跳")
            # 远距弹幕为主(标准树r3/39: 布置弹幕渐进接近, 不直冲)
            if spr > 0.35 and self.t >= self.next_shot:
                self.next_shot = self.t + 1.2
                self.shot_i += 1
                if self.shot_i % 4 == 0 and spr > 0.8:
                    return name("236B")
                return name("5B") if self.shot_i % 2 else name("6B")
            return name("前进")
        # 标准树r3/40: 中距=空弹>66>打击基本形
        adx = abs(opp - own)
        if 250 < adx < self.SHOOT_DX:
            k = int(self.t * 2.0) % 3
            return [name("jB"), name("j6A"), name("DA")][k]
        if 130 <= adx <= 250:
            # 标准树r3/41: 近距=择时体术/防御
            if opp_atk:
                return name("蹲防")
            return name("5A") if int(self.t * 3.0) % 2 else name("2A")
        if obs.get("close"):
            return name("2A") if int(self.t * 2.5) % 2 else name("5A")
        if opp is None and own is None:
            return name("前进")
        if own is None and opp is not None:
            return name("前进")
        if own is not None and opp is None:
            return name("前进")
        adx = abs(opp - own)
        if adx >= self.SHOOT_DX:
            return name("前进")
        if adx >= self.MELEE_DX:
            if spr >= 0.8 and int(self.t * 2) % 4 == 3:
                return name("236B")
            return name("5B")
        return name("2A") if int(self.t * 2.5) % 2 else name("5A")


class DemoBot:
    """时间轴状态机(开环演示, 行为不依赖画面, 不适合做克隆目标)。"""

    def __init__(self):
        self.mode = "advance"
        self.i = 0
        self.t = 0.0

    def tick(self, dt, obs):
        """dt: 距上一帧的真实秒数; obs: {"hp_hit": bool}。
        返回本帧需要按住的虚拟键码列表。"""
        hp_hit = obs.get("hp_hit", False)
        if hp_hit and self.mode != "retreat":
            self.mode = "retreat"
            self.i = 0
            self.t = 0.0
        steps = ADVANCE_STEPS if self.mode == "advance" else RETREAT_STEPS
        dur, names = steps[self.i]
        self.t += dt
        if self.t >= dur:
            self.t = 0.0
            self.i += 1
            if self.i >= len(steps):
                self.i = 0
                self.mode = "retreat" if self.mode == "advance" else "advance"
        return [KEYMAP[n] for n in names]
