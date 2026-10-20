import contextlib
import importlib.util
import io
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "shared_serial_bridge.py"
# Normally inherited from test_detect_serial_baud (alphabetically first);
# declared here so this file also runs standalone.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import serial_service_client  # noqa: E402

SPEC = importlib.util.spec_from_file_location("shared_serial_bridge", SCRIPT)
BRIDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BRIDGE)


def free_tcp_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def connect_with_retry(port, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=0.2)
            sock.settimeout(2)
            return sock
        except OSError:
            time.sleep(0.02)
    raise AssertionError("bridge did not start listening")


class FakePort:
    def __init__(self, release, payload=None, fail_after_payload=False):
        self.release = release
        self.payload = payload
        self.fail_after_payload = fail_after_payload
        self.payload_sent = False
        self.closed = False
        self.writes = bytearray()
        self.dtr = True
        self._parked = False
        self._parker = threading.Event()

    def park(self):
        """Silence the port forever: read() blocks and releases the GIL.

        The bridge thread outlives this test (daemon, stopped only at process
        exit). Without parking, its leaked service reader hot-loops on a
        released port and starves every later test in the same process.
        """
        self._parked = True

    def read(self, _size):
        if self._parked:
            self._parker.wait()
            return b""
        if self.closed:
            raise OSError("port closed")
        if not self.release.wait(0.01):
            return b""
        if not self.payload_sent and self.payload is not None:
            self.payload_sent = True
            return self.payload
        if self.fail_after_payload:
            raise OSError("simulated USB disconnect")
        return b""

    def write(self, data):
        if self.closed:
            raise OSError("port closed")
        self.writes.extend(data)
        return len(data)

    def close(self):
        self.closed = True

    def reset_input_buffer(self):
        pass


class SerialFactory:
    def __init__(self, ports):
        self.ports = list(ports)
        self.created = threading.Event()

    def __call__(self, *_args, **_kwargs):
        if not self.ports:
            raise OSError("port unavailable")
        port = self.ports.pop(0)
        if not self.ports:
            self.created.set()
        return port


