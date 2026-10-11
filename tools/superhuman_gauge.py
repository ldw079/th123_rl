# -*- coding: utf-8 -*-
"""R63(F6): 超人距离度量 — 把"占位读数"换成**有定义、有区间、有真实人类锚**的度量。

## 为什么重写(审查结论)

原实现(`eval_matrix.analyze`)只有一行:

    metric = top['avg_wr'] - top['var']

三个致命问题:
1. **量纲不对**: `var` 是"胜率的标准差", `avg_wr` 是"胜率"。用一个胜率的
   方差去减一个胜率, 没有统计意义, 也没有上界/下界可比性;
2. **不是"超人距离"**: 它度量的是"该角色在**自己人打自己人**的对手池里
   赢得是否均匀", 既不含任何基准(人类/COM/满分), 也不含"离超人还有多远"
   的参照点。项目文档把它记为"占位口径"是准确的;
3. **小样本不自知**: 4 局的方差与 400 局的方差被同等对待; 1W-0L 与
   50W-0L 的胜率都记为 100%。

## 现在给的是什么(三件可证伪的东西)

以**人机同口径**为原则, 只报能被曲解之前就先自我限定好的量:

1. `dominance` — **最差对位下界**(Wilson 95% 下界的最小值)。
   传统评估"平均胜率"会把弱对位平均掉; 超人应表现为"**没有弱对位**",
   所以取"最差那个对位的保守下界"。样本不足的对位进入 `insufficient`
   而不是被当成 0 或忽略。
   ⚠ 注意: 同架构模型互打得出的对位胜率**度量的是对手/池强度, 不是角色
   或策略的绝对强度**(同一算法在两侧 → 自身镜像≈50%, 且该矩阵的
   "排名"不能读作角色强弱)。故本工具把它标为"对抗池广度", 并给出
   单侧(our_side)口径供 `--side-a` 使用。

2. `human_anchor` — **真实人类锚**(来自 `data/oracle/shards`, 对战网络
   重放, 191 局): 逐角色胜率 + 逐对位胜率, 全部带 Wilson 区间。
   这是项目里**唯一**的真人数据, 此前从未接线。

3. `grading` — 把两个量放在一起, 但**只在同口径时才给"距离"**:
   人-人胜率 与 模型-模型胜率 **不可相减**(对手不同), 该情形下
   `comparable=False` 并给出原因, 而不是硬造一个数字。

## 为什么"人类 vs COM"这个最理想的锚没有做

最干净的超人判据是"模型对 COM 的胜率 − 人类对 COM 的胜率"。项目**没有**
"人类打 COM"的数据(0 局), 只有人-人对战重放。要造这个锚必须真人上机,
脚本无法生成 —— 因此这里如实留空并标注需要什么, 而不是拿人-人数据
去冒充。代码留了 `HumanBaseline.from_com_log()` 的接线点(读
`docs/com_ladder_log.md` 形态的实测记录)。

## 用法

    from tools.superhuman_gauge import gauge_from_matrix, load_human_baseline
    rep = gauge_from_matrix(matrix, chars)          # 纯离线, 不需要游戏
    print(rep['dominance']['worst_lower'], rep['human_anchor']['chars'])
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

STORE = os.environ.get('TH123_STORE', r'D:\temp\th123_models')

# engine 角色id → 名字(与 train_tm.CHAR 同源; 此处自带一份以保持
# 本模块零依赖/可离线导入 — 拿不到 train_tm 时仍能算人类锚)
CHAR_BY_ID = {
    0: 'reimu', 1: 'marisa', 9: 'suika', 2: 'sakuya', 4: 'patchouli',
    7: 'yuyuko', 10: 'reisen', 12: 'komachi', 14: 'tenshi', 3: 'alice',
    5: 'youmu', 6: 'remilia', 8: 'yukari', 11: 'aya', 13: 'iku',
    15: 'sanae', 16: 'cirno', 17: 'meiling', 18: 'utsuho', 19: 'suwako',
}

Z95 = 1.959963984540054   # 正态 97.5% 分位(Wilson 用)

# ---------------------------------------------------------------- 已知标尺事实
# R63(F6): **用户实测口径(2026-10-07)** —— "真人对 COM 的胜率是百分之百,
# COM 的水平远逊于真人"。
#
# 这条事实对度量的意义是决定性的: **COM 在天花板处不可分辨**。
# 若强真人打 COM 恒 100%, 那么"模型打 COM 的胜率"就退化成一个上界已封顶的
# 标尺 —— 它只能证明"模型低于人类"(打 COM 输), 无法区分"人类水平"与
# "超人水平"(两者都是 100%)。所以:
#   · 距离度量的**分母不能是 COM**;
#   · 与 COM 的比较只保留一个诊断含义: "模型是否已低于人类下限";
#   · 真正的超人判据必须用**能区分的对手**: 人-人相对强度, 或人 vs 模型直接对打。
#
# 记录为常量而非注释, 以便报告/门禁引用同一份事实(可被后续真实测量覆盖)。
COM_VS_HUMAN = {
    'human_wr': 1.0,
    'source': '用户实测(2026-10-07): "真人对COM胜率百分之百, COM远逊于真人"',
    'implication': ('COM 在天花板处饱和 → 不能作为超人距离的分母/标尺; '
                    '只能用于"是否已低于人类下限"的诊断'),
    'discriminates_at_top': False,
}


def com_ruler_verdict(model_wr, human_wr=None, n_games=0, near=0.05):
    """给定"模型 vs COM"胜率, 判定该标尺此刻能说什么、不能说什么。

    near: "已贴近人类读数"的阈值(下界 ≥ 人类值 − near 即认为未观测到低于)。
    返回 dict: 判定 + 能得出的结论 + **不能**得出的结论(防误读)。
    """
    hw = COM_VS_HUMAN['human_wr'] if human_wr is None else float(human_wr)
    mw = None if model_wr is None else float(model_wr)
    out = {
        'model_wr': mw, 'human_wr': hw, 'games': int(n_games),
        'ruler_saturated': True,
        'can_conclude': [], 'cannot_conclude': [],
    }
    if mw is None or n_games <= 0:
        out['verdict'] = 'no_data'
        out['can_conclude'].append('无数据 — 不判定')
        return out
    lo, hi = wilson(int(round(mw * n_games)), n_games)
    out['model_ci'] = [lo, hi]
    if hi < hw:
        out['verdict'] = 'below_human_floor'
        out['can_conclude'].append(
            '模型对COM上限%.3f < 人类%.3f → **低于人类下限**(确定)' % (hi, hw))
    elif lo >= hw - near:
        # 注: 双侧Wilson的hi上限恒为1.0, 故 `lo >= hw`(hw=1.0时) **不可能**
        # 成立 —— R63自测抓出的死分支。改用"下界是否已贴近人类读数"判定,
        # 这样该分支可达且语义明确(样本足够大时才敢说"未观测到低于人类")。
        out['verdict'] = 'at_or_above_human_on_saturated_ruler'
        out['can_conclude'].append(
            '模型对COM下界%.3f 已贴近人类%.3f(差≤%.2f) → 本标尺上'
            '**未观测到低于人类**' % (lo, hw, near))
        out['cannot_conclude'].append(
            '**不能**据此称超人: 人类打COM已是100%, 该标尺在此处无分辨力')
    else:
        out['verdict'] = 'indistinguishable_from_human'
        out['can_conclude'].append(
            '区间[%.3f,%.3f]与人类值%.3f重叠 → 与人类水平**不可区分**'
            '(样本不足, 或标尺已饱和致无法分辨)' % (lo, hi, hw))
    out['cannot_conclude'].append(
        '任何"比人类强多少"的量化 — 需要能区分顶端的对手(人-人相对强度, '
        '或人 vs 模型直接对打)')
    return out


# ---------------------------------------------------------------- 统计基础

def wilson(k, n, z=Z95):
    """二项比例的 Wilson 得分区间 → (low, high)。n=0 → (0.0, 1.0)。

    Wilson 而非 Wald: 小样本/极端比例(0%与100%)下 Wald 区间会越界或宽度为0,
    而评估前期几乎全是"3局全胜"这类极端值 — 用 Wald 会把噪声读成超人。

    边界显式钳制: k=0/k=n 时闭式解存在 ±1e-17 级的浮点残差(实测
    wilson(0,3) 下界 = 4.868e-17 而非 0)。残差会让"最差对位下界"永远
    >0 并与 ==0.0 的比较失效, 故按定义钉死端点。
    """
    n = int(n)
    k = int(k)
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1.0 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(max(0.0, p * (1 - p) / n + z * z / (4 * n * n)))
    lo = (c - h) / d
    hi = (c + h) / d
    # 端点按定义钉死: k=0 → lo 恰为 0(闭式解有 1e-17 级残差);
    # k=n → hi 恰为 1。残差会让"最差对位下界"永远 >0 且 ==0 比较失效。
    if k <= 0:
        lo = 0.0
    if k >= n:
        hi = 1.0
    return (0.0 if lo < 0.0 else min(1.0, lo),
            1.0 if hi > 1.0 else max(0.0, hi))


def wilson_lower(k, n, z=Z95):
    return wilson(k, n, z)[0]


def wilson_upper(k, n, z=Z95):
    return wilson(k, n, z)[1]


def rate(k, n):
    """点估计 + 区间 + 样本量。n=0 → wr=None(不冒充0)。"""
    n = int(n)
    k = int(k)
    lo, hi = wilson(k, n)
    return {
        'wins': k, 'games': n,
        'wr': (k / n) if n else None,
        'lo': lo, 'hi': hi,
        'note': ('无样本' if n == 0 else None),
    }


def _merge(a, b):
    """合并两个计数(用于多对口位汇总)。"""
    return {'wins': a['wins'] + b['wins'], 'games': a['games'] + b['games']}


def _finalize(cnt):
    return rate(cnt['wins'], cnt['games'])


# ---------------------------------------------------------- 人类锚(重放数据)

def human_baseline_path():
    return os.path.join(ROOT, 'data', 'human_baseline.json')


def export_human_baseline(baseline=None, path=None):
    """把人类锚导出为**小派生档**(只含汇总结论, 不含重放原文)。

    存在的理由: 变异沙箱(gate_selftest)不带 191 份重放 shard(约200MB),
    但 F6 的锚断言需要在沙箱内也成立 → 导出档随源码树走(几十KB),
    沙箱里读到完全相同的汇总结论。重放原文仍是**唯一真值源**, 导出档
    可用 `--rebuild` 随时重建。
    """
    b = baseline if baseline is not None else load_human_baseline(_from_cache=False)
    p = path or human_baseline_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf8') as f:
        json.dump(b, f, ensure_ascii=False, indent=1, sort_keys=True)
    return p


def load_human_baseline(shard_glob=None, verbose=False, _from_cache=True):
    """读人类真人基线。优先**派生导出档**(快/沙箱可用), 无则从重放原文重算。

    数据源: `data/oracle/shards/*.npz` — 真人网络对战重放。每局 meta 含
    char_x/char_y 与 `score_final`(X视角回合比分) → 每局胜负 →
    逐角色 / 逐对位胜率 + Wilson 区间。

    返回 dict:
      chars      {name: rate}
      matchups   {'a|b': rate}   (a=该局X方视角的胜率)
      n_matches  可用局数
      sources    读取的文件数(导出档路径时为0)
      caveat     口径说明(必须原样展示给使用者)
      origin     'export' | 'shards'
    """
    if _from_cache and shard_glob is None:
        p = human_baseline_path()
        if os.path.exists(p):
            try:
                with open(p, encoding='utf8') as f:
                    d = json.load(f)
                if isinstance(d, dict) and d.get('chars'):
                    d['origin'] = 'export'
                    if verbose:
                        print('[human-baseline] 派生档 %s (%d局)'
                              % (os.path.basename(p), d.get('n_matches', 0)))
                    return d
            except Exception:
                pass
    pat = shard_glob or os.path.join(ROOT, 'data', 'oracle', 'shards', '*.npz')
    files = sorted(glob.glob(pat))
    per_char = {}
    per_mu = {}
    n_ok = 0
    for f in files:
        try:
            import numpy as np
            d = np.load(f, allow_pickle=True)
            m = json.loads(str(d['meta']))
            d.close()
        except Exception:
            continue
        if m.get('err') or m.get('score_final') is None:
            continue
        sf = m['score_final']
        if len(sf) < 2 or sf[0] == sf[1]:
            continue          # 平分/无比分 = 不可判, 不计(不硬猜)
        x = CHAR_BY_ID.get(m.get('char_x'))
        y = CHAR_BY_ID.get(m.get('char_y'))
        if x is None or y is None:
            continue
        xw = sf[0] > sf[1]
        n_ok += 1
        for nm, won in ((x, xw), (y, not xw)):
            c = per_char.setdefault(nm, {'wins': 0, 'games': 0})
            c['games'] += 1
            c['wins'] += 1 if won else 0
        key = '%s|%s' % (x, y)
        c = per_mu.setdefault(key, {'wins': 0, 'games': 0})
        c['games'] += 1
        c['wins'] += 1 if xw else 0
    out = {
        'chars': {k: _finalize(v) for k, v in per_char.items()},
        'matchups': {k: _finalize(v) for k, v in per_mu.items()},
        'n_matches': n_ok,
        'sources': len(files),
        'source_pattern': pat,
        'origin': 'shards',
        'caveat': ('真人 vs 真人 网络对战重放。是**唯一**真人数据; '
                   '与"模型 vs 模型"胜率**不可相减**(对手不同), '
                   '仅作人类水平的量级参照与逐对位基线。'),
        'missing_for_ideal_gauge': (
            '缺少"真人 vs COM(各难度)"实测 — 那才是与模型评估同口径的锚。'
            '需要真人上机若干局并按难度记录(接线点: from_com_log)。'),
    }
    if verbose:
        print('[human-baseline] %d 局 / %d shard' % (n_ok, len(files)))
    return out


def from_com_log(path=None):
    """接线点: 从实测记录读"真人 vs COM 各难度"胜率(当前无数据 → None)。

    期望记录形态(尚未产生): 每行 JSON 或 md 表格含 char/difficulty/wins/games。
    返回 None 表示无数据 —— **不要**用别的数据代替它。
    """
    p = path or os.path.join(ROOT, 'data', 'human_com_baseline.json')
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d else None
    except Exception:
        return None


# ------------------------------------------------------------- 矩阵 → 对位

def matchup_rates(matrix, chars, our_side=None):
    """把 `build_matrix` 的原始结果整理成**每个角色视角**的对位胜负。

    matrix key = 'a|b'(a,b 为 chars 内角色), value = {'a_wins','b_wins','games'}。

    our_side:
      None        → **双边**口径: 每场对局同时写入 a 视角(对手=b)与
                    b 视角(对手=a), 两视角胜率互补。这样任何角色都能拿到
                    完整对位集(不会因为"总是排在 b 侧"而空手 — R63 自测
                    抓出的覆盖洞: 原实现只写 a 视角, marisa 在
                    {'reimu|marisa','marisa|suika'} 里恒为 b → avg_wr=None)。
                    同一场只计一次(胜/负互补, 不重复计数)。
      'a'         → 只取作为 a 方的对位(单侧模型驱动口径; 对手=同架构快照)
      'b'         → 只取作为 b 方的对位

    返回 {char: {'pairs': {opp: rate}, 'agg': rate, 'insufficient': [opp...]}}
    """
    per = {c: {'pairs': {}, 'insufficient': []} for c in chars}
    for key, r in sorted(matrix.items()):
        if '|' not in key:
            continue
        ca, cb = key.split('|', 1)
        if ca not in per or cb not in per or ca == cb:
            continue
        games = int(r.get('games', 0) or 0)
        aw = int(r.get('a_wins', 0) or 0)
        bw = int(r.get('b_wins', 0) or 0)
        # 只采信实际打过的局数(全部异常时 games>0 而 aw+bw=0 → 记 0 局)
        played = aw + bw
        n = played if played else games
        if our_side in (None, 'a'):
            per[ca]['pairs'][cb] = rate(aw, n)
        if our_side is None:
            per[cb]['pairs'][ca] = rate(bw, n)
        elif our_side == 'b':
            per[cb]['pairs'][ca] = rate(bw, n)
    for c, d in per.items():
        tot = {'wins': 0, 'games': 0}
        for opp, rt in d['pairs'].items():
            tot['wins'] += rt['wins']
            tot['games'] += rt['games']
        d['agg'] = _finalize(tot)
        if not d['pairs'] and len(chars) > 1:
            d['insufficient'] = sorted(o for o in chars if o != c)
    return per


# --------------------------------------------------------- 主度量(可证伪)

def gauge_from_matrix(matrix, chars, our_side=None, min_games=4,
                      human_baseline=None):
    """主入口: 矩阵 → 结构化"超人距离"报告(纯离线, 无游戏/无torch)。

    min_games: 单对位进入"最差对位下界"所需的最少局数(低于此值只报告,
               不参与判定 — 防 1 局定强弱)。
    """
    per = matchup_rates(matrix, chars, our_side=our_side)
    rows = []
    total = {'wins': 0, 'games': 0}
    for c in chars:
        d = per.get(c) or {'pairs': {}, 'agg': rate(0, 0),
                           'insufficient': []}
        pairs = d['pairs']
        elig = {o: r for o, r in pairs.items() if r['games'] >= min_games}
        worst_o, worst_lo = None, None
        for o, r in elig.items():
            if worst_lo is None or r['lo'] < worst_lo:
                worst_lo, worst_o = r['lo'], o
        rows.append({
            'char': c,
            'avg_wr': d['agg']['wr'],
            'games': d['agg']['games'],
            'pairs': {o: r for o, r in sorted(pairs.items())},
            'n_pairs': len(pairs),
            'n_pairs_eligible': len(elig),
            'worst_opp': worst_o,
            'worst_wr': (elig[worst_o]['wr'] if worst_o else None),
            'worst_lower': worst_lo,
            'insufficient': sorted(d['insufficient']),
        })
        total['wins'] += d['agg']['wins']
        total['games'] += d['agg']['games']
    rows.sort(key=lambda r: (-(r['avg_wr'] if r['avg_wr'] is not None else -1),
                             r['char']))

    # 全局最差对位下界: 所有角色中"最薄弱对位的保守下界"的最小值。
    # 这是"没有弱对位"这一超人特征的可证伪代理: 它只会被**真实弱对位**
    # 拉低, 不会被平均掉。
    all_elig = [(r['char'], r['worst_opp'], r['worst_lower'])
                for r in rows if r['worst_lower'] is not None]
    if all_elig:
        wc, wo, wl = min(all_elig, key=lambda t: t[2])
        _tot_games = sum(r['games'] for r in rows)
        dominance = {
            'worst_char': wc, 'worst_opp': wo,
            'worst_lower': wl,
            'eligible_pairs': len(all_elig),
            'total_games': _tot_games,
            # 样本充分性如实标注: 每对2局时一次失利即可把下界压到0,
            # 此时该值**不应**被当作强度结论
            'reliable': bool(_tot_games >= 20 * max(1, len(rows))),
            'interpretation': ('最薄弱对位的Wilson下界 — 越高说明越"无弱对位"; '
                               '样本不足的对位不参与(见insufficient)。'
                               + ('' if _tot_games >= 20 * max(1, len(rows))
                                  else ' ⚠ 当前总样本%d局偏小, 数值仅供参考'
                                       '(单场失利即可压到0)' % _tot_games)),
        }
    else:
        dominance = {
            'worst_char': None, 'worst_opp': None, 'worst_lower': None,
            'eligible_pairs': 0, 'total_games': 0, 'reliable': False,
            'interpretation': '对位样本均 < min_games=%d — 无判定' % min_games,
        }

    # 人类锚
    hb = human_baseline if human_baseline is not None else \
        load_human_baseline()

    # 同口径比较: 只有"真人 vs 该对手集"与"模型 vs 同一对手集"才可相减。
    # 人-人数据是"真人 vs 真人", 模型矩阵是"模型 vs 模型快照" → 不可相减。
    #
    # R63(F6, 用户 2026-10-07 口径): 真人打 COM 恒 100% → COM 在天花板处
    # **饱和不可分辨**。因此即便拿到"真人 vs COM"数据, 它也**不能**充当
    # 超人距离的分母: 人类与超人在该标尺上同为 100%。这推翻了本文件先前
    # "只缺真人vs COM"的判断 —— 缺的不是那一份数据, 而是一个**能区分顶端**
    # 的标尺。故 comparable 只在"能区分"时才为 True。
    comparable = False
    why = ('对手分布不同(真人 vs 真人 ≠ 模型 vs 模型快照) — 胜率之差不是能力之差。')
    com_human = from_com_log()
    _ruler_ok = bool(com_human) and bool(
        (com_human.get('discriminates_at_top')
         if isinstance(com_human, dict) else False))
    if com_human and not _ruler_ok:
        why += (' 已检测到"真人 vs COM"数据, 但**该标尺饱和**'
                '(真人100%) → 不可作分母; 见 com_ruler。')
    if _ruler_ok:
        comparable = True
        why = '检测到"真人 vs 对手"实测且该标尺在顶端可分辨 → 可行差。'

    report = {
        'dominance': dominance,
        'ranking': rows,
        'our_side': our_side or 'bilateral',
        'min_games': int(min_games),
        'games_total': total['games'],
        'human_anchor': hb,
        'com_ruler': {
            **COM_VS_HUMAN,
            'can_do': ('诊断"模型是否已低于人类下限"(对COM输=确定低于人类)'),
            'cannot_do': ('区分人类水平与超人水平(两者同为100%); '
                          '作为任何"距离"的分母'),
            'usage': ('outer_loop.py comeval → com_ruler_verdict(model_wr, n) '
                      '取判定'),
        },
        'comparison': {
            'comparable': comparable,
            'distance': None,
            'reason': why,
            'needed': (None if comparable else
                       '能区分顶端的标尺: (a)真人 vs 该模型直接对打; '
                       '或 (b)在**同一批固定对手**上同时测真人与模型'),
        },
        'caveat': [
            '同架构模型互打: 对位胜率度量**对手/池强度**, 不等于角色或'
            '策略的绝对强弱; 镜像对位≈50% 是算法对称性的结果, 不是"平衡"。',
            'rstd/温度等退火状态会影响胜率; 跨日比较须记录模型 meta。',
            'Wilson 区间已含抽样误差; 但重放抽取偏差(对手水平/角色选择)'
            '不在区间内 — 人类锚的解读须带此限定。',
            '真人打 COM 恒100% → COM 标尺在天花板处饱和, 只能诊断'
            '"是否低于人类下限", 不能度量"高于人类多少"。',
        ],
    }
    return report


def format_report(report, top=12):
    """人类可读输出(供 CLI 与人工核查)。"""
    L = []
    L.append('=== 对抗池广度(最差对位下界) ===')
    d = report['dominance']
    if d['worst_lower'] is None:
        L.append('  无足够样本对位(min_games=%d)' % report['min_games'])
    else:
        L.append('  最弱: %s vs %s — Wilson下界 %.3f (对位样本≥%d, 总%d局%s)'
                 % (d['worst_char'], d['worst_opp'], d['worst_lower'],
                    report['min_games'], d.get('total_games', 0),
                    '' if d.get('reliable') else ' ⚠样本偏小'))
    L.append('  口径: %s' % report['our_side'])
    L.append('')
    L.append('=== 排名(按平均对位胜率; 非角色强度) ===')
    for i, r in enumerate(report['ranking'][:top], 1):
        wr = '  n/a ' if r['avg_wr'] is None else '%5.1f%%' % (r['avg_wr'] * 100)
        L.append('  %2d. %-10s %s  对位%d(可用%d) 最弱%s=%s  %d局'
                 % (i, r['char'], wr, r['n_pairs'], r['n_pairs_eligible'],
                    r['worst_opp'] or '-',
                    ('n/a' if r['worst_lower'] is None
                     else '%.3f' % r['worst_lower']), r['games']))
    hb = report['human_anchor']
    L.append('')
    L.append('=== 真实人类锚(oracle重放, %d局) ===' % hb['n_matches'])
    for c, r in sorted(hb['chars'].items(), key=lambda kv: -(kv[1]['wr'] or 0)):
        L.append('  %-10s 胜率%5.1f%% [%.3f,%.3f] n=%d'
                 % (c, (r['wr'] or 0) * 100, r['lo'], r['hi'], r['games']))
    L.append('  注: %s' % hb['caveat'])
    L.append('')
    cp = report['comparison']
    L.append('=== 距离判定 ===')
    L.append('  comparable=%s  distance=%s'
             % (cp['comparable'], cp['distance']))
    L.append('  原因: %s' % cp['reason'])
    if cp['needed']:
        L.append('  还缺: %s' % cp['needed'])
    cr = report.get('com_ruler')
    if cr:
        L.append('')
        L.append('=== COM 标尺的能/不能(用户实测: 真人打COM=%.0f%%) ==='
                 % (cr['human_wr'] * 100))
        L.append('  能做: %s' % cr['can_do'])
        L.append('  不能: %s' % cr['cannot_do'])
    return '\n'.join(L)


def com_report(model_wr, n_games, human_wr=None):
    """便捷入口: 给定"模型 vs COM"实测读数, 打印该标尺能得出的结论。"""
    v = com_ruler_verdict(model_wr, human_wr, n_games)
    L = ['=== 模型 vs COM: %s ===' % v['verdict']]
    L.append('  模型%.1f%% (%d局) vs 人类%.0f%%'
             % ((v['model_wr'] or 0) * 100, v['games'],
                v['human_wr'] * 100))
    if 'model_ci' in v:
        L.append('  Wilson 95%%: [%.3f, %.3f]' % tuple(v['model_ci']))
    for s in v['can_conclude']:
        L.append('  ✔ 能说: %s' % s)
    for s in v['cannot_conclude']:
        L.append('  ✘ 不能说: %s' % s)
    return '\n'.join(L)


def _main():
    import argparse
    ap = argparse.ArgumentParser(description='超人距离度量(F6)')
    ap.add_argument('matrix', nargs='?', default=None,
                    help='eval_matrix 产出的 JSON; 省略则只看人类锚')
    ap.add_argument('--side', choices=['a', 'b', 'bilateral'],
                    default='bilateral')
    ap.add_argument('--min-games', type=int, default=4)
    ap.add_argument('--rebuild', action='store_true',
                    help='从重放原文重建 data/human_baseline.json 派生档')
    ap.add_argument('--com-wr', type=float, default=None,
                    help='模型 vs COM 胜率(0~1), 与 --com-games 合用 → 只出'
                         '该标尺的能/不能判定')
    ap.add_argument('--com-games', type=int, default=0)
    a = ap.parse_args()
    if a.com_wr is not None:
        print(com_report(a.com_wr, a.com_games))
        return
    if a.rebuild:
        p = export_human_baseline()
        print('已重建派生档: %s' % p)
    hb = load_human_baseline(verbose=True)
    if not a.matrix:
        print(format_report({'dominance': {'worst_lower': None},
                             'ranking': [], 'our_side': a.side,
                             'min_games': a.min_games,
                             'human_anchor': hb,
                             'comparison': {'comparable': False,
                                            'distance': None,
                                            'reason': '未提供矩阵',
                                            'needed': None}}))
        return
    with open(a.matrix, encoding='utf8') as f:
        blob = json.load(f)
    report = gauge_from_matrix(blob.get('matrix', blob),
                               blob.get('chars') or [],
                               our_side=(None if a.side == 'bilateral'
                                         else a.side),
                               min_games=a.min_games,
                               human_baseline=hb)
    print(format_report(report))


if __name__ == '__main__':
    _main()
