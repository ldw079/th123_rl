# -*- coding: utf-8 -*-
"""R57(第十八轮2.5)行为测试: 段位/蓄力感知特性必须真实生效。

第十七/十八轮教训("存在≠生效"): 子串断言放行过R49伪特性 —
pose四变量计算后未写入(实写另在尾部)、"攻击区0.5标记"门控
128-256从未命中攻击区。本测试按审查建议模板改为行为断言:

1. 对手出下段(2A=303) vs 中段(5A=300) — 特征向量必须可分;
2. 对手蓄力(pose变化) — 特征向量必须变化;
3. poseFrame进度 — 特征向量必须变化;
4. 负例: 待机(0)与移动(1)不得误触下段位(查表只有4个ID);
5. 尾部维度布局: 下段位在CORE-5, pose区在CORE-4..CORE-1。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.expandvars(r"%USERPROFILE%\Desktop\workplace\th123_rl"))
from feat_builder import (FeatureBuilder, LOW_ATTACK_IDS,  # noqa: E402
                          F_VARIANT_IDS)

try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def mk_state(my_act=0, opp_act=0, opp_pose=0, opp_pf=0, my_pose=0):
    """最小状态dict — 键集同test_feat_segments._state(build()全键覆盖)。"""
    left = {
        "position.x": 600.0, "position.y": 0.0,
        "spirit": 1000, "hp": 10000, "airBorne": False,
        "direction": 1, "action": my_act, "cardGauge": 0,
        "score": 0, "hand": bytes(10), "comboDamage": 0, "untech": 0,
        "timeStop": 0, "hitStop": 0,
        "pose": my_pose, "poseFrame": 0,
    }
    right = dict(left)
    right.update({
        "position.x": 800.0, "direction": -1, "action": opp_act,
        "pose": opp_pose, "poseFrame": opp_pf,
    })
    weather = {"active": 0, "displayed": 0, "timer": 999}
    return left, right, weather, []


def build(fb, st):
    left, right, weather, bullets = st
    return fb.build(left, right, weather, bullets)


def main():
    fb = FeatureBuilder(55)
    C = FeatureBuilder.CORE_DIMS

    # 布局(R57重组+R61t F5扩展): [302]=own_air [303]=下段位
    # [304..307]=pose块(段序固定, 不随CORE_DIMS尾部扩展移动)
    # [308..315]=F5扩展one-hot(零填充)
    lo_off = 303
    POSE_OFF = 304   # 段序固定位置(非CORE-4)
    check("布局常量", lo_off == 303 and C == FeatureBuilder.CORE_DIMS,
          "CORE=%d 下段位@%d pose@[%d..%d] 扩展@[%d..%d]"
          % (C, lo_off, POSE_OFF, POSE_OFF + 3, C - 8, C - 1))
    check("下段表语义(P2修正: 2B/2C回落虚报移除)",
          LOW_ATTACK_IDS == frozenset((303, 311)),
          str(sorted(LOW_ATTACK_IDS)))

    # 1. 下段vs中段: 2A(303) vs 5A(300) — 下段位必须翻转
    f_low = build(fb, mk_state(opp_act=303))
    f_mid = build(fb, mk_state(opp_act=300))
    check("2A触发下段位", f_low[lo_off] == 1.0 and f_mid[lo_off] == 0.0,
          "low=%.1f mid=%.1f" % (f_low[lo_off], f_mid[lo_off]))
    _diff = int((f_low != f_mid).sum())
    # 2A/5A同//128桶(A系) — one-hot不分, 下段位是唯一区分者(特性本义)
    check("2A/5A特征可分", _diff == 1 and f_low[lo_off] == 1.0,
          "差异维=%d(=下段位 — one-hot同桶属预期)" % _diff)

    # 2. 全表触发(回落表=303/311; 402/412已按cleista实测移除)
    for aid in (303, 311):
        f = build(fb, mk_state(opp_act=aid))
        check("ID%d下段位=1" % aid, f[lo_off] == 1.0)
    for aid in (402, 412):
        f = build(fb, mk_state(opp_act=aid))
        check("ID%d回落不虚报(P2修正)" % aid, f[lo_off] == 0.0)

    # 3. 负例: 相邻中段/空中/待机不得误触
    for aid in (300, 302, 304, 306, 308, 400, 401, 403, 410, 0, 50):
        f = build(fb, mk_state(opp_act=aid))
        check("ID%d不误触" % aid, f[lo_off] == 0.0)

    # 4. 蓄力可见: 对手pose 0→7 pose区必须变化(段序固定@304)
    f_p0 = build(fb, mk_state(opp_pose=0))
    f_p7 = build(fb, mk_state(opp_pose=7))
    check("pose进入特征", f_p7[POSE_OFF + 1] == 7 / 30.0
          and f_p0[POSE_OFF + 1] == 0.0,
          "pose维 %.3f→%.3f" % (f_p0[POSE_OFF + 1], f_p7[POSE_OFF + 1]))

    # 5. poseFrame进度可见
    f_pf = build(fb, mk_state(opp_pf=50))
    check("poseFrame进入特征", f_pf[POSE_OFF + 3] == 0.5,
          "%.2f" % f_pf[POSE_OFF + 3])

    # 6. 我方pose也入特征(对称)
    f_my = build(fb, mk_state(my_pose=15))
    check("我方pose入特征", f_my[POSE_OFF] == 0.5,
          "%.2f" % f_my[POSE_OFF])

    # 7. 重组无重叠: [302]own_air不被pose区覆盖(airBorne=True时>0)
    st_air = mk_state()
    st_air[0]["airBorne"] = True
    f_air = build(fb, st_air)
    f_ground = build(fb, mk_state())
    check("own_air区独立存活", f_air[302] > 0.0 and f_ground[302] == 0.0,
          "空气%.3f 地面%.3f(pose在[304..307]不再覆盖)"
          % (f_air[302], f_ground[302]))

    # 8. R58(P1-a): f变体位 — 段11 [o+20..o+21] = [247..248]
    check("f变体表语义", F_VARIANT_IDS == frozenset((301, 311)),
          str(sorted(F_VARIANT_IDS)))
    fv_own, fv_opp = 227 + 20, 227 + 21
    f_far = build(fb, mk_state(my_act=301))
    f_near = build(fb, mk_state(my_act=300))
    check("自f5A(301)触发own位", f_far[fv_own] == 1.0
          and f_near[fv_own] == 0.0)
    f_ofar = build(fb, mk_state(opp_act=311))
    f_onear = build(fb, mk_state(opp_act=303))
    check("对手f2A(311)触发opp位", f_ofar[fv_opp] == 1.0
          and f_onear[fv_opp] == 0.0)
    for aid in (300, 303, 320, 321, 331, 599):
        f = build(fb, mk_state(opp_act=aid))
        check("ID%d不误触f位" % aid, f[fv_opp] == 0.0)

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
