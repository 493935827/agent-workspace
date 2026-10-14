"""Regression tests for the unified style work (2026-10 style pass).

Covers: dark-first default with persisted override, Tab focus traversal,
status-bar error visibility (previously clobbered within one 30 ms poll),
inline dialog error helper, and search field width.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from PySide6.QtCore import QEvent, QCoreApplication
    from PySide6.QtWidgets import QApplication, QDialog, QFormLayout
    from serial_gui_qt import Workbench
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


def dispose_window(window):
    """Close and really destroy a Workbench inside a long-lived QApplication.

    PySide6 keeps every closed workbench alive through child-widget signal
    connections that Python GC cannot traverse; each survivor makes the next
    application-wide setStyleSheet (theme/zoom) slower. Flushing the deferred
    delete drops the widget count back to zero after every test.
    """
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench style tests')
class StyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, **kwargs):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = Path(directory.name) / 'settings.json'
        window = Workbench(persist=kwargs.pop('persist', False), settings_path=settings,
                           port_provider=lambda: [], **kwargs)
        self.addCleanup(dispose_window, window)
        return window, settings

    def test_dark_is_default_without_saved_settings(self):
        window, _ = self.make_window(persist=True)
        self.assertTrue(window.dark, 'first run must default to the dark theme')

    def test_saved_light_preference_is_restored(self):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = Path(directory.name) / 'settings.json'
        first = Workbench(persist=True, settings_path=settings, port_provider=lambda: [])
        first.theme(False)
        first.save_settings()
        dispose_window(first)
        second = Workbench(persist=True, settings_path=settings, port_provider=lambda: [])
        self.addCleanup(dispose_window, second)
        self.assertFalse(second.dark, 'saved light preference must override the dark default')

    def test_tab_without_macro_match_is_not_consumed(self):
        window, _ = self.make_window()
        window.command.setText('不存在的宏名')
        self.assertFalse(window.expand_macro(), 'no match must let Tab traverse focus')

    def test_tab_with_macro_match_expands(self):
        window, _ = self.make_window()
        window.command.setText('status')
        self.assertTrue(window.expand_macro())
        self.assertEqual(window.command.text(), 'status')

    def test_report_error_holds_status_and_danger_role(self):
        window, _ = self.make_window()
        window.report_error('串口未连接，数据未发送')
        self.assertEqual(window.state.text(), '串口未连接，数据未发送')
        self.assertEqual(window.state.property('role'), 'danger')
        # The old bug: the next poll's update_state wiped the message in 30 ms.
        window.update_state()
        window.update_state()
        self.assertEqual(window.state.text(), '串口未连接，数据未发送')
        self.assertEqual(window.state.property('role'), 'danger')
        self.assertTrue(any(r['tag'] == 'ERROR' and '串口未连接' in r['text']
                            for r in window.sessions[window.active]['records']))

    def test_status_error_expires_back_to_normal(self):
        window, _ = self.make_window()
        window.report_error('测试错误')
        window._status_error = ('测试错误', time.monotonic() - 1)
        window.update_state()
        self.assertEqual(window.state.property('role'), 'muted')
        self.assertNotEqual(window.state.text(), '测试错误')

    def test_inline_form_error_shows_message_near_fields(self):
        window, _ = self.make_window()
        dialog = QDialog(window)
        form = QFormLayout(dialog)
        show = window.inline_form_error(form)
        error = form.itemAt(0).widget()
        self.assertFalse(error.isVisibleTo(dialog))
        show('名称不能为空或与其他宏重复')
        self.assertIn('名称不能为空', error.text())
        self.assertEqual(error.property('role'), 'danger')
        self.assertTrue(error.isVisibleTo(dialog))

    def test_search_field_widened(self):
        window, _ = self.make_window()
        self.assertGreaterEqual(window.search.maximumWidth(), 220)


if __name__ == '__main__':
    unittest.main()
