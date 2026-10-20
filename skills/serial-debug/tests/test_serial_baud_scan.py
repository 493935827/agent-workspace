import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from serial_baud_scan import rank_samples, readability, scan_open_device


class FakeDevice:
    """Simulates a device transmitting one payload at a fixed true baud."""

    def __init__(self, good_baud=921600, payload=b'atom>> ready\r\n', reject_bauds=()):
        self.good = good_baud
        self.payload = payload
        self.reject_bauds = tuple(reject_bauds)
        self.settings = dict(baudrate=115200)
        self.writes = bytearray()

    def read(self, size):
        time.sleep(0.001)  # one chunk per millisecond, like a real UART window
        if self.settings['baudrate'] == self.good:
            return self.payload
        return bytes((byte * 7 + 13) % 256 for byte in self.payload)

    def write(self, data):
        self.writes.extend(data)
        return len(data)

    def get_settings(self):
        return self.settings.copy()

    def apply_settings(self, settings):
        if settings.get('baudrate') in self.reject_bauds:
            raise OSError('unsupported baud')
        self.settings.update(settings)


class ReadabilityTests(unittest.TestCase):
    def test_read_console_text_scores_high(self):
        self.assertGreater(readability(b'Booting ATOM\r\nversion 1.2.3\r\n'), 0.9)
        self.assertGreater(readability('系统启动完成\r\n'.encode('utf-8')), 0.9)

    def test_binary_noise_scores_low(self):
        self.assertLess(readability(b'\xff\x00\x91\x03\x80\x00\xfe\x02' * 4), 0.2)

    def test_empty_input_scores_zero(self):
        self.assertEqual(0.0, readability(b''))

    def test_rank_samples_rejects_garbage_only_input(self):
        baud, _scores, reason = rank_samples(
            {115200: b'\xff\x00\x91\x03' * 8, 9600: b'\xfe\x01\x87\x7f' * 8}, 8)
        self.assertIsNone(baud)
        self.assertEqual('no_signal', reason)


class ScanOpenDeviceTests(unittest.TestCase):
    def test_finds_winner_on_open_device_and_restores_start_baud(self):
        device = FakeDevice(good_baud=921600)
        winner, _scores, reason = scan_open_device(
            device, (115200, 921600), seconds=0.02, rounds=1, min_bytes=4)
        self.assertEqual(921600, winner)
        self.assertIsNone(reason)
        self.assertEqual(115200, device.settings['baudrate'])

    def test_restores_start_baud_when_no_signal(self):
        device = FakeDevice(payload=b'')
        winner, _scores, reason = scan_open_device(
            device, (115200, 921600), seconds=0.02, rounds=1, min_bytes=4)
        self.assertIsNone(winner)
        self.assertEqual('no_signal', reason)
        self.assertEqual(115200, device.settings['baudrate'])

    def test_active_mode_writes_probe_per_candidate_and_round(self):
        device = FakeDevice(payload=b'')
        scan_open_device(device, (115200, 921600), seconds=0.02, rounds=2, min_bytes=4,
                         probe=b'\r', attempts=1)
        self.assertEqual(b'\r' * 4, bytes(device.writes))

    def test_passive_mode_never_writes(self):
        device = FakeDevice(good_baud=9600)
        winner, _scores, _reason = scan_open_device(
            device, (115200, 9600), seconds=0.02, rounds=1, min_bytes=4)
        self.assertEqual(9600, winner)
        self.assertEqual(b'', bytes(device.writes))

    def test_unsupported_candidate_is_skipped_without_aborting(self):
        device = FakeDevice(good_baud=9600, reject_bauds=(123,))
        winner, scores, reason = scan_open_device(
            device, (123, 9600), seconds=0.02, rounds=1, min_bytes=4)
        self.assertEqual(9600, winner)
        self.assertIsNone(reason)
        self.assertEqual({123, 9600}, {item.baud for item in scores})

    def test_abort_stops_the_sweep_and_restores_start_baud(self):
        # The bridge hands should_abort to every live scan so a takeover or
        # device action can reclaim the port instead of clobbering the scan's
        # transition while the scan still owns the device.
        device = FakeDevice(payload=b'')
        applied = []
        original_apply = device.apply_settings

        def tracking_apply(settings):
            applied.append(settings.get('baudrate'))
            return original_apply(settings)

        device.apply_settings = tracking_apply
        state = dict(calls=0)

        def abort_at_third_check():
            state['calls'] += 1
            return state['calls'] > 2

        winner, _scores, reason = scan_open_device(
            device, (115200, 9600, 19200), seconds=0.05, rounds=1, min_bytes=4,
            should_abort=abort_at_third_check)
        self.assertIsNone(winner)
        self.assertEqual('interrupted', reason)
        self.assertEqual(115200, device.settings['baudrate'])
        self.assertNotIn(9600, applied)
        self.assertNotIn(19200, applied)

    def test_abort_before_first_candidate_probes_nothing(self):
        device = FakeDevice(payload=b'')
        winner, _scores, reason = scan_open_device(
            device, (9600,), seconds=0.02, rounds=1, min_bytes=4,
            should_abort=lambda: True)
        self.assertIsNone(winner)
        self.assertEqual('interrupted', reason)
        self.assertEqual(115200, device.settings['baudrate'])
        self.assertEqual(b'', bytes(device.writes))


if __name__ == '__main__':
    unittest.main()
