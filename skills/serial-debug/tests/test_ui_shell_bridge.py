"""GUI shell-bridge integration: 「共享终端桥」分组、启动 worker 与停止流程。

Covers the workbench-side of the proc:// terminal bridge:
- ShellBridgeStartWorker: attach-when-already-running, command line building
  (source mode), spawn failure, child exit reporting, readiness wait, pid file
  shared with the Windows controller, log-directory bootstrap.
- poll() sentinel routing for tab-less bridge workers: shell_start_result
  attaches a session, baud_notice must NOT retire a pending stop worker, and
  service_stop_result closes matching sessions with 终端桥 wording.
- open_shell_terminal_window spawns the connect client (with a console), also
  in the frozen-exe form.
- main() --bridge dual-mode dispatch into shared_serial_bridge.build_parser.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import queue
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from PySide6.QtWidgets import QApplication
    from serial_gui_qt import (Workbench, ShellBridgeStartWorker, ServiceStopWorker,
                                _BRIDGE_SERVICE, _clean_shell_preset)
    import serial_gui_qt
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

BRIDGE_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'shared_serial_bridge.py'


class FakeControlClient:
    """ServiceClient stand-in: `ready` decides whether `status` answers."""

    def __init__(self, ready=True):
        self.ready = ready
        self.closed = False

    def call(self, action, **params):
        if action != 'status' or not self.ready:
            raise OSError(f'control call refused: {action}')
        return {'instance': 'fake', 'connected': True}

    def close(self):
        self.closed = True


class FakeProc:
    pid = 4242

    def __init__(self, exit_code=None):
        self.exit_code = exit_code

    def poll(self):
        return self.exit_code


def free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class CleanPresetTests(unittest.TestCase):
    def test_strips_proc_prefix_case_insensitive(self):
        self.assertEqual(_clean_shell_preset('proc://powershell'), 'powershell')
        self.assertEqual(_clean_shell_preset('  PROC://cmd '), 'cmd')

    def test_plain_names_pass_through(self):
        self.assertEqual(_clean_shell_preset('python'), 'python')
        self.assertEqual(_clean_shell_preset('  '), '')


class ShellBridgeStartWorkerTests(unittest.TestCase):
    def make_worker(self, events, client_factory, **kwargs):
        return ShellBridgeStartWorker('cmd', 8890, 8891, events, client_factory, **kwargs)

    def result(self, events):
        w, kind, payload, _ = events.get_nowait()
        self.assertEqual(kind, 'shell_start_result')
        return payload

    def test_attaches_when_bridge_already_running(self):
        events = queue.Queue()
        worker = self.make_worker(events, lambda *a, **kw: FakeControlClient(ready=True))
        with mock.patch.object(serial_gui_qt.subprocess, 'Popen',
                               side_effect=AssertionError('must not spawn twice')):
            worker.run()
        ok, message, service = self.result(events)
        self.assertTrue(ok)
        self.assertIn('已在运行', message)
        self.assertEqual(service, dict(host='127.0.0.1', control=8891,
                                       device='proc://cmd', baud='115200'))

    def test_command_line_source_mode(self):
        events = queue.Queue()
        worker = self.make_worker(events, lambda *a, **kw: FakeControlClient(),
                                  cwd='D:/tmp', conpty=False, log_directory='X:/logs')
        command = worker._command()
        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith('shared_serial_bridge.py'))
        rest = command[2:]
        self.assertEqual(rest[0], 'bridge')
        for flag, value in (('--port', 'proc://cmd'), ('--host', '127.0.0.1'),
                            ('--tcp', '8890'), ('--control', '8891'),
                            ('--proc-cwd', 'D:/tmp'), ('--proc-conpty', 'off')):
            self.assertIn([flag, value], [rest[i:i + 2] for i in range(len(rest) - 1)],
                          f'{flag} {value} missing from {rest}')
        # ConPTY 默认（auto）不传开关；未设 cwd 也不传 --proc-cwd。
        plain = self.make_worker(events, lambda *a, **kw: FakeControlClient())._command()
        self.assertNotIn('--proc-conpty', plain)
        self.assertNotIn('--proc-cwd', plain)

    def test_spawn_failure_is_reported(self):
        events = queue.Queue()
        worker = self.make_worker(events, lambda *a, **kw: (_ for _ in ()).throw(OSError('refused')))
        with mock.patch.object(serial_gui_qt.subprocess, 'Popen', side_effect=OSError('no exec')):
            worker.run()
        ok, message, service = self.result(events)
        self.assertFalse(ok)
        self.assertIn('无法启动终端桥进程', message)
        self.assertIsNone(service)

    def test_child_exit_code_is_reported(self):
        events = queue.Queue()
        worker = self.make_worker(events, lambda *a, **kw: (_ for _ in ()).throw(OSError('refused')))
        with mock.patch.object(serial_gui_qt.subprocess, 'Popen', return_value=FakeProc(exit_code=3)):
            worker.run()
        ok, message, service = self.result(events)
        self.assertFalse(ok)
        self.assertIn('退出码 3', message)
        self.assertIsNone(service)

    def test_ready_success_records_pid_and_bootstraps_log_dir(self):
        events = queue.Queue()
        state = {'calls': 0}

        def factory(*a, **kw):
            state['calls'] += 1
            # First probe ("nothing running"), then the bridge comes up.
            if state['calls'] < 2:
                raise OSError('connection refused')
            return FakeControlClient(ready=True)

        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / 'nested' / 'logs'
            runtime = Path(tmp) / 'runtime'
            worker = self.make_worker(events, factory, log_directory=str(log_dir))
            with mock.patch.object(serial_gui_qt.subprocess, 'Popen',
                                   return_value=FakeProc()) as popen, \
                 mock.patch('serial_gui_qt._shell_runtime_dir', return_value=runtime):
                worker.run()
            ok, message, service = self.result(events)
            self.assertTrue(ok)
            self.assertIn('终端桥已启动', message)
            self.assertIn('PID 4242', message)
            self.assertIn('ConPTY 真终端', message)
            self.assertEqual(service['device'], 'proc://cmd')
            # 日志目录按需创建，pid 文件落在与 Windows 控制器共用的运行时目录。
            self.assertTrue(log_dir.is_dir())
            self.assertEqual((runtime / 'bridge_shell.pid').read_text(encoding='ascii'), '4242')
            self.assertEqual(popen.call_count, 1)


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class FakeSentinelWorker:
    """Hashable stand-in for a tab-less bridge worker (needs `.service`)."""

    def __init__(self, control=4242):
        self.service = dict(control=control)


class ShellBridgeGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def until(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        self.fail('workbench did not reach expected state')

    def records(self, window, index, tag):
        return [r['text'] for r in window.sessions[index]['records'] if r['tag'] == tag]

    def make_window(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = Workbench(persist=False,
                           settings_path=Path(directory.name) / 'settings.json',
                           port_provider=lambda: [])
        self.addCleanup(window.close)
        return window

    def emit_sentinel(self, window, worker, kind, payload):
        window.workers[worker] = _BRIDGE_SERVICE
        window.events.put((worker, kind, payload, serial_gui_qt.datetime.now()))
        window.poll()

    def test_baud_notice_keeps_stop_worker_alive(self):
        """停止流程的中间事件不能提前注销 worker，否则按钮永远禁用。"""
        window = self.make_window()
        worker = FakeSentinelWorker(control=4242)
        window._shell_stop_pending = True
        window.shell_stop.setEnabled(False)
        self.emit_sentinel(window, worker, 'baud_notice', 'Agent 正持有设备，先收回租约再停止桥…')
        self.assertIn(worker, window.workers)
        self.assertIn('收回租约', window.state.text())
        self.assertFalse(window.shell_stop.isEnabled())
        # 终态事件才注销 worker 并复位按钮。
        self.emit_sentinel(window, worker, 'service_stop_result',
                           (True, '终端桥已停止，shell 会话已结束（127.0.0.1:4242）'))
        self.assertNotIn(worker, window.workers)
        self.assertFalse(window._shell_stop_pending)
        self.assertTrue(window.shell_stop.isEnabled())

    def test_stop_shell_bridge_uses_terminal_wording_and_marks_sessions(self):
        from test_serial_service import FakeSerial
        from serial_service import SerialService

        holder = {}

        def factory(*_):
            holder['device'] = FakeSerial()
            return holder['device']

        service = SerialService(port='FAKE', tcp=0, control=0, serial_factory=factory).start()
        self.addCleanup(service.close)
        window = self.make_window()
        control = service.control_port
        index = window.create_session(f'service:127.0.0.1:{control}/proc://cmd')
        window.sessions[index]['service'] = dict(host='127.0.0.1', control=control,
                                                 device='proc://cmd', baud='115200')
        dialog = mock.Mock()
        dialog.getText.return_value = (str(control), True)
        real_box = serial_gui_qt.QMessageBox
        question = mock.Mock()
        question.StandardButton = real_box.StandardButton   # Yes | No 需要真实枚举
        question.question.return_value = real_box.StandardButton.Yes
        with mock.patch('serial_gui_qt.QInputDialog', dialog), \
             mock.patch('serial_gui_qt.QMessageBox', question):
            window.shell_stop.click()
        self.until(lambda: service.stop.is_set())
        self.until(lambda: any('终端桥已停止' in text and 'shell 会话已结束' in text
                               for text in self.records(window, index, 'SYS')))
        self.assertFalse(window._shell_stop_pending)
        self.assertTrue(window.shell_stop.isEnabled())

    def test_open_shell_terminal_window_spawns_connect_client(self):
        window = self.make_window()
        dialog = mock.Mock()
        dialog.getText.return_value = ('8890', True)
        with mock.patch('serial_gui_qt.QInputDialog', dialog), \
             mock.patch.object(serial_gui_qt.subprocess, 'Popen') as popen:
            window.shell_terminal.click()
        command = popen.call_args.args[0]
        self.assertTrue(command[1].endswith('shared_serial_bridge.py'))
        self.assertIn('connect', command)
        self.assertIn('8890', command)
        if os.name == 'nt':
            self.assertTrue(popen.call_args.kwargs.get('creationflags', 0)
                            & subprocess.CREATE_NEW_CONSOLE)

    def test_open_shell_terminal_window_frozen_wraps_cmd_console(self):
        """打包 exe 是 GUI 子系统进程：必须经 cmd 才能拿到新控制台。"""
        window = self.make_window()
        dialog = mock.Mock()
        dialog.getText.return_value = ('8890', True)
        with mock.patch('serial_gui_qt.QInputDialog', dialog), \
             mock.patch.object(sys, 'frozen', True, create=True), \
             mock.patch.object(serial_gui_qt.subprocess, 'Popen') as popen:
            window.shell_terminal.click()
        command = popen.call_args.args[0]
        self.assertEqual(command[:3], ['cmd', '/c', sys.executable])
        self.assertIn('--bridge', command)
        self.assertIn('connect', command)


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class ShellBridgeEndToEndTests(unittest.TestCase):
    """真桥端到端：GUI worker 拉起 proc://cmd 桥 → 附着会话 → 停止桥。"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def until(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.02)
        self.fail('workbench did not reach expected state')

    def test_start_worker_launches_bridge_and_attaches_session(self):
        import shutil
        import serial_service_client

        window = Workbench(persist=False,
                           settings_path=Path(tempfile.mkdtemp()) / 'settings.json',
                           port_provider=lambda: [])
        self.addCleanup(window.close)
        tcp, control = free_port(), free_port()
        runtime = Path(tempfile.mkdtemp()) / 'runtime'
        self.addCleanup(shutil.rmtree, runtime, ignore_errors=True)
        # pid 文件目录必须整段测试期间指向临时目录：worker 线程异步写 pid，
        # 早停 patch 会把真实 windows/.runtime/bridge_shell.pid 覆盖掉。
        runtime_patch = mock.patch('serial_gui_qt._shell_runtime_dir', return_value=runtime)
        runtime_patch.start()
        self.addCleanup(runtime_patch.stop)
        worker = ShellBridgeStartWorker('cmd', tcp, control, window.events,
                                        window.service_client_factory,
                                        log_directory=str(Path(tempfile.mkdtemp()) / 'logs'))
        window.workers[worker] = _BRIDGE_SERVICE
        worker.start()
        name = f'service:127.0.0.1:{control}/proc://cmd'
        self.until(lambda: any(s['port'] == name for s in window.sessions))
        index = next(i for i, s in enumerate(window.sessions) if s['port'] == name)
        self.until(lambda: window.sessions[index]['state'] == 'connected')
        self.assertTrue(any('终端桥已启动' in r['text']
                            for r in window.sessions[index]['records']))
        # pid 文件指向真实桥进程。
        pid = int((runtime / 'bridge_shell.pid').read_text(encoding='ascii'))
        self.assertGreater(pid, 0)
        # 停止桥：会话随后失联退役，worker 不再占用。
        client = serial_service_client.Client('127.0.0.1', control, timeout=5)
        try:
            instance = client.call('status').get('instance')
            client.call('service.stop', instance=instance)
        finally:
            client.close()
        self.until(lambda: not window.sessions[index].get('worker'))
        self.assertIn(window.sessions[index]['state'], ('error', 'disconnected'))


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class BridgeModeEntryTests(unittest.TestCase):
    def test_bridge_flag_dispatches_to_bridge_parser(self):
        import shared_serial_bridge

        seen = {}

        class FakeParser:
            def parse_args(self, extra):
                seen['extra'] = list(extra)
                return SimpleNamespace(func=lambda ns: 77)

        with mock.patch.object(sys, 'argv', ['serial_gui_qt.py', '--bridge',
                                             'connect', '--tcp', '8890']), \
             mock.patch('shared_serial_bridge.build_parser', return_value=FakeParser()):
            self.assertEqual(serial_gui_qt.main(), 77)
        self.assertEqual(seen['extra'], ['connect', '--tcp', '8890'])

    def test_bridge_mode_survives_windowed_null_stdio(self):
        """--windowed 打包无控制台时 PyInstaller 把 stdio 置 None：桥模块的
        print / stderr.write 不能因此 AttributeError（exe 实测崩过）。"""

        def crashes_on_stderr(_ns):
            sys.stderr.write('no console here\n')
            return 4

        class FakeParser:
            def parse_args(self, extra):
                return SimpleNamespace(func=crashes_on_stderr)

        stdout, stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = None
        try:
            with mock.patch.object(sys, 'argv', ['serial_gui_qt.py', '--bridge',
                                                 'autobaud', '--control', '1']), \
                 mock.patch('shared_serial_bridge.build_parser', return_value=FakeParser()):
                self.assertEqual(serial_gui_qt.main(), 4)
        finally:
            sys.stdout.close()
            sys.stderr.close()
            sys.stdout, sys.stderr = stdout, stderr

    def test_unknown_flag_without_bridge_still_errors(self):
        with mock.patch.object(sys, 'argv', ['serial_gui_qt.py', '--wat']), \
             self.assertRaises(SystemExit):
            serial_gui_qt.main()


if __name__ == '__main__':
    unittest.main()
