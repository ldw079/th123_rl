# -*- coding: utf-8 -*-
"""屏幕捕获模块: 用 GDI BitBlt 抓取窗口客户区像素(纯标准库, 零依赖)。

设计约束(与项目约定一致):
- 只读"显示器上呈现的像素", 不读游戏进程内存;
- 不安装驱动/服务, 不写注册表, 不修改任何系统文件;
- 捕获坐标按物理像素处理(模块加载时声明 DPI 感知)。
"""

import ctypes
import time
from ctypes import wintypes

SRCCOPY = 0x00CC0020
BI_RGB = 0
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
WM_CLOSE = 0x0010

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32


def _set_dpi_aware():
    """让本进程的窗口坐标/捕获坐标都以物理像素为准。"""
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)):
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


_set_dpi_aware()


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


# ---- 函数原型: 显式声明参数/返回类型, 避免 64 位下指针被截断 ----
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.DWORD,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.StretchBlt.restype = wintypes.BOOL
gdi32.StretchBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             wintypes.DWORD]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]

user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_size_t]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]


def find_windows(title_substr):
    """返回标题包含 title_substr 的可见窗口: [(hwnd, title), ...]"""
    results = []

    @WNDENUMPROC
    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if title_substr in buf.value:
            results.append((hwnd, buf.value))
        return True

    user32.EnumWindows(_cb, 0)
    return results


def list_visible_windows():
    """调试用: 当前所有可见且带标题的窗口。"""
    titles = []

    @WNDENUMPROC
    def _cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                titles.append(buf.value)
        return True

    user32.EnumWindows(_cb, 0)
    return titles


def get_client_rect(hwnd):
    """窗口客户区在屏幕上的物理像素坐标 (x, y, w, h)。"""
    rc = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        raise RuntimeError("GetClientRect 失败")
    tl = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(tl))
    return tl.x, tl.y, rc.right, rc.bottom


