# 引擎语义表（社区逆向+官方文档交叉）— CA-0 产出 2026-10-17

> 来源: th123ai document.txt (744行, 本地副本) + SWRSAddr-110.ini (101条)
> 交叉: 官方 wiki wikiwiki.jp/th123ai/ API页(2021-02版, 含fflags/aflags逐位)
> 纪律: 偏移跨版本可失效; **语义表是版本无关的解码知识**(CA方案核心判断)
> 标注: 未确认位标"?" — 采用前与实测交叉(R4)

## 1. correction 特殊补正位(6位, offset 0x4AD)

| 位值 | 补正名 | 中文 |
|---|---|---|
| 1 | Rift Attack | 裂空攻击 |
| 2 | Smash Attack | 击飞攻击 |
| 4 | Border Resist | 结界抵抗 |
| 8 | Chain Arts | 连击武功 |
| 16 | Chain Spell | 连击符卡 |
| **32** | **Counter Hit** | **反击命中(CH)** ← S-1/CE-1核心缺失信号 |

- 语义: 自己最后给对手的特殊补正标志(叠加); 例: 吹飞+CH = 2+32 = 34
- **CA-6b 消费**: CH信号(bit 5=32)是 punish 追踪器与连段起始价值判定的直接判据

## 2. fflags 帧标志(攻击无关, offset 0x4C)

| bit | 含义 | 确认 |
|---|---|---|
| 4 | 空中 | ✓(document.txt示例) |
| 其余 | wiki "解析中" | ? |

## 3. aflags 攻击标志(攻击相关, offset 0x4D?)

| bit | 含义 | 确认 |
|---|---|---|
| 2/4/8/16 | 站防/蹲防/空防/地上不可防 | ?(CA方案v2引wiki) |
| +64 | 误防(不能) | ? |
| +524288 | 破防 | ?(CA方案v2引wiki) |

- **CA-6b 消费**: 防御高度表的双源交叉验证

## 4. 环境变量语义(document.txt 440-744)

| 变量 | 语义 | 我方对应 |
|---|---|---|
| my_dam / enemy_dam | 合计连段伤害 | comboDamage (JZ-1已消费) |
| my_limit / enemy_limit | 与Limit值 | comboLimit (JZ-1已消费) |
| my_rate / enemy_rate | 与Rate值 | — (我方未消费) |
| my_combo / enemy_combo | 连段Hit数 | — (combo_count在偏移表0x4B4) |
| my_air | 空中Dash已用次数 | airDashCount (JZ-1已消费) |
| my_frame | 当前动作已过帧 | frameCount (已消费) |
| my_hitstop | 打击/防御/受击硬直帧 | hitStop (已消费) |
| my_xspeed / my_yspeed | 内部速度(比差分快1帧) | — (opp_model有EMA版) |
| my_img | 当前角色图像ID | — (CE-2 objs field[3]可能对应) |
| my_dir | 朝向(-1左/+1右) | direction (已消费) |
| my_attackarea_n | 攻击判定矩形数 | — (CA-7 live判定框) |
| my_hitarea_n | 受击判定矩形数 | — (CA-7) |
| weather_time | 气质计数器×10 | — (我方读天气ID) |
| weather2 | 天气预报 | — (我方无预报) |
| key_delay | 键入延迟帧 | — (CA-3 W1垫片) |
| data_delay | 对手状态获取延迟帧 | — (CA-3 W1垫片) |

## 5. get_obj_data 13值( objs 语义, CA-2解码钥匙)

```
id, ox, oy, hp, img, frame, oxs, oys, oid, attack_n, hit_n, fflags, aflags
```

| 位置 | 含义 |
|---|---|
| 0 id | 对象ID(唯一) |
| 1 ox | X坐标 |
| 2 oy | Y坐标 |
| 3 hp | HP |
| 4 img | 图像ID |
| 5 frame | 帧数 |
| 6 oxs | X速度 |
| 7 oys | Y速度 |
| **8 oid** | **固有識別子( obj-ID 对应表)** |
| 9 attack_n | 攻击范围数 |
| 10 hit_n | 受击范围数 |
| 11 fflags | 帧标志 |
| 12 aflags | 攻击标志 |

### obj-ID 对応表(CA-2 先验值域)

| 值域 | 类型 |
|---|---|
| 800-809 | 弹幕系 |
| 810-849 | 技能对象(爱丽丝5步进: 810系=236/815系=623/820系=214/825系=22) |
| 850-869 | 符卡对象 |
| 899 | 特例(妖梦=半霊/衣玖=899·998) |
| 848 | 特例(天子) |

## 6. mod封包 CS_FIELDS × 语义表交叉(CA-6a 审计)

| 封包字段 | 语义表对应 | 状态 |
|---|---|---|
| position.x/y | x/y | ✓已消费 |
| hp | my_hp→HPOFS 0x184 | ✓已消费 |
| spirit | my_spell→REIPOWEROFS 0x49E | ✓已消费 |
| action | my_act→ACTIONIDOFS 0x13C | ✓已消费 |
| airBorne | fflags bit4 | ✓已消费 |
| untech | (JZ-1推算路径) | ◐推算(BH-3.1门) |
| comboDamage | my_dam→COMBODAMAGEOFS 0x4B6 | ✓已消费 |
| comboLimit | my_limit | ✓JZ-1 |
| airDashCount | my_air→AIRDASHCOUNTOFS 0x49B | ✓JZ-1 |
| cardGauge | my_spell→SCGauge | ✓已消费 |
| hitStop | my_hitstop→HITSTOPOFS 0x196 | ✓已消费 |
| timeStop | my_timestop→TIMESTOPOFS 0x4A8 | ✓已消费 |
| **correction(0x4AD)** | my_correction 6位 | **❌未消费 — CA-6b CH信号候选** |
| **frameflags(0x4C)** | fflags | **❌未消费** |
| **attackflags(0x4D)** | aflags | **❌未消费** |
| **combo_count(0x4B4)** | my_combo | ❌未消费 |
| **combo_rate(0x4B0)** | my_rate | ❌未消费 |
| **rei_stop(0x4A2)** | 灵力冷却 | **❌未消费 — CA-4直读候选** |
| **xspeed(0xF4)** | my_xspeed | ❌未消费(opp_model EMA替代) |

## 7. 地址表偏移一致性核验(CA-0.1)

社区表(SWRSAddr-110.ini, 101条) vs 我方已知偏移:
- **16项核验: 15项✓一致 / 1项✗(SCENEID=全局地址, mod补丁差异, 预期内)**
- 角色级偏移(HP/position/action/direction/spirit等)全部一致 → 游戏版本兼容
- 结论: **地址表可直接用于 RPM 直读工具(B标尺/CA-4), 无需换算**

### 高价值未消费偏移(远期 C9 候选)

| 偏移 | 字段 | 价值 |
|---|---|---|
| 0x4AD | correction(CH bit5) | S-1/CE-1核心 |
| 0x4C | fflags | 帧标志 |
| 0x4D | aflags | 攻击标志(防御高度) |
| 0x4A2 | rei_stop | 灵力冷却 |
| 0x4B4 | combo_count | 连段HIT数 |
| 0x334 | hitarea_flag | 受击标志 |
| 0x1CB/0x1CC | attackarea_n/hitarea_n | 判定矩形数(CA-7) |
