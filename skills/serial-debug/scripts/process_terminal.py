#!/usr/bin/env python3
"""proc:// endpoint adapter: share a local process (cmd, PowerShell, ...) as a terminal.

The bridge owns the child process's stdin/stdout and exposes it through the
same TCP endpoints as a serial port. Two concrete adapters exist:

- ``ProcessTerminal`` (pipe mode): raw pipes plus a line discipline here.
  Input from all clients is assembled into lines (backspace erases pending
  characters), normalized to CRLF and forwarded to the child. Every completed
  line is handed to ``echo_hook`` so the service can mirror it to raw terminal
  clients and the session log — a piped shell echoes nothing by itself.
  Ctrl+C can only clear the pending line; a running command cannot be
  interrupted through a pipe.

- ``ConPtyTerminal`` (ConPTY mode, Windows 10 1809+): a real pseudo console.
  The child believes it is attached to a console, so it prints its own prompt
  and echoes keystrokes, line editing and history work natively, VT output
  flows through, and a Ctrl+C byte actually interrupts a running command.
  ``echo_hook`` is not needed: the child's own echo serves every client and
  the log, exactly like a serial device's echo.

``open_endpoint`` picks the adapter: ``proc_terminal='auto'`` (default) uses
ConPTY when available and falls back to pipes, ``'on'/'conpty'`` forces
ConPTY, ``'off'/'pipe'`` forces pipes.
"""

import ctypes
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


