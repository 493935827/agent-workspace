"""Standalone Qt visual preview matching the September 11 reference. In-memory simulated data only.

Run: python serial_gui_qt_prototype.py
The actual Qt widgets are the visual reference, not an HTML/image mockup.

Workbench pass (2026-09-11): DevTools-grade UX refinement — stateful header,
log toolbar with type filters, aligned log columns, collapsible side panels,
macro manager tab, log settings tab and a slim status bar.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from tempfile import TemporaryDirectory
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QSize, QObject, QEvent, QRect, QByteArray
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import (QAction, QColor, QFont, QKeySequence, QPalette,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextBlockFormat, QPainter, QIcon, QPixmap, QMouseEvent, QFocusEvent, QShortcut, QCursor)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QPlainTextEdit, QPushButton, QSizePolicy, QSplitter, QStackedWidget,
    QStyleFactory, QTextEdit, QVBoxLayout, QWidget, QMessageBox, QToolButton, QMenuBar, QMenu, QTabBar, QTabWidget, QFormLayout, QFileDialog, QInputDialog, QLayout, QDialog, QDialogButtonBox)


class SessionTabBar(QTabBar):
    def minimumSizeHint(self):
        # Qt reserves room for scroll buttons even with one short tab. Never
        # let that minimum create a blank tail before the new-session button.
        return super().minimumSizeHint().boundedTo(self.sizeHint())


def row(*items, margins=(0, 0, 0, 0), spacing=8):
    host = QWidget()
    layout = QHBoxLayout(host)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for item in items:
        if item is None:
            layout.addStretch()
        else:
            layout.addWidget(item)
    return host


def label(text, role=None):
    widget = QLabel(text)
    if role:
        widget.setProperty('role', role)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setAccessibleName(text)
    widget.clicked.connect(callback)
    if primary:
        widget.setProperty('fluentAppearance', 'primary')
    return widget


def set_role(widget, role):
    if widget.property('role') == role:
        return
    widget.setProperty('role', role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_fluent_property(widget, name, value):
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()

# Original, consistent 24-unit outline SVG symbols; no external image dependencies.
ICON_PATHS = {
    'status': '<circle cx="12" cy="12" r="4" fill="currentColor"/>',
    'terminal': '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m7 8 4 4-4 4m6 0h4"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'close': '<path d="m6 6 12 12M6 18 18 6"/>',
    'minimize': '<path d="M5 12h14"/>',
    'maximize': '<rect x="5" y="5" width="14" height="14" rx="1"/>',
    'restore': '<path d="M8 5V3h13v13h-2"/><rect x="3" y="8" width="13" height="13"/>',
    'search': '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
    'usb': '<path d="M12 20V3m-3 3 3-3 3 3M12 15l-6-4V7m6 5 6-3V6"/><circle cx="12" cy="20" r="1"/><rect x="16" y="3" width="4" height="3"/>',
    'settings': '<circle cx="12" cy="12" r="4"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/>',
    'trash': '<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
    'save': '<path d="M4 3h13l4 4v14H3V3h1m3 0v7h10V3M7 21v-7h10v7"/>',
    'pause': '<path d="M7 5v14M17 5v14"/>',
    'play': '<path d="m7 4 13 8-13 8z"/>',
    'more': '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    'send': '<path d="m3 10 18-7-7 18-4-7-7-4 18-7M10 14l5-5"/>',
    'disconnect': '<path d="M7 3v6m10-6v6M5 9h14v3a7 7 0 0 1-14 0zM12 19v3"/>',
    'scan': '<circle cx="12" cy="12" r="8"/><path d="m12 12 7-9M8 12a4 4 0 0 0 4 4"/>',
    'edit': '<path d="m4 16 12-12 4 4L8 20H4zm10-10 4 4"/>',
    'help': '<circle cx="12" cy="12" r="9"/><path d="M9 8a3 3 0 0 1 6 1c0 2-3 2-3 5m0 3v1"/>',
    'down': '<path d="m7 10 5 5 5-5"/>',
    'chevron_left': '<path d="m15 6-6 6 6 6"/>',
    'chevron_right': '<path d="m9 6 6 6-6 6"/>',
    'history': '<path d="M12 8v5l3 2"/><circle cx="12" cy="12" r="9"/>',
    'refresh': '<path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5"/>',
}

def icon(name, color=None):
    color = color or QApplication.palette().color(QPalette.ColorRole.WindowText).name()
    data = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
            f'<g color="{color}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
            + ICON_PATHS[name] + '</g></svg>')
    pix = QPixmap(48, 48)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    QSvgRenderer(QByteArray(data.encode())).render(painter)
    painter.end()
    return QIcon(pix)

def tool(name, text, callback, vertical=False):
    w = QToolButton()
    w.setProperty('iconName', name)
    w.setIcon(icon(name))
    w.setIconSize(QSize(16, 16))
    w.setText(text)
    w.setAccessibleName(text)
    w.setToolTip(text)
    w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    w.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon if vertical else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    w.clicked.connect(callback)
    return w

# Session connection states shared across the header, device list and dialogs.
SESSION_STATE_TEXT = {'connected': '已连接', 'disconnected': '未连接', 'connecting': '连接中', 'error': '连接异常'}
SESSION_STATE_COLOR = {'connected': 'success_foreground', 'disconnected': 'text_secondary',
                       'connecting': 'brand_foreground', 'error': 'warning_foreground'}
SESSION_STATE_ROLE = {'connected': 'success', 'disconnected': 'muted', 'connecting': 'info', 'error': 'warning'}
CONNECT_LABEL = {'connected': '断开连接', 'disconnected': '连接', 'connecting': '连接中…', 'error': '重连'}
CONNECT_ICON = {'connected': 'disconnect', 'disconnected': 'usb', 'connecting': 'scan', 'error': 'refresh'}

# Log tag column colors; the body keeps its own entry color so whole lines are not flooded.
TAG_COLORS = {'TX': 'brand_foreground', 'WARN': 'warning_foreground', 'ERROR': 'danger_foreground',
              'OK': 'success_foreground', 'BOOT': 'brand_foreground', 'DEMO': 'success_foreground',
              'RX': 'text_tertiary', 'INFO': 'text_secondary', 'SYS': 'text_secondary'}
TAG_SEVERITY = {'ERROR': 3, 'WARN': 2}

def fmt_bytes(count):
    if count < 1024:
        return f'{count} B'
    if count < 1024 ** 2:
        return f'{count / 1024:.1f} KB'
    return f'{count / 1024 ** 2:.1f} MB'

def parse_hex(text):
    """Parse '01 a3 0x0B' style input into bytes, or None when invalid."""
    cleaned = re.sub(r'0x|[\s,]', '', text, flags=re.IGNORECASE)
    if not cleaned or len(cleaned) % 2 or re.search(r'[^0-9a-fA-F]', cleaned):
        return None
    return bytes.fromhex(cleaned)

class TitleStrip(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().toggle_maximize()

class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent(self, event):
        e = self.editor
        painter = QPainter(self)
        palette = e.palette()
        painter.fillRect(event.rect(), palette.color(QPalette.ColorRole.AlternateBase))
        painter.setPen(palette.color(QPalette.ColorRole.PlaceholderText))
        painter.setFont(e.font())
        block = e.firstVisibleBlock()
        top = round(e.blockBoundingGeometry(block).translated(e.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(e.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.drawText(0, top, self.width()-8, e.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, str(block.blockNumber()+1))
            top += height
            block = block.next()

# Window controllers adapted from the local pyside6-fluent-ui template.
class _ResizeHandle(QWidget):
    """Invisible client-edge target that delegates resizing to the window manager."""

    def __init__(
        self,
        window: QWidget,
        edges: Qt.Edge,
        cursor: Qt.CursorShape,
        name: str,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._edges = edges
        self.setObjectName(f"framelessResizeHandle{name}")
        self.setCursor(cursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            start_resize = getattr(handle, "startSystemResize", None) if handle else None
            if callable(start_resize) and start_resize(self._edges):
                event.accept()
                return
        super().mousePressEvent(event)


class _CaptionButton(QToolButton):
    """Caption action that exposes a keyboard-only focus-visible property."""

    _KEYBOARD_REASONS = {
        Qt.FocusReason.TabFocusReason,
        Qt.FocusReason.BacktabFocusReason,
        Qt.FocusReason.ShortcutFocusReason,
    }

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802 - Qt API
        set_fluent_property(self, "keyboardFocus", event.reason() in self._KEYBOARD_REASONS)
        super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802 - Qt API
        set_fluent_property(self, "keyboardFocus", False)
        super().focusOutEvent(event)


class FramelessWindowController(QObject):
    """Restore Qt-native edge/corner resizing for a frameless top-level widget."""

    EDGE_SIZE = 6
    CORNER_SIZE = 12

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setObjectName("framelessWindowController")
        self.window = window
        top = Qt.Edge.TopEdge
        bottom = Qt.Edge.BottomEdge
        left = Qt.Edge.LeftEdge
        right = Qt.Edge.RightEdge
        definitions = {
            "TopLeft": (top | left, Qt.CursorShape.SizeFDiagCursor),
            "Top": (top, Qt.CursorShape.SizeVerCursor),
            "TopRight": (top | right, Qt.CursorShape.SizeBDiagCursor),
            "Left": (left, Qt.CursorShape.SizeHorCursor),
            "Right": (right, Qt.CursorShape.SizeHorCursor),
            "BottomLeft": (bottom | left, Qt.CursorShape.SizeBDiagCursor),
            "Bottom": (bottom, Qt.CursorShape.SizeVerCursor),
            "BottomRight": (bottom | right, Qt.CursorShape.SizeFDiagCursor),
        }
        self.handles = {
            name: _ResizeHandle(window, edges, cursor, name)
            for name, (edges, cursor) in definitions.items()
        }
        window.installEventFilter(self)
        self._update_handles()

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if watched is self.window and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.WindowStateChange,
        ):
            self._update_handles()
        return super().eventFilter(watched, event)

    def _update_handles(self) -> None:
        maximized = self.window.isMaximized() or self.window.isFullScreen()
        for handle in self.handles.values():
            handle.setVisible(not maximized)
        if maximized:
            return

        width = self.window.width()
        height = self.window.height()
        edge = self.EDGE_SIZE
        corner = min(self.CORNER_SIZE, max(0, width // 2), max(0, height // 2))
        middle_width = max(0, width - 2 * corner)
        middle_height = max(0, height - 2 * corner)
        geometries = {
            "TopLeft": (0, 0, corner, corner),
            "Top": (corner, 0, middle_width, edge),
            "TopRight": (max(0, width - corner), 0, corner, corner),
            "Left": (0, corner, edge, middle_height),
            "Right": (max(0, width - edge), corner, edge, middle_height),
            "BottomLeft": (0, max(0, height - corner), corner, corner),
            "Bottom": (corner, max(0, height - edge), middle_width, edge),
            "BottomRight": (
                max(0, width - corner),
                max(0, height - corner),
                corner,
                corner,
            ),
        }
        for name, geometry in geometries.items():
            self.handles[name].setGeometry(*geometry)  # fluent-audit: allow resize hit targets
            self.handles[name].raise_()



"""Optional Windows 11 Snap Layout support for the frameless title-bar profile."""



import ctypes
import sys

from PySide6.QtCore import QByteArray, QPoint, QPointF, QTimer, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QToolButton, QWidget



WM_NCHITTEST = 0x0084
WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCMOUSELEAVE = 0x02A2
WM_CANCELMODE = 0x001F
HTMAXBUTTON = 9


class _NativePoint(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


class _NativeMessage(ctypes.Structure):
    _fields_ = (
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt", _NativePoint),
        ("lPrivate", ctypes.c_uint),
    )


def windows_snap_layout_supported() -> bool:
    """Return whether this process is running on Windows 11 or newer."""
    if sys.platform != "win32":
        return False
    version = sys.getwindowsversion()
    return version.major >= 10 and version.build >= 22000


def _signed_word(value: int) -> int:
    return ctypes.c_short(value & 0xFFFF).value


def screen_point_from_lparam(lparam: int) -> QPoint:
    """Decode signed virtual-screen coordinates from a Win32 message lParam."""
    return QPoint(_signed_word(lparam), _signed_word(lparam >> 16))


class WindowsSnapLayoutWindowMixin:
    """Route top-level native messages to an attached Snap Layout adapter."""

    def nativeEvent(  # noqa: N802 - Qt API
        self,
        event_type: QByteArray,
        message: int,
    ) -> tuple[bool, int]:
        adapter = getattr(self, "windows_snap_layout_adapter", None)
        if adapter is not None:
            handled, result = adapter.handle_native_event(event_type, message)
            if handled:
                return handled, result
        return super().nativeEvent(event_type, message)  # type: ignore[misc]


class WindowsSnapLayoutAdapter:
    """Expose a custom Qt maximize button as ``HTMAXBUTTON`` on Windows 11.

    The adapter intentionally owns only the maximize-button hit result. Every
    other native message is returned to Qt, so ``FramelessWindowController``
    remains responsible for client-side edge and corner resize targets.
    """

    EVENT_TYPES = {b"windows_generic_MSG", b"windows_dispatcher_MSG"}

    def __init__(
        self,
        window: QWidget,
        maximize_button: QToolButton,
        *,
        enabled: bool | None = None,
    ) -> None:
        self.window = window
        self.maximize_button = maximize_button
        supported = windows_snap_layout_supported()
        requested = supported if enabled is None else bool(enabled)
        has_maximize_hint = bool(
            window.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint
        )
        has_native_route = isinstance(window, WindowsSnapLayoutWindowMixin)
        self.enabled = bool(
            requested and supported and has_maximize_hint and has_native_route
        )
        self._installed = self.enabled
        self._native_hover = False
        self._pending_native_hover = False
        self._pending_button_down = False
        self._pending_button_activation = False
        self._window_id = int(window.winId()) if self.enabled else 0
        self._hover_apply_timer = QTimer(window)
        self._hover_apply_timer.setSingleShot(True)
        self._hover_apply_timer.timeout.connect(self._apply_pending_native_hover)
        self._hover_timer = QTimer(window)
        self._hover_timer.setInterval(80)
        self._hover_timer.timeout.connect(self._sync_native_hover)
        self._interaction_timer = QTimer(window)
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.timeout.connect(self._apply_pending_interaction)

    @property
    def installed(self) -> bool:
        return self._installed

    def dispose(self, *_args: object) -> None:
        """Disable the adapter and clear its deferred interaction state."""
        try:
            self._hover_apply_timer.stop()
            self._hover_timer.stop()
            self._interaction_timer.stop()
        except RuntimeError:
            pass
        self._installed = False
        self._pending_native_hover = False
        self._pending_button_down = False
        self._pending_button_activation = False
        self._set_native_hover(False)

    def hit_test_client_position(self, position: QPointF | QPoint) -> int | None:
        """Return the native hit result for a Qt client-area position."""
        if self.maximize_button.isHidden() or not self.maximize_button.isEnabled():
            return None
        point = position.toPoint() if isinstance(position, QPointF) else position
        local = self.maximize_button.mapFrom(self.window, point)
        if self.maximize_button.rect().contains(local):
            return HTMAXBUTTON
        return None

    def handle_native_event(
        self,
        event_type: QByteArray,
        message: int,
    ) -> tuple[bool, int]:
        if not self.enabled or bytes(event_type) not in self.EVENT_TYPES:
            return False, 0

        try:
            native_message = ctypes.cast(
                int(message), ctypes.POINTER(_NativeMessage)
            ).contents
        except (TypeError, ValueError, RuntimeError):
            return False, 0

        if int(native_message.hwnd or 0) != self._window_id:
            return False, 0
        if native_message.message in (WM_NCMOUSELEAVE, WM_CANCELMODE):
            self._queue_native_hover(False)
            if native_message.message == WM_CANCELMODE:
                self._pending_button_activation = False
            self._queue_button_interaction(down=False)
            return False, 0
        if native_message.message == WM_NCMOUSEMOVE:
            if int(native_message.wParam) == HTMAXBUTTON:
                self._queue_native_hover(True)
            return False, 0
        if (
            native_message.message in (WM_NCLBUTTONDOWN, WM_NCLBUTTONUP)
            and int(native_message.wParam) == HTMAXBUTTON
        ):
            pressed = native_message.message == WM_NCLBUTTONDOWN
            self._queue_button_interaction(
                down=pressed,
                activate=not pressed,
            )
            return True, 0
        if native_message.message != WM_NCHITTEST:
            return False, 0

        client_position = self._client_position_from_lparam(
            self._window_id, native_message.lParam
        )
        result = self.hit_test_client_position(client_position)
        self._queue_native_hover(result == HTMAXBUTTON)
        if result == HTMAXBUTTON:
            if not self._hover_timer.isActive():
                self._hover_timer.start()
            return True, HTMAXBUTTON
        return False, 0

    def _client_position_from_lparam(self, hwnd: int, lparam: int) -> QPointF:
        screen_position = screen_point_from_lparam(lparam)
        if sys.platform != "win32":
            return QPointF(screen_position)

        point = _NativePoint(screen_position.x(), screen_position.y())
        user32 = ctypes.windll.user32
        if not user32.ScreenToClient(ctypes.c_void_p(hwnd), ctypes.byref(point)):
            return QPointF(screen_position)
        dpi_getter = getattr(user32, "GetDpiForWindow", None)
        dpi = int(dpi_getter(ctypes.c_void_p(hwnd))) if dpi_getter else 96
        scale = max(1.0, dpi / 96.0)
        return QPointF(point.x / scale, point.y / scale)

    def _sync_native_hover(self) -> None:
        try:
            local = self.maximize_button.mapFromGlobal(QCursor.pos())
            hovering = (
                self.maximize_button.isVisible()
                and self.maximize_button.isEnabled()
                and self.maximize_button.rect().contains(local)
            )
        except RuntimeError:
            hovering = False
        self._queue_native_hover(hovering)
        if not hovering:
            self._hover_timer.stop()

    def _queue_native_hover(self, hovering: bool) -> None:
        """Defer Qt repolishing until native window-message handling has returned."""
        self._pending_native_hover = hovering
        if not self._hover_apply_timer.isActive():
            self._hover_apply_timer.start(0)

    def _apply_pending_native_hover(self) -> None:
        self._set_native_hover(self._pending_native_hover)

    def _queue_button_interaction(
        self,
        *,
        down: bool,
        activate: bool = False,
    ) -> None:
        self._pending_button_down = down
        self._pending_button_activation = (
            self._pending_button_activation or activate
        )
        if not self._interaction_timer.isActive():
            self._interaction_timer.start(0)

    def _apply_pending_interaction(self) -> None:
        try:
            self.maximize_button.setDown(self._pending_button_down)
            if self._pending_button_activation:
                self._pending_button_activation = False
                self.maximize_button.click()
        except RuntimeError:
            self._pending_button_activation = False

    def _set_native_hover(self, hovering: bool) -> None:
        if self._native_hover == hovering:
            return
        self._native_hover = hovering
        try:
            set_fluent_property(self.maximize_button, "nativeHover", hovering)
        except RuntimeError:
            pass


class LogView(QPlainTextEdit):
    """Read-only log with an explicit, simulated direct-key input path."""
    transmit = Signal(str)

    def __init__(self):
        super().__init__()
        self.main = None
        self.direct = False
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont('Consolas', 8))
        self.setObjectName('serialLog')
        self.log_scale = 1.0
        self.numbers = LineNumbers(self)
        self.setViewportMargins(30, 0, 0, 0)
        self.updateRequest.connect(lambda rect, dy: self.numbers.update())
        self.blockCountChanged.connect(lambda _: self.numbers.update())
        self.setAccessibleName('串口接收日志；直接发送模式下可输入模拟按键')

    def set_log_scale(self, scale):
        self.log_scale = scale
        font = QFont('Consolas')
        font.setPointSizeF(8*scale)
        self.setFont(font)
        self.setViewportMargins(round(30*scale), 0, 0, 0)
        self.numbers.setGeometry(1, 1, round(30*scale), self.height()-2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.numbers.setGeometry(1, 1, round(30*self.log_scale), self.height()-2)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            return super().keyPressEvent(event)
        if self.direct and event.matches(QKeySequence.StandardKey.Paste):
            self.transmit.emit(QApplication.clipboard().text())
            return
        keys = {Qt.Key.Key_Return: '\r', Qt.Key.Key_Enter: '\r',
                Qt.Key.Key_Backspace: '\x7f', Qt.Key.Key_Up: '\x1b[A',
                Qt.Key.Key_Down: '\x1b[B', Qt.Key.Key_Right: '\x1b[C',
                Qt.Key.Key_Left: '\x1b[D'}
        if self.direct and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            value = keys.get(event.key(), event.text())
            if value:
                self.transmit.emit(value)
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        if self.main is not None:
            menu = self.main.log_menu(self)
            menu.exec(event.globalPos())
            menu.deleteLater()
            event.accept()
        else:
            super().contextMenuEvent(event)


class MacroRow(QWidget):
    """One saved macro: click selects it, the play button runs it immediately."""

    def __init__(self, index, command, description, main):
        super().__init__()
        self.index = index
        self.main = main
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(6)
        self.run_button = QToolButton()
        self.run_button.setProperty('iconName', 'play')
        self.run_button.setIcon(icon('play'))
        self.run_button.setIconSize(QSize(14, 14))
        self.run_button.setFixedSize(20, 20)
        self.run_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_button.setAccessibleName(f'运行宏 {command}')
        self.run_button.setToolTip(f'运行 {command}')
        self.run_button.clicked.connect(lambda: main.run_macro_command(self.index))
        layout.addWidget(self.run_button)
        command_label = label(command, 'command')
        layout.addWidget(command_label)
        layout.addStretch()
        layout.addWidget(label(description, 'muted'))

    def mousePressEvent(self, event):
        self.main.macro_list.setCurrentRow(self.index)
        super().mousePressEvent(event)


class Preview(WindowsSnapLayoutWindowMixin, QMainWindow):
    def __init__(self, native_title=False, zoom=125):
        super().__init__()
        self.ui_scale = 1.0
        self.log_zoom = 1.0
        self._wheel_zoom_delta = 0
        self.native_title = native_title
        if not native_title:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle('Serial Workbench — Qt 界面预览')
        self.resize(946, 531)
        self.setMinimumSize(900, 530)
        self.tokens = json.loads(Path(__file__).with_name('qt-preview-tokens.json').read_text('utf-8'))['aliases']['colors']
        self.sessions = [dict(port='COM5', name='主控调试', state='connected', connected_at=datetime.now(), draft='', mode=0,
                              baud='115200', fmt='8N1', flow='无', query='', sent=0, received=0, rx_bytes=0, history=[], sent_log=[]),
                         dict(port='COM8', name='传感器模组', state='disconnected', connected_at=None, draft='', mode=0,
                              baud='921600', fmt='8N1', flow='无', query='', sent=0, received=0, rx_bytes=0, history=[], sent_log=[]),
                         dict(port='COM3', name='备用串口', state='disconnected', connected_at=None, draft='', mode=0,
                              baud='115200', fmt='8N1', flow='无', query='', sent=0, received=0, rx_bytes=0, history=[], sent_log=[])]
        self.active = -1
        self.dark = False
        self.ticks = 0
        self.paused = False
        self.pending = 0
        self.tag_filters = set()
        self.history_index = None
        self.history_draft = ''
        self.sidebar_collapsed = False
        self.inspector_collapsed = False
        self.connect_delay = 700
        self.matches = []
        self.match_index = -1
        self._icon_cache = {}
        self._theme_assets = TemporaryDirectory(prefix='serial-workbench-theme-')
        self.macros = [('status', '查询系统状态'), ('help', '显示帮助信息'), ('version', '查询固件版本'),
                       ('ram', '读取 RAM 数据'), ('css_pwr', '控制电源 --on'), ('reboot', '重启设备')]
        self.build()
        self.theme(False)
        self.seed()
        self.devices.setCurrentRow(0)
        self.timer = QTimer(self)
        self.timer.setInterval(850)
        self.timer.timeout.connect(self.tick)
        self._capture_scale_metrics()
        self.set_zoom(zoom)
        QApplication.instance().installEventFilter(self)

    def build(self):
        root = QFrame()
        root.setObjectName('windowFrame')
        outer = QVBoxLayout(root)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        self.setCentralWidget(root)
        self.title_strip = TitleStrip()
        self.title_strip.setObjectName('top')
        top = QHBoxLayout(self.title_strip)
        top.setContentsMargins(12, 0, 0, 0)
        top.setSpacing(8)
        logo = label('')
        logo.setProperty('iconName', 'terminal')
        logo.setPixmap(icon('terminal').pixmap(20, 20))
        logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        top.addWidget(logo)
        top.addWidget(label('Serial Workbench', 'brand'))
        top.addWidget(label('串口调试工作台', 'muted'))
        menu = QMenuBar()
        menu.setNativeMenuBar(False)
        top.addWidget(menu)
        top.addStretch()
        self.caption_buttons = []
        if not self.native_title:
            for name, text, callback in [('minimize', '最小化', self.showMinimized),
                                          ('maximize', '最大化', self.toggle_maximize),
                                          ('close', '关闭', self.close)]:
                b = tool(name, text, callback)
                b.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                b.setFixedSize(34, 28)
                top.addWidget(b)
                self.caption_buttons.append(b)
            self.snap_adapter = WindowsSnapLayoutAdapter(self, self.caption_buttons[1])
            self.windows_snap_layout_adapter = self.snap_adapter
        self.title_strip.setFixedHeight(30)
        outer.addWidget(self.title_strip)
        file_menu = menu.addMenu('文件(&F)')
        file_menu.addAction('保存日志…', self.save_log, 'Ctrl+S')
        file_menu.addAction('退出', self.close)
        edit_menu = menu.addMenu('编辑(&E)')
        edit_menu.addAction('复制', lambda: self.views[self.active].copy())
        view_menu = menu.addMenu('查看(&V)')
        search_action = view_menu.addAction('搜索日志', self.open_search)
        search_action.setShortcut(QKeySequence.StandardKey.Find)
        view_menu.addAction('聚焦命令输入', self.focus_command, 'Ctrl+L')
        view_menu.addAction('清屏', self.clear_log, 'Ctrl+K')
        zoom_menu = view_menu.addMenu('界面缩放')
        zoom_menu.addAction('放大', lambda: self.set_zoom(round(self.ui_scale*100)+25), 'Ctrl+=')
        zoom_menu.addAction('缩小', lambda: self.set_zoom(round(self.ui_scale*100)-25), 'Ctrl+-')
        zoom_menu.addAction('恢复界面 100%', lambda: self.set_zoom(100))
        log_zoom_menu = view_menu.addMenu('日志字号')
        log_zoom_menu.addAction('放大日志', lambda: self.set_log_zoom(round(self.log_zoom*100)+10))
        log_zoom_menu.addAction('缩小日志', lambda: self.set_log_zoom(round(self.log_zoom*100)-10))
        log_zoom_menu.addAction('恢复日志 100%', lambda: self.set_log_zoom(100), 'Ctrl+0')
        view_menu.addAction('切换浅色 / 深色', lambda: self.theme(not self.dark))
        view_menu.addAction('折叠 / 展开设备栏', lambda: self.set_sidebar_collapsed(not self.sidebar_collapsed), 'Ctrl+B')
        view_menu.addAction('折叠 / 展开右侧面板', lambda: self.set_inspector_collapsed(not self.inspector_collapsed), 'Ctrl+Shift+B')
        tools_menu = menu.addMenu('工具(&T)')
        tools_menu.addAction('宏编辑器', self.toggle_editor)
        tools_menu.addAction('暂停接收 / 恢复接收', self.toggle_pause)
        window_menu = menu.addMenu('窗口(&W)')
        window_menu.addAction('最大化 / 还原', self.toggle_maximize)
        window_menu.addAction('最小化', self.showMinimized)
        help_menu = menu.addMenu('帮助(&H)')
        help_menu.addAction('关于预览', self.about)
        self.system_menu = QMenu(self)
        self.system_menu.addAction('还原', self.showNormal)
        self.system_menu.addAction('最小化', self.showMinimized)
        self.system_menu.addAction('最大化', self.showMaximized)
        self.system_menu.addAction('关闭', self.close)
        shortcut = QShortcut(QKeySequence('Alt+Space'), self)
        shortcut.activated.connect(lambda: self.system_menu.popup(self.mapToGlobal(self.rect().topLeft())))
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter, 1)
        self._build_sidebar()
        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        self.tabs = SessionTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.addTab('COM5    主控调试')
        self.tabs.setTabData(0, 0)
        self.tabs.currentChanged.connect(lambda i: self.devices.setCurrentRow(self.tabs.tabData(i)) if i >= 0 else None)
        add_tab = tool('plus', '新建会话', self.new_session)
        add_tab.setObjectName('newSessionTab')
        add_tab.setFixedSize(24, 24)
        add_tab.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        tab_row = row(self.tabs, add_tab, None, margins=(0, 0, 8, 0), spacing=4)
        tab_row.setObjectName('tabs')
        tab_row.setFixedHeight(30)
        workspace_layout.addWidget(tab_row)
        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setHandleWidth(1)
        self.body_splitter.setChildrenCollapsible(False)
        workspace_layout.addWidget(self.body_splitter, 1)
        self._build_main(workspace_layout)
        self._build_inspector()
        self.splitter.addWidget(workspace)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([134, 810])
        self._build_status_bar(outer)
        self.ending.currentTextChanged.connect(lambda _: self.update_state())
        self.encoding.currentTextChanged.connect(lambda _: self.update_state())
        if not self.native_title:
            self.resize_controller = FramelessWindowController(self)

    def _build_sidebar(self):
        self.sidebar_host = QWidget()
        self.sidebar_host.setObjectName('sidebarHost')
        host_layout = QHBoxLayout(self.sidebar_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setMinimumWidth(132)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(8, 6, 8, 12)
        side.setSpacing(3)
        side.addWidget(row(label('设备会话', 'heading'), None,
                           tool('scan', '自动检测串口', self.detect),
                           tool('chevron_left', '折叠设备栏 (Ctrl+B)', lambda: self.set_sidebar_collapsed(True)),
                           spacing=2))
        for b in side.itemAt(0).widget().findChildren(QToolButton):
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        # Split button: main click creates a serial session, the arrow keeps room
        # for future transports (TCP / UDP / simulated devices).
        self.new_button = QToolButton()
        self.new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        new_menu = QMenu(self.new_button)
        serial_action = QAction(icon('plus'), '新建会话', self.new_button)
        serial_action.setToolTip('新建串口会话')
        serial_action.triggered.connect(self.new_session)
        new_menu.addAction(serial_action)
        for transport in ('TCP Client', 'TCP Server', 'UDP', '模拟设备'):
            action = QAction(f'{transport}（即将支持）', self.new_button)
            action.setEnabled(False)
            new_menu.addAction(action)
        self.new_button.setDefaultAction(serial_action)
        self.new_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.new_button.setMenu(new_menu)
        self.new_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.new_button.setProperty('iconName', 'plus')
        side.addWidget(self.new_button)
        self.devices = QListWidget()
        self.devices.setAccessibleName('设备会话')
        self.devices.setIconSize(QSize(8, 8))
        self.devices.setSpacing(2)
        for session in self.sessions:
            item = QListWidgetItem()
            item.setSizeHint(QSize(108, 42))
            self.devices.addItem(item)
        self.refresh_devices()
        self.devices.currentRowChanged.connect(self.switch)
        self.devices.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side.addWidget(self.devices, 1)
        self.sidebar_strip = self._build_strip('chevron_right', '展开设备栏 (Ctrl+B)',
                                               lambda: self.set_sidebar_collapsed(False), 'leftStrip')
        self.sidebar_strip.hide()
        host_layout.addWidget(self.sidebar)
        host_layout.addWidget(self.sidebar_strip)
        self.splitter.addWidget(self.sidebar_host)

    def _build_main(self, workspace_layout):
        main = QWidget()
        main.setObjectName('main')
        content = QVBoxLayout(main)
        content.setContentsMargins(6, 0, 6, 6)
        content.setSpacing(2)
        # Header: the current working object (device identity + live status).
        self.title = label('COM5', 'title')
        self.status_dot = label('')
        self.status_dot.setFixedSize(8, 8)
        self.connection = label('已连接', 'success')
        self.params = label('115200 · 8N1', 'muted')
        identity = QWidget()
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(2)
        identity_layout.addWidget(row(self.title, self.status_dot, self.connection, self.params, None, spacing=8))
        self.subtitle = label('主控调试 · USB Serial Port', 'muted')
        identity_layout.addWidget(self.subtitle)
        self.connect_btn = tool('disconnect', '断开连接', self.toggle_connection, True)
        self.clear_btn = tool('trash', '清屏', self.clear_log, True)
        self.clear_btn.setToolTip('清屏 (Ctrl+K)')
        self.save_btn = tool('save', '保存日志', self.save_log, True)
        self.save_btn.setToolTip('保存日志 (Ctrl+S)')
        self.pause_button = tool('pause', '暂停接收', self.toggle_pause, True)
        self.pause_button.setCheckable(True)
        self.pause_button.setProperty('pauseAction', True)
        self.more = tool('more', '更多', lambda: None, True)
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(self.more)
        more_menu.addAction('宏编辑器', self.toggle_editor)
        more_menu.addAction('连接设置…', self.connection_settings)
        more_menu.addAction('模拟设备异常', self.simulate_error)
        more_menu.addSeparator()
        more_menu.addAction('关于预览', self.about)
        self.more.setMenu(more_menu)
        header = row(identity, None, self.connect_btn, self.clear_btn, self.save_btn,
                     self.pause_button, self.more, margins=(10, 6, 6, 4), spacing=2)
        header.setFixedHeight(52)
        content.addWidget(header)
        # Log toolbar: search, type filters, follow and pause — small on purpose.
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索日志 (Ctrl+F)')
        self.search.setAccessibleName('搜索日志')
        self.search.addAction(icon('search'), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setMaximumWidth(140)
        self.search.setMinimumWidth(80)
        self.search.textChanged.connect(self.find)
        self.search.returnPressed.connect(self.next_match)
        self.match_count = label('', 'muted')
        self.filter_buttons = {}
        chips = row(spacing=2)
        chips.setObjectName('filterChips')
        for tag in ('全部', 'RX', 'TX', 'INFO', 'WARN', 'ERROR'):
            chip = QToolButton()
            chip.setText(tag)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setProperty('filterChip', True)
            chip.setAccessibleName(f'过滤 {tag}')
            chip.clicked.connect(lambda checked, t=tag: self.filter_clicked(t))
            self.filter_buttons[tag] = chip
            chips.layout().addWidget(chip)
        self.filter_buttons['全部'].setChecked(True)
        self.auto_scroll = tool('down', '自动滚动', lambda: None)
        self.auto_scroll.setCheckable(True)
        self.auto_scroll.setChecked(True)
        self.auto_scroll.setProperty('logAction', True)
        self.auto_scroll.setToolTip('自动滚动：开启时新日志跟随到底部；关闭后可自由查看历史')
        self.pause_tool = tool('pause', '暂停接收', self.toggle_pause)
        self.pause_tool.setCheckable(True)
        self.pause_tool.setProperty('pauseAction', True)
        self.pause_tool.setToolTip('暂停接收：仅冻结日志显示，数据继续记录，恢复后补齐')
        toolbar = row(self.search, self.match_count, chips, None, self.auto_scroll, self.pause_tool,
                      margins=(6, 2, 8, 2), spacing=6)
        toolbar.setObjectName('logToolbar')
        toolbar.setFixedHeight(28)
        content.addWidget(toolbar)
        self.search_row = toolbar
        self.vertical = QSplitter(Qt.Orientation.Vertical)
        self.vertical.setChildrenCollapsible(False)
        self.logs = QStackedWidget()
        self.views = []
        for index in range(len(self.sessions)):
            log = LogView()
            log.main = self
            log.transmit.connect(lambda value, i=index: self.direct_send(i, value))
            self.views.append(log)
            self.logs.addWidget(log)
        self.logs.installEventFilter(self)
        self.pause_badge = QLabel('已暂停')
        self.pause_badge.setObjectName('pauseBadge')
        self.pause_badge.hide()
        self.pause_badge.setParent(self.logs)
        self.vertical.addWidget(self.logs)
        self.editor = QWidget()
        editor_layout = QVBoxLayout(self.editor)
        editor_layout.setContentsMargins(4, 4, 4, 4)
        editor_layout.addWidget(label('宏编辑器 · 每行一条模拟命令', 'heading'))
        self.macro_text = QPlainTextEdit('version\nstatus\nhelp')
        self.macro_text.setAccessibleName('宏命令，每行一条')
        editor_layout.addWidget(self.macro_text)
        self.macro_run = button('运行模拟宏', self.run_macro, True)
        editor_layout.addWidget(self.macro_run)
        self.vertical.addWidget(self.editor)
        self.editor.hide()
        content.addWidget(self.vertical, 1)
        # Command row: input gets the space; history and line endings stay compact.
        self.mode = QComboBox()
        self.mode.addItems(['命令模式', '直接发送'])
        self.mode.setAccessibleName('输入模式')
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.command = QLineEdit()
        self.command.setPlaceholderText('输入命令，按 Enter 发送 · ↑/↓ 浏览历史')
        self.command.setAccessibleName('命令输入')
        self.command.returnPressed.connect(self.send)
        self.command.setMinimumWidth(100)
        self.command.installEventFilter(self)
        self.history_button = tool('history', '历史命令', self.show_history_menu)
        self.history_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.history_button.setFixedSize(26, 24)
        self.history_button.setToolTip('历史命令（↑/↓ 浏览）')
        self.ending = QComboBox()
        self.ending.addItems(['CRLF', 'CR', 'LF'])
        self.ending.setAccessibleName('发送行尾')
        self.encoding = QComboBox()
        self.encoding.addItems(['UTF-8', 'ASCII', 'HEX'])
        self.encoding.setAccessibleName('发送编码')
        self.encoding.setToolTip('HEX 模式下输入按十六进制字节发送，如: 01 A2 0B')
        self.send_button = button('发送 (Enter)', self.send, True)
        self.send_button.setProperty('iconName', 'send')
        send_row = row(self.mode, self.command, self.history_button, self.ending, self.encoding, self.send_button, spacing=6, margins=(4, 4, 2, 2))
        send_row.layout().setStretch(1, 1)
        content.addWidget(send_row)
        self.body_splitter.addWidget(main)

    def _build_inspector(self):
        self.inspector_host = QWidget()
        self.inspector_host.setObjectName('inspectorHost')
        host_layout = QHBoxLayout(self.inspector_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        self.inspector = QTabWidget()
        self.inspector.setMinimumWidth(205)
        self.inspector.setObjectName('inspector')
        self._build_info_tab()
        self._build_macro_tab()
        self._build_log_settings_tab()
        collapse = tool('chevron_right', '折叠右侧面板 (Ctrl+Shift+B)', lambda: self.set_inspector_collapsed(True))
        collapse.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.inspector.setCornerWidget(collapse)
        self.inspector_strip = self._build_strip('chevron_left', '展开右侧面板 (Ctrl+Shift+B)',
                                                 lambda: self.set_inspector_collapsed(False), 'rightStrip')
        self.inspector_strip.hide()
        host_layout.addWidget(self.inspector)
        host_layout.addWidget(self.inspector_strip)
        self.body_splitter.addWidget(self.inspector_host)
        self.body_splitter.setStretchFactor(0, 1)
        self.body_splitter.setSizes([600, 207])

    def _build_info_tab(self):
        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(4)
        self.device_state_label = label('运行中', 'success')
        info_layout.addWidget(row(label('设备状态', 'heading'), None, self.device_state_label))
        self.info_values = {}
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(7)
        for name in ('串口类型', '数据格式', '流控', '连接时长', '接收字节', '发送字节', '设备运行状态'):
            field = label('—', 'muted')
            self.info_values[name] = field
            form.addRow(label(name), field)
        info_layout.addLayout(form)
        info_layout.addStretch()
        self.inspector.addTab(info, '设备信息')

    def _build_macro_tab(self):
        macro_tab = QWidget()
        ml = QVBoxLayout(macro_tab)
        ml.setContentsMargins(8, 8, 8, 8)
        ml.setSpacing(4)
        header = row(label('命令宏', 'heading'), None,
                     tool('edit', '批量编辑器', self.toggle_editor),
                     tool('plus', '新增宏', self.add_macro), spacing=2)
        for b in header.findChildren(QToolButton):
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        ml.addWidget(header)
        self.macro_list = QListWidget()
        self.macro_list.setAccessibleName('命令宏列表')
        self.macro_list.setObjectName('macroList')
        ml.addWidget(self.macro_list, 1)
        self.rebuild_macro_list()
        actions = row(button('运行', self.run_selected_macro),
                      button('编辑', lambda: self.edit_macro_dialog()),
                      button('删除', self.delete_macro),
                      None,
                      button('上移', lambda: self.move_macro(-1)),
                      button('下移', lambda: self.move_macro(1)), spacing=4)
        ml.addWidget(actions)
        self.expand = button('展开宏编辑器', self.toggle_editor)
        ml.addWidget(self.expand)
        self.inspector.addTab(macro_tab, '命令宏')

    def _build_log_settings_tab(self):
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(10, 8, 10, 8)
        settings_layout.setSpacing(4)
        settings_layout.addWidget(label('日志显示设置', 'heading'))
        self.timestamps = QCheckBox('显示时间戳')
        self.timestamps.setChecked(True)
        self.timestamps.toggled.connect(self.rerender)
        self.wrap = QCheckBox('自动换行')
        self.wrap.toggled.connect(lambda enabled: [v.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap) for v in self.views])
        self.show_rx = QCheckBox('显示 RX')
        self.show_rx.setChecked(True)
        self.show_rx.toggled.connect(self.rerender)
        self.show_tx = QCheckBox('显示 TX')
        self.show_tx.setChecked(True)
        self.show_tx.toggled.connect(self.rerender)
        for checkbox in (self.timestamps, self.wrap, self.show_rx, self.show_tx):
            settings_layout.addWidget(checkbox)
        self.display_mode = QComboBox()
        self.display_mode.addItems(['ASCII', 'HEX'])
        self.display_mode.setAccessibleName('日志显示格式')
        self.display_mode.currentIndexChanged.connect(self.rerender)
        self.log_level = QComboBox()
        self.log_level.addItems(['全部', '信息', '警告', '错误'])
        self.log_level.setAccessibleName('日志等级')
        self.log_level.currentIndexChanged.connect(self.rerender)
        self.rx_encoding = QComboBox()
        self.rx_encoding.addItems(['UTF-8', 'GBK'])
        self.rx_encoding.setAccessibleName('接收编码')
        self.save_policy = QComboBox()
        self.save_policy.addItems(['手动保存', '会话结束自动保存'])
        self.save_policy.setAccessibleName('日志保存策略')
        for name, combo in (('显示格式', self.display_mode), ('日志等级', self.log_level),
                            ('编码', self.rx_encoding), ('保存策略', self.save_policy)):
            settings_layout.addWidget(row(label(name, 'muted'), None, combo, spacing=4))
        settings_layout.addSpacing(6)
        settings_layout.addWidget(label('编码与保存策略将在接入真实串口后生效。', 'muted'))
        settings_layout.addStretch()
        self.inspector.addTab(settings, '日志设置')

    def _build_strip(self, icon_name, tooltip, callback, object_name):
        strip = QWidget()
        strip.setObjectName(object_name)
        layout = QVBoxLayout(strip)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(4)
        expand = QToolButton()
        expand.setProperty('iconName', icon_name)
        expand.setIcon(icon(icon_name))
        expand.setIconSize(QSize(16, 16))
        expand.setFixedSize(18, 20)
        expand.setCursor(Qt.CursorShape.PointingHandCursor)
        expand.setAccessibleName(tooltip)
        expand.setToolTip(tooltip)
        expand.clicked.connect(callback)
        layout.addWidget(expand)
        layout.addStretch()
        return strip

    def _build_status_bar(self, outer):
        self.state = label('就绪 · 模拟会话', 'muted')
        self.stats = label('', 'muted')
        self.status_encoding = label('', 'muted')
        self.zoom_combo = QComboBox()
        self.zoom_combo.setAccessibleName('界面缩放比例')
        self.zoom_combo.setToolTip('整体界面缩放；日志区 Ctrl+滚轮只调整日志字号')
        self.zoom_combo.addItems([f'{n}%' for n in range(75, 201, 25)])
        self.zoom_combo.setCurrentText('100%')
        self.zoom_combo.currentTextChanged.connect(lambda value: self.set_zoom(int(value.rstrip('%'))) if hasattr(self, '_scale_metrics') else None)
        self.log_zoom_combo = QComboBox()
        self.log_zoom_combo.setAccessibleName('日志字号比例')
        self.log_zoom_combo.setToolTip('日志独立缩放：日志区 Ctrl+滚轮；Ctrl+0 恢复日志 100%')
        self.log_zoom_combo.addItems([f'{n}%' for n in (50, 75, 100, 125, 150, 175, 200, 250, 300)])
        self.log_zoom_combo.setCurrentText('100%')
        self.log_zoom_combo.currentTextChanged.connect(lambda text: self.set_log_zoom(int(text.rstrip('%'))))
        status = row(self.state, self.stats, None, self.status_encoding, label('界面', 'muted'),
                     self.zoom_combo, label('日志', 'muted'), self.log_zoom_combo, margins=(12, 2, 12, 2), spacing=14)
        status.setObjectName('status')
        status.setFixedHeight(23)
        outer.addWidget(status)

    def _capture_scale_metrics(self):
        # Always scale from the 100% baseline, avoiding rounding drift.
        self._scale_metrics = []
        for widget in self.findChildren(QWidget):
            if widget.isWindow() or isinstance(widget, _ResizeHandle):
                continue
            self._scale_metrics.append((widget, widget.minimumSize(), widget.maximumSize()))
        self._layout_metrics = []
        for layout in self.findChildren(QLayout):
            m = layout.contentsMargins()
            extra = (layout.horizontalSpacing(), layout.verticalSpacing()) if isinstance(layout, QFormLayout) else None
            self._layout_metrics.append((layout, (m.left(), m.top(), m.right(), m.bottom()), layout.spacing(), extra))
        self._icon_metrics = [(w, w.iconSize()) for w in self.findChildren(QToolButton)+self.findChildren(QPushButton)]
        self._zoom_ready = True

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and watched is self.logs:
            self._position_badge()
        if (event.type() == QEvent.Type.KeyPress and watched is self.command
                and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)):
            if event.key() == Qt.Key.Key_Up:
                self.browse_history(-1)
                return True
            if event.key() == Qt.Key.Key_Down:
                self.browse_history(1)
                return True
        if (event.type() == QEvent.Type.Wheel and isinstance(watched, QWidget)
                and watched.window() is self
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            log = next((v for v in self.views if watched is v or v.isAncestorOf(watched)), None)
            if log is not None:
                delta = event.angleDelta().y() or event.pixelDelta().y()*3
                self._wheel_zoom_delta += delta
                steps = int(self._wheel_zoom_delta / 120)
                if steps:
                    self._wheel_zoom_delta -= steps*120
                    self.set_log_zoom(round(self.log_zoom*100) + steps*10)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def set_log_zoom(self, percent):
        percent = max(50, min(300, int(percent)))
        if percent == round(self.log_zoom*100):
            return
        self.log_zoom = percent/100
        # A wheel step must not repolish the entire application. Qt's font
        # setter updates only each log document and its attached number gutter.
        for view in self.views:
            top = view.verticalScrollBar().value()
            view.set_log_scale(self.ui_scale*self.log_zoom)
            view.verticalScrollBar().setValue(top)
            view.numbers.update()
        self.log_zoom_combo.blockSignals(True)
        text = f'{percent}%'
        if self.log_zoom_combo.findText(text) < 0:
            self.log_zoom_combo.addItem(text)
        self.log_zoom_combo.setCurrentText(text)
        self.log_zoom_combo.blockSignals(False)

    def set_zoom(self, percent):
        percent = max(75, min(200, int(percent)))
        scale = percent / 100
        if scale == self.ui_scale or not hasattr(self, '_scale_metrics'):
            return
        previous = self.ui_scale
        positions = [((v.textCursor().anchor(), v.textCursor().position()), v.verticalScrollBar().value(),
                      v.horizontalScrollBar().value()) for v in self.views]
        self.ui_scale = scale
        px = lambda value: max(0, round(value*scale))
        self.setUpdatesEnabled(False)
        try:
            for widget, minimum, maximum in self._scale_metrics:
                widget.setMinimumSize(px(minimum.width()), px(minimum.height()))
                widget.setMaximumSize(*(px(n) if n < 16777215 else n for n in (maximum.width(), maximum.height())))
            for layout, margins, spacing, extra in self._layout_metrics:
                layout.setContentsMargins(*(px(n) for n in margins))
                if spacing >= 0:
                    layout.setSpacing(px(spacing))
                if extra:
                    layout.setHorizontalSpacing(px(extra[0]))
                    layout.setVerticalSpacing(px(extra[1]))
            for widget, size in self._icon_metrics:
                widget.setIconSize(QSize(px(size.width()), px(size.height())))
            # Scale the window minimum with the UI so high zoom never starves
            # the log area; clamp to the screen for small displays.
            available = QApplication.primaryScreen().availableGeometry()
            self.setMinimumSize(min(available.width(), px(900)), min(available.height(), px(530)))
            self.devices.setIconSize(QSize(px(8), px(8)))
            self.devices.setSpacing(px(2))
            for i in range(self.devices.count()):
                self.devices.item(i).setSizeHint(QSize(px(108), px(42)))
            for view in self.views:
                view.set_log_scale(scale*self.log_zoom)
            self.theme(self.dark)
            self.splitter.setSizes([px(134), max(1, self.width()-px(134))])
            self.body_splitter.setSizes([max(1, self.width()-px(341)), px(207)])
            self._apply_panel_widths()
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentText(f'{percent}%')
            self.zoom_combo.blockSignals(False)
            if not self.isMaximized():
                available = self.screen().availableGeometry()
                self.resize(min(available.width(), round(self.width()*scale/previous)),
                            min(available.height(), round(self.height()*scale/previous)))
            for view, (cursor, vertical, horizontal) in zip(self.views, positions):
                restored = QTextCursor(view.document())
                restored.setPosition(min(cursor[0], view.document().characterCount()-1))
                restored.setPosition(min(cursor[1], view.document().characterCount()-1), QTextCursor.MoveMode.KeepAnchor)
                view.setTextCursor(restored)
                view.verticalScrollBar().setValue(vertical)
                view.horizontalScrollBar().setValue(horizontal)
        finally:
            self.setUpdatesEnabled(True)

    # ---- Collapsible side panels (CRT / MobaXterm style thin strips) ----

    def _strip_width(self):
        return max(12, round(22*self.ui_scale))

    def _apply_panel_widths(self):
        if self.sidebar_collapsed:
            self.sidebar_host.setFixedWidth(self._strip_width())
            self.splitter.setSizes([self._strip_width(), max(1, self.splitter.width()-self._strip_width())])
        if self.inspector_collapsed:
            self.inspector_host.setFixedWidth(self._strip_width())
            self.body_splitter.setSizes([max(1, self.body_splitter.width()-self._strip_width()), self._strip_width()])

    def set_sidebar_collapsed(self, collapsed):
        collapsed = bool(collapsed)
        if collapsed == self.sidebar_collapsed:
            return
        self.sidebar_collapsed = collapsed
        if collapsed:
            self._sidebar_width = self.sidebar_host.width()
            self.sidebar.hide()
            self.sidebar_strip.show()
            self.sidebar_host.setFixedWidth(self._strip_width())
            # QSplitter retains its allocated pane size after the child is
            # constrained. Redistribute it explicitly to avoid an empty gutter.
            self.splitter.setSizes([self._strip_width(), max(1, self.splitter.width()-self._strip_width())])
        else:
            self.sidebar_strip.hide()
            self.sidebar.show()
            self.sidebar_host.setMinimumSize(0, 0)
            self.sidebar_host.setMaximumSize(16777215, 16777215)
            preferred = getattr(self, '_sidebar_width', 0) or round(134*self.ui_scale)
            self.splitter.setSizes([preferred, max(1, self.splitter.width()-preferred)])

    def set_inspector_collapsed(self, collapsed):
        collapsed = bool(collapsed)
        if collapsed == self.inspector_collapsed:
            return
        self.inspector_collapsed = collapsed
        if collapsed:
            self._inspector_width = self.inspector_host.width()
            self.inspector.hide()
            self.inspector_strip.show()
            self.inspector_host.setFixedWidth(self._strip_width())
            self.body_splitter.setSizes([max(1, self.body_splitter.width()-self._strip_width()), self._strip_width()])
        else:
            self.inspector_strip.hide()
            self.inspector.show()
            self.inspector_host.setMinimumSize(0, 0)
            self.inspector_host.setMaximumSize(16777215, 16777215)
            preferred = getattr(self, '_inspector_width', 0) or round(207*self.ui_scale)
            self.body_splitter.setSizes([max(1, self.body_splitter.width()-preferred), preferred])

    def about(self):
        QMessageBox.information(self, 'Qt 视觉预览', '真实 Qt Widgets 界面，所有会话与发送均为模拟。\n未访问真实串口，也不修改正式配置。')

    def toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, event):
        super().changeEvent(event)
        if hasattr(self, 'caption_buttons') and self.caption_buttons:
            b = self.caption_buttons[1]
            name = 'restore' if self.isMaximized() else 'maximize'
            b.setProperty('iconName', name)
            b.setIcon(icon(name))
            b.setAccessibleName('还原' if self.isMaximized() else '最大化')
            b.setToolTip(b.accessibleName())
        if self.centralWidget():
            set_fluent_property(self.centralWidget(), 'windowActive', self.isActiveWindow())
            set_fluent_property(self.centralWidget(), 'maximized', self.isMaximized() or self.isFullScreen())

    def clear_log(self):
        self.sessions[self.active]['history'].clear()
        self.views[self.active].clear()
        self.find()

    def save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存当前会话日志', 'serial-preview.log', '日志 (*.log);;文本 (*.txt)')
        if path:
            try:
                Path(path).write_text(self.views[self.active].toPlainText(), encoding='utf-8')
                self.state.setText('已保存模拟日志')
            except OSError as exc:
                QMessageBox.warning(self, '保存失败', str(exc))

    def save_selection(self, view):
        text = self._lines_text(view)
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(self, '保存选中内容', 'serial-selection.log', '日志 (*.log);;文本 (*.txt)')
        if path:
            try:
                Path(path).write_text(text, encoding='utf-8')
                self.state.setText('已保存选中内容')
            except OSError as exc:
                QMessageBox.warning(self, '保存失败', str(exc))

    def connection_settings(self):
        session = self.sessions[self.active]
        dialog = QDialog(self)
        dialog.setWindowTitle(f'连接设置 · {session["port"]}')
        form = QFormLayout(dialog)
        form.setContentsMargins(12, 12, 12, 12)
        baud = QComboBox()
        baud.addItems(['9600', '57600', '115200', '460800', '921600'])
        baud.setCurrentText(session['baud'])
        baud.setEnabled(session['state'] != 'connected')
        fmt = QComboBox()
        fmt.addItems(['8N1', '8E1', '8O1', '7E1'])
        fmt.setCurrentText(session['fmt'])
        fmt.setEnabled(session['state'] != 'connected')
        flow = QComboBox()
        flow.addItems(['无', 'RTS/CTS'])
        flow.setCurrentText(session.get('flow', '无'))
        flow.setEnabled(session['state'] != 'connected')
        form.addRow('波特率', baud)
        form.addRow('数据格式', fmt)
        form.addRow('流控', flow)
        if session['state'] == 'connected':
            form.addRow(label('已连接：参数将在下次连接时生效。', 'muted'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            session['baud'] = baud.currentText()
            session['fmt'] = fmt.currentText()
            session['flow'] = flow.currentText()
            self.refresh_devices()
            self.update_state()

    def detect(self):
        self.state.setText('模拟检测完成 · COM5 / COM8 / COM3')

    def new_session(self):
        port, accepted = QInputDialog.getText(self, '新建模拟会话', '模拟端口名称：', text=f'COM{len(self.sessions)+6}')
        if accepted and port.strip():
            self.create_session(port.strip())

    def create_session(self, port):
        index = len(self.sessions)
        self.sessions.append(dict(port=port, name='新建会话', state='disconnected', connected_at=None, draft='', mode=0,
                                  baud='115200', fmt='8N1', flow='无', query='', sent=0, received=0, rx_bytes=0, history=[], sent_log=[]))
        log = LogView()
        log.main = self
        log.transmit.connect(lambda value, i=index: self.direct_send(i, value))
        self.views.append(log)
        self.logs.addWidget(log)
        item = QListWidgetItem()
        item.setSizeHint(QSize(round(108*self.ui_scale), round(42*self.ui_scale)))
        self.devices.addItem(item)
        self.refresh_devices()
        self.devices.setCurrentRow(index)
        log.ensurePolished()
        log.set_log_scale(self.ui_scale*self.log_zoom)
        self.append(index, 'SYS', '模拟会话已创建，尚未连接。', 'text_secondary')
        return index

    # ---- Saved macros (命令宏 tab) ----

    def rebuild_macro_list(self):
        self.macro_list.clear()
        color = self.c['text_secondary'] if hasattr(self, 'c') else None
        for index, (command, description) in enumerate(self.macros):
            item = QListWidgetItem()
            item.setSizeHint(QSize(120, max(20, round(26*self.ui_scale))))
            self.macro_list.addItem(item)
            row_widget = MacroRow(index, command, description, self)
            if color:
                row_widget.run_button.setIcon(icon('play', color))
            self.macro_list.setItemWidget(item, row_widget)
        if self.macro_list.count():
            self.macro_list.setCurrentRow(0)

    def add_macro_command(self, command, description):
        self.macros.append((command, description))
        self.rebuild_macro_list()
        self.macro_list.setCurrentRow(len(self.macros)-1)

    def add_macro(self):
        self.edit_macro_dialog(-1)

    def edit_macro_dialog(self, index=None):
        if index is None:
            index = self.macro_list.currentRow()
            if index < 0:
                return
        existing = self.macros[index] if 0 <= index < len(self.macros) else ('', '')
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑宏' if 0 <= index < len(self.macros) else '新增宏')
        form = QFormLayout(dialog)
        form.setContentsMargins(12, 12, 12, 12)
        command = QLineEdit(existing[0])
        description = QLineEdit(existing[1])
        form.addRow('命令', command)
        form.addRow('说明', description)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() and command.text().strip():
            entry = (command.text().strip(), description.text().strip() or '—')
            if 0 <= index < len(self.macros):
                self.macros[index] = entry
            else:
                self.macros.append(entry)
            self.rebuild_macro_list()
            self.macro_list.setCurrentRow(min(index if 0 <= index < len(self.macros) else len(self.macros)-1, len(self.macros)-1))

    def delete_macro(self):
        index = self.macro_list.currentRow()
        if 0 <= index < len(self.macros):
            del self.macros[index]
            self.rebuild_macro_list()
            self.macro_list.setCurrentRow(min(index, len(self.macros)-1))

    def move_macro(self, delta):
        index = self.macro_list.currentRow()
        target = index + delta
        if index < 0 or not (0 <= target < len(self.macros)):
            return
        self.macros[index], self.macros[target] = self.macros[target], self.macros[index]
        self.rebuild_macro_list()
        self.macro_list.setCurrentRow(target)

    def run_macro_command(self, index):
        if 0 <= index < len(self.macros):
            command = self.macros[index][0]
            self.dispatch_command(command + '\r', display=command)

    def run_selected_macro(self):
        self.run_macro_command(self.macro_list.currentRow())

    def rerender(self):
        for i, view in enumerate(self.views):
            view.clear()
            for entry in self.sessions[i]['history']:
                if self.entry_visible(entry[1]):
                    self.render(i, *entry)
        if self.active >= 0:
            self.find()

    def entry_visible(self, tag):
        if self.tag_filters and tag not in self.tag_filters:
            return False
        if tag in ('RX', 'TX'):
            if tag == 'RX' and not self.show_rx.isChecked():
                return False
            if tag == 'TX' and not self.show_tx.isChecked():
                return False
            return True
        return TAG_SEVERITY.get(tag, 1) >= self.log_level.currentIndex()

    def filter_clicked(self, tag):
        if tag == '全部':
            self.tag_filters.clear()
        else:
            if tag in self.tag_filters:
                self.tag_filters.discard(tag)
            else:
                self.tag_filters.add(tag)
        for name, chip in self.filter_buttons.items():
            chip.blockSignals(True)
            chip.setChecked(name == '全部' if not self.tag_filters else name in self.tag_filters)
            chip.blockSignals(False)
        self.rerender()

    def theme(self, dark):
        self.dark = dark
        self._icon_cache = {}
        theme = 'dark' if dark else 'light'
        self.c = {name: value[theme] for name, value in self.tokens.items()}
        c = self.c
        # QSS complex controls need an explicit arrow once native borders are
        # replaced. Cache a theme-colored version of the existing icon family.
        arrow_path = Path(self._theme_assets.name) / f'chevron-{theme}.png'
        icon('down', c['text_secondary']).pixmap(32, 32).save(str(arrow_path))
        palette = QPalette()
        for role, alias in [('Window', 'window_background'), ('WindowText', 'text_primary'),
                            ('Base', 'canvas_background'), ('AlternateBase', 'surface_secondary'),
                            ('Text', 'text_primary'), ('Button', 'surface_background'),
                            ('ButtonText', 'text_primary'), ('Highlight', 'brand_background'),
                            ('HighlightedText', 'text_on_brand'), ('PlaceholderText', 'text_secondary'),
                            ('ToolTipBase', 'tooltip_background'), ('ToolTipText', 'tooltip_foreground')]:
            palette.setColor(getattr(QPalette.ColorRole, role), QColor(c[alias]))
        for role in [QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText]:
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c['text_disabled']))
        QApplication.instance().setPalette(palette)
        stylesheet = f"""
            QWidget {{ color: {c['text_primary']}; font-family: 'Microsoft YaHei UI'; font-size: 7pt; }}
            QMainWindow, #sidebar, #sidebarHost, #inspectorHost, #tabs, #status, #top {{ background: {c['surface_secondary']}; }}
            #windowFrame {{ background: {c['surface_secondary']}; border: 1px solid {c['border_primary']}; }}
            #windowFrame[windowActive="true"] {{ border-color: {c['focus_border']}; }}
            #windowFrame[maximized="true"] {{ border: none; }}
            #main, #inspector::pane {{ background: {c['canvas_background']}; }}
            #top, #tabs {{ border-bottom: 1px solid {c['border_subtle']}; }}
            #status {{ border-top: 1px solid {c['border_subtle']}; }}
            #logToolbar {{ background: {c['canvas_background']}; border-bottom: 1px solid {c['border_subtle']}; }}
            #leftStrip {{ background: {c['surface_secondary']}; border-right: 1px solid {c['border_subtle']}; }}
            #rightStrip {{ background: {c['surface_secondary']}; border-left: 1px solid {c['border_subtle']}; }}
            QLabel {{ background: transparent; }}
            QLabel[role="muted"] {{ color: {c['text_secondary']}; font-size: 6.75pt; }}
            QLabel[role="brand"], QLabel[role="heading"] {{ font-weight: 600; }}
            QLabel[role="title"] {{ font-size: 12pt; font-weight: 700; }}
            QLabel[role="success"] {{ color: {c['success_foreground']}; font-size: 6.75pt; font-weight: 600; }}
            QLabel[role="info"] {{ color: {c['brand_foreground']}; font-size: 6.75pt; font-weight: 600; }}
            QLabel[role="warning"] {{ color: {c['warning_foreground']}; font-size: 6.75pt; font-weight: 600; }}
            QLabel[role="danger"] {{ color: {c['danger_foreground']}; font-size: 6.75pt; font-weight: 600; }}
            QLabel[role="command"] {{ font-family: Consolas; }}
            #pauseBadge {{ background: {c['warning_background']}; color: {c['warning_foreground']}; border: 1px solid {c['warning_border']}; border-radius: 4px; padding: 2px 8px; font-size: 6.75pt; font-weight: 600; }}
            QPushButton, QComboBox {{ background: {c['surface_background']}; border: 1px solid {c['border_primary']}; border-radius: 4px; padding: 3px 6px; min-height: 16px; }}
            QComboBox {{ padding-right: 18px; }}
            QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 16px; border: none; }}
            QComboBox::down-arrow {{ image: url("{arrow_path.as_posix()}"); width: 12px; height: 12px; }}
            QPushButton:hover, QComboBox:hover, QToolButton:hover {{ background: {c['surface_background_hover']}; border-color: {c['border_hover']}; }}
            QPushButton:pressed, QToolButton:pressed {{ background: {c['surface_background_pressed']}; }}
            QPushButton[fluentAppearance="primary"] {{ background: {c['brand_background']}; color: {c['text_on_brand']}; border-color: {c['brand_background']}; }}
            QPushButton[fluentAppearance="primary"]:hover {{ background: {c['brand_background_hover']}; }}
            QPushButton[fluentAppearance="primary"]:pressed {{ background: {c['brand_background_pressed']}; }}
            QPushButton:disabled, QPushButton[fluentAppearance="primary"]:disabled, QComboBox:disabled, QToolButton:disabled {{ color: {c['text_disabled']}; background: {c['surface_disabled']}; border-color: {c['border_disabled']}; }}
            QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 3px 5px; font-size: 6.75pt; }}
            #leftStrip QToolButton, #rightStrip QToolButton {{ padding: 0; }}
            #newSessionTab {{ padding: 0; border-radius: 12px; }}
            QToolButton[nativeCaptionHover="true"] {{ background: {c['surface_background_hover']}; }}
            QToolButton[iconName="close"]:hover {{ background: {c['danger_background']}; }}
            QToolButton[filterChip="true"] {{ padding: 2px 6px; font-size: 6.5pt; }}
            QToolButton[filterChip="true"]:checked {{ background: {c['brand_background_subtle']}; color: {c['brand_foreground']}; border-color: {c['brand_border_subtle']}; }}
            QToolButton[logAction="true"]:checked {{ background: {c['brand_background_subtle']}; color: {c['brand_foreground']}; border-color: {c['brand_border_subtle']}; }}
            QToolButton[pauseAction="true"]:checked {{ background: {c['warning_background']}; color: {c['warning_foreground']}; border-color: {c['warning_border']}; }}
            QLineEdit, QPlainTextEdit {{ background: {c['canvas_background']}; border: 1px solid {c['border_primary']}; border-radius: 4px; padding: 4px; selection-background-color: {c['brand_background']}; selection-color: {c['text_on_brand']}; }}
            QPlainTextEdit {{ font-family: Consolas; font-size: 8pt; padding: 4px 2px; }}
            QLineEdit:disabled {{ color: {c['text_disabled']}; background: {c['surface_disabled']}; }}
            QPushButton:focus, QToolButton:focus, QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus {{ border: 1px solid {c['focus_border']}; }}
            QCheckBox {{ spacing: 5px; font-size: 6.75pt; }}
            QCheckBox:focus {{ outline: 1px solid {c['focus_border']}; }}
            QListWidget {{ background: transparent; border: 1px solid transparent; }}
            QListWidget::item {{ padding: 4px 4px; border: 1px solid transparent; border-left: 3px solid transparent; border-radius: 3px; }}
            QListWidget::item:hover {{ background: {c['subtle_hover']}; }}
            QListWidget::item:selected {{ background: {c['brand_background_subtle']}; color: {c['text_primary']}; border-left: 3px solid {c['brand_background']}; }}
            #macroList::item {{ padding: 1px 2px; border-bottom: 1px solid {c['border_tertiary']}; }}
            QSplitter::handle {{ background: {c['border_subtle']}; }}
            QMenuBar {{ background: transparent; font-size: 6.75pt; }}
            QMenuBar::item {{ padding: 4px 6px; }}
            QMenuBar::item:selected, QMenu::item:selected {{ background: {c['brand_background_subtle']}; color: {c['text_primary']}; }}
            QTabBar::tab {{ background: transparent; padding: 7px 9px; border: 1px solid transparent; font-size: 6.75pt; }}
            QTabBar::tab:selected {{ background: {c['canvas_background']}; border-top: 2px solid {c['brand_background']}; }}
            QTabBar::tab:hover {{ background: {c['subtle_hover']}; }}
            #inspector QTabBar::tab:selected {{ border-top: none; border-bottom: 2px solid {c['brand_background']}; }}
            QTabWidget::pane {{ border: 1px solid {c['border_subtle']}; }}
            QScrollBar:vertical {{ background: {c['surface_secondary']}; width: 10px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {c['border_primary']}; min-height: 24px; border-radius: 4px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            #status QComboBox {{ background: transparent; border: 1px solid transparent; padding: 1px 2px; min-height: 14px; font-size: 6.5pt; color: {c['text_secondary']}; }}
            #status QComboBox:hover {{ background: {c['subtle_hover']}; border-color: {c['border_subtle']}; }}
            #status QComboBox::drop-down {{ border: none; }}
        """
        stylesheet = re.sub(r"(\d+(?:\.\d+)?)(px|pt)", lambda m: f"{float(m[1])*self.ui_scale:g}{m[2]}", stylesheet)
        QApplication.instance().setStyleSheet(stylesheet)
        font = QFont('Microsoft YaHei UI')
        font.setPointSizeF(7*self.ui_scale)
        self.devices.setFont(font)
        for log in self.views:
            font = QFont('Consolas')
            font.setPointSizeF(8*self.ui_scale*self.log_zoom)
            log.setFont(font)
        for w in self.findChildren(QToolButton) + self.findChildren(QPushButton):
            name = w.property('iconName')
            if name:
                w.setIcon(icon(name, c['text_on_brand'] if w.property('fluentAppearance')=='primary' else c['text_secondary']))
        if hasattr(self, 'new_button') and self.new_button.defaultAction() is not None:
            self.new_button.defaultAction().setIcon(icon('plus', c['text_secondary']))
        for w in self.findChildren(QLabel):
            name = w.property('iconName')
            if name:
                w.setPixmap(icon(name, c['text_primary']).pixmap(round((20 if name=='terminal' else 30)*self.ui_scale), round((20 if name=='terminal' else 30)*self.ui_scale)))
        self.search.actions()[0].setIcon(icon('search', c['text_secondary']))
        self.rebuild_macro_list()
        self.refresh_devices()
        self.rerender()
        if self.active >= 0:
            self.update_state()

    def refresh_devices(self):
        for i, session in enumerate(self.sessions):
            state = session['state']
            color = SESSION_STATE_COLOR[state]
            self.devices.item(i).setIcon(icon('status', self.c[color]) if hasattr(self, 'c') else icon('status'))
            self.devices.item(i).setText(f"{session['port']}   {session['name']}\n{session['baud']} · {SESSION_STATE_TEXT[state]}")

    def switch(self, index):
        if index < 0:
            return
        if self.active >= 0:
            self.sessions[self.active].update(draft=self.command.text(), mode=self.mode.currentIndex(), query=self.search.text())
        self.active = index
        self.history_index = None
        session = self.sessions[index]
        self.logs.setCurrentIndex(index)
        self.title.setText(session['port'])
        tab_index = next((i for i in range(self.tabs.count()) if self.tabs.tabData(i)==index), -1)
        if tab_index < 0:
            self.tabs.blockSignals(True)
            tab_index = self.tabs.addTab(f"{session['port']}    {session['name']}")
            self.tabs.setTabData(tab_index, index)
            self.tabs.blockSignals(False)
        self.tabs.setCurrentIndex(tab_index)
        self.command.setText(session['draft'])
        self.mode.setCurrentIndex(session['mode'])
        self.search.setText(session['query'])
        self.find()
        self.update_state()

    def update_state(self):
        if self.active < 0:
            return
        session = self.sessions[self.active]
        state = session['state']
        direct = self.mode.currentIndex() == 1
        self.connection.setText(SESSION_STATE_TEXT[state])
        set_role(self.connection, SESSION_STATE_ROLE[state])
        dot = max(6, round(8*self.ui_scale))
        self.status_dot.setPixmap(self.themed_icon('status', SESSION_STATE_COLOR[state]).pixmap(dot, dot))
        self.status_dot.setFixedSize(dot, dot)
        self.params.setText(f"{session['baud']} · {session['fmt']}")
        self.subtitle.setText(f"{session['name']} · USB Serial Port")
        self.connect_btn.setText(CONNECT_LABEL[state])
        self.connect_btn.setAccessibleName(CONNECT_LABEL[state])
        self.connect_btn.setToolTip(CONNECT_LABEL[state])
        self.connect_btn.setProperty('iconName', CONNECT_ICON[state])
        self.connect_btn.setIcon(self.themed_icon(CONNECT_ICON[state], 'text_secondary'))
        self.connect_btn.setEnabled(state != 'connecting')
        self.command.setEnabled(not direct)
        self.command.setPlaceholderText('点击日志区，按键将直接模拟发送' if direct else '输入命令，按 Enter 发送 · ↑/↓ 浏览历史')
        self.send_button.setEnabled(not direct)
        self.ending.setEnabled(not direct)
        self.encoding.setEnabled(not direct)
        self.macro_run.setEnabled(state == 'connected')
        self.views[self.active].direct = state == 'connected' and direct
        self.stats.setText(f"RX {session['received']:,} 行 · TX {session['sent']:,} 字节")
        set_role(self.state, 'warning' if self.paused else 'muted')
        self.state.setText('已暂停 · 恢复接收后继续显示' if self.paused else '就绪 · 模拟会话')
        self.info_values['串口类型'].setText('USB Serial Port')
        self.info_values['数据格式'].setText(session['fmt'])
        self.info_values['流控'].setText(session.get('flow', '无'))
        self.info_values['连接时长'].setText(self._connected_for(session))
        self.info_values['接收字节'].setText(fmt_bytes(session.get('rx_bytes', 0)))
        self.info_values['发送字节'].setText(fmt_bytes(session['sent']))
        self.info_values['设备运行状态'].setText({'connected': '运行中 · 模拟', 'connecting': '连接中',
                                                   'disconnected': '未连接', 'error': '异常 · 无响应'}[state])
        set_role(self.device_state_label, SESSION_STATE_ROLE[state])
        self.device_state_label.setText(SESSION_STATE_TEXT[state])
        self.status_encoding.setText(f"{self.encoding.currentText()} · {self.ending.currentText()}")

    def _connected_for(self, session):
        if session['state'] != 'connected' or not session.get('connected_at'):
            return '—'
        seconds = int((datetime.now() - session['connected_at']).total_seconds())
        return f'{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}'

    def themed_icon(self, name, color_key):
        """Cached icon lookup; hot paths must not re-render SVGs per log line."""
        key = (name, color_key)
        cached = self._icon_cache.get(key)
        if cached is None:
            cached = icon(name, self.c[color_key])
            self._icon_cache[key] = cached
        return cached

    def mode_changed(self):
        self.update_state()
        if self.active >= 0 and self.mode.currentIndex() == 1:
            self.views[self.active].setFocus()

    def toggle_connection(self):
        session = self.sessions[self.active]
        if session['state'] in ('disconnected', 'error'):
            session['state'] = 'connecting'
            self.refresh_devices()
            self.update_state()
            index = self.active
            QTimer.singleShot(self.connect_delay, lambda: self._finish_connect(index))
        elif session['state'] == 'connected':
            session['state'] = 'disconnected'
            session['connected_at'] = None
            self.append(self.active, 'SYS', '模拟连接已断开', 'text_secondary')
            self.refresh_devices()
            self.update_state()

    def _finish_connect(self, index):
        if self.sessions[index]['state'] != 'connecting':
            return
        self.sessions[index]['state'] = 'connected'
        self.sessions[index]['connected_at'] = datetime.now()
        self.append(index, 'SYS', '模拟连接已建立', 'text_secondary')
        self.refresh_devices()
        self.update_state()

    def simulate_error(self):
        session = self.sessions[self.active]
        if session['state'] == 'connected':
            session['state'] = 'error'
            session['connected_at'] = None
            self.append(self.active, 'ERROR', '串口通信错误：设备无响应（模拟异常，可用“重连”恢复）', 'text_primary')
            self.refresh_devices()
            self.update_state()

    def render(self, index, stamp, tag, text, role):
        view = self.views[index]
        bar = view.verticalScrollBar()
        follow = self.auto_scroll.isChecked() and bar.value() >= bar.maximum() - 3
        position = bar.value()
        cursor = QTextCursor(view.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not view.document().isEmpty():
            cursor.insertBlock()
        block_format = QTextBlockFormat()
        block_format.setLineHeight(14*self.ui_scale, QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        cursor.setBlockFormat(block_format)
        # Fixed columns: timestamp (weak gray) | tag (fixed width, colored) | body (primary).
        stamp_format = QTextCharFormat()
        stamp_format.setForeground(QColor(self.c['text_tertiary']))
        tag_format = QTextCharFormat()
        tag_format.setForeground(QColor(self.c[TAG_COLORS.get(tag, 'text_secondary')]))
        body_format = QTextCharFormat()
        body_format.setForeground(QColor(self.c[role]))
        if self.timestamps.isChecked():
            cursor.insertText(f'{stamp}  ', stamp_format)
        cursor.insertText(f'{tag:<5}  ', tag_format)
        if self.display_mode.currentIndex() == 1:
            text = ' '.join(f'{b:02X}' for b in text.encode('utf-8'))
        cursor.insertText(text, body_format)
        if follow:
            bar.setValue(bar.maximum())
        else:
            bar.setValue(position)

    def append(self, index, tag, text, role='text_primary', stamp=None):
        entry = (stamp or datetime.now().strftime('%H:%M:%S.%f')[:-3], tag, text, role)
        session = self.sessions[index]
        session['history'].append(entry)
        session['history'] = session['history'][-2000:]
        session['received'] += text.count('\n') + 1
        session['rx_bytes'] = session.get('rx_bytes', 0) + len(text.encode('utf-8'))
        if self.paused:
            # Paused freezes display only; entries keep accumulating in history.
            self.pending += 1
            self.pause_badge.setText(f'已暂停 · 新增 {self.pending} 条')
            self._position_badge()
            if index == self.active:
                self.update_state()
            return
        self.render(index, *entry)
        if index == self.active:
            self.update_state()
            if self.search.text():
                self.find()

    def seed(self):
        entries = [('SYS', 'Serial connection established · COM5 @ 115200', 'text_secondary'),
                   ('BOOT', 'Firmware v2.4.0  |  build Sep 11 2026  09:32:16', 'brand_foreground'),
                   ('INFO', 'CPU clock: 240 MHz    Flash: 2048 KB    SRAM: 512 KB', 'text_primary'),
                   ('OK', 'Clock tree initialized', 'text_primary'),
                   ('OK', 'GPIO / UART / SPI peripheral initialization complete', 'text_primary'),
                   ('INFO', 'Loading calibration data from flash...', 'text_primary'),
                   ('OK', 'Calibration CRC verified: 0xA72F', 'text_primary'),
                   ('WARN', 'Sample interval exceeded: 1024 ms (target: 1000 ms)', 'text_primary'),
                   ('INFO', 'Sensor task started. Sampling interval: 1000 ms', 'text_primary'),
                   ('ERROR', 'I2C bus timeout: sensor @0x48 no ACK (retry 1/3)', 'text_primary'),
                   ('RX', 'temperature=26.42 C    voltage=3.301 V    status=READY', 'text_primary'),
                   ('RX', 'temperature=26.45 C    voltage=3.298 V    status=READY', 'text_primary'),
                   ('RX', 'temperature=26.44 C    voltage=3.302 V    status=READY', 'text_primary'),
                   ('TX', 'status', 'text_primary'),
                   ('INFO', 'uptime=00:12:48    heap_free=186432    tasks=7', 'text_primary'),
                   ('OK', 'Self-test passed. All peripherals online.', 'text_primary'),
                   ('RX', 'temperature=26.43 C    voltage=3.300 V    status=READY', 'text_primary'),
                   ('INFO', '等待命令输入；此窗口使用真实 Qt 控件与模拟数据。', 'text_secondary')]
        for i, entry in enumerate(entries):
            self.append(0, *entry, stamp=f'10:24:{i + 12:02}.083')
        self.append(0, 'TX', 'status', 'text_primary', stamp='10:27:52.246')
        self.append(0, 'DEMO', 'uptime=00:12:48    heap_free=186432    tasks=7    state=READY', 'success_foreground', stamp='10:27:52.246')
        self.append(0, 'TX', "按键字节  61  'a'", 'text_primary', stamp='10:27:52.307')
        for i in range(7):
            self.append(1, 'RX', f'sensor[{i}]  x=0.012  y=-0.006  z=9.803 m/s²', stamp=f'10:24:{i + 12:02}.156')
        self.append(2, 'SYS', '尚未连接。点击顶部“连接”体验连接状态流转。', 'text_secondary', stamp='10:24:00.000')

    def dispatch_command(self, text, display=None):
        """Send path shared by the command row, macros and history picks."""
        session = self.sessions[self.active]
        shown = display if display is not None else text.rstrip('\r\n')
        if session['state'] != 'connected':
            self.append(self.active, 'TX', f'ERROR  串口未连接 — “{shown}” 未发送', 'danger_foreground')
            set_role(self.state, 'danger')
            self.state.setText('发送失败 · 串口未连接')
            return False
        session['sent'] += len(text.encode('utf-8'))
        session['sent_log'].append(text.rstrip('\r\n'))
        session['sent_log'] = session['sent_log'][-50:]
        self.append(self.active, 'TX', shown, 'text_primary')
        responses = {'version': 'Firmware v2.4.0 · Board AE350-EVB · simulated response',
                     'status': 'uptime=00:12:48    heap_free=186432    tasks=7    state=READY',
                     'help': 'Available demo commands: version, status, help',
                     'ram': 'heap_free=186432 B    stack_peak=8.2 KB',
                     'css_pwr': 'power rail: ON (simulated)',
                     'reboot': 'Rebooting device… (simulated)'}
        response = responses.get(text.strip())
        if response:
            self.append(self.active, 'DEMO', response, 'success_foreground')
        return True

    def send(self):
        if self.mode.currentIndex() == 1 or not self.command.isEnabled():
            return
        text = self.command.text()
        if not text:
            return
        self.browse_reset()
        if self.encoding.currentText() == 'HEX':
            payload = parse_hex(text)
            if payload is None:
                self.append(self.active, 'TX', f'ERROR  HEX 输入无效：{text}', 'danger_foreground')
                set_role(self.state, 'danger')
                self.state.setText('发送失败 · HEX 格式无效')
                return
            display = ' '.join(f'{b:02X}' for b in payload)
            sent = self.dispatch_command(payload.decode('latin-1') + '\r', display=display)
        else:
            ending = {'CR': '\r', 'LF': '\n', 'CRLF': '\r\n'}[self.ending.currentText()]
            sent = self.dispatch_command(text + ending)
        if sent:
            self.command.clear()

    def direct_send(self, index, value):
        if index == self.active and self.sessions[index]['state'] == 'connected':
            self.sessions[index]['sent'] += len(value.encode('utf-8'))
            self.append(index, 'TX', f'按键字节  {value.encode("utf-8").hex(" ")}  {value!r}', 'text_primary')

    def browse_history(self, direction):
        if self.active < 0:
            return
        history = self.sessions[self.active]['sent_log']
        if not history:
            return
        if self.history_index is None:
            self.history_draft = self.command.text()
            self.history_index = len(history)
        self.history_index = max(0, min(len(history), self.history_index + direction))
        if self.history_index >= len(history):
            self.command.setText(self.history_draft)
        else:
            self.command.setText(history[self.history_index])

    def browse_reset(self):
        self.history_index = None
        self.history_draft = ''

    def show_history_menu(self):
        if self.active < 0:
            return
        history = self.sessions[self.active]['sent_log']
        menu = QMenu(self)
        if not history:
            empty = menu.addAction('暂无历史命令')
            empty.setEnabled(False)
        else:
            for command in reversed(history[-12:]):
                menu.addAction(command, lambda command=command: self._pick_history(command))
        menu.exec(QCursor.pos())
        menu.deleteLater()

    def _pick_history(self, command):
        self.command.setText(command)
        self.command.setFocus()

    def focus_command(self):
        self.command.setFocus()
        self.command.selectAll()

    def toggle_pause(self, paused=None):
        self.paused = not self.paused if paused is None else bool(paused)
        self.pause_button.blockSignals(True)
        self.pause_button.setChecked(self.paused)
        self.pause_button.blockSignals(False)
        self.pause_tool.blockSignals(True)
        self.pause_tool.setChecked(self.paused)
        self.pause_tool.blockSignals(False)
        for button in (self.pause_button, self.pause_tool):
            button.setText('恢复接收' if self.paused else '暂停接收')
            button.setProperty('iconName', 'play' if self.paused else 'pause')
            button.setIcon(icon('play' if self.paused else 'pause'))
        if self.paused:
            self.pending = 0
            self.pause_badge.setText('已暂停')
            self.pause_badge.show()
            self.pause_badge.raise_()
            self._position_badge()
        else:
            self.pause_badge.hide()
            self.rerender()
            if self.auto_scroll.isChecked() and self.active >= 0:
                bar = self.views[self.active].verticalScrollBar()
                bar.setValue(bar.maximum())
        self.update_state()

    def _position_badge(self):
        if not self.pause_badge.isVisible():
            return
        hint = self.pause_badge.sizeHint()
        self.pause_badge.resize(hint)
        self.pause_badge.move(self.logs.width() - hint.width() - round(26*self.ui_scale), round(6*self.ui_scale))

    def tick(self):
        self.ticks += 1
        for i, session in enumerate(self.sessions):
            if session['state'] == 'connected':
                self.append(i, 'RX', f'sample={self.ticks:05}    temperature={26.40 + self.ticks % 8 * .01:.2f} C    status=READY')

    def toggle_editor(self):
        opened = self.editor.isHidden()
        self.editor.setVisible(opened)
        self.expand.setText('收起宏编辑器' if opened else '展开宏编辑器')
        if opened:
            self.vertical.setSizes([450, 190])
        else:
            self.expand.setFocus()

    def run_macro(self):
        for command in self.macro_text.toPlainText().splitlines():
            if command.strip():
                self.dispatch_command(command.strip() + '\r')

    def open_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def close_search(self):
        self.search.clear()
        self.views[self.active].setFocus()

    def find(self):
        if self.active < 0:
            return
        view = self.views[self.active]
        self.matches = []
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(view.document())
        selection.cursor.movePosition(QTextCursor.MoveOperation.End)
        selection.format.setBackground(QColor(self.c['brand_background_subtle']))
        selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        selections = [selection]
        cursor = QTextCursor(view.document())
        query = self.search.text()
        while query:
            cursor = view.document().find(query, cursor)
            if cursor.isNull():
                break
            self.matches.append(QTextCursor(cursor))
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(cursor)
            selection.format.setBackground(QColor(self.c['warning_background']))
            selection.format.setForeground(QColor(self.c['warning_foreground']))
            selections.append(selection)
        view.setExtraSelections(selections)
        self.match_index = -1
        self.match_count.setText(f'{len(self.matches)} 个匹配' if query else '')

    def next_match(self):
        if self.matches:
            self.match_index = (self.match_index + 1) % len(self.matches)
            view = self.views[self.active]
            view.setTextCursor(self.matches[self.match_index])
            view.ensureCursorVisible()
            self.match_count.setText(f'{self.match_index + 1} / {len(self.matches)}')

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.search_row.isVisible():
            self.close_search()
            return
        super().keyPressEvent(event)

    # ---- Log context menu ----

    def _lines_text(self, view, raw=False):
        cursor = view.textCursor()
        if not cursor.hasSelection():
            return ''
        document = view.document()
        block = document.findBlock(cursor.selectionStart())
        last = document.findBlock(cursor.selectionEnd())
        lines = []
        while block.isValid():
            text = block.text()
            if raw:
                if self.timestamps.isChecked():
                    text = re.sub(r'^\d{2}:\d{2}:\d{2}\.\d{3}\s+', '', text)
                text = re.sub(r'^\S+\s+', '', text, count=1)
            lines.append(text)
            if block == last:
                break
            block = block.next()
        return '\n'.join(lines)

    def copy_lines(self, view):
        text = self._lines_text(view)
        if text:
            QApplication.clipboard().setText(text)

    def copy_raw(self, view):
        text = self._lines_text(view, raw=True)
        if text:
            QApplication.clipboard().setText(text)

    def log_menu(self, view):
        has_selection = view.textCursor().hasSelection()
        menu = QMenu(self)
        copy_action = menu.addAction('复制', view.copy)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.setEnabled(has_selection)
        lines_action = menu.addAction('复制选中行', lambda: self.copy_lines(view))
        lines_action.setEnabled(has_selection)
        raw_action = menu.addAction('复制原始数据', lambda: self.copy_raw(view))
        raw_action.setEnabled(has_selection)
        menu.addSeparator()
        clear_action = menu.addAction('清屏', self.clear_log)
        clear_action.setShortcut(QKeySequence('Ctrl+K'))
        save_action = menu.addAction('保存选中内容…', lambda: self.save_selection(view))
        save_action.setEnabled(has_selection)
        return menu


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path, help='Capture real Qt client area and exit')
    parser.add_argument('--native-title', action='store_true', help='Use the native window frame')
    parser.add_argument('--zoom', type=int, default=125, help='UI scale percent (75-200)')
    parser.add_argument('--size', default=None, help='Logical window size, e.g. 946x531')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setStyle(QStyleFactory.create('Fusion'))
    app.setFont(QFont('Microsoft YaHei UI', 7))
    window = Preview(native_title=args.native_title, zoom=args.zoom)
    if args.size:
        window.resize(*map(int, args.size.lower().split('x')))
    window.show()
    if args.capture:
        args.capture.mkdir(parents=True, exist_ok=True)
        def capture():
            if app.focusWidget():
                app.focusWidget().clearFocus()
            window.grab().save(str(args.capture / 'qt-preview-light.png'))
            window.toggle_editor()
            app.processEvents()
            window.grab().save(str(args.capture / 'qt-preview-macros.png'))
            window.toggle_editor()
            app.processEvents()
            window.toggle_pause(True)
            app.processEvents()
            window.grab().save(str(args.capture / 'qt-preview-paused.png'))
            window.toggle_pause(False)
            window.set_sidebar_collapsed(True)
            window.set_inspector_collapsed(True)
            app.processEvents()
            window.grab().save(str(args.capture / 'qt-preview-collapsed.png'))
            window.set_sidebar_collapsed(False)
            window.set_inspector_collapsed(False)
            window.theme(True)
            app.processEvents()
            window.grab().save(str(args.capture / 'qt-preview-dark.png'))
            app.quit()
        QTimer.singleShot(500, capture)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
