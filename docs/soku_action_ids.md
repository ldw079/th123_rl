# 非想天则（Touhou 12.3 Hisoutensoku）动作编号对照表

> 用途：SokuAI 每帧发送的 `action` 字段、`OPCODE_RESTRICT_MOVES` 黑名单、以及任何需要「招式 ↔ 动作编号」互查的场景。

## 0. 数据来源与版本（重要）

| 项 | 值 |
|---|---|
| 仓库 | `https://github.com/SokuDev/SokuLib` |
| 文件 | `src/Action.hpp`（`enum Action : unsigned short`） |
| 锁定 commit | `09fed348bf71ce7466093d0bce7505f903723147` |
| commit 日期 / 作者 | 2025-03-22 / PinkySmile（即 SokuAI 作者） |
| blob sha (Action.hpp) | `1b6eaf8f8aad81cf50b40d536ee167a29f51f367`（9128 字节） |
| 该 commit 与 SokuAI 的关系 | SokuAI 的 `.gitmodules` 把 `SokuLib` 子模块固定在此 commit |
| 动作字段的宿主结构 | `src/CharacterManager.hpp` → `ObjectManager`：`Action action;`（偏移 `0x13C`，2 字节），注释为 `ADDR_ACTIONIDOFS` |

访问方式（若需复核）：
```
https://github.com/SokuDev/SokuLib/blob/09fed348bf71ce7466093d0bce7505f903723147/src/Action.hpp
```

**SokuAI 自身不含此表**。它只做转发，详见文末第 4 节。

---

## 1. 编号分区总览

| 范围 | 含义 | 条目数 |
|---|---|---|
| 0–10 | 基础待机/移动/着地 | 11 |
| 50–98 | 受击硬直（地面/空中/蹲姿，按 hitstun 等级） | 24 |
| 100 / 143 / 145 | 投技被抓 / 地面蹲姿 / 空中蹲姿 | 3 |
| 150–199 | 防御（正确防御/错误防御/空防）与三种落地受身 | 27 |
| 200–226 | 冲刺、空中冲刺、大跳、飞行、jBE | 20 |
| 300–332 | A 系（含 jA、66A、Suwako 专属） | 18 |
| 400–432 | B/C 系（含 jB/jC、66B/66C、Orreries 专属） | 26 |
| 500–593 | 必杀技（默认配置 / ALT1 / ALT2 × 地面 B、地面 C、空中 B、空中 C） | 72 |
| 600–619 | 使用符卡（`SC_ID_200`–`SC_ID_219`） | 20 |
| 650–669 | 使用符卡的「里」效果（ALT_EFFECT） | 20 |
| 690–698 | 技能卡/系统卡、道具、喝药、卡组回收、魔法药、龙星、符卡宣告等 | 9 |

编号写法提示：`enum Action : unsigned short`，值即线上字节（`GAME_FRAME` 中 2 字节，含 `sequence`/`pose` 各 2 字节）。收发时按 `uint16` 小端处理。

---

## 2. 完整动作编号对照表（按编号排序）

