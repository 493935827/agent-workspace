# -*- coding: utf-8 -*-
"""proc:// process-terminal adapter: line discipline, echo, EOF semantics."""
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from process_terminal import ProcessTerminal, SpecError, open_endpoint, resolve_spec  # noqa: E402

# Deterministic child: banner, one ECHO per input line, exits on 'exit'.
CHILD = (
    "import sys\n"
    "sys.stdout.write('READY\\n'); sys.stdout.flush()\n"
    "for line in sys.stdin:\n"
    "    line = line.rstrip('\\r\\n')\n"
    "    if line == 'exit':\n"
    "        sys.stdout.write('BYE\\n'); sys.stdout.flush()\n"
    "        break\n"
    "    sys.stdout.write('ECHO:' + line + '\\n'); sys.stdout.flush()\n"
)


def make_terminal(spec=None, **kwargs):
    kwargs.setdefault('proc_args', ['-u', '-c', CHILD])
    return ProcessTerminal(spec or f'proc://{sys.executable}', **kwargs)


def read_until(terminal, marker, timeout=5.0):
    """Collect output until marker appears; returns (bytes, error_or_None)."""
    buf = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            buf.extend(terminal.read(4096))
        except OSError as exc:
            return bytes(buf), exc
        if marker in buf:
            return bytes(buf), None
        time.sleep(0.005)
    return bytes(buf), TimeoutError(f'missing {marker!r} in {bytes(buf)!r}')


class ProcessTerminalTests(unittest.TestCase):
    def setUp(self):
        self.term = make_terminal()
        self.addCleanup(self.term.close)
        data, error = read_until(self.term, b'READY')
        self.assertIsNone(error, f'startup banner failed: {data!r}')

    def test_echo_roundtrip_completes_on_cr(self):
        self.term.write(b'hello\r')
        data, error = read_until(self.term, b'ECHO:hello')
        self.assertIsNone(error, repr(data))

    def test_line_ends_may_arrive_in_separate_writes(self):
        # chardelay-style char-by-char writes must still assemble one line.
        for byte in b'abc':
            self.term.write(bytes([byte]))
            time.sleep(0.01)
        self.term.write(b'\r')
        data, error = read_until(self.term, b'ECHO:abc')
        self.assertIsNone(error, repr(data))

    def test_backspace_edits_pending_line(self):
        self.term.write(b'ab\bc\r')
        data, error = read_until(self.term, b'ECHO:ac')
        self.assertIsNone(error, repr(data))
        self.assertNotIn(b'ECHO:ab', data)

    def test_bare_enter_sends_empty_line(self):
        self.term.write(b'\r')
        data, error = read_until(self.term, b'ECHO:')
        self.assertIsNone(error, repr(data))

    def test_ctrl_c_clears_pending_line_only(self):
        self.term.write(b'abc\x03de\r')
        data, error = read_until(self.term, b'ECHO:de')
        self.assertIsNone(error, repr(data))
        self.assertNotIn(b'ECHO:abc', data)

    def test_echo_hook_receives_processed_line(self):
        seen = []
        self.term.echo_hook = seen.append
        self.term.write(b'hi\r')
        data, error = read_until(self.term, b'ECHO:hi')
        self.assertIsNone(error, repr(data))
        self.assertIn(b'hi\r\n', seen)

    def test_echo_hook_sees_ctrl_c_marker(self):
        seen = []
        self.term.echo_hook = seen.append
        self.term.write(b'abc\x03')
        self.assertTrue(any(b'^C' in item for item in seen))

    def test_eof_reports_exit_code_and_further_writes_fail(self):
        self.term.write(b'exit\r')
        data, error = read_until(self.term, b'BYE')
        self.assertIsNone(error, repr(data))
        with self.assertRaises(OSError) as ctx:
            while True:
                self.term.read(4096)
                time.sleep(0.005)
        self.assertIn('exit code', str(ctx.exception))
        with self.assertRaises(OSError):
            self.term.write(b'x\r')

    def test_settings_shape_is_pyserial_like(self):
        settings = self.term.get_settings()
        self.assertEqual(settings['port'], self.term.spec)
        self.assertEqual(settings['baudrate'], 115200)
        self.term.apply_settings({'baudrate': 9600})  # no-op, must not raise

    def test_close_terminates_child(self):
        child = make_terminal()
        read_until(child, b'READY')
        child.close()
        self.assertIsNotNone(child._proc.poll())
        with self.assertRaises(OSError):
            child.read(1)


class ProcessSpecTests(unittest.TestCase):
    def test_unknown_preset_fails_closed(self):
        with self.assertRaises(SpecError):
            resolve_spec('proc://no_such_executable_xyz')

    def test_empty_spec_fails_closed(self):
        with self.assertRaises(SpecError):
            resolve_spec('proc://')

    def test_powershell_preset_uses_command_dash(self):
        argv, env, init, cwd = resolve_spec('proc://powershell')
        self.assertIn('-Command', argv)
        self.assertEqual(argv[argv.index('-Command') + 1], '-')
        self.assertIn(b'OutputEncoding', init)

    def test_generic_exe_with_args(self):
        argv, env, init, cwd = resolve_spec(
            f'proc://{sys.executable}', proc_args='-u -c "print(1)"', proc_cwd=os.getcwd())
        self.assertTrue(argv[0].lower().endswith('python.exe'))
        self.assertEqual(argv[1:], ['-u', '-c', 'print(1)'])
        self.assertEqual(cwd, os.getcwd())

    def test_open_endpoint_delegates_non_proc_to_pyserial(self):
        device = open_endpoint('loop://', 9600)
        self.addCleanup(device.close)
        self.assertFalse(getattr(device, 'is_process_terminal', False))
        self.assertEqual(device.write(b'x'), 1)


@unittest.skipUnless(os.name == 'nt', 'cmd.exe preset needs Windows')
class CmdPresetSmokeTests(unittest.TestCase):
    def test_cmd_prompt_appears_and_survives_command(self):
        terminal = ProcessTerminal('proc://cmd')
        self.addCleanup(terminal.close)
        data, error = read_until(terminal, b'>', timeout=8)
        self.assertIsNone(error, repr(data))
        terminal.write(b'echo probe123\r')
        data, error = read_until(terminal, b'probe123', timeout=8)
        self.assertIsNone(error, repr(data))


if __name__ == '__main__':
    unittest.main()
