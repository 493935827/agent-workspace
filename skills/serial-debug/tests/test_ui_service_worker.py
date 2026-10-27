"""ServiceWorker hardening: bridge-death probe and non-fatal takeover failure.

Covers the two review P1s on the GUI service worker:
- a dead bridge used to leave the session "connected" forever (the event
  socket died silently and the call socket was only touched on send), so the
  run loop now probes `status` and reports error -> closed;
- a failed takeover used to emit the fatal 'error' event, poisoning a
  healthy session (state='error' while the transport was alive); it now
  emits a dedicated non-fatal 'takeover_failed' event.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import queue
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

try:
    from PySide6.QtWidgets import QApplication
    from serial_gui_qt import ServiceWorker, Workbench
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from serial_service_client import RemoteError


class FakeServiceClient:
    """ServiceClient stand-in with scriptable call outcomes."""

    def __init__(self, status_fail_after=None, takeover_error='busy', connected=True):
        self.host = self.port = None
        self.status_calls = 0
        self.status_fail_after = status_fail_after  # None: status never fails
        self.takeover_error = takeover_error        # None: takeover succeeds
        self.connected = connected
        self.actions = []
        self.serial_open_calls = 0
        self.events = queue.Queue()
        self.gaps = 0
        self.closed = False

    def subscribe(self):
        pass

    def call(self, action, **params):
        self.actions.append(action)
        if action == 'serial.open':
            self.serial_open_calls += 1
            return {'connected': True, 'owner': 'agent', 'instance': 'fake',
                    'config': {'baudrate': 115200}}
        if action == 'status':
            self.status_calls += 1
            if self.status_fail_after is not None and self.status_calls > self.status_fail_after:
                raise OSError('bridge is gone')
            if not self.connected:
                return {'connected': False, 'error': 'released'}
            return {'connected': True, 'owner': 'agent'}
        if action == 'agent.takeover':
            if self.takeover_error:
                raise RemoteError('busy', 'Device transition in progress')
            return {'owner': 'human'}
        raise RemoteError('unknown_action', action)

    def next_event(self, timeout=0):
        # Same contract as the real client: queue.Empty propagates on an
        # empty queue (pump_events relies on it to end the drain loop).
        return self.events.get(timeout=timeout)

    def close(self):
        self.closed = True


def make_worker(client, events, device='FAKE', **kwargs):
    service = dict(host='127.0.0.1', control=1, device=device, baud='115200', name=device)
    return ServiceWorker(service, events, lambda host, port: client, **kwargs)


def collect(events):
    kinds = []
    while True:
        try:
            _worker, kind, _payload, _stamp = events.get_nowait()
        except queue.Empty:
            return kinds
        kinds.append(kind)


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class ServiceWorkerProbeTests(unittest.TestCase):
    def test_bridge_death_is_detected_by_status_probe(self):
        # Regression: with the bridge process dead the run loop used to spin
        # forever: the event socket died silently (gaps nobody consumed) and
        # the call socket was only touched when the user sent. The session
        # stayed "connected" with no RX and no error.
        client = FakeServiceClient(status_fail_after=0)
        events = queue.Queue()
        worker = make_worker(client, events, probe_interval=.05)
        worker.start()
        worker.join(3)
        self.assertFalse(worker.is_alive(), 'worker never noticed the dead bridge')
        self.assertTrue(client.closed)
        kinds = collect(events)
        self.assertIn('error', kinds)
        self.assertIn('closed', kinds)

    def test_healthy_bridge_survives_periodic_probing(self):
        client = FakeServiceClient()
        events = queue.Queue()
        worker = make_worker(client, events, probe_interval=.05)
        worker.start()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and client.status_calls < 5:
            time.sleep(.01)
        self.assertGreaterEqual(client.status_calls, 5, 'status probe never ran')
        worker.stopped.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        kinds = collect(events)
        self.assertNotIn('error', kinds)
        self.assertIn('closed', kinds)

    def test_takeover_failure_is_non_fatal(self):
        # Regression: a failed takeover emitted the fatal 'error' event, which
        # poisoned the healthy session (state='error' although the bridge and
        # the device were fine; sends were rejected and the takeover button
        # disabled itself).
        client = FakeServiceClient(takeover_error='busy')
        events = queue.Queue()
        worker = make_worker(client, events)
        worker.takeover.set()
        worker.start()
        deadline = time.monotonic() + 2
        kinds = []
        while time.monotonic() < deadline:
            kinds = collect(events)
            if 'takeover_failed' in kinds and 'opened' in kinds:
                break
            time.sleep(.02)
        self.assertIn('takeover_failed', kinds)
        self.assertNotIn('error', kinds)
        self.assertFalse(worker.stopped.is_set())
        self.assertTrue(worker.is_alive())
        worker.stopped.set()
        worker.join(2)


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class ProcessEndpointWorkerTests(unittest.TestCase):
    """proc:// service sessions attach to the running bridge without reopening."""

    def run_worker_briefly(self, client, device, probe_interval=.05):
        events = queue.Queue()
        worker = make_worker(client, events, device=device, probe_interval=probe_interval)
        worker.start()
        return worker, events

    def test_proc_device_attaches_without_serial_open(self):
        client = FakeServiceClient(connected=True)
        worker, events = self.run_worker_briefly(client, 'proc://powershell')
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and 'opened' not in collect(events):
            time.sleep(.01)
        worker.stopped.set()
        worker.join(2)
        self.assertNotIn('serial.open', client.actions)
        self.assertEqual(client.serial_open_calls, 0)
        self.assertIn('status', client.actions)

    def test_proc_device_bootstraps_released_endpoint(self):
        client = FakeServiceClient(connected=False)
        worker, events = self.run_worker_briefly(client, 'proc://powershell')
        kinds = []
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            kinds += collect(events)
            if 'opened' in kinds:
                break
            time.sleep(.01)
        worker.stopped.set()
        worker.join(2)
        kinds += collect(events)
        self.assertEqual(client.serial_open_calls, 1, 'released endpoint was not respawned')
        self.assertIn('opened', kinds)

    def test_serial_device_still_opens_on_attach(self):
        # Guard the existing attach behavior for COM endpoints.
        client = FakeServiceClient()
        worker, events = self.run_worker_briefly(client, 'FAKE')
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and 'opened' not in collect(events):
            time.sleep(.01)
        worker.stopped.set()
        worker.join(2)
        self.assertEqual(client.serial_open_calls, 1)


