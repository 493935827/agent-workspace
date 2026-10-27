import base64
import contextlib
import io
import json
import queue
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import serial_control  # noqa: E402
from serial_service import SerialService  # noqa: E402
from serial_client import Client, RemoteError  # noqa: E402


class FakeSerial:
    def __init__(self):
        self.input = queue.Queue()
        self.writes = bytearray()
        self.closed = False
        self.settings = dict(baudrate=115200, bytesize=8, stopbits=1, parity='N',
                             xonxoff=False, rtscts=False, dsrdtr=False)

    def read(self, size):
        if self.closed:
            raise OSError('closed')
        try:
            item = self.input.get(timeout=.02)
        except queue.Empty:
            return b''
        if isinstance(item, Exception):
            raise item
        return item

    def write(self, data):
        if self.closed:
            raise OSError('closed')
        self.writes.extend(data)
        return len(data)

    def get_settings(self):
        return self.settings.copy()

    def apply_settings(self, settings):
        if settings.get('baudrate') == 123:
            raise OSError('unsupported baud')
        self.settings.update(settings)

    def close(self):
        self.closed = True


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.device = FakeSerial()
        self.service = SerialService(port='FAKE', tcp=0, control=0,
                                     serial_factory=lambda *_: self.device).start()
        self.addCleanup(self.service.close)
        self.client = Client(port=self.service.control_port)
        self.addCleanup(self.client.close)

    def wait_job(self, job):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = self.client.call('job.status', job_id=job['job_id'])
            if state['state'] not in ('queued', 'writing'):
                return state
            time.sleep(.01)
        self.fail('job did not finish')

    def test_hex_send_reports_actual_tx_without_inventing_rx(self):
        self.client.subscribe()
        job = self.client.call('send.hex', data='AA 55 01 02 FF')
        self.assertEqual(self.wait_job(job)['state'], 'written')
        self.assertEqual(self.device.writes, b'\xaa\x55\x01\x02\xff')
        event = self.client.next_event(timeout=1)
        events = [event]
        while event.get('event') != 'tx':
            event = self.client.next_event(timeout=1)
            events.append(event)
        self.assertEqual(base64.b64decode(event['data']), b'\xaa\x55\x01\x02\xff')
        self.assertFalse(any(e['event'] == 'rx' for e in events))

    def test_takeover_cancels_active_and_pending_jobs_and_invalidates_token(self):
        token = self.client.call('agent.acquire')['token']
        active = self.client.call('send', token=token, data='abcdef', chardelay=.2)
        pending = self.client.call('send', token=token, data='NEVER')
        deadline = time.monotonic() + 1
        while not self.device.writes and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertTrue(self.device.writes)
        self.assertEqual(self.client.call('agent.takeover')['owner'], 'human')
        written = bytes(self.device.writes)
        self.assertLess(len(written), 6)
        self.assertEqual(self.wait_job(active)['state'], 'cancelled')
        self.assertEqual(self.wait_job(pending)['written'], 0)
        for action in ('send', 'agent.heartbeat', 'serial.close', 'agent.acquire'):
            with self.assertRaises(RemoteError) as error:
                self.client.call(action, token=token, data='bad')
            self.assertEqual(error.exception.code, 'invalid_token')
        time.sleep(.25)
        self.assertEqual(self.device.writes, written)

    def test_exclusive_blocks_mutations_and_raw_writes_but_allows_observation(self):
        token = self.client.call('agent.acquire')['token']
        for action in ('send', 'serial.close', 'serial.configure', 'serial.open', 'service.stop'):
            with self.assertRaises(RemoteError) as error:
                self.client.call(action, data='bad')
            self.assertEqual(error.exception.code, 'occupied')
        self.assertTrue(self.client.call('status')['connected'])
        with socket.create_connection(('127.0.0.1', self.service.tcp_port), timeout=1) as raw:
            raw.sendall(b'BAD')
            # Rejected sends keep the raw connection alive and tell the
            # operator why, instead of disconnecting on the first keypress.
            raw.settimeout(2)
            self.assertIn('[串口桥]'.encode('utf-8'), raw.recv(200))
        self.assertEqual(self.device.writes, b'')
        self.client.call('agent.release', token=token)
        job = self.client.call('send', data='human')
        self.assertEqual(self.wait_job(job)['state'], 'written')

    def test_sends_do_not_interleave_and_busy_acquire_is_explicit(self):
        first = self.client.call('send', data='abc', chardelay=.03)
        second = self.client.call('send', data='XYZ')
        with self.assertRaises(RemoteError) as error:
            self.client.call('agent.acquire')
        self.assertEqual(error.exception.code, 'busy')
        self.wait_job(first)
        self.wait_job(second)
        self.assertEqual(self.device.writes, b'abcXYZ')

    def test_config_failure_preserves_actual_state_and_close_releases_only_device(self):
        self.client.call('serial.configure', baudrate=57600, parity='E')
        with self.assertRaises(RemoteError):
            self.client.call('serial.configure', baudrate=123)
        state = self.client.call('status')
        self.assertEqual(state['config']['baudrate'], 57600)
        self.assertEqual(state['config']['parity'], 'E')
        self.client.call('serial.close')
        time.sleep(.1)
        self.assertTrue(self.device.closed)
        self.assertFalse(self.client.call('status')['connected'])
        with self.assertRaises(RemoteError):
            self.client.call('send.hex', data='AA')

    def test_invalid_hex_and_ascii_are_rejected_before_any_write(self):
        for action, params in [('send.hex', {'data': 'AA 55 GG 01'}),
                               ('send.hex', {'data': 'AA 5'}),
                               ('send', {'data': '中文', 'encoding': 'ascii'})]:
            with self.assertRaises(RemoteError):
                self.client.call(action, **params)
        self.assertEqual(self.device.writes, b'')

    def test_call_channel_rebuilds_after_transport_death(self):
        # Regression: an idle GUI used to lose its call channel (30s control
        # socket timeout) while the subscription stayed alive; every later
        # send failed until a manual disconnect+connect. The client must
        # rebuild the call channel so only the in-flight call is lost.
        self.client.subscribe()
        # Call channel dies out-of-band; shutdown bypasses the makefile refcount.
        self.client.socket.shutdown(socket.SHUT_RDWR)
        self.client.socket.close()
        with self.assertRaises((OSError, EOFError, ValueError)):
            self.client.call('status')
        job = self.client.call('send', data='recovered')
        self.assertEqual(self.wait_job(job)['state'], 'written')
        self.assertEqual(self.device.writes, b'recovered')
        event = self.client.next_event(timeout=2)
        self.assertEqual(event.get('event'), 'state')  # subscription survived

    def start_scan(self, **overrides):
        """Kick a manual scan and block until it actually owns the device."""
        params = dict(mode='passive', bauds=[9600], seconds=.3, rounds=1, min_bytes=1)
        params.update(overrides)
        result = self.client.call('serial.autobaud', **params)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.service.scan_active:
                return result
            time.sleep(.01)
        self.fail('scan did not start')

    def test_agent_takeover_during_baud_scan_aborts_scan_first(self):
        # Regression: agent.takeover used to clear the scan transition without
        # stopping the scan, so the writer resumed (at the candidate baud)
        # while the scan thread still owned the device, and the scan could
        # still flip the baud under the human who had just taken over.
        self.start_scan()
        status = self.client.call('agent.takeover')
        self.assertEqual('human', status['owner'])
        self.assertFalse(self.service.scan_active)
        self.assertIsNone(self.service.transition)
        self.assertEqual(115200, self.device.settings['baudrate'])  # start restored
        job = self.client.call('send', data='after')
        self.assertEqual(self.wait_job(job)['state'], 'written')
        self.assertEqual(115200, self.device.settings['baudrate'])

    def test_device_actions_stay_busy_during_running_baud_scan(self):
        # Pin the dispatch contract the takeover fix relies on: while a scan
        # owns the device (transition set) regular actions are refused with
        # 'busy'; agent.takeover is the one action allowed through, and it
        # waits the scan out (regression test above). _device_action still
        # aborts a scan itself so the direct-call entry point stays safe.
        self.start_scan()
        with self.assertRaises(RemoteError) as error:
            self.client.call('serial.configure', baudrate=57600)
        self.assertEqual('busy', error.exception.code)

    def test_raw_send_rejection_keeps_connection_and_notifies(self):
        # Regression: a raw terminal was disconnected on the first rejected
        # send, so a human typing while an agent held the lease got kicked
        # and reconnected for every keypress.
        token = self.client.call('agent.acquire')['token']
        raw = socket.create_connection(('127.0.0.1', self.service.tcp_port), timeout=1)
        self.addCleanup(raw.close)
        time.sleep(.2)  # let the service register the raw client first
        raw.sendall(b'X')
        raw.settimeout(3)
        notice = raw.recv(200)
        self.assertIn('[串口桥]'.encode('utf-8'), notice)
        # Still connected: once the lease is back, raw bytes flow to the device.
        self.client.call('agent.release', token=token)
        time.sleep(.1)
        raw.sendall(b'OK')
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and b'OK' not in bytes(self.device.writes):
            time.sleep(.01)
        self.assertIn(b'OK', bytes(self.device.writes))

    def test_reader_survives_concurrent_raw_notice_drop(self):
        # Regression: _raw_notice dropped dead raw clients without the lock,
        # racing the reader's `del self.raw_clients[sock]` into a KeyError
        # that killed the reader thread and stopped all RX forwarding.
        stop = threading.Event()

        def hammer():
            while not stop.is_set():
                self.service._raw_notice('压力')
                time.sleep(0)  # yield: pressure without starving other threads

        hammer_thread = threading.Thread(target=hammer, daemon=True)
        hammer_thread.start()
        # Cleanups run LIFO: stop the hammer before joining it.
        self.addCleanup(hammer_thread.join)
        self.addCleanup(stop.set)
        for _round in range(40):
            try:
                raw = socket.create_connection(('127.0.0.1', self.service.tcp_port), timeout=1)
            except OSError:
                break
            outgoing = None
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                with self.service.lock:
                    outgoing = self.service.raw_clients.get(raw)
                if outgoing is not None:
                    break
                time.sleep(.005)
            if outgoing is not None:
                try:
                    while True:
                        outgoing.put_nowait(b'x' * 64)
                except queue.Full:
                    pass
                self.device.input.put(b'RACE' * 64)  # reader hits Full on this client
            time.sleep(.03)
            raw.close()  # release the slot now: the service caps live connections
        # The race rounds are over: stop the hammer so it stops flooding the
        # final client's queue, then verify the reader is still alive.
        stop.set()
        hammer_thread.join()
        # The reader must still be alive and forwarding device data.
        raw = socket.create_connection(('127.0.0.1', self.service.tcp_port), timeout=1)
        self.addCleanup(raw.close)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.service.lock:
                if len(self.service.raw_clients) >= 1:
                    break
            time.sleep(.01)
        self.device.input.put(b'AFTER' * 8)  # only the live reader forwards this
        seen = b''
        deadline = time.monotonic() + 3
        raw.settimeout(1)
        while time.monotonic() < deadline and b'AFTER' not in seen:
            try:
                seen += raw.recv(4096)
            except socket.timeout:
                continue
        self.assertIn(b'AFTER', seen)


