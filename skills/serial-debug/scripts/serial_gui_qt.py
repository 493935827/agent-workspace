"""Qt serial workbench. Real I/O; the visual demo remains a separate entry point."""
from __future__ import annotations

import argparse
import base64
import collections
import codecs
import json
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import serial
from serial.tools import list_ports
from PySide6.QtCore import QEvent, QTimer, Qt, QByteArray
from PySide6.QtGui import QColor, QCursor, QFont, QKeySequence, QShortcut, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QInputDialog, QLabel, QLineEdit,
    QMenu, QMenuBar, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSystemTrayIcon,
    QTextEdit, QVBoxLayout, QWidget)

from serial_common import AlertMonitor, AnsiLogParser, parse_macro_line
from serial_baud_scan import (COOLDOWN_FAIL, COOLDOWN_SUCCESS, DEFAULT_BAUDS, MONITOR_MIN_BYTES,
                              MONITOR_THRESHOLD, MONITOR_WINDOW, SCAN_SECONDS, readability, scan_open_device)
from serial_gui_qt_prototype import Preview, icon, parse_hex, row, set_role
from serial_service_client import Client as ServiceClient, RemoteError as ServiceError

def _app_dir() -> Path:
    """用户数据目录（设置/宏/日志）。

    源码运行取脚本目录，行为与历史版本一致；打包成 exe 后 __file__ 指向
    临时解压目录（退出即删），因此改取 exe 同目录，不可写时回退 %APPDATA%。
    """
    if not getattr(sys, 'frozen', False):
        return Path(__file__).resolve().parent
    exe_dir = Path(sys.executable).resolve().parent
    probe = exe_dir / '.serial_workbench_write_test'
    try:
        probe.touch()
        probe.unlink()
        return exe_dir
    except OSError:
        appdata = Path(os.environ.get('APPDATA') or Path.home()) / 'SerialWorkbench'
        appdata.mkdir(parents=True, exist_ok=True)
        return appdata

TIME_FORMATS = ('时分秒', '时分秒.毫秒', '日期 时分秒', '日期 时分秒.毫秒')
DEFAULT_OPTIONS = dict(timestamps=True, time_format=TIME_FORMATS[1], wrap=False,
    show_rx=True, show_tx=True, show_keybytes=False, display_mode='ASCII', log_level=0,
    rx_encoding='UTF-8', encoding='UTF-8', ending='CR', auto_scroll=True,
    case=False, whole=False, tags=[], paused=False, save_policy='手动保存',
    log_timestamp=True, log_format=TIME_FORMATS[1], log_append=False,
    log_encoding='UTF-8', log_newline='LF', log_auto=False,
    log_directory=str(_app_dir() / 'logs'),
    autobaud_monitor=True, autobaud_probe=False)

# 每个会话的屏幕缓冲上限；LogView.setMaximumBlockCount(5000) 与此保持一致。
RECORD_LIMIT = 5000
# 搜索高亮重扫防抖：RX 流速时搜索框每条记录都全文档重扫会冻住主线程
# （handoff 20261027-1610），合并为停顿后一次；命中数到达上限即停止收集。
FIND_DEBOUNCE_MS = 200
FIND_MATCH_LIMIT = 500
# 影响既有记录渲染方式的选项：rerender 只在这些取值与上次构建不同（或暂停
# 期间积压了未渲染记录）时才重建会话视图，其余情况视图随记录实时渲染保持同步。
RENDER_OPTION_KEYS = ('timestamps', 'time_format', 'wrap', 'show_rx', 'show_tx',
                      'display_mode', 'log_level', 'tags')
# 打开超大日志时只解析末尾这么多字节（从换行边界起读），避免卡住界面。
LOG_TAIL_BYTES = 8 * 1024 * 1024


def timestamp(stamp, fmt):
    value = stamp.strftime('%Y-%m-%d %H:%M:%S' if fmt.startswith('日期') else '%H:%M:%S')
    return value + (f'.{stamp.microsecond // 1000:03d}' if fmt.endswith('毫秒') else '')


# 打开日志文件时识别的行首时间戳形态，从最具体到最宽松依次尝试。
_DATE = r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'
_CLOCK = r'(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?'
LOG_STAMP_PATTERNS = tuple((re.compile(rx), dated) for rx, dated in (
    (rf'\[{_DATE}[ T]{_CLOCK}\] ?', True),   # [2026-10-20 14:06:01.123]（本工具默认格式）
    (rf'{_DATE}[ T]{_CLOCK} ?', True),       # 2026-10-20 14:06:01.123 / 2026-10-20T14:06:01
    (rf'\[{_CLOCK}\] ?', False),             # [14:06:01.123]（本工具「时分秒」格式）
    (rf'{_CLOCK} ?', False),                 # 14:06:01.123
))


def match_log_stamp(line, base_date):
    """Recognize a leading timestamp; return (match, datetime, has_date) or None.

    没有日期部分的时间戳按 base_date（通常取日志文件自身的日期）补齐；候选
    不合法（如 25:61:61、不存在的闰日）时继续尝试更宽松的形态，最终退回
    普通文本行处理。
    """
    for pattern, dated in LOG_STAMP_PATTERNS:
        m = pattern.match(line)
        if not m:
            continue
        g = m.groups()
        try:
            if dated:
                stamp = datetime(int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4]), int(g[5]),
                                 int((g[6] or '').ljust(6, '0')[:6]))
            else:
                stamp = datetime(base_date.year, base_date.month, base_date.day, int(g[0]),
                                 int(g[1]), int(g[2]), int((g[3] or '').ljust(6, '0')[:6]))
        except ValueError:
            continue
        return m, stamp, dated
    return None


def decode_log_bytes(data):
    """Decode raw log bytes; return (text, 面向用户的编码名称).

    UTF-16 只认带 BOM 的数据——Python 的 utf-16 解码器在无 BOM 时会按
    本机字节序硬解，偶数长度的 GBK/ASCII 内容会被错误解码成乱码。
    """
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return data.decode('utf-16'), 'UTF-16'
        except UnicodeError:
            pass
    for name, encoding in (('UTF-8', 'utf-8-sig'), ('GBK', 'gbk')):
        try:
            return data.decode(encoding), name
        except UnicodeError:
            continue
    return data.decode('gbk', errors='replace'), 'GBK'


def clean_log_spans(spans):
    """Strip device erase markers from imported text; return (spans, removed)."""
    cleaned, removed = [], 0
    for value, style in spans:
        text = value.replace('\x08', '').replace('\x7f', '')
        removed += len(value) - len(text)
        if text:
            cleaned.append((text, style))
    return cleaned, removed


def parse_log_text(text, base_stamp):
    """Split decoded log text into LOG records, recognizing leading timestamps.

    识别出行首时间戳的行开始一条新记录：时间戳并入记录的 stamp、从正文里
    去掉（显示时由「显示时间戳」统一渲染）；其后无时间戳的行并入同一条
    记录——本工具写出的日志正是把一条记录折行保存，这样能还原原始结构。
    整个文件都识别不到时间戳时，每行单独成条并按 base_stamp（文件修改
    时间）标注。ANSI 颜色序列照常解析。返回 (records, stats)。
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    matches = [match_log_stamp(line, base_stamp.date()) for line in lines]
    # 只有存在时间戳的文件才把无时间戳行当作记录折行；纯文本日志逐行成条。
    merge = any(matched is not None for matched in matches)
    parser = AnsiLogParser()
    records = []
    stats = dict(lines=len(lines), stamps=0, dated=0, merged=0, plain=0, erases=0)
    for line, matched in zip(lines, matches):
        source = line[matched[0].end():] if matched else line
        spans, removed = clean_log_spans(parser.feed(source + '\n'))
        stats['erases'] += removed
        chunk = ''.join(value for value, _ in spans)
        if matched is not None:
            _, stamp, dated = matched
            records.append(dict(tag='LOG', text=chunk, stamp=stamp, raw=b'', spans=spans))
            stats['stamps'] += 1
            stats['dated'] += 1 if dated else 0
        elif records and merge:
            previous = records[-1]
            previous['text'] += chunk
            previous['spans'] += spans
            stats['merged'] += 1
        else:
            records.append(dict(tag='LOG', text=chunk, stamp=base_stamp, raw=b'', spans=spans))
            stats['plain'] += 1
    return records, stats


class SerialWorker(threading.Thread):
    """Own the port on one thread; no serial call or wait blocks Qt's GUI thread."""
    def __init__(self, options, events, factory=serial.serial_for_url):
        super().__init__(daemon=True, name=f"serial:{options['port']}")
        self.options = dict(options)
        # `options` is the session dict; per-session switches live in options['options'].
        session_options = options.get('options')
        self.session_options = session_options if isinstance(session_options, dict) else {}
        self.events = events
        self.factory = factory
        self.commands = queue.Queue(maxsize=256)
        self.controls = queue.Queue(maxsize=16)
        self.stopped = threading.Event()
        self._scan_request = None
        self._suspect_window = collections.deque()
        self._cooldown_until = 0.0

    def emit(self, kind, payload=None):
        # Backpressure bounds memory without silently dropping received bytes.
        while True:
            try:
                self.events.put((self, kind, payload, datetime.now()), timeout=.05)
                return
            except queue.Full:
                if self.stopped.is_set() and kind not in ('closed', 'error', 'sent', 'rx',
                                                          'baud_notice'):
                    return

    def run(self):
        port = None
        try:
            o = self.options
            port = self.factory(o['port'], baudrate=int(o['baud']),
                bytesize=int(o['fmt'][0]), parity=o['fmt'][1], stopbits=int(o['fmt'][2]),
                rtscts=o.get('flow') == 'RTS/CTS', timeout=.02, write_timeout=.3)
            self.emit('opened')
            while not self.stopped.is_set():
                if self._drain_controls(port):
                    continue
                try:
                    token, payload, shown = self.commands.get_nowait()
                except queue.Empty:
                    pass
                else:
                    offset = 0
                    while offset < len(payload) and not self.stopped.is_set():
                        count = port.write(payload[offset:])
                        if not count:
                            raise OSError('串口写入未完成')
                        offset += count
                    if offset == len(payload):
                        self.emit('sent', (token, payload, shown))
                data = port.read(min(port.in_waiting or 1, 8192))
                if data:
                    self.emit('rx', data)
                    if self.session_options.get('autobaud_monitor'):
                        self._feed_suspect(data, time.monotonic())
                if self._scan_request:
                    self._run_scan(port)
        except Exception as exc:
            self.emit('error', str(exc))
        finally:
            if port is not None:
                try:
                    port.close()
                except Exception as exc:
                    self.emit('error', str(exc))
            self.emit('closed')

    def _drain_controls(self, port):
        ran = False
        while True:
            try:
                action = self.controls.get_nowait()
            except queue.Empty:
                return ran
            if action.get('action') == 'scan':
                # A manual scan replaces any pending automatic one and runs now;
                # the scan itself owns the port while RX/TX pause in this thread.
                self._run_scan(port, dict(mode=action.get('mode') or 'passive', manual=True))
                ran = True

    def _feed_suspect(self, data, now):
        window = self._suspect_window
        window.append((now, data))
        horizon = now - MONITOR_WINDOW
        while window and window[0][0] < horizon:
            window.popleft()
        if now < self._cooldown_until:
            return
        if sum(len(chunk) for _, chunk in window) < MONITOR_MIN_BYTES:
            return
        combined = b''.join(chunk for _, chunk in window)
        if readability(combined) <= MONITOR_THRESHOLD:
            window.clear()
            self._scan_request = dict(
                mode='active' if self.session_options.get('autobaud_probe') else 'passive',
                manual=False)

    def _run_scan(self, port, request=None):
        request = request or self._scan_request or {}
        self._scan_request = None
        active = request.get('mode') == 'active'
        o = self.options
        start_baud = int(o['baud'])
        candidates = [start_baud] + [b for b in DEFAULT_BAUDS if b != start_baud]
        self.emit('baud_notice', ('主动扫描波特率中（发送回车探测；候选：%s），收发暂停' if active
                                  else '被动扫描波特率中（不发送数据；候选：%s），收发暂停')
                  % '、'.join(str(b) for b in candidates))
        try:
            winner, _scores, reason = scan_open_device(
                port, candidates, SCAN_SECONDS, 1, 4 if active else 12,
                probe=b'\r' if active else None)
        except (OSError, serial.SerialException, ValueError) as exc:
            self.emit('baud_notice', f'波特率扫描出错：{exc}；已保持 {start_baud}')
            self._cooldown_until = time.monotonic() + COOLDOWN_FAIL
            return
        now = time.monotonic()
        if winner is not None and winner != start_baud:
            try:
                port.apply_settings({'baudrate': winner})
            except (OSError, serial.SerialException, ValueError) as exc:
                self.emit('baud_notice', f'切换波特率 {winner} 失败：{exc}；已保持 {start_baud}')
                self._cooldown_until = now + COOLDOWN_FAIL
                return
            o['baud'] = str(winner)
            self._cooldown_until = now + COOLDOWN_SUCCESS
            self.emit('baud_changed', (start_baud, winner))
        elif winner == start_baud:
            self._cooldown_until = now + COOLDOWN_SUCCESS
            self.emit('baud_notice', f'在线检测完成：当前波特率 {start_baud} 有效')
        else:
            hint = ('设备可读输出不足：让设备多打印，或改用主动探测（发送回车）。'
                    if not active else '设备没有应答回车探测；请确认固件支持，或改用被动监听。')
            self._cooldown_until = now + COOLDOWN_FAIL
            self.emit('baud_notice', f'未能确定波特率（{reason}）：已保持 {start_baud}。{hint}')


