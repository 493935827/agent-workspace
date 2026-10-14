import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "windows" / "detect_serial_port.py"
SPEC = importlib.util.spec_from_file_location("detect_serial_port", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakePort:
    def __init__(self, device, description="", hwid="", vid=None, pid=None):
        self.device = device
        self.description = description
        self.hwid = hwid
        self.vid = vid
        self.pid = pid


def enumerator(*ports):
    return lambda: list(ports)


USB_FTDI = FakePort("COM6", "USB Serial Port (COM6)", "USB VID:PID=0403:6001", vid=0x0403, pid=0x6001)
BLUETOOTH = FakePort("COM4", "蓝牙链接上的标准串行 (COM4)",
                     "BTHENUM{...}", vid=0x0403, pid=0x6001)
LEGACY = FakePort("COM1", "通信端口", "ACPI\\PNP0501")


class ScriptedEnumerator:
    """Return one phase of ports per call: the first call is the snapshot."""

    def __init__(self, *phases):
        self.phases = phases
        self.calls = 0

    def __call__(self):
        phase = self.phases[min(self.calls, len(self.phases) - 1)]
        self.calls += 1
        return list(phase)


class DetectSerialPortTests(unittest.TestCase):
    def test_pick_now_prefers_usb_over_bluetooth_and_legacy(self):
        best = MODULE.pick_attached_port(enumerator(BLUETOOTH, LEGACY, USB_FTDI))
        self.assertEqual("COM6", best.device)

    def test_pick_now_returns_none_without_usb_serial(self):
        self.assertIsNone(MODULE.pick_attached_port(enumerator(BLUETOOTH, LEGACY)))

    def test_pick_now_ranks_multiple_usb_ports_by_natural_order(self):
        first = FakePort("COM10", "USB Serial Port", "USB VID:PID=0403:6001", vid=1, pid=2)
        second = FakePort("COM9", "USB Serial Port", "USB VID:PID=0403:6001", vid=1, pid=2)
        best = MODULE.pick_attached_port(enumerator(first, second))
        self.assertEqual("COM9", best.device)

    def test_detect_next_port_reports_newly_inserted(self):
        det = MODULE.detect_next_port(0.5, 0.01, enumerator=ScriptedEnumerator([], [USB_FTDI]))
        self.assertEqual("COM6", det.device)

    def test_detect_next_port_reports_reattached(self):
        det = MODULE.detect_next_port(
            0.5, 0.01, enumerator=ScriptedEnumerator([USB_FTDI], [], [USB_FTDI])
        )
        self.assertEqual("COM6", det.device)

    def test_detect_next_port_times_out_without_change(self):
        self.assertIsNone(
            MODULE.detect_next_port(0.03, 0.01, enumerator=ScriptedEnumerator([], []))
        )


if __name__ == "__main__":
    unittest.main()
