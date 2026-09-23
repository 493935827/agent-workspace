"""Qt-free client. Calls are serialized; observations use a separate connection."""
import queue
import socket
import threading
import uuid

from serial_protocol import VERSION, ActionError, encode, read_message


class RemoteError(ActionError):
    pass


class Client:
    def __init__(self, host='127.0.0.1', port=8889, timeout=5):
        self.host, self.port, self.timeout = host, port, timeout
        self.socket = socket.create_connection((host, port), timeout)
        self.stream = self.socket.makefile('rb')
        self.lock = threading.Lock()
        self.events = queue.Queue(1024)
        self.event_socket = None
        self.closed = threading.Event()
        self.gaps = 0
        try:
            self.call('hello')
        except Exception:
            self.close()
            raise

    def call(self, action, token=None, **params):
        with self.lock:
            request_id = uuid.uuid4().hex
            self.socket.sendall(encode(dict(version=VERSION, id=request_id, action=action,
                                            params=params, token=token)))
            response = read_message(self.stream)
            if response.get('id') != request_id:
                raise RemoteError('protocol', 'Response ID mismatch; outcome unknown')
            if not response.get('ok'):
                error = response['error']
                raise RemoteError(error['code'], error['message'])
            return response['result']

    def subscribe(self):
        if self.event_socket is not None:
            return
        sock = socket.create_connection((self.host, self.port), self.timeout)
        sock.sendall(encode(dict(version=VERSION, id='subscribe', action='subscribe', params={})))
        stream = sock.makefile('rb')
        response = read_message(stream)
        if not response.get('ok'):
            stream.close()
            sock.close()
            raise RemoteError('subscribe', str(response))
        sock.settimeout(None)
        self.event_socket = sock

        def receive():
            try:
                while not self.closed.is_set():
                    event = read_message(stream)
                    try:
                        self.events.put_nowait(event)
                    except queue.Full:
                        self.gaps += 1
            except (OSError, EOFError, ActionError):
                if not self.closed.is_set():
                    self.gaps += 1
            finally:
                stream.close()
        threading.Thread(target=receive, daemon=True).start()

    def next_event(self, timeout=0):
        return self.events.get(timeout=timeout)

    def close(self):
        self.closed.set()
        for sock in (self.event_socket, self.socket):
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
