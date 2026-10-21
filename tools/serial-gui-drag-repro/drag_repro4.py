# -*- coding: utf-8 -*-
"""在真实 Workbench 外壳上定位“菜单栏右侧拖不动”：
1) childAt/widgetAt 逐点探测，找出那段空白归哪个控件；
2) 真实鼠标注入，分别拖“标题文字区”和“菜单栏右侧空白区”，对比位移。
不写配置、不枚举串口、不碰硬件。
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
        return dict(result='not-foreground-skipped', before=before)
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
    return dict(result='ok', before=before, after=after,
                moved=[after[0] - before[0], after[1] - before[1]])


def issue(**kw):
    CMD.clear()
    CMD.update(kw)


ENUMPROTO = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def find_own_window(title):
    """只找本进程的窗口，避免误伤用户正在运行的实例。"""
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


def controller(results, app):
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

        def fresh_points():
            issue(cmd='points')
            for _ in range(100):
                pts = CMD.get('points')
                if pts:
                    return pts
                time.sleep(0.05)
            return None

        pts0 = fresh_points()
        if not pts0:
            results['error'] = 'points-timeout'
            issue(cmd='quit')
            return
        results['probe'] = pts0

        def phys(pts, logical_xy):
            rect = get_rect(hwnd)
            factor = (rect[2] - rect[0]) / pts['frame'][2]
            return (round(rect[0] + (logical_xy[0] - pts['frame'][0]) * factor),
                    round(rect[1] + (logical_xy[1] - pts['frame'][1]) * factor))

        # 拖 1：标题文字区（预期可拖）
        pts = fresh_points()
        x, y = phys(pts, pts['brand'])
        results['drag_brand'] = drag_at(hwnd, x, y)
        time.sleep(0.3)
        # 拖 2：菜单栏右侧空白（用户圈红的那段；fresh 坐标）
        pts = fresh_points()
        x, y = phys(pts, pts['tail'])
        results['drag_menu_tail'] = drag_at(hwnd, x, y)
        issue(cmd='quit')
    except Exception:
        results['error'] = traceback.format_exc()
        issue(cmd='quit')


def main():
    import serial_gui_qt as gui
    app = QApplication.instance() or QApplication(sys.argv[:1])
    w = gui.Workbench(persist=False, port_provider=lambda: [])
    w.show()

    def poll():
        cmd = CMD.get('cmd')
        if not cmd:
            return
        CMD['cmd'] = None
        if cmd == 'points':
            ts = w.title_strip
            fg = w.frameGeometry()
            labels = [l for l in ts.findChildren(QLabel) if l.text() == 'Serial Workbench']
            brand = labels[0] if labels else None
            menus = ts.findChildren(QMenuBar)
            mb = menus[0] if menus else None
            btns = sorted([b for b in ts.findChildren(QToolButton) if b.parent() is ts],
                          key=lambda b: b.x())
            first_btn_x = btns[0].x() if btns else ts.width()
            tail_x = ((mb.x() + mb.width() + first_btn_x) // 2) if mb else ts.width() // 2
            tp = QPoint(tail_x, ts.height() // 2)
            probe = []
            for fx in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9):
                p = QPoint(int(fx * ts.width()), ts.height() // 2)
                c = ts.childAt(p)
                g = ts.mapToGlobal(p)
                wa = QApplication.widgetAt(g)
                probe.append(dict(fx=fx,
                                  childAt=None if c is None else f'{type(c).__name__}({c.objectName()})',
                                  childAt_geom=None if c is None else [c.x(), c.y(), c.width(), c.height()],
                                  widgetAt=None if wa is None else f'{type(wa).__name__}({wa.objectName()})'))
            CMD['points'] = dict(
                frame=[fg.x(), fg.y(), fg.width(), fg.height()],
                brand=None if brand is None else [brand.mapToGlobal(brand.rect().center()).x(),
                                                  brand.mapToGlobal(brand.rect().center()).y()],
                tail=[ts.mapToGlobal(tp).x(), ts.mapToGlobal(tp).y()],
                strip=dict(w=ts.width(), h=ts.height(), maximized=w.isMaximized()),
                menu=None if mb is None else dict(x=mb.x(), width=mb.width(),
                                                  hint=mb.sizeHint().width(),
                                                  hpolicy=str(mb.sizePolicy().horizontalPolicy())),
                children=[dict(cls=type(c).__name__, name=c.objectName(),
                               geom=[c.x(), c.y(), c.width(), c.height()],
                               visible=c.isVisible(), enabled=c.isEnabled(),
                               transparent=bool(c.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)))
                          for c in ts.findChildren(QWidget) if c.parent() is ts],
                probe=probe)
        elif cmd == 'quit':
            QApplication.instance().quit()

    poller = QTimer(w)
    poller.timeout.connect(poll)
    poller.start(15)
    results = {}
    th = threading.Thread(target=controller, args=(results, app), daemon=True)
    th.start()
    app.exec()
    th.join(timeout=3)
    print(json.dumps(results, ensure_ascii=True, default=str, indent=1))


if __name__ == '__main__':
    main()
