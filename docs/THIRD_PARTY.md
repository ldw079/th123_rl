# 第三方来源与许可清单（THIRD_PARTY）

> **状态**: 施工起草（2026-10-18），待规划侧确认后并入 `docs/INDEX.md` 登记。
> 依据: 公开化方案 Phase 4 + 宪法 R4「不猜数据 / 来源必须实际取自」。
> 本文件只列**外部来源**；本仓库原创代码与文档的许可见根 `LICENSE`(MIT)
> 与 `docs/LICENSE-docs.md`(CC BY 4.0)。

## 0. 一句话结论

本仓库**不分发**任何游戏本体、第三方 mod、第三方代码包或训练数据（见
`docs/DATA_POLICY.md`）；仓库内出现的第三方内容只有三类：**引用的事实性数据
（帧数据/动作编号/攻略结论）**、**来源标注**、以及**为可复现而 vendored 的自有包**
（`soku_arch/`，见其 `VENDORED.md`，非第三方）。

## 1. 数据来源

| 来源 | 内容 | 使用方式 | 许可/条款 | 落档位置 |
|---|---|---|---|---|
| **soku.cleista.cc/framedata** | 20 角色帧数据（发生/全体/防御优势/伤害/逐帧属性窗/蓄力版/System actions） | 用户 2026-10-14 裁定为**权威帧数据源**(R4)；经其 llms.txt 公共 JSON API 抓取（≤50 请求/分 < 站点 120/分上限、ETag 缓存、一次性落盘、逐个文件署名 `source=cleista`） | 站点公开数据，使用须遵守其 `llms.txt` 条款与署名要求；**不转售、不整体镜像** | `data/guide_tables/cleista/`（`api/`+`detail/`+`non_main_charge.json`），文件内 `source` 字段逐条标注 |
| **wikiwiki.jp/th123ai** | 引擎语义表：`fflags`/`aflags` 逐位含义、动作值全表、obj-ID 対応表、`get_special_data` | 用户 2026-10-17 裁定为**第二权威源**，与 cleista **分域**（cleista=帧数据，wiki=引擎标志/动作分类）；wiki 标注"解析中"的位**不得当定论**，采用前须实测交叉 | 社区 wiki（公开），引用须注出处；**未确认位标 unverified** | `docs/th123ai_community_ai_analysis_2026-10-16.md §7`、`docs/game_semantics_tables.md` |
| **CHM 中文攻略集成包** | 各角色攻略正文（起手/连段/择/压起身/警戒表等） | 早期为主要来源；cleista 到位后**降为交叉验证源**；只提取结论与输入序列，不整段引用原文 | 攻略文本版权归原作者；本仓库只保留**结论性摘要与出处锚点**，不镜像原文 | `data/guide_tables/fangyu_counters.json`、`data/guide_tables/matchup_combo_prior.json`（含 `guide_quote`/`guide_doc`） |
| **SokuLib**（`github.com/SokuDev/SokuLib`） | 动作编号枚举 `src/Action.hpp`（`enum Action : unsigned short`） | 只取**枚举值**（事实性数据）；锁定 commit `09fed348bf71ce7466093d0bce7505f903723147`（2025-03-22, PinkySmile），并记录 blob sha `1b6eaf8f8aad81cf50b40d536ee167a29f51f367` | **MIT**（GitHub API `repos/SokuDev/SokuLib/license` 实测 2026-10-18） | `docs/soku_action_ids.md`（头部钉仓库+commit+作者+blob） |

## 2. 仅作分析、未采纳代码的来源

| 来源 | 用途 | 边界 |
|---|---|---|
| **th123ai 社区 AI**（wikiwiki.jp/th123ai + 其发布物） | 对标分析：RPM 观察方式、键盘输入、Lua 脚本结构、2011 公平垫片先例、偏移地图 | **只读分析**，未拷贝其代码入库；结论落 `docs/th123ai_community_ai_analysis_2026-10-16.md`；若未来采纳代码须按上游许可处理 |
| **东方非想天则（Touhou 12.3 Hisoutensoku）** | 被训练的游戏本体 | © 黄昏フロンティア / 上海アリス幻樂団。**本仓库不分发游戏本体、模型权重、回放或任何游戏资产**（`docs/DATA_POLICY.md`）；用户须自行合法持有游戏 |
| **自制 mod（SokuAITrainer / MemoryPatch 等）** | 训练通道（TCP 锁步 + 内存只读） | 本项目自制，**不在本仓库分发二进制**；血统由 `tools/mod_provenance.json` 钉 MD5（门禁 C9） |

## 3. 软件依赖

`requirements.txt` 内为公开 PyPI 包（PyTorch / NumPy 等），各自遵循其上游许可；
本项目不修改、不再分发其源码。**非 pip 依赖**（便携 Python、游戏本体、自制 mod）
见 `README.md`「已知状态」段。

## 4. 本仓库自身许可

| 对象 | 许可 | 文件 |
|---|---|---|
| 代码（`*.py`，含 `soku_arch/`） | **MIT** | [`LICENSE`](../LICENSE) |
| 文档（`*.md`） | **CC BY 4.0**（仅覆盖原创整理与注释，**不覆盖**上述第三方数据/结论原文） | [`docs/LICENSE-docs.md`](LICENSE-docs.md) |
| 训练数据 / 模型权重 / 回放 | **不提供** | [`docs/DATA_POLICY.md`](DATA_POLICY.md) |

## 5. 待办（规划侧）

1. 把本文件登记进 `docs/INDEX.md`；
2. `docs/LICENSE-docs.md` 已加"CC BY 4.0 仅覆盖原创整理"限定句（施工 2026-10-18）；
3. 若后续引入任何第三方**代码**（非枚举/数据），必须在此登记 `来源/许可/加工程度`。
