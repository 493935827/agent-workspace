# -*- coding: utf-8 -*-
"""自动复现“GUI 窗口有时拖不动”：
造一个带原生标题栏的 Qt 窗口，在多种状态下用真实鼠标注入拖标题栏，
同时测量主线程消息泵延迟（SendMessageTimeout WM_NULL），量化“拖不动”。

状态：基线 / 模态对话框 / 真实串口枚举风暴 / 主线程睡 600ms / 睡 5.6s(未响应) / 最大化 / 真实工作台窗口。
"""
import ctypes
import json
import sys
import threading
import time
import traceback
from ctypes import wintypes

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMainWindow
from serial.tools import list_ports

user32 = ctypes.WinDLL('user32', use_last_error=True)

try:  # 坐标统一用物理像素，避免 DPI 虚拟化干扰
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

TITLE = 'DSZ 拖动复现窗口'
WORKBENCH_TITLE = 'Serial Workbench — Qt 串口工作台'
CMD = {}          # 控制线程 -> GUI 线程 的简单指令板（GIL 下读写安全）
SMTO_ABORTIFHUNG = 0x0002
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
KEYEVENTF_KEYUP = 0x0002
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]


class INPUTUNION(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('union', INPUTUNION)]


def send_mouse(flags, dx=0, dy=0):
    mi = MOUSEINPUT(dx, dy, 0, flags, 0, 0)
    inp = INPUT(0, INPUTUNION(mi))
    return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def set_cursor_abs(x, y):
    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)
    nx = int((x - vx) * 65535 / max(vw - 1, 1))
    ny = int((y - vy) * 65535 / max(vh - 1, 1))
    send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny)


def get_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def get_cursor():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def pump_latency_ms(hwnd, timeout_ms=200):
    """向窗口发 WM_NULL 并等待处理，返回处理耗时；超时说明主线程没在泵消息。"""
    res = ULONG_PTR(0)
    t0 = time.perf_counter()
    ok = user32.SendMessageTimeoutW(hwnd, 0, 0, 0, SMTO_ABORTIFHUNG,
                                    timeout_ms, ctypes.byref(res))
    ms = (time.perf_counter() - t0) * 1000
    return dict(ms=round(ms, 1), processed=bool(ok))


def is_hung(hwnd):
    return bool(user32.IsHungAppWindow(hwnd))


def is_zoomed(hwnd):
    return bool(user32.IsZoomed(hwnd))


def force_foreground(hwnd):
    # 经典绕前台锁手法：先敲一下 ALT 再 SetForegroundWindow
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.06)
    return int(user32.GetForegroundWindow() or 0) == int(hwnd)


