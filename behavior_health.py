# -*- coding: utf-8 -*-
"""BH-1(行为健康方案v4): 行为健康仪表盘 — 采集侧计数器+报告侧聚合。

设计(方案§BH-1):
  轻量宏转移计数 — macro_counts机制旁, 每决策点记账(内存dict, 每局
  ~1KB json旁车落盘到episodes目录, 与episode同生命周期), 不改episode
  npz契约(R63代际契约零触碰)。

仪表覆盖(方案八表中的2-5):
  承诺动作占比 — 决策类别分布(攻击/连段类 vs 移动/防御/其他)
  续打率 — 我方命中(上一决策窗dec_dmg>0)→本决策选攻击/连段类%
  连段完成率 — 选连段类宏→执行窗结算(命中/被防/落空/被打断)
  对位连段成功率 — 完成率按对手角色分解(对位盲直接测量)
  宏转移矩阵 — (prev,cur)稀疏计数, 报告取Top转移

反应延迟/位移混乱度/防守错位矩阵(6-8表)依赖CE-0.1帧日志
(TH123_FRAME_LOG开关, 本模块frame_log_enabled/should_log提供抽样判据,
逐帧数据由train_tm落盘, 报告侧解析)。

类别判定复用my_punish_tracker.classify(6类) — 攻击/连段族=
{MELEE, SKILL}; 连段完成率的"连段类"= 宏名以'连段'/'空连'/'版边连'
开头或classify∈{MELEE,SKILL}且名含'连'。
"""
from __future__ import annotations

import glob
import io
import json
import os
import time

# ---- 连段类判定 ----


def is_combo_macro(name, cls):
    """连段完成率的分母: 连段路线宏(执行健康度口径)。"""
    if name.startswith(('连段', '空连', '版边连', '目押')):
        return True
    return cls in ('MELEE', 'SKILL') and '连' in name


def is_attack_macro(cls):
    """续打率/承诺占比的"攻击/连段类"。"""
    return cls in ('MELEE', 'SKILL')


class BehaviorCounter:
    """每trainer一个; 决策点记账, 局末flush成旁车json。"""

    def __init__(self, char):
        self.char = char
        self.n_dec = 0
        # 承诺占比
        self.cls_count = {}
        # 续打率: (hit|nohit) × (attack|other)
        self.follow = {'hit_atk': 0, 'hit_n': 0,
                       'nohit_atk': 0, 'nohit_n': 0}
        # 连段完成率: fate计数(总+按对手)
        self.combo = {'hit': 0, 'blocked': 0, 'dropped': 0,
                      'interrupted': 0}
        self.combo_by_opp = {}
        # 宏转移稀疏
        self.trans = {}
        # 上一决策状态(私有)
        self._prev = None   # (name, cls, was_combo)

    # ---- 决策点记账(在dec_name被替换前调用) ----
    def note_decision(self, prev_name, prev_cls, prev_dmg, prev_guarded,
                      cur_name, cur_cls, opp_char):
        self.n_dec += 1
        self.cls_count[cur_cls] = self.cls_count.get(cur_cls, 0) + 1
        # 续打率: 上一决策窗是否命中 × 本决策类别
        if self._prev is not None:
            _hit = prev_dmg > 0
            _atk = is_attack_macro(cur_cls)
            if _hit:
                self.follow['hit_atk' if _atk else 'hit_n'] += 1
            else:
                self.follow['nohit_atk' if _atk else 'nohit_n'] += 1
            # 宏转移
            tk = '%s→%s' % (prev_name, cur_name)
            self.trans[tk] = self.trans.get(tk, 0) + 1
        # 连段完成率: 上一决策是连段类 → 结算fate
        if self._prev is not None and self._prev[2]:
            if prev_name is None:
                fate = 'interrupted'       # 受击/R34中止清名
            elif prev_dmg > 0:
                fate = 'hit'
            elif prev_guarded:
                fate = 'blocked'
            else:
                fate = 'dropped'
            self.combo[fate] += 1
            d = self.combo_by_opp.setdefault(opp_char or '?',
                                             {'hit': 0, 'blocked': 0,
                                              'dropped': 0,
                                              'interrupted': 0})
            d[fate] += 1
        self._prev = (cur_name, cur_cls,
                      is_combo_macro(cur_name, cur_cls))

    # ---- 局末 ----
    def flush(self, ep_dir, actor_id, ep_idx, extra=None):
        """旁车json落盘(原子); 返回路径或None(无决策不落盘)。"""
        if self.n_dec == 0:
            return None
        rec = {'char': self.char, 'ts': time.strftime('%Y%m%d_%H%M%S'),
               'n_dec': self.n_dec, 'cls': self.cls_count,
               'follow': self.follow, 'combo': self.combo,
               'combo_by_opp': self.combo_by_opp,
               'trans_top': dict(sorted(self.trans.items(),
                                        key=lambda kv: -kv[1])[:200])}
        if extra:
            rec.update(extra)
        os.makedirs(ep_dir, exist_ok=True)
        fname = 'bh_%s_%02d_%05d_%s.json' % (self.char, actor_id, ep_idx,
                                             rec['ts'])
        tmp = os.path.join(ep_dir, fname + '.tmp')
        dst = os.path.join(ep_dir, fname)
        io.open(tmp, 'w', encoding='utf8').write(
            json.dumps(rec, ensure_ascii=False))
        os.replace(tmp, dst)
        return dst


