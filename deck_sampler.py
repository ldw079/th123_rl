# -*- coding: utf-8 -*-
"""R47卡组采样器(可行性报告天花板2): 训练局的deck从恒系统卡1-20
改为按角色合法卡池采样 — 技能卡(100+)/符卡(200+)入手激活整套
技能子系统(等级特征/SC宏门控/等级条件宏)。

来源: card_tables.py(解包CSV测量级) + mod侧isDeckValid白名单
(mod network.cpp: 每卡≤4张; 系统卡≤20; 技能卡100..112+; SC需在
角色合法表内)。

采样策略(课程化):
- 前期(前100局): 50%系统卡 / 50%混合(技能+SC入池)
- 后期: 20%系统卡 / 80%混合 — 给SC宏+技能升级足够的触发密度
"""
from __future__ import annotations

import collections
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from card_tables import CHAR_CARD_TABLES, SYSTEM_CARDS  # noqa: E402

# 系统卡合法id集合(mod: card<=20)
_SYSTEM_IDS = sorted(cid for cid, _n, _c in SYSTEM_CARDS)

# 每角色合法SC(200+)id — card_tables只含角色专属
_CHAR_SC_IDS = {}
_CHAR_SKILL_IDS = {}
for _cid, _cards in CHAR_CARD_TABLES.items():
    _CHAR_SC_IDS[_cid] = sorted(int(i) for i, _n, _c in _cards
                                if int(i) >= 200)
    _CHAR_SKILL_IDS[_cid] = sorted(int(i) for i, _n, _c in _cards
                                   if 100 <= int(i) < 200)

# mod侧技能上限: 112+帕秋莉3=115, 我们表内数据即白名单子集


def sample_deck(char_engine_id: int, rng: random.Random,
                mixed_ratio: float = 0.5) -> list:
    """采样一份20张卡组。

    mixed_ratio: 混合卡组概率(系统卡vs角色卡池).
    角色卡池: 技能卡池(每角色12张)+SC池(每角色8-15张)随机填充,
    技能:SC约3:1(升级路线比终结大招更需要密度).
    """
    if rng.random() > mixed_ratio:
        return list(_SYSTEM_IDS[:20])   # 纯系统卡(保证基础技能全解锁)

    skills = _CHAR_SKILL_IDS.get(char_engine_id, [])
    scs = _CHAR_SC_IDS.get(char_engine_id, [])
    if not skills and not scs:
        return list(_SYSTEM_IDS[:20])

    deck = []
    # 技能卡: 从12张池中抽4-6张各×3-4(升级路线密度)
    n_skill_types = rng.randint(4, min(6, len(skills)))
    for sid in rng.sample(skills, n_skill_types):
        deck.extend([sid] * rng.randint(3, 4))
    # SC: 从池中抽2-4张各×1-2 (R51修复: 上界用len(scs)而非len(skills))
    if scs:
        n_sc_types = rng.randint(2, min(4, len(scs)))
        for sid in rng.sample(scs, n_sc_types):
            deck.extend([sid] * rng.randint(1, 2))
    # R61f(F3, 从零审计"deck>4张边界"): 极端抽样6×4+4×2=32>20 —
    # 技能段可能被SC挤出(升级路线密度受损)。修: 先截20, 技能段天然
    # 在前保住; 且系统卡填充分支仅在<20时触发(原语义不变)。
    if len(deck) > 20:
        deck = deck[:20]
    # 填充系统卡到20
    while len(deck) < 20:
        deck.append(rng.choice(_SYSTEM_IDS))
    return deck[:20]


def curriculum_ratio(episode: int) -> float:
    """课程化混合比例: 前期50%混合→后期80%混合"""
    if episode < 100:
        return 0.5
    return min(0.8, 0.5 + (episode - 100) * 0.001)


# ==== D/C(用户2026-10-07"只做DCB"): 卡组原型 — 流派仪表+对抗性卡组池 ====

ARCHETYPES = ('system', 'skill', 'sc', 'mixed')
# task-35 stage1: 卡组条件化采样(env 默认0=旧行为; 先验文件缺省=无偏置)
_DECK_COND = os.environ.get('TH123_DECK_COND', '0') != '0'
_DECK_PRIOR = os.environ.get(
    'TH123_DECK_COND_PRIOR',
    r'D:\temp\th123_models\deck_cond_prior.json')
_COND_CACHE = {}
_COND_LOGGED = [False]