class DriftSerial:
    """Device that transmits readable text only when read at its true baud."""

    def __init__(self, good_baud=921600):
        self.good = good_baud
        self.settings = dict(baudrate=115200, bytesize=8, stopbits=1, parity='N',
                             xonxoff=False, rtscts=False, dsrdtr=False)
        self.input = queue.Queue()
        self.writes = bytearray()
        self.closed = False

    def read(self, size):
        if self.closed:
            raise OSError('closed')
        time.sleep(0.001)  # one chunk per millisecond, like a real UART stream
        try:
            chunk = self.input.get(timeout=.02)
        except queue.Empty:
            return b''
        if self.settings['baudrate'] == self.good:
            return chunk
        return bytes(255 - byte for byte in chunk)  # bit-inverted: unreadable noise

    @property
    def in_waiting(self):
        return self.input.qsize()

    def write(self, data):
        if self.closed:
            raise OSError('closed')
        self.writes.extend(data)
        return len(data)

    def get_settings(self):
        return self.settings.copy()

    def apply_settings(self, settings):
        if settings.get('baudrate') == 123:
            raise OSError('unsupported baud')
        self.settings.update(settings)

    def close(self):
        self.closed = True


class AutoBaudTests(unittest.TestCase):
    def setUp(self):
        self.device = DriftSerial()
        self.service = SerialService(
            port='FAKE', tcp=0, control=0, serial_factory=lambda *_: self.device,
            auto_baud=dict(enabled=True, active=False, bauds=(921600,), seconds=0.05,
                           rounds=1, min_bytes=8, min_suspect_bytes=24,
                           window_seconds=2.0, cooldown_fail=60.0)).start()
        self.addCleanup(self.service.close)
        self.client = Client(port=self.service.control_port)
        self.addCleanup(self.client.close)

    def subscribe(self):
        self.client.subscribe()

    def wait_event(self, name, timeout=5):
        deadline = time.monotonic() + timeout
        seen = []
        while time.monotonic() < deadline:
            try:
                event = self.client.next_event(timeout=.1)
            except queue.Empty:
                continue
            seen.append(event)
            if event.get('event') == name:
                return event, seen
        self.fail(f'{name} event not observed; got {[e.get("event") for e in seen]}')

    def wait_scan_done(self, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.client.call('autobaud.status')
            if not state.get('scanning') and not state.get('requested'):
                return state
            time.sleep(.02)
        self.fail('scan did not finish')

    def test_auto_scan_switches_baud_on_sustained_garbage_without_writing(self):
        self.subscribe()
        for _ in range(500):
            self.device.input.put(b'hello world\r\n')
        event, _ = self.wait_event('baud_changed')
        self.assertEqual(115200, event['from'])
        self.assertEqual(921600, event['to'])
        self.assertEqual('auto', event['trigger'])
        state = self.wait_scan_done()
        self.assertEqual(921600, self.device.settings['baudrate'])
        self.assertEqual(921600, self.client.call('status')['config']['baudrate'])
        self.assertEqual(b'', bytes(self.device.writes))  # passive scan sends nothing
        self.assertIsNone(state['last_reason'])
        self.assertEqual('auto', state['last_change']['trigger'])

    def test_failed_auto_scan_restores_baud_and_starts_cooldown(self):
        self.subscribe()
        for _ in range(500):
            self.device.input.put(b'\xff\x00\x91\x03\x80\x00\xfe\x02')
        event, _ = self.wait_event('baud_scan')
        self.assertEqual('started', event['state'])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.client.call('autobaud.status')
            if state.get('last_reason'):
                break
            time.sleep(.02)
        self.assertEqual('no_signal', state['last_reason'])
        self.assertEqual(115200, self.device.settings['baudrate'])
        self.assertEqual(115200, self.client.call('status')['config']['baudrate'])
        self.assertGreater(state['cooldown_remaining'], 30)

    def test_manual_active_scan_writes_probes_and_reports_no_signal(self):
        self.subscribe()
        result = self.client.call('serial.autobaud', mode='active', bauds=[921600],
                                  seconds=0.05, rounds=2, min_bytes=4)
        self.assertTrue(result['requested'])
        with self.assertRaises(RemoteError) as error:
            self.client.call('serial.autobaud', mode='passive')
        self.assertEqual(error.exception.code, 'busy')
        state = self.wait_scan_done()
        # candidates = [current 115200, 921600] x 2 rounds x 1 probe each.
        self.assertEqual(b'\r' * 4, bytes(self.device.writes))
        self.assertEqual('no_signal', state['last_reason'])
        self.assertEqual(115200, self.device.settings['baudrate'])

    def test_serial_close_drops_pending_scan_request(self):
        # Regression: a queued (not yet started) scan request used to survive
        # an explicit release; 'requested' then stayed on forever, the CLI
        # wait reported bogus success and later scans answered 'busy'.
        # The transition guard keeps the monitor loop from picking the request
        # up; _device_action is invoked under the lock exactly as action()
        # calls it, because the action() entry refuses requests during a
        # transition.
        with self.service.lock:
            self.service.transition = 'baud_scan'
            self.service.scan_requested = dict(mode='passive', bauds=(921600,),
                                               seconds=0.05, rounds=1, min_bytes=8,
                                               probe=None, manual=True)
            self.service._device_action('serial.close', {})
        self.assertFalse(self.client.call('autobaud.status')['requested'])
        self.assertTrue(self.device.closed)

    def test_device_loss_drops_pending_scan_request(self):
        # Same contract for the unplug path: the reader's SerialException must
        # discard the pending request together with the device.
        with self.service.lock:
            self.service.transition = 'baud_scan'
            self.service.scan_requested = dict(mode='passive', bauds=(921600,),
                                               seconds=0.05, rounds=1, min_bytes=8,
                                               probe=None, manual=True)
        self.device.closed = True  # next read() raises, like a USB unplug
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = self.client.call('autobaud.status')
            if not state['requested']:
                break
            time.sleep(.02)
        else:
            self.fail('pending scan request survived the device loss')
        self.assertFalse(self.client.call('status')['connected'])
        self.assertTrue(self.device.closed)

    def test_agent_lease_blocks_auto_scan_until_released(self):
        self.subscribe()
        token = self.client.call('agent.acquire')['token']
        for _ in range(3000):
            self.device.input.put(b'hello world\r\n')
        time.sleep(.8)
        self.assertEqual(115200, self.device.settings['baudrate'])
        self.client.call('agent.release', token=token)
        event, _ = self.wait_event('baud_changed')
        self.assertEqual(921600, event['to'])

    def test_autobaud_actions_validate_input_and_connection(self):
        with self.assertRaises(RemoteError) as error:
            self.client.call('serial.autobaud', mode='turbo')
        self.assertEqual(error.exception.code, 'invalid_input')
        with self.assertRaises(RemoteError) as error:
            self.client.call('serial.autobaud', bauds=[0])
        self.assertEqual(error.exception.code, 'invalid_input')
        with self.assertRaises(RemoteError) as error:
            self.client.call('serial.autobaud.configure', bogus=1)
        self.assertEqual(error.exception.code, 'invalid_input')
        state = self.client.call('serial.autobaud.configure', enabled=False)
        self.assertFalse(state['enabled'])
        service = SerialService(port=None, tcp=0, control=0,
                                serial_factory=lambda *_: self.device).start()
        self.addCleanup(service.close)
        client = Client(port=service.control_port)
        self.addCleanup(client.close)
        with self.assertRaises(RemoteError) as error:
            client.call('serial.autobaud')
        self.assertEqual(error.exception.code, 'disconnected')

    def test_manual_baud_change_emits_event_and_raw_notice(self):
        self.subscribe()
        raw = socket.create_connection(('127.0.0.1', self.service.tcp_port), timeout=1)
        self.addCleanup(raw.close)
        time.sleep(.2)  # let the service register the raw client first
        self.client.call('serial.baud', baudrate=9600)
        event, _ = self.wait_event('baud_changed')
        self.assertEqual(9600, event['to'])
        self.assertEqual('manual', event['trigger'])
        raw.settimeout(2)
        self.assertIn('波特率'.encode('utf-8'), raw.recv(200))
        self.assertEqual(9600, self.client.call('status')['config']['baudrate'])


class SerialControlLeasePathTests(unittest.TestCase):
    """The Windows controller's -Exclusive path drives serial_control.py with
    plain --data flags (PS 5.1 cannot pass a JSON object through argv
    reliably), so that CLI must round-trip the whole one-shot lease against a
    real service: acquire → send --token --wait → release, with tokenless
    sends still blocked by `occupied` while the lease is held."""

    def setUp(self):
        self.device = FakeSerial()
        self.service = SerialService(port='FAKE', tcp=0, control=0,
                                     serial_factory=lambda *_: self.device).start()
        self.addCleanup(self.service.close)

    def run_cli(self, *argv):
        stdout = io.StringIO()
        args = ['serial_control.py', '--host', '127.0.0.1',
                '--control', str(self.service.control_port), *argv]
        with mock.patch.object(serial_control.sys, 'argv', args), \
                contextlib.redirect_stdout(stdout):
            code = serial_control.main()
        return code, stdout.getvalue()

    def wait_written(self, expected):
        deadline = time.monotonic() + 2
        while bytes(self.device.writes) != expected and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(expected, bytes(self.device.writes))

    def test_exclusive_controller_path_round_trip(self):
        code, out = self.run_cli('agent.acquire')
        self.assertEqual(0, code)
        lease = json.loads(out)['result']
        self.assertEqual(10.0, lease['timeout'])

        code, out = self.run_cli('send', '--data', 'lease-cmd', '--newline', 'cr',
                                 '--token', lease['token'], '--wait', '2')
        self.assertEqual(0, code)
        self.assertEqual('written', json.loads(out)['result']['state'])
        self.wait_written(b'lease-cmd\r')

        code, out = self.run_cli('agent.release', '--token', lease['token'])
        self.assertEqual(0, code)
        self.assertEqual('human', json.loads(out)['result']['owner'])

    def test_lease_blocks_tokenless_cli_send(self):
        _, out = self.run_cli('agent.acquire')
        token = json.loads(out)['result']['token']
        code, out = self.run_cli('send', '--data', 'sneaky', '--newline', 'cr', '--wait', '1')
        self.assertEqual(2, code)
        self.assertEqual('occupied', json.loads(out)['error']['code'])
        self.assertEqual(b'', bytes(self.device.writes))
        self.run_cli('agent.release', '--token', token)


class ReaderRobustnessTests(unittest.TestCase):
    """The 2026-10-23 silent RX death contract: a reader thread that dies or
    wedges must surface in status and stop the bridge, byte flow must be
    observable, and a baud scan must never issue a device.read() concurrent
    with the reader's (pyserial win32 backs every read() with ONE shared
    OVERLAPPED per Serial object; two in-flight reads can wedge both)."""

    def setUp(self):
        self.device = FakeSerial()
        self.service = SerialService(port='FAKE', tcp=0, control=0,
                                     serial_factory=lambda *_: self.device).start()
        self.addCleanup(self.service.close)
        self.client = Client(port=self.service.control_port)
        self.addCleanup(self.client.close)

    def wait_job(self, job):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = self.client.call('job.status', job_id=job['job_id'])
            if state['state'] not in ('queued', 'writing'):
                return state
            time.sleep(.01)
        self.fail('job did not finish')

    def test_status_counts_rx_and_tx_bytes_with_last_rx_timestamp(self):
        status = self.client.call('status')
        self.assertEqual(0, status['rx_bytes_total'])
        self.assertEqual(0, status['tx_bytes_total'])
        self.assertIsNone(status['last_rx_timestamp'])
        self.device.input.put(b'hello')
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = self.client.call('status')
            if status['rx_bytes_total'] >= 5:
                break
            time.sleep(.01)
        self.assertGreaterEqual(status['rx_bytes_total'], 5)
        self.assertIsNotNone(status['last_rx_timestamp'])
        job = self.client.call('send', data='abc')
        self.assertEqual(self.wait_job(job)['state'], 'written')
        self.assertGreaterEqual(self.client.call('status')['tx_bytes_total'], 3)

    def test_reader_thread_death_surfaces_in_status_then_stops_bridge(self):
        from serial_service import READER_STALL_SECONDS
        self.device.input.put(ValueError('boom'))
        error = None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                error = self.client.call('status').get('error')
            except (OSError, EOFError, ValueError):
                break  # bridge already stopped loudly
            if error:
                break
            time.sleep(.02)
        self.assertTrue(error, 'reader thread death never surfaced in status.error')
        self.assertIn('_reader', error)
        deadline = time.monotonic() + READER_STALL_SECONDS + 3
        while time.monotonic() < deadline and not self.service.stop.is_set():
            time.sleep(.05)
        self.assertTrue(self.service.stop.is_set(), 'watchdog never stopped the bridge')

    def test_reader_stall_watchdog_stops_the_bridge(self):
        from serial_service import READER_STALL_SECONDS
        gate = threading.Event()
        entered = threading.Event()
        original_read = self.device.read

        def wedged_read(size):
            entered.set()
            gate.wait(READER_STALL_SECONDS + 5)  # a read that never returns
            return original_read(size)

        self.device.read = wedged_read
        self.assertTrue(entered.wait(2), 'reader never entered device.read')
        deadline = time.monotonic() + READER_STALL_SECONDS + 3
        while time.monotonic() < deadline and not self.service.stop.is_set():
            time.sleep(.05)
        self.assertTrue(self.service.stop.is_set(), 'watchdog never stopped a wedged reader')
        self.assertIn('reader', self.service.last_error or '')
        gate.set()  # unblock so addCleanup can join the threads

    def test_scan_reads_exclusively_never_concurrent_with_reader(self):
        lock = threading.Lock()
        stats = dict(active=0, max_active=0, scan_reads=0)
        original_read = self.device.read

        def tracked_read(size):
            with lock:
                stats['active'] += 1
                stats['max_active'] = max(stats['max_active'], stats['active'])
                if threading.current_thread().name != '_reader':
                    stats['scan_reads'] += 1
            try:
                time.sleep(.05)  # widen each read so an overlap cannot hide
                return original_read(size)
            finally:
                with lock:
                    stats['active'] -= 1

        self.device.read = tracked_read
        for _ in range(60):
            self.device.input.put(b'0123456789abcdef')
        # The reader is essentially always inside a read with data streaming;
        # start the scan while that is true.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with lock:
                if stats['active'] >= 1:
                    break
            time.sleep(.005)
        self.client.call('serial.autobaud', mode='passive', bauds=[9600],
                         seconds=.2, rounds=1, min_bytes=1)
        # Wait for the scan to actually run to completion before judging the
        # overlap counter (pre-fix, reader reads share the counter because the
        # worker threads are unnamed; the scan-done poll bounds the window).
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.client.call('autobaud.status')
            if not state.get('scanning') and not state.get('requested'):
                break
            time.sleep(.02)
        self.assertEqual(1, stats['max_active'],
                         'reader and scan were inside device.read at the same time')

    def test_logger_opens_with_a_session_header_line(self):
        device = FakeSerial()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / 'session.log'
            service = SerialService(port='FAKE', tcp=0, control=0,
                                    serial_factory=lambda *_: device,
                                    log=str(log_path)).start()
            try:
                device.input.put(b'payload')
                content = b''
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if log_path.exists():
                        content = log_path.read_bytes()
                        if b'payload' in content:
                            break
                    time.sleep(.02)
            finally:
                service.close()
            self.assertIn(b'payload', content)
            self.assertTrue(content.startswith(b'=== bridge session start '),
                            f'log file does not open with a session header: {content[:80]!r}')


class FakeProc:
    """Process-terminal stand-in: no line discipline, hook invoked on write."""

    is_process_terminal = True
    no_respawn = True
    echo_tx = True

    def __init__(self):
        self.echo_hook = None
        self.closed = False
        self.eof = False
        self.writes = bytearray()

    def read(self, size):
        if self.eof:
            raise OSError('终端进程已退出 (exit code=0)；用 serial.open 重新拉起')
        return b''

    def write(self, data):
        if self.closed or self.eof:
            raise OSError('终端已关闭')
        self.writes.extend(data)
        if self.echo_hook is not None:
            self.echo_hook(bytes(data))
        return len(data)

    def get_settings(self):
        return dict(port='proc://fake', baudrate=115200, bytesize=8, stopbits=1,
                    parity='N', xonxoff=False, rtscts=False, dsrdtr=False)

    def apply_settings(self, settings):
        pass

    def close(self):
        self.closed = True


class ProcessEndpointTests(unittest.TestCase):
    def setUp(self):
        self.devices = []

        def factory(port, baud):
            device = FakeProc()
            self.devices.append(device)
            return device

        self.service = SerialService(port='proc://fake', tcp=0, control=0,
                                     serial_factory=factory).start()
        self.addCleanup(self.service.close)
        deadline = time.monotonic() + 3
        while self.service.device is None and time.monotonic() < deadline:
            time.sleep(.01)
        self.client = Client(port=self.service.control_port)
        self.addCleanup(self.client.close)

    def raw_client(self):
        raw = socket.create_connection(('127.0.0.1', self.service.tcp_port), timeout=1)
        self.addCleanup(raw.close)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if self.service.raw_clients:
                break
            time.sleep(.01)
        return raw

    def wait_disconnected(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if not self.client.call('status')['connected']:
                return
            time.sleep(.02)
        self.fail('service still reports connected after process exit')

    def test_status_reports_process_endpoint_kind(self):
        status = self.client.call('status')
        self.assertEqual(status['endpoint_kind'], 'process')
        self.assertIn('proc-terminal', status['capabilities'])

    def test_send_echoes_written_line_to_raw_clients(self):
        # Payload shape comes from the device's echo hook (FakeProc passes the
        # written chunk through verbatim); the real CRLF-processed echo is
        # covered in test_process_terminal.py.
        raw = self.raw_client()
        job = self.client.call('send', data=base64.b64encode(b'hi\r').decode(), format='base64')
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.client.call('job.status', job_id=job['job_id'])['state'] == 'written':
                break
            time.sleep(.01)
        raw.settimeout(2)
        self.assertIn(b'hi\r', raw.recv(200))

    def test_process_exit_disables_reconnect_and_keeps_service_alive(self):
        self.devices[0].eof = True
        self.wait_disconnected()
        status = self.client.call('status')
        self.assertFalse(status['reconnect'])
        self.assertIn('终端进程已退出', status['error'])
        time.sleep(1.2)  # longer than the 1s maintenance respawn interval
        self.assertEqual(len(self.devices), 1, 'released process terminal was respawned')

    def test_serial_open_respawns_process_after_exit(self):
        self.devices[0].eof = True
        self.wait_disconnected()
        status = self.client.call('serial.open', port='proc://fake', baudrate=115200)
        self.assertTrue(status['connected'])
        self.assertEqual(len(self.devices), 2)
        self.assertEqual(status['endpoint_kind'], 'process')

    def test_baud_change_is_refused_for_process_terminal(self):
        with self.assertRaises(RemoteError) as ctx:
            self.client.call('serial.baud', baudrate=9600)
        self.assertEqual(ctx.exception.code, 'unsupported')

    def test_online_baud_scan_is_refused_for_process_terminal(self):
        with self.assertRaises(RemoteError) as ctx:
            self.client.call('serial.autobaud', mode='passive')
        self.assertEqual(ctx.exception.code, 'unsupported')


if __name__ == '__main__':
    unittest.main()
