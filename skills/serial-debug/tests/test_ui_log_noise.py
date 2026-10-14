"""Regression tests for log noise filtering (silent Enter pass).

Covers: direct-key Enter submits without a 按键字节 TX record, empty
command submissions stay silent, the Enter echo closes the prompt line
instead of printing a blank one, and bare blank RX pieces never render
as standalone timestamped lines. Records keep full text; only the view
is filtered.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import queue
import re
import sys
import threading
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from PySide6.QtCore import QEvent, QCoreApplication
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
        self.commands = queue.Queue(maxsize=8)
        self.stopped = threading.Event()


def bare_rx_lines(text):
    """Display lines that carry a timestamp and the RX tag but no content."""
    return [line for line in text.split('\n') if re.search(r'\bRX\s*$', line)]


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench log noise tests')
class LogNoiseTests(unittest.TestCase):
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
        return index, s, worker

    def tx_records(self, s):
        return [r for r in s['records'] if r['tag'] == 'TX']

    def test_direct_enter_is_queued_without_display_text(self):
        window = self.make_window()
        index, s, worker = self.connect_fake(window)
        window.direct_send(index, '\r')
        window.direct_send(index, 'a')
        token, payload, shown = worker.commands.get_nowait()
        self.assertEqual(payload, b'\r')
        self.assertIsNone(shown, 'Enter must not carry a 按键字节 display text')
        token, payload, shown = worker.commands.get_nowait()
        self.assertEqual(payload, b'a')
        self.assertIn('按键字节', shown)

    def test_sent_event_without_display_text_adds_no_record(self):
        window = self.make_window()
        index, s, worker = self.connect_fake(window)
        window.events.put((worker, 'sent', (None, b'\r', None), datetime.now()))
        window.poll()
        self.assertEqual(s['sent'], 1, 'byte counters must still track silent sends')
        self.assertFalse(self.tx_records(s))

    def test_empty_command_submission_stays_silent(self):
        window = self.make_window()
        index, s, worker = self.connect_fake(window)
        self.assertTrue(window.dispatch_command('\r'))
        token, payload, shown = worker.commands.get_nowait()
        self.assertEqual(payload, b'\r')
        self.assertEqual(shown, '')
        window.events.put((worker, 'sent', (token, payload, shown), datetime.now()))
        window.poll()
        self.assertFalse(self.tx_records(s))

    def test_enter_echo_closes_prompt_without_blank_line(self):
        window = self.make_window()
        index = window.create_session('COM_FAKE')
        stamp = datetime.now()
        window.receive_text(index, 'atom>>', stamp)
        window.receive_text(index, '\r\natom>>', stamp)
        lines = window.views[index].toPlainText().split('\n')
        hits = [i for i, line in enumerate(lines) if 'atom>>' in line]
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[1] - hits[0], 1,
                         f'echo CRLF must close the prompt line, got: {lines!r}')
        self.assertFalse(bare_rx_lines('\n'.join(lines)))

    def test_blank_echo_after_tx_record_is_not_rendered(self):
        window = self.make_window()
        index = window.create_session('COM_FAKE')
        stamp = datetime.now()
        window.add_record(index, 'RX', 'atom>>', stamp)
        window.add_record(index, 'TX', "按键字节 0d '\\r'\n", stamp, raw=b'\r')
        window.add_record(index, 'RX', '\r\natom>>', stamp)
        text = window.views[index].toPlainText()
        self.assertFalse(bare_rx_lines(text),
                         f'blank RX line must not render, got: {text!r}')
        self.assertEqual(text.count('atom>>'), 2)

    def test_output_blank_lines_are_suppressed_in_view_only(self):
        window = self.make_window()
        index = window.create_session('COM_FAKE')
        stamp = datetime.now()
        # Real path: the ANSI parser normalizes CR to LF and collapses CRLF.
        window.receive_text(index, 'line1\r\n\r\nline2\r\n', stamp)
        text = window.views[index].toPlainText()
        self.assertFalse(bare_rx_lines(text))
        self.assertIn('line1', text)
        self.assertIn('line2', text)
        # The record keeps the blank line: display filtering must not lose data.
        self.assertEqual(window.sessions[index]['records'][-1]['text'], 'line1\n\nline2\n')

    def test_raw_cr_blank_piece_is_not_rendered(self):
        window = self.make_window()
        index = window.create_session('COM_FAKE')
        stamp = datetime.now()
        # Peer writes and any direct record path can carry a raw CR piece.
        window.add_record(index, 'RX', '\r\natom>>', stamp)
        text = window.views[index].toPlainText()
        self.assertFalse(bare_rx_lines(text), f'raw CR must not print a blank line, got: {text!r}')
        self.assertIn('atom>>', text)


if __name__ == '__main__':
    unittest.main()
