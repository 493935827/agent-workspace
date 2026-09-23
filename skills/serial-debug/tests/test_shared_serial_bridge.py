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


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "shared_serial_bridge.py"
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

    def read(self, _size):
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


if __name__ == "__main__":
    unittest.main()
