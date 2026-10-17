# 公开化改造方案（PR-0..PR-5）— 2026-10-17

> 触发: 仓库已上 GitHub（ldw079/th123_rl，private，main+planning），
> 用户要求改造至适合切 public。
> 格式: 遵循 PLANNING_AGENT.md 三段式。编号前缀 **PR-**（public release）。
> 性质: **审计已完成的可执行转化**——审计证据见 §①，改造动作见 §②，
> 切换 runbook 见 §③。

---

## ① 现状核验（敏感性审计，2026-10-17 完成）

| 检查项 | 方法 | 结果 |
|---|---|---|
| 历史密钥 | 全部 1311 个历史 blob（34MB）单流正则扫描（ghp_/github_pat_/PRIVATE KEY/AKIA/sk-ant-/sk-proj-） | **零命中** ✅ |
| 工作树凭据 | git grep 全树（api_key/password/token/secret 等） | 仅宏记号与按键名误报，无真实凭据 ✅ |
| 公网 IP/端点 | 全树 IPv4 正则 + fleet/hub/kit/actor/side_driver 的 URL 扫描 | 无公网 IP、无外部端点（全部本机/环境变量注入） ✅ |
| 邮箱/手机/微信/QQ | 全树正则 | 零命中 ✅ |
| 第三方代码拷贝 | th123ai/SWRSAddr/hisoutensoku 引用定位 | 引用全为文档级（分析/计划/工具读外部路径）；**仓库内无社区 Lua/源码拷贝** ✅ |
| 游戏资产 | 入库文件类型普查（411 py/124 md/42 json/12 bat/2 npz） | 无游戏本体/解包资源/rep 文件；入库的 action_tables/reach_maps 为**帧数据事实表**（社区公开同款: cleista/wikiwiki 均公开发布）✅ |
| 大产物 | .gitignore | data/（BC 库/模型档）、dist/、frames/、_archive 大文件均已排除 ✅ |
| **Windows 用户名 <name>** | 全树计数 | **98 文件/108 处**（约 90 处在 _archive 冻结区；活文件约 15: HANDOVER/runbook/2 plan/3 review/~10 py 默认路径）；且**遍布全历史**（路径引用进入提交信息与文档） ⚠️ |
| LICENSE | 根目录 | **不存在**（public 默认"保留所有权利"，访客零合法复用权） ⚠️ |
| README | 人工读 | 面向内部（.bat 快速开始/本机路径），公开可读但缺"访客视角"说明 ⚠️ 轻度 |

**审计结论**: 无任何 must-fix 级安全阻塞项（无密钥/无 PII/无侵权资产）；
三个待决/待办项为用户名暴露面、LICENSE 缺失、README 访客视角。
**历史无需因安全问题重写**。

---

## ② 可执行方案

### 层次 A: 立即执行（改造本体，≈0.5 人日）

**PR-1 LICENSE 决策与添加**（需用户裁定，见 §④ 决策 1）
- 推荐: 代码 MIT + 文档 CC-BY-4.0 双列（docs/ 含大量方法论与社区
  逆向表格的转引，CC-BY 的署名要求与我们的"来源标注"实践一致）;
- LICENSE（MIT）+ docs/LICENSE-docs（CC-BY-4.0）+ README 徽标行。

**PR-2 用户名脱敏（工作树机械替换，历史保留——见 §④ 决策 2）**
- 替换规则（三档）:
  - `C:\Users\<name>\Desktop\workplace\th123_rl` → `<repo>`（文档叙述处）或 `.`（示例命令处）;
  - `C:\Users\<name>` → `%USERPROFILE%`（.bat/可执行脚本）;
  - 其余 `<name>` 逐个人工过目（预计 <10 处实质引用）;
- 范围: 活文件 ~15 个（HANDOVER/runbook/plans/reviews/约 10 py）;
  **_archive 冻结区不动**（历史文物，替换无意义且添乱）;
- 执行方: 代码侧（py/bat）= 施工（经队列），文档侧 = 规划;
- 注意: py 中的路径多为**运行时默认值**，替换成 `os.path.expanduser("~/...")`
  或保持显式相对路径时须逐处验证不破坏本机三 worktree 运行（施工门禁）。

**PR-3 README 访客视角段**（0.1 天）
- 头部加一段: 项目性质（研究型 RL 项目/62 帧游戏约束/教学模型目标）、
  复现须知（需要 th123 游戏本体+mod+Windows，data/ 不分发——
  BC 语料与模型档含游戏对局衍生数据，不入库不分发）、
  内部文档体系导读（METHODOLOGY 宪法/HANDOVER 接手/INDEX 索引）;
