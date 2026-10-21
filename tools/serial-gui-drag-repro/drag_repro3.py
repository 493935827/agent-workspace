# -*- coding: utf-8 -*-
"""A/B 复现：无边框窗口顶栏 = TitleStrip(整行可拖) + QMenuBar(Expanding)。
A 条：与工作台完全一致的拼法 —— 预期标题区可拖、菜单栏右侧空白拖不动；
B 条：修复版 —— QMenuBar 子类在空白处按下时调 startSystemMove() —— 预期整段可拖。
"""
import ctypes
import json
import sys
import threading
import time
import traceback
from ctypes import wintypes

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,
                               QMenuBar, QToolButton, QVBoxLayout, QWidget)

user32 = ctypes.WinDLL('user32', use_last_error=True)
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

TITLE = 'DSZ 顶栏拖动 A/B'
CMD = {}
ME_MOVE, ME_DOWN, ME_UP = 0x0001, 0x0002, 0x0004
ME_ABS, ME_VIRT = 0x8000, 0x4000
ULONG_PTR = ctypes.c_size_t
SMTO_ABORTIFHUNG = 0x0002


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


def drag_at(hwnd, px, py, dx=120, dy=60, steps=10, step_ms=22):
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


class StripBase(QWidget):
    """与原型 TitleStrip 相同：整行左键按下即 startSystemMove。"""
    flag = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            CMD[self.flag] = True
            self.window().windowHandle().startSystemMove()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            w = self.window().windowHandle()
            if w and w.windowStates() & Qt.WindowState.WindowMaximized:
                w.setWindowStates(Qt.WindowState.WindowNoState)
            else:
                w.setWindowStates(Qt.WindowState.WindowMaximized)


class StripA(StripBase):
    flag = 'pressA'


class StripB(StripBase):
    flag = 'pressB'


class DragMenuBar(QMenuBar):
    """修复版：按在空白处（无菜单项）时交给窗口移动。"""
    flag = 'pressBmenu'

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.actionAt(event.pos()) is None:
            CMD[self.flag] = True
            self.window().windowHandle().startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)


def make_menu(klass):
    m = klass()
    m.setNativeMenuBar(False)
    m.addMenu('文件(&F)').addAction('退出', lambda: None)
    m.addMenu('编辑(&E)').addAction('复制', lambda: None)
    return m


class Demo(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.resize(760, 300)
        self.move(300, 300)
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(1, 1, 1, 1)
        v.setSpacing(0)
        for strip_klass, menu_klass, tag in ((StripA, QMenuBar, 'A 问题版'),
                                             (StripB, DragMenuBar, 'B 修复版')):
            strip = strip_klass()
            strip.setObjectName('top')
            strip.setFixedHeight(30)
            h = QHBoxLayout(strip)
            h.setContentsMargins(12, 0, 0, 0)
            h.setSpacing(8)
            brand = QLabel('Serial Workbench')
            h.addWidget(brand)
            h.addWidget(QLabel(tag))
            menu = make_menu(menu_klass)
            h.addWidget(menu)          # QMenuBar 默认 Expanding，铺满剩余宽度
            h.addStretch()             # 拿不到宽度，只是形式
            for _ in range(3):
                b = QToolButton()
                b.setFixedSize(34, 28)
                h.addWidget(b)
            v.addWidget(strip)
            if strip_klass is StripA:
                self.stripA, self.menuA, self.brandA = strip, menu, brand
            else:
                self.stripB, self.menuB = strip, menu
        v.addStretch()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_cmd)
        self.timer.start(15)

    def poll_cmd(self):
        cmd = CMD.get('cmd')
        if not cmd:
            return
        CMD['cmd'] = None
        if cmd == 'points':
            fg = self.frameGeometry()
            def center(w):
                g = w.mapToGlobal(w.rect().center())
                return [g.x(), g.y()]
            def tail(menu):
                g = menu.mapToGlobal(QPoint(0, 0))
                return [g.x() + menu.width() - 40, g.y() + menu.height() // 2]
            CMD['points'] = dict(
                frame=[fg.x(), fg.y(), fg.width(), fg.height()],
                brand=center(self.brandA),
                tailA=tail(self.menuA), tailB=tail(self.menuB),
                menuA_width=self.menuA.width(), stripA_width=self.stripA.width(),
                tailA_no_action=self.menuA.actionAt(
                    QPoint(self.menuA.width() - 60, self.menuA.height() // 2)) is None,
                tailB_no_action=self.menuB.actionAt(
                    QPoint(self.menuB.width() - 60, self.menuB.height() // 2)) is None)
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
        issue(cmd='points')
        pts = None
        for _ in range(100):
            pts = CMD.get('points')
            if pts:
                break
            time.sleep(0.05)
        if not pts:
            results['error'] = 'points-timeout'
            return
        results['layout'] = dict(menuA_width=pts['menuA_width'], stripA_width=pts['stripA_width'],
                                 tailA_no_action=pts['tailA_no_action'],
                                 tailB_no_action=pts['tailB_no_action'])
        rect = get_rect(hwnd)
        factor = (rect[2] - rect[0]) / pts['frame'][2]

        def phys(p):
            return (round(rect[0] + (p[0] - pts['frame'][0]) * factor),
                    round(rect[1] + (p[1] - pts['frame'][1]) * factor))

        # 1) A 条标题文字处拖动（基线：应可拖）
        issue(cmd='noop')
        CMD['pressA'] = False
        x, y = phys(pts['brand'])
        results['A1_title_label'] = dict(drag=drag_at(hwnd, x, y), press_reached_stripA=CMD.get('pressA'))
        time.sleep(0.3)
        # 2) A 条菜单栏右侧空白拖动（问题点：预期拖不动）
        CMD['pressA'] = False
        x, y = phys(pts['tailA'])
        results['A2_menu_tail'] = dict(drag=drag_at(hwnd, x, y), press_reached_stripA=CMD.get('pressA'))
        time.sleep(0.3)
        # 3) B 条菜单栏右侧空白拖动（修复版：预期可拖）
        CMD['pressBmenu'] = False
        x, y = phys(pts['tailB'])
        results['B1_menu_tail_fixed'] = dict(drag=drag_at(hwnd, x, y),
                                             press_reached_menubar=CMD.get('pressBmenu'))
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