| 编号 | SokuLib 常量 | 派生含义（由 236/5A 等指令记法推导，非 SokuLib 原文） |
|---:|---|---|
| 0 | `ACTION_IDLE` | 站立待机 |
| 1 | `ACTION_CROUCHING` | 下蹲（进入） |
| 2 | `ACTION_CROUCHED` | 蹲姿（保持） |
| 3 | `ACTION_STANDING_UP` | 起身 |
| 4 | `ACTION_WALK_FORWARD` | 前走 6 |
| 5 | `ACTION_WALK_BACKWARD` | 后走 4 |
| 6 | `ACTION_NEUTRAL_JUMP` | 垂直跳 8 |
| 7 | `ACTION_FORWARD_JUMP` | 前跳 9 |
| 8 | `ACTION_BACKWARD_JUMP` | 后跳 7 |
| 9 | `ACTION_FALLING` | 下落 |
| 10 | `ACTION_LANDING` | 着地 |
| 50 | `ACTION_STAND_GROUND_HIT_SMALL_HITSTUN` | 站立受击·小硬直 |
| 51 | `ACTION_STAND_GROUND_HIT_MEDIUM_HITSTUN` | 站立受击·中硬直 |
| 52 | `ACTION_STAND_GROUND_HIT_BIG_HITSTUN` | 站立受击·大硬直 |
| 53 | `ACTION_STAND_GROUND_HIT_HUGE_HITSTUN` | 站立受击·特大硬直 |
| 56 | `ACTION_STAND_GROUND_HIT_SMALL_HITSTUN_2` | 站立受击·小硬直（第二套） |
| 57 | `ACTION_STAND_GROUND_HIT_MEDIUM_HITSTUN_2` | 站立受击·中硬直（第二套） |
| 58 | `ACTION_STAND_GROUND_HIT_BIG_HITSTUN_2` | 站立受击·大硬直（第二套） |
| 62 | `ACTION_CROUCH_GROUND_HIT_SMALL_HITSTUN` | 蹲姿受击·小硬直 |
| 63 | `ACTION_CROUCH_GROUND_HIT_MEDIUM_HITSTUN` | 蹲姿受击·中硬直 |
| 64 | `ACTION_CROUCH_GROUND_HIT_BIG_HITSTUN` | 蹲姿受击·大硬直 |
| 70 | `ACTION_AIR_HIT_SMALL_HITSTUN` | 空中受击·小硬直 |
| 71 | `ACTION_AIR_HIT_MEDIUM_HITSTUN` | 空中受击·中硬直 |
| 72 | `ACTION_AIR_HIT_BIG_HITSTUN` | 空中受击·大硬直 |
| 73 | `ACTION_AIR_HIT_DIRECT_KNOCKDOWN` | 空中被击落（直接倒地） |
| 74 | `ACTION_AIR_HIT_CAN_WALL_SLAM` | 空中受击·可撞墙 |
| 75 | `ACTION_AIR_HIT_BIG_HITSTUN4` | 空中受击·大硬直（第 4 种） |
| 76 | `ACTION_AIR_HIT_WALL_SLAMMED` | 空中受击·已撞墙 |
| 77 | `ACTION_AIR_HIT_HUGE_HITSTUN` | 空中受击·特大硬直 |
| 78 | `ACTION_AIR_HIT_WALL_SLAMMED2` | 空中受击·已撞墙（第二种） |
| 88 | `ACTION_AIR_HIT_WILL_GROUND_SLAM` | 空中受击·将被砸向地面 |
| 89 | `ACTION_AIR_HIT_GROUND_SLAMMED` | 空中受击·已被砸向地面 |
| 97 | `ACTION_KNOCKED_DOWN` | 倒地（弹跳/移动中） |
| 98 | `ACTION_KNOCKED_DOWN_STATIC` | 倒地静止（源码注释：此时角色不再弹跳或移动） |
| 100 | `ACTION_GRABBED` | 被投技抓住 |
| 143 | `ACTION_GROUND_CRUSHED` | 地面被压溃 |
| 145 | `ACTION_AIR_CRUSHED` | 空中被压溃 |
| 150 | `ACTION_RIGHTBLOCK_HIGH_SMALL_BLOCKSTUN` | 正确防御·上段·小防御硬直 |
| 151 | `ACTION_RIGHTBLOCK_HIGH_MEDIUM_BLOCKSTUN` | 正确防御·上段·中防御硬直 |
| 152 | `ACTION_RIGHTBLOCK_HIGH_BIG_BLOCKSTUN` | 正确防御·上段·大防御硬直 |
| 153 | `ACTION_RIGHTBLOCK_HIGH_HUGE_BLOCKSTUN` | 正确防御·上段·特大防御硬直 |
| 154 | `ACTION_RIGHTBLOCK_LOW_SMALL_BLOCKSTUN` | 正确防御·下段·小防御硬直 |
| 155 | `ACTION_RIGHTBLOCK_LOW_MEDIUM_BLOCKSTUN` | 正确防御·下段·中防御硬直 |
| 156 | `ACTION_RIGHTBLOCK_LOW_BIG_BLOCKSTUN` | 正确防御·下段·大防御硬直 |
| 157 | `ACTION_RIGHTBLOCK_LOW_HUGE_BLOCKSTUN` | 正确防御·下段·特大防御硬直 |
| 158 | `ACTION_AIR_GUARD` | 空中防御 |
| 159 | `ACTION_WRONGBLOCK_HIGH_SMALL_BLOCKSTUN` | 错误防御·上段·小 |
| 160 | `ACTION_WRONGBLOCK_HIGH_MEDIUM_BLOCKSTUN` | 错误防御·上段·中 |
| 161 | `ACTION_WRONGBLOCK_HIGH_BIG_BLOCKSTUN` | 错误防御·上段·大 |
| 162 | `ACTION_WRONGBLOCK_HIGH_HUGE_BLOCKSTUN` | 错误防御·上段·特大 |
| 163 | `ACTION_WRONGBLOCK_LOW_SMALL_BLOCKSTUN` | 错误防御·下段·小 |
| 164 | `ACTION_WRONGBLOCK_LOW_MEDIUM_BLOCKSTUN` | 错误防御·下段·中 |
| 165 | `ACTION_WRONGBLOCK_LOW_BIG_BLOCKSTUN` | 错误防御·下段·大 |
| 166 | `ACTION_WRONGBLOCK_LOW_HUGE_BLOCKSTUN` | 错误防御·下段·特大 |
| 180 | `ACTION_FORWARD_AIRTECH` | 前方受身（空中） |
| 181 | `ACTION_BACKWARD_AIRTECH` | 后方受身（空中） |
| 197 | `ACTION_FORWARD_TECH` | 前方受身（落地） |
| 198 | `ACTION_BACKWARD_TECH` | 后方受身（落地） |
| 199 | `ACTION_NEUTRAL_TECH` | 原地受身（落地） |
| 200 | `ACTION_FORWARD_DASH` | 前冲刺 66 |
| 201 | `ACTION_BACKDASH` | 后冲刺 44 |
| 202 | `ACTION_FORWARD_AIRDASH` | 前空中冲刺 66（空中） |
| 203 | `ACTION_BACKWARD_AIRDASH` | 后空中冲刺 44（空中） |
| 204 | `ACTION_GROUNDDASH_RECOVERY` | 地面冲刺收招 |
| 206 | `ACTION_LILYPAD_FORWARD_DASH` | 踩踏弹幕前冲 |
| 207 | `ACTION_LILYPAD_BACKDASH` | 踩踏弹幕后冲 |
| 208 | `ACTION_NEUTRAL_HIGH_JUMP` | 垂直大跳 28 |
| 209 | `ACTION_FORWARD_HIGH_JUMP` | 前大跳 29 |
| 210 | `ACTION_BACKWARD_HIGH_JUMP` | 后大跳 27 |
| 211 | `ACTION_NEUTRAL_HIGH_JUMP_FROM_GROUND_DASH` | 地面冲刺接垂直大跳 |
| 212 | `ACTION_FORWARD_HIGH_JUMP_FROM_GROUND_DASH` | 地面冲刺接前大跳 |
| 214 | `ACTION_FLY` | 飞行（空中 D / 66D 等） |
| 215 | `ACTION_HARDLAND` | 硬着陆 |
| 218 | `ACTION_SUWAKO_j2D` | 洩矢诹访子 j2D |
| 219 | `ACTION_SUWAKO_j1D_j3D` | 洩矢诹访子 j1D / j3D |
| 220 | `ACTION_BE2` | 弹幕回避 2（下+DD） |
| 222 | `ACTION_BE1` | 弹幕回避 1（后+DD） |
| 223 | `ACTION_BE6` | 弹幕回避 6（前+DD） |
| 224 | `ACTION_BE4` | 弹幕回避 4（4+DD） |
| 225 | `ACTION_jBE4` | 空中 BE4 |
| 226 | `ACTION_jBE6` | 空中 BE6 |
| 300 | `ACTION_5A` | 5A（站立 A） |
| 301 | `ACTION_f5A` | f5A（远 5A，射程外变体） |
| 302 | `ACTION_6A` | 6A |
| 303 | `ACTION_2A` | 2A（蹲 A） |
| 304 | `ACTION_3A` | 3A（斜下 A） |
| 305 | `ACTION_66A` | 66A（冲刺 A） |
| 306 | `ACTION_j5A` | j5A（空中 A） |
| 307 | `ACTION_j6A` | j6A |
| 308 | `ACTION_j2A` | j2A |
| 309 | `ACTION_j8A` | j8A |
| 311 | `ACTION_f2A` | f2A（远 2A） |
| 320 | `ACTION_5AA` | 5AA（5A 连段第 2 段） |
| 321 | `ACTION_5AAA` | 5AAA（第 3 段） |
| 322 | `ACTION_5AAAA` | 5AAAA（第 4 段） |
| 323 | `ACTION_5AAAAA` | 5AAAAA（第 5 段） |
| 324 | `ACTION_5AAA3A` | 5AAA3A（连段分支） |
| 325 | `ACTION_j5AA` | j5AA（空中 A 第 2 段） |
| 330 | `ACTION_4A` | 4A |
| 331 | `ACTION_SUWAKO_3A` | 洩矢诹访子 3A（角色专属） |
| 332 | `ACTION_SUWAKO_LILYPAD_6A` | 洩矢诹访子踩踏 6A |
| 400 | `ACTION_5B` | 5B |
| 401 | `ACTION_6B` | 6B |
| 402 | `ACTION_2B` | 2B |
| 403 | `ACTION_3B` | 3B |
| 404 | `ACTION_j5B` | j5B |
| 405 | `ACTION_j6B` | j6B |
| 406 | `ACTION_j2B` | j2B |
| 407 | `ACTION_4B` | 4B |
| 408 | `ACTION_66B` | 66B（冲刺 B） |
| 409 | `ACTION_j4B` | j4B |
| 410 | `ACTION_5C` | 5C |
| 411 | `ACTION_6C` | 6C |
| 412 | `ACTION_2C` | 2C |
| 413 | `ACTION_4C` | 4C |
| 414 | `ACTION_j5C` | j5C |
| 415 | `ACTION_j6C` | j6C |
| 416 | `ACTION_j2C` | j2C |
| 417 | `ACTION_j1C` | j1C |
| 418 | `ACTION_66C` | 66C（冲刺 C） |
| 419 | `ACTION_ALICE_4C` | 爱丽丝 4C（角色专属） |
| 420 | `ACTION_ORRERIES_B` | 玛丽莎「Orreries Sun」B 版 |
| 422 | `ACTION_AIR_ORRERIES_B` | 同名技能的空中 B 版 |
| 430 | `ACTION_ORRERIES_C` | 玛丽莎「Orreries Sun」C 版 |
| 432 | `ACTION_AIR_ORRERIES_C` | 同名技能的空中 C 版 |
| 500 | `ACTION_DEFAULT_SKILL1_B` | 必杀技 1·默认配置·地面 B |
| 501 | `ACTION_DEFAULT_SKILL1_C` | 必杀技 1·默认配置·地面 C |
| 502 | `ACTION_DEFAULT_SKILL1_AIR_B` | 必杀技 1·默认配置·空中 B |
| 503 | `ACTION_DEFAULT_SKILL1_AIR_C` | 必杀技 1·默认配置·空中 C |
| 505 | `ACTION_ALT1_SKILL1_B` | 必杀技 1·装配 1·地面 B |
| 506 | `ACTION_ALT1_SKILL1_C` | 必杀技 1·装配 1·地面 C |
| 507 | `ACTION_ALT1_SKILL1_AIR_B` | 必杀技 1·装配 1·空中 B |
| 508 | `ACTION_ALT1_SKILL1_AIR_C` | 必杀技 1·装配 1·空中 C |
| 510 | `ACTION_ALT2_SKILL1_B` | 必杀技 1·装配 2·地面 B |
| 511 | `ACTION_ALT2_SKILL1_C` | 必杀技 1·装配 2·地面 C |
| 512 | `ACTION_ALT2_SKILL1_AIR_B` | 必杀技 1·装配 2·空中 B |
| 513 | `ACTION_ALT2_SKILL1_AIR_C` | 必杀技 1·装配 2·空中 C |
| 520 | `ACTION_DEFAULT_SKILL2_B` | 必杀技 2·默认·地面 B |
| 521 | `ACTION_DEFAULT_SKILL2_C` | 必杀技 2·默认·地面 C |
| 522 | `ACTION_DEFAULT_SKILL2_AIR_B` | 必杀技 2·默认·空中 B |
| 523 | `ACTION_DEFAULT_SKILL2_AIR_C` | 必杀技 2·默认·空中 C |
| 525 | `ACTION_ALT1_SKILL2_B` | 必杀技 2·装配 1·地面 B |
| 526 | `ACTION_ALT1_SKILL2_C` | 必杀技 2·装配 1·地面 C |
| 527 | `ACTION_ALT1_SKILL2_AIR_B` | 必杀技 2·装配 1·空中 B |
| 528 | `ACTION_ALT1_SKILL2_AIR_C` | 必杀技 2·装配 1·空中 C |
| 530 | `ACTION_ALT2_SKILL2_B` | 必杀技 2·装配 2·地面 B |
| 531 | `ACTION_ALT2_SKILL2_C` | 必杀技 2·装配 2·地面 C |
| 532 | `ACTION_ALT2_SKILL2_AIR_B` | 必杀技 2·装配 2·空中 B |
| 533 | `ACTION_ALT2_SKILL2_AIR_C` | 必杀技 2·装配 2·空中 C |
| 540 | `ACTION_DEFAULT_SKILL3_B` | 必杀技 3·默认·地面 B |
| 541 | `ACTION_DEFAULT_SKILL3_C` | 必杀技 3·默认·地面 C |
| 542 | `ACTION_DEFAULT_SKILL3_AIR_B` | 必杀技 3·默认·空中 B |
| 543 | `ACTION_DEFAULT_SKILL3_AIR_C` | 必杀技 3·默认·空中 C |
| 545 | `ACTION_ALT1_SKILL3_B` | 必杀技 3·装配 1·地面 B |
| 546 | `ACTION_ALT1_SKILL3_C` | 必杀技 3·装配 1·地面 C |
| 547 | `ACTION_ALT1_SKILL3_AIR_B` | 必杀技 3·装配 1·空中 B |
| 548 | `ACTION_ALT1_SKILL3_AIR_C` | 必杀技 3·装配 1·空中 C |
| 550 | `ACTION_ALT2_SKILL3_B` | 必杀技 3·装配 2·地面 B |
| 551 | `ACTION_ALT2_SKILL3_C` | 必杀技 3·装配 2·地面 C |
| 552 | `ACTION_ALT2_SKILL3_AIR_B` | 必杀技 3·装配 2·空中 B |
| 553 | `ACTION_ALT2_SKILL3_AIR_C` | 必杀技 3·装配 2·空中 C |
| 560 | `ACTION_DEFAULT_SKILL4_B` | 必杀技 4·默认·地面 B |
| 561 | `ACTION_DEFAULT_SKILL4_C` | 必杀技 4·默认·地面 C |
| 562 | `ACTION_DEFAULT_SKILL4_AIR_B` | 必杀技 4·默认·空中 B |
| 563 | `ACTION_DEFAULT_SKILL4_AIR_C` | 必杀技 4·默认·空中 C |
| 565 | `ACTION_ALT1_SKILL4_B` | 必杀技 4·装配 1·地面 B |
| 566 | `ACTION_ALT1_SKILL4_C` | 必杀技 4·装配 1·地面 C |
| 567 | `ACTION_ALT1_SKILL4_AIR_B` | 必杀技 4·装配 1·空中 B |
| 568 | `ACTION_ALT1_SKILL4_AIR_C` | 必杀技 4·装配 1·空中 C |
| 570 | `ACTION_ALT2_SKILL4_B` | 必杀技 4·装配 2·地面 B |
| 571 | `ACTION_ALT2_SKILL4_C` | 必杀技 4·装配 2·地面 C |
| 572 | `ACTION_ALT2_SKILL4_AIR_B` | 必杀技 4·装配 2·空中 B |
| 573 | `ACTION_ALT2_SKILL4_AIR_C` | 必杀技 4·装配 2·空中 C |
| 580 | `ACTION_DEFAULT_SKILL5_B` | 必杀技 5·默认·地面 B |
| 581 | `ACTION_DEFAULT_SKILL5_C` | 必杀技 5·默认·地面 C |
| 582 | `ACTION_DEFAULT_SKILL5_AIR_B` | 必杀技 5·默认·空中 B |
| 583 | `ACTION_DEFAULT_SKILL5_AIR_C` | 必杀技 5·默认·空中 C |
| 585 | `ACTION_ALT1_SKILL5_B` | 必杀技 5·装配 1·地面 B |
| 586 | `ACTION_ALT1_SKILL5_C` | 必杀技 5·装配 1·地面 C |
| 587 | `ACTION_ALT1_SKILL5_AIR_B` | 必杀技 5·装配 1·空中 B |
| 588 | `ACTION_ALT1_SKILL5_AIR_C` | 必杀技 5·装配 1·空中 C |
| 590 | `ACTION_ALT2_SKILL5_B` | 必杀技 5·装配 2·地面 B |
| 591 | `ACTION_ALT2_SKILL5_C` | 必杀技 5·装配 2·地面 C |
| 592 | `ACTION_ALT2_SKILL5_AIR_B` | 必杀技 5·装配 2·空中 B |
| 593 | `ACTION_ALT2_SKILL5_AIR_C` | 必杀技 5·装配 2·空中 C |
| 600 | `ACTION_USING_SC_ID_200` | 使用符卡 ID 200 |
| 601 | `ACTION_USING_SC_ID_201` | 使用符卡 ID 201 |
| 602 | `ACTION_USING_SC_ID_202` | 使用符卡 ID 202 |
| 603 | `ACTION_USING_SC_ID_203` | 使用符卡 ID 203 |
| 604 | `ACTION_USING_SC_ID_204` | 使用符卡 ID 204 |
| 605 | `ACTION_USING_SC_ID_205` | 使用符卡 ID 205 |
| 606 | `ACTION_USING_SC_ID_206` | 使用符卡 ID 206 |
| 607 | `ACTION_USING_SC_ID_207` | 使用符卡 ID 207 |
| 608 | `ACTION_USING_SC_ID_208` | 使用符卡 ID 208 |
| 609 | `ACTION_USING_SC_ID_209` | 使用符卡 ID 209 |
| 610 | `ACTION_USING_SC_ID_210` | 使用符卡 ID 210 |
| 611 | `ACTION_USING_SC_ID_211` | 使用符卡 ID 211 |
| 612 | `ACTION_USING_SC_ID_212` | 使用符卡 ID 212 |
| 613 | `ACTION_USING_SC_ID_213` | 使用符卡 ID 213 |
| 614 | `ACTION_USING_SC_ID_214` | 使用符卡 ID 214 |
| 615 | `ACTION_USING_SC_ID_215` | 使用符卡 ID 215 |
| 616 | `ACTION_USING_SC_ID_216` | 使用符卡 ID 216 |
| 617 | `ACTION_USING_SC_ID_217` | 使用符卡 ID 217 |
| 618 | `ACTION_USING_SC_ID_218` | 使用符卡 ID 218 |
| 619 | `ACTION_USING_SC_ID_219` | 使用符卡 ID 219 |
| 650 | `ACTION_SC_ID_200_ALT_EFFECT` | 符卡 200 的里效果 |
| 651 | `ACTION_SC_ID_201_ALT_EFFECT` | 符卡 201 的里效果 |
| 652 | `ACTION_SC_ID_202_ALT_EFFECT` | 符卡 202 的里效果 |
| 653 | `ACTION_SC_ID_203_ALT_EFFECT` | 符卡 203 的里效果 |
| 654 | `ACTION_SC_ID_204_ALT_EFFECT` | 符卡 204 的里效果 |
| 655 | `ACTION_SC_ID_205_ALT_EFFECT` | 符卡 205 的里效果 |
| 656 | `ACTION_SC_ID_206_ALT_EFFECT` | 符卡 206 的里效果 |
| 657 | `ACTION_SC_ID_207_ALT_EFFECT` | 符卡 207 的里效果 |
| 658 | `ACTION_SC_ID_208_ALT_EFFECT` | 符卡 208 的里效果 |
| 659 | `ACTION_SC_ID_209_ALT_EFFECT` | 符卡 209 的里效果 |
| 660 | `ACTION_SC_ID_210_ALT_EFFECT` | 符卡 210 的里效果 |
| 661 | `ACTION_SC_ID_211_ALT_EFFECT` | 符卡 211 的里效果 |
| 662 | `ACTION_SC_ID_212_ALT_EFFECT` | 符卡 212 的里效果 |
| 663 | `ACTION_SC_ID_213_ALT_EFFECT` | 符卡 213 的里效果 |
| 664 | `ACTION_SC_ID_214_ALT_EFFECT` | 符卡 214 的里效果 |
| 665 | `ACTION_SC_ID_215_ALT_EFFECT` | 符卡 215 的里效果 |
| 666 | `ACTION_SC_ID_216_ALT_EFFECT` | 符卡 216 的里效果 |
| 667 | `ACTION_SC_ID_217_ALT_EFFECT` | 符卡 217 的里效果 |
| 668 | `ACTION_SC_ID_218_ALT_EFFECT` | 符卡 218 的里效果 |
| 669 | `ACTION_SC_ID_219_ALT_EFFECT` | 符卡 219 的里效果 |
| 669 | `ACTION_FANTASY_HEAVEN_ACTIVATE` | 幻想天生（霊梦）发动 —— 与上一条同值 |
| 690 | `ACTION_SKILL_CARD` | 使用技能卡 |
| 691 | `ACTION_SYSTEM_CARD` | 使用系统卡 |
| 692 | `ACTION_IBUKI_GOURD` | 伊吹瓢（萃香） |
| 693 | `ACTION_RECOVERY_CHARM` | 回复符 |
| 694 | `ACTION_MAGIC_POTION` | 魔法药 |
| 695 | `ACTION_TALISMAN` | 符咒 |
| 695 | `ACTION_BOMB` | 炸弹 —— 与 `ACTION_TALISMAN` 同值 |
| 696 | `ACTION_HANGEKI` | 反击（「反撃」） |
| 696 | `ACTION_DIVINE_RAIMENT_OF_THE_DRAGON_FISH` | 龙鱼的羽衣 —— 与 `ACTION_HANGEKI` 同值 |
| 697 | `ACTION_LEFT_HANDED_FOLDING_FAN` | 左手持扇（扇子系道具） |
| 698 | `ACTION_SPELL_BREAKING_DRUG` | 符卡破坏药 |