@unittest.skipUnless(HAVE_QT, 'PySide6 is required for workbench integration tests')
class TakeoverFailureGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        self.fail('workbench did not reach expected state')

    def records(self, window, index, tag):
        return [r['text'] for r in window.sessions[index]['records'] if r['tag'] == tag]

    def test_takeover_failure_keeps_service_session_connected(self):
        client = FakeServiceClient(takeover_error='busy')
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = Workbench(persist=False,
                           settings_path=Path(directory.name) / 'settings.json',
                           port_provider=lambda: [],
                           service_client_factory=lambda host, port: client)
        self.addCleanup(window.close)
        index = window.create_session('service:127.0.0.1:1/FAKE')
        window.sessions[index]['service'] = dict(host='127.0.0.1', control=1,
                                                 device='FAKE', baud='115200')
        self.assertTrue(window.connect_session(index))
        self.until(lambda: window.sessions[index]['state'] == 'connected')
        self.until(lambda: window.service_takeover.isEnabled())
        window.service_takeover.click()
        self.until(lambda: any('接管失败' in text for text in self.records(window, index, 'WARN')))
        # The transport is alive: the session must NOT be poisoned into error.
        self.assertEqual('connected', window.sessions[index]['state'])
        self.assertFalse(window.service_takeover.isHidden())

    def test_proc_service_session_refuses_online_baud_scan(self):
        client = FakeServiceClient()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = Workbench(persist=False,
                           settings_path=Path(directory.name) / 'settings.json',
                           port_provider=lambda: [],
                           service_client_factory=lambda host, port: client)
        self.addCleanup(window.close)
        index = window.create_session('service:127.0.0.1:1/proc://powershell')
        window.sessions[index]['service'] = dict(host='127.0.0.1', control=1,
                                                 device='proc://powershell', baud='115200')
        window.scan_baud_online()
        self.assertTrue(any('没有波特率' in text for text in self.records(window, index, 'ERROR')))


if __name__ == '__main__':
    unittest.main()
