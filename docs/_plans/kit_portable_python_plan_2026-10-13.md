# 方案: dist 采集包便携化(自带 Python)+ 三项 bug 清偿(2026-10-13)

> 需求来源: 用户指令"我选便携python的方案, 把上述打包版相关意见整理为
> 文档"(2026-10-13; 前置问答: kit 现不自带 Python, 默认收件机无 Python)。
> 定位: build_kit 产物从"需自装环境"升级为"解压即用", 同时清偿 dist 专项
> 审计(111a88b)三项 bug。
> 与主规划映射: B 线人测数据采集的外发基建; 不触训练主链。

## 0. 现状核验(时点: 2026-10-13 深夜; 基线 `6c46aa4`)

| # | 盘点项 | 实况(已验证) | 方式 |
|---|---|---|---|
| 1 | kit 结构 | dist/th123rl_kit: README/setup/start/export 三 bat + th123rl/(32 py+macros+3角色模型) + zip(11MB) | ls/cat 亲验 10-13 |
| 2 | Python 依赖 | **不自带解释器**; requirements.txt 声明 `numpy>=1.26, torch>=2.0`; setup.bat 裸调 pip/python | cat 亲验 |
| 3 | torch 真实依赖 | 闭包内仅 series_meter(:75)/value_curve(:19)含 torch, **均为函数内惰性导入+响亮降级设计** → 推理路径 numpy-only 可行; requirements 的 torch 属过申报 | grep 全闭包亲验 |
| 4 | bug-1 store 硬编码 | human_match_v2.py:372 `os.environ.get('TH123_STORE', r'D:\temp\th123_models')` 绕过 kit_config; 打包 models/ 无任何代码路径使用 | 亲验(grep+kit 内跑 kit_config.STORE_DIR) |
| 5 | bug-2 strftime | export_helper.py `%%Y` 双百分号 → 实跑输出字面量 `match_data_%Y%m%d_%H%M%S.zip`, 恒定名覆盖 | 实跑亲验 |
| 6 | bug-3 对手角色盲打 | SideDriver.opp_char_id 恒 None(hm2 零接线); 对手 one-hot 恒零特征失配; AI 侧角色亦无运行时校验 | grep 全库亲验 |
| 7 | build_kit 构成 | tools/build_kit.py:168 build() — trace_imports 闭包 + 内嵌常量(SETUP_HELPER/START_BAT/EXPORT_HELPER/README)生成收件人脚本 → **bat/helper 的全部改动单一真值源在此** | sed 亲验 |
| 8 | 复现先例 | hm2 import 闭包在 kit 上下文 OK; R90b headless 端到端 1878 帧在**开发机**通过(掩盖 #4) | 10-13 实测+提交链 |

## 1. K1 便携 Python 层(build_kit 扩展, 核心)

- **接入点**: tools/build_kit.py build() 在"附产物"段后新增 `_bundle_python
  (kit_dir)`: ①从缓存目录(无则首次联网下载, URL+sha256 固定写入构建器)取
  `python-3.12.x-embed-amd64.zip` → 解包至 `kit\python\`; ②numpy wheel
  以开发机 `pip download numpy --only-binary :all: -d cache` 缓存, 解包
  安装至 `kit\python\Lib\site-packages\`; ③写 `kit\python\python312._pth`
  启用 site-packages(embed 默认禁用 import 路径)。
- **bat 改造**(build_kit 内嵌常量): setup.bat 删 `pip install` 段(依赖已
  自带), 保留 game_dir 配置+exe md5, 调用改 `%~dp0python\python.exe`;
  start.bat/export.bat 同改固定路径(收件机 PATH 无 python 亦可)。
- **工作量**: 1.5-2 人日(构建器 1 + bat/模板 0.5 + 干净机验证 0.5)。
- **回滚**: _bundle_python 独立函数+构建开关 `--no-python`(降级为现行为)。
- **体积预算**: embed ~11MB + numpy ~18MB + 现有 11MB ≈ **40MB 内**。
- **[用户裁定项 A]** embed 版本钉 3.12.x(与开发 pyenv 3.12 一致,
  建议); 体积上限是否 40MB。

## 2. K2 store 包内回落(bug-1 清偿)

- **接入点**: tools/human_match_v2.py:372 改 `from kit_config import
  STORE_DIR; store = STORE_DIR`; kit_config.py STORE_DIR 四层回落:
  `config.json store_dir > TH123_STORE > 包内 th123rl/models(存在即用) >
  本机默认 D:\temp\th123_models`(末层仅开发机生效, 附告警打印);
  config.json.template 补 store_dir 注释行。
- **验收**: 清空 TH123_STORE/TH123RL_CONFIG 指向空目录, kit 内
  `STORE_DIR` 解析到包内 models 且 driver.load 成功。
- 工作量 0.5 人日。

## 3. K3 导出修复(bug-2 清偿)

- export_helper 常量(build_kit 单源)内 `%%`→`%`, 导出后断言文件名含
  当日日期(`os.path.basename` 正则) — 连续两次导出文件名不同。
- 工作量 0.1 人日(随 K1 改常量顺手)。

## 4. K4 依赖正名: numpy-only

- requirements.txt(build_kit 生成处)改 `numpy>=1.26`, 删 torch 行;
  README 要求段删 "Python 3.10+"(自带)。
- **验证**: 在 kit 的 embed python(无 torch)下跑 headless 端到端 —
  value_curve/series_meter 走响亮降级路径, 对战功能不受影响
  (降级文案出现在日志=验收的一部分, 不允许静默)。
- 工作量 0.5 人日(含验证)。

## 5. K5 对手角色识别(bug-3 清偿; **[用户裁定项 B]** 是否随本方案做)

- 两段: ①B-1 校准链追加双方 char id 内存读数(角色管理器偏移,
  先例 rep 头 b[14]/b[63]; rpm_calibration 扩一项, 0.5-1 人日含实证);
  ②hm2 每局开局读双方 char → AI 侧校验==--char(不符响亮警告) +
  `driver.opp_char_id = 池序(对手char)` 接线 + 特征断言
  core[227+oid]==1。
- **后果声明**: 修复后人测模型从"盲打"变为"知情" — 实战表现预期上修,
  **R91 基线(用户 3-0)不再可比, 需重测**。
- 工作量合计 1.5-2 人日。

## 验收与总验收

| 项 | 量化阈值 | 测量方法 | 回归线 |
|---|---|---|---|
| K1 | 干净机模拟(清 TH123_* 环境变量+PATH 前置空 python shim)下 setup→start→export 三 bat 全通; zip <40MB | 模拟干净机冒烟(或虚拟用户环境变量子进程) | `--no-python` 构建的 kit 与现行行为逐字节等价(bat 除外) |
| K2 | 空 store 环境下 headless 从包内加载, 1878 帧级对局完成 | headless 端到端(复用 R90b 协议) | 开发机默认路径行为不变(末层回落) |
| K3 | 连续两次导出文件名不同且含日期 | 实跑+断言 | — |
| K4 | 无 torch 环境端到端通过且降级文案出现在日志 | embed python 下 headless | 有 torch 环境输出不变 |
| K5(若裁) | 双角色对局 core[227+oid]==1; 错配角色警告触发; 新基线 BO5≥3 局留档 | 单元断言+人测会话 | hm2 既有测试全绿 |
| 总 | 门禁全绿; kit 内 py 编译零错; 行为测试入 C15 随行 | contract_check | 主库训练链零改动(diff 范围仅 tools/build_kit+hm2 store 行+kit_config) |

## 排期与依赖

```
K3(0.1) → K2(0.5) → K1(2) → K4(0.5)   主线, 合计 ~3.5 人日
K5(1.5-2) 独立, 可并行或后置(裁定项B)
```
构建顺序理由: 先修 store 回落(K1 的干净机验证依赖它), 便携层最后接。

## 不变面

- 训练主链/fleet/门禁断言零改动; hm2 仅动 store 一行+K5 接线。
- 打包闭包 trace_imports 机制不变; 模型打包集合(3 角色)不变。
- 收件人使用流程(README 四步)结构不变, 仅去掉"装 Python"门槛。

## 风险表

| 风险 | 概率 | 缓解 |
|---|---|---|
| embed python ._pth 路径配置踩坑(import 系统库失败) | 中 | K1 先做 30 分钟探针(numpy import+hm2 import 通即放行); 先例: 项目 safe-path 教训入册 |
| numpy wheel 与 embed 版本不匹配(3.12 ABI) | 低 | 钉同小版本; 构建器写死 sha256 校验 |
| 干净机验证不可完全模拟(防火墙/杀软/权限) | 中 | 验收以"环境变量+PATH shim"为准; README 保留故障联系渠道; 首个真实收件人试发一轮 |
| 内存读写(bt 权限)在收件机被拒 | 中(既有) | 非本方案引入; setup 增加 OpenProcess 自检探针(可选) |

## 用户裁定项汇总

- A: embed 版本钉 3.12.x / zip 体积上限 40MB(建议值, 可改)。
- B: K5(对手角色识别+重测基线)是否随本方案做, 还是独立排期。
