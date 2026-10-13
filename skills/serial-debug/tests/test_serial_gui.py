import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from PySide6.QtWidgets import QApplication
    from serial_gui_qt import Workbench
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from test_serial_service import FakeSerial
from serial_service import SerialService
from serial_client import Client


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class GuiTests(unittest.TestCase):
    """The vendored Qt workbench drives the real managed service end to end."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        self.fail('workbench did not reach expected state')

    def make_window(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Workbench(persist=False,
                         settings_path=Path(directory.name) / 'settings.json',
                         port_provider=lambda: [])

    def test_service_session_send_takeover_and_close_preserve_service(self):
        holder = {}
        def factory(*_):
            holder['device'] = FakeSerial()
            return holder['device']
        service = SerialService(port='FAKE', tcp=0, control=0, serial_factory=factory).start()
        self.addCleanup(service.close)
        window = self.make_window()
        self.addCleanup(window.close)
        name = f"service:127.0.0.1:{service.control_port}/FAKE"
        index = window.create_session(name)
        window.sessions[index]['service'] = dict(host='127.0.0.1', control=service.control_port,
                                                 device='FAKE', baud='115200')
        self.assertTrue(window.connect_session(index))
        self.until(lambda: window.sessions[index]['state'] == 'connected')
        self.until(lambda: '控制权：人工' in window.info_values['设备运行状态'].text())
        self.assertTrue(window.dispatch_command('help\r'))
        self.until(lambda: 'device' in holder and bytes(holder['device'].writes) == b'help\r')
        self.until(lambda: any(r['tag'] == 'TX' and 'help' in r['text']
                               for r in window.sessions[index]['records']))
        with Client(port=service.control_port) as client:
            client.call('agent.acquire')
            self.until(lambda: window.service_takeover.isEnabled())
            window.service_takeover.click()
            self.until(lambda: not window.service_takeover.isEnabled())
            status = client.call('status')
        self.assertEqual(status['owner'], 'human')
        self.assertTrue(status['connected'])
        window.disconnect_session(window.sessions[index])
        self.until(lambda: not window.sessions[index].get('worker'))
        window.close()
        self.assertFalse(holder['device'].closed)


if __name__ == '__main__':
    unittest.main()
