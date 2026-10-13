# 审计报告: rep 数据采集链从严审查(2026-10-13, 用户裁定修订版)

- **基线**: commit `ac8ba8b`(HEAD; 工作区干净)。审查对象: rep 采集全链
  (tools/expert_harvest_tr.py / oracle_batch2.py / scan 选角过滤 /
  bc_build.build_rows 消费 / docs/rep_format_notes.md 格式依据)。
- **审计时刻**: 2026-10-12 深夜~10-13; **双边过夜批正在运行中**
  (`--kind both` 与降速 fleet 并存), 审计全程只读未干扰。
- **修订记录**: 初版曾将"'ours' 单边无高手侧判定"列为 P1 设计缺口;
  **用户裁定(2026-10-13 原文回显): "双方都是顶尖高手,这个不用担心"** —
  该假设为真, P1 撤销, 'ours' 通道按原设计可用(裁定入档, 后续采集
  不再以此为由设卡)。
- **与上一份归档差异**(audit_2026-10-12_from_zero_3): R80 已修 #3 全部
  P1 六项(独立确认); 本报告为专项(采集链), 非增量全库。

## 总判定: **能发挥目的功能**(双边通道实测达标; 'ours' 通道经裁定无碍)

**实测通过项**(采集目的 = 专家输入+全量状态流喂 BC 重建):
1. **选角过滤正确性**: scan 的 b[14]/b[63] 与 parse_rep_file.char_x/y
   交叉验证 20/20 零不符 — 角色筛选无偏。
2. **产物结构自洽**: 抽查 shard 帧尺寸 min 215B=105+105+4+1+0 恰合格式
   下界; inputs/ilog/rounds/meta 齐全; **ilog 覆盖 232/234(99.1%)**,
   ilog 行数与帧数精确相等(R40 同帧对齐达成)。
3. **去重与断点**: manifest md5 零重复; 放弃不记档 → 下轮自愈重采;
   shard 落盘 tmp+os.replace 原子 ✓。
4. **消费选边正确**: bc_build.build_rows 按 char_x/char_y 分别走左/右
   路径, 右侧镜像(frames+input), 无"恒左"错配 — 双边 shard 双侧皆可用;
   'ours' 单边同理可用(两侧均顶尖, 任意一侧皆为有效专家信号)。
5. **隔离纪律**: mod 切换作用于隔离副本 rl_game 的 ML(非训练目录),
   finally 逐字节恢复; 硬杀残留也不污染训练。
6. **进度健康**: tr 235 局 / 0 err / 270 万帧(12.1h@62fps), 过夜批进行中。

## 发现(修订后)

| # | 级 | 发现 | 证据 |
|---|---|---|---|
| 1 | P2 | R81b 只修 harvest 侧; oracle_batch2.main:145 同型兜底 `rep = parse_rep_file(path)` 仍无保护 — 截断 rep 在旧通道会崩批(旧库已采完, 实际风险低, 对称性欠账) | 两文件对照 |
| 2 | P2 | run_one 失败后的离线兜底 parse 是死代码: offsets 恒空 → 必被 `len(offsets)<=100` 闸拒, 只改放弃文案, 不产出 shard — 误导读者以为有离线采集能力 | 代码路径推演 |
| 3 | 观察 | 2/234 shard 无 ilog → bc_build 走旧互相关对齐(±24 帧残余, R40 已知), 有 ALIGN_PASS_MIN 拒收兜底 | manifest 统计 |

## 建议(待用户指令, 审计不修)

- oracle_batch2 同型保护补齐 + 死代码兜底清理(顺手波)。

## 修复记录(2026-10-13, 采集链专项后随手波)

两笔 P2 均已修: ①oracle_batch2.main 同型兜底 parse 删除(截断 rep 不再
可能崩旧通道); ②死代码兜底清理 — harvest/oracle_batch2 两处 except 分支
的 parse 全删(err 置位+offsets 恒空 → 闸必拒 → 放弃, parse 结果从不被
消费; harvest 侧合并为单闸)。观察项#3(2/234 无 ilog)按 R40 已知取舍
维持, ALIGN_PASS_MIN 兜底在位。用户裁定(双方皆顶尖)已入档。