class ScreenCapturer:
    """抓取屏幕上的一个矩形区域, grab() 返回 BGRA 字节流(每像素 4 字节)。

    scale: 抓取时整体缩小倍数(StretchBlt), 感知层坐标全部按比例计算, 不受影响;
    高 DPI 屏幕上 scale=2 可把 1280x960 的游戏画面缩到 640x480, 大幅降低像素处理量。
    """

    def __init__(self, x, y, w, h, scale=1):
        if w <= 0 or h <= 0:
            raise ValueError("捕获区域宽高必须为正")
        self.x, self.y = x, y
        self.sw, self.sh = w, h          # 源区域(客户区像素)
        self.scale = scale
        self.w = max(1, w // scale)      # 抓取结果尺寸
        self.h = max(1, h // scale)
        self._screen_dc = user32.GetDC(0)
        if not self._screen_dc:
            raise RuntimeError("GetDC 失败")
        self._mem_dc = gdi32.CreateCompatibleDC(self._screen_dc)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = self.w
        bmi.bmiHeader.biHeight = -self.h        # 负高度 = 自上而下, 行序与常规内存一致
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        self._pbits = ctypes.c_void_p()
        self._bmp = gdi32.CreateDIBSection(
            self._mem_dc, ctypes.byref(bmi), 0, ctypes.byref(self._pbits), None, 0)
        if not self._bmp:
            raise RuntimeError("CreateDIBSection 失败")
        self._old = gdi32.SelectObject(self._mem_dc, self._bmp)
        self._size = self.w * self.h * 4

    def grab(self):
        if self.scale == 1:
            ok = gdi32.BitBlt(self._mem_dc, 0, 0, self.w, self.h,
                              self._screen_dc, self.x, self.y, SRCCOPY)
        else:
            ok = gdi32.StretchBlt(self._mem_dc, 0, 0, self.w, self.h,
                                  self._screen_dc, self.x, self.y, self.sw, self.sh,
                                  SRCCOPY)
        if not ok:
            raise RuntimeError("抓屏失败(窗口可能被遮挡或已关闭)")
        return ctypes.string_at(self._pbits.value, self._size)

    def close(self):
        gdi32.SelectObject(self._mem_dc, self._old)
        gdi32.DeleteObject(self._bmp)
        gdi32.DeleteDC(self._mem_dc)
        user32.ReleaseDC(0, self._screen_dc)


class DxcamCapturer:
    """DXGI 桌面复制抓屏(dxcam): ~0.1ms/帧, 支撑 60fps 控制环。

    与 ScreenCapturer 同接口: grab() 返回 BGRA 字节流, .w/.h 为缩放后尺寸。
    每次抓取重新读取窗口客户区位置(窗口可移动); 无新帧时复用上一帧。
    target_hz: 建议的控制环频率(DXGI 受显示器刷新率限制, 通常 60)。
    """

    target_hz = 60.0

    def __init__(self, x, y, w, h, scale=1):
        import dxcam
        # 退化矩形防御(修: 训练器在窗口过渡态启动→capturer出生即1px,
        # 之后每帧"合规地"补成1像素宽, 首帧特征计算即崩): 等待健康矩形
        t0 = time.time()
        while (w < 100 or h < 100) and time.time() - t0 < 5.0:
            time.sleep(0.2)
            # 直接重读一次游戏窗口矩形(启动瞬间可能处于过渡态)
            try:
                rc = wintypes.RECT()
                tl = wintypes.POINT(0, 0)
                for sub in ("非想天则", "非想天則", "th123", "东方非想天"):
                    ws = find_windows(sub)
                    if ws:
                        hwnd0 = ws[0][0]
                        if user32.GetClientRect(hwnd0, ctypes.byref(rc)) \
                                and user32.ClientToScreen(hwnd0, ctypes.byref(tl)):
                            x, y, w, h = tl.x, tl.y, rc.right, rc.bottom
                        break
            except Exception:
                pass
        if w < 100 or h < 100:
            raise RuntimeError("游戏窗口尺寸退化(%dx%d) — 恢复窗口后重新运行训练" % (w, h))
        self._hwnd_finder = None
        self.scale = scale
        self.w = max(1, w // scale)
        self.h = max(1, h // scale)
        # 视频模式(批18滴流6盲局后的根本方案): 后台线程60fps持续AcquireNextFrame
        # 保持duplication热态 — 拉取模式在grab间隙里接口变冷是滴流根源。
        # region在create时固化(区域冻结的最终形态); 代价≈2-5%常驻CPU。
        sw0 = user32.GetSystemMetrics(0)
        sh0 = user32.GetSystemMetrics(1)
        self._region = (max(0, x), max(0, y),
                        min(sw0, x + w), min(sh0, y + h))
        self._cam = dxcam.create(output_color="BGRA", region=self._region)
        if self._cam is None:
            raise RuntimeError("dxcam 初始化失败")
        self._video_mode = True
        self._cam.start(target_fps=60, video_mode=True)
        self._win_x, self._win_y = x, y
        self._win_w, self._win_h = w, h
        self._last = None
        self._none_streak = 0     # grab连续无新帧计数(DXGI僵死检测/自愈用)
        self._same_streak = 0     # grab连续返回相同字节计数(内容级僵死, 2026-09-08盲局事故)
        self._fresh_ts = []       # 最近新鲜帧时间戳(慢滴速率看门狗: 15帧>3s=供帧<5fps)
        self._last_rebuild_t = time.time()   # 定期预防性重建计时起点(修: 默认值曾写成
        #                                      getattr(...,now)导致差值恒0, 批6实证未生效)

    def _update_rect(self):
        """重读窗口客户区矩形(瞬时异常自愈用; 退化矩形不采信, 保上一有效值)。"""
        try:
            rc = wintypes.RECT()
            tl = wintypes.POINT(0, 0)
            if user32.GetClientRect(self._find_hwnd(), ctypes.byref(rc)) \
                    and user32.ClientToScreen(self._find_hwnd(), ctypes.byref(tl)) \
                    and rc.right >= 100 and rc.bottom >= 100:
                self._win_x, self._win_y, self._win_w, self._win_h = \
                    tl.x, tl.y, rc.right, rc.bottom
        except Exception:
            pass

    def grab(self):
        now = time.time()
        # 窗口大位移检测(2s低频): 视频模式region固化在create, 窗口被拖走则
        # 重建接口跟新region — 训练期窗口不动, 此为兜底。
        if now - getattr(self, "_rect_read_t", 0.0) > 2.0:
            self._rect_read_t = now
            self._update_rect()
            sw = user32.GetSystemMetrics(0)
            sh = user32.GetSystemMetrics(1)
            cand = (max(0, self._win_x), max(0, self._win_y),
                    min(sw, self._win_x + self._win_w), min(sh, self._win_y + self._win_h))
            if any(abs(a - b) > 2 for a, b in zip(cand, self._region)):
                print("[抓屏] 窗口位移 — 按新区域重建DXGI")
                self._region = cand
                self._force_rebuild = True
        # 定期预防性重建(视频模式下应罕见 — 后台线程保温; 周期放宽到300s
        # 防泄漏堆积; 场景切换定点/看门狗仍即时触发)
        if getattr(self, "_force_rebuild", False) \
                or now - getattr(self, "_last_rebuild_t", now) > 300.0:
            self._force_rebuild = False
            print("[抓屏] %s重建DXGI" % ("场景切换定点" if now - self._last_rebuild_t < 295.0
                                        else "定期预防性(300s)"))
            self._rebuild_cam()
            self._fresh_ts = []
            self._none_streak = 0
        # 视频模式取帧: get_latest_frame 返回缓冲区最新帧(热态线程持续写入)
        try:
            f = self._cam.get_latest_frame()
        except Exception:
            f = None
        if f is None:
            # 热身期(启动后~1帧间隙)或异常: 回退拉取模式一次
            try:
                f = self._cam.grab(region=self._region)
            except Exception:
                f = None
        if f is None:
            self._none_streak += 1
            if self._none_streak >= 8:
                print("[抓屏] 连续%d次无新帧 — 重建DXGI采集(视频模式僵死自愈)"
                      % self._none_streak)
                self._rebuild_cam()
                self._none_streak = 0
            if self._last is None:
                raise RuntimeError("DXGI 无帧(屏幕无刷新/输出切换? 稍后重试)")
            return self._last
        self._none_streak = 0
        arr = f[::self.scale, ::self.scale]
        # 尺寸规整: 窗口客户区±1px抖动(宽缩高涨的混合漂移)时统一补/裁到名义
        # 尺寸, 保证下游恒定 — 修: 旧补边只处理"双维都小", 混合漂移直接崩
        if arr.shape[0] != self.h or arr.shape[1] != self.w:
            import numpy as np
            pad = np.zeros((self.h, self.w, arr.shape[2]), dtype=arr.dtype)
            h = min(arr.shape[0], self.h)
            w = min(arr.shape[1], self.w)
            pad[:h, :w] = arr[:h, :w]
            arr = pad
        new_bytes = arr.tobytes()
        # 内容级僵死看门狗(2026-09-08盲局事故: dxcam持续返回同一帧非None字节,
        # none检测不触发; 传感器帧计数照常推进 → 主循环"帧在走"误判, AI被蒙眼
        # 打完一整局12决策0伤害)。同字节连续>150次(~2.5s, 超必杀闪光最长1s)
        # 判僵死重建。重建代价≈一次dxcam.create, 误触发无害。
        if new_bytes == self._last:
            self._same_streak += 1
            if self._same_streak >= 150:
                print("[抓屏] 连续%d次画面零变化 — 重建DXGI采集(内容级僵死自愈)"
                      % self._same_streak)
                self._rebuild_cam()
                self._same_streak = 0
        else:
            self._same_streak = 0
        self._last = new_bytes
        return self._last

    def on_scene_change(self):
        """场景切换定点重建(批7实证滴流高发于回合/场景转换后 — 切换即重置
        采集接口, 把盲区从"一整局"压到"一帧间隙")。"""
        self._force_rebuild = True

    def _rebuild_cam(self):
        """重建DXGI采集接口(视频模式)。批21铁证: dxcam工厂用
        WeakValueDictionary缓存实例 — 只stop不del时 create() 拿回同一个
        停死实例(region也被丢弃, start()在坏态下静默无效), 重建=空操作,
        0-0盲局的直接根源。正解: stop→del强引用→gc让弱注册表失效→真新建。"""
        try:
            self._cam.stop()
        except Exception as _e:
            print("[抓屏] 旧cam停止异常: %r" % _e)
        _old = self._cam
        self._cam = None
        del _old                      # 丢强引用(dxcam官方指示的重建路径)
        import gc
        gc.collect()                  # 立即回收 → 弱注册表条目失效
        try:
            import dxcam
            self._cam = dxcam.create(output_color="BGRA", region=self._region)
            self._cam.start(target_fps=60, video_mode=True)
        except Exception as _e:
            print("[抓屏] 重建异常: %r" % _e)
        self._last_rebuild_t = time.time()

    def _find_hwnd(self):
        if self._hwnd_finder is None:
            for sub in ("非想天则", "非想天則", "东方非想天", "東方非想天", "th123", "TH123"):
                ws = find_windows(sub)
                if ws and "资源管理器" not in ws[0][1] and "Explorer" not in ws[0][1]:
                    self._hwnd_finder = ws[0][0]
                    break
            if self._hwnd_finder is None:
                self._hwnd_finder = user32.GetForegroundWindow()
        return self._hwnd_finder

    def close(self):
        try:
            self._cam.release()
        except Exception:
            pass


def make_capturer(x, y, w, h, scale=1, backend=None):
    """抓屏器工厂: 优先 dxcam(DXGI, 快), 失败回退 GDI。
    窗口瞬时退化(0x0/最小化闪动)在两条路径都要等健康矩形 — 2026-09-08
    批31启动崩: dxcam侧等了5s正确拒绝, GDI回退却拿同一坏矩形直接崩。"""
    import config as _config
    backend = backend or getattr(_config, "CAPTURE_BACKEND", "dxcam")
    if backend == "dxcam":
        try:
            return DxcamCapturer(x, y, w, h, scale=scale)
        except Exception as e:
            print("[警告] dxcam 不可用(%s), 回退 GDI(30fps)" % e)
    t0 = time.time()
    while (w < 100 or h < 100) and time.time() - t0 < 5.0:
        time.sleep(0.2)
        try:
            rc = wintypes.RECT()
            tl = wintypes.POINT(0, 0)
            for sub in ("非想天则", "非想天則", "th123", "东方非想天"):
                ws = find_windows(sub)
                if ws:
                    hwnd0 = ws[0][0]
                    if user32.GetClientRect(hwnd0, ctypes.byref(rc)) \
                            and user32.ClientToScreen(hwnd0, ctypes.byref(tl)):
                        x, y, w, h = tl.x, tl.y, rc.right, rc.bottom
                    break
        except Exception:
            pass
    c = ScreenCapturer(x, y, w, h, scale=scale)
    c.target_hz = 30.0
    return c