> 说明：`enum` 末尾没有逗号后的续项，`69x` 区即以 698 结束。

---

## 3. 指令记法（数字 = 小键盘方向）

非想天则通用记法，配合上表把「236B」这类招名翻译成编号：

```
7 8 9        7=后上  8=上    9=前上
4 5 6        4=后    5=中立  6=前        （方向相对角色朝向）
1 2 3        1=后下  2=下    3=前下
```

- 字母 = 攻击键：`A` 弱 / `B` 强 / `C` 弹幕 / `D` 飞・回避，`j` 前缀 = 空中版，`f` 前缀 = 远距离版。
- 因此 `236B` = `↓↘→ + B`，`623C` = `→↓↘ + C`，`2A` = `↓ + A`，`66B` = `→→ + B`。
- 上表第 3 列的「派生含义」是我按这个记法从常量名推导的标注（SokuLib 源码里只有常量名，没有中文/指令注释），可作为查询助记，但**不要当作游戏内官方命名**。
- 属同一招但需区分「地面 B / 地面 C / 空中 B / 空中 C」时：500–593 区每个必杀技有 12 个槽位 —— 4 个输入形态 × 3 种装配（默认 / ALT1 / ALT2），同一角色同一必杀技因装配不同会落在不同的编号上。

### 与 SokuAI 招式名的对应示例