def sample_archetype_deck(char_engine_id: int, rng: random.Random,
                          archetype: str, sc_stats=None,
                          sys_stats=None) -> list:
    """原型卡组生成(合法约束同sample_deck: 每卡≤4/系统≤20/表内白名单)。
    system: 纯系统卡 | skill: 技能重(5-6种×3-4, 无SC)
    sc:     SC重(3-4种SC×2-3 + 2技能×2) | mixed: 标准混合(=sample_deck)
    L3(用户2026-10-07"sc和系统卡也细化"): sc/mixed内SC选择与系统卡填充
    均可按逐卡败率加权(sc_stats/sys_stats, league同源)。"""
    system = list(_SYSTEM_IDS[:20])
    if archetype == 'system':
        return system
    skills = _CHAR_SKILL_IDS.get(char_engine_id, [])
    scs = _CHAR_SC_IDS.get(char_engine_id, [])
    if not skills and not scs:
        return system
    if archetype == 'mixed':
        return sample_deck(char_engine_id, rng, 1.0)
    deck = []
    if archetype == 'skill':
        n = rng.randint(5, min(6, len(skills)))
        for sid in rng.sample(skills, n):
            deck.extend([sid] * rng.randint(3, 4))
    elif archetype == 'sc':
        for sid in rng.sample(skills, min(2, len(skills))):
            deck.extend([sid] * 2)
        for sid in _weighted_sample(scs, 3, rng,
                                    sc_stats):
            deck.extend([sid] * rng.randint(2, 3))
    else:
        raise ValueError('未知原型: %s (可用: %s)' % (archetype,
                                                    ARCHETYPES))
    if len(deck) > 20:
        deck = deck[:20]
    deck = _fill_system(deck, rng, sys_stats)
    return deck[:20]


def _card_weight(cid, stats):
    """L3: 单卡采样权重(league同源; 无统计=中性0.5, <3局=中性)。"""
    if not stats:
        return 0.5
    wl = stats.get(cid, [0, 0])
    if sum(wl) >= 3:
        from league import league_weight
        return max(0.1, league_weight(wl[0], wl[1]))
    return 0.5


def _weighted_sample(pool, n, rng, stats=None):
    """无放回加权抽n个(权重随stats, 无stats=均匀)。"""
    pool = list(pool)
    out = []
    for _ in range(min(n, len(pool))):
        ws = [_card_weight(c, stats) for c in pool]
        c = rng.choices(pool, weights=ws)[0]
        pool.remove(c)
        out.append(c)
    return out


def _fill_system(deck, rng, sys_stats=None):
    """系统卡填充(L3: 填充位可按逐卡败率加权 — 哪张系统卡基础能力强
    对我, 就多填哪张; 已有4张的卡不再填, 保每卡≤4)。"""
    cnt = collections.Counter(deck)
    while len(deck) < 20:
        cands = [c for c in _SYSTEM_IDS if cnt[c] < 4]
        if not cands:
            break
        if sys_stats:
            c = rng.choices(
                cands, weights=[_card_weight(x, sys_stats)
                                for x in cands])[0]
        else:
            c = rng.choice(cands)
        deck.append(c)
        cnt[c] += 1
    return deck


def archetype_of(deck) -> str:
    """卡组原型分类(C: 对手战绩按流派归桶用)。
    判据: 无角色卡=system; SC≥4且SC≥技能=sc; 技能≥10=skill; 余mixed。"""
    sc = sum(1 for c in deck if c >= 200)
    sk = sum(1 for c in deck if 100 <= c < 200)
    if sc == 0 and sk == 0:
        return 'system'
    if sc >= 4 and sc >= sk:
        return 'sc'
    if sk >= 10:
        return 'skill'
    return 'mixed'


def cond_arch_weights(my_id, opp_id):
    """task-35: (我,敌)角色对 → 流派先验权重 dict 或 None.

    先验格式: {str(my_id): {str(opp_id): {arch: weight}}} (由 deck_matchup
    分析工具生成; 缺省文件/缺项 → None = 无偏置).
    """
    if not _DECK_COND:
        return None
    if not _COND_LOGGED[0]:
        _COND_LOGGED[0] = True
        print('[deck_cond] ON prior=%s my=%s opp=%s'
              % (_DECK_PRIOR if os.path.exists(_DECK_PRIOR) else 'missing',
                 my_id, opp_id))
    if my_id is None or opp_id is None:
        return None
    try:
        import json
        import os as _os
        mt = _os.path.getmtime(_DECK_PRIOR)
    except OSError:
        return None
    tab = _COND_CACHE.get(mt)
    if tab is None:
        try:
            import json as _json
            tab = _json.load(open(_DECK_PRIOR, encoding='utf8'))
        except Exception:
            tab = {}
        _COND_CACHE.clear()
        _COND_CACHE[mt] = tab
    w = (tab.get(str(my_id)) or {}).get(str(opp_id))
    if not w:
        return None
    out = {a: float(w.get(a, 1.0)) for a in ARCHETYPES}
    print('[deck_cond] weights my=%s opp=%s weights=%s'
          % (my_id, opp_id, out))
    return out


