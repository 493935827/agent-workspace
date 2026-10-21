# -*- coding: utf-8 -*-
"""真外壳最终验证：
P1 窗口化：拖 QMenuBar 自身空白区（sizeHint 之外被撑出来的部分）——预期死区
P2 窗口化：拖菜单栏与标题按钮之间的纯空白——预期可拖（对照）
P3 最大化：拖标题文字区 / 菜单空白区——预期全部拖不动（startSystemMove 对最大化无效）
P4 还原后：再拖标题文字区——预期恢复可拖
"""
import ctypes
import json
import os
import sys
import threading
import time
import traceback
from ctypes import wintypes

sys.path.insert(0, r'D:\App\agent-workspace\skills\serial-debug\scripts')

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (QApplication, QLabel, QMenuBar, QToolButton, QWidget)

user32 = ctypes.WinDLL('user32', use_last_error=True)
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

WORKBENCH_TITLE = 'Serial Workbench — Qt 串口工作台'
CMD = {}
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


def force_foreground(hwnd):
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 0x0002, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.06)
    return int(user32.GetForegroundWindow() or 0) == int(hwnd)


def drag_at(hwnd, px, py, dx=130, dy=70, steps=10, step_ms=22):
    before = get_rect(hwnd)
    cur0 = get_cursor()
    if not force_foreground(hwnd):
        return dict(result='not-foreground-skipped')
    set_cursor_abs(px, py)
    time.sleep(0.04)
    send_mouse(ME_DOWN)
    time.sleep(0.02)
    for i in range(1, steps + 1):
        set_cursor_abs(px + dx * i // steps, py + dy * i // steps)
        time.sleep(step_ms / 1000)
    send_mouse(ME_UP)
    time.sleep(0.25)
    set_cursor_abs(*cur0)
    after = get_rect(hwnd)
    return dict(result='ok', moved=[after[0] - before[0], after[1] - before[1]])


ENUMPROTO = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def find_own_window(title):
    hits = []
    pid_self = os.getpid()

    def on_window(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value == title:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == pid_self:
                    hits.append(hwnd)
        return True

    user32.EnumWindows(ENUMPROTO(on_window), 0)
    return hits[0] if hits else 0


def issue(**kw):
    CMD.clear()
    CMD.update(kw)


def main():
    import serial_gui_qt as gui
    app = QApplication.instance() or QApplication(sys.argv[:1])
    w = gui.Workbench(persist=False, port_provider=lambda: [])
    w.show()

    def dump_points():
        ts = w.title_strip
        fg = w.frameGeometry()
        labels = [l for l in ts.findChildren(QLabel) if l.text() == 'Serial Workbench']
        brand = labels[0] if labels else None
        mb = ts.findChildren(QMenuBar)[0]
        btns = sorted([b for b in ts.findChildren(QToolButton) if b.parent() is ts],
                      key=lambda b: b.x())
        first_btn_x = btns[0].x() if btns else ts.width()
        # 菜单栏内部空白：菜单宽度末端往左 50px（保证无菜单项）
        menu_empty = mb.mapToGlobal(QPoint(max(0, mb.width() - 50), mb.height() // 2))
        no_action = mb.actionAt(QPoint(max(0, mb.width() - 50), mb.height() // 2)) is None
        # 纯空白：菜单栏右端 与 第一个标题按钮之间
        stretch_x = (mb.x() + mb.width() + first_btn_x) // 2
        stretch = ts.mapToGlobal(QPoint(stretch_x, ts.height() // 2))
        def g2p(g):
            return [g.x(), g.y()]
        CMD['points'] = dict(
            frame=[fg.x(), fg.y(), fg.width(), fg.height()],
            maximized=w.isMaximized(),
            menu=dict(x=mb.x(), width=mb.width(), hint=mb.sizeHint().width()),
            menu_empty=g2p(menu_empty) + [no_action],
            brand=g2p(brand.mapToGlobal(brand.rect().center())) if brand else None,
            stretch=g2p(stretch))

    def poll():
        cmd = CMD.get('cmd')
        if not cmd:
            return
        CMD['cmd'] = None
        if cmd == 'points':
            dump_points()
        elif cmd == 'maximize':
            w.showMaximized()
        elif cmd == 'restore':
            w.showNormal()
        elif cmd == 'quit':
            QApplication.instance().quit()

    poller = QTimer(w)
    poller.timeout.connect(poll)
    poller.start(15)

    def fresh_points():
        issue(cmd='points')
        for _ in range(100):
            pts = CMD.get('points')
            if pts:
                return pts
            time.sleep(0.05)
        return None

    def controller():
        try:
            hwnd = 0
            for _ in range(200):
                hwnd = find_own_window(WORKBENCH_TITLE)
                if hwnd:
                    break
                time.sleep(0.05)
            if not hwnd:
                results['error'] = 'window-not-found'
                issue(cmd='quit')
                return
            time.sleep(1.0)

            def phys(pts, logical_xy):
                rect = get_rect(hwnd)
                factor = (rect[2] - rect[0]) / pts['frame'][2]
                return (round(rect[0] + (logical_xy[0] - pts['frame'][0]) * factor),
                        round(rect[1] + (logical_xy[1] - pts['frame'][1]) * factor))

            def drag(key):
                pts = fresh_points()
                if not pts:
                    return dict(error='points-timeout')
                x, y = phys(pts, pts[key])
                out = drag_at(hwnd, x, y)
                out['maximized_at_test'] = pts['maximized']
                out['menu_w'] = pts['menu']['width']
                return out

            results['P1_windowed_menu_empty'] = drag('menu_empty')
            time.sleep(0.3)
            results['P2_windowed_stretch'] = drag('stretch')
            time.sleep(0.3)
            issue(cmd='maximize')
            time.sleep(0.8)
            results['P3_max_brand'] = drag('brand')
            time.sleep(0.3)
            results['P3b_max_menu_empty'] = drag('menu_empty')
            time.sleep(0.3)
            issue(cmd='restore')
            time.sleep(0.8)
            results['P4_restored_brand'] = drag('brand')
            issue(cmd='quit')
        except Exception:
            results['error'] = traceback.format_exc()
            issue(cmd='quit')

    results = {}
    th = threading.Thread(target=controller, daemon=True)
    th.start()
    app.exec()
    th.join(timeout=3)
    print(json.dumps(results, ensure_ascii=True, default=str, indent=1))


if __name__ == '__main__':
    main()