SokuAI 的 `BaseAI::actions` 标签可直接反查编号（同角色同装配前提下）：

| SokuAI 标签 | 可能编号 | 备注 |
|---|---|---|
| `5a` | 300 | 站立 A |
| `2a` | 303 | 蹲 A |
| `6a` | 302 | 前 A |
| `66a` | 305 | 冲刺 A |
| `2b` | 402 | 蹲 B |
| `3b` | 403 | 斜下 B |
| `4b` | 407 | 后 B |
| `5b` | 400 | 站立 B |
| `6b` | 401 | 前 B |
| `66b` | 408 | 冲刺 B |
| `5c` | 410 | 站立 C |
| `2c` | 412 | 蹲 C |
| `6c` | 411 | 前 C |
| `66c` | 418 | 冲刺 C |
| `236b` / `236c` / `623b` / `623c` / `214b` / `214c` / `421b` / `421c` / `22b` / `22c` | **无法从招名直接得知** | 落在 500–593（必杀技）或 400 区角色专属项；取决于该角色把该指令装在哪个必杀技槽、以及 B/C 与地面/空中，必须结合角色与装配查表 |
| `be1/be2/be4/be6` | 222 / 220 / 224 / 223 | 弹幕回避 |
| `fly*` | 214（及 Suwako 218/219 等衍生） | 飞行 |
| `forward_dash` / `backward_dash` | 200 / 201 | 冲刺 |
| `forward_jump` / `backward_jump` / `neutral_jump` | 7 / 8 / 6 | 跳跃 |
| `forward_highjump` 等 | 209 / 210 / 208 | 大跳 |
| `crouch` / `block_low` | 1–2 / 150+ 或 159+ | 蹲 / 防御 |
| `use_current_card` | 600–619（按卡 ID） | 符卡，编号 = 600 + (卡ID − 200) |
| `upgrade_skillcard` | 690 | 技能卡 |
| `switch_to_card_*` | 无独立动作 | 仅切换选中卡，通常不产生新的 action |

