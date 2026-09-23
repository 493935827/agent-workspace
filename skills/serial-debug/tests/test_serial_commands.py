import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from serial_commands import parse_command, format_command, StreamBuffer


class CommandTests(unittest.TestCase):
    def test_generated_command_roundtrips_quotes_unicode_newlines_and_booleans(self):
        params = dict(data='中文 "quote" \\ path\nnext', newline='crlf', encoding='utf-8')
        self.assertEqual(parse_command(format_command('send', params)), ('send', params))
        self.assertEqual(parse_command('serial.configure {"rtscts":false,"baudrate":57600}'),
                         ('serial.configure', dict(rtscts=False, baudrate=57600)))

    def test_incremental_utf8_and_hex_keep_same_bounded_raw_bytes(self):
        view = StreamBuffer(capacity=8)
        self.assertEqual(view.append('rx', b'\xe4\xb8'), '')
        self.assertEqual(view.append('rx', b'\xad'), '中')
        self.assertEqual(view.render('hex'), '[RX] E4 B8 AD')
        view.append('rx', b'0123456789')
        self.assertEqual(view.dropped, 5)
        self.assertEqual(view.raw_size, 8)
        view.clear()
        self.assertEqual(view.render('text'), '')


if __name__ == '__main__':
    unittest.main()
