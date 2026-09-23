"""Shared physical port owner and its local raw/control TCP transports."""
import base64
from collections import OrderedDict
import math
import os
from pathlib import Path
import queue
import socket
import threading
import time
import uuid

import serial
from serial.tools import list_ports
from serial_protocol import VERSION, ActionError, encode, payload, read_message


def close_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


class SerialService:
    def __init__(self, port=None, baud=115200, host='127.0.0.1', tcp=8888,
                 control=8889, chardelay=0, serial_factory=None, **options):
        self.host, self.tcp_port, self.control_port = host, tcp, control
        self.config = dict(port=port, baudrate=baud, bytesize=8, stopbits=1, parity='N',
                           xonxoff=False, rtscts=False, dsrdtr=False)
        self.factory = serial_factory or (lambda p, b: serial.serial_for_url(
            p, baudrate=b, timeout=.05, write_timeout=.5))
        self.chardelay = chardelay
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.stop = threading.Event()
        self.device = None
        self.listeners = []
        self.connections = set()
        self.subscribers = set()
        self.raw_clients = {}
        self.sequence = 0
        self.jobs = OrderedDict()
        self.send_queue = queue.Queue(options.get('send_capacity', 64))
        self.threads = set()
        self.active = None
        self.token = None
        self.lease_timeout = options.get('lease_timeout', 10.0)
        self.lease_deadline = 0.0
        self.transition = None
        self.reconnect = bool(port)
        self.last_error = None
        self.instance = uuid.uuid4().hex
        self.log_path = options.get('log')
        self.log_queue = queue.Queue(options.get('log_capacity', 1024))
        self.log_error = None
        self.log_dropped = 0
        self.client_drops = 0
        self.event_capacity = options.get('event_capacity', 1024)

    def _thread(self, target, *args):
        def run():
            try:
                target(*args)
            finally:
                with self.lock:
                    self.threads.discard(threading.current_thread())
        thread = threading.Thread(target=run, daemon=True)
        with self.lock:
            self.threads.add(thread)
        thread.start()

    def start(self):
        try:
            if self.host not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('Service must bind to loopback')
            # Reserve BOTH endpoints before touching the physical device.
            for port in (self.tcp_port, self.control_port):
                listener = socket.socket()
                if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                self.listeners.append(listener)
                listener.bind((self.host, port))
                listener.listen(16)
                listener.settimeout(.2)
            self.tcp_port, self.control_port = [s.getsockname()[1] for s in self.listeners]
            if self.config['port']:
                try:
                    self.device = self._open_device(self.config)
                except (OSError, serial.SerialException) as exc:
                    self.last_error = str(exc)
            self._thread(self._accept, self.listeners[0], self._raw)
            self._thread(self._accept, self.listeners[1], self._control)
            self._thread(self._writer)
            self._thread(self._reader)
            self._thread(self._maintenance)
            self._thread(self._logger)
            return self
        except Exception:
            self.close()
            raise

    def close(self):
        self.stop.set()
        for sock in self.listeners:
            sock.close()
        with self.lock:
            self._cancel_jobs()
            for sock in list(self.connections):
                close_socket(sock)
            if self.device:
                self.device.close()
                self.device = None
            threads = list(self.threads)
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(.5)

    def _accept(self, listener, handler):
        while not self.stop.is_set():
            try:
                sock, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self.lock:
                if len(self.connections) >= 32:
                    close_socket(sock)
                    continue
                self.connections.add(sock)
            self._thread(self._connection, sock, handler)

    def _connection(self, sock, handler):
        try:
            sock.settimeout(30)
            handler(sock)
        except (OSError, EOFError):
            pass
        finally:
            with self.lock:
                self.connections.discard(sock)
            close_socket(sock)

    def _emit(self, name, **fields):
        with self.lock:
            self.sequence += 1
            event = dict(event=name, seq=self.sequence, **fields)
            for outgoing, sock in list(self.subscribers):
                try:
                    outgoing.put_nowait(event)
                except queue.Full:
                    self.subscribers.discard((outgoing, sock))
                    self.client_drops += 1
                    close_socket(sock)

    def status(self):
        return dict(version=VERSION, connected=self.device is not None,
                    config=self.config.copy(), sequence=self.sequence, instance=self.instance,
                    pid=os.getpid(), script=str(Path(__file__).with_name('shared_serial_bridge.py').resolve()),
                    tcp_port=self.tcp_port, control_port=self.control_port,
                    owner='revoking' if self.transition == 'revoking' else ('agent' if self.token else 'human'),
                    transition=self.transition, reconnect=self.reconnect, error=self.last_error,
                    lease_timeout=self.lease_timeout, log_path=str(self.log_path) if self.log_path else None,
                    log_error=self.log_error, log_dropped=self.log_dropped, client_drops=self.client_drops,
                    capabilities=['events', 'jobs', 'exclusive', 'configure', 'device-release'])

    def _control(self, sock):
        with sock.makefile('rb') as stream:
            while not self.stop.is_set():
                request = {}
                try:
                    request = read_message(stream)
                    if request.get('version') != VERSION:
                        raise ActionError('version', 'Requires protocol version 1')
                    action = request.get('action')
                    params = request.get('params', {})
                    if not isinstance(params, dict) or not isinstance(action, str):
                        raise ActionError('invalid_message', 'Expected action and parameter object')
                    if action == 'subscribe':
                        outgoing = queue.Queue(self.event_capacity)
                        with self.lock:
                            self.subscribers.add((outgoing, sock))
                            outgoing.put(dict(event='state', seq=self.sequence, state=self.status()))
                        sock.sendall(encode(dict(id=request.get('id'), ok=True, result={})))
                        sock.settimeout(1)
                        try:
                            while not self.stop.is_set():
                                try:
                                    event = outgoing.get(timeout=.2)
                                except queue.Empty:
                                    continue
                                sock.sendall(encode(event))
                        finally:
                            with self.lock:
                                self.subscribers.discard((outgoing, sock))
                        return
                    result = self.action(action, params, request.get('token'))
                    response = dict(id=request.get('id'), ok=True, result=result)
                except (ActionError, ValueError, TypeError, KeyError) as exc:
                    response = dict(id=request.get('id'), ok=False,
                                    error=dict(code=getattr(exc, 'code', 'invalid_input'), message=str(exc)))
                sock.sendall(encode(response))
                if response.get('error', {}).get('code') == 'too_large':
                    return

    def action(self, action, params, token=None):
        with self.lock:
            if self.token and time.monotonic() >= self.lease_deadline:
                self._revoke()
            if token is not None and token != self.token:
                raise ActionError('invalid_token', 'Lease is no longer valid; do not resume this task')
            if action in ('hello', 'status'):
                return self.status()
            if action == 'serial.list':
                return [dict(port=p.device, description=p.description) for p in list_ports.comports()]
            if action == 'job.status':
                job = self.jobs.get(params.get('job_id'))
                if job is None:
                    raise ActionError('not_found', 'Job not retained')
                return self._job_state(job)
            if action == 'agent.takeover':
                self._revoke()
                return self.status()
            if self.transition:
                raise ActionError('busy', 'Device transition in progress')
            if self.token and token != self.token and action != 'agent.takeover':
                raise ActionError('occupied', 'Agent owns the device; observe or explicitly take over')
            if action == 'agent.acquire':
                if self.token or self.active or not self.send_queue.empty():
                    raise ActionError('busy', 'Wait for outstanding sends to finish before acquiring')
                self.token = uuid.uuid4().hex
                self.lease_deadline = time.monotonic() + self.lease_timeout
                self._emit('state', state=self.status())
                return dict(token=self.token, timeout=self.lease_timeout, heartbeat=self.lease_timeout / 3)
            if action in ('agent.heartbeat', 'agent.release'):
                if not self.token or token != self.token:
                    raise ActionError('invalid_token', 'A current lease token is required')
                if action == 'agent.release':
                    self._revoke()
                else:
                    self.lease_deadline = time.monotonic() + self.lease_timeout
                return self.status()
            if action in ('serial.open', 'serial.close', 'serial.reconnect', 'serial.configure', 'serial.baud', 'service.stop'):
                if action == 'service.stop' and params.get('instance') != self.instance:
                    raise ActionError('identity', 'Expected the managed service instance ID')
                return self._device_action(action, params)
            if action in ('send', 'send.hex'):
                if self.device is None:
                    raise ActionError('disconnected', 'Device is not connected')
                data = payload(action, params)
                delay = params.get('chardelay', self.chardelay)
                if not isinstance(delay, (float, int)) or not math.isfinite(delay) or not 0 <= delay <= 1:
                    raise ActionError('invalid_input', 'chardelay must be between 0 and 1 second')
                job = dict(job_id=uuid.uuid4().hex, data=data, written=0, state='queued',
                           token=token, cancel=threading.Event(), chardelay=delay, size=len(data))
                try:
                    self.send_queue.put_nowait(job)
                except queue.Full as exc:
                    raise ActionError('queue_full', 'Send queue is full') from exc
                self.jobs[job['job_id']] = job
                for key in list(self.jobs):
                    if len(self.jobs) <= 256:
                        break
                    if self.jobs[key]['state'] not in ('queued', 'writing'):
                        del self.jobs[key]
                self._emit('job', **self._job_state(job))
                return self._job_state(job)
            raise ActionError('unknown_action', action)

    @staticmethod
    def _job_state(job):
        return {k: v for k, v in job.items() if k not in ('data', 'token', 'cancel')}

    def _writer(self):
        while not self.stop.is_set():
            with self.changed:
                if self.transition:
                    self.changed.wait(.02)
                    continue
                try:
                    job = self.send_queue.get_nowait()
                except queue.Empty:
                    self.changed.wait(.02)
                    continue
                if job['cancel'].is_set() or self.device is None:
                    job['state'] = 'cancelled'
                    self._emit('job', **self._job_state(job))
                    continue
                device = self.device
                self.active = job
                job['state'] = 'writing'
            try:
                while job['written'] < len(job['data']):
                    if job['cancel'].is_set() or self.stop.is_set():
                        job['state'] = 'cancelled'
                        break
                    offset = job['written']
                    chunk = job['data'][offset:offset + (1 if job['chardelay'] else 4096)]
                    count = device.write(chunk)
                    if not isinstance(count, int) or count <= 0 or count > len(chunk):
                        raise OSError('Driver returned an invalid write count')
                    with self.lock:
                        job['written'] += count
                        self._emit('tx', data=base64.b64encode(chunk[:count]).decode(), job_id=job['job_id'])
                    if job['chardelay']:
                        job['cancel'].wait(job['chardelay'])
                else:
                    job['state'] = 'written'
            except (OSError, serial.SerialException) as exc:
                job['state'] = 'unknown'
                job['error'] = str(exc)
                self._disconnect(device, exc)
            finally:
                with self.changed:
                    self.active = None
                    self._emit('job', **self._job_state(job))
                    self.changed.notify_all()

    def _cancel_jobs(self):
        if self.active:
            self.active['cancel'].set()
        while True:
            try:
                job = self.send_queue.get_nowait()
            except queue.Empty:
                break
            job['cancel'].set()
            job['state'] = 'cancelled'
            self._emit('job', **self._job_state(job))

    def _wait_active(self, timeout=1.5):
        deadline = time.monotonic() + timeout
        while self.active:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ActionError('busy', 'Writer has not stopped; control has NOT been returned')
            self.changed.wait(remaining)

    def _revoke(self):
        self.token = None
        self.transition = 'revoking'
        self._cancel_jobs()
        self._emit('state', state=self.status())
        try:
            self._wait_active()
        finally:
            self.transition = None
        self._emit('state', state=self.status())

    def _settings(self, params):
        if set(params) - set(self.config):
            raise ActionError('invalid_input', 'Unknown serial configuration field')
        value = dict(self.config, **params)
        if (not isinstance(value['port'], (str, type(None))) or
                not isinstance(value['baudrate'], int) or isinstance(value['baudrate'], bool) or
                not 1 <= value['baudrate'] <= 12000000 or value['bytesize'] not in (5, 6, 7, 8) or
                value['stopbits'] not in (1, 1.5, 2) or value['parity'] not in ('N', 'E', 'O', 'M', 'S') or
                any(type(value[k]) is not bool for k in ('xonxoff', 'rtscts', 'dsrdtr'))):
            raise ActionError('invalid_input', 'Invalid serial configuration')
        return value

    def _open_device(self, config):
        device = self.factory(config['port'], config['baudrate'])
        try:
            if hasattr(device, 'apply_settings'):
                device.apply_settings({k: v for k, v in config.items() if k != 'port'})
            return device
        except Exception:
            device.close()
            raise

    def _device_action(self, action, params):
        if action == 'serial.baud':
            params = dict(baudrate=params.get('baudrate', params.get('baud')))
        config = self._settings(params) if action in ('serial.configure', 'serial.baud', 'serial.open') else self.config.copy()
        releasing = action in ('serial.close', 'serial.reconnect', 'serial.open', 'service.stop')
        self.transition = action
        try:
            if releasing:
                self.reconnect = False
                self._cancel_jobs()
            self._wait_active()
            if action in ('serial.configure', 'serial.baud') and self.device and config['port'] == self.config['port']:
                try:
                    self.device.apply_settings({k: v for k, v in config.items() if k != 'port'})
                finally:
                    self.config.update({k: v for k, v in self.device.get_settings().items() if k in self.config})
            else:
                if action in ('serial.configure', 'serial.baud') and self.device:
                    raise ActionError('invalid_input', 'Use serial.open to switch ports')
                if self.device:
                    self.device.close()
                    self.device = None
                if action in ('serial.open', 'serial.reconnect'):
                    if not config['port']:
                        raise ActionError('invalid_input', 'A port is required')
                    self.device = self._open_device(config)
                    self.reconnect = True
                self.config = config
            self.last_error = None
            if action == 'service.stop':
                self.stop.set()
        except (OSError, serial.SerialException, ValueError) as exc:
            self.last_error = str(exc)
            raise ActionError('device_error', str(exc)) from exc
        finally:
            self.transition = None
            self._emit('state', state=self.status())
        return self.status()

    def _disconnect(self, device, error):
        with self.lock:
            if self.device is not device:
                return
            self.device = None
            self.last_error = str(error)
            self.token = None
            self._cancel_jobs()
            if self.active:
                self.transition = 'revoking'
            device.close()
            # Drain already received data before EOF, preserving the old raw behavior.
            for outgoing in self.raw_clients.values():
                try:
                    outgoing.put_nowait(None)
                except queue.Full:
                    pass
            self._emit('state', state=self.status())

    def _maintenance(self):
        retry_at = 0
        while not self.stop.wait(.05):
            with self.lock:
                if self.token and time.monotonic() >= self.lease_deadline:
                    try:
                        self._revoke()
                    except ActionError:
                        pass
                if self.transition == 'revoking' and not self.active:
                    self.transition = None
                    self._emit('state', state=self.status())
                if self.device is None and self.reconnect and not self.transition and time.monotonic() >= retry_at:
                    retry_at = time.monotonic() + 1
                    try:
                        self.device = self._open_device(self.config)
                        self.last_error = None
                        self._emit('state', state=self.status())
                    except (OSError, serial.SerialException) as exc:
                        self.last_error = str(exc)

    def _logger(self):
        if not self.log_path:
            return
        try:
            Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, 'ab') as stream:
                while not self.stop.is_set() or not self.log_queue.empty():
                    try:
                        data = self.log_queue.get(timeout=.1)
                    except queue.Empty:
                        continue
                    stream.write(data)
                    stream.flush()
        except OSError as exc:
            with self.lock:
                self.log_error = str(exc)
                self._emit('state', state=self.status())

    def _reader(self):
        while not self.stop.is_set():
            device = self.device
            if device is None:
                self.stop.wait(.05)
                continue
            try:
                data = device.read(4096)
            except (OSError, serial.SerialException) as exc:
                self._disconnect(device, exc)
                continue
            if data:
                with self.lock:
                    if device is not self.device:
                        continue
                    self._emit('rx', data=base64.b64encode(data).decode())
                    if self.log_path:
                        try:
                            if self.log_error:
                                raise queue.Full()
                            self.log_queue.put_nowait(data)
                        except queue.Full:
                            self.log_dropped += len(data)
                    for sock, outgoing in list(self.raw_clients.items()):
                        try:
                            outgoing.put_nowait(data)
                        except queue.Full:
                            self.client_drops += 1
                            close_socket(sock)
                            del self.raw_clients[sock]

    def _raw_writer(self, sock, outgoing):
        try:
            while not self.stop.is_set():
                try:
                    data = outgoing.get(timeout=.2)
                except queue.Empty:
                    with self.lock:
                        if sock not in self.raw_clients:
                            return
                    continue
                if data is None:
                    return
                sock.sendall(data)
        except OSError:
            pass
        finally:
            close_socket(sock)

    def _raw(self, sock):
        outgoing = queue.Queue(self.event_capacity)
        sock.settimeout(1)
        with self.lock:
            self.raw_clients[sock] = outgoing
        self._thread(self._raw_writer, sock, outgoing)
        try:
            while not self.stop.is_set():
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    return
                self.action('send', dict(data=base64.b64encode(data).decode(), format='base64'))
        except ActionError as exc:
            self._emit('raw_rejected', reason=exc.code, message=str(exc))
            return
        finally:
            with self.lock:
                self.raw_clients.pop(sock, None)