> 注意：`236b` 这类指令**不能**直接推出编号。500–593 区是按「必杀技槽位 × 装配 × 按键 × 地面/空中」编号的，**编号里不含指令信息**。同一个 `236B` 在 A 角色可能是 500、在 B 角色可能是 540，甚至同一角色换个装配就从 500 变 505。要精确对应，必须查该角色/装配的技能配置（游戏内技能卡装配表），本表只能提供编号 → 语义，无法提供「指令 → 编号」。

### SokuLib 防御硬直参考卡（编号 ↔ 等级）

`150–157` 与 `159–166` 是同一套（正确/错误防御）的镜像结构，可按公式定位：

| 上段（High） | 正确防御 | 错误防御 |
|---:|---:|---:|
| 小 Small | 150 | 159 |
| 中 Medium | 151 | 160 |
| 大 Big | 152 | 161 |
| 特大 Huge | 153 | 162 |

| 下段（Low） | 正确防御 | 错误防御 |
|---:|---:|---:|
| 小 Small | 154 | 163 |
| 中 Medium | 155 | 164 |
| 大 Big | 156 | 165 |
| 特大 Huge | 157 | 166 |

`158` = `ACTION_AIR_GUARD`（空中防御，不分段位/等级）；`178–179` 未定义（enum 直接跳到 180）。

