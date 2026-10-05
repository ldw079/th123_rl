# mod遮蔽运行时实测证据

- 日期: 2026-09-22 20:48
- 部署DLL MD5: `0BD2A84339E469FEE7D300A2C5EFC1E0`
- 方法: SET_WEATHER强制天气 + 逐帧dump原始字段(tools/runtime_masking_probe.py)

## 阶段1 晴岚(11)

```
{'n': 1375, 'hit': 300, 'hand_masked_L': 300, 'hand_masked_R': 300, 'gauge_sent_L': 300, 'gauge_sent_R': 300, 'active_vals': {'21/21': 182, '9/21': 137, '10/21': 53, '11/21': 703, '11/11': 300}, 'control_n': 0, 'control_hand_real': 0, 'control_gauge_real': 0, 'rounds': 0, 'errs': {'协议错误 err=17': 808}}
```

## 阶段2 极光(19)

```
{'n': 300, 'hit': 300, 'hand_masked_L': 300, 'hand_masked_R': 0, 'gauge_sent_L': 0, 'gauge_sent_R': 0, 'active_vals': {'19/19': 300}, 'control_n': 0, 'control_hand_real': 0, 'control_gauge_real': 0, 'rounds': 0, 'errs': {'未知op=12': 1}}
```

## 判定

**PASS** — 晴岚帧双方hand全0xFF且cardGauge==65535(300/300帧); displayed==19的帧active恒为19, 无真实效果外泄。
