"""Shared-bridge control group in the workbench settings tab.

Covers the「共享串口桥」group (connect / takeover / one-click stop) and the
one-click stop path: confirm dialog, agent-lease recovery, service.stop with
the live instance id, and port release.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import socket
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

from test_serial_service import FakeSerial
from serial_service import SerialService
from serial_client import Client


class FakeButton:
    def __init__(self, text):
        self.text = text


class FakeMessageBox:
    """Offscreen QMessageBox stand-in; `confirm` picks the clicked button."""

    confirm = True
    instances = []

    class Icon:
        Warning = 'warning'

    class ButtonRole:
        AcceptRole = 'accept'
        RejectRole = 'reject'

    def __init__(self, *args, **kwargs):
        self.buttons = []
        self.clicked = None
        self.reject = None
        FakeMessageBox.instances.append(self)

    def addButton(self, text, role):
        button = FakeButton(text)
        self.buttons.append(button)
        if role == self.ButtonRole.AcceptRole:
            self.clicked = button
        else:
            self.reject = button
        return button

    def setDefaultButton(self, button):
        pass

    def exec(self):
        if not FakeMessageBox.confirm:
            self.clicked = self.reject

    def clickedButton(self):
        return self.clicked


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class ServiceControlGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        FakeMessageBox.confirm = True
        del FakeMessageBox.instances[:]

    def until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        self.fail('workbench did not reach expected state')

    def records(self, window, index, tag):
        return [r['text'] for r in window.sessions[index]['records'] if r['tag'] == tag]

    def make_window(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = Workbench(persist=False,
                           settings_path=Path(directory.name) / 'settings.json',
                           port_provider=lambda: [])
        self.addCleanup(window.close)
        return window

    def connect_service_session(self, window, service):
        name = f"service:127.0.0.1:{service.control_port}/FAKE"
        index = window.create_session(name)
        window.sessions[index]['service'] = dict(host='127.0.0.1', control=service.control_port,
                                                 device='FAKE', baud='115200')
        self.assertTrue(window.connect_session(index))
        return index

    def make_service(self, holder):
        def factory(*_):
            holder['device'] = FakeSerial()
            return holder['device']
        service = SerialService(port='FAKE', tcp=0, control=0, serial_factory=factory).start()
        self.addCleanup(service.close)
        return service

    def test_bridge_group_buttons_follow_session_type(self):
        window = self.make_window()
        # Direct session: only the connect entry is offered in the group.
        self.assertFalse(window.service_connect.isHidden())
        self.assertTrue(window.service_takeover.isHidden())
        self.assertTrue(window.service_stop.isHidden())
        # A service session (even before connecting) offers the one-click stop.
        index = window.create_session('service:127.0.0.1:1/FAKE')
        window.sessions[index]['service'] = dict(host='127.0.0.1', control=1,
                                                 device='FAKE', baud='115200')
        window.switch(index)
        self.assertFalse(window.service_stop.isHidden())
        self.assertTrue(window.service_takeover.isHidden())

    def test_stop_bridge_confirmed_releases_port_and_retires_session(self):
        holder = {}
        service = self.make_service(holder)
        window = self.make_window()
        index = self.connect_service_session(window, service)
        self.until(lambda: window.sessions[index]['state'] == 'connected')
        self.until(lambda: holder.get('device') is not None)
        self.assertFalse(holder['device'].closed)
        self.assertFalse(window.service_stop.isHidden())
        with mock.patch('serial_gui_qt.QMessageBox', FakeMessageBox):
            window.service_stop.click()
        self.until(lambda: holder['device'].closed)
        self.assertTrue(service.stop.is_set())
        self.until(lambda: window.sessions[index]['state'] == 'disconnected')
        self.until(lambda: not window.sessions[index].get('worker'))
        self.assertTrue(any('共享串口桥已停止' in text for text in self.records(window, index, 'SYS')))
        self.assertIsNone(window.sessions[index].get('service_stop_pending'))
        self.assertTrue(window.service_stop.isEnabled())

    def test_stop_bridge_takes_lease_back_from_agent_first(self):
        holder = {}
        service = self.make_service(holder)
        window = self.make_window()
        index = self.connect_service_session(window, service)
        self.until(lambda: window.sessions[index]['state'] == 'connected')
        with Client(port=service.control_port) as client:
            client.call('agent.acquire')
            self.until(lambda: window.service_takeover.isEnabled())
            with mock.patch('serial_gui_qt.QMessageBox', FakeMessageBox):
                window.service_stop.click()
            self.until(lambda: holder['device'].closed)
            self.until(lambda: any('收回租约' in text for text in self.records(window, index, 'SYS')))
            status = client.call('status')
        self.assertIsNone(service.token)
        self.assertEqual(status['owner'], 'human')

    def test_stop_bridge_cancel_keeps_service_running(self):
        holder = {}
        service = self.make_service(holder)
        window = self.make_window()
        index = self.connect_service_session(window, service)
        self.until(lambda: window.sessions[index]['state'] == 'connected')
        FakeMessageBox.confirm = False
        with mock.patch('serial_gui_qt.QMessageBox', FakeMessageBox):
            window.service_stop.click()
        self.assertFalse(holder['device'].closed)
        self.assertFalse(service.stop.is_set())
        self.assertEqual(window.sessions[index]['state'], 'connected')
        self.assertFalse(any('正在停止共享串口桥' in text for text in self.records(window, index, 'SYS')))
        window.disconnect_session(window.sessions[index])
        self.until(lambda: not window.sessions[index].get('worker'))

    def test_stop_bridge_reports_unreachable_service(self):
        window = self.make_window()
        # Reserve a port, then close it: nothing is listening there.
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        dead_port = probe.getsockname()[1]
        probe.close()
        index = window.create_session(f'service:127.0.0.1:{dead_port}/FAKE')
        window.sessions[index]['service'] = dict(host='127.0.0.1', control=dead_port,
                                                 device='FAKE', baud='115200')
        window.switch(index)
        with mock.patch('serial_gui_qt.QMessageBox', FakeMessageBox):
            window.service_stop.click()
        self.until(lambda: any('停止共享串口桥失败' in text
                               for text in self.records(window, index, 'ERROR')))
        self.assertIsNone(window.sessions[index].get('service_stop_pending'))
        self.assertTrue(window.service_stop.isEnabled())


if __name__ == '__main__':
    unittest.main()
