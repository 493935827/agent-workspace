import base64
import queue
import socket
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from serial_service import SerialService
from serial_client import Client, RemoteError


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
            self.assertEqual(raw.recv(100), b'')
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


if __name__ == '__main__':
    unittest.main()
