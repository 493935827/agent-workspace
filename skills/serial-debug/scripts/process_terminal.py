#!/usr/bin/env python3
"""proc:// endpoint adapter: share a local process (cmd, PowerShell, ...) as a terminal.

The bridge owns the child process's stdin/stdout and exposes it through the
same TCP endpoints as a serial port. Line discipline lives here: input from
all clients is assembled into lines (backspace erases pending characters),
normalized to CRLF and forwarded to the child. Every completed line is also
handed to ``echo_hook`` so the service can mirror it to raw terminal clients
and the session log — a piped shell echoes nothing by itself.
"""

import os
import shlex
import shutil
import subprocess
import sys
import threading
import time

SCHEME = 'proc://'
UTF8_ENV = {'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
POWERSHELL_INIT = b'[Console]::OutputEncoding=[System.Text.Encoding]::UTF8\r\n'


class SpecError(ValueError):
    """Raised when a proc:// endpoint spec cannot be resolved."""


def split_args(text):
    """Split a command-line tail into tokens, dropping token-level quotes.

    Already-listed arguments (API callers, tests) pass through unchanged.
    """
    if text is None:
        return []
    if isinstance(text, (list, tuple)):
        return [str(token) for token in text]
    tokens = shlex.split(str(text), posix=False)
    return [token[1:-1] if len(token) > 1 and token[0] == token[-1] and token[0] in ('"', "'")
            else token for token in tokens]


def _preset(argv_prefix, extra_args, env=None, init=b''):
    argv = list(argv_prefix) + list(extra_args or [])
    environment = None if env is None else {**os.environ, **env}
    return argv, environment, init


def resolve_spec(spec, proc_args=None, proc_cwd=None):
    """Turn a proc:// spec into (argv, env, init_line).

    Presets: proc://cmd, proc://powershell (prefers pwsh), proc://python.
    Anything else after the scheme is resolved as an executable on PATH.
    """
    name = spec[len(SCHEME):].strip()
    extra = split_args(proc_args)
    if not name:
        raise SpecError('proc:// 后面需要一个预设名或可执行文件，例如 proc://powershell')
    lowered = name.lower()
    if lowered == 'cmd':
        argv, env, init = _preset(['cmd.exe', '/Q', '/K'], extra, init=b'\r\n')
    elif lowered in ('powershell', 'pwsh'):
        exe = shutil.which('pwsh') or shutil.which('powershell')
        if exe is None:
            raise SpecError('未找到 PowerShell（powershell.exe / pwsh.exe）')
        argv, env, init = _preset(
            [exe, '-NoProfile', '-NoLogo', '-Command', '-'], extra, init=POWERSHELL_INIT)
    elif lowered == 'python':
        argv, env, init = _preset([sys.executable, '-u', '-i'], extra, env=UTF8_ENV)
    else:
        exe = name if os.path.isfile(name) else shutil.which(name)
        if exe is None:
            raise SpecError(f'未找到可执行文件：{name}')
        argv, env, init = _preset([exe], extra)
    return argv, env, init, proc_cwd or None


class ProcessTerminal:
    """Duck-typed pyserial device around one child process.

    Service contract: read() with a short timeout, write() returning the
    accepted length, get_settings()/apply_settings(), close(). Class flags
    steer the service: echo_tx wires echo_hook, no_respawn stops the
    reconnect loop after the child exits (the shell session state is gone,
    silently respawning would pretend otherwise).
    """

    is_process_terminal = True
    no_respawn = True
    echo_tx = True
    timeout = 0.05

    def __init__(self, spec, baud=115200, proc_args=None, proc_cwd=None):
        if not (isinstance(spec, str) and spec.lower().startswith(SCHEME)):
            raise SpecError(f'不是 proc:// 端点：{spec!r}')
        self.spec = spec
        self.baud = baud
        self.echo_hook = None
        self.exit_code = None
        argv, env, init, cwd = resolve_spec(spec, proc_args, proc_cwd)
        self._rx_cond = threading.Condition()
        self._rx = bytearray()
        self._eof = False
        self._closed = False
        self._input_lock = threading.Lock()
        self._input = bytearray()
        try:
            self._proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, env=env, cwd=cwd)
        except OSError as exc:
            raise OSError(f'无法启动终端进程 {argv[0]}：{exc}') from exc
        self._pump_thread = threading.Thread(
            target=self._pump, daemon=True, name='proc-reader')
        self._pump_thread.start()
        if init:
            self._write_stdin(init)

    # ---- child output side -------------------------------------------------

    def _pump(self):
        try:
            fd = self._proc.stdout.fileno()
            while True:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                with self._rx_cond:
                    self._rx.extend(chunk)
                    self._rx_cond.notify_all()
        finally:
            try:
                self._proc.wait(timeout=2)
            except Exception:
                pass
            self.exit_code = self._proc.poll()
            with self._rx_cond:
                self._eof = True
                self._rx_cond.notify_all()

    def _exit_error(self):
        code = '未知' if self.exit_code is None else str(self.exit_code)
        return OSError(f'终端进程已退出 (exit code={code})；用 serial.open 重新拉起')

    def read(self, size=1):
        with self._rx_cond:
            deadline = time.monotonic() + self.timeout
            while not self._rx:
                if self._closed:
                    raise OSError('终端已关闭')
                if self._eof:
                    raise self._exit_error()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return b''
                self._rx_cond.wait(remaining)
            data = bytes(self._rx[:size])
            del self._rx[:size]
            return data

    # ---- child input side --------------------------------------------------

    def _write_stdin(self, data):
        try:
            self._proc.stdin.write(data)
            self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise OSError(f'终端进程输入通道已断开：{exc}') from exc

    def _emit_line(self, line):
        payload = line + b'\r\n'
        self._write_stdin(payload)
        if self.echo_hook is not None:
            try:
                self.echo_hook(payload)
            except Exception:
                pass

    def write(self, data):
        if self._closed:
            raise OSError('终端已关闭')
        with self._input_lock:
            self._input.extend(data)
            pending = self._input
            index = 0
            while index < len(pending):
                byte = pending[index]
                if byte in (0x0D, 0x0A):        # CR or LF completes the line
                    line = bytes(pending[:index])
                    del pending[:index + 1]
                    index = 0
                    self._emit_line(line)
                elif byte in (0x08, 0x7F):      # backspace erases a pending char
                    del pending[index]
                    if index > 0:
                        del pending[index - 1]
                        index -= 1
                elif byte == 0x03:              # Ctrl+C clears the pending line
                    del pending[:index + 1]
                    index = 0
                    if self.echo_hook is not None:
                        try:
                            self.echo_hook(b'^C\r\n')
                        except Exception:
                            pass
                elif byte == 0x1B:              # escape: drop, pipe shells cannot honor it
                    del pending[index]
                else:
                    index += 1
        return len(data)

    # ---- settings/close, pyserial-shaped ----------------------------------

    def get_settings(self):
        return dict(port=self.spec, baudrate=self.baud, bytesize=8, stopbits=1,
                    parity='N', xonxoff=False, rtscts=False, dsrdtr=False)

    def apply_settings(self, settings):
        """No-op: a piped process has no baud or line parameters to apply."""

    def close(self):
        if self._closed:
            return
        self._closed = True
        proc = getattr(self, '_proc', None)
        if proc is not None:
            for stream in (proc.stdin, proc.stdout):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                except OSError:
                    pass
        with self._rx_cond:
            self._rx_cond.notify_all()
        self._pump_thread.join(timeout=1)


def open_endpoint(port, baud=115200, proc_args=None, proc_cwd=None):
    """Factory for the bridge: proc:// spawns a process, anything else is pyserial."""
    if isinstance(port, str) and port.lower().startswith(SCHEME):
        return ProcessTerminal(port, baud, proc_args=proc_args, proc_cwd=proc_cwd)
    import serial
    return serial.serial_for_url(port, baudrate=baud, timeout=0.05, write_timeout=0.5)