# ---- CE-0.1 帧日志开关(R131定稿: 默认关, EVERY抽样) ----

def frame_log_enabled():
    return os.environ.get('TH123_FRAME_LOG', '0') == '1'


def frame_log_interval():
    """R151: 抽样间隔(秒, 默认1800=30分钟/角色) — 时间基准对进程
    重启鲁棒(原局计数在fleet重启后清零, 反复重启把抽样吃掉)."""
    return max(60, int(os.environ.get('TH123_FRAME_LOG_INTERVAL', '1800')))


# 帧日志字段(R131定稿12字段/侧+BH-1增direction — 位移混乱度/防守
# 错位矩阵需要; 格式随首投产定稿)
FL_FIELDS = ('position.x', 'position.y', 'hp', 'spirit', 'action',
             'airBorne', 'untech', 'comboDamage', 'cardGauge', 'score',
             'hitStop', 'timeStop', 'direction')


# ---- 报告侧聚合 ----

def aggregate(eps_dir, char, last_n=200):
    """读最近last_n个旁车json → 聚合dict。"""
    files = sorted(glob.glob(os.path.join(
        eps_dir, 'bh_%s_*.json' % char)),
        key=lambda p: (os.path.getmtime(p), p))[-last_n:]
    agg = {'n_files': len(files), 'n_dec': 0, 'cls': {},
           'follow': {'hit_atk': 0, 'hit_n': 0,
                      'nohit_atk': 0, 'nohit_n': 0},
           'combo': {'hit': 0, 'blocked': 0, 'dropped': 0,
                     'interrupted': 0},
           'combo_by_opp': {}, 'trans': {}}
    for p in files:
        try:
            r = json.load(io.open(p, encoding='utf8'))
        except Exception:
            continue
        agg['n_dec'] += r.get('n_dec', 0)
        for k, v in r.get('cls', {}).items():
            agg['cls'][k] = agg['cls'].get(k, 0) + v
        for k in agg['follow']:
            agg['follow'][k] += r.get('follow', {}).get(k, 0)
        for k in agg['combo']:
            agg['combo'][k] += r.get('combo', {}).get(k, 0)
        for oc, d in r.get('combo_by_opp', {}).items():
            t = agg['combo_by_opp'].setdefault(
                oc, {'hit': 0, 'blocked': 0, 'dropped': 0,
                     'interrupted': 0})
            for k in t:
                t[k] += d.get(k, 0)
        for k, v in r.get('trans_top', {}).items():
            agg['trans'][k] = agg['trans'].get(k, 0) + v
    return agg


def rates(agg):
    """聚合dict → 人读指标。"""
    out = {'files': agg['n_files'], 'decisions': agg['n_dec']}
    n = agg['n_dec']
    atk = sum(v for k, v in agg['cls'].items()
              if is_attack_macro(k))
    out['commit_rate'] = atk / n if n else 0.0
    f = agg['follow']
    hn = f['hit_atk'] + f['hit_n']
    out['followup_hit'] = (f['hit_atk'] / hn) if hn else 0.0
    nn = f['nohit_atk'] + f['nohit_n']
    out['followup_nohit'] = (f['nohit_atk'] / nn) if nn else 0.0
    c = agg['combo']
    cn = sum(c.values())
    out['combo_total'] = cn
    out['combo_hit_rate'] = (c['hit'] / cn) if cn else 0.0
    out['combo_interrupt_rate'] = (c['interrupted'] / cn) if cn else 0.0
    out['combo_by_opp'] = {}
    for oc, d in sorted(agg['combo_by_opp'].items()):
        m = sum(d.values())
        out['combo_by_opp'][oc] = {
            'n': m, 'hit_rate': (d['hit'] / m) if m else 0.0}
    out['trans_top'] = dict(sorted(agg['trans'].items(),
                                   key=lambda kv: -kv[1])[:8])
    return out
