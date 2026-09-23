import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "windows" / "detect_serial_baud.py"
SPEC = importlib.util.spec_from_file_location("detect_serial_baud", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DetectSerialBaudTests(unittest.TestCase):
    def test_selects_clear_console_output(self):
        samples = {
            115200: b"Booting ATOM\r\nversion 1.2.3\r\natom_io>> ",
            57600: b"\xff\x00\x91\x03\x80\x00\xfe\x02" * 5,
            9600: b"",
        }

        def sampler(_port, baud, _seconds):
            return samples[baud]

        baud, _scores, reason = MODULE.detect_baud(
            "COM_TEST", tuple(samples), 0.01, 1, 16, sampler=sampler
        )
        self.assertEqual(115200, baud)
        self.assertIsNone(reason)

    def test_rejects_silent_input(self):
        baud, _scores, reason = MODULE.detect_baud(
            "COM_TEST", (115200, 57600), 0.01, 2, 16,
            sampler=lambda *_args: b"",
        )
        self.assertIsNone(baud)
        self.assertEqual("no_signal", reason)

    def test_accepts_utf8_console_output(self):
        samples = {
            115200: "系统启动完成\r\n请输入命令> ".encode("utf-8"),
            9600: b"\xff\x00\x91\x03\x80\x00\xfe\x02" * 5,
        }
        baud, _scores, reason = MODULE.detect_baud(
            "COM_TEST", tuple(samples), 0.01, 1, 16,
            sampler=lambda _port, candidate, _seconds: samples[candidate],
        )
        self.assertEqual(115200, baud)
        self.assertIsNone(reason)

    def test_rejects_two_similarly_good_candidates(self):
        baud, _scores, reason = MODULE.detect_baud(
            "COM_TEST", (115200, 57600), 0.01, 1, 16,
            sampler=lambda _port, candidate, _seconds: (
                f"candidate {candidate}\r\nready> ".encode("ascii")
            ),
        )
        self.assertIsNone(baud)
        self.assertEqual("ambiguous", reason)

    def test_parse_bauds_deduplicates_in_order(self):
        self.assertEqual((115200, 9600), MODULE.parse_bauds("115200,9600,115200"))


if __name__ == "__main__":
    unittest.main()
