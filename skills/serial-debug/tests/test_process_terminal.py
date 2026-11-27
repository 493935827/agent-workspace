# -*- coding: utf-8 -*-
"""proc:// process-terminal adapter: line discipline, echo, EOF semantics."""
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from process_terminal import (  # noqa: E402
    ConPtyTerminal, ProcessTerminal, SpecError, conpty_supported, open_endpoint,
    resolve_spec)

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

    def test_powershell_preset_interactive_drops_command_dash(self):
        # A true console child reads from the console; powershell.exe refuses
        # "-Command -" when stdin is a console, so ConPTY mode must use -NoExit.
        argv, env, init, cwd = resolve_spec('proc://powershell', interactive=True)
        self.assertIn('-NoExit', argv)
        self.assertNotIn('-Command', argv)
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


def needs_conpty(testcase):
    """Class/method decorator guard: real ConPTY tests need Windows 10 1809+."""
    return unittest.skipUnless(
        os.name == 'nt' and conpty_supported(),
        'ConPTY needs Windows 10 1809+')(testcase)


@needs_conpty
class ConPtyTerminalTests(unittest.TestCase):
    """The true-terminal contract: child echoes itself, Ctrl+C interrupts."""

    def make_terminal(self, **kwargs):
        terminal = ConPtyTerminal('proc://cmd', **kwargs)
        self.addCleanup(terminal.close)
        return terminal

    def test_per_character_echo_and_true_prompt(self):
        # Pipe mode shows nothing until Enter; ConPTY echoes every keystroke
        # through the console host, so even 'echo' typed one char at a time
        # is visible before the command runs.
        terminal = self.make_terminal()
        data, error = read_until(terminal, b'>', timeout=10)
        self.assertIsNone(error, repr(data))
        for byte in b'echo probe42':
            terminal.write(bytes([byte]))
            time.sleep(0.005)
        terminal.write(b'\r')
        data, error = read_until(terminal, b'probe42', timeout=10)
        self.assertIsNone(error, repr(data))

    def test_ctrl_c_interrupts_running_command(self):
        terminal = self.make_terminal()
        data, error = read_until(terminal, b'>', timeout=10)
        self.assertIsNone(error, repr(data))
        terminal.write(b'ping -n 30 127.0.0.1\r')
        data, error = read_until(terminal, b'TTL', timeout=10)
        self.assertIsNone(error, f'ping 没有开始输出: {data!r}')
        terminal.write(b'\x03')
        # The decisive signal: the prompt comes back while ping would still
        # be running (30 replies at 1s intervals). Pipe mode cannot do this.
        data, error = read_until(terminal, b'>', timeout=10)
        self.assertIsNone(error, f'Ctrl+C 后提示符未返回: {data!r}')

    def test_exit_code_reported_on_eof(self):
        terminal = self.make_terminal()
        data, error = read_until(terminal, b'>', timeout=10)
        self.assertIsNone(error, repr(data))
        terminal.write(b'exit 7\r')
        deadline = time.monotonic() + 10
        with self.assertRaises(OSError) as ctx:
            while time.monotonic() < deadline:
                terminal.read(4096)
                time.sleep(0.005)
            raise AssertionError('EOF not reported within 10s')
        self.assertIn('exit code=7', str(ctx.exception))
        with self.assertRaises(OSError):
            terminal.write(b'x\r')

    def test_close_shuts_down_child_and_stream(self):
        terminal = self.make_terminal()
        data, error = read_until(terminal, b'>', timeout=10)
        self.assertIsNone(error, repr(data))
        terminal.close()
        with self.assertRaises(OSError):
            terminal.read(1)
        with self.assertRaises(OSError):
            terminal.write(b'x\r')

    def test_resize_succeeds_on_live_console(self):
        terminal = self.make_terminal()
        data, error = read_until(terminal, b'>', timeout=10)
        self.assertIsNone(error, repr(data))
        self.assertTrue(terminal.resize(100, 25))


