"""Shared physical port owner and its local raw/control TCP transports."""
import base64
from collections import OrderedDict, deque
from datetime import datetime
import math
import os
from pathlib import Path
import queue
import socket
import sys
import threading
import time
import uuid

import serial
from serial.tools import list_ports
from serial_protocol import VERSION, ActionError, encode, payload, read_message
from serial_baud_scan import (COOLDOWN_FAIL, COOLDOWN_SUCCESS, DEFAULT_BAUDS, MONITOR_MIN_BYTES,
                              MONITOR_THRESHOLD, MONITOR_WINDOW, readability, scan_open_device)


# Control (call) connections idle for as long as the human steps away between
# commands, so they must not carry a socket read timeout: the GUI only writes
# to this channel when the user actually sends. Event and raw handlers apply
# their own short timeouts. Kept as a module constant for tests.
CONTROL_READ_TIMEOUT = None

AUTO_BAUD_DEFAULTS = dict(enabled=False, active=False, bauds=DEFAULT_BAUDS,
                          seconds=0.5, rounds=1, min_bytes=None,
                          threshold=MONITOR_THRESHOLD, window_seconds=MONITOR_WINDOW,
                          min_suspect_bytes=MONITOR_MIN_BYTES,
                          cooldown_success=COOLDOWN_SUCCESS, cooldown_fail=COOLDOWN_FAIL)

# The reader must never overlap a baud scan's device.read(): pyserial win32
# backs every read() of one Serial object with ONE shared OVERLAPPED struct,
# and two in-flight reads on it can wedge the reader forever with a perfectly
# healthy-looking status (the 2026-10-23 silent RX death). The scan therefore
# waits for the reader to park (READER_PAUSE_TIMEOUT), and the maintenance
# watchdog stops the whole bridge when the reader stops making progress
# (READER_STALL_SECONDS) instead of leaving it half-alive.
READER_PAUSE_TIMEOUT = 1.5
READER_STALL_SECONDS = 5.0


