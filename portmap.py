# -*- coding: utf-8 -*-
"""端口段地图(第六轮审计§3): 显式划分, 段间不重叠, 门禁C12静态校验。
背景: train_tm异常重建端口=base+100+ep 曾与外环/实验实例撞段, 且
SO_REUSEADDR在Windows上允许双活绑定 — 撞击不报错, 直接串流。
D4修复(从零审查): 原10宽×slot布局下slot=2/3越段撞eval — 12宽×4道+域校验。
R19(审查2026-10-02): 域校验原只查"base落段内", 从不模拟tm_env的车道内
行走 — 12宽道×10宽行走必然重叠9口且slot3越入eval段7口。改为枚举
**真实绑定集合**(整条车道), 两两相交即红。
"""

LANE_W = 12   # rebuild车道宽(12宽×4道=48, 恰填满train_rebuild 50口)

SEGMENTS = {
    # 三角色训练主端口: 20800/20810/20820起, 各自10宽车道内环回
    "train_main":   (20800, 20849),
    # 训练器异常重建: 12宽×4道(slot0-3)
    "train_rebuild": (20850, 20899),
    # 外环matchup评估(EVAL_PORT=20900)
    "eval":         (20900, 20919),
    # 命中实验室(hitlab)
    "hitlab":       (20920, 20939),
    # 自对弈实验分叉(reimu_exp等)
    "exp":          (20940, 20959),
    # 一次性探针(masking probe等)
    "probe":        (20960, 20999),
    # R56(fleet): 车队段 — 16车道×10宽(21000-21159) + learner保留(21160-21299)
    "fleet":        (21000, 21299),
}

FLEET_LANE_W = 10   # fleet车道宽(10宽×16道=160口)
FLEET_MAX_ACTORS = 16


def fleet_lane(actor_id):
    """fleet actor的车道(lo, hi) — 与train_main同宽10口。"""
    lo = SEGMENTS["fleet"][0] + actor_id * FLEET_LANE_W
    hi = lo + FLEET_LANE_W - 1
    assert hi < SEGMENTS["fleet"][0] + 16 * FLEET_LANE_W, \
        "fleet车道越段: actor=%d hi=%d" % (actor_id, hi)
    return lo, hi


def fleet_port(actor_id, ep=0):
    """fleet actor的端口(车道内取值; 越段assert拒绝)。"""
    lo, hi = fleet_lane(actor_id)
    p = lo + (ep % FLEET_LANE_W)
    assert lo <= p <= hi, "fleet_port越段: %d" % p
    return p


def rebuild_lane(slot):
    """slot的rebuild车道(lo, hi) — tm_env行走被锚定在此车道内环回。"""
    lo = SEGMENTS["train_rebuild"][0] + (slot or 0) * LANE_W
    return lo, lo + LANE_W - 1


def rebuild_port(slot, ep):
    """训练器异常重建端口(车道内取值; 越段assert拒绝)"""
    lo, hi = rebuild_lane(slot)
    p = lo + (ep % LANE_W)
    assert lo <= p <= hi, "rebuild_port越段: %d" % p
    return p


# G2(R77, 接口常量化): 工具端口单一事实源 — 原各工具字面量+手写段注释
# 已漂移(branch_demo 20935注释"eval段"实为hitlab)。改动段划分时这里
# 的check_reserved会红(门禁C12消费), 不再靠人眼对表。
RESERVED = {
    "branch_demo":       ("hitlab", 20935),
    "habit_punish_demo": ("hitlab", 20936),
    "human_match":       ("probe", 20975),
    "human_solo_oracle": ("probe", 20970),
    "expert_harvest":    ("probe", 20971),
    # BH-4.2并行采集worker(2026-10-16用户指令多rep并行): 4路切片
    "expert_harvest_w0": ("probe", 20981),
    "expert_harvest_w1": ("probe", 20982),
    "expert_harvest_w2": ("probe", 20983),
    "expert_harvest_w3": ("probe", 20984),
    # P1-9(从零#4): danger_reveal真实模式启动即KeyError — 新工具注册
    # 端口时只改调用方未改表(单源表的两半不同步)
    "danger_reveal":     ("probe", 20976),
}


def reserved_port(name):
    """RESERVED访问器(返回int端口号) — R77b: G2首版把(段,端口)元组
    整个赋给PORT, TrainerClient.bind当场TypeError(15局人测数据
    首轮处理全灭的教训 — 收敛到单一访问点, 类型错无处可犯)."""
    seg, port = RESERVED[name]
    assert isinstance(port, int), "RESERVED[%r]端口非int: %r" % (name, port)
    return port


def check_reserved():
    """RESERVED各端口必须落在其声明段内(漂移即红)。"""
    for name, (seg, port) in RESERVED.items():
        lo, hi = SEGMENTS[seg]
        if not lo <= port <= hi:
            return False, "%s: %d不在%s段%s" % (name, port, seg, (lo, hi))
    return True, ""


def check_disjoint():
    segs = sorted(SEGMENTS.values())
    for (a1, a2), (b1, b2) in zip(segs, segs[1:]):
        if a2 >= b1:
            return False, "重叠: %s-%s" % (a1, b1)
    return True, ""


def check_rebuild_domain(slots=(0, 1, 2, 3), eps=range(200)):
    """R19: 枚举每个slot的**真实绑定集合**(整条车道, 含tm_env行走可达的
    每个口), 断言: ①两两不相交 ②不触train_rebuild以外的任何段。
    原版只查rebuild_port单点落段 — 12宽道+10宽行走的重叠逃过校验。"""
    lo, hi = SEGMENTS["train_rebuild"]
    lanes = {}
    for s in slots:
        lanes[s] = set(range(*rebuild_lane(s))) | {
            rebuild_lane(s)[0] + (e % LANE_W) for e in eps}
        for p in lanes[s]:
            if not (lo <= p <= hi):
                return False, "slot=%d 车道口%d越出train_rebuild" % (s, p)
    ls = sorted(lanes.values(), key=lambda x: min(x))
    for a, b in zip(ls, ls[1:]):
        ov = a & b
        if ov:
            return False, "slot车道重叠: %s" % sorted(ov)[:6]
    return True, ""
