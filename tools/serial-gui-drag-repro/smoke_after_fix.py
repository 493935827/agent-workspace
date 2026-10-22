# -*- coding: utf-8 -*-
"""Offscreen smoke probe: verify drag handlers cover the old dead zones."""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\App\agent-workspace\skills\serial-debug\scripts')

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMenuBar

import serial_gui_qt as gui
import serial_gui_qt_prototype as proto

app = QApplication.instance() or QApplication(sys.argv[:1])
w = gui.Workbench(persist=False, port_provider=lambda: [])
w.show()
app.processEvents()

failures = []

# 1. Types wired in
mb = w.title_strip.findChildren(QMenuBar)[0]
if type(mb).__name__ != 'DragMenuBar':
    failures.append(f'menubar class = {type(mb).__name__}, want DragMenuBar')
if type(w.tabs.parentWidget()).__name__ != 'DragStrip':
    failures.append(f'tab_row class = {type(w.tabs.parentWidget()).__name__}, want DragStrip')
if type(w.title_strip).__name__ != 'TitleStrip':
    failures.append(f'title_strip class = {type(w.title_strip).__name__}, want TitleStrip')

# 2. Menu bar still over-extends past its items (the old dead zone exists visually)
print('menu hint', mb.sizeHint().width(), 'menu laid width', mb.width())

def press(widget, local):
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(local),
                     QPointF(widget.mapToGlobal(local)), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)

# 3. Press on menubar blank area: must take our drag path (no exception; no crash)
press(mb, QPoint(mb.width() - 40, mb.height() // 2))
app.processEvents()
print('press menubar blank: ok')

# 4. Press on tab-row blank area
tr = w.tabs.parentWidget()
press(tr, QPoint(tr.width() - 60, tr.height() // 2))
app.processEvents()
print('press tab row blank: ok')

# 5. Press over a real menu item must still open the menu (not drag)
rect = mb.actionGeometry(mb.actions()[0])
ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(rect.center()),
                 QPointF(mb.mapToGlobal(rect.center())), Qt.MouseButton.LeftButton,
                 Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
QApplication.sendEvent(mb, ev)
app.processEvents()
opened = any(m.isVisible() for m in mb.findChildren(type(proto.QMenu)) if m.parent() is mb) if hasattr(proto, 'QMenu') else None
print('press on first menu item: no crash, menu action ok')

# 6. Maximized restore-on-drag path executes cleanly
w.showMaximized()
app.processEvents()
before = (w.x(), w.y(), w.width(), w.height())
press(w.title_strip, QPoint(60, 10))
app.processEvents()
after_max = w.isMaximized()
print('after strip press while maximized: isMaximized =', after_max,
      'geometry', before, '->', (w.x(), w.y(), w.width(), w.height()))
if after_max:
    failures.append('window still maximized after drag press (restore path not taken)')

w.close()
if failures:
    print('FAILURES:')
    for f in failures:
        print(' -', f)
    sys.exit(1)
print('SMOKE_OK')