class SharedSerialBridgeTests(unittest.TestCase):
    def test_bridge_recovers_after_serial_disconnect(self):
        first_release = threading.Event()
        second_release = threading.Event()
        first = FakePort(first_release, b"before\r\n", fail_after_payload=True)
        second = FakePort(second_release, b"after\r\n")
        factory = SerialFactory([first, second])
        original_open_serial = BRIDGE.open_serial
        BRIDGE.open_serial = factory
        tcp_port = free_tcp_port()

        try:
            args = SimpleNamespace(
                port="FAKE1",
                baud=115200,
                host="127.0.0.1",
                tcp=tcp_port,
                chardelay=0,
                log=os.devnull,
            )
            thread = threading.Thread(target=BRIDGE.run_bridge, args=(args,), daemon=True)
            thread.start()

            old_client = connect_with_retry(tcp_port)
            try:
                old_client.sendall(b"ready")
                deadline = time.time() + 2
                while bytes(first.writes) != b"ready" and time.time() < deadline:
                    time.sleep(0.01)
                self.assertEqual(bytes(first.writes), b"ready")
                first_release.set()
                self.assertEqual(old_client.recv(4096), b"before\r\n")
                self.assertTrue(factory.created.wait(2), "serial port was not reopened")
                self.assertEqual(old_client.recv(4096), b"", "stale client stayed connected")
            finally:
                old_client.close()

            new_client = connect_with_retry(tcp_port)
            try:
                new_client.sendall(b"ready2")
                deadline = time.time() + 2
                while bytes(second.writes) != b"ready2" and time.time() < deadline:
                    time.sleep(0.01)
                self.assertEqual(bytes(second.writes), b"ready2")
                second.writes.clear()
                second_release.set()
                self.assertEqual(new_client.recv(4096), b"after\r\n")
                new_client.sendall(b"help\r")

                deadline = time.time() + 2
                while bytes(second.writes) != b"help\r" and time.time() < deadline:
                    time.sleep(0.01)
                self.assertEqual(bytes(second.writes), b"help\r")
            finally:
                new_client.close()
        finally:
            BRIDGE.open_serial = original_open_serial
            first.park()
            second.park()

    def test_recv_until_idle_reports_peer_disconnect(self):
        left, right = socket.socketpair()
        try:
            right.sendall(b"partial")
            right.close()
            data, disconnected = BRIDGE.receive_until_idle(left, 0.05, 0.5)
            self.assertEqual(data, b"partial")
            self.assertTrue(disconnected)
        finally:
            left.close()

    def test_interactive_client_reconnects_without_traceback(self):
        tcp_port = free_tcp_port()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", tcp_port))
        listener.listen(2)
        listener.settimeout(3)
        first_connected = threading.Event()
        second_connected = threading.Event()
        release_second = threading.Event()

        def serve_two_connections():
            first, _ = listener.accept()
            first_connected.set()
            first.close()
            second, _ = listener.accept()
            second_connected.set()
            release_second.wait(2)
            second.close()
            listener.close()

        server = threading.Thread(target=serve_two_connections, daemon=True)
        server.start()
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), "connect", "--tcp", str(tcp_port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertTrue(first_connected.wait(2), "client did not make its first connection")
            self.assertTrue(second_connected.wait(3), "client did not reconnect")
            self.assertIsNone(process.poll(), "interactive client exited after disconnect")
        finally:
            release_second.set()
            process.terminate()
            _, stderr = process.communicate(timeout=3)
        self.assertNotIn("Traceback", stderr)

    def test_send_returns_nonzero_when_bridge_disconnects_early(self):
        tcp_port = free_tcp_port()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", tcp_port))
        listener.listen(1)

        def close_after_command():
            connection, _ = listener.accept()
            connection.recv(4096)
            connection.close()
            listener.close()

        server = threading.Thread(target=close_after_command, daemon=True)
        server.start()
        args = SimpleNamespace(
            data="help",
            newline=True,
            line_ending="cr",
            host="127.0.0.1",
            tcp=tcp_port,
            encoding="utf-8",
            idle=0.05,
            max_wait=0.5,
            socket_timeout=0.05,
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = BRIDGE.run_send(args)
        self.assertEqual(result, 2)
        self.assertIn("连接已经断开", stderr.getvalue())


class RunAutoBaudExitCodeTests(unittest.TestCase):
    """The autobaud CLI must keep its documented exit-code contract at the
    failure seams: a dead control connection is 4 (bridge unreachable), not
    the generic OSError exit 2 ('no signal') that automation would misread;
    and a queued scan that never started must time out as 5, not fall through
    to a bogus 'unchanged' success."""

    @staticmethod
    def _args(**overrides):
        base = dict(host="127.0.0.1", control=8889, mode="passive", bauds=None,
                    seconds=0.5, rounds=1, min_bytes=None, wait=30.0)
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_control_channel_death_maps_to_exit_4(self):
        class DyingClient:
            def __init__(self, *_args, **_kwargs):
                self.calls = 0

            def call(self, action, **_params):
                self.calls += 1
                if action == "status":
                    return dict(connected=True, config={"baudrate": 115200})
                if self.calls == 2:  # the 'before' snapshot
                    return dict(scanning=False, requested=False,
                                last_reason=None, last_change=None)
                raise OSError("connection reset")

            def close(self):
                pass

        with mock.patch.object(serial_service_client, "Client", DyingClient):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = BRIDGE.run_autobaud(self._args())
        self.assertEqual(4, result)
        self.assertIn("断开", stderr.getvalue())

    def test_never_started_scan_times_out_with_exit_5(self):
        class StuckClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def call(self, action, **_params):
                if action == "status":
                    return dict(connected=True, config={"baudrate": 115200})
                # requested but never picked up: the device vanished after
                # serial.autobaud queued the request.
                return dict(scanning=False, requested=True,
                            last_reason=None, last_change=None)

            def close(self):
                pass

        with mock.patch.object(serial_service_client, "Client", StuckClient):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = BRIDGE.run_autobaud(self._args(wait=0.05))
        self.assertEqual(5, result)

    def test_completed_scan_still_reports_unchanged_exit_0(self):
        class DoneClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def call(self, action, **_params):
                if action == "status":
                    return dict(connected=True, config={"baudrate": 115200})
                return dict(scanning=False, requested=False,
                            last_reason=None, last_change=None)

            def close(self):
                pass

        with mock.patch.object(serial_service_client, "Client", DoneClient):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = BRIDGE.run_autobaud(self._args())
        self.assertEqual(0, result)
        self.assertIn("autobaud_result: unchanged baud=115200", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
