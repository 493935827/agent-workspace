"""Regression tests for direct-send arrow keys (预输入显示消失).

The workbench log is an append-only view, so in-line cursor movement can
never be rendered: devices answer the transmitted ←/→ escape sequences
with backspace-style erasure (or invisible cursor moves), which wiped the
device-echoed input line from the log. ←/→ must stay local in direct-send
mode; history (↑/↓) and editing keys keep their byte-for-byte behavior.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import queue
import sys
import threading
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    from serial_gui_qt import Workbench
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


def dispose_window(window):
    """Destroy a Workbench inside a long-lived QApplication (see test_ui_style)."""
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class FakeWorker:
    """Just enough worker surface for write_payload and the poll() event pump."""

    def __init__(self):
        self.commands = queue.Queue(maxsize=256)
        self.stopped = threading.Event()


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class DirectArrowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = Workbench(persist=False,
                           settings_path=Path(directory.name) / 'settings.json',
                           port_provider=lambda: [])
        self.addCleanup(dispose_window, window)
        return window

    def connect_fake(self, window, port='COM_FAKE'):
        index = window.create_session(port)
        s = window.sessions[index]
        worker = FakeWorker()
        s['worker'] = worker
        window.workers[worker] = s
        s['state'] = 'connected'
        window.update_state()
        return index, s, worker

    def press(self, view, key, text=''):
        QApplication.sendEvent(view, QKeyEvent(QEvent.Type.KeyPress, key,
                                               Qt.KeyboardModifier.NoModifier, text))

    def direct_view(self, window, index):
        view = window.views[index]
        self.assertTrue(view.direct, 'connected direct-send session must have a direct view')
        return view

    def test_left_right_are_never_transmitted(self):
        window = self.make_window()
        index, s, worker = self.connect_fake(window)
        view = self.direct_view(window, index)
        self.press(view, Qt.Key.Key_Left)
        self.press(view, Qt.Key.Key_Right)
        self.press(view, Qt.Key.Key_Left, '')
        self.assertTrue(worker.commands.empty(),
                        '←/→ reached the serial device from the direct-send log view')

    def test_typed_line_survives_arrow_keys(self):
        window = self.make_window()
        index, s, worker = self.connect_fake(window)
        view = self.direct_view(window, index)
        for ch in 'abc':
            self.press(view, getattr(Qt.Key, 'Key_' + ch.upper()), ch)
        typed = []
        while not worker.commands.empty():
            typed.append(worker.commands.get_nowait()[1])
        self.assertEqual(typed, [b'a', b'b', b'c'])
        # The board echoes the typed characters; the log shows the input line.
        window.receive_text(index, 'abc', datetime.now())
        self.assertIn('abc', view.toPlainText())
        # Before the fix the arrows were sent, the board answered with
        # backspaces and the echoed input line disappeared from the log.
        self.press(view, Qt.Key.Key_Left)
        self.press(view, Qt.Key.Key_Right)
        self.assertTrue(worker.commands.empty())
        self.assertIn('abc', view.toPlainText())

    def test_history_and_editing_keys_keep_transmitting(self):
        window = self.make_window()
        index, s, worker = self.connect_fake(window)
        view = self.direct_view(window, index)
        expectations = [(Qt.Key.Key_Up, b'\x1b[A'), (Qt.Key.Key_Down, b'\x1b[B'),
                        (Qt.Key.Key_Return, b'\r'), (Qt.Key.Key_Backspace, b'\x08'),
                        (Qt.Key.Key_Tab, b'\t'), (Qt.Key.Key_Escape, b'\x1b')]
        for key, expected in expectations:
            self.press(view, key)
            token, payload, shown = worker.commands.get_nowait()
            self.assertEqual(payload, expected, f'{key} must keep its direct-send byte')
            self.assertEqual(worker.commands.qsize(), 0)

    def test_left_right_still_edit_the_command_input(self):
        window = self.make_window()
        index, s, worker = self.connect_fake(window)
        window.mode.setCurrentIndex(0)
        window.update_state()
        command = window.command
        command.setFocus()
        self.app.processEvents()
        for ch in 'ver':
            self.press(command, getattr(Qt.Key, 'Key_' + ch.upper()), ch)
        self.assertEqual(command.text(), 'ver')
        self.press(command, Qt.Key.Key_Left)
        self.press(command, Qt.Key.Key_Right)
        self.assertEqual(command.text(), 'ver', '←/→ must stay ordinary cursor keys in the command input')


if __name__ == '__main__':
    unittest.main()
