# JZ-2b 宏时序审计（首两角色）— 2026-10-14 晚

> 数据源: cleista帧数据库(用户裁定权威源, data/guide_tables/cleista/
> {reimu,suika}.json — 用户手工提取件按内容归位, 文件名互换已记录)。
> 口径: 宏**注释**中的帧数声明逐条对照站发生帧; **脚本时序**(输入模式)
> 本轮不动 — 输入模式匹配专家rep行为, 时序重调需hitlab共同验证
> (裁定: 与hitlab出入并列上报不自动取舍)。

## 萃香(suika) — 8条注释声明对照

| 宏 | 注释 | 站 | 判定 | 处置 |
|---|---|---|---|---|
| 5A | 9F | 9f | ✓ | — |
| 2A | 10F | 9f | ✗ 差1 | 注释修9F(全体29→28) |
| 3A | 25F | 19f | **✗✗ 差6** | 注释修19F(全体62→54) — CHM派生错值实证 |
| 5B | 17F | 15f | ✗ 差2 | 注释修15F(全体44→42); 蓄力5[B]=30f替换旧32F口径 |
| 6B | 18F | 18f | ✓(hitlab修复) | — |
| 5C | 22F+30F爆炸 | 52f | 语义差异非错误 | 注释改双值(弹体22F/主判定52F), 站startup记爆炸 |
| jA | 9F | 9f | ✓ | — |
| j6A | 12F | 12f | ✓ | — |

方案登记的"萃香已知3处偏差"=3A/2A/5B, 全部命中并已修注释。

## 灵梦(reimu) — 无可矛盾项

宏注释无"发生NF"式帧数声明(描述性注释为主), 站数据
(5A=8f/5B=15f/5[B]=31f/5[C]=50f...)已入cleista缓存供后续
宏时序标定使用。

## 蓄力宏阈值替换(CH-2裁定执行)

- 萃香: 5B蓄 完成点30(hold34)/jB蓄 29(hold33) — 替换旧32F注释口径
- 灵梦: 5B蓄31/6B蓄30/jB蓄31/j2B蓄30/5C蓄50/jC蓄43/j2C蓄46
  (hold=+4) — **全部替换extrapolated_from_suika外推**
- 魔理沙: 站数据未取得(反爬), 5招保持36F外推占位显式标注
  `source=extrapolated_from_suika`, 补采后替换

## 系统动作区交叉验证(意外收获)

萃香System actions枚举无敌窗与既有JZ-2表互相印证:
- KNOCKED_DOWN_STATIC 1-10f全无敌 = 起身投技无敌10F(throw_invuln)✓
- NEUTRAL/FORWARD/BACKWARD_HIGH_JUMP 擦弹1-21f = 大跳被康窗21F
  (jump_recovery_windows)✓
- 三tech无敌窗1-48/36/15f = 受身窗实证(airtech 15F口径扩充)✓

## 补采完成(2026-10-14晚, API直连)

作者开放public JSON API(https://soku.cleista.cc/llms.txt, 限速120/分,
ETag, 只许JSON不抓HTML) — **20/20角色全量入档**
data/guide_tables/cleista/api/(build 8bd50f33, 1000+招式行, 出处+署名齐全);
魔理沙蓄力真值经?charged=1端点取得: 5B/6B=28, **2B=12**(外推36错24F),
j.5B/j.2B=31, 5C=47, j.5C=48 — charge_table外推全部清零, 三主力全真值。

## 待办

1. ~~魔理沙补采~~ ✓ ~~剩余17角色~~ ✓(API全量)
2. 非主力角色蓄力宏(charge_table扩展)与JZ-2b注释审计随下波
3. 宏脚本时序重调(需hitlab同窗验证, 列JZ-2b二期)