- "快速开始"节前加醒目框: 本节面向维护者本机环境，访客参考
  docs/fleet_ignition_runbook.md 的通用步骤。

**PR-4 数据分发边界声明**（0.1 天）
- README 或 docs/ 新增 `DATA_POLICY.md` 一句话版: 训练数据
  （replay 语料/模型权重/转储帧）不在本仓库分发；帧数据表
  （action_tables/reach_maps）为社区公开事实数据的整理产物，
  来源与权威源（cleista/wikiwiki/CHM）已在 docs 内标注。

### 层次 B: 用户决策项（§④，决策后 ≤0.5 天执行）

**PR-5 历史重写（仅当用户裁定 <name> 须从历史移除）**
- 工具: `git filter-repo --replace-text`（规则=PR-2 同款）;
- 代价与副作用（全都要走一遍）:
  1. 全部 commit 哈希变化 → 控制臂 D:/temp/th123_rl_control 钉的
     46920e9 失锚（须先以新哈希重钉: 在重写后仓库按日期序定位对应
     提交，**重钉后跑一次身份校验**——比对树哈希而非提交哈希）;
  2. planning 分支与 main 同步重写 + 双分支 force-push;
  3. 三个 worktree 全部重新 clone/重置（施工窗口执行，避开 BH-4.4）;
  4. GitHub 侧旧哈希可能残留在 PR/issue 引用与 API 缓存（新仓库无
     PR 历史，影响≈0）;
- **不裁定时默认不做**（审计已确认用户名是唯一历史暴露物，属
  低敏感个人信息: Windows 账户名，非姓名/邮箱/手机号）。

### 层次 C: 切换与切换后（§③ runbook）

无代码动作，纯运维。

---

## ③ 验收途径

| 组件 | 验收 | 判据 |
|---|---|---|
| PR-1 | LICENSE 双文件 | LICENSE(MIT)+docs/LICENSE-docs(CC-BY-4.0)+README 徽标行; 施工提交 |
| PR-2 | 脱敏提交 | 活文件 <name> 计数=0（_archive 除外）; 三 worktree 门禁全绿; bat 在本机实跑一遍冒烟 |
| PR-3 | README v2 | 访客段+复现须知+维护者框三要素齐 |
| PR-4 | DATA_POLICY | 一页内说明数据边界与帧表来源标注 |
| PR-5（条件） | 历史重写 | 重写后全历史正则复扫 <name>=0; 控制臂重钉+树哈希校验; 双分支 force-push 成功 |
| 切换 runbook | public 生效 | §③ 步骤全过 |

### 公开切换 runbook（用户操作，5 分钟）

1. 前置确认: PR-1..4 已合入 main 并推送（`git ls-remote` 与本地一致）;
2. GitHub 网页 → Settings → General → 拉到底 Danger Zone →
   **Change repository visibility → Make public**（输仓库名确认）;
3. 切换后立即检查（施工或规划任一方）:
   - `gh repo view ldw079/th123_rl --json visibility` = PUBLIC;
   - 匿名视角抽查: 隐身窗口开仓库页，确认无登录也可见、
     README 渲染正常、无意外大文件出现在文件树;
   - Issues/Discussions 开关按用户偏好设置（建议 Issues 开、
     Discussions 关——维护带宽有限）;
   - Settings → Social preview 上传一张预览图（可选）;
4. 观察期（切换后 48h）: 关注 fork 数异常增长（爬虫式批量 fork
   通常无恶意但值得知道）、Issues 首批提问。

### 红线自检

零训练数据出库（data/ 维持排除，PR-4 反而强化边界声明）; 不删改
_archive 历史（除非 PR-5 被裁定且单独执行）; LICENSE 涉及社区
衍生内容时**只声明我们整理的部分**（帧数据事实本身属公共领域级
事实数据，来源标注义务在 docs 已履行）; 三 worktree 运行不因
PR-2 路径替换而破坏（施工门禁把关）; 切换 public 是用户手动操作
（智能体不代按 Danger Zone）。

---

## ④ 用户决策项（2 项）——**已裁定（2026-10-17）**