---

## 4. SokuAI 仓库内唯一的「编号 → 招式名」硬编码（反向表）

`Training/AITrainerScriptPY/ReactAI.py` 是 SokuAI 里唯一直接写死动作编号的地方，而且方向相反（编号 → 应对），且只覆盖**红美铃**一个角色：

```python
remilia_high_block_moves = [302, 306, 307, 308, 309, 320]
remilia_low_block_moves  = [301, 304]
...
if 300 <= op_state["action"] < 400:
    ...
if move == 304:
    return "be2"
```

对照第 2 节：302=`6A`、301=`f5A`、304=`3A`、306=`j5A`、307=`j6A`、308=`j2A`、309=`j8A`、320=`5AA`。也就是说这段逻辑实际含义是「对手用 A 系（300–399）时，按上/下段分类决定防御或 `be2` 回避」。它只覆盖 7 个编号、单角色、手工维护，**不构成通用对照表**。

---

## 5. 记录这个表时要避开的两个坑

1. **不要把 `600 + (卡ID - 200)` 与 SokuAI 的 `characterSpellCards` 混为一谈。**
   SokuAI 的 `Training/TrainingMod/sokuData.cpp` 里有 `characterSpellCards`，值是 200–219。那是**符卡卡牌 ID**（用于 `isDeckValid()` 校验卡组），不是动作编号。使用符卡的动作编号在上表 600–619，需要 +400 换算。

