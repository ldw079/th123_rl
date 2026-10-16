# -*- coding: utf-8 -*-
"""W2阶段1行为测试: 反事实危险显影卡(mock续演).

计划验收锚定:
1. 合成必败分支检出率 ≥80% (mock alt×猛攻=90%KO)
2. 实际路线同局危险率 ≤20% (mock actual≈5%KO+小伤害)
3. 分布非退化: 正常mock ≥2种终局; 退化mock → 作废(void)
4. 报告字段: 随机源配置/接管者标注/逐副本终局列表/作废裁决
5. 种子可复现: 同输入两次运行逐副本终局一致
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
try:
    sys.stdout.reconfigure(encoding="utf8")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


def run_mock(mode='normal'):
    out = os.path.join(tempfile.mkdtemp(prefix='dr_'), 'card.json')
    cmd = [sys.executable,
           os.path.join(ROOT, 'tools', 'danger_reveal.py'),
           '--mock', '--mock-mode', mode,
           '--actual', '立防', '--alt', '前冲,DA',
           '--output', out]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-500:]
    return json.load(open(out, encoding='utf8'))


def main():
    card = run_mock()

    # 1. 必败分支检出 ≥80%
    alt = card['tempting_alternative']
    check("必败分支检出率≥80%", alt['danger_rate'] >= 0.8,
          "danger=%.2f" % alt['danger_rate'])

    # 2. 实际路线危险率 ≤20%
    act = card['actual']
    check("实际路线危险率≤20%", act['danger_rate'] <= 0.2,
          "danger=%.2f" % act['danger_rate'])

    # 3. 非退化
    check("正常批次≥2种终局",
          act['distinct_endings'] >= 2 and alt['distinct_endings'] >= 2,
          "act=%d alt=%d" % (act['distinct_endings'],
                             alt['distinct_endings']))
    degen = run_mock('degenerate')
    bv = degen['batch_validity']
    check("退化批次作废", bv['actual_void'] and bv['alt_void']
          and bv['verdict'] == '作废重跑', str(bv))
    check("正常批次有效", card['batch_validity']['verdict'] == '有效')

    # 4. 报告字段
    for k in ('random_sources', 'takeover', 'per_replica_endings',
              'danger_rule', 'human_condition'):
        check("报告字段:%s" % k, k in card)
    rs = card['random_sources']
    check("随机源≥2项启用", rs['n_sources_active'] >= 2
          and len(rs['opponent_rotation']) >= 2, str(rs))
    check("接管者标注", '原策略接管' in card['takeover'])
    check("逐副本终局列表",
          len(card['per_replica_endings']['alt']) == 20)

    # 5. 可复现: 同输入重跑 → 逐副本终局一致
    card2 = run_mock()
    e1 = [(e['i'], e['outcome'], e['my_d']) for e in
          card['per_replica_endings']['alt']]
    e2 = [(e['i'], e['outcome'], e['my_d']) for e in
          card2['per_replica_endings']['alt']]
    check("种子可复现", e1 == e2)

    print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