1. **LICENSE**: ✅ 裁定 A = **MIT(代码) + CC-BY-4.0(文档) 双列**。
2. **用户名 <name>**: ✅ 裁定 B = **全历史重写**（PR-5 执行）。
   替换规则（filter-repo replace-text, 全 blob+消息）:
   - `C:\Users\<name>` → `%USERPROFILE%`
   - `C:\\Users\\<name>`（JSON 转义形态）→ `%USERPROFILE%`
   - `C:/Users/<name>` 与 `/c/Users/<name>` → `%USERPROFILE%`
   审计佐证: 非路径形态的 <name> 仅 1 处（INDEX 自引用, 已改）;
   提交信息零命中; 提交者身份为通用代理名（zcode/th123-rl）,
   **无姓名/邮箱暴露, 无需 mailmap**。

---

## 修订记录

| 日期 | 版本 | 说明 |
|---|---|---|
| 2026-10-17 | v1 | 审计完成（历史零密钥/无 PII/无侵权资产）; PR-1..5 分层; 2 项用户决策; 切换 runbook; 默认路径=工作树脱敏+历史保留 |
| 2026-10-17 | v2 | 用户裁定落档（MIT+CC-BY-4.0 / 全历史重写）; PR-1/3/4 内容批次执行（LICENSE/LICENSE-docs/DATA_POLICY/README 访客段）; PR-5 重写规则定稿（含 JSON 双反斜杠变体; 验收=重写后全历史 <name>=0） |
| 2026-10-17 | v3 | **PR-5 执行完毕**: filter-repo 四变体替换+计划书自引用折叠, 重写后 1318 blob 账户名=0 ✅; main→a0a27e7 / planning→2dd82c5 已 force-push 并远端验证; 控制臂映射 46920e9→ef7f92f（本地 worktree 不动, 旧对象经 worktree HEAD+pre-rewrite-backup 保活）; 遗留=PR-2 余项（~10 py 工具默认路径现为 %USERPROFILE% 字面量, 需 expandvars 适配+2 测试核对, 见队列条目 6）; **切 public 前仅剩 §③ runbook** |
| 2026-10-17 | v4（**审计侧 §1 更正 + 用户裁定 D1-D4**）| ①**更正 v3 两处结论**：v3「无 PII」只对 96120 一族成立——另有**另一台机器用户名 6 行 + 第三方玩家昵称 37 行**（tracked 且在 main 历史）；v3「切 public 前仅剩 runbook」实际还差 PR-6/7/8 ≈1.8 人日（见 docs/audit/audit_2026-10-17_public_release_remediation_plan.md）。②**实测新事实（施工 2026-10-17 22:4x）**：`gh api` 与匿名 API 双证 `ldw079/th123_rl` 当前 **visibility=PUBLIC**（审计 §1 记为 private 的前提已不成立）→ PR-6 从「切 public 前必做」升级为**已暴露止血项**。③**用户裁定（2026-10-17）**：D1=**A** 一次性全历史重写清 PII / D2=**A** soku_arch vendor 入库 / D3=**A** 重写时一并剔除 _archive / D4=**B** 会话JSON匿名化保留结构（保 new_reps 长度）。④PR-2 余项**已由 R170 以「仓库相对/文件位置派生」口径清偿**（不用 expandvars，见 METHODOLOGY 3.60）。 |
| 2026-10-18 | v5（**PR-6/PR-7 执行 + 第二次全历史重写**）| ①PR-6 内容脱敏(施工 R171): 4 会话JSON new_reps→rep_%03d(D4=B 保长度)/solo_report 15条/human_match_v2 写者改 basename+sha1_12/config.py 第三方profile名/审计文档自身 15 处原文→代称; 门禁加"零第三方昵称/他人机用户名"常驻断言。②PR-7: 路径字面量归零(R170)+评估读活档(R171/P1-1)+门禁改读活档产物(R172, 5 WARN→0)。③**第二次全历史重写**(git-filter-repo, 规则 literal: 前缀, 442 提交/5.2s): 全历史复扫 0 命中; 工作树树哈希不变(main tree bda05011 前后一致); main→**7461a11** / planning→**d6ba5e2**; 控制臂 **46920e9→5cf18bb**(commit-map 映射, worktree HEAD 已自动重锚); 三 worktree 变更文件数 0/1/5(未跟踪产物)。④**可见性两跳**: 施工实测原为 PUBLIC(审计§1 前提失效)→ 用户裁定切回 private 止血 → 本步重写完成后用户裁定切 public, 匿名 API 200 / gh visibility=public 复核。⑤备份: 仓外镜像 D:\temp\repo-mirror-20261018(重写前全对象) + 本地分支 pii-backup-20261018。 |
