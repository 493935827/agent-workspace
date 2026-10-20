"""Baud-rate scoring and live re-scan shared by the offline detector and the bridge.

The offline detector (windows/detect_serial_baud.py) opens the port itself per
candidate. The bridge instead sweeps candidates on an already-open device via
``scan_open_device`` while pausing its reader/writer threads. Both share the
same scoring and winner rules so offline and online detection agree.
"""
import math
import time
from dataclasses import dataclass

import serial


DEFAULT_BAUDS = (115200, 57600, 38400, 19200, 9600, 230400, 460800, 921600)

# Live drift monitor: readable-text ratio below the threshold over a sliding
# window with at least MIN bytes marks the session as garbled (wrong baud).
MONITOR_THRESHOLD = 0.55
MONITOR_WINDOW = 3.0
MONITOR_MIN_BYTES = 48
SCAN_SECONDS = 0.5          # per-candidate listen time for live re-scans
COOLDOWN_SUCCESS = 5.0      # after a switch/confirmation before re-checking
COOLDOWN_FAIL = 20.0        # after an inconclusive scan before retrying


@dataclass(frozen=True)
class SampleScore:
    baud: int
    byte_count: int
    printable_ratio: float
    control_ratio: float
    score: float


def readability(data):
    """Return 0..1 printable-text ratio; invalid UTF-8 and controls count against.

    U+FFFD (the decode replacement character) is formally "printable" but marks
    bytes that were NOT decoded, so it is subtracted again here.
    """
    if not data:
        return 0.0
    decoded = data.decode("utf-8", errors="replace")
    invalid = decoded.count("\ufffd")
    printable = sum(char in "\b\t\n\r" or char.isprintable() for char in decoded) - invalid
    return max(0, printable) / len(decoded)


def score_sample(baud, data):
    """Score ASCII/UTF-8 console text while penalizing binary-looking data."""
    if not data:
        return SampleScore(baud, 0, 0.0, 1.0, float("-inf"))

    decoded = data.decode("utf-8", errors="replace")
    printable = sum(char in "\b\t\n\r" or char.isprintable() for char in decoded)
    invalid = decoded.count("\ufffd")
    controls = sum(not char.isprintable() and char not in "\b\t\n\r" for char in decoded)
    printable_ratio = printable / len(decoded)
    control_ratio = (controls + invalid) / len(decoded)
    line_bonus = 6.0 if b"\n" in data or b"\r" in data else 0.0
    diversity_bonus = min(len(set(data)), 16) / 4.0
    length_bonus = min(math.log2(len(data) + 1), 8.0) * 3.0
    score = printable_ratio * 100.0 - control_ratio * 80.0 + line_bonus + diversity_bonus + length_bonus
    return SampleScore(baud, len(data), printable_ratio, control_ratio, score)


def rank_samples(samples, min_bytes):
    """Rank collected samples per baud and pick one unambiguous winner."""
    scores = sorted(
        (score_sample(baud, bytes(data)) for baud, data in samples.items()),
        key=lambda item: item.score,
        reverse=True,
    )
    eligible = [
        item
        for item in scores
        if item.byte_count >= min_bytes
        and item.printable_ratio >= 0.75
        and item.control_ratio <= 0.08
    ]
    if not eligible:
        return None, scores, "no_signal"
    if len(eligible) > 1 and eligible[0].score - eligible[1].score < 8.0:
        return None, scores, "ambiguous"
    return eligible[0].baud, scores, None


SAMPLE_CAP = 512 * 1024


def _read_window(device, seconds, collector, abort=None):
    deadline = time.monotonic() + max(seconds, 0.0)
    while time.monotonic() < deadline:
        if abort is not None and abort():
            return False
        if len(collector) >= SAMPLE_CAP:
            return True
        try:
            chunk = device.read(4096)
        except (OSError, serial.SerialException):
            return False
        if chunk:
            collector.extend(chunk)
    return True


def _apply_baud(device, baud, applier):
    try:
        if applier is not None:
            applier(baud)
        else:
            device.apply_settings({"baudrate": baud})
        return True
    except (OSError, serial.SerialException, ValueError):
        return False


def _start_baud(device):
    try:
        return int(device.get_settings().get("baudrate"))
    except (AttributeError, OSError, ValueError, TypeError):
        return None


def scan_open_device(device, bauds, seconds, rounds, min_bytes, probe=None, attempts=1,
                     reader=None, applier=None, writer=None, should_abort=None):
    """Sweep candidate baud rates on an already-open device.

    ``reader(device, seconds, collector)`` defaults to a plain read loop;
    ``applier(baud)`` and ``writer(device, data)`` default to the device's own
    ``apply_settings``/``write``. The scan always restores the starting baud
    before returning; applying a winning baud is the caller's decision.
    ``should_abort()`` is polled between candidates and between reads so the
    bridge can reclaim the device mid-sweep (takeover, device actions); an
    abort reports the same ``'interrupted'`` reason as a failed read.

    Returns ``(winner_baud_or_None, scores, reason)`` with the same contract as
    :func:`rank_samples`.
    """
    if reader is None:
        def reader(device, seconds, collector):
            # The built-in reader honors cooperative aborts; custom readers
            # keep their (device, seconds, collector) contract.
            return _read_window(device, seconds, collector, abort=should_abort)
    start = _start_baud(device)
    candidates = []
    for baud in bauds:
        baud = int(baud)
        if baud not in candidates:
            candidates.append(baud)
    samples = {baud: bytearray() for baud in candidates}
    interrupted = False
    try:
        for _ in range(max(1, rounds)):
            for baud in candidates:
                if should_abort is not None and should_abort():
                    interrupted = True
                    break
                if not _apply_baud(device, baud, applier):
                    continue
                if probe:
                    window = max(seconds, 0.0) / max(1, attempts)
                    for _attempt in range(max(1, attempts)):
                        try:
                            if writer is not None:
                                writer(device, probe)
                            else:
                                device.write(probe)
                        except (OSError, serial.SerialException):
                            interrupted = True
                            break
                        if not reader(device, window, samples[baud]):
                            interrupted = True
                            break
                    if interrupted:
                        break
                else:
                    if not reader(device, seconds, samples[baud]):
                        interrupted = True
                        break
            if interrupted:
                break
    finally:
        if start is not None:
            _apply_baud(device, start, applier)
    if interrupted:
        return None, [score_sample(baud, bytes(data)) for baud, data in samples.items()], "interrupted"
    return rank_samples({baud: bytes(data) for baud, data in samples.items()}, min_bytes)