def resolve_spec(spec, proc_args=None, proc_cwd=None, interactive=False):
    """Turn a proc:// spec into (argv, env, init_line).

    Presets: proc://cmd, proc://powershell (prefers pwsh), proc://python.
    Anything else after the scheme is resolved as an executable on PATH.
    ``interactive=True`` selects the ConPTY-style argv: a true console child
    reads its commands from the console, and e.g. powershell.exe refuses
    ``-Command -`` (stdin-based command mode) when stdin is a console.
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
        if interactive:
            argv, env, init = _preset(
                [exe, '-NoProfile', '-NoLogo', '-NoExit'], extra, init=POWERSHELL_INIT)
        else:
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
    proc_mode = 'pipe'
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


# ---- ConPTY (Windows pseudo console, the "real terminal" mode) -------------

PROC_TERMINAL_DEFAULT_COLS = 120
PROC_TERMINAL_DEFAULT_ROWS = 30
PROC_TERMINAL_MODES = ('auto', 'on', 'off', 'conpty', 'pipe')

# Vendored Windows Terminal console host (MIT, mirrored from the pywinpty
# wheel). The in-box conhost ConPTY transport is broken on some builds (seen
# on Windows 11 24H2: conhost and the child attach, but the pipes stay
# silent), so the bundled conpty.dll + OpenConsole.exe pair is preferred and
# the kernel32 API is only the fallback.
CONPTY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'conpty')


def conpty_backend():
    """'conpty-local' (bundled conpty.dll), 'kernel32', or None."""
    if os.name != 'nt':
        return None
    try:
        return _conpty_api()['backend']
    except OSError:
        return None


def conpty_supported():
    """True when a ConPTY backend is available (Windows 10 1809+)."""
    return conpty_backend() is not None


_CONPTY_STATE = {}


def _conpty_api():
    """Load the ConPTY bindings once; raises OSError when unavailable."""
    cached = _CONPTY_STATE.get('api')
    if cached is not None:
        return cached
    if os.name != 'nt':
        raise OSError('ConPTY 仅在 Windows 10 1809+ 上可用')
    import ctypes
    from ctypes import wintypes

    class COORD(ctypes.Structure):
        _fields_ = [('X', ctypes.c_short), ('Y', ctypes.c_short)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR),
            ('lpDesktop', wintypes.LPWSTR), ('lpTitle', wintypes.LPWSTR),
            ('dwX', wintypes.DWORD), ('dwY', wintypes.DWORD),
            ('dwXSize', wintypes.DWORD), ('dwYSize', wintypes.DWORD),
            ('dwXCountChars', wintypes.DWORD), ('dwYCountChars', wintypes.DWORD),
            ('dwFillAttribute', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
            ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD),
            ('lpReserved2', ctypes.c_void_p),
            ('hStdInput', wintypes.HANDLE), ('hStdOutput', wintypes.HANDLE),
            ('hStdError', wintypes.HANDLE),
        ]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [('StartupInfo', STARTUPINFOW),
                    ('lpAttributeList', ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE),
                    ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)]

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [('nLength', wintypes.DWORD),
                    ('lpSecurityDescriptor', ctypes.c_void_p),
                    ('bInheritHandle', wintypes.BOOL)]

    class UNICODE_STRING(ctypes.Structure):
        _fields_ = [('Length', wintypes.USHORT), ('MaximumLength', wintypes.USHORT),
                    ('Buffer', wintypes.LPWSTR)]

    class OBJECT_ATTRIBUTES(ctypes.Structure):
        _fields_ = [('Length', wintypes.ULONG), ('RootDirectory', wintypes.HANDLE),
                    ('ObjectName', ctypes.POINTER(UNICODE_STRING)),
                    ('Attributes', wintypes.ULONG),
                    ('SecurityDescriptor', ctypes.c_void_p),
                    ('SecurityQualityOfService', ctypes.c_void_p)]

    class IO_STATUS_BLOCK(ctypes.Structure):
        class _Status(ctypes.Union):
            _fields_ = [('Status', ctypes.c_long), ('Pointer', ctypes.c_void_p)]
        _fields_ = [('status', _Status), ('information', ctypes.c_size_t)]

    ntdll = ctypes.WinDLL('ntdll')
    ntdll.RtlInitUnicodeString.argtypes = [
        ctypes.POINTER(UNICODE_STRING), wintypes.LPWSTR]
    ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
        ctypes.POINTER(OBJECT_ATTRIBUTES), ctypes.POINTER(IO_STATUS_BLOCK),
        ctypes.POINTER(wintypes.LARGE_INTEGER), wintypes.ULONG, wintypes.ULONG,
        wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG]
    ntdll.NtCreateFile.restype = ctypes.c_long
    ntdll.NtCreateNamedPipeFile.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
        ctypes.POINTER(OBJECT_ATTRIBUTES), ctypes.POINTER(IO_STATUS_BLOCK),
        wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG,
        wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG,
        wintypes.ULONG, ctypes.POINTER(wintypes.LARGE_INTEGER)]
    ntdll.NtCreateNamedPipeFile.restype = ctypes.c_long

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t)]
    kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel32.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CreateProcessW.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.PeekNamedPipe.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.PeekNamedPipe.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.DuplicateHandle.argtypes = [
        wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL,
        wintypes.DWORD]
    kernel32.DuplicateHandle.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    # Backend selection: the bundled conpty.dll + OpenConsole.exe pair first,
    # the in-box kernel32 API second. Both families return 0 on success and
    # store the console token through the same byref(c_void_p) shape.
    backend = None
    local_dll = None
    dll_path = os.path.join(CONPTY_DIR, 'conpty.dll')
    if os.path.isfile(dll_path):
        try:
            local_dll = ctypes.WinDLL(dll_path)
            local_dll.ConptyCreatePseudoConsole.argtypes = [
                COORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD,
                ctypes.c_void_p]
            local_dll.ConptyCreatePseudoConsole.restype = ctypes.c_int
            local_dll.ConptyResizePseudoConsole.argtypes = [ctypes.c_void_p, COORD]
            local_dll.ConptyResizePseudoConsole.restype = ctypes.c_int
            local_dll.ConptyClosePseudoConsole.argtypes = [ctypes.c_void_p]
            local_dll.ConptyClosePseudoConsole.restype = ctypes.c_int
            local_dll.ConptyShowHidePseudoConsole.argtypes = [ctypes.c_void_p, wintypes.BOOL]
            local_dll.ConptyShowHidePseudoConsole.restype = ctypes.c_int
            backend = 'conpty-local'
        except (OSError, AttributeError):
            local_dll = None
    if backend is None and hasattr(kernel32, 'CreatePseudoConsole'):
        kernel32.CreatePseudoConsole.argtypes = [
            COORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p)]
        kernel32.CreatePseudoConsole.restype = ctypes.HRESULT
        kernel32.ResizePseudoConsole.argtypes = [ctypes.c_void_p, COORD]
        kernel32.ResizePseudoConsole.restype = ctypes.HRESULT
        kernel32.ClosePseudoConsole.argtypes = [ctypes.c_void_p]
        kernel32.ClosePseudoConsole.restype = None
        backend = 'kernel32'
    if backend is None:
        raise OSError('本机没有可用的 ConPTY 后端（缺少捆绑 conpty.dll，且系统无 CreatePseudoConsole）')

    def conpty_create(size, h_input, h_output, flags, hpc_ref):
        if local_dll is not None:
            return local_dll.ConptyCreatePseudoConsole(size, h_input, h_output, flags, hpc_ref)
        return kernel32.CreatePseudoConsole(size, h_input, h_output, flags, hpc_ref)

    def conpty_resize(hpc, size):
        if local_dll is not None:
            return local_dll.ConptyResizePseudoConsole(hpc, size)
        return kernel32.ResizePseudoConsole(hpc, size)

    def conpty_close(hpc):
        if local_dll is not None:
            return local_dll.ConptyClosePseudoConsole(hpc)
        return kernel32.ClosePseudoConsole(hpc)

    def conpty_show_hide(hpc, show):
        if local_dll is not None:
            return local_dll.ConptyShowHidePseudoConsole(hpc, show)
        return None

    api = dict(
        ctypes=ctypes, wintypes=wintypes, kernel32=kernel32, ntdll=ntdll,
        backend=backend, create=conpty_create, resize=conpty_resize,
        close=conpty_close, show_hide=conpty_show_hide,
        COORD=COORD, STARTUPINFOEXW=STARTUPINFOEXW,
        PROCESS_INFORMATION=PROCESS_INFORMATION, SECURITY_ATTRIBUTES=SECURITY_ATTRIBUTES,
        UNICODE_STRING=UNICODE_STRING, OBJECT_ATTRIBUTES=OBJECT_ATTRIBUTES,
        IO_STATUS_BLOCK=IO_STATUS_BLOCK,
        PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE=0x00020016,
        EXTENDED_STARTUPINFO_PRESENT=0x00080000,
        CREATE_UNICODE_ENVIRONMENT=0x00000400,
        STARTF_USESTDHANDLES=0x00000100,
        GENERIC_READ=0x80000000, GENERIC_WRITE=0x40000000,
        FILE_SHARE_READ=0x00000001, FILE_SHARE_WRITE=0x00000002,
        OBJ_CASE_INSENSITIVE=0x00000040,
        FILE_OPEN=0x00000001, FILE_CREATE=0x00000002,
        FILE_SYNCHRONOUS_IO_NONALERT=0x00000020,
        FILE_NON_DIRECTORY_FILE=0x00000040,
        SYNCHRONIZE=0x00100000,
        INVALID_HANDLE_VALUE=wintypes.HANDLE(-1).value,
        DUPLICATE_SAME_ACCESS=0x00000002,
        STILL_ACTIVE=0x00000103, WAIT_OBJECT_0=0,
    )
    _CONPTY_STATE['api'] = api
    return api


def _env_block(ct, env):
    """Encode an environment mapping as a double-NUL-terminated UTF-16 block."""
    text = '\0'.join(f'{key}={value}' for key, value in env.items()) + '\0'
    return ct.create_unicode_buffer(text)


class ConPtyTerminal:
    """Duck-typed pyserial device around one child on a real pseudo console.

    Same service contract as ProcessTerminal (read() with a short timeout,
    write() returns the accepted length, get_settings/apply_settings, close),
    but there is no local line discipline: keystroke bytes go straight into
    the console input pipe and the child echoes itself, so ``echo_tx`` stays
    off. Ctrl+C and other control bytes are interpreted by the console host,
    which is what makes interrupting a running command possible.
    """

    is_process_terminal = True
    no_respawn = True
    echo_tx = False
    proc_mode = 'conpty'
    timeout = 0.05

    def __init__(self, spec, baud=115200, proc_args=None, proc_cwd=None,
                 cols=PROC_TERMINAL_DEFAULT_COLS, rows=PROC_TERMINAL_DEFAULT_ROWS):
        if not (isinstance(spec, str) and spec.lower().startswith(SCHEME)):
            raise SpecError(f'不是 proc:// 端点：{spec!r}')
        self.spec = spec
        self.baud = baud
        self.echo_hook = None
        self.exit_code = None
        argv, env, init, cwd = resolve_spec(spec, proc_args, proc_cwd, interactive=True)
        self._rx_cond = threading.Condition()
        self._rx = bytearray()
        self._eof = False
        self._closed = False
        self._hpc = None
        self._h_io_pipe = None        # our end of the transport pipe
        self._h_pty_input = None      # dup handed to the pty as hInput
        self._h_pty_output = None     # dup handed to the pty as hOutput
        self._h_process = None
        api = _conpty_api()
        self._api = api
        self._spawn(api, argv, env, cwd, cols, rows)
        self._pump_thread = threading.Thread(
            target=self._pump, daemon=True, name='proc-conpty-reader')
        self._pump_thread.start()
        if init:
            # Console cooked input treats CR as Enter; a trailing LF would
            # submit the same init line twice.
            self._write_input(init.rstrip(b'\r\n') + b'\r')

    # ---- child spawn -------------------------------------------------------

    def _spawn(self, api, argv, env, cwd, cols, rows):
        ct, wintypes, kernel32 = api['ctypes'], api['wintypes'], api['kernel32']

        def fail(message, *handles):
            for handle in handles:
                if handle is not None:
                    kernel32.CloseHandle(handle)
            raise OSError(message)

        # Transport: one byte-mode duplex named pipe built exactly like
        # winpty-rs/pywinpty do it — NtCreateNamedPipeFile with a kernel-
        # generated name, the twin end opened through RootDirectory. Plain
        # CreatePipe/CreateNamedPipeW shapes stay silent on modern ConPTY
        # hosts (the child never attaches), so mirror the proven shape.
        # conhost/OpenConsole receives duplicates of the client end as
        # hInput/hOutput; all bridge I/O happens on the server end.
        ntdll, nt = api['ntdll'], api
        iosb = nt['IO_STATUS_BLOCK']()
        dir_handle = wintypes.HANDLE()
        dir_name = ct.create_unicode_buffer('\\Device\\NamedPipe\\')
        dir_uni = nt['UNICODE_STRING']()
        ntdll.RtlInitUnicodeString(ctypes.byref(dir_uni), dir_name)
        dir_oa = nt['OBJECT_ATTRIBUTES'](
            Length=ct.sizeof(nt['OBJECT_ATTRIBUTES']), RootDirectory=None,
            ObjectName=ctypes.pointer(dir_uni), Attributes=nt['OBJ_CASE_INSENSITIVE'])
        status = ntdll.NtCreateFile(
            ctypes.byref(dir_handle), nt['SYNCHRONIZE'] | nt['GENERIC_READ'],
            ctypes.byref(dir_oa), ctypes.byref(iosb), None, 0,
            nt['FILE_SHARE_READ'] | nt['FILE_SHARE_WRITE'], nt['FILE_OPEN'],
            nt['FILE_SYNCHRONOUS_IO_NONALERT'], None, 0)
        if status < 0:
            raise OSError(f'打开 NamedPipe 目录失败（NTSTATUS 0x{status & 0xFFFFFFFF:08X}）')

        def make_pipe_end(root):
            uni = nt['UNICODE_STRING']()
            ntdll.RtlInitUnicodeString(ctypes.byref(uni), None)
            oa = nt['OBJECT_ATTRIBUTES'](
                Length=ct.sizeof(nt['OBJECT_ATTRIBUTES']), RootDirectory=root,
                ObjectName=ctypes.pointer(uni), Attributes=nt['OBJ_CASE_INSENSITIVE'])
            iosb_local = nt['IO_STATUS_BLOCK']()
            return oa, iosb_local, uni

        pipe_oa, pipe_iosb, pipe_uni = make_pipe_end(dir_handle)
        server = wintypes.HANDLE()
        timeout = wintypes.LARGE_INTEGER(-10_0000_0000)
        status = ntdll.NtCreateNamedPipeFile(
            ctypes.byref(server),
            nt['SYNCHRONIZE'] | nt['GENERIC_READ'] | nt['GENERIC_WRITE'],
            ctypes.byref(pipe_oa), ctypes.byref(pipe_iosb),
            nt['FILE_SHARE_READ'] | nt['FILE_SHARE_WRITE'], nt['FILE_CREATE'],
            0, 0, 0, 0, 1, 128 * 1024, 128 * 1024, ctypes.byref(timeout))
        if status < 0:
            kernel32.CloseHandle(dir_handle)
            raise OSError(f'创建终端传输管道失败（NTSTATUS 0x{status & 0xFFFFFFFF:08X}）')

        client_oa, client_iosb, client_uni = make_pipe_end(server)
        client = wintypes.HANDLE()
        status = ntdll.NtCreateFile(
            ctypes.byref(client),
            nt['SYNCHRONIZE'] | nt['GENERIC_READ'] | nt['GENERIC_WRITE'],
            ctypes.byref(client_oa), ctypes.byref(client_iosb), None, 0,
            nt['FILE_SHARE_READ'] | nt['FILE_SHARE_WRITE'], nt['FILE_OPEN'],
            nt['FILE_NON_DIRECTORY_FILE'], None, 0)
        kernel32.CloseHandle(dir_handle)
        if status < 0:
            fail(f'连接终端传输管道失败（NTSTATUS 0x{status & 0xFFFFFFFF:08X}）', server)
        pty_input = wintypes.HANDLE()
        pty_output = wintypes.HANDLE()
        me = kernel32.GetCurrentProcess()
        for source, target in ((client, pty_input), (client, pty_output)):
            if not kernel32.DuplicateHandle(me, source, me, ctypes.byref(target),
                                            0, True, api['DUPLICATE_SAME_ACCESS']):
                fail(f'复制终端管道句柄失败（WinError {ct.get_last_error()}）',
                     server, client)
        kernel32.CloseHandle(client)
        hpc = ct.c_void_p()
        hr = api['create'](
            api['COORD'](max(1, int(cols)), max(1, int(rows))),
            pty_input, pty_output, 0, ctypes.byref(hpc))
        if hr != 0:
            fail(f'CreatePseudoConsole 失败（status 0x{hr & 0xFFFFFFFF:08X}）；'
                 'ConPTY 模式需要 Windows 10 1809+', server, pty_input, pty_output)
        # The bundled console host can own a visible pseudo window; hide it so
        # a hidden bridge stays hidden. Best effort on both backends.
        try:
            api['show_hide'](hpc, False)
        except Exception:
            pass
        attribute_size = ct.c_size_t(0)
        kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(attribute_size))
        attribute = ct.create_string_buffer(attribute_size.value)
        if not kernel32.InitializeProcThreadAttributeList(
                attribute, 1, 0, ctypes.byref(attribute_size)):
            fail(f'InitializeProcThreadAttributeList 失败（WinError {ct.get_last_error()}）',
                 hpc, server, pty_input, pty_output)
        if not kernel32.UpdateProcThreadAttribute(
                attribute, 0, api['PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE'],
                hpc, ct.sizeof(hpc), None, None):
            # lpValue must be the HPCON token value itself, not a pointer to
            # it — passing byref(hpc) silently produces a console the child
            # never attaches to (it spawns its own conhost instead) and pty
            # pipes that stay forever silent. winpty-rs/pywinpty pass the
            # token directly and are the proven reference here.
            kernel32.DeleteProcThreadAttributeList(attribute)
            fail(f'UpdateProcThreadAttribute 失败（WinError {ct.get_last_error()}）',
                 hpc, server, pty_input, pty_output)
        startup = api['STARTUPINFOEXW']()
        startup.StartupInfo.cb = ct.sizeof(startup)
        # STARTF_USESTDHANDLES with all three hStd* left NULL is what Windows
        # Terminal itself does: without the flag CreateProcessW copies the
        # parent's std handle values into the child's process parameters
        # regardless of bInheritHandles, and the child then writes to the
        # parent's stdout instead of to the pseudoconsole.
        startup.StartupInfo.dwFlags = api['STARTF_USESTDHANDLES']
        # The kernel reads the attribute list through this field: without it
        # the child silently ignores the pseudoconsole and inherits our console.
        startup.lpAttributeList = ctypes.cast(attribute, ctypes.c_void_p)
        process = api['PROCESS_INFORMATION']()
        flags = api['EXTENDED_STARTUPINFO_PRESENT'] | api['CREATE_UNICODE_ENVIRONMENT']
        environment = None if env is None else _env_block(ct, env)
        command_line = ct.create_unicode_buffer(subprocess.list2cmdline(argv))
        cwd_buffer = ct.create_unicode_buffer(cwd) if cwd else None
        ok = kernel32.CreateProcessW(
            None, command_line, None, None, False, flags, environment, cwd_buffer,
            ctypes.byref(startup), ctypes.byref(process))
        kernel32.DeleteProcThreadAttributeList(attribute)
        if not ok:
            fail(f'无法启动终端进程 {argv[0]}（WinError {ct.get_last_error()}）',
                 hpc, server, pty_input, pty_output)
        kernel32.CloseHandle(process.hThread)
        self._hpc = hpc
        self._h_io_pipe = server
        self._h_pty_input = pty_input
        self._h_pty_output = pty_output
        self._h_process = process.hProcess

    # ---- child output side -------------------------------------------------

    def _pump(self):
        api = self._api
        ct, wintypes, kernel32 = api['ctypes'], api['wintypes'], api['kernel32']
        try:
            chunk = ct.create_string_buffer(4096)
            received = wintypes.DWORD()
            available = wintypes.DWORD()
            while True:
                # The child may exit while the pty host keeps the transport
                # pipe open (ConPTY holds a reference handle), so EOF cannot
                # rely on a pipe break alone: poll the process handle too.
                if self._h_process is not None and kernel32.WaitForSingleObject(
                        self._h_process, 0) == api['WAIT_OBJECT_0']:
                    available.value = 0
                    while kernel32.PeekNamedPipe(
                            self._h_io_pipe, None, 0, None,
                            ctypes.byref(available), None) and available.value:
                        received.value = 0
                        ok = kernel32.ReadFile(
                            self._h_io_pipe, chunk, len(chunk),
                            ctypes.byref(received), None)
                        if not ok or received.value == 0:
                            break
                        with self._rx_cond:
                            self._rx.extend(chunk.raw[:received.value])
                            self._rx_cond.notify_all()
                    break
                # Peek-then-read instead of a blocking ReadFile: a blocking
                # read on the transport pipe would ignore close() forever.
                available.value = 0
                if not kernel32.PeekNamedPipe(
                        self._h_io_pipe, None, 0, None,
                        ctypes.byref(available), None):
                    break
                if available.value == 0:
                    if self._closed:
                        break
                    time.sleep(0.005)
                    continue
                received.value = 0
                ok = kernel32.ReadFile(
                    self._h_io_pipe, chunk, len(chunk), ctypes.byref(received), None)
                if not ok or received.value == 0:
                    break
                data = chunk.raw[:received.value]
                with self._rx_cond:
                    self._rx.extend(data)
                    self._rx_cond.notify_all()
        finally:
            exit_code = self._collect_exit_code()
            with self._rx_cond:
                self.exit_code = exit_code
                self._eof = True
                self._rx_cond.notify_all()

    def _collect_exit_code(self):
        process = self._h_process
        if process is None:
            return None
        api = self._api
        wintypes = api['wintypes']
        api['kernel32'].WaitForSingleObject(process, 5000)
        code = wintypes.DWORD()
        if api['kernel32'].GetExitCodeProcess(process, ctypes.byref(code)):
            if code.value != api['STILL_ACTIVE']:
                return int(code.value)
        return None

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

    def _write_input(self, data):
        api = self._api
        wintypes = api['wintypes']
        total = len(data)
        offset = 0
        while offset < total:
            written = wintypes.DWORD()
            ok = api['kernel32'].WriteFile(
                self._h_io_pipe, bytes(data[offset:]), total - offset,
                ctypes.byref(written), None)
            if not ok or written.value == 0:
                raise OSError(
                    f'终端进程输入通道已断开（WinError {api["ctypes"].get_last_error()}）')
            offset += written.value

    def write(self, data):
        with self._rx_cond:
            if self._closed:
                raise OSError('终端已关闭')
            if self._eof:
                raise self._exit_error()
        self._write_input(data)
        return len(data)

    def resize(self, cols, rows):
        """Best-effort pseudo console resize (no control-plane wiring yet)."""
        hpc = self._hpc
        if hpc is None:
            return False
        return self._api['resize'](
            hpc, self._api['COORD'](int(cols), int(rows))) == 0

    # ---- settings/close, pyserial-shaped ----------------------------------

    def get_settings(self):
        return dict(port=self.spec, baudrate=self.baud, bytesize=8, stopbits=1,
                    parity='N', xonxoff=False, rtscts=False, dsrdtr=False)

    def apply_settings(self, settings):
        """No-op: a process terminal has no baud or line parameters to apply."""

    def close(self):
        if self._closed:
            return
        self._closed = True
        api = self._api
        hpc, self._hpc = self._hpc, None
        if hpc is not None:
            # Closing the pseudo console blocks while the console host drains
            # a wedged child; bound it so close() can still terminate the
            # child below.
            closer = threading.Thread(target=api['close'], args=(hpc,), daemon=True)
            closer.start()
            closer.join(2)
        kernel32 = api['kernel32']
        for attr in ('_h_pty_input', '_h_pty_output'):
            handle = getattr(self, attr)
            if handle is not None:
                kernel32.CloseHandle(handle)
                setattr(self, attr, None)
        self._pump_thread.join(timeout=1)
        # Only after the reader stopped may the transport handle be closed; a
        # live ReadFile on a closed handle is undefined on Windows. Closing it
        # also unblocks a reader that outlived the join deadline.
        pipe_handle, self._h_io_pipe = self._h_io_pipe, None
        if pipe_handle is not None:
            kernel32.CloseHandle(pipe_handle)
        process, self._h_process = self._h_process, None
        if process is not None:
            if kernel32.WaitForSingleObject(process, 1000) != api['WAIT_OBJECT_0']:
                kernel32.TerminateProcess(process, 1)
                kernel32.WaitForSingleObject(process, 1000)
            kernel32.CloseHandle(process)
        with self._rx_cond:
            self._rx_cond.notify_all()


def open_endpoint(port, baud=115200, proc_args=None, proc_cwd=None,
                  proc_terminal='auto', proc_cols=PROC_TERMINAL_DEFAULT_COLS,
                  proc_rows=PROC_TERMINAL_DEFAULT_ROWS):
    """Factory for the bridge: proc:// spawns a process, anything else is pyserial.

    ``proc_terminal`` selects the shell adapter: ``auto`` (default) uses ConPTY
    when the host provides it and falls back to pipes; ``on``/``conpty`` forces
    ConPTY and fails loudly on hosts without it; ``off``/``pipe`` forces the
    legacy pipe mode.
    """
    if isinstance(port, str) and port.lower().startswith(SCHEME):
        mode = (proc_terminal or 'auto').lower()
        if mode not in PROC_TERMINAL_MODES:
            raise ValueError(
                f"未知的 proc 终端模式 {proc_terminal!r}（支持 {'/'.join(PROC_TERMINAL_MODES)}）")
        use_conpty = mode in ('on', 'conpty') or (mode == 'auto' and conpty_supported())
        if use_conpty:
            try:
                return ConPtyTerminal(port, baud, proc_args=proc_args, proc_cwd=proc_cwd,
                                      cols=proc_cols, rows=proc_rows)
            except OSError:
                if mode != 'auto':
                    raise
                # auto mode owns the fallback: a broken ConPTY transport or a
                # wedged console host degrades to the legacy pipe session
                # instead of failing the whole bridge start.
                sys.stderr.write('[串口桥] ConPTY 终端创建失败，退回管道模式（行编辑）\n')
        return ProcessTerminal(port, baud, proc_args=proc_args, proc_cwd=proc_cwd)
    import serial
    return serial.serial_for_url(port, baudrate=baud, timeout=0.05, write_timeout=0.5)
