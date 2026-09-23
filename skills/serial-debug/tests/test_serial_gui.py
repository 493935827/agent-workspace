import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from serial_gui import SerialWindow
from test_serial_service import FakeSerial
from serial_service import SerialService
from serial_client import Client


class GuiTests(unittest.TestCase):
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
        self.fail('GUI did not reach expected state')

    def test_shared_state_keyboard_send_and_close_preserve_service(self):
        device = FakeSerial()
        service = SerialService(port='FAKE', tcp=0, control=0, serial_factory=lambda *_: device).start()
        self.addCleanup(service.close)
        window = SerialWindow(control=service.control_port, tcp=service.tcp_port, autostart=False)
        window.show()
        self.addCleanup(window.close)
        self.until(lambda: window.state and window.state['connected'])
        with Client(port=service.control_port) as client:
            client.call('serial.configure', baudrate=57600)
            self.until(lambda: window.baud.currentText() == '57600')
            window.command.setText('send.hex {"data":"AA 55"}')
            QTest.keyClick(window.command, Qt.Key_Return)
            self.until(lambda: bytes(device.writes) == b'\xaaU')
            client.call('agent.acquire')
            self.until(lambda: not window.send_button.isEnabled())
            QTest.mouseClick(window.takeover, Qt.LeftButton)
            self.until(lambda: window.send_button.isEnabled())
            window.close()
            self.assertTrue(client.call('status')['connected'])
            self.assertFalse(device.closed)


if __name__ == '__main__':
    unittest.main()
