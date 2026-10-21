# -*- coding: utf-8 -*-
"""第二轮复验：基线拖两次、模态拒前台、卡顿期间/松手后窗口位置、未响应阈值、最大化。"""
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
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

TITLE = 'DSZ 拖动复现窗口'
CMD = {}
SMTO_ABORTIFHUNG = 0x0002
ME_MOVE, ME_DOWN, ME_UP = 0x0001, 0x0002, 0x0004
ME_ABS, ME_VIRT = 0x8000, 0x4000
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
    vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    send_mouse(ME_MOVE | ME_ABS | ME_VIRT,
               int((x - vx) * 65535 / max(vw - 1, 1)),
               int((y - vy) * 65535 / max(vh - 1, 1)))


def get_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return [r.left, r.top, r.right, r.bottom]


def get_cursor():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def pump_latency_ms(hwnd, timeout_ms=200):
    res = ULONG_PTR(0)
    t0 = time.perf_counter()
    ok = user32.SendMessageTimeoutW(hwnd, 0, 0, 0, SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(res))
    return dict(ms=round((time.perf_counter() - t0) * 1000, 1), processed=bool(ok))


def is_hung(hwnd):
    return bool(user32.IsHungAppWindow(hwnd))


def is_zoomed(hwnd):
    return bool(user32.IsZoomed(hwnd))


def force_foreground(hwnd):
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 0x0002, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.06)
    return int(user32.GetForegroundWindow() or 0) == int(hwnd)


def drag_title(hwnd, dx=150, dy=90, steps=12, step_ms=25, settle_ms=300):
    if user32.IsIconic(hwnd) or is_hung(hwnd):
        return dict(result='skipped-iconic-or-hung')
    before = get_rect(hwnd)
    zoomed = is_zoomed(hwnd)
    cur0 = get_cursor()
    if not force_foreground(hwnd):
        return dict(result='not-foreground-skipped', before=before)
    x0 = before[0] + (before[2] - before[0]) // 2
    y0 = before[1] + 14
    set_cursor_abs(x0, y0)
    time.sleep(0.04)
    send_mouse(ME_DOWN)
    time.sleep(0.02)
    for i in range(1, steps + 1):
        set_cursor_abs(x0 + dx * i // steps, y0 + dy * i // steps)
        time.sleep(step_ms / 1000)
    send_mouse(ME_UP)
    at_release = get_rect(hwnd)
    time.sleep(settle_ms / 1000)
    settled = get_rect(hwnd)
    set_cursor_abs(*cur0)
    return dict(result='ok', before=before, at_release=at_release, settled=settled,
                moved_px=[settled[0] - before[0], settled[1] - before[1]],
                zoomed=zoomed, zoomed_after=is_zoomed(hwnd))


class Demo(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(560, 360)
        self.move(300, 300)
        self.setCentralWidget(QLabel('拖动复验窗口', alignment=Qt.AlignmentFlag.AlignCenter))
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
            d.exec()
        elif cmd == 'stall':
            time.sleep(CMD.get('ms', 600) / 1000)
        elif cmd == 'burst':
            t0 = time.perf_counter()
            for _ in range(CMD.get('n', 120)):
                list(list_ports.comports())
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
        results['pump_idle'] = pump_latency_ms(hwnd)

        results['P1a_first_drag'] = drag_title(hwnd)
        results['P1b_second_drag'] = drag_title(hwnd)

        issue(cmd='modal')
        time.sleep(0.4)
        # 模态期间：尝试把前台切回主窗口 + 拖主窗口
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 0x0002, 0)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)
        fg_now = int(user32.GetForegroundWindow() or 0) == int(hwnd)
        results['P2_modal_open'] = dict(
            fg_switch_to_main_ok=fg_now,
            pump=pump_latency_ms(hwnd),
            drag=drag_title(hwnd))
        time.sleep(2.6)
        results['P2_after_close'] = dict(drag=drag_title(hwnd))

        issue(cmd='burst', n=120)
        time.sleep(0.03)
        lat = pump_latency_ms(hwnd)
        drag = drag_title(hwnd, steps=8, step_ms=25)
        time.sleep(0.3)
        results['P3_comports_burst'] = dict(latency_during=lat, drag=drag, burst_ms=CMD.get('burst_ms'))

        issue(cmd='stall', ms=600)
        time.sleep(0.04)
        lat = pump_latency_ms(hwnd)
        drag = drag_title(hwnd, steps=10, step_ms=35)
        time.sleep(0.4)
        results['P4_stall_600ms'] = dict(latency_during=lat, drag=drag)

        issue(cmd='stall', ms=5600)
        time.sleep(2.0)
        hung_2s = is_hung(hwnd)
        lat_2s = pump_latency_ms(hwnd, timeout_ms=300)
        time.sleep(3.3)
        hung_5s = is_hung(hwnd)
        results['P4b_stall_5600ms'] = dict(hung_at_2s=hung_2s, latency_at_2s=lat_2s, hung_at_5s=hung_5s)
        results['P4c_after_recover'] = dict(drag=drag_title(hwnd))

        issue(cmd='maximize')
        time.sleep(0.6)
        results['P5_maximized'] = dict(drag=drag_title(hwnd))
        issue(cmd='restore')
        time.sleep(0.5)
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
