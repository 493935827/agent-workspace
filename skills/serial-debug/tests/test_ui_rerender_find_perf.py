"""Regression tests for the dual-bridge heavy-dataflow UI freeze (双桥卡顿).

Handoff 20261027-1610: with a full screen buffer (~5000 records) every
rerender() repainted every record through per-record insertText — switching
session tabs froze the main thread for seconds — and find() rescanned the
whole document once per received record while the search box had text, so
the poll loop stalled, the GUI event queue saturated and the bridge-side
subscription queue dropped data.

Locked-in behavior:
- switching sessions with a full buffer stays interactive (a view is only
  rebuilt when its render-relevant options actually changed, and a needed
  rebuild lands as a single batched document edit);
- a forced rebuild of a full buffer stays bounded;
- search keeps up with the RX stream: highlight rescans are debounced and
  match collection is capped.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from serial_gui_qt import Workbench
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

RECORDS = 5000  # RECORD_LIMIT: the full screen buffer from the incident report


def dispose_window(window):
    """Destroy a Workbench inside a long-lived QApplication (see test_ui_style)."""
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def wait_ms(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class RerenderFindPerfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = Workbench(persist=False,
                           settings_path=Path(directory.name) / 'settings.json',
                           port_provider=lambda: [])
        self.addCleanup(dispose_window, window)
        return window

    def feed(self, window, index, count, text='RRAM_TEST seq={i} ok\n'):
        stamp = datetime.now()
        for i in range(count):
            window.add_record(index, 'RX', text.replace('{i}', str(i)), stamp)

    def test_switch_with_full_buffer_stays_interactive(self):
        window = self.make_window()
        index_a = window.active
        index_b = window.create_session('COM_TEST_B')
        self.feed(window, index_a, RECORDS)
        window.switch(index_a)
        start = time.perf_counter()
        window.switch(index_b)
        window.switch(index_a)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.8,
            'a round-trip tab switch with a full buffer froze the main thread '
            f'for {elapsed*1000:.0f} ms')

    def test_option_change_rebuilds_view_correctly_and_stays_bounded(self):
        # Guards the fingerprint skip: an option change must really rebuild
        # the view (stale filters would be a correctness bug), and the rebuild
        # must not become slower than the old per-record path.
        window = self.make_window()
        index = window.active
        stamp = datetime.now()
        for i in range(RECORDS):
            if i % 5 == 0:
                window.add_record(index, 'TX', f'TXM echo seq={i} ok\n', stamp)
            else:
                window.add_record(index, 'RX', f'RRAM_TEST seq={i} ok\n', stamp)
        view = window.views[index]
        start = time.perf_counter()
        window.show_tx.setChecked(False)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0,
            f'rebuilding a full buffer froze the main thread for {elapsed*1000:.0f} ms')
        self.assertNotIn('TXM', view.toPlainText(), 'TX records must disappear while TX is hidden')
        window.show_tx.setChecked(True)
        self.assertIn('TXM', view.toPlainText(), 'TX records must come back when TX is shown')

    def test_search_does_not_rescan_per_received_record(self):
        window = self.make_window()
        index = window.active
        stamp = datetime.now()
        window.add_record(index, 'RX', 'NEEDLE setup\n', stamp)
        window.search.setText('NEEDLE')
        self.app.processEvents()
        for i in range(5):
            window.add_record(index, 'RX', f'NEEDLE hit {i}\n', stamp)
        self.app.processEvents()
        self.assertLess(len(window.matches), 6,
            'the log rescanned the whole document for every received record while search was active')
        wait_ms(400)
        self.assertEqual(len(window.matches), 6, 'the debounced rescan must still find every match')
        self.assertEqual(window.match_count.text(), '6 个匹配')

    def test_match_collection_is_capped(self):
        window = self.make_window()
        index = window.active
        self.feed(window, index, 600, text='KW line {i} ok\n')
        window.search.setText('KW')
        wait_ms(400)
        self.app.processEvents()
        self.assertLessEqual(len(window.matches), 500,
            'match collection must stop at the cap on a large document')
        self.assertIn('500+', window.match_count.text(),
            'a capped result must be reported as "<cap>+ 个匹配"')


if __name__ == '__main__':
    unittest.main()
