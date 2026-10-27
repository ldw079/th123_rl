# R19 历史行为指标（human vs model, rep 代理）

- reps=51；session=17

| 指标 | 模型 | 人类 |
|---|---|---|
| dec_per_sec | 10.694 | 11.203 |
| macro_avg_frames | 8.939 | 8.369 |
| attack_rate | 0.344 | 0.265 |
| approach_rate | 0.259 | 0.278 |
| guard_retreat_rate | 0.25 | 0.275 |
| jump_rate | 0.131 | 0.082 |

## 受威胁反应（人类攻击后12F）
- react_rate=0.673 avg_delay=2.89F threats=10847 reacted=7453

## 会话（历史）
- sess_20261013_165124_hl.json char=suika 人0-模型0 reps=0
- sess_20261013_172441.json char=suika 人2-模型0 reps=2
- sess_20261013_172558.json char=suika 人1-模型0 reps=1
- sess_20261013_213252.json char=suika 人5-模型0 reps=6
- sess_20261015_165447.json char=reimu 人6-模型0 reps=6
- sess_20261015_170129.json char=suika 人5-模型0 reps=5
- sess_20261015_170909.json char=marisa 人5-模型0 reps=5
- sess_20261018_122201.json char=reimu 人3-模型0 reps=3
- sess_20261018_122650.json char=marisa 人3-模型0 reps=3
- sess_20261018_123158.json char=suika 人3-模型0 reps=3
- sess_20261019_092609.json char=reimu 人7-模型0 reps=7
- sess_20261027_172439_hl.json char=reimu 人0-模型0 reps=0
- sess_20261027_184857_hl.json char=reimu 人1-模型0 reps=0
- sess_20261027_185110_hl.json char=reimu 人1-模型0 reps=0
- sess_20261027_185322_hl.json char=reimu 人0-模型0 reps=0
- sess_20261027_193918_hl.json char=reimu 人0-模型0 reps=0
- sess_20261027_194152_hl.json char=reimu 人1-模型0 reps=0

说明：rep 无弹幕状态；擦弹/防御用"后方向/dash/jump 反应"代理；受威胁窗口=人类攻击起始后 12F。
