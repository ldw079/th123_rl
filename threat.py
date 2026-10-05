# -*- coding: utf-8 -*-
"""威胁预测: 弹速/方向线性外推 → 最早命中帧(TTI)与来袭计数。
用途: 侧输入风险感知 / 危险层判定(TTI替代距离) / 硬直窗口内选无保护招式的预知惩罚。
坐标系与 BulletSensor 同源(世界坐标, 弹速度单位=世界/游戏帧)。"""

HITBOX_X = 70.0     # 自身受击半宽(世界坐标, 估)
HITBOX_Y = 90.0     # 自身受击半高

# 教义(用户2026-09-21): 非想天则是62帧游戏 — 所有帧↔秒换算一律 /62, 禁用60
GAME_FPS = 62


def threat_predict(own_x, own_y, bullets, horizon_gf=GAME_FPS):
    """对每颗弹解包围盒相交的最早帧(闭式, 假设自身静止)。
    bullets: [(act,x,y,vx,vy), ...]  返回 (tti_min 或 None, horizon内命中数)。
    P0-3/P0-4/P0-4b修复(2026-09-23):
    - t0/t_end同时加下界>=0(已过界的弹不再计入)
    - 删除y>200过滤(游戏y轴地面=0向上为正, >200是高空弹不是UI)"""
    tti_min = None
    incoming = 0
    for _a, x, y, vx, vy in bullets:
        # R16-P0K: 零速弹(未匹配/静止)不参与威胁判定
        # — 实测行为测试: 零速+盒内→TTI=0伪威胁(行为级确证)
        if abs(vx) < 1e-6 and abs(vy) < 1e-6:
            continue
        # x 轴重叠窗口 [t1x, t2x]: |x+vx*t-own_x| < HITBOX_X
        dx = own_x - x
        if abs(vx) < 1e-6:
            if abs(dx) < HITBOX_X:
                t1x, t2x = 0.0, float(horizon_gf)
            else:
                continue
        else:
            r = vx / abs(vx)
            a = (dx - r * HITBOX_X) / vx    # 进入边界时间
            b = (dx + r * HITBOX_X) / vx
            t1x, t2x = (a, b) if a <= b else (b, a)
        # y 轴重叠窗口
        dy = own_y - y
        if abs(vy) < 1e-6:
            if abs(dy) < HITBOX_Y:
                t1y, t2y = 0.0, float(horizon_gf)
            else:
                continue
        else:
            r = vy / abs(vy)
            a = (dy - r * HITBOX_Y) / vy
            b = (dy + r * HITBOX_Y) / vy
            t1y, t2y = (a, b) if a <= b else (b, a)
        t0 = max(t1x, t1y)
        t_end = min(t2x, t2y)
        # P0-4修复: t_end>0(窗口延伸到未来才计入; t0>=0不取负TTI)
        if t0 <= t_end and t0 < horizon_gf and t_end > 0:
            t0 = max(0.0, t0)  # 钳位到0(弹已重叠时TTI=0而非负)
            incoming += 1
            if tti_min is None or t0 < tti_min:
                tti_min = t0
    return tti_min, incoming
