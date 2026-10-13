# Bug: 人测通道对手角色不识别 — opp_char_id 恒 None 特征失配(未修, P1)

- **发现**: 2026-10-13 dist 专项审计(用户问"能否自动识别对手选取的角色")。
- **症状**: `side_driver.py:112` `self.opp_char_id = None # 由外部wire`,
  而 `tools/human_match_v2.py` **从未接线**(全库 grep 零赋值) →
  `_side_feat` 的对手 one-hot(core[227+oid]/扩展区 core[308+i])恒零,
  与训练分布(对手 one-hot 恒有值)失配 — **模型对 matchup 盲打**。
  同时 AI 自身角色也无运行时校验(start.bat 手输 --char, 游戏内选错
  角色/输错参数 = 模型与实际机体错配, 无检测)。
- **根因**: R19 设计"由外部 wire"的集成缝在 fleet/eval 侧有人接
  (EvalEnv 池序), 人测通道(hm2)漏接 — "单元可用、集成缝断"复发型;
  且内存侧没有双方 char id 读数(B-1 校准链覆盖 hp/action/spirit/
  position/hand/weather/对象, 无角色 ID)。
- **引入**: R89/R90 人测 runner 落地起。
- **影响面**: R91 人机 BO5 与一切 hm2 会话均在盲打状态下进行
  (对手 one-hot 全零); kit 与主库同病。
- **修复与验证**: 未修。修法两段: ①内存 char id 读数(角色管理器偏移,
  B-1 校准链追加一项; rep 头 b[14]/b[63] 有同款先例); ②hm2 每局开局
  读双方 char → 校验 AI 侧 == --char(不符响亮警告) + 接线
  `driver.opp_char_id = 池序(对手char)`。验证: 双角色对局断言
  core[227+oid]==1; 故意选错角色断言警告触发。
- **防复发**: 端到端行为测试(模拟双 char id → 特征断言); R91 类
  人测报告注明对手 one-hot 是否接线(读数透明)。
- **状态**: 未修。
