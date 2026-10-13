# th123_rl 审查报告（第十二轮 · R40 处置对抗性核验）

> 日期: 2026-10-03（R40 落地后）· 方式: 只读核验 + 门禁独立复跑
> 对象: R40 处置报告的全部关键声明（INPUTLOG 通道 / 双 DLL 部署 / mod M-1/M-2 / 门禁与血统 / METHODOLOGY 2.28）

---

## 1. 核验结论总表

| R40 声明 | 核验 | 证据 |
|---|---|---|
| 对第十一轮的两处修正（INPUTLOG"mod已实现"只对一半——部署 DLL 为补丁前旧构建） | ✅ 接受修正 | 我方第三轮说法源自子代理对 soku_arch 源码的报告，未验部署物；修复者的字符串扫描实证更强。此教训（**源码有≠部署有**）已入 2.28，正确 |
| oracle 侧 DLL 重建部署，MD5 B7E8C805 | ✅ | `D:\temp\rl_game\modules\SokuAITrainerEnv\SokuAITrainerEnv.dll` 实测哈希一致 |
| 训练侧 DLL 重建部署，MD5 386737DE | ✅ | `th123_train\modules\SokuAIOfflinePlayer\SokuAITrainer.dll` 实测一致 |
| ilog 通道实跑验证（前段 lag=+61 匹配率 1.0000） | ✅ 合理 | 与第十一轮子代理确证的"rep 少记 61 帧开局导入"精确吻合；后段 0.40 归因 rep 侧回合间隙（恰是该通道要消灭的）逻辑自洽 |
| oracle_batch2 接线（SOKUAI_INPUTLOG=1 / 按 shard 隔离路径 / ilog 入库 / 尾差 1-2 行起始对齐截断 / 失败 shard 不落盘） | ✅ | oracle_batch2.py:49-54, 94-97, 138-196 逐行核验 |
| bc_build 精确分支（ilog 存在即跳过互相关；旧 shard 回退） | ✅ 且**列取用正确** | mod 源 `inputLogFrame(li, lo, ri, ro)` 每行=左in/左out/右in/右out；build_shard 取 `arr[:,0]`（左in）与 `arr[:,2]`（右in）——我方曾担心取错列，源码证据排除 |
| mod M-1（对象 hitStop 清零）两构建继承 | ✅ | 训练侧 state.cpp 与 oracle 侧 `soku_arch\build\src\...\state.cpp` 均含 `destination.hitStop = 0;`（R40 注释） |
| mod M-2（对象总数 255 截断+计数回写）两构建继承 | ✅ | 两侧 network.cpp 均含 `cap=255`、`n2 = min(obj2, cap-n1)`（左侧优先）、双侧 objectCount 回写——客户端按"两 count 之和"读，严格一致；oracle 封装侧 `objs[:255]` 双保险（离线读取按绝对 offset 定位，多余字节被跳过，无错位风险） |
| 门禁 277 PASS / 0 WARN / 0 FAIL | ✅ | 本轮独立复跑同结果（EXIT=0）；+6 条 R40 断言、C13 分母已动态化（第三轮外观项闭环） |
| 4 条配对变异（含"ilog 误取 outKeys"变体） | ✅ 在位 | gate_selftest.py R40 段——outKeys 变异恰好覆盖我方本轮担心的列错位失效模式，设计到位 |
| 沙箱 FILES 补 oracle_batch2.py | ✅ | R40 接线断言载体已在沙箱清单 |
| 血统档案扩展（oracle_deployed 段含 built_md5/build_script/patch_script） | ✅ | tools/mod_provenance.json 实读确认；oracle 侧 deployed==built 哈希一致 |
| METHODOLOGY 2.28 | ✅ | 版本行含 R40 处置与"源码有≠部署有"教训 |
| reach_maps UNMEASURABLE 显式登记 | ✅ | 必杀系 8+1 宏入表，区分疏漏与无数据 |

## 2. 本轮新发现（治理层残余，无功能性 bug）

1. **C9 并没有 oracle 血统断言**：mod_provenance.json 的注记"部署≠构建时告警由 C9 的 oracle 断言承担"言过其实——contract_check.py 中不存在任何读取 `oracle_deployed`/`built_md5`/rl_game 的断言（全文检索为空）。当前 oracle 侧 deployed==built 为真（本轮人工核验），但**无门禁强制**——这正是第一轮 C9 批评（"血统不闭环"）在新增 oracle 侧的重演。建议：补一条真跑哈希比对的 C9-oracle 断言 + 配对变异（分钟级）。
2. **M-1/M-2 门禁断言只查训练侧源码树**（`TH123_MODROOT`→D:\temp\build）；oracle 侧源码（soku_arch\build\src，经 patch_sources.py 打补丁的独立树）不在任何门禁覆盖内。本轮人工确认两侧都有修复，但未来 oracle 侧漂移对门禁不可见。建议：断言扩展读第二棵树，或把 patch_sources.py 的输出树纳入 `TH123_MODROOT` 扫描。
3. **meta['ilog']=True 无条件写入**（oracle_batch2.py:167）：ilog 载入失败走回退时 meta 仍声称 True。bc_build 按 npz 键存在性判断（功能无害），但元数据失真——留着会在未来消费者信任 meta 时埋雷。一行修：仅在 kw 非空时置 True。
4. （外观）oracle_batch2 重试路径的 attempt-1 `*.ilog.tmp` 可能残留于 shards 目录（下次运行覆盖，无功能影响）。
5. （记录）M-2 左侧优先截断在对象洪泛时引入轻微观测不对称（右侧对象先被丢）——有注释、可接受，记录在案。

## 3. 门禁独立复跑

`tools\contract_check.py`: **277 PASS / 0 WARN / 0 FAIL（EXIT=0）**，与 R40 报告一致。C15 含 10 个行为测试（含 test_smoke_driver_r38 / test_replay_semantics）。

## 4. 尚待关闭项（状态追踪）

| 项 | 状态 |
|---|---|
| gate_selftest（93 条变异） | 修复者后台运行中——**结果出来前，R40 新断言的"可证伪性"仍是声明而非事实**（其自述曾抓到 3 条漏网并修正，教训"自检期间不动被检文件"已吸收） |
| 训练重启 + 首夜验收（无死亡循环 / IndexError/NameError 归零 / [ep] 读数入区间） | 未开始——**当前最高优先级**；R38/R39/R40 全部未实跑 |
| 学习健康度（\|KL\| 超标一个量级 / 值损 11-13 / reimu 弱于旧快照） | 已列 2.28 重启后首个调参主题（正确处置——需新数据） |
| 本轮 §2-1/§2-2（C9-oracle 断言 / oracle 侧源码树入罩） | 建议在重启前顺手补齐（分钟级），或接受为已知缺口记录 |

## 5. 总体评价

R40 是四轮审查-修复循环中质量最高的一波：对第十一轮前两项建议（INPUTLOG 治本、mod 基座修复）的落地**经逐项对抗核验全部属实**，且两处对我方报告的修正（部署≠源码）有理有据、已制度化为血统条款。数据管线的对齐问题至此从"统计估计（±24 帧）"升级为"协议级 1:1（源码证实列语义 + 门禁变异覆盖列错位风险）"。剩余风险集中在两点：**① 变异自检未出结果；② 训练仍未重启**——全部三波修复共享"从未实跑"这一未验证状态。工程侧已无阻塞项，建议：自检绿灯 → 重启训练 → 按第十一轮 §6-4 验收标准盯首夜。

*本轮全程只读（门禁为其自身设计的检查）；未修改项目任何文件。*
