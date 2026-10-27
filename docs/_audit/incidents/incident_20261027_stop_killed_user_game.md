# 事故：22:45 停训 helper 误杀用户原版游戏（P1）

## 现象
- 2026-10-27 22:45 `train_stop_clean --live` 停机账 games=[**24260**, 2812, 28148, 8356, 27036]；
  24260 = 用户原版 `D:\touhou\hisoutensoku2026-06-15\th123\th123.exe`，被与 4 个训练游戏一起停止。
- 训练 main/control/watcher/训练游戏全停、锁 False、marker 22:45:00 正确；训练/生产未损。

## 根因
- `game_pids()` 仅按 `Name='th123.exe'` 匹配，**未区分训练/非训练实例**。

## 修复
- live 模式只杀 `th123_train` + 车道端口 21000–21089（同 health probe）；test marker 模式不变。
- 测试：`test_train_stop_clean_v1` 增加"live games 只杀训练"断言；下次停训/窗口前必须 PASS。
- 记录：用户游戏若非训练实例，停训前应提示/排除；不做自动重启用户游戏。

## 预防
- 所有 kill/stop helper 统一用"训练车道端口"过滤；新增 lab 实例端口排除。
- 窗口脚本停训前打印 games 列表并断言无 24260 类非训练路径。
