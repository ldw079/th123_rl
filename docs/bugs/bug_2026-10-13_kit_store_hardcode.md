# Bug: kit 硬编码本机 store — 打包模型从未被使用(未修, P1)

- **发现**: 2026-10-13 深夜, dist 采集包专项审计(用户问"打包版能否正确运行")。
- **症状**: `tools/human_match_v2.py:372`
  `store = os.environ.get('TH123_STORE', r'D:\temp\th123_models')` —
  **绕过 kit_config**(可迁移化 commit 40cf85b 声称"路径集中化", 此调用点
  未迁移)。收件人机器无 D:\temp\th123_models → 模型加载失败, **打包的
  th123rl/models/ 从未被任何代码路径使用**(死重); kit 只能在开发机上实战。
- **根因**: 路径集中化改造漏改此调用点(复制陷阱); kit_config 三层回落
  (config.json>env>本机默认)本就缺"包内 models"第四层; R90b 的 headless
  端到端验证在开发机跑, 掩盖了硬编码。
- **引入**: 40cf85b(可迁移化)与 R89/R90 间。
- **影响面**: dist 采集包在收件人机器不可实战; config.json.template 也未
  含 store_dir 字段(用户无从自救)。
- **修复与验证**: 未修。修法: hm2:372 改用 `kit_config.STORE_DIR` +
  kit_config 增加"包内 th123rl/models"最末回落层 + 模板补 store_dir 注释;
  验证: 清掉 TH123_STORE 环境变量在非 D 盘机器(或临时改名 D:\temp 目录)
  跑 --headless 能从包内加载。
- **防复发**: 路径字面量横扫(`r'D:\temp` 在 tools/*.py 出现处逐一归属
  kit_config); headless 端到端在"无本机 store"条件下再跑一次。
- **状态**: 未修。