class ServiceWorker(threading.Thread):
    """Own one managed-service management session on one thread.

    Emits the same event kinds as SerialWorker (opened/rx/sent/error/closed)
    so records, macros, alerts and views work unchanged, plus 'service_state'
    (service status dict) and 'peer_tx' (bytes another client wrote).
    """

    def __init__(self, service, events, client_factory=ServiceClient, probe_interval=1.0):
        super().__init__(daemon=True, name=f"service:{service['host']}:{service['control']}")
        self.service = dict(service)
        self.options = {'port': self.service.get('name') or
                        f"service:{service['host']}:{service['control']}/{service['device']}"}
        self.events = events
        self.client_factory = client_factory
        self.probe_interval = probe_interval
        self.commands = queue.Queue(maxsize=256)
        self.controls = queue.Queue(maxsize=16)
        self.stopped = threading.Event()
        self.takeover = threading.Event()
        self.status = {}

    def emit(self, kind, payload=None):
        while True:
            try:
                self.events.put((self, kind, payload, datetime.now()), timeout=.05)
                return
            except queue.Full:
                if self.stopped.is_set() and kind not in ('closed', 'error', 'sent', 'rx',
                                                          'peer_tx', 'service_state', 'baud_notice',
                                                          'takeover_failed'):
                    return

    def run(self):
        client = None
        pending = {}   # our job_id -> (token, raw, shown)
        tx_bytes = {}  # job_id -> bytes another client wrote
        try:
            c = self.service
            client = self.client_factory(c['host'], int(c['control']))
            client.subscribe()
            if str(c['device']).startswith('proc://'):
                # A process bridge owns its child shell already; calling
                # serial.open here would kill and respawn the shared session.
                # Attach as-is, and only bootstrap an endpoint that exited.
                status = client.call('status')
                if not status.get('connected'):
                    status = client.call('serial.open', port=c['device'],
                                         baudrate=int(c.get('baud') or 115200))
            else:
                status = client.call('serial.open', port=c['device'], baudrate=int(c['baud']))
            if not status.get('connected'):
                raise ServiceError('open_failed', status.get('error') or '设备打开失败')
            self.status = status
            self.emit('service_state', status)
            self.emit('opened')
            next_probe = time.monotonic() + self.probe_interval
            probe_failures = 0
            last_gaps = client.gaps
            while not self.stopped.is_set():
                # The event subscription can die out-of-band (dead bridge);
                # nobody consumes `gaps`, so probe the call channel instead of
                # spinning forever on a session that only looks connected.
                if client.gaps != last_gaps:
                    last_gaps = client.gaps
                    next_probe = 0.0
                now = time.monotonic()
                if now >= next_probe:
                    next_probe = now + self.probe_interval
                    try:
                        client.call('status')
                        probe_failures = 0
                    except Exception as exc:
                        # One failure may be a transient channel hiccup (the
                        # client rebuilds it); a second failure on the fresh
                        # channel means the bridge is gone.
                        probe_failures += 1
                        if probe_failures >= 2:
                            raise OSError(f'共享串口桥已失联：{exc}') from exc
                if self.takeover.is_set():
                    self.takeover.clear()
                    try:
                        client.call('agent.takeover')
                    except Exception as exc:
                        # Non-fatal: the bridge and the device are fine, only
                        # the takeover was refused. A fatal 'error' here used
                        # to poison the healthy session.
                        self.emit('takeover_failed', f'接管失败：{exc}')
                self.drain_controls(client)
                self.drain_commands(client, pending)
                self.pump_events(client, pending, tx_bytes)
                self.stopped.wait(.01)
        except Exception as exc:
            self.emit('error', str(exc))
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            self.emit('closed')

    def drain_controls(self, client):
        while True:
            try:
                action = self.controls.get_nowait()
            except queue.Empty:
                return
            if action.get('action') == 'scan':
                try:
                    client.call('serial.autobaud', mode=action.get('mode') or 'passive')
                except Exception as exc:
                    self.emit('baud_notice', f'在线检测无法开始：{exc}')

    def drain_commands(self, client, pending):
        while True:
            try:
                token, raw, shown = self.commands.get_nowait()
            except queue.Empty:
                return
            try:
                job = client.call('send', data=base64.b64encode(raw).decode(), format='base64')
            except Exception as exc:
                self.emit('send_failed', (token, f'发送被拒绝：{exc}'))
                continue
            pending[job['job_id']] = (token, raw, shown)

    def pump_events(self, client, pending, tx_bytes):
        while True:
            try:
                event = client.next_event(0)
            except Exception:
                break
            kind = event.get('event')
            if kind == 'rx':
                self.emit('rx', base64.b64decode(event.get('data', '')))
            elif kind == 'tx':
                job_id = event.get('job_id')
                if job_id not in pending:
                    tx_bytes[job_id] = tx_bytes.get(job_id, b'') + base64.b64decode(event.get('data', ''))
            elif kind == 'job':
                job_id = event.get('job_id')
                state = event.get('state')
                if job_id in pending:
                    if state in ('written', 'unknown', 'cancelled'):
                        token, raw, shown = pending.pop(job_id)
                        if state == 'written':
                            self.emit('sent', (token, raw, shown))
                        elif state == 'unknown':
                            self.emit('send_failed', (token, '发送结果未知，设备可能已收到部分数据；不要自动重发'))
                        else:
                            self.emit('send_failed', (token, '发送已取消'))
                    # 'queued'/'writing' keep waiting for a terminal job event.
                elif state == 'written' and job_id in tx_bytes:
                    self.emit('peer_tx', tx_bytes.pop(job_id))
            elif kind == 'baud_scan':
                state = event.get('state')
                if state == 'started':
                    text = ('在线波特率扫描中（%s；候选：%s），收发暂停'
                            % ('主动' if event.get('mode') == 'active' else '被动',
                               '、'.join(str(b) for b in event.get('candidates', []))))
                elif state == 'unchanged':
                    text = f'在线检测完成：波特率 {event.get("baud")} 有效'
                elif state == 'failed':
                    text = f'在线检测失败（{event.get("reason")}）：已保持原波特率'
                else:
                    text = f'波特率扫描：{state}'
                self.emit('baud_notice', text)
            elif kind == 'baud_changed':
                self.emit('baud_changed', (event.get('from'), event.get('to')))
            elif kind == 'state':
                self.status = event.get('state') or {}
                self.emit('service_state', self.status)


class ServiceStopWorker(threading.Thread):
    """One-shot helper that stops a shared bridge process and releases its port.

    Works whether or not the session currently holds a live ServiceWorker:
    it opens a short-lived control connection, takes the lease back from an
    agent if needed, then asks the service to stop itself (which closes the
    device before the process exits).
    """

    def __init__(self, service, events, client_factory=ServiceClient):
        super().__init__(daemon=True, name=f"service-stop:{service['host']}:{service['control']}")
        self.service = dict(service)
        self.events = events
        self.client_factory = client_factory

    def emit(self, kind, payload=None):
        self.events.put((self, kind, payload, datetime.now()))

    def run(self):
        c = self.service
        target = f"{c['host']}:{int(c['control'])}"
        client = None
        try:
            client = self.client_factory(c['host'], int(c['control']))
            status = client.call('status')
            instance = status.get('instance')
            if not instance:
                raise ServiceError('identity', '服务未提供实例标识，拒绝停止')
            if status.get('owner') == 'agent':
                self.emit('baud_notice', 'Agent 正持有设备，先收回租约再停止桥…')
                client.call('agent.takeover')
            client.call('service.stop', instance=instance)
            self.emit('service_stop_result', (True, f'共享串口桥已停止，串口已释放（{target}）'))
        except Exception as exc:
            self.emit('service_stop_result', (False, f'停止共享串口桥失败（{target}）：{exc}'))
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass


def usb_serial_rank(port):
    """Sort key for attached ports: USB VID/PID first, Bluetooth last, natural COM order."""
    text = f'{port.description} {port.hwid}'.upper()
    has_usb_id = port.vid is not None and port.pid is not None
    is_bluetooth = 'BTHENUM' in text or 'BLUETOOTH' in text
    natural = [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', port.device.upper())]
    return (not has_usb_id, is_bluetooth, natural)


def is_usb_serial(port):
    """An attached USB serial port: VID/PID present and not Bluetooth."""
    text = f'{port.description} {port.hwid}'.upper()
    return (port.vid is not None and port.pid is not None
            and 'BTHENUM' not in text and 'BLUETOOTH' not in text)


class Workbench(Preview):
    def __init__(self, *, settings_path=None, persist=True, serial_factory=serial.serial_for_url,
                 port_provider=list_ports.comports, service_client_factory=ServiceClient, **kwargs):
        self.ready = False
        self.persist = persist
        self.settings_path = Path(settings_path or _app_dir() / 'serial_qt_settings.json')
        self.macros_path = self.settings_path.with_name(self.settings_path.stem + '_macros.json')
        self.serial_factory = serial_factory
        self.port_provider = port_provider
        self.service_client_factory = service_client_factory
        self.events = queue.Queue(maxsize=512)
        self.workers = {}
        self.retired = []
        self.macro_job = None
        self.detecting = False
        self._closing = False
        self._restoring = False
        self._status_error = None
        self.notice_windows = []
        self.named_macros = {}
        super().__init__(**kwargs)
        self.setWindowTitle('Serial Workbench — Qt 串口工作台')
        self.timer.stop()
        self.sessions[0].update(port='', name='串口会话', state='disconnected', connected_at=None, mode=1)
        # Preview's seeded sessions are removed without ever opening hardware.
        while len(self.sessions) > 1:
            self.sessions.pop()
            view = self.views.pop()
            self.logs.removeWidget(view)
            view.deleteLater()
            self.devices.takeItem(self.devices.count()-1)
        self.initialize_session(self.sessions[0])
        self.install_controls()
        self.ready = True
        self.active = -1
        self.switch(0)
        self.restore_settings()
        self.refresh_devices()
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(30)
        self.poll_timer.timeout.connect(self.poll)
        self.poll_timer.start()
        self.detect_timer = QTimer(self)
        self.detect_timer.setInterval(500)
        self.detect_timer.timeout.connect(self.poll_ports)
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(5000)
        self.save_timer.timeout.connect(self.save_settings)
        if persist:
            self.save_timer.start()

    def seed(self):
        pass

    def initialize_session(self, s):
        s.update(options=dict(DEFAULT_OPTIONS, tags=[]), records=[],
            decoder=codecs.getincrementaldecoder('utf-8')(errors='replace'), ansi=AnsiLogParser(),
            alerts=AlertMonitor(), log_file=None, log_path=None, file_line_start=True,
            display_line_start=True, received=0, rx_bytes=0, sent=0, mode=1,
            locked=False, history=[], sent_log=[], pending=0)
        s['render_sync'] = self.render_fingerprint(s)

    def install_controls(self):
        if getattr(self, '_find_timer', None) is None:
            self._find_timer = QTimer(self)
            self._find_timer.setSingleShot(True)
            self._find_timer.setInterval(FIND_DEBOUNCE_MS)
            self._find_timer.timeout.connect(self.find_now)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(lambda i: self.close_session(self.tabs.tabData(i)))
        self.tabs.setTabText(0, '选择串口')
        self.ending.addItem('无')
        self.wrap.toggled.disconnect()
        self.wrap.toggled.connect(self.rerender)
        self.inspector.setMovable(True)
        self.modules = [(self.inspector.widget(i), self.inspector.tabText(i)) for i in range(self.inspector.count())]
        # 「更多」只留会话与界面入口；配置统一进右侧「设置」页分区，文件动作归「文件」菜单。
        menu = self.more.menu()
        for action in list(menu.actions()):
            if action.text() in ('模拟设备异常', '关于预览'):
                menu.removeAction(action)
        menu.addAction('关闭当前会话', lambda: self.close_session(self.active))
        menu.addAction('布局模块…', self.show_modules)
        menu.addAction('关于工作台', self.about)
        # Also expose log opening where save lives: the 文件 menubar menu.
        menubar = self.findChild(QMenuBar)
        file_menu = menubar.actions()[0].menu() if menubar is not None and menubar.actions() else None
        if file_menu is not None:
            before = file_menu.actions()[0]
            open_action = file_menu.addAction('打开日志文件…', self.open_log_dialog, 'Ctrl+O')
            file_menu.removeAction(open_action)
            file_menu.insertAction(before, open_action)
        # Surface functional controls in the matching settings sections, keeping the shell unchanged.
        note = self.settings_note
        note.setText('设置仅作用于当前会话；文件日志独立于显示过滤。')
        sections = self.settings_sections
        # 日志文件：持续日志开关 + 打开/文件设置入口（对话框承载具体字段）。
        files = sections['files']
        self.logging_button = QPushButton('开始持续日志…')
        self.logging_button.clicked.connect(self.toggle_logging)
        self.logging_button.setToolTip('把当前会话的收发内容持续写入日志文件')
        files.addWidget(self.logging_button)
        for title, callback, tip in [('打开日志文件…', self.open_log_dialog, '读取日志文件回放到当前会话（Ctrl+O）'),
                                     ('时间戳与文件设置…', self.show_file_settings, '文件日志的时间戳格式、编码、换行与目录')]:
            b = QPushButton(title)
            b.clicked.connect(callback)
            b.setToolTip(tip)
            files.addWidget(b)
        # 提醒。
        alerts = sections['提醒']
        alert_button = QPushButton('条件提醒…')
        alert_button.clicked.connect(self.show_alert_settings)
        alert_button.setToolTip('命中关键字或错误时弹窗/气泡提醒')
        alerts.addWidget(alert_button)
        recount_button = QPushButton('提醒重新计数')
        recount_button.clicked.connect(self.reset_alerts)
        recount_button.setToolTip('把条件提醒的已命中计数清零')
        alerts.addWidget(recount_button)
        # 波特率。
        baud = sections['波特率']
        self.autobaud_monitor = QCheckBox('乱码自动重扫波特率')
        self.autobaud_monitor.setToolTip('连接期间收到持续乱码（多为设备中途换了波特率）时，自动用候选波特率重扫并切换；被动方式不发送任何数据')
        self.autobaud_probe = QCheckBox('自动重扫允许主动探测')
        self.autobaud_probe.setToolTip('允许自动重扫向设备发送回车探测（适合中途换波特率且平时安静的设备）；默认关闭')
        self.baud_scan_button = QPushButton('在线检测波特率')
        self.baud_scan_button.clicked.connect(self.scan_baud_online)
        self.baud_scan_button.setToolTip('保持当前连接，扫描候选波特率并在确认后切换')
        baud.addWidget(row(self.autobaud_monitor, None, self.baud_scan_button))
        baud.addWidget(self.autobaud_probe)
        # 共享串口桥。
        bridge = sections['共享串口桥']
        self.service_connect = QPushButton('连接共享服务…')
        self.service_connect.clicked.connect(self.connect_service_dialog)
        self.service_connect.setToolTip('接入本机共享串口桥，作为人工客户端查看与发送')
        self.service_takeover = QPushButton('终止 Agent 并接管')
        self.service_takeover.clicked.connect(self.request_takeover)
        self.service_takeover.setVisible(False)
        self.service_takeover.setToolTip('收回共享服务的控制权，取消 Agent 排队任务后恢复人工控制')
        self.service_stop = QPushButton('停止桥并释放端口')
        self.service_stop.clicked.connect(self.stop_service_bridge)
        self.service_stop.setVisible(False)
        self.service_stop.setToolTip('停止共享串口桥进程并释放串口；Agent 与其他客户端的连接会一并断开')
        for b in (self.service_connect, self.service_takeover, self.service_stop):
            bridge.addWidget(b)
        self.search.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search.customContextMenuRequested.connect(self.search_menu)
        QShortcut(QKeySequence('F3'), self, activated=self.next_match)
        QShortcut(QKeySequence('Shift+F3'), self, activated=lambda: self.next_match(-1))
        QShortcut(QKeySequence('Ctrl+Shift+W'), self, activated=lambda: self.close_session(self.active))
        self.interval = QSpinBox()
        self.interval.setRange(0, 60000)
        self.interval.setValue(500)
        self.interval.setSuffix(' ms')
        self.interval.setAccessibleName('宏默认间隔，毫秒')
        self.macro_stop = QPushButton('停止')
        self.macro_stop.clicked.connect(self.stop_macro)
        self.macro_stop.setEnabled(False)
        self.macro_save = QPushButton('命名保存…')
        self.macro_save.clicked.connect(self.save_editor_macro)
        self.macro_progress = QLabel('宏：未运行')
        self.editor.layout().insertWidget(2, row(QLabel('默认间隔'), self.interval, self.macro_save, self.macro_stop))
        self.editor.layout().addWidget(self.macro_progress)
        self.macro_run.setText('运行宏')
        self.editor.layout().itemAt(0).widget().setText('宏编辑器 · [port=COM34, delay=500] 命令')
        self.tray = QSystemTrayIcon(icon('terminal'), self)
        self.tray.setToolTip('Serial Workbench')
        tray_menu = QMenu(self)
        tray_menu.addAction('显示工作台', self.showNormal)
        self.tray.setContextMenu(tray_menu)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def options(self, index=None):
        return self.sessions[self.active if index is None else index]['options']

    def capture_session(self):
        if not self.ready or self._restoring or self.active < 0:
            return
        s = self.sessions[self.active]
        s.update(draft=self.command.text(), mode=self.mode.currentIndex(), query=self.search.text())
        o = s['options']
        for key in ('timestamps', 'wrap', 'show_rx', 'show_tx', 'show_keybytes', 'auto_scroll'):
            o[key] = getattr(self, key).isChecked()
        for key in ('display_mode', 'rx_encoding', 'encoding', 'ending', 'save_policy'):
            o[key] = getattr(self, key).currentText()
        o.update(log_level=self.log_level.currentIndex(), tags=sorted(self.tag_filters), paused=self.paused)
        o['autobaud_monitor'] = self.autobaud_monitor.isChecked()
        o['autobaud_probe'] = self.autobaud_probe.isChecked()

    def switch(self, index):
        if not self.ready:
            return super().switch(index)
        if not 0 <= index < len(self.sessions):
            return
        self.capture_session()
        self.active = -1
        s = self.sessions[index]
        o = s['options']
        for key in ('timestamps', 'wrap', 'show_rx', 'show_tx', 'show_keybytes', 'auto_scroll'):
            w = getattr(self, key)
            w.blockSignals(True)
            w.setChecked(o[key])
            w.blockSignals(False)
        for key in ('display_mode', 'rx_encoding', 'encoding', 'ending', 'save_policy'):
            w = getattr(self, key)
            w.blockSignals(True)
            w.setCurrentText(o[key])
            w.blockSignals(False)
        for key in ('autobaud_monitor', 'autobaud_probe'):
            w = getattr(self, key)
            w.blockSignals(True)
            w.setChecked(o.get(key, key == 'autobaud_monitor'))
            w.blockSignals(False)
        self.log_level.blockSignals(True)
        self.log_level.setCurrentIndex(o['log_level'])
        self.log_level.blockSignals(False)
        self.tag_filters = set(o['tags'])
        self.paused = o['paused']
        self.pending = s['pending']
        for name, chip in self.filter_buttons.items():
            chip.setChecked(name in self.tag_filters if self.tag_filters else name == '全部')
        super().switch(index)
        b = self.pause_tool
        b.blockSignals(True)
        b.setChecked(self.paused)
        b.setText('恢复接收' if self.paused else '暂停接收')
        b.blockSignals(False)
        self.pause_badge.setVisible(self.paused)
        self.rerender()

    def create_session(self, port):
        duplicate = next((i for i, s in enumerate(self.sessions) if s['port'].casefold() == port.casefold()), None)
        if duplicate is not None:
            self.devices.setCurrentRow(duplicate)
            return duplicate
        # Base creation switches immediately; initialize new dictionaries before that switch.
        index = super().create_session(port)
        self.views[index].setAccessibleName('串口接收日志；直接发送模式下输入串口按键')
        return index

    def refresh_devices(self):
        if self.ready:
            for s in self.sessions:
                if 'options' not in s:
                    self.initialize_session(s)
        super().refresh_devices()

    def new_session(self):
        ports = [p.device for p in self.port_provider()]
        port, ok = QInputDialog.getItem(self, '新建串口会话', '串口名称（可手动输入）：', ports, 0, True)
        if ok and port.strip():
            self.create_session(port.strip())

    def detect(self):
        if self.detecting:
            self.detecting = False
            self.detect_timer.stop()
            self.state.setText('已停止等待新串口')
            return
        try:
            ports = list(self.port_provider())
        except Exception as exc:
            self.report_error(str(exc))
            return
        # 自动检测：优先连接已接入的 USB 串口（排除蓝牙）。唯一候选直接连，
        # 不再弹窗；多个候选时列表预选排序最优的一个；没有 USB 串口才等待。
        usb = sorted((p for p in ports if is_usb_serial(p)), key=usb_serial_rank)
        if len(usb) == 1:
            self.connect_session(self.create_session(usb[0].device))
            return
        labels = {p.device: f'{p.device} · {p.description}' for p in ports}
        usb_items = [labels[p.device] for p in usb]
        other_items = [labels[device] for device in sorted(set(labels) - {p.device for p in usb})]
        wait = '等待新设备插入'
        items = [wait] + usb_items + other_items
        port, ok = QInputDialog.getItem(self, '检测串口', '选择连接，或等待新设备插入：', items,
                                        1 if usb_items else 0, False)
        if not ok:
            return
        if port == wait:
            self.known_ports = {p.device for p in ports}
            self.detecting = True
            self.detect_timer.start()
            self.state.setText('等待新串口插入 · 再次点击检测可取消')
        elif port:
            self.connect_session(self.create_session(port.split(' · ')[0].strip()))

    def poll_ports(self):
        try:
            current = {p.device for p in self.port_provider()}
        except Exception as exc:
            self.detect_timer.stop()
            self.detecting = False
            self.report_error(str(exc))
            return
        added = sorted(current - self.known_ports)
        self.known_ports = current
        if added:
            self.detect_timer.stop()
            self.detecting = False
            # One inserted device is unambiguous; multiple devices stay selectable.
            if len(added) == 1:
                self.connect_session(self.create_session(added[0]))
            else:
                self.state.setText('检测到多个新串口：' + ' / '.join(added) + '；请新建会话选择')

    def connection_settings(self):
        s = self.sessions[self.active]
        d = QDialog(self)
        d.setWindowTitle('串口连接设置')
        f = QFormLayout(d)
        widgets = {}
        choices = dict(port=[p.device for p in self.port_provider()],
            baud=['9600', '57600', '115200', '460800', '921600'],
            fmt=['8N1', '8N2', '8E1', '8O1', '7E1', '7O1'], flow=['无', 'RTS/CTS'])
        for key, title in [('port', '串口'), ('baud', '波特率'), ('fmt', '数据格式'), ('flow', '流控')]:
            w = QComboBox()
            w.addItems(choices[key])
            w.setEditable(key in ('port', 'baud'))
            w.setCurrentText(s[key])
            w.setEnabled(s['state'] not in ('connected', 'connecting') and not s.get('worker'))
            widgets[key] = w
            f.addRow(title, w)
        buttons = self.dialog_buttons(d, f)
        buttons.accepted.disconnect()
        show_error = self.inline_form_error(f)

        def accept():
            values = {k: w.currentText().strip() for k, w in widgets.items()}
            try:
                baud = int(values['baud'])
            except ValueError:
                baud = 0
            if not values['port'] or baud <= 0:
                show_error('请输入串口及正整数波特率')
                return
            if any(other is not s and other['port'].casefold() == values['port'].casefold() for other in self.sessions):
                show_error('该串口已有会话')
                return
            s.update(values)
            d.accept()
        buttons.accepted.connect(accept)
        if d.exec():
            self.refresh_devices()
            self.title.setText(s['port'])
            for i in range(self.tabs.count()):
                if self.tabs.tabData(i) == self.active:
                    self.tabs.setTabText(i, s['port'] + '    ' + s['name'])
            self.update_state()

    def toggle_connection(self):
        s = self.sessions[self.active]
        if s.get('worker'):
            self.disconnect_session(s)
        else:
            if not s['port']:
                self.connection_settings()
            if s['port']:
                self.connect_session(self.active)

    def connect_service_dialog(self):
        s = self.sessions[self.active]
        d = QDialog(self)
        d.setWindowTitle('连接共享串口服务')
        f = QFormLayout(d)
        host = QLineEdit('127.0.0.1')
        control = QLineEdit('8889')
        port = QComboBox()
        port.addItems([p.device for p in self.port_provider()])
        port.addItems(['proc://powershell', 'proc://cmd', 'proc://python'])
        port.setEditable(True)
        baud = QComboBox()
        baud.addItems(['9600', '57600', '115200', '460800', '921600'])
        baud.setEditable(True)
        baud.setCurrentText('57600')
        for title, w in [('服务地址（仅限本机）', host), ('控制端口', control),
                         ('目标串口 / proc:// 终端', port), ('波特率', baud)]:
            f.addRow(title, w)
        buttons = self.dialog_buttons(d, f)
        buttons.accepted.disconnect()
        show_error = self.inline_form_error(f)

        def accept():
            try:
                control_port = int(control.text().strip() or '8889')
            except ValueError:
                control_port = 0
            try:
                baud_value = int(baud.currentText().strip())
            except ValueError:
                baud_value = 0
            device = port.currentText().strip()
            if device.startswith('proc://'):
                # A process terminal has no baud rate; any placeholder passes.
                baud_value = 115200
            elif not device or baud_value <= 0:
                show_error('请填写目标串口和正整数波特率')
                return
            if control_port <= 0:
                show_error('控制端口需为正整数')
                return
            d.accept()
        buttons.accepted.connect(accept)
        if not d.exec():
            return
        device = port.currentText().strip()
        baud_text = baud.currentText().strip() or ('115200' if device.startswith('proc://') else '')
        service = dict(host=host.text().strip() or '127.0.0.1',
                       control=int(control.text().strip() or '8889'),
                       device=device, baud=baud_text)
        name = f"service:{service['host']}:{service['control']}/{service['device']}"
        index = self.create_session(name)
        self.sessions[index]['service'] = service
        self.connect_session(index)

    def request_takeover(self):
        s = self.sessions[self.active]
        worker = s.get('worker')
        if isinstance(worker, ServiceWorker):
            worker.takeover.set()

    def stop_service_bridge(self):
        s = self.sessions[self.active]
        if not s.get('service'):
            self.report_error('当前会话未接入共享服务，无法停止桥')
            return
        if s.get('service_stop_pending'):
            return
        service = s['service']
        device = service.get('device') or '串口'
        if device.startswith('proc://'):
            detail = ('桥进程将退出，其 shell 子进程一并结束；'
                      'Agent 与其他客户端的连接会断开。')
            title = '停止共享终端桥'
        else:
            detail = ('桥进程将退出，Agent 与其他客户端的连接会断开；'
                      '之后其他工具可以直接打开该串口。')
            title = '停止共享串口桥'
        box = QMessageBox(QMessageBox.Icon.Warning, title,
                          f'停止 {service["host"]}:{service["control"]} 上的桥（{device}）？\n\n{detail}',
                          parent=self)
        stop = box.addButton('停止桥并释放端口', QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton('取消', QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not stop:
            return
        s['service_stop_pending'] = True
        self.append(self.active, 'SYS', f'正在停止共享串口桥（{service["host"]}:{service["control"]}）…')
        stopper = ServiceStopWorker(s['service'], self.events, self.service_client_factory)
        self.workers[stopper] = s
        stopper.start()
        self.update_state()

    def scan_baud_online(self):
        s = self.sessions[self.active]
        if (s.get('service') or {}).get('device', '').startswith('proc://'):
            self.report_error('进程终端没有波特率，无需在线检测')
            return
        worker = s.get('worker')
        if worker is None or s['state'] != 'connected':
            self.report_error('请先连接串口，再使用在线波特率检测')
            return
        items = ['被动监听（不发送数据，设备需持续输出）', '主动探测（发送回车，适合安静设备）']
        mode, ok = QInputDialog.getItem(self, '在线检测波特率', '检测方式（串口保持连接）：',
                                        items, 1 if s['options']['autobaud_probe'] else 0, False)
        if not ok:
            return
        mode = 'active' if mode.startswith('主动') else 'passive'
        if mode == 'active':
            self.append(self.active, 'WARN', '主动探测会向设备发送回车字节')
        worker.controls.put({'action': 'scan', 'mode': mode})

    def connect_session(self, index):
        self.capture_session()
        s = self.sessions[index]
        if s.get('worker') or not s['port']:
            return False
        if any(w.is_alive() and w.options['port'].casefold() == s['port'].casefold() for w in self.retired):
            self.report_error('串口仍在释放，请稍后再连接')
            return False
        o = s['options']
        s['decoder'] = codecs.getincrementaldecoder(o['rx_encoding'].lower())(errors='replace')
        s['decoder_encoding'] = o['rx_encoding']
        s['ansi'].reset()
        s['state'] = 'connecting'
        if s.get('service'):
            w = ServiceWorker(s['service'], self.events, self.service_client_factory)
        else:
            w = SerialWorker(s, self.events, self.serial_factory)
        s['worker'] = w
        self.workers[w] = s
        w.start()
        self.refresh_devices()
        self.update_state()
        return True

    def disconnect_session(self, s):
        if self.macro_job and any(target is s for target in self.macro_job['targets']):
            self.stop_macro('目标串口断开，宏已停止')
        worker = s.get('worker')
        if worker:
            worker.stopped.set()
        s['state'] = 'disconnected'
        s['connected_at'] = None
        s['alerts'].reset()
        self.refresh_devices()
        self.update_state()

    def poll(self):
        self.capture_session()
        deadline = time.monotonic() + .012
        dirty = False
        while time.monotonic() < deadline:
            try:
                w, kind, payload, stamp = self.events.get_nowait()
            except queue.Empty:
                break
            s = self.workers.get(w)
            if s is None:
                continue
            if not any(s is item for item in self.sessions):
                self.workers.pop(w, None)
                continue
            index = next(i for i, item in enumerate(self.sessions) if item is s)
            if kind == 'opened' and not w.stopped.is_set():
                s.update(state='connected', connected_at=stamp)
                s['alerts'].reset(time.monotonic())
                self.append(index, 'SYS', '串口连接已建立')
                if s['options']['log_auto']:
                    self.start_logging(index=index, automatic=True)
            elif kind == 'rx':
                self.receive(index, payload, stamp)
            elif kind == 'sent':
                token, raw, shown = payload
                s['sent'] += len(raw)
                # Empty submissions (Enter on a bare prompt, blank macro lines,
                # empty HEX input) carry no text to show; stay silent instead
                # of printing bare TX lines. Byte counters still track them.
                if shown:
                    self.add_record(index, 'TX', shown + '\n', stamp, raw=raw)
                if self.macro_job and token is self.macro_job.get('token'):
                    self.macro_ack()
            elif kind == 'peer_tx':
                # Another client (typically an agent) wrote through the service.
                shown = payload.decode(s['options']['rx_encoding'].lower(), errors='replace')
                self.add_record(index, 'TX', shown + '\n', stamp, raw=payload)
            elif kind == 'service_state':
                s['service_status'] = payload
                if self.sessions[self.active] is s:
                    self.update_state()
            elif kind == 'baud_notice':
                self.append(index, 'SYS', payload)
            elif kind == 'service_stop_result':
                ok, message = payload
                s.pop('service_stop_pending', None)
                self.workers.pop(w, None)
                if ok:
                    self.append(index, 'SYS', message)
                    # The bridge is gone; retire any live client worker now
                    # instead of leaving a zombie "connected" session behind.
                    if s.get('worker'):
                        self.disconnect_session(s)
                else:
                    self.append(index, 'ERROR', message)
                    if self.sessions[self.active] is s:
                        self._status_error = (message, time.monotonic() + 8)
            elif kind == 'baud_changed':
                old, new = payload
                s['baud'] = str(new)
                if s.get('service'):
                    s['service']['baud'] = str(new)
                self.append(index, 'SYS', f'波特率已从 {old} 切换为 {new}')
            elif kind == 'send_failed':
                token, message = payload
                self.append(index, 'WARN', message)
                if self.macro_job and token is self.macro_job.get('token'):
                    self.stop_macro(message)
            elif kind == 'takeover_failed':
                # Non-fatal: the transport is alive; the operator can retry.
                self.append(index, 'WARN', payload)
            elif kind == 'error':
                s.update(state='error', connected_at=None)
                self.append(index, 'ERROR', payload)
                if self.macro_job and any(t is s for t in self.macro_job['targets']):
                    self.stop_macro('串口错误，宏已停止')
            elif kind == 'closed':
                tail = s['decoder'].decode(b'', final=True)
                if tail:
                    self.receive_text(index, tail, stamp)
                self.stop_logging(index)
                if s['options']['save_policy'] == '会话结束自动保存':
                    self.save_snapshot(index, self.default_log_path(s))
                if s['state'] != 'error':
                    s['state'] = 'disconnected'
                s['connected_at'] = None
                s['alerts'].reset()
                s.pop('worker', None)
                self.workers.pop(w, None)
                self.retired.append(w)
            dirty = True
        self.retired = [w for w in self.retired if w.is_alive()]
        for i in reversed(range(len(self.sessions))):
            s = self.sessions[i]
            if s.get('close_requested') and not s.get('worker'):
                self.remove_session(i)
        if self.events.empty():
            for s in self.sessions:
                if s['state'] == 'connected':
                    self.notify_alerts(s, s['alerts'].check(time.monotonic()))
        if dirty:
            self.refresh_devices()
        self.update_state()

    def receive(self, index, raw, stamp=None):
        s = self.sessions[index]
        stamp = stamp or datetime.now()
        encoding = s['options']['rx_encoding']
        if s.get('decoder_encoding') != encoding:
            tail = s['decoder'].decode(b'', final=True)
            if tail:
                self.receive_text(index, tail, stamp)
            s['decoder'] = codecs.getincrementaldecoder(encoding.lower())(errors='replace')
            s['decoder_encoding'] = encoding
        s['rx_bytes'] += len(raw)
        self.receive_text(index, s['decoder'].decode(raw), stamp, raw)

    def receive_text(self, index, text, stamp, raw=b''):
        s = self.sessions[index]
        spans = s['ansi'].feed(text)
        if any(char in self.ERASE_CHARS for value, _ in spans for char in value):
            plain, grouped, erased = self.erase_received(index, spans)
            if erased:
                self.erase_view(index, erased)
        else:
            plain = ''.join(value for value, _ in spans)
            grouped = spans
        s['received'] += plain.count('\n')
        # Erase markers never become records; HEX display still shows the raw
        # bytes as received, including the backspace markers themselves.
        if plain or raw:
            self.add_record(index, 'RX', plain, stamp, raw=raw, spans=grouped)
        self.notify_alerts(s, s['alerts'].check(time.monotonic(), plain, received=bool(raw)))

    ERASE_CHARS = '\x08\x7f'

    def erase_received(self, index, spans):
        """Apply device backspace echoes to the still-visible current line.

        Erase markers pop the freshest character, from this batch first and
        then from earlier RX batches (byte-by-byte echo). They never cross a
        newline and never touch local TX, error or notice records. Returns the
        cleaned fresh text, its styled spans, and how many already rendered
        view characters were erased.
        """
        s = self.sessions[index]
        o = s['options']
        rendered_tail = not o['paused'] and o['display_mode'] != 'HEX' and self.visible_record(s, 'RX')
        fresh, erased = [], 0  # fresh: (char, style)
        for text, style in spans:
            for char in text:
                if char in self.ERASE_CHARS:
                    if fresh:
                        if fresh[-1][0] != '\n':
                            fresh.pop()
                        # A fresh newline blocks erasing into earlier batches.
                    elif self.erase_record_char(s['records']):
                        erased += 1
                else:
                    fresh.append((char, style))
        grouped = self.group_chars(fresh)
        return ''.join(value for value, _ in grouped), grouped, erased if rendered_tail else 0

    @staticmethod
    def erase_record_char(records):
        """Drop one character from the tail of the current RX line in records."""
        for record in reversed(records):
            if record['tag'] != 'RX' or record['text'].endswith('\n'):
                return False
            if not record['text']:
                continue  # Empty RX records carry no visible characters.
            record['text'] = record['text'][:-1]
            if record['spans']:
                text, style = record['spans'][-1]
                if len(text) > 1:
                    record['spans'][-1] = (text[:-1], style)
                else:
                    record['spans'].pop()
            return True
        return False

    @staticmethod
    def group_chars(chars):
        grouped = []
        for char, style in chars:
            if grouped and grouped[-1][1] == style:
                grouped[-1][0] += char
            else:
                grouped.append([char, style])
        return [(text, style) for text, style in grouped]

    def erase_view(self, index, count):
        """Remove already rendered characters from the end of the log view."""
        view = self.views[index]
        bar = view.verticalScrollBar()
        position = bar.value()
        follow = self.sessions[index]['options']['auto_scroll'] and position >= bar.maximum()-3
        cursor = QTextCursor(view.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.KeepAnchor, count)
        cursor.removeSelectedText()
        if follow:
            bar.setValue(bar.maximum())
        else:
            bar.setValue(position)

    def write_payload(self, s, payload, shown, token=None):
        if s['state'] != 'connected' or not s.get('worker') or s['worker'].stopped.is_set():
            self.report_error('串口未连接，数据未发送')
            return False
        if s['locked'] and token is None:
            self.report_error('该会话正在参与宏，请等待完成或点击停止')
            return False
        try:
            s['worker'].commands.put_nowait((token, payload, shown))
        except queue.Full:
            self.report_error('发送队列已满，请稍后重试')
            return False
        return True

    def dispatch_command(self, text, display=None):
        self.capture_session()
        s = self.sessions[self.active]
        try:
            payload = text if isinstance(text, bytes) else text.encode(s['options']['encoding'].lower())
        except (UnicodeError, LookupError) as exc:
            self.report_error(f'编码失败：{exc}')
            return False
        return self.write_payload(s, payload, display if display is not None else (text.rstrip('\r\n') if isinstance(text, str) else payload.hex(' ')))

    def send(self):
        if self.mode.currentIndex() == 1:
            return
        self.capture_session()
        text = self.command.text()
        if self.encoding.currentText() == 'HEX':
            raw = parse_hex(text)
            if raw is None:
                self.report_error('HEX 输入无效，请输入完整十六进制字节，例如 00 FF 1B')
                return
            sent = self.dispatch_command(raw, raw.hex(' ').upper())
        elif '\n' in text or re.match(r'^\s*\[(?:port|delay)\s*=', text, re.I):
            sent = self.run_commands(text)
        else:
            ending = {'CR': '\r', 'LF': '\n', 'CRLF': '\r\n', '无': ''}[self.ending.currentText()]
            sent = self.dispatch_command(text + ending)
        if sent:
            history = self.sessions[self.active]['sent_log']
            if text and (not history or history[-1] != text):
                history.append(text)
                del history[:-500]
            self.command.clear()
            self.browse_reset()

    def direct_send(self, index, value):
        if 0 <= index < len(self.sessions):
            s = self.sessions[index]
            raw = value.encode('utf-8')
            # Keypress records are opt-in: by default nothing is printed per
            # key (the device echo already shows what was typed, and control
            # keys like Enter or Backspace are pure noise between prompts).
            # The 显示按键字节 switch prints every keypress byte for
            # debugging devices that do not echo.
            shown = f'按键字节 {raw.hex(" ")} {value!r}' if s['options']['show_keybytes'] else None
            self.write_payload(s, raw, shown)

    def eventFilter(self, watched, event):
        if self.ready and event.type() == QEvent.Type.KeyPress:
            if watched is self.command and event.key() == Qt.Key.Key_Tab:
                # Tab expands a matching macro; without a match it stays a
                # normal focus traversal key instead of trapping the cursor.
                if self.expand_macro():
                    return True
            if watched in self.views:
                index = self.views.index(watched)
                if watched.direct:
                    if event.matches(QKeySequence.StandardKey.Copy) and watched.textCursor().hasSelection():
                        watched.copy()
                        return True
                    if event.matches(QKeySequence.StandardKey.Paste):
                        value = QApplication.clipboard().text().replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r')
                    elif event.modifiers() & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_A <= event.key() <= Qt.Key.Key_Z:
                        value = chr(event.key() - Qt.Key.Key_A + 1)
                    elif event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
                        return super().eventFilter(watched, event)
                    else:
                        # ←/→ stay local: the log is append-only and cannot
                        # render in-line cursor movement, and boards whose
                        # shell answers cursor-left with backspaces erased the
                        # echoed input line (预输入) from the display. ↑/↓
                        # still go out because history recall re-echoes the
                        # line, which renders correctly as a new line.
                        keys = {Qt.Key.Key_Return:'\r', Qt.Key.Key_Enter:'\r', Qt.Key.Key_Backspace:'\x08',
                            Qt.Key.Key_Up:'\x1b[A', Qt.Key.Key_Down:'\x1b[B',
                            Qt.Key.Key_Home:'\x1b[H', Qt.Key.Key_End:'\x1b[F', Qt.Key.Key_Delete:'\x1b[3~',
                            Qt.Key.Key_Insert:'\x1b[2~', Qt.Key.Key_PageUp:'\x1b[5~', Qt.Key.Key_PageDown:'\x1b[6~', Qt.Key.Key_Tab:'\t', Qt.Key.Key_Escape:'\x1b'}
                        value = keys.get(event.key(), event.text())
                    if value:
                        self.direct_send(index, value)
                        return True
        return super().eventFilter(watched, event)

    def update_state(self):
        if not self.ready:
            return super().update_state()
        super().update_state()
        s = self.sessions[self.active]
        self.connect_btn.setEnabled(not (s.get('worker') and s['state'] in ('disconnected', 'error')))
        self.command.setPlaceholderText('点击日志区直接发送按键' if self.mode.currentIndex() == 1 else '输入命令，Enter 发送 · Tab 展开宏 · ↑/↓ 历史')
        self.info_values['设备运行状态'].setText('串口已连接' if s['state'] == 'connected' else self.connection.text())
        service = s.get('service_status') or {}
        if s.get('service'):
            owner = {'human': '人工', 'agent': 'Agent', 'revoking': '正在接管'}.get(service.get('owner'), '未知')
            device = '设备已连接' if service.get('connected') else '设备已释放'
            self.info_values['设备运行状态'].setText(f'服务 {s["service"]["host"]}:{s["service"]["control"]} · {device} · 控制权：{owner}')
        is_service = bool(s.get('service'))
        self.service_takeover.setVisible(is_service and bool(s.get('worker')))
        self.service_takeover.setEnabled(service.get('owner') == 'agent' and s['state'] == 'connected')
        self.service_stop.setVisible(is_service)
        self.service_stop.setEnabled(is_service and not s.get('service_stop_pending'))
        status = '已暂停显示' if self.paused else '就绪'
        if s.get('log_file'):
            status += ' · 持续记录中'
        if s.get('locked'):
            status += ' · 宏占用中'
        if self.detecting:
            status += ' · 等待新设备插入'
        error = self._status_error
        if error and error[1] < time.monotonic():
            error = self._status_error = None
        if error:
            self.state.setText(error[0])
            set_role(self.state, 'danger')
        else:
            self.state.setText(status)
            set_role(self.state, 'warning' if self.paused else 'muted')
        self.logging_button.setText('停止持续日志' if s.get('log_file') else '开始持续日志…')
        self.macro_run.setEnabled(s['state'] == 'connected' and self.macro_job is None)

    def report_error(self, text):
        if self.ready and self.active >= 0:
            self.append(self.active, 'ERROR', text)
            # The status bar is rewritten by every poll; hold the error there
            # in danger color for a few seconds instead of losing it in 30 ms.
            self._status_error = (text, time.monotonic() + 8)
            self.update_state()

    def append(self, index, tag, text, role='text_primary', stamp=None):
        if not self.ready:
            return
        self.add_record(index, tag, text.replace('模拟会话已创建', '串口会话已创建') + '\n', datetime.now())

    def add_record(self, index, tag, text, stamp, raw=b'', spans=None):
        s = self.sessions[index]
        record = dict(tag=tag, text=text, stamp=stamp, raw=raw,
                      spans=spans if spans is not None else [(text, AnsiLogParser.DEFAULT)])
        s['records'].append(record)
        # A bounded screen buffer; continuous files have no record-count limit.
        del s['records'][:-RECORD_LIMIT]
        if s['log_file']:
            try:
                value, s['file_line_start'] = self.format_file([record], s['file_options'], s['file_line_start'])
                s['log_file'].write(value)
                s['log_file'].flush()
            except OSError as exc:
                self.stop_logging(index)
                self.report_error(f'持续日志写入失败：{exc}')
        if s['options']['paused']:
            s['pending'] += 1
            if index == self.active:
                self.pause_badge.setText(f"已暂停 · 新增 {s['pending']} 条")
            return
        self.render_record(index, record)
        if index == self.active and self.search.text():
            self.find()

    def visible_record(self, s, tag):
        o = s['options']
        if o['tags'] and tag not in o['tags']:
            return False
        if tag in ('RX', 'TX'):
            return o['show_rx' if tag == 'RX' else 'show_tx']
        return {'ERROR':3, 'WARN':2}.get(tag, 1) >= o['log_level']

    def render_record(self, index, record):
        s = self.sessions[index]
        o = s['options']
        if not self.visible_record(s, record['tag']):
            return
        view = self.views[index]
        bar = view.verticalScrollBar()
        position = bar.value()
        follow = o['auto_scroll'] and position >= bar.maximum()-3
        self.append_record(index, record)
        if follow:
            bar.setValue(bar.maximum())
        else:
            bar.setValue(position)

    def append_record(self, index, record):
        """把一条记录渲染追加到该会话日志视图末尾（不处理滚动条）。"""
        s = self.sessions[index]
        o = s['options']
        view = self.views[index]
        cursor = QTextCursor(view.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        spans = record['spans']
        if o['display_mode'] == 'HEX' and record['raw']:
            spans = [(record['raw'].hex(' ').upper()+'\n', AnsiLogParser.DEFAULT)]
        elif record['tag'] == 'RX' and not record['text']:
            return
        last_tag = s.get('display_tag')
        if last_tag != record['tag'] and not s['display_line_start']:
            cursor.insertText('\n')
            s['display_line_start'] = True
        for text, style in spans:
            pieces = text.split('\n')
            for i, part in enumerate(pieces):
                newline = i < len(pieces)-1
                # A piece with no visible content at line start would render
                # as a bare timestamped blank line — the CRLF echo of Enter
                # between prompts (the parser normalizes CR to LF, and peer
                # writes can still carry raw CR); skip it. Mid-line such a
                # piece still closes the current line, and a whitespace tail
                # without a newline may hold erasable characters, so both of
                # those must keep rendering.
                if not part and not newline:
                    continue
                if newline and s['display_line_start'] and not part.strip():
                    continue
                if s['display_line_start']:
                    fmt = QTextCharFormat()
                    fmt.setForeground(QColor(self.c['text_tertiary']))
                    if o['timestamps']:
                        cursor.insertText(timestamp(record['stamp'], o['time_format'])+'  ', fmt)
                    fmt.setForeground(QColor(self.c[{'TX':'brand_foreground','ERROR':'danger_foreground','WARN':'warning_foreground'}.get(record['tag'], 'text_secondary')]))
                    cursor.insertText(f"{record['tag']:<5}  ", fmt)
                fmt = QTextCharFormat()
                fg, bg, bold, dim, italic, underline, reverse, strike = style
                fg = fg or self.c['text_primary']
                bg = bg or self.c['canvas_background']
                if reverse:
                    fg, bg = bg, fg
                color = QColor(fg)
                if dim:
                    color.setAlphaF(.65)
                fmt.setForeground(color)
                fmt.setBackground(QColor(bg))
                fmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
                fmt.setFontItalic(italic)
                fmt.setFontUnderline(underline)
                fmt.setFontStrikeOut(strike)
                cursor.insertText(part + ('\n' if newline else ''), fmt)
                s['display_line_start'] = newline
        s['display_tag'] = record['tag']

    def render_fingerprint(self, s):
        """当前会话「渲染相关状态」的签名：选项 + 主题。"""
        o = s['options']
        return (self.dark, tuple(tuple(o[k]) if k == 'tags' else o[k] for k in RENDER_OPTION_KEYS))

    def rebuild_view(self, index):
        """按 records 全量重建一个会话的日志视图。

        逐条 insertText 会让文档排版与滚动条逐条刷新，满缓冲时一次重建可冻住
        主线程数秒（handoff 20261027-1610）；单个 edit block 把排版、undo 与
        滚动条工作合并到重建完成后一次完成。
        """
        s = self.sessions[index]
        view = self.views[index]
        o = s['options']
        view.clear()
        s['display_line_start'] = True
        s['display_tag'] = None
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if o['wrap'] else QPlainTextEdit.LineWrapMode.NoWrap)
        cursor = QTextCursor(view.document())
        cursor.beginEditBlock()
        try:
            for record in s['records']:
                if self.visible_record(s, record['tag']):
                    self.append_record(index, record)
        finally:
            cursor.endEditBlock()
        view.setExtraSelections([])
        bar = view.verticalScrollBar()
        bar.setValue(bar.maximum() if o['auto_scroll'] else 0)
        s['render_sync'] = self.render_fingerprint(s)

    def rerender(self):
        if not self.ready:
            return super().rerender()
        if self._restoring:
            return
        self.capture_session()
        for i, s in enumerate(self.sessions):
            if s['options']['paused']:
                continue
            # 记录到达时实时渲染，视图始终与 records 同步；只有渲染选项变化
            # （或暂停积压）才让视图过期。满缓冲切换标签不再全量重画。
            if s.get('render_sync') == self.render_fingerprint(s):
                continue
            self.rebuild_view(i)
        if self.active >= 0:
            self.find()

    def toggle_pause(self, paused=None):
        if not self.ready:
            return super().toggle_pause(paused)
        self.paused = not self.paused if paused is None else bool(paused)
        self.options()['paused'] = self.paused
        self.sessions[self.active]['pending'] = 0
        b = self.pause_tool
        b.blockSignals(True)
        b.setChecked(self.paused)
        b.setText('恢复接收' if self.paused else '暂停接收')
        b.setIcon(icon('play' if self.paused else 'pause'))
        b.blockSignals(False)
        self.pause_badge.setText('已暂停')
        self.pause_badge.setVisible(self.paused)
        self._position_badge()
        if not self.paused:
            # 暂停期间积压的记录没有渲染过，视图已过期，必须整帧重建。
            self.sessions[self.active]['render_sync'] = None
            self.rerender()
        self.update_state()

    def clear_log(self):
        s = self.sessions[self.active]
        s['records'].clear()
        s['display_line_start'] = True
        s['display_tag'] = None
        self.views[self.active].clear()
        self.find()

    @staticmethod
    def format_file(records, options, line_start=True):
        result = []
        for r in records:
            parts = r['text'].split('\n')
            for i, part in enumerate(parts):
                newline = i < len(parts)-1
                if not part and not newline:
                    continue
                if line_start and options['log_timestamp']:
                    result.append('[' + timestamp(r['stamp'], options['log_format']) + '] ')
                result.append(part + ('\n' if newline else ''))
                line_start = newline
        text = ''.join(result)
        if options['log_newline'] == 'CRLF':
            text = text.replace('\n', '\r\n')
        return text, line_start

    def default_log_path(self, s):
        name = re.sub(r'[^\w.-]', '_', s['port'] or 'serial')
        return Path(s['options']['log_directory']) / f'{name}_{datetime.now():%Y%m%d_%H%M%S_%f}.log'

    def open_log_file(self, path, options):
        path = Path(path).resolve()
        if any(s.get('log_path') == path and s.get('log_file') for s in self.sessions):
            raise OSError('该文件正在持续记录，请选择其他文件')
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.open('a' if options['log_append'] else 'w',
            encoding='utf-8-sig' if options['log_encoding'] == 'UTF-8 BOM' else 'utf-8', newline='')

    def save_snapshot(self, index, path):
        s = self.sessions[index]
        try:
            with self.open_log_file(path, s['options']) as out:
                out.write(self.format_file(s['records'], s['options'])[0])
            return True
        except OSError as exc:
            self.report_error(f'保存失败：{exc}')
            return False

    def save_log(self):
        self.capture_session()
        path, _ = QFileDialog.getSaveFileName(self, '保存会话日志（不受过滤、暂停或 HEX 显示影响）', str(self.default_log_path(self.sessions[self.active])), '日志 (*.log);;所有文件 (*)')
        if path:
            self.options()['log_directory'] = str(Path(path).parent)
            self.save_snapshot(self.active, path)

    def open_log_dialog(self):
        """Pick a saved log file and load it into the current session."""
        self.capture_session()
        directory = self.options()['log_directory']
        start = directory if Path(directory).exists() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, '打开日志文件（自动识别时间戳与编码）', start,
                                              '日志 (*.log *.txt *.csv);;所有文件 (*)')
        if path and self.load_log_file(self.active, path):
            self.options()['log_directory'] = str(Path(path).parent)

    @staticmethod
    def read_log_source(path):
        """Read a log file; oversized files are capped to their tail."""
        size = path.stat().st_size
        if size <= LOG_TAIL_BYTES:
            return path.read_bytes(), False
        with path.open('rb') as stream:
            stream.seek(size - LOG_TAIL_BYTES)
            data = stream.read()
        newline = data.find(b'\n')
        if newline >= 0:
            data = data[newline + 1:]  # Start on a whole line after the cut.
        return data, True

    def load_log_file(self, index, path):
        """Open a saved log file, recognize it, and append it to session `index`.

        识别结果以 SYS 摘要说明（行数、时间戳识别情况、编码、截断提示）。
        导入的记录不写入正在进行的持续日志文件，也不计入收发统计。
        """
        path = Path(path)
        try:
            data, capped = self.read_log_source(path)
        except OSError as exc:
            self.report_error(f'打开日志失败：{exc}')
            return False
        text, encoding = decode_log_bytes(data)
        try:
            base_stamp = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            base_stamp = datetime.now()
        records, stats = parse_log_text(text, base_stamp)
        total = len(records)
        if not records:
            self.report_error(f'打开日志失败：{path.name} 没有可识别的内容')
            return False
        del records[:-RECORD_LIMIT]
        s = self.sessions[index]
        s['records'].extend(records)
        del s['records'][:-RECORD_LIMIT]
        if s['options']['paused']:
            s['pending'] += len(records)
            if index == self.active:
                self.pause_badge.setText(f"已暂停 · 新增 {s['pending']} 条")
        else:
            bar = self.views[index].verticalScrollBar()
            position = bar.value()
            self.rebuild_view(index)
            if not s['options']['auto_scroll']:
                bar.setValue(position)
            if index == self.active and self.search.text():
                self.find()
        summary = [f'已打开日志 {path.name}（{encoding}）：{stats["lines"]} 行 → {total} 条记录']
        notes = []
        if capped:
            notes.append(f'文件较大，仅解析末尾 {LOG_TAIL_BYTES // (1024 * 1024)} MB')
        if total > len(records):
            notes.append(f'仅保留最近 {RECORD_LIMIT} 条')
        if stats['stamps']:
            notes.append(f"识别时间戳 {stats['stamps']} 个（{stats['dated']} 带日期）")
            if stats['dated'] < stats['stamps']:
                notes.append('无日期时间戳按文件日期补齐')
        else:
            notes.append('未识别到时间戳，按文件修改时间标注')
        if stats['merged']:
            notes.append(f"{stats['merged']} 行无时间戳并入前条")
        if stats['erases']:
            notes.append(f"已忽略 {stats['erases']} 个退格控制符")
        self.append(index, 'SYS', summary[0] + ('\n' + '；'.join(notes) if notes else ''))
        return True

    def toggle_logging(self):
        if self.sessions[self.active]['log_file']:
            self.stop_logging(self.active)
        else:
            self.start_logging()

    def start_logging(self, path=None, index=None, automatic=False):
        self.capture_session()
        index = self.active if index is None else index
        s = self.sessions[index]
        if s['log_file']:
            return True
        if path is None:
            path = self.default_log_path(s)
            if not automatic:
                path, _ = QFileDialog.getSaveFileName(self, '开始持续日志', str(path), '日志 (*.log)')
        if not path:
            return False
        try:
            s['log_file'] = self.open_log_file(path, s['options'])
            s['log_path'] = Path(path).resolve()
            s['file_options'] = dict(s['options'])
            s['file_line_start'] = True
            s['options']['log_directory'] = str(Path(path).parent)
            return True
        except OSError as exc:
            self.report_error(f'日志打开失败：{exc}')
            return False

    def stop_logging(self, index):
        s = self.sessions[index]
        stream = s.get('log_file')
        s['log_file'] = None
        s['log_path'] = None
        if stream:
            try:
                stream.close()
            except OSError as exc:
                self.report_error(f'日志关闭失败：{exc}')

    def show_file_settings(self):
        self.capture_session()
        o = self.options()
        d = QDialog(self)
        d.setWindowTitle('当前会话 · 时间戳与日志文件')
        f = QFormLayout(d)
        widgets = {}
        for key, title in [('timestamps','显示时间戳'), ('log_timestamp','文件时间戳'),
                           ('log_append','追加到已有文件'), ('log_auto','连接后自动持续记录')]:
            w = QCheckBox(title)
            w.setChecked(o[key])
            widgets[key] = w
            f.addRow(w)
        for key, title, choices in [('time_format','显示时间格式',TIME_FORMATS),
            ('log_format','文件时间格式',TIME_FORMATS), ('log_encoding','文件编码',['UTF-8','UTF-8 BOM']),
            ('log_newline','文件行尾',['LF','CRLF'])]:
            w = QComboBox()
            w.addItems(choices)
            w.setCurrentText(o[key])
            widgets[key] = w
            f.addRow(title, w)
        directory = QLineEdit(o['log_directory'])
        browse = QPushButton('选择…')
        def choose():
            path = QFileDialog.getExistingDirectory(d, '日志目录', directory.text())
            if path:
                directory.setText(path)
        browse.clicked.connect(choose)
        f.addRow('日志目录', row(directory, browse))
        f.addRow(QLabel('正在记录的文件沿用开始时的设置；新设置用于下一份文件。'))
        self.dialog_buttons(d, f)
        if d.exec():
            for key, w in widgets.items():
                o[key] = w.isChecked() if isinstance(w, QCheckBox) else w.currentText()
            o['log_directory'] = directory.text().strip() or DEFAULT_OPTIONS['log_directory']
            self.timestamps.blockSignals(True)
            self.timestamps.setChecked(o['timestamps'])
            self.timestamps.blockSignals(False)
            self.rerender()
            self.save_settings()

    def reset_alerts(self):
        s = self.sessions[self.active]
        s['alerts'].reset(time.monotonic() if s['state'] == 'connected' else None)
        self.state.setText('提醒已重新计数')

    def notify_alerts(self, s, reasons, options=None):
        if not reasons:
            return
        o = options or s['alerts'].options
        text = s['port'] + '：' + '；'.join(reasons)
        index = next(i for i, item in enumerate(self.sessions) if item is s)
        self.append(index, 'WARN', '提醒 · ' + text)
        if o['sound']:
            QApplication.beep()
        if o['taskbar']:
            QApplication.alert(self, 0)
        if o['windows'] and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage('串口条件提醒', text, QSystemTrayIcon.MessageIcon.Information, 10000)
        if o['popup']:
            box = QMessageBox(QMessageBox.Icon.Information, '串口条件提醒', text, QMessageBox.StandardButton.Ok, self)
            box.setModal(False)
            box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self.notice_windows.append(box)
            box.finished.connect(lambda _: self.notice_windows.remove(box) if box in self.notice_windows else None)
            box.show()
            point = QCursor.pos()
            screen = QApplication.screenAt(point) or QApplication.primaryScreen()
            bounds = screen.availableGeometry()
            box.move(max(bounds.left(), min(point.x()+16, bounds.right()-box.width())),
                     max(bounds.top(), min(point.y()+16, bounds.bottom()-box.height())))

    def show_alert_settings(self):
        s = self.sessions[self.active]
        o = s['alerts'].options
        d = QDialog(self)
        d.setWindowTitle('当前会话 · 条件提醒')
        f = QFormLayout(d)
        flags, values = {}, {}
        for key, title in [('enabled','启用提醒'), ('sound','声音'), ('popup','鼠标附近弹窗'),
                           ('windows','Windows 系统通知'), ('taskbar','任务栏高亮')]:
            w = QCheckBox(title)
            w.setChecked(o[key])
            flags[key] = w
            f.addRow(w)
        keywords = QPlainTextEdit(o['keywords'])
        keywords.setMaximumHeight(90)
        f.addRow('提示词（每行一个）', keywords)
        for key, title in [('seconds','经过时间（秒）'), ('lines','累计打印（行）'), ('idle','无数据时长（秒）')]:
            w = QLineEdit(str(o[key]))
            values[key] = w
            f.addRow(title, w)
        f.addRow(QLabel('0 表示不检查；任一条件满足即提醒，每个条件每轮提醒一次。'))
        def read():
            return AlertMonitor.validate({**{k:w.isChecked() for k,w in flags.items()},
                **{k:w.text() or '0' for k,w in values.items()}, 'keywords':keywords.toPlainText()})
        test = QPushButton('测试提醒方式')
        show_error = self.inline_form_error(f)
        def preview():
            try:
                self.notify_alerts(s, ['测试提醒'], read())
            except ValueError as exc:
                show_error(str(exc))
        test.clicked.connect(preview)
        f.addRow(test)
        buttons = self.dialog_buttons(d, f)
        buttons.accepted.disconnect()
        def accept():
            try:
                s['alerts'].options = read()
            except ValueError as exc:
                show_error(str(exc))
                return
            self.reset_alerts()
            d.accept()
        buttons.accepted.connect(accept)
        d.exec()
        self.save_settings()

    def show_search_settings(self):
        d = QDialog(self)
        d.setWindowTitle('当前会话 · 搜索选项')
        f = QFormLayout(d)
        case = QCheckBox('区分大小写')
        whole = QCheckBox('全词匹配')
        case.setChecked(self.options()['case'])
        whole.setChecked(self.options()['whole'])
        f.addRow(case)
        f.addRow(whole)
        f.addRow(QLabel('F3 下一处；Shift+F3 上一处；Enter 下一处。'))
        self.dialog_buttons(d, f)
        if d.exec():
            self.options().update(case=case.isChecked(), whole=whole.isChecked())
            self.find()

    def search_menu(self, position):
        menu = self.search.createStandardContextMenu()
        menu.addSeparator()
        menu.addAction('搜索选项…', self.show_search_settings)
        menu.addAction('上一处 (Shift+F3)', lambda: self.next_match(-1))
        menu.addAction('下一处 (F3)', self.next_match)
        menu.exec(self.search.mapToGlobal(position))
        menu.deleteLater()

    def find(self):
        """调度一次搜索高亮重扫；防抖窗口内的多次触发合并为一次。"""
        if not self.ready:
            return super().find()
        if self.active < 0:
            return
        self._find_timer.start()

    def find_now(self):
        """立即执行一次重扫（绕过防抖；F3/导航需要最新匹配时用）。"""
        if not self.ready:
            return super().find()
        if self.active < 0:
            return
        o = self.options()
        flags = QTextDocument.FindFlag(0)
        if o['case']:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if o['whole']:
            flags |= QTextDocument.FindFlag.FindWholeWords
        view = self.views[self.active]
        query = self.search.text()
        self.matches = []
        selections = []
        cursor = QTextCursor(view.document())
        while query and len(self.matches) < FIND_MATCH_LIMIT:
            cursor = view.document().find(query, cursor, flags)
            if cursor.isNull():
                break
            self.matches.append(QTextCursor(cursor))
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(cursor)
            selection.format.setBackground(QColor(self.c['warning_background']))
            selection.format.setForeground(QColor(self.c['warning_foreground']))
            selections.append(selection)
        # 命中到达上限时再探一步，区分「正好 500」与「500+」。
        capped = (len(self.matches) == FIND_MATCH_LIMIT
                  and not view.document().find(query, cursor, flags).isNull())
        view.setExtraSelections(selections)
        self.match_index = -1
        if capped:
            self.match_count.setText(f'{FIND_MATCH_LIMIT}+ 个匹配')
        else:
            self.match_count.setText(f'{len(self.matches)} 个匹配' if query else '')

    def next_match(self, direction=1):
        if self._find_timer.isActive():
            # 防抖窗口内导航时先出结果，避免 F3 用上一轮的旧匹配。
            self._find_timer.stop()
            self.find_now()
        if self.matches:
            if self.match_index == -1 and direction == -1:
                self.match_index = 0
            self.match_index = (self.match_index + direction) % len(self.matches)
            view = self.views[self.active]
            view.setTextCursor(self.matches[self.match_index])
            view.ensureCursorVisible()
            self.match_count.setText(f'{self.match_index+1} / {len(self.matches)}')

    def run_commands(self, text, name='宏'):
        self.capture_session()
        if self.macro_job:
            self.report_error('已有宏正在执行，请先停止')
            return False
        steps = []
        owner = self.sessions[self.active]
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        if len(lines) > 1 and not lines[-1]:
            lines.pop()
        try:
            for number, line in enumerate(lines, 1):
                port, delay, command = parse_macro_line(line, self.interval.value())
                s = owner if port is None else next((s for s in self.sessions if s['port'].casefold() == port.casefold()), None)
                if s is None or s['state'] != 'connected' or not s.get('worker') or s['worker'].stopped.is_set():
                    raise ValueError(f'第 {number} 行：串口 {port or owner["port"]} 未连接')
                if s['locked']:
                    raise ValueError(f'第 {number} 行：目标串口被占用')
                o = s['options']
                ending = {'CR':'\r', 'LF':'\n', 'CRLF':'\r\n', '无':''}[o['ending']]
                # Macros are text commands; HEX is confined to the explicit HEX input row.
                encoding = o['encoding'].lower() if o['encoding'] != 'HEX' else 'utf-8'
                payload = (command+ending).encode(encoding)
                steps.append((s, s['worker'], payload, command, delay))
        except (ValueError, UnicodeError) as exc:
            self.report_error(str(exc))
            return False
        targets = []
        for s in [owner] + [step[0] for step in steps]:
            if not any(t is s for t in targets):
                targets.append(s)
                s['locked'] = True
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self.macro_step)
        self.macro_job = dict(steps=steps, targets=targets, index=0, name=name, timer=timer, token=None)
        self.macro_stop.setEnabled(True)
        self.macro_step()
        return True

    def macro_step(self):
        job = self.macro_job
        if not job:
            return
        i = job['index']
        if i == len(job['steps']):
            self.stop_macro(f"{job['name']}：{i}/{i} 完成")
            return
        s, worker, payload, shown, delay = job['steps'][i]
        if s.get('worker') is not worker or s['state'] != 'connected':
            self.stop_macro(f'第 {i+1} 行目标已断开，宏已停止')
            return
        job['token'] = object()
        self.macro_progress.setText(f"{job['name']}：{i+1}/{len(job['steps'])} · {s['port']}")
        if not self.write_payload(s, payload, shown, token=job['token']):
            self.stop_macro('发送失败，宏已停止')

    def macro_ack(self):
        job = self.macro_job
        if not job:
            return
        delay = job['steps'][job['index']][4]
        job['index'] += 1
        job['token'] = None
        job['timer'].start(delay)

    def stop_macro(self, reason='宏已停止'):
        if isinstance(reason, bool):
            reason = '宏已停止'
        job = self.macro_job
        if job:
            job['timer'].stop()
            job['timer'].deleteLater()
            for s in job['targets']:
                s['locked'] = False
                # Cancel queued macro sends; a write already in progress cannot be recalled.
                worker = s.get('worker')
                if worker:
                    with worker.commands.mutex:
                        kept = [item for item in worker.commands.queue if item[0] is None]
                        worker.commands.queue.clear()
                        worker.commands.queue.extend(kept)
            self.macro_job = None
        if hasattr(self, 'macro_stop'):
            self.macro_stop.setEnabled(False)
            self.macro_progress.setText(reason)

    def run_macro(self):
        self.run_commands(self.macro_text.toPlainText())

    def run_macro_command(self, index):
        if 0 <= index < len(self.macros):
            name = self.macros[index][0]
            self.run_commands(self.named_macros.get(name, name), name)

    def add_macro(self):
        self.edit_macro_dialog(-1)

    def edit_macro_dialog(self, index=None):
        index = self.macro_list.currentRow() if index is None else index
        exists = 0 <= index < len(self.macros)
        old_name, description = self.macros[index] if exists else ('', '')
        d = QDialog(self)
        d.setWindowTitle('编辑宏' if exists else '新增宏')
        f = QFormLayout(d)
        name = QLineEdit(old_name)
        desc = QLineEdit(description)
        body = QPlainTextEdit(self.named_macros.get(old_name, old_name))
        f.addRow('宏名称（Tab 展开）', name)
        f.addRow('说明', desc)
        f.addRow('命令（支持逐行 port / delay）', body)
        buttons = self.dialog_buttons(d, f)
        buttons.accepted.disconnect()
        show_error = self.inline_form_error(f)
        def accept():
            new_name = name.text().strip()
            if not new_name or any(n == new_name and (not exists or i != index) for i,(n,_) in enumerate(self.macros)):
                show_error('名称不能为空或与其他宏重复')
                return
            if exists:
                self.macros[index] = (new_name, desc.text())
                self.named_macros.pop(old_name, None)
            else:
                self.macros.append((new_name, desc.text()))
            self.named_macros[new_name] = body.toPlainText()
            d.accept()
        buttons.accepted.connect(accept)
        if d.exec():
            self.rebuild_macro_list()
            self.macro_list.setCurrentRow(index if exists else len(self.macros)-1)
            self.persist_macros()

    def save_editor_macro(self):
        name, ok = QInputDialog.getText(self, '命名保存宏', '宏名称：')
        if ok and name.strip():
            name = name.strip()
            if name in self.named_macros or any(n == name for n,_ in self.macros):
                self.report_error('名称已存在，请在宏列表中选择编辑')
                return
            self.macros.append((name, '逐行宏'))
            self.named_macros[name] = self.macro_text.toPlainText()
            self.rebuild_macro_list()
            self.persist_macros()

    def delete_macro(self):
        index = self.macro_list.currentRow()
        if 0 <= index < len(self.macros):
            self.named_macros.pop(self.macros[index][0], None)
        super().delete_macro()
        self.persist_macros()

    def move_macro(self, delta):
        super().move_macro(delta)
        self.persist_macros()

    def add_macro_command(self, command, description):
        super().add_macro_command(command, description)
        self.named_macros[command] = command
        self.persist_macros()

    def expand_macro(self):
        name = self.command.text().strip()
        body = self.named_macros.get(name)
        if body is None and any(n == name for n,_ in self.macros):
            body = name
        if body is None:
            return False
        if '\n' in body or '\r' in body:
            self.macro_text.setPlainText(body)
            if self.editor.isHidden():
                self.toggle_editor()
            self.macro_text.setFocus()
        else:
            self.command.setText(body)
        return True

    def persist_macros(self):
        if not self.persist or not self.ready:
            return
        try:
            self.atomic_json(self.macros_path, [dict(name=n, description=d, body=self.named_macros.get(n,n)) for n,d in self.macros])
        except OSError as exc:
            self.report_error(f'宏保存失败：{exc}')

    def show_modules(self):
        d = QDialog(self)
        d.setWindowTitle('布局模块')
        f = QFormLayout(d)
        checks = []
        for widget, title in self.modules:
            box = QCheckBox(title)
            box.setChecked(self.inspector.isTabVisible(self.inspector.indexOf(widget)))
            checks.append((widget, box))
            f.addRow(box)
        left = QCheckBox('设备栏展开')
        left.setChecked(not self.sidebar_collapsed)
        right = QCheckBox('右侧面板展开')
        right.setChecked(not self.inspector_collapsed)
        f.addRow(left)
        f.addRow(right)
        f.addRow(QLabel('拖动右侧标签可调整模块顺序；分隔线可调整大小。'))
        self.dialog_buttons(d, f)
        if d.exec():
            for widget, box in checks:
                self.inspector.setTabVisible(self.inspector.indexOf(widget), box.isChecked())
            self.set_sidebar_collapsed(not left.isChecked())
            self.set_inspector_collapsed(not right.isChecked())
            self.save_settings()

    def close_session(self, index):
        if index is None or not 0 <= index < len(self.sessions):
            return
        self.capture_session()
        s = self.sessions[index]
        self.disconnect_session(s)
        # Active workers finish asynchronously before removal so accepted RX/TX is drained.
        if s.get('worker'):
            s['close_requested'] = True
            return
        self.remove_session(index)

    def remove_session(self, index):
        s = self.sessions[index]
        self.stop_logging(index)
        self.devices.blockSignals(True)
        self.tabs.blockSignals(True)
        self.active = -1
        view = self.views.pop(index)
        self.logs.removeWidget(view)
        view.deleteLater()
        self.sessions.pop(index)
        self.devices.takeItem(index)
        for i in reversed(range(self.tabs.count())):
            data = self.tabs.tabData(i)
            if data == index:
                self.tabs.removeTab(i)
            elif data > index:
                self.tabs.setTabData(i, data-1)
        self.devices.blockSignals(False)
        self.tabs.blockSignals(False)
        if not self.sessions:
            self.create_session('')
        else:
            target = min(index, len(self.sessions)-1)
            self.devices.setCurrentRow(target)
            self.switch(target)
        # Rebind by view identity; no stale index closures after removing a middle session.
        for view in self.views:
            view.transmit.disconnect()
            view.transmit.connect(lambda value, v=view: self.direct_send(self.views.index(v), value))
        self.save_settings()

    @staticmethod
    def atomic_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)

    def save_settings(self):
        if not self.persist or not self.ready or self._restoring or self.active < 0:
            return
        self.capture_session()
        data = dict(version=1, sessions=[{**{k:s[k] for k in ('port','name','baud','fmt','flow','mode','draft','query','sent_log')},
            'service': s.get('service'), 'options':s['options'], 'alerts':s['alerts'].options} for s in self.sessions],
            active=self.active, dark=self.dark, zoom=round(self.ui_scale*100), log_zoom=round(self.log_zoom*100),
            geometry=bytes(self.saveGeometry().toBase64()).decode(),
            splitter=bytes(self.splitter.saveState().toBase64()).decode(),
            body=bytes(self.body_splitter.saveState().toBase64()).decode(),
            vertical=bytes(self.vertical.saveState().toBase64()).decode(),
            sidebar_collapsed=self.sidebar_collapsed, inspector_collapsed=self.inspector_collapsed,
            editor_open=not self.editor.isHidden(), macro_text=self.macro_text.toPlainText(), interval=self.interval.value(),
            modules=[dict(title=self.inspector.tabText(i), visible=self.inspector.isTabVisible(i)) for i in range(self.inspector.count())],
            selected_module=self.inspector.tabText(self.inspector.currentIndex()),
            tabs=[self.tabs.tabData(i) for i in range(self.tabs.count())])
        try:
            self.atomic_json(self.settings_path, data)
            self.persist_macros()
        except OSError as exc:
            self.report_error(f'配置保存失败：{exc}')

    def restore_settings(self):
        if not self.persist:
            return
        self._restoring = True
        try:
            if self.macros_path.exists():
                items = json.loads(self.macros_path.read_text('utf-8'))
                if not isinstance(items, list) or any(not isinstance(m, dict) or not all(isinstance(m.get(k), str) for k in ('name','description','body')) for m in items):
                    raise ValueError('宏配置格式无效')
                self.macros = [(m['name'],m['description']) for m in items]
                self.named_macros = {m['name']:m['body'] for m in items}
            if not self.settings_path.exists():
                # Read legacy named macros without changing the original file.
                legacy = _app_dir() / 'serial_macros.json'
                if not self.macros_path.exists() and legacy.exists():
                    items = json.loads(legacy.read_text('utf-8'))
                    if isinstance(items, dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in items.items()):
                        self.macros = [(k,'旧版宏') for k in items]
                        self.named_macros = dict(items)
                return
            data = json.loads(self.settings_path.read_text('utf-8'))
            if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('sessions'), list):
                raise ValueError('配置版本或会话列表无效')
            for i, saved in enumerate(data['sessions'][:64]):
                if not isinstance(saved, dict):
                    continue
                port = str(saved.get('port',''))
                if i:
                    index = self.create_session(port)
                else:
                    index = 0
                s = self.sessions[index]
                for k in ('port','name','baud','fmt','flow','draft','query'):
                    if isinstance(saved.get(k), str):
                        s[k] = saved[k]
                if not s['baud'].isdigit() or int(s['baud']) <= 0:
                    s['baud'] = '115200'
                if not re.fullmatch('[5-8][NEO][12]', s['fmt']):
                    s['fmt'] = '8N1'
                if s['flow'] not in ('无','RTS/CTS'):
                    s['flow'] = '无'
                s['mode'] = saved.get('mode') if saved.get('mode') in (0,1) else 1
                service = saved.get('service')
                if isinstance(service, dict) and all(isinstance(service.get(k), str) and service[k]
                        for k in ('host', 'device', 'baud')):
                    try:
                        service['control'] = int(service.get('control', 8889))
                    except (TypeError, ValueError):
                        service = None
                    if service:
                        s['service'] = service
                hist = saved.get('sent_log', [])
                s['sent_log'] = [h for h in hist if isinstance(h,str)][-500:] if isinstance(hist,list) else []
                options = saved.get('options', {})
                if isinstance(options, dict):
                    for key, default in DEFAULT_OPTIONS.items():
                        if type(options.get(key)) is type(default):
                            s['options'][key] = options[key]
                o = s['options']
                allowed = dict(time_format=TIME_FORMATS, log_format=TIME_FORMATS,
                    log_encoding=['UTF-8','UTF-8 BOM'], log_newline=['LF','CRLF'],
                    display_mode=['ASCII','HEX'], rx_encoding=['UTF-8','GBK'],
                    encoding=['UTF-8','ASCII','HEX'], ending=['CR','LF','CRLF','无'],
                    save_policy=['手动保存','会话结束自动保存'], log_level=[0,1,2,3])
                for key, values in allowed.items():
                    if o[key] not in values:
                        o[key] = DEFAULT_OPTIONS[key]
                o['tags'] = [t for t in o['tags'] if t in ('RX','TX','INFO','WARN','ERROR')]
                try:
                    s['alerts'].options = AlertMonitor.validate(saved.get('alerts', {}))
                except (ValueError, TypeError, AttributeError):
                    pass
            self.active = -1
            active = data.get('active',0)
            self.switch(active if isinstance(active,int) and 0 <= active < len(self.sessions) else 0)
            self.devices.setCurrentRow(self.active)
            self.theme(bool(data.get('dark', True)))
            self.set_zoom(int(data.get('zoom',125)))
            self.set_log_zoom(int(data.get('log_zoom',100)))
            self.macro_text.setPlainText(str(data.get('macro_text','')))
            self.interval.setValue(int(data.get('interval',500)))
            self.editor.setVisible(bool(data.get('editor_open',False)))
            self.expand.setText('收起宏编辑器' if data.get('editor_open') else '展开宏编辑器')
            for target, key in [(self,'geometry'), (self.splitter,'splitter'), (self.body_splitter,'body'), (self.vertical,'vertical')]:
                if isinstance(data.get(key), str):
                    blob = QByteArray.fromBase64(data[key].encode())
                    target.restoreGeometry(blob) if key == 'geometry' else target.restoreState(blob)
            for target_index, module in enumerate(data.get('modules', [])):
                if not isinstance(module,dict):
                    continue
                source = next((i for i in range(self.inspector.count()) if self.inspector.tabText(i)==module.get('title')), None)
                if source is not None:
                    self.inspector.tabBar().moveTab(source, min(target_index,self.inspector.count()-1))
                    self.inspector.setTabVisible(min(target_index,self.inspector.count()-1), bool(module.get('visible',True)))
            for i in range(self.inspector.count()):
                if self.inspector.tabText(i) == data.get('selected_module') and self.inspector.isTabVisible(i):
                    self.inspector.setCurrentIndex(i)
            self.tabs.blockSignals(True)
            for target, session_index in enumerate(data.get('tabs',[])):
                source = next((i for i in range(self.tabs.count()) if self.tabs.tabData(i)==session_index), None)
                if source is not None:
                    self.tabs.moveTab(source,min(target,self.tabs.count()-1))
            self.tabs.blockSignals(False)
            self.set_sidebar_collapsed(bool(data.get('sidebar_collapsed',False)))
            self.set_inspector_collapsed(bool(data.get('inspector_collapsed',False)))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            self.report_error(f'配置恢复失败，已保留可用设置：{exc}')
        finally:
            self._restoring = False
            self.rebuild_macro_list()
            self.rerender()
            self.refresh_devices()
            self.update_state()

    def closeEvent(self, event):
        if not self.ready:
            return super().closeEvent(event)
        if not self._closing:
            self.save_settings()
            self.save_timer.stop()
            self.detect_timer.stop()
            self.stop_macro()
            self._closing = True
            for s in self.sessions:
                self.disconnect_session(s)
        if self.workers or self.retired:
            event.ignore()
            QTimer.singleShot(50, self.close)
            return
        for i in range(len(self.sessions)):
            self.stop_logging(i)
        self.poll_timer.stop()
        self.tray.hide()
        QApplication.instance().removeEventFilter(self)
        event.accept()

    def about(self):
        QMessageBox.information(self, 'Serial Workbench',
            '真实 Qt 串口工作台\n支持多串口、ANSI、逐行宏、持续日志、条件提醒和配置恢复。\n'
            '屏幕保留最近 5000 条接收/发送记录；持续日志不受此限制。\n'
            '可打开历史日志文件：自动识别行首时间戳（无日期按文件日期补齐）与\n'
            'UTF-8/UTF-16/GBK 编码；识别结果在 SYS 摘要中说明。\n'
            'ANSI 仅解析颜色和样式，不模拟光标终端。')

    @staticmethod
    def dialog_buttons(dialog, layout):
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        return buttons

    @staticmethod
    def inline_form_error(layout):
        """Attach an inline validation message to a QFormLayout dialog.

        Returns show(message): keep the entered values, surface the error next
        to the fields, and leave the dialog open for correction.
        """
        error = QLabel('')
        error.setWordWrap(True)
        set_role(error, 'danger')
        error.hide()
        layout.addRow(error)

        def show(message):
            error.setText(message)
            error.show()
        return show


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-title', action='store_true')
    parser.add_argument('--zoom', type=int, default=125)
    parser.add_argument('--settings', type=Path)
    args = parser.parse_args()
    app = QApplication([])
    app.setStyle('Fusion')
    app.setFont(QFont('Microsoft YaHei UI', 7))
    window = Workbench(native_title=args.native_title, zoom=args.zoom, settings_path=args.settings)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
