# -*- coding: utf-8 -*-
"""回放一致性审计(兄弟工程§4.19判据): 驱动全长rep, 
跟踪score事件(回合胜场)的帧号与终值, 与文件名比分交叉验证。
关键判据: score(回合计数器)而非HP/KO — HP归零只在一帧, score持久。"""
import sys, os, re, time, json
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
from tools.rep_distill import (
    SyncClient, GameEnded, parse_rep, battle_to_trainer)

REP_DIR = r'D:\temp\expert_reps'
PORT = 20985
score_pat = re.compile(r'\((\d+)[︰:](\d+)_(胜|负)\)')

# 选5个不同比分的rep
cands = []
for f in sorted(os.listdir(REP_DIR)):
    if not f.endswith('.rep'):
        continue
    b = open(os.path.join(REP_DIR, f), 'rb').read(70)
    if b[14] not in (0, 1, 9) or b[63] not in (0, 1, 9):
        continue
    m = score_pat.search(f)
    if m:
        cands.append((f, int(m.group(1)), int(m.group(2)), m.group(3)))
seen_scores = set()
selected = []
for item in cands:
    key = (item[1], item[2])
    if key not in seen_scores:
        seen_scores.add(key)
        selected.append(item)
    if len(selected) >= 5:
        break

print('=== 回放一致性审计(v4 mod种子, score判据) ===')
print('选%d个带比分rep, 全长驱动\n' % len(selected))

results = []
for rep_file, fn_sl, fn_sr, fn_res in selected:
    print('--- %s ---' % rep_file[:60])
    print('  文件名比分: %d:%d (%s)' % (fn_sl, fn_sr, fn_res))
    rep_path = os.path.join(REP_DIR, rep_file)
    hdr = parse_rep(rep_path)
    inputs = hdr['inputs']
    n_frames = len(inputs) // 2
    print('  角色%d/%d 帧%d 种子%d' % (hdr['char_x'], hdr['char_y'],
                                      n_frames, hdr['seed']))

    cli = SyncClient(PORT + len(results))
    cli.launch(tps=None, seed=hdr['seed'])
    winner = None
    drv_sl, drv_sr = -1, -1
    score_events = []    # (帧号, 左score, 右score, 左hp, 右hp)
    hands_l, hands_r = set(), set()
    f = 0
    prev_sl, prev_sr = 0, 0
    t0 = time.time()
    try:
        first = cli.start_game_sync(
            hdr['char_x'], hdr['char_y'],
            hdr['deck_x'], hdr['deck_y'],
            hdr['pal_x'], hdr['pal_y'])
        L, R = first[0], first[1]
        for i in range(5):
            if L['hand'][i*2] not in (0xFF, 0):
                hands_l.add(int(L['hand'][i*2]))
            if R['hand'][i*2] not in (0xFF, 0):
                hands_r.add(int(R['hand'][i*2]))
        while f < n_frames and time.time() - t0 < n_frames / 25.0:
            il = battle_to_trainer(inputs[f * 2]) \
                if f * 2 + 1 < len(inputs) else {}
            ir = battle_to_trainer(inputs[f * 2 + 1]) \
                if f * 2 + 1 < len(inputs) else {}
            try:
                r = cli.step(il, ir)
            except GameEnded as ge:
                winner = ge.winner
                drv_sl, drv_sr = ge.ls, ge.rs
                break
            left, right = r[0], r[1]
            f += 1
            # 手牌采集
            for i in range(5):
                if left['hand'][i*2] not in (0xFF, 0):
                    hands_l.add(int(left['hand'][i*2]))
                if right['hand'][i*2] not in (0xFF, 0):
                    hands_r.add(int(right['hand'][i*2]))
            # score事件检测(回合结束 = score增量)
            if left['score'] > prev_sl or right['score'] > prev_sr:
                score_events.append((f, left['score'], right['score'],
                                     left['hp'], right['hp']))
                prev_sl = left['score']
                prev_sr = right['score']
        if winner is None:
            drv_sl, drv_sr = left['score'], right['score']
    except Exception as e:
        print('  [异常]', type(e).__name__, str(e)[:80])
        results.append({'match': '异常'})
        cli.close()
        time.sleep(2)
        continue
    finally:
        cli.close()

    deck_l = {c for c in hdr['deck_x'] if c}
    deck_r = {c for c in hdr['deck_y'] if c}
    sync_l = hands_l <= deck_l | {0} if hands_l else True
    sync_r = hands_r <= deck_r | {0} if hands_r else True

    print('  驱动: %d/%d帧 (%.0f%%) 终局winner=%s score=%d:%d'
          % (f, n_frames, 100.0 * f / n_frames, winner, drv_sl, drv_sr))
    print('  手牌: 左⊆左=%s 右⊆右=%s' % (sync_l, sync_r))
    if score_events:
        print('  回合事件:')
        for fr, sl, sr, hl, hr in score_events:
            print('    帧%d score=%d:%d hp=%d/%d'
                  % (fr, sl, sr, hl, hr))
    else:
        print('  (无回合事件 — 可能流尽于第一回合内)')

    # 比分比对
    match = None
    if drv_sl >= 0:
        if drv_sl == fn_sl and drv_sr == fn_sr:
            match = '✓正序一致'
        elif drv_sl == fn_sr and drv_sr == fn_sl:
            match = '✓反序一致'
        else:
            match = '✗不一致(drv=%d:%d fn=%d:%d)' % (drv_sl, drv_sr,
                                                       fn_sl, fn_sr)
    print('  [判定] %s' % (match or '不可判'))
    results.append({'match': match, 'sync': sync_l and sync_r,
                    'frames': f, 'total': n_frames})
    time.sleep(2)

print('\n=== 汇总 ===')
ok = sum(1 for r in results if r.get('match', '').startswith('✓'))
bad = sum(1 for r in results if r.get('match', '').startswith('✗'))
other = len(results) - ok - bad
sync_ok = sum(1 for r in results if r.get('sync'))
print('总数%d: 一致%d 不一致%d 其他%d | 手牌同步%d/%d'
      % (len(results), ok, bad, other, sync_ok, len(results)))
if ok + bad > 0:
    print('一致率: %.1f%% (随机基线50%%)' % (100.0 * ok / (ok + bad)))