def close_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


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
        self.auto_baud_cfg = self._auto_baud_options(options.get('auto_baud'))
        self.auto_baud_state = dict(last_reason=None, last_change=None, cooldown_until=0.0)
        self.scan_requested = None
        self.scan_active = False
        self._scan_wakeup = threading.Event()
        self.scan_abort = threading.Event()
        self._suspect_window = deque()
        self.rx_bytes_total = 0
        self.tx_bytes_total = 0
        self.last_rx_timestamp = None
        self._reader_beat = time.monotonic()
        self._reader_parked = threading.Event()

    def _thread(self, target, *args):
        name = getattr(target, '__name__', 'worker')

        def run():
            try:
                target(*args)
            except BaseException as exc:  # never silent: a dead worker must
                # not leave the bridge reporting a healthy-looking status.
                message = f'{name} thread died: {exc!r}'
                with self.lock:
                    self.last_error = message
                    state = self.status()
                self._emit('state', state=state)
                try:
                    sys.stderr.write(f'[串口桥] {message}\n')
                    sys.stderr.flush()
                except OSError:
                    pass
            finally:
                with self.lock:
                    self.threads.discard(threading.current_thread())
        thread = threading.Thread(target=run, daemon=True, name=name)
        with self.lock:
            self.threads.add(thread)
        thread.start()

    def _panic(self, message):
        """Stop the whole bridge loudly instead of leaving it half-alive."""
        with self.lock:
            self.last_error = message
            state = self.status()
        self._emit('state', state=state)
        try:
            sys.stderr.write(f'[串口桥] {message}\n')
            sys.stderr.flush()
        except OSError:
            pass
        self.stop.set()

    @staticmethod
    def _auto_baud_options(raw):
        cfg = dict(AUTO_BAUD_DEFAULTS)
        if not isinstance(raw, dict):
            return cfg
        unknown = set(raw) - set(cfg)
        if unknown:
            raise ValueError(f'Unknown auto_baud options: {sorted(unknown)}')
        cfg.update(raw)
        bauds = tuple(dict.fromkeys(int(b) for b in cfg['bauds']))
        if not bauds or any(b <= 0 for b in bauds):
            raise ValueError('auto_baud bauds must be positive integers')
        cfg['bauds'] = bauds
        cfg['enabled'] = bool(cfg['enabled'])
        cfg['active'] = bool(cfg['active'])
        for key in ('seconds', 'threshold', 'window_seconds', 'cooldown_success', 'cooldown_fail'):
            cfg[key] = float(cfg[key])
        for key in ('rounds', 'min_suspect_bytes'):
            cfg[key] = int(cfg[key])
        min_bytes = cfg['min_bytes']
        cfg['min_bytes'] = None if min_bytes is None else int(min_bytes)
        if not 0.05 <= cfg['seconds'] <= 5 or not 1 <= cfg['rounds'] <= 5:
            raise ValueError('auto_baud seconds/rounds out of range')
        if not 0 < cfg['threshold'] < 1:
            raise ValueError('auto_baud threshold must be between 0 and 1')
        return cfg

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
            self._thread(self._auto_baud_loop)
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

    def _auto_baud_public(self):
        state = self.auto_baud_state
        cfg = self.auto_baud_cfg
        return dict(enabled=cfg['enabled'], active=cfg['active'],
                    scanning=self.scan_active, requested=self.scan_requested is not None,
                    bauds=list(cfg['bauds']), seconds=cfg['seconds'], rounds=cfg['rounds'],
                    min_bytes=cfg['min_bytes'] or (4 if cfg['active'] else 12),
                    last_reason=state['last_reason'], last_change=state['last_change'],
                    cooldown_remaining=max(0.0, round(state['cooldown_until'] - time.monotonic(), 2)))

    def status(self):
        return dict(version=VERSION, connected=self.device is not None,
                    config=self.config.copy(), sequence=self.sequence, instance=self.instance,
                    pid=os.getpid(), script=str(Path(__file__).with_name('shared_serial_bridge.py').resolve()),
                    tcp_port=self.tcp_port, control_port=self.control_port,
                    owner='revoking' if self.transition == 'revoking' else ('agent' if self.token else 'human'),
                    transition=self.transition, reconnect=self.reconnect, error=self.last_error,
                    lease_timeout=self.lease_timeout, log_path=str(self.log_path) if self.log_path else None,
                    log_error=self.log_error, log_dropped=self.log_dropped, client_drops=self.client_drops,
                    rx_bytes_total=self.rx_bytes_total, tx_bytes_total=self.tx_bytes_total,
                    last_rx_timestamp=self.last_rx_timestamp,
                    auto_baud=self._auto_baud_public(),
                    capabilities=['events', 'jobs', 'exclusive', 'configure', 'device-release', 'auto-baud'])

    def _control(self, sock):
        # Call connections must survive arbitrarily long idle periods between
        # user actions; see CONTROL_READ_TIMEOUT above.
        sock.settimeout(CONTROL_READ_TIMEOUT)
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
            if action == 'autobaud.status':
                return self._auto_baud_public()
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
            if action == 'serial.autobaud':
                return self._autobaud_start(params)
            if action == 'serial.autobaud.configure':
                return self._autobaud_configure(params)
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
                        self.tx_bytes_total += count
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

    def _abort_scan_and_wait(self, timeout=3.0):
        """Abort an in-flight baud scan and wait until it released the device.

        The scan thread owns the device (its read buffer and apply_settings)
        while it holds the 'baud_scan' transition. Takeover and device actions
        must wait it out instead of silently clobbering the transition, which
        used to let the writer resume at the candidate baud and let the scan
        flip the baud under the new owner. Called under self.lock; the wait
        releases the lock so the scan's cleanup can run, and the scan cleanup
        notifies self.changed to wake us. Callers keep the transition held (or
        are the takeover path), so no new scan can start while we wait.
        """
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                if not self.scan_active:
                    return
                self.scan_abort.set()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ActionError('busy', 'Baud scan did not stop; control has NOT been returned')
                self.changed.wait(remaining)

    def _revoke(self):
        self._abort_scan_and_wait()
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
            # Hold the transition first, then wait out a running scan: the
            # monitor loop cannot start a new scan while a transition is set.
            self._abort_scan_and_wait()
            if releasing:
                self.reconnect = False
                # Explicit release must also drop a queued (not yet started)
                # scan request; the device it targeted is going away.
                self.scan_requested = None
                self._cancel_jobs()
            self._wait_active()
            if action in ('serial.configure', 'serial.baud') and self.device and config['port'] == self.config['port']:
                previous_baud = self.config['baudrate']
                try:
                    self.device.apply_settings({k: v for k, v in config.items() if k != 'port'})
                finally:
                    self.config.update({k: v for k, v in self.device.get_settings().items() if k in self.config})
                if self.config['baudrate'] != previous_baud:
                    self.auto_baud_state['last_change'] = dict(
                        **{'from': previous_baud, 'to': self.config['baudrate']}, trigger='manual')
                    self._emit('baud_changed', **{'from': previous_baud, 'to': self.config['baudrate']},
                               trigger='manual')
                    self._raw_notice(f"波特率已从 {previous_baud} 切换为 {self.config['baudrate']}")
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
            # A queued scan request dies with the device: leaving it set kept
            # 'requested' stuck on, reporting bogus success and blocking later
            # scans with 'busy' until the port returned.
            self.scan_requested = None
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
            # Reader watchdog: device.read() is capped near 50 ms, so a healthy
            # reader beats constantly. A stale beat means the reader thread
            # died or is wedged inside a read; stop the whole bridge loudly
            # instead of leaving a connected:true, error:null half-dead shell.
            if (self.device is not None
                    and time.monotonic() - self._reader_beat > READER_STALL_SECONDS):
                self._panic(f'reader thread stalled or died (no progress for '
                            f'{READER_STALL_SECONDS:g}s); stopping the bridge')
                break

    def _raw_notice(self, text):
        """Inject a human-readable status line into every raw TCP client."""
        data = f"\r\n[串口桥] {text}\r\n".encode('utf-8')
        # raw_clients is shared with the reader, the raw handlers and the
        # scan thread; dropping a dead client must hold the lock or the
        # reader's del can race this pop into a thread-killing KeyError.
        with self.lock:
            for sock, outgoing in list(self.raw_clients.items()):
                try:
                    outgoing.put_nowait(data)
                except queue.Full:
                    self.client_drops += 1
                    close_socket(sock)
                    self.raw_clients.pop(sock, None)

    def _auto_baud_feed(self, data, now):
        """Called with the lock held: watch RX for sustained garbled output."""
        cfg = self.auto_baud_cfg
        if not cfg['enabled'] or self.scan_active or self.scan_requested or self.transition or self.token:
            return
        if now < self.auto_baud_state['cooldown_until']:
            return
        window = self._suspect_window
        window.append((now, data))
        horizon = now - cfg['window_seconds']
        while window and window[0][0] < horizon:
            window.popleft()
        total = sum(len(chunk) for _, chunk in window)
        if total < cfg['min_suspect_bytes']:
            return
        combined = b''.join(chunk for _, chunk in window)
        if readability(combined) <= cfg['threshold']:
            window.clear()
            self.scan_requested = dict(
                mode='active' if cfg['active'] else 'passive', bauds=cfg['bauds'],
                seconds=cfg['seconds'], rounds=cfg['rounds'],
                min_bytes=cfg['min_bytes'] or (4 if cfg['active'] else 12),
                probe=b"\r" if cfg['active'] else None, manual=False)
            self._scan_wakeup.set()

    def _auto_baud_loop(self):
        while not self.stop.wait(0.1):
            self._scan_wakeup.wait(0.5)
            self._scan_wakeup.clear()
            request = None
            with self.lock:
                if (self.scan_requested and self.device is not None
                        and not self.transition and not self.scan_active):
                    if not self.scan_requested.get('manual') and self.token:
                        self.scan_requested = None  # agent owns the device; drop auto request
                    else:
                        request = self.scan_requested
                        self.scan_requested = None
                        self.scan_active = True
                        self.transition = 'baud_scan'
            if request is None:
                continue
            self.scan_abort.clear()
            # Handshake first: the reader must be parked OUTSIDE device.read
            # before the scan touches the device. pyserial win32 read() shares
            # one OVERLAPPED per Serial object, so a scan read overlapping the
            # reader's read can wedge both forever (silent RX death). A
            # timed-out wait means the reader is wedged or dead; scanning
            # anyway is exactly the race this handshake exists to close.
            if not self._reader_parked.wait(READER_PAUSE_TIMEOUT):
                with self.lock:
                    self.scan_active = False
                    if self.transition == 'baud_scan':
                        self.transition = None
                    self.auto_baud_state['last_reason'] = 'reader_unavailable'
                    self._suspect_window.clear()
                    self.changed.notify_all()
                    self._emit('baud_scan', state='failed', reason='reader_unavailable',
                               trigger='manual' if request.get('manual') else 'auto')
                    self._emit('state', state=self.status())
                continue
            try:
                self._perform_scan(request)
            except Exception as exc:  # the monitor thread must survive anything
                with self.lock:
                    self.auto_baud_state['last_reason'] = f'error: {exc}'
                    self._emit('baud_scan', state='failed', reason=str(exc),
                               trigger='manual' if request.get('manual') else 'auto')
                try:
                    self._raw_notice('波特率扫描出错，已恢复原波特率。')
                except Exception:
                    pass
            finally:
                with self.lock:
                    self.scan_active = False
                    # Clear only our own transition: with the abort handshake
                    # a takeover or device action may already hold 'revoking'
                    # or its own action transition when the scan stops.
                    if self.transition == 'baud_scan':
                        self.transition = None
                    self._suspect_window.clear()
                    self.changed.notify_all()
                    self._emit('state', state=self.status())

    def _perform_scan(self, request):
        device = self.device
        if device is None:
            return
        cfg = self.auto_baud_cfg
        mode = request['mode']
        trigger = 'manual' if request.get('manual') else 'auto'
        start_baud = self.config['baudrate']
        candidates = [start_baud] + [int(b) for b in request['bauds'] if int(b) != start_baud]
        self._emit('baud_scan', state='started', mode=mode, candidates=candidates, trigger=trigger)
        self._raw_notice(
            "检测到疑似波特率失配，正在%s扫描（候选：%s），期间暂停收发" %
            ('主动' if mode == 'active' else '被动', ', '.join(str(b) for b in candidates)))
        winner, scores, reason = scan_open_device(
            device, candidates, request['seconds'], request['rounds'], request['min_bytes'],
            probe=request.get('probe'), applier=lambda baud: device.apply_settings({'baudrate': baud}),
            should_abort=self.scan_abort.is_set)
        with self.lock:
            state = self.auto_baud_state
            now = time.monotonic()
            if self.device is device:
                try:
                    self.config.update({k: v for k, v in device.get_settings().items() if k in self.config})
                except (OSError, serial.SerialException, AttributeError):
                    pass
            state['last_reason'] = reason
            # -inf scores (empty samples) are not JSON-compliant (allow_nan=False).
            summary = [dict(baud=s.baud, bytes=s.byte_count,
                            score=round(s.score, 1) if math.isfinite(s.score) else None)
                       for s in scores]
            if reason == 'interrupted' or self.device is not device:
                state['cooldown_until'] = now + cfg['cooldown_fail']
                self._emit('baud_scan', state='failed', reason=reason, trigger=trigger, scores=summary)
                self._raw_notice('波特率扫描被中断，已恢复原波特率。')
                return
            if winner is not None and winner != start_baud:
                applied = False
                try:
                    device.apply_settings({'baudrate': winner})
                    self.config.update({k: v for k, v in device.get_settings().items() if k in self.config})
                    applied = True
                except (OSError, serial.SerialException, ValueError) as exc:
                    state['last_reason'] = reason = f'apply_failed: {exc}'
                if applied:
                    state['last_reason'] = None
                    state['last_change'] = {'from': start_baud, 'to': winner, 'trigger': trigger}
                    state['cooldown_until'] = now + cfg['cooldown_success']
                    self._emit('baud_changed', **{'from': start_baud, 'to': winner},
                               trigger=trigger, scores=summary)
                    self._raw_notice(f"波特率已从 {start_baud} 切换为 {winner}（在线检测）")
                    return
            if winner == start_baud:
                state['last_reason'] = None
                state['cooldown_until'] = now + cfg['cooldown_success']
                self._emit('baud_scan', state='unchanged', baud=start_baud, trigger=trigger, scores=summary)
                self._raw_notice(f"在线检测确认当前波特率 {start_baud} 有效")
                return
            state['cooldown_until'] = now + cfg['cooldown_fail']
            hint = ('可读输出不足：让设备多打印，或改用主动探测（会发送回车）。'
                    if mode == 'passive' else '设备没有应答回车探测；请确认固件支持，或改用被动模式。')
            self._emit('baud_scan', state='failed', reason=reason, trigger=trigger, scores=summary)
            self._raw_notice(f"未能确定波特率（{reason}），已保持 {start_baud}。{hint}")

    def _autobaud_start(self, params):
        params = params or {}
        cfg = self.auto_baud_cfg
        mode = params.get('mode') or ('active' if cfg['active'] else 'passive')
        if mode not in ('passive', 'active'):
            raise ActionError('invalid_input', "mode must be 'passive' or 'active'")
        bauds = params.get('bauds')
        if bauds is None:
            bauds = cfg['bauds']
        else:
            if (not isinstance(bauds, list) or not bauds or len(bauds) > 16 or
                    any(isinstance(b, bool) or not isinstance(b, int) or b <= 0 for b in bauds)):
                raise ActionError('invalid_input', 'bauds must be a list of 1..16 positive integers')
            bauds = tuple(dict.fromkeys(int(b) for b in bauds))
        seconds = params.get('seconds', cfg['seconds'])
        rounds = params.get('rounds', cfg['rounds'])
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not 0.05 <= seconds <= 5:
            raise ActionError('invalid_input', 'seconds must be between 0.05 and 5')
        if not isinstance(rounds, int) or isinstance(rounds, bool) or not 1 <= rounds <= 5:
            raise ActionError('invalid_input', 'rounds must be between 1 and 5')
        min_bytes = params.get('min_bytes')
        if min_bytes is None:
            min_bytes = cfg['min_bytes'] or (4 if mode == 'active' else 12)
        if not isinstance(min_bytes, int) or isinstance(min_bytes, bool) or not 1 <= min_bytes <= 65536:
            raise ActionError('invalid_input', 'min_bytes must be a positive integer')
        with self.lock:
            if self.device is None:
                raise ActionError('disconnected', 'Device is not connected')
            if self.scan_active or self.scan_requested:
                raise ActionError('busy', 'A baud scan is already pending or running')
            # Assign under the lock so concurrent requests cannot both pass the
            # busy check and silently overwrite each other.
            self.scan_requested = dict(mode=mode, bauds=tuple(bauds), seconds=float(seconds),
                                       rounds=int(rounds), min_bytes=int(min_bytes),
                                       probe=b"\r" if mode == 'active' else None, manual=True)
        self._scan_wakeup.set()
        return self._auto_baud_public()

    def _autobaud_configure(self, params):
        if not isinstance(params, dict) or not params:
            raise ActionError('invalid_input', 'Expected auto_baud configuration fields')
        unknown = set(params) - set(self.auto_baud_cfg)
        if unknown:
            raise ActionError('invalid_input', f'Unknown auto_baud fields: {sorted(unknown)}')
        merged = dict(self.auto_baud_cfg)
        merged.update(params)
        cfg = self._auto_baud_options(merged)
        with self.lock:
            self.auto_baud_cfg = cfg
            if not cfg['enabled']:
                self.scan_requested = None
                self._suspect_window.clear()
        self._emit('state', state=self.status())
        return self._auto_baud_public()

    def _logger(self):
        if not self.log_path:
            return
        try:
            Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, 'ab') as stream:
                # Bracket every session: bytes already in the file (e.g. a
                # hand-seeded tail of a previous session) must never masquerade
                # as new bridge output when triaging a dead RX path.
                stream.write(f"=== bridge session start "
                             f"{datetime.now():%Y-%m-%d %H:%M:%S} pid={os.getpid()} ===\n"
                             .encode('utf-8'))
                stream.flush()
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
            self._reader_beat = time.monotonic()
            device = self.device
            if device is None:
                self._reader_parked.set()
                self.stop.wait(.05)
                continue
            if self.scan_active:
                # The baud scan owns the device (and its read buffer) right
                # now. Park OUTSIDE device.read and say so: pyserial win32
                # read() shares one OVERLAPPED per Serial object, so a scan
                # read that overlaps this thread's read can wedge both
                # forever. The scan waits for _reader_parked first.
                self._reader_parked.set()
                self.stop.wait(.02)
                continue
            self._reader_parked.clear()
            if self.scan_active:  # re-check after clearing: a scan may have started
                self._reader_parked.set()
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
                    self.rx_bytes_total += len(data)
                    self.last_rx_timestamp = time.time()
                    self._emit('rx', data=base64.b64encode(data).decode())
                    self._auto_baud_feed(data, time.monotonic())
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
                            with self.lock:
                                # pop-with-default: another locked mutator
                                # (raw notice/handler) may have dropped this
                                # client already; a KeyError here used to kill
                                # the reader thread and stop all RX forwarding.
                                if self.raw_clients.pop(sock, None) is not None:
                                    self.client_drops += 1
                                    close_socket(sock)

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
                try:
                    self.action('send', dict(data=base64.b64encode(data).decode(), format='base64'))
                except ActionError as exc:
                    # A rejected send must not disconnect the raw terminal: a
                    # human typing while an agent holds the lease used to be
                    # kicked (and reconnected) for every keypress. Tell the
                    # operator on this connection and keep listening.
                    self._emit('raw_rejected', reason=exc.code, message=str(exc))
                    try:
                        outgoing.put_nowait(f"\r\n[串口桥] 发送被拒绝：{exc}\r\n".encode('utf-8'))
                    except queue.Full:
                        pass
        finally:
            with self.lock:
                self.raw_clients.pop(sock, None)