2. **不要用 SokuAI 的 `moveBlacklist` 去反推招名。**
   `OPCODE_RESTRICT_MOVES` 收的是动作编号，但 SokuAI 仓库内没有任何表来填充它 —— 值由服务端（AI 客户端）发包给出；同样的编号在不同角色/装配下含义不同，黑名单是逐角色、逐装配手工指定的。

---

## 6. 在 SokuAI 侧的使用位置（备忘）

| 位置 | 用法 |
|---|---|
| `Training/TrainingMod/state.cpp` | `destination.action = source.frameState.actionId;`（同处还有 `sequence = frameState.sequenceId;`、`pose = frameState.poseId;`）—— 编号来源 |
| `Training/AITrainerScriptCPP/Packet.hpp` | `SokuLib::Action action;` + `actionBlockId` + `animationCounter/SubFrame` —— 线格式；非 Windows 分支 `#include <Action.hpp>` |
| `Training/TrainingMod/Packet.hpp` | `struct CharacterState { ... unsigned short action; unsigned short sequence; unsigned short pose; ... }` —— 无类型裸数值 |
| `Training/TrainingMod/main.cpp` | `objectBase.action = SokuLib::ACTION_IDLE;`（= 0）复位黑名单命中项 |
| `Training/AITrainerScriptCPP/GameManager.cpp` | **仓库内唯一用符号名写动作编号的地方**：`restrictMoves({SokuLib::ACTION_FORWARD_DASH, SokuLib::ACTION_BACKDASH, SokuLib::ACTION_6A, SokuLib::ACTION_5A, SokuLib::ACTION_f5A})` —— 数值全部来自 SokuLib 的 enum，SokuAI 自己一个数字都没写 |
| `Training/TrainingMod/network.cpp` | `OPCODE_RESTRICT_MOVES` 处 `moveBlacklist.insert(...)` 填充编号黑名单 |
| `Training/AITrainerScriptPYTorch/Soku/Env.py` | `action=Bounded(low=0, high=799)`、`if me.action < 50 or 200 <= me.action < 220:` 判定待机 |
| `Training/AITrainerScriptCPP/NeuronAi.cpp` | `#define DIVISOR_ACTION 1000.f` —— 编号归一化后喂神经网络，**从不解析成名字** |
| `Training/AITrainerScriptCPP/ObjectsNeuron.cpp` | `#define DIVISOR_ACTION 65535.f`（弹幕/物件同样只归一化） |
| `Training/AITrainerScriptCPP/BaseAi.cpp` | `BaseAI::actions` 招式名标签 + `actionsBuffers` 按键序列（**与编号无关**） |
| `Training/AITrainerScriptPY/ReactAI.py` | 第 4 节所述的 7 个硬编码编号（唯一反向表） |
| `Training/AITrainerScriptPYTorch/Soku/characters.py` | 角色 ID 0–36（**不是**动作编号，注意别混） |