def sample_deck_weighted(char_engine_id: int, rng: random.Random,
                         arch_stats=None, skill_stats=None,
                         sc_stats=None, sys_stats=None, cond=None):
    """C(对抗性卡组池): 对手卡组按我方各流派败率加权采样。
    arch_stats: {arch: [W, L]} — L1流派比例层(fictitious play)。
    skill_stats/sc_stats/sys_stats: {card_id: [W, L]} — L2/L3逐卡层
    (用户"流派不仅是SC占比,还有必杀类型" + "sc和系统卡也细化"):
    技能选择/SC选择/系统卡填充各自按逐卡败率加权。
    返回 (deck, archetype)。"""
    archs = list(ARCHETYPES)
    # 中性=0.5(league_weight同款约定) — 原中性1.0等于弱流派顶格权重,
    # 全败流派无法取得相对优势(测试2当场抓出)
    ws = []
    for a in archs:
        wl = arch_stats.get(a, [0, 0]) if arch_stats else [0, 0]
        if sum(wl) >= 3:
            from league import league_weight
            ws.append(max(0.1, league_weight(wl[0], wl[1])))
        else:
            ws.append(0.5)
    _cw = cond_arch_weights(*cond) if cond else None
    if _cw:
        ws = [w * _cw.get(a, 1.0) for a, w in zip(archs, ws)]
    arch = rng.choices(archs, weights=ws)[0]
    if arch == 'skill':
        return (_sample_with_skill_weights(char_engine_id, rng, arch,
                                           skill_stats, sys_stats), arch)
    if arch in ('sc', 'mixed'):
        return (sample_archetype_deck(char_engine_id, rng, arch,
                                      sc_stats, sys_stats), arch)
    return sample_archetype_deck(char_engine_id, rng, arch), arch


def _sample_with_skill_weights(char_engine_id, rng, arch,
                               skill_stats, sys_stats=None):
    """L2: 技能id加权选择的skill卡组(L3: 系统填充亦可加权)。"""
    skills = _CHAR_SKILL_IDS.get(char_engine_id, [])
    deck = []
    n_types = rng.randint(5, min(6, len(skills)))
    if skills:
        chosen = _weighted_sample(skills, n_types, rng, skill_stats)
        for sid in chosen:
            deck.extend([sid] * rng.randint(3, 4))
    if len(deck) > 20:
        deck = deck[:20]
    return _fill_system(deck, rng, sys_stats)[:20]


def sample_skillset_deck(char_engine_id: int, skill_ids,
                         rng: random.Random = None) -> list:
    """L2(D仪表): 固定必杀系别的对照卡组 — skill_ids为指定装备的
    技能卡id(每张×3-4), 无SC(纯系别对照), 余位系统卡填充。"""
    rng = rng or random.Random(0)
    skills = _CHAR_SKILL_IDS.get(char_engine_id, [])
    assert all(s in skills for s in skill_ids), \
        '技能id不在角色%s卡池: %r' % (char_engine_id, skill_ids)
    deck = []
    for sid in skill_ids:
        deck.extend([sid] * 3)
    while len(deck) < 20:
        deck.append(rng.choice(_SYSTEM_IDS))
    return deck[:20]


def skillset_key(deck) -> tuple:
    """L2签名(C归桶/D报告): 卡组内技能卡id的去重升序元组。"""
    return tuple(sorted({c for c in deck if 100 <= c < 200}))


def sample_solo_sc_deck(char_engine_id: int, sc_id: int,
                        rng: random.Random = None) -> list:
    """L3-D(用户"模型对哪一张sc应对不足"): 单SC聚焦对照卡组 —
    指定SC×3 + 2个技能×2 + 系统填充(隔离该SC的威胁变量)。"""
    rng = rng or random.Random(0)
    scs = _CHAR_SC_IDS.get(char_engine_id, [])
    skills = _CHAR_SKILL_IDS.get(char_engine_id, [])
    assert sc_id in scs, 'SC id不在角色%s卡池' % char_engine_id
    deck = [sc_id] * 3
    for sid in rng.sample(skills, min(2, len(skills))):
        deck.extend([sid] * 2)
    return _fill_system(deck, rng)[:20]


def sample_sysfocus_deck(sys_ids, rng: random.Random = None) -> list:
    """L3-D(系统卡细化): 系统卡聚焦对照卡组 — 指定系统卡各×4
    (每卡上限), 余位默认系统填充。"""
    rng = rng or random.Random(0)
    deck = []
    for c in sys_ids:
        deck.extend([c] * 4)
    return _fill_system(deck, rng)[:20]