def drag_title(hwnd, dx=150, dy=90, steps=12, step_ms=25, hold_ms=0):
    """按住标题栏中心拖一段，返回窗口位移。只在自己成功抢到前台时注入，防误点别的窗口。"""
    if user32.IsIconic(hwnd):
        return dict(result='minimized-skipped')
    if is_hung(hwnd):
        return dict(result='hung-skipped')
    before = get_rect(hwnd)
    zoomed = is_zoomed(hwnd)
    cur0 = get_cursor()
    if not force_foreground(hwnd):
        return dict(result='not-foreground-skipped', before=before)
    x0 = before[0] + (before[2] - before[0]) // 2
    y0 = before[1] + 14          # 标题栏中部
    set_cursor_abs(x0, y0)
    time.sleep(0.04)
    send_mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.02)
    for i in range(1, steps + 1):
        set_cursor_abs(x0 + dx * i // steps, y0 + dy * i // steps)
        time.sleep(step_ms / 1000)
    if hold_ms:
        time.sleep(hold_ms / 1000)
    send_mouse(MOUSEEVENTF_LEFTUP)
    time.sleep(0.2)
    set_cursor_abs(*cur0)
    after = get_rect(hwnd)
    return dict(result='ok', before=before, after=after,
                moved_px=[after[0] - before[0], after[1] - before[1]],
                zoomed=zoomed, zoomed_after=is_zoomed(hwnd))


class Demo(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(560, 360)
        self.move(300, 300)
        lab = QLabel('拖动复现测试窗口\n(期间会自动模拟拖动)', alignment=Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(lab)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_cmd)
        self.timer.start(15)

    def poll_cmd(self):
        cmd = CMD.get('cmd')
        if not cmd:
            return
        CMD['cmd'] = None
        if cmd == 'modal':
            d = QDialog(self)
            d.setWindowTitle('模态对话框(2.5s 后自动关)')
            d.resize(260, 120)
            QTimer.singleShot(2500, d.accept)
            d.exec()                      # 模态：阻塞主窗口直到关闭
        elif cmd == 'stall':
            time.sleep(CMD.get('ms', 600) / 1000)   # 模拟主线程被耗时操作占住
        elif cmd == 'burst':
            t0 = time.perf_counter()
            for _ in range(CMD.get('n', 120)):
                list(list_ports.comports())         # 复现工作台 poll_ports 的真实调用
            CMD['burst_ms'] = round((time.perf_counter() - t0) * 1000, 1)
        elif cmd == 'maximize':
            self.showMaximized()
        elif cmd == 'restore':
            self.showNormal()
        elif cmd == 'quit':
            QApplication.instance().quit()


def issue(**kw):
    CMD.clear()
    CMD.update(kw)


def controller(results):
    try:
        hwnd = 0
        for _ in range(100):
            hwnd = user32.FindWindowW(None, TITLE)
            if hwnd:
                break
            time.sleep(0.05)
        if not hwnd:
            results['error'] = 'window-not-found'
            return
        time.sleep(0.5)

        # 真实数据：本机枚举一次串口的耗时
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            list(list_ports.comports())
            times.append(round((time.perf_counter() - t0) * 1000, 1))
        results['comports_single_ms'] = times
        results['pump_idle_ms'] = pump_latency_ms(hwnd)

        # P1 基线
        results['P1_baseline'] = dict(latency=pump_latency_ms(hwnd), drag=drag_title(hwnd))

        # P2 模态对话框开着时拖主窗口
        issue(cmd='modal')
        time.sleep(0.4)
        lat = pump_latency_ms(hwnd)
        drag = drag_title(hwnd)
        time.sleep(2.6)                     # 等模态自动关闭
        results['P2_modal_open'] = dict(latency=lat, drag=drag)
        results['P2_after_close'] = dict(drag=drag_title(hwnd))

        # P3 真实串口枚举风暴期间拖动（复现 poll_ports 在 GUI 线程调 comports）
        issue(cmd='burst', n=120)
        time.sleep(0.03)
        lat = pump_latency_ms(hwnd)
        drag = drag_title(hwnd, steps=8, step_ms=25)
        time.sleep(0.3)
        results['P3_comports_burst'] = dict(latency_during=lat, drag=drag, burst_ms=CMD.get('burst_ms'))

        # P4 主线程卡 600ms（模拟慢枚举/慢盘）
        issue(cmd='stall', ms=600)
        time.sleep(0.04)
        lat = pump_latency_ms(hwnd)
        drag = drag_title(hwnd, steps=10, step_ms=35)
        time.sleep(0.4)
        results['P4_stall_600ms'] = dict(latency_during=lat, hung=is_hung(hwnd), drag=drag)

        # P4b 主线程卡 5.6s（越过 Windows“未响应”阈值）
        issue(cmd='stall', ms=5600)
        time.sleep(0.3)
        lat = pump_latency_ms(hwnd, timeout_ms=300)
        hung = is_hung(hwnd)
        time.sleep(5.6)
        results['P4b_stall_5600ms'] = dict(latency_during=lat, hung_during=hung)
        results['P4c_after_recover'] = dict(drag=drag_title(hwnd))

        # P5 最大化后拖动
        issue(cmd='maximize')
        time.sleep(0.6)
        results['P5_maximized'] = dict(drag=drag_title(hwnd))
        issue(cmd='restore')
        time.sleep(0.5)

        # P6 真实工作台若在运行，试拖一次
        whwnd = user32.FindWindowW(None, WORKBENCH_TITLE)
        if whwnd and not user32.IsIconic(whwnd):
            results['P6_real_workbench'] = dict(drag=drag_title(whwnd))
        else:
            results['P6_real_workbench'] = dict(result='not-running')

        issue(cmd='quit')
    except Exception:
        results['error'] = traceback.format_exc()
        issue(cmd='quit')


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    win = Demo()
    win.show()
    results = {}
    th = threading.Thread(target=controller, args=(results,), daemon=True)
    th.start()
    app.exec()
    th.join(timeout=3)
    print(json.dumps(results, ensure_ascii=True, default=str, indent=1))


if __name__ == '__main__':
    main()
