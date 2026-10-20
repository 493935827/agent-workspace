import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


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

    def test_active_selects_baud_that_answers_enter(self):
        samples = {
            115200: b"\r\natom>> ",
            57600: b"\xff\x00\x91\x03\x80\x00\xfe\x02" * 5,
            9600: b"",
        }

        def prober(_port, baud, _seconds, probe, _attempts):
            self.assertEqual(b"\r", probe, "active probing must submit the probe bytes")
            return samples[baud]

        baud, _scores, reason = MODULE.detect_baud_active(
            "COM_TEST", tuple(samples), 0.01, 1, 4, probe=b"\r", attempts=2, prober=prober
        )
        self.assertEqual(115200, baud)
        self.assertIsNone(reason)

    def test_active_rejects_silent_device(self):
        baud, _scores, reason = MODULE.detect_baud_active(
            "COM_TEST", (115200, 57600), 0.01, 1, 4,
            prober=lambda *_args: b"",
        )
        self.assertIsNone(baud)
        self.assertEqual("no_signal", reason)

    def test_active_rejects_ambiguous_answers(self):
        baud, _scores, reason = MODULE.detect_baud_active(
            "COM_TEST", (115200, 57600), 0.01, 1, 4,
            prober=lambda _port, _baud, _seconds, _probe, _attempts: b"\r\nready> ",
        )
        self.assertIsNone(baud)
        self.assertEqual("ambiguous", reason)

    def test_active_accumulates_rounds(self):
        calls = []

        def prober(_port, baud, seconds, probe, attempts):
            calls.append((baud, seconds, probe, attempts))
            return b"\r\natom>> " if baud == 115200 else b""

        baud, _scores, reason = MODULE.detect_baud_active(
            "COM_TEST", (115200, 57600), 0.6, 2, 4, probe=b"\r", attempts=3, prober=prober
        )
        self.assertEqual(115200, baud)
        self.assertIsNone(reason)
        # 2 rounds x 2 bauds, and probe parameters forwarded unchanged.
        self.assertEqual([(115200, 0.6, b"\r", 3), (57600, 0.6, b"\r", 3)] * 2, calls)

    def test_parse_probe_supports_escapes(self):
        self.assertEqual(b"\r", MODULE.parse_probe("\\r"))
        self.assertEqual(b"\n", MODULE.parse_probe("\\n"))
        self.assertEqual(b"help\r", MODULE.parse_probe("help\\r"))

    def test_parse_probe_keeps_non_ascii_bytes(self):
        # unicode_escape re-maps UTF-8 bytes as latin-1; encoding back with
        # latin-1 (not utf-8) restores them, so Chinese probe commands reach
        # the device byte-for-byte.
        self.assertEqual("复位\r".encode("utf-8"), MODULE.parse_probe("复位\\r"))

    def test_passive_sampling_holds_control_lines_low(self):
        seen = {}
        reads = iter([b"atom>> "])

        class FakeSerial:
            def __init__(self, **kwargs):
                seen.update(kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def reset_input_buffer(self):
                pass

            @property
            def in_waiting(self):
                return 1

            def read(self, _size):
                return next(reads, b"")

        with mock.patch.object(MODULE.serial, "Serial", FakeSerial):
            data = MODULE.sample_baud("COM_TEST", 115200, 0.05)
        self.assertEqual(b"atom>> ", data)
        self.assertFalse(seen.get("rts", True), "passive detection must hold RTS low")
        self.assertFalse(seen.get("dtr", True), "passive detection must hold DTR low")


if __name__ == "__main__":
    unittest.main()
