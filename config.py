# -*- coding: utf-8 -*-
"""集中配置: 所有可调参数都在这里, 其他脚本只读不改。

约束(项目约定):
- 本文件本身不碰游戏; 游戏状态经mod TCP通道获取(mod自读内存, 我方不注入
  本进程外内存 — tm_env的R2预检写是唯一例外且有预检/校验纪律);
  屏幕捕获通道已废弃(遮挡即冻结);
- 不安装驱动, 不修改任何系统文件;
- 运行期产生的文件(截图/日志)只写在本项目目录内。
"""

# ---- 游戏窗口 ----
# 窗口标题候选子串(按顺序逐个匹配; 覆盖繁体/简体/英文等常见版本;
# 窗口枚举旧工具已归档 _archive/root_dead_r17/loop.py — R17§3.3)
TITLE_CANDIDATES = ["非想天則", "非想天则", "東方非想天", "东方非想天",
                    "th123", "TH123", "Hisoutensoku", "緋想天"]

# ---- 注入通道 ----
# 实测结论(2026-09-01): 本游戏过滤 SendInput 合成按键, 但接受 keybd_event(神AI th123_ai 同款路径)。
# 可选: "keybd_scan"(默认, 扫描码) / "keybd_vk" / "vk" / "scan" / "journal"
INPUT_MODE = "keybd_scan"

# ---- 帧循环 ----
FPS = 62                # 游戏逻辑帧率(教义: 非想天则是62帧游戏, 帧↔秒一律/62)
CAPTURE_SCALE = 2       # 抓屏缩放(2 = 1280x960 客户区缩到 640x480; 感知坐标是比例制, 不受影响)
CAPTURE_BACKEND = "dxcam"   # "dxcam"(DXGI, ~0.1ms/帧, 60fps 控制环) / "gdi"(回退, 30fps)

# ---- 键位: 与游戏内键位设置保持一致, 不符就改这里 ----
# 已按你游戏 profile 里的实际键位设定(整合包默认, 从 .pf 文件读到的):
# 上=W 下=S 左=A 右=D, A(打撃)=J B(射撃)=K C(必殺)=L D(ダッシュ)=O
# 用卡=I 切卡=U (2026-09-07 用户指正: 旧"SC":0x55 是U=切卡; I=0x49 才是用卡)
# 虚拟键码: W=0x57 S=0x53 A=0x41 D=0x44 J=0x4A K=0x4B L=0x4C O=0x4F U=0x55 I=0x49
KEYMAP = {
    "left": 0x41, "right": 0x44, "up": 0x57, "down": 0x53,   # A D W S
    "A": 0x4A,     # J
    "B": 0x4B,     # K
    "C": 0x4C,     # L
    "D": 0x4F,     # O
    "SC": 0x49,    # I 用卡(消耗手牌)
    "SCSW": 0x55,  # U 切卡(旋转选中位)
}

# P2侧键位(自对弈第二实例用; --side right时整体接管KEYMAP)
# 来源: 用户指认"2P键位与神AI一致" → AI（请勿复制修改）.pf 键位块差分解码(2026-09-21):
# 方向=Home/End/Delete/PgDn, ABCD=小键盘÷/*\\/ (刻意的防P1冲突布局)
# 卡键1/2/3=Insert/PgUp/小键盘. — 切卡/用卡归属待2P实战用卡传感器实证(50/50)
KEYMAP2 = {
    "left": 0x2E, "right": 0x22, "up": 0x24, "down": 0x23,   # Delete PgDn Home End
    "A": 0x6F,     # 小键盘 /
    "B": 0x6A,     # 小键盘 *
    "C": 0xDC,     # \(OEM_5)
    "D": 0xBF,     # /(OEM_2)
    "SC": 0x21,    # PgUp 用卡(暂定, 待实证)
    "SCSW": 0x2D,  # Insert 切卡(暂定, 待实证)
}

# ---- 感知: 命中检测(自动) ----
# HP_AUTO=True 时按整合包 HUD 的实测坐标自动读两条 HP 条, 无需标定;
# 对手条(默认右侧)黄色像素相对峰值下降 >= HP_HIT_DROP_PX 判定一次命中。
HP_AUTO = True
HP_OPPONENT = "right"      # 对手 HP 条在哪侧(练习模式你=左, 木桩=右)
HP_HIT_DROP_PX = 400       # 黄色像素下降阈值(约 3% 血量, 可调)
HP_HIT_COOLDOWN = 0.5      # 两次命中事件的最小间隔(秒)

# ---- 感知: 手动 HP 条区域(旧方案, HP_AUTO=True 时忽略) ----
HP_RECT = (0, 0, 0, 0)        # (x, y, w, h)
HP_HIT_CHANGED_PX = 30        # 区域内变化像素数 >= 该值 → 视为命中事件

# ---- 演示 bot 时间轴(键名见 KEYMAP) ----
ADVANCE_STEPS = [
    (0.8,  ["right"]),            # 前进(D)
    (0.05, ["right", "B"]),       # 前进 + 射撃(K, 轻点)
    (0.08, []),
    (0.05, ["right", "B"]),
    (0.08, []),
    (0.6,  ["right"]),
    (0.05, ["right", "B"]),
]
RETREAT_STEPS = [
    (0.05, ["left"]),
    (0.05, []),
    (0.6,  ["left"]),             # 后撤(A)
    (0.30, ["up", "left"]),       # 后跳(W+A)
    (0.05, ["up", "left", "B"]),  # 后跳射撃
    (0.05, ["up", "left"]),
]

# ---- 决策器: "demo"(时间轴脚本) / "reactive"(状态反射式专家) / "bc"(行为克隆模型) ----
BOT_MODE = "bc"
POLICY_MODEL = "model_rl.npz"   # 当前策略: RL 模型(观看用 demo.bat --stochastic); BC 模型是 "model_bc.npz"
DATA_DIR = "data"        # 录制样本目录(相对项目根)
BC_FEAT_W, BC_FEAT_H = 80, 60   # 视觉输入尺寸(弹幕3~4px可辨, conv 3层感知基础)
BC_HISTORY = 3           # 帧堆叠: 输入最近 N 帧(让模型看到运动方向)
BC_THRESH = 0.5          # 按键输出阈值

# ---- 输出目录(相对项目根目录) ----
FRAME_DIR = "frames"