---

## 7. 溯源备忘

- **README 自己把动作表甩给了 SokuLib**：`2 bytes: Soku action (List [here](.../SokuLib/blob/51486a0.../src/Core/CharacterManager.hpp#L25))`。该链接指向的是**更旧的 commit `51486a0`**（当时 `CharacterManager.hpp` 第 25 行就是 `enum Action : unsigned short {`），而子模块实际锁定的是 `09fed348`（那时 enum 已拆到独立的 `src/Action.hpp`）。查表请以子模块锁定的 `09fed348/src/Action.hpp` 为准。
- **`characterSpellCards` 在仓库里有三份副本**：`Training/TrainingMod/sokuData.cpp`、`Training/OfflineVersusMod/main.cpp`（内容相同）；`OnlineHostMod/main.cpp` 里是第三份 `std::map<SokuLib::Character, std::array<unsigned short, 20>>`，多数为空，红美铃一项是真实 20 张卡组 `{100,100,100,100,102,102,105,105,105,105,203,203,204,204,205,205,206,206,209,209}`（卡牌 ID，会喂给 `leftPlayerInfo.effectiveDeck`）。三份都是**卡牌 ID**，都不是动作编号。
- SokuAI 仓库 `has_wiki=true` 但 `/wiki` 会重定向回仓库首页（无内容）；`issues` 为空数组（0 条）。没有额外文档可挖。

---

*本文件由对 SokuLib `src/Action.hpp` @ `09fed348` 的逐行解析生成；编号与常量名一一对应，未做任何省略。若需升级到更新的 SokuLib 版本，请以新 commit 的 `Action.hpp` 为准重新核对。*
