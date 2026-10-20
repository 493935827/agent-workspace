import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from PySide6.QtWidgets import QApplication
    from serial_gui_qt import Workbench
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from test_serial_service import DriftSerial
from serial_service import SerialService


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class AutoBaudGuiTests(unittest.TestCase):
    """Online baud detection wired into both direct and service sessions."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Shrink live scan windows so candidate sweeps finish quickly offscreen.
        patcher = mock.patch('serial_gui_qt.SCAN_SECONDS', 0.02)
        patcher.start()
        self.addCleanup(patcher.stop)

    def until(self, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        self.fail('workbench did not reach expected state')

    def records(self, window, index, tag):
        return [r['text'] for r in window.sessions[index]['records'] if r['tag'] == tag]

    def make_window(self, serial_factory=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        kwargs = dict(persist=False, settings_path=Path(directory.name) / 'settings.json',
                      port_provider=lambda: [])
        if serial_factory is not None:
            kwargs['serial_factory'] = serial_factory
        return Workbench(**kwargs)

    def close_cleanly(self, window, index):
        # Stop and fully reap the worker first; a lingering worker would keep
        # emitting into this window and slow every later test's processEvents.
        window.disconnect_session(window.sessions[index])
        self.until(lambda: not window.sessions[index].get('worker'))
        window.close()

    def test_direct_session_auto_rescans_on_garbage_without_writing(self):
        holder = {}
        def factory(*args, **kwargs):
            holder['device'] = DriftSerial()
            return holder['device']
        window = self.make_window(serial_factory=factory)
        index = window.create_session('FAKE')
        window.sessions[index]['baud'] = '115200'
        self.assertTrue(window.connect_session(index))
        self.until(lambda: window.sessions[index]['state'] == 'connected')
        for _ in range(800):
            holder['device'].input.put(b'hello world\r\n')
        self.until(lambda: window.sessions[index]['baud'] == '921600')
        self.until(lambda: any('波特率已从 115200 切换为 921600' in t
                               for t in self.records(window, index, 'SYS')))
        self.assertTrue(any('被动扫描波特率中' in t for t in self.records(window, index, 'SYS')))
        self.assertEqual(921600, holder['device'].settings['baudrate'])
        self.assertEqual(b'', bytes(holder['device'].writes))  # passive monitor sends nothing
        self.close_cleanly(window, index)

    def test_manual_online_scan_updates_service_session(self):
        holder = {}
        def factory(*args, **kwargs):
            holder['device'] = DriftSerial()
            return holder['device']
        service = SerialService(port='FAKE', tcp=0, control=0, serial_factory=factory,
                                auto_baud=dict(enabled=False, seconds=0.05)).start()
        self.addCleanup(service.close)
        window = self.make_window()
        self.addCleanup(window.close)
        name = f"service:127.0.0.1:{service.control_port}/FAKE"
        index = window.create_session(name)
        window.sessions[index]['service'] = dict(host='127.0.0.1', control=service.control_port,
                                                 device='FAKE', baud='115200')
        self.assertTrue(window.connect_session(index))
        self.until(lambda: window.sessions[index]['state'] == 'connected')
        window.switch(index)
        for _ in range(800):
            holder['device'].input.put(b'hello world\r\n')
        with mock.patch('serial_gui_qt.QInputDialog.getItem',
                        return_value=('被动监听（不发送数据，设备需持续输出）', True)):
            window.baud_scan_button.click()
        self.until(lambda: window.sessions[index]['baud'] == '921600')
        self.until(lambda: any('波特率已从 115200 切换为 921600' in t
                               for t in self.records(window, index, 'SYS')))
        self.assertEqual('921600', window.sessions[index]['service']['baud'])
        self.assertEqual(b'', bytes(holder['device'].writes))
        self.close_cleanly(window, index)

    def test_scan_button_requires_connected_session(self):
        window = self.make_window()
        self.addCleanup(window.close)
        window.baud_scan_button.click()
        self.until(lambda: any('请先连接串口' in t for t in self.records(window, 0, 'ERROR')))

    def test_autobaud_session_options_roundtrip(self):
        window = self.make_window()
        self.addCleanup(window.close)
        self.assertTrue(window.sessions[0]['options']['autobaud_monitor'])
        self.assertFalse(window.sessions[0]['options']['autobaud_probe'])
        window.autobaud_probe.setChecked(True)
        window.autobaud_monitor.setChecked(False)
        window.capture_session()
        options = window.sessions[window.active]['options']
        self.assertFalse(options['autobaud_monitor'])
        self.assertTrue(options['autobaud_probe'])
        window.autobaud_probe.setChecked(False)
        window.autobaud_monitor.setChecked(True)
        window.switch(window.active)
        self.assertFalse(window.autobaud_probe.isChecked())
        self.assertTrue(window.autobaud_monitor.isChecked())


if __name__ == '__main__':
    unittest.main()
