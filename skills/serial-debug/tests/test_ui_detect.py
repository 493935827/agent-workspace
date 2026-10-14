"""Regression tests for the GUI auto-detect (自动检测串口) button.

The button must connect an already-attached USB serial port instead of
waiting for a new insertion; multiple USB candidates open a pre-sorted
choice dialog with the best candidate pre-selected; only a machine with
no USB serial port falls back to waiting.
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
    from PySide6.QtWidgets import QApplication
    import serial_gui_qt
    from serial_gui_qt import Workbench, is_usb_serial, usb_serial_rank
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


class FakePort:
    def __init__(self, device, description='', hwid='', vid=None, pid=None):
        self.device = device
        self.description = description
        self.hwid = hwid
        self.vid = vid
        self.pid = pid


USB_FTDI = FakePort('COM6', 'USB Serial Port (COM6)', 'USB VID:PID=0403:6001', vid=0x0403, pid=0x6001)
USB_OTHER = FakePort('COM10', 'CMSIS-DAP', 'USB VID:PID=1fc9:0143', vid=0x1fc9, pid=0x0143)
BLUETOOTH = FakePort('COM4', '蓝牙链接上的标准串行 (COM4)', 'BTHENUM{...}', vid=0x0403, pid=0x6001)
LEGACY = FakePort('COM1', '通信端口', 'ACPI\\PNP0501')


class FakeLink:
    """Calm fake port: the read blocks briefly so worker loops stay slow."""

    def __init__(self, *args, **kwargs):
        self.writes = bytearray()

    @property
    def in_waiting(self):
        return 0

    def write(self, data):
        self.writes.extend(data)
        return len(data)

    def read(self, size):
        time.sleep(.02)
        return b''

    def close(self):
        pass


class PatchedDialog:
    """Stand-in for QInputDialog that records the item list and choice."""

    calls = []
    choice = ('', False)

    @staticmethod
    def getItem(parent, title, label, items, current=0, editable=True):
        PatchedDialog.calls.append((tuple(items), current))
        return PatchedDialog.choice


def dispose_window(window):
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench detect tests')
class DetectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, ports):
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        holder = {'ports': list(ports)}
        window = Workbench(persist=False,
                           settings_path=Path(directory.name) / 'settings.json',
                           port_provider=lambda: list(holder['ports']),
                           serial_factory=lambda *args, **kwargs: FakeLink())
        self.addCleanup(dispose_window, window)
        self.addCleanup(self.stop_workers, window)
        return window, holder

    def pump(self, window, seconds=2.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            window.poll()
            time.sleep(.01)

    def stop_workers(self, window):
        for s in window.sessions:
            if s.get('worker'):
                window.disconnect_session(s)
        self.pump(window, 1.0)

    def states(self, window):
        return [(s['port'], s['state']) for s in window.sessions]

    def patch_dialog(self, choice):
        original = serial_gui_qt.QInputDialog
        serial_gui_qt.QInputDialog = PatchedDialog
        PatchedDialog.calls = []
        PatchedDialog.choice = choice
        self.addCleanup(setattr, serial_gui_qt, 'QInputDialog', original)

    def test_single_attached_usb_port_connects_directly(self):
        window, _ = self.make_window([BLUETOOTH, LEGACY, USB_FTDI])
        window.detect()  # one USB candidate: no dialog, straight to connecting
        self.pump(window)
        self.assertIn(('COM6', 'connected'), self.states(window))

    def test_multiple_usb_ports_open_presorted_choice(self):
        window, _ = self.make_window([BLUETOOTH, USB_OTHER, USB_FTDI])
        self.patch_dialog((f'{USB_FTDI.device} · {USB_FTDI.description}', True))
        window.detect()
        self.assertEqual(1, len(PatchedDialog.calls))
        items, current = PatchedDialog.calls[0]
        self.assertEqual('等待新设备插入', items[0])
        self.assertEqual(1, current, 'the best USB candidate must be pre-selected')
        ftdi = items.index(f'{USB_FTDI.device} · {USB_FTDI.description}')
        other = items.index(f'{USB_OTHER.device} · {USB_OTHER.description}')
        bluetooth = items.index(f'{BLUETOOTH.device} · {BLUETOOTH.description}')
        self.assertLess(ftdi, other, 'natural COM order must rank COM6 before COM10')
        self.assertLess(other, bluetooth, 'USB candidates come before Bluetooth ports')
        self.pump(window)
        self.assertIn(('COM6', 'connected'), self.states(window))

    def test_no_usb_port_falls_back_to_waiting(self):
        window, holder = self.make_window([BLUETOOTH, LEGACY])
        self.patch_dialog(('等待新设备插入', True))
        window.detect()
        self.assertTrue(window.detecting)
        self.assertTrue(window.detect_timer.isActive())
        holder['ports'] = [BLUETOOTH, LEGACY, USB_FTDI]
        window.poll_ports()
        self.assertFalse(window.detecting)
        self.pump(window)
        self.assertIn(('COM6', 'connected'), self.states(window))

    def test_usb_serial_ranking(self):
        ports = [BLUETOOTH, USB_OTHER, LEGACY, USB_FTDI]
        self.assertEqual(['COM6', 'COM10'],
                         [p.device for p in sorted((p for p in ports if is_usb_serial(p)), key=usb_serial_rank)])
        self.assertTrue(is_usb_serial(USB_FTDI))
        self.assertFalse(is_usb_serial(BLUETOOTH), 'Bluetooth ports must not count as USB serial')
        self.assertFalse(is_usb_serial(LEGACY), 'ports without VID/PID must not count as USB serial')


if __name__ == '__main__':
    unittest.main()