@needs_conpty
class ConPtyEndToEndBridgeTests(unittest.TestCase):
    """Full path: TCP client -> service -> ConPTY -> cmd.exe -> back."""

    BRIDGE_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'shared_serial_bridge.py'

    @staticmethod
    def free_tcp_port():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    def test_send_expect_roundtrip_through_conpty_cmd(self):
        import tempfile

        import serial_service_client

        tcp = self.free_tcp_port()
        control = self.free_tcp_port()
        # ignore_cleanup_errors：桥停后 ConPTY 子进程/OpenConsole 可能迟几毫秒才
        # 松开日志句柄，满载跑套件时 rmtree 偶发 PermissionError（Windows 会
        # 清理 %TEMP%，不能让清理竞态推翻通过的功能断言）。
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as log_dir:
            bridge = subprocess.Popen(
                [sys.executable, str(self.BRIDGE_SCRIPT), 'bridge',
                 '--port', 'proc://cmd', '--tcp', str(tcp), '--control', str(control),
                 '--proc-conpty', 'on',
                 '--log', str(Path(log_dir) / 'proc_e2e.log')],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.time() + 10
                while True:
                    try:
                        probe = socket.create_connection(('127.0.0.1', tcp), timeout=0.3)
                        probe.close()
                        break
                    except OSError:
                        if time.time() > deadline or bridge.poll() is not None:
                            self.fail('bridge did not start listening')
                        time.sleep(0.05)
                sent = subprocess.run(
                    [sys.executable, str(self.BRIDGE_SCRIPT), 'send', 'echo probe77',
                     '--host', '127.0.0.1', '--tcp', str(tcp),
                     '--newline', '--line-ending', 'cr',
                     '--expect', 'probe77', '--expect-timeout', '15'],
                    capture_output=True, timeout=30)
                self.assertEqual(sent.returncode, 0,
                                 f'send failed: rc={sent.returncode} '
                                 f'out={sent.stdout!r} err={sent.stderr!r}')
                self.assertIn(b'probe77', sent.stdout)
            finally:
                client = None
                try:
                    client = serial_service_client.Client('127.0.0.1', control, timeout=5)
                    client.call('service.stop')
                except Exception:
                    pass
                if client is not None:
                    client.close()
                try:
                    bridge.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    bridge.kill()
                    bridge.wait(timeout=3)


class ProcTerminalModeTests(unittest.TestCase):
    def test_open_endpoint_pipe_mode_forces_legacy_adapter(self):
        terminal = open_endpoint('proc://cmd', proc_terminal='pipe')
        self.addCleanup(terminal.close)
        self.assertIsInstance(terminal, ProcessTerminal)
        self.assertEqual(terminal.proc_mode, 'pipe')

    def test_open_endpoint_off_alias_forces_pipe(self):
        terminal = open_endpoint('proc://cmd', proc_terminal='off')
        self.addCleanup(terminal.close)
        self.assertIsInstance(terminal, ProcessTerminal)

    def test_open_endpoint_unknown_mode_fails_closed(self):
        with self.assertRaises(ValueError):
            open_endpoint('proc://cmd', proc_terminal='turbo')

    @needs_conpty
    def test_open_endpoint_forced_conpty(self):
        terminal = open_endpoint('proc://cmd', proc_terminal='on')
        self.addCleanup(terminal.close)
        self.assertIsInstance(terminal, ConPtyTerminal)
        self.assertEqual(terminal.proc_mode, 'conpty')

    def test_open_endpoint_auto_on_non_windows_is_pipe(self):
        if os.name == 'nt' and conpty_supported():
            self.skipTest('auto falls back to pipe only off-Windows')
        terminal = open_endpoint('proc://cmd')
        self.addCleanup(terminal.close)
        self.assertIsInstance(terminal, ProcessTerminal)

    def test_conpty_unsupported_off_windows_raises(self):
        if os.name == 'nt' and conpty_supported():
            self.skipTest('forced ConPTY works on this host')
        with self.assertRaises(OSError):
            open_endpoint('proc://cmd', proc_terminal='on')


if __name__ == '__main__':
    unittest.main()
