#!/usr/bin/env python3
"""Share one serial port between an interactive terminal and command senders."""

import argparse
import os
import select
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import serial

from serial_baud_scan import DEFAULT_BAUDS


LINE_ENDINGS = {"cr": "\r", "lf": "\n", "crlf": "\r\n"}
BACKSPACES = {"bs": "\x08", "del": "\x7f"}


def close_socket(sock):
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def open_serial(port, baud):
    # serial_for_url also accepts normal COM names and lets us test with loop://.
    return serial.serial_for_url(port, baudrate=baud, timeout=0.05, write_timeout=0.5)


def run_bridge(args):
    # Also importable by the original standalone importlib test harness.
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from serial_service import SerialService

    auto_baud = None
    if getattr(args, 'autobaud', False):
        auto_baud = dict(enabled=True, active=bool(args.autobaud_probe))
        if args.autobaud_bauds:
            auto_baud['bauds'] = args.autobaud_bauds
        if args.autobaud_seconds is not None:
            auto_baud['seconds'] = args.autobaud_seconds
        if args.autobaud_rounds is not None:
            auto_baud['rounds'] = args.autobaud_rounds
    safe_port = ''.join(c if c.isalnum() else '_' for c in (args.port or 'released'))
    log_path = args.log or f"serial_{safe_port}_{datetime.now():%Y%m%d_%H%M%S}.log"
    service = SerialService(
        port=args.port, baud=args.baud, host=args.host, tcp=args.tcp,
        control=getattr(args, 'control', None) or args.tcp + 1,
        chardelay=args.chardelay, log=log_path, serial_factory=open_serial,
        auto_baud=auto_baud,
    ).start()
    print(f"bridge_start port={args.port} baud={args.baud} "
          f"tcp={args.host}:{service.tcp_port} control={service.control_port} log={log_path} "
          f"autobaud={'on' if auto_baud else 'off'}", flush=True)
    try:
        while not service.stop.wait(.2):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        service.close()


def receive_until_idle(sock, idle_seconds, max_seconds):
    output = bytearray()
    disconnected = False
    deadline = time.monotonic() + max_seconds
    last_receive = time.monotonic()
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            if time.monotonic() - last_receive >= idle_seconds:
                break
            continue
        if not chunk:
            disconnected = True
            break
        output.extend(chunk)
        last_receive = time.monotonic()
    return bytes(output), disconnected


def run_send(args):
    payload = args.data
    if args.newline:
        payload += LINE_ENDINGS[args.line_ending]
    sock = socket.create_connection((args.host, args.tcp), timeout=args.socket_timeout)
    sock.settimeout(args.socket_timeout)
    if payload:
        sock.sendall(payload.encode(args.encoding))
    output, disconnected = receive_until_idle(sock, args.idle, args.max_wait)
    close_socket(sock)
    sys.stdout.write(output.decode(args.encoding, errors="replace"))
    if disconnected:
        sys.stderr.write("[串口桥] 响应稳定前连接已经断开\n")
        return 2
    return 0


def run_connect(args):
    stop = threading.Event()
    socket_lock = threading.Lock()
    socket_state = {"socket": None}
    connected_once = False

    def get_socket():
        with socket_lock:
            return socket_state["socket"]

    def set_socket(value):
        with socket_lock:
            socket_state["socket"] = value

    def drop_socket(failed_socket):
        with socket_lock:
            if socket_state["socket"] is failed_socket:
                socket_state["socket"] = None
        close_socket(failed_socket)

    def send_bytes(data):
        current = get_socket()
        if current is None:
            print("\n[串口桥] 当前未连接，本次输入已丢弃", flush=True)
            return
        try:
            current.sendall(data)
        except OSError:
            drop_socket(current)
            print("\n[串口桥] 连接丢失，正在重新连接", flush=True)

    def translate_windows_key(first_char, get_char):
        if first_char == "\r":
            return LINE_ENDINGS[args.line_ending].encode(args.encoding)
        if first_char == "\t":
            return b"\t"
        if first_char in ("\b", "\x7f"):
            return BACKSPACES[args.backspace_mode].encode(args.encoding)
        if first_char in ("\x00", "\xe0"):
            second = get_char()
            return {
                "H": b"\x1b[A", "P": b"\x1b[B", "K": b"\x1b[D", "M": b"\x1b[C",
                "G": b"\x1b[H", "O": b"\x1b[F", "S": b"\x1b[3~",
            }.get(second, b"")
        return first_char.encode(args.encoding)

    def reader():
        nonlocal connected_once
        while not stop.is_set():
            current = get_socket()
            if current is None:
                try:
                    current = socket.create_connection((args.host, args.tcp), timeout=1)
                except OSError:
                    stop.wait(1)
                    continue
                current.settimeout(0.05)
                set_socket(current)
                state = "已重新连接" if connected_once else "已连接"
                connected_once = True
                print(f"{state} {args.host}:{args.tcp}; Ctrl+C exits", flush=True)
            try:
                data = current.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                data = b""
            if not data:
                drop_socket(current)
                if not stop.is_set():
                    print("\n[串口桥] 已断开，正在重新连接", flush=True)
                    stop.wait(1)
                continue
            sys.stdout.write(data.decode(args.encoding, errors="replace"))
            sys.stdout.flush()

    threading.Thread(target=reader, daemon=True).start()
    try:
        if os.name == "nt":
            import msvcrt

            while True:
                if msvcrt.kbhit():
                    char = msvcrt.getwch()
                    if char == "\x03":
                        break
                    send_bytes(translate_windows_key(char, msvcrt.getwch))
                time.sleep(0.01)
        else:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    continue
                data = os.read(sys.stdin.fileno(), 1024)
                if not data or b"\x03" in data:
                    break
                data = data.replace(b"\x7f", BACKSPACES[args.backspace_mode].encode())
                if args.line_ending != "lf":
                    data = data.replace(b"\n", LINE_ENDINGS[args.line_ending].encode())
                send_bytes(data)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        close_socket(get_socket())
        print("\n已退出串口终端")


def run_autobaud(args):
    """Trigger an online baud scan on a running bridge and report the outcome."""
    from serial_service_client import Client, RemoteError

    try:
        client = Client(args.host, args.control, timeout=5)
    except OSError as exc:
        sys.stderr.write(f"[串口桥] 无法连接控制端口 {args.host}:{args.control}：{exc}\n")
        return 4
    try:
        status = client.call('status')
        if not status.get('connected'):
            sys.stderr.write("[串口桥] 串口桥未连接物理串口，无法在线检测波特率。\n")
            return 4
        before = client.call('autobaud.status')
        params = dict(mode=args.mode, seconds=args.seconds, rounds=args.rounds)
        if args.bauds:
            params['bauds'] = list(args.bauds)
        if args.min_bytes:
            params['min_bytes'] = args.min_bytes
        try:
            client.call('serial.autobaud', **params)
        except RemoteError as exc:
            sys.stderr.write(f"[串口桥] 无法开始在线检测：{exc}\n")
            return 6 if exc.code in ('occupied', 'busy') else 4
        deadline = time.monotonic() + args.wait
        state = before
        while True:
            state = client.call('autobaud.status')
            if not state.get('scanning') and not state.get('requested'):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.3)
        # 'requested' without 'scanning' means the queued scan never started
        # (the device vanished after serial.autobaud); reporting "unchanged"
        # would hide the failure, and later scans keep answering 'busy'.
        if state.get('scanning') or state.get('requested'):
            sys.stderr.write("[串口桥] 等待超时，扫描仍在进行或尚未开始；可用 autobaud.status 查询结果。\n")
            return 5
        if state.get('last_reason'):
            print(f"在线检测失败：{state['last_reason']}", file=sys.stderr)
            return 3 if state['last_reason'] == 'ambiguous' else 2
        change = state.get('last_change')
        if change and change != before.get('last_change'):
            print(f"在线检测完成：波特率已从 {change['from']} 切换为 {change['to']}")
            print(f"autobaud_result: changed from={change['from']} to={change['to']}")
            return 0
        baud = status.get('config', {}).get('baudrate')
        print(f"在线检测完成：波特率保持 {baud}")
        print(f"autobaud_result: unchanged baud={baud}")
        return 0
    except (OSError, EOFError, RemoteError) as exc:
        # A dead control channel means the scan outcome is unknown (exit 4 =
        # bridge unreachable), not 'no signal' (2): the generic OSError handler
        # in main() would otherwise misreport it to automation.
        sys.stderr.write(f"[串口桥] 控制连接在检测期间断开：{exc}\n")
        return 4
    finally:
        client.close()


def bauds_list(value):
    try:
        bauds = tuple(dict.fromkeys(int(item.strip()) for item in value.split(",") if item.strip()))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("波特率列表必须是逗号分隔的正整数") from exc
    if not bauds or any(baud <= 0 for baud in bauds):
        raise argparse.ArgumentTypeError("波特率列表必须包含正整数")
    return bauds


def build_parser():
    parser = argparse.ArgumentParser(description="共享串口桥")
    commands = parser.add_subparsers(dest="command", required=True)

    bridge = commands.add_parser("bridge", help="独占串口并提供本机 TCP 共享端点")
    bridge.add_argument("--port", help="Omit to start with the device released")
    bridge.add_argument("--baud", type=int, default=115200)
    bridge.add_argument("--host", default="127.0.0.1")
    bridge.add_argument("--tcp", type=int, default=8888)
    bridge.add_argument("--chardelay", type=float, default=0.0)
    bridge.add_argument("--log")
    bridge.add_argument("--control", type=int, help="Management TCP port; default raw TCP + 1")
    bridge.add_argument("--autobaud", action="store_true",
                        help="监视接收乱码并自动重扫波特率（被动，不发送任何数据）")
    bridge.add_argument("--autobaud-probe", action="store_true",
                        help="允许自动重扫发送回车探测（适合安静设备；默认关闭）")
    bridge.add_argument("--autobaud-bauds", type=bauds_list, default=None,
                        help="自动重扫候选波特率，逗号分隔（默认 " + ",".join(map(str, DEFAULT_BAUDS)) + "）")
    bridge.add_argument("--autobaud-seconds", type=float, default=None,
                        help="自动重扫每个候选的监听秒数（默认 0.5）")
    bridge.add_argument("--autobaud-rounds", type=int, default=None,
                        help="自动重扫轮数（默认 1）")
    bridge.set_defaults(func=run_bridge)

    autobaud = commands.add_parser("autobaud", help="对运行中的串口桥发起在线波特率检测（桥保持运行）")
    autobaud.add_argument("--host", default="127.0.0.1")
    autobaud.add_argument("--control", type=int, default=8889, help="控制端口（默认 raw TCP + 1）")
    autobaud.add_argument("--mode", choices=("passive", "active"), default="passive",
                          help="passive 只监听；active 会发送回车探测")
    autobaud.add_argument("--bauds", type=bauds_list, default=None, help="候选波特率，逗号分隔")
    autobaud.add_argument("--seconds", type=float, default=0.5, help="每个候选每轮监听秒数")
    autobaud.add_argument("--rounds", type=int, default=1, help="轮询候选的轮数")
    autobaud.add_argument("--min-bytes", type=int, default=None, help="判定所需最少接收字节数")
    autobaud.add_argument("--wait", type=float, default=30.0, help="等待扫描完成的最长秒数")
    autobaud.set_defaults(func=run_autobaud)

    connect = commands.add_parser("connect", help="打开交互串口终端")
    connect.add_argument("--host", default="127.0.0.1")
    connect.add_argument("--tcp", type=int, default=8888)
    connect.add_argument("--encoding", default="utf-8")
    connect.add_argument("--line-ending", choices=LINE_ENDINGS, default="cr")
    connect.add_argument("--backspace-mode", choices=BACKSPACES, default="bs")
    connect.set_defaults(func=run_connect)

    send = commands.add_parser("send", help="通过串口桥发送一条命令")
    send.add_argument("data", nargs="?", default="")
    send.add_argument("--host", default="127.0.0.1")
    send.add_argument("--tcp", type=int, default=8888)
    send.add_argument("--encoding", default="utf-8")
    send.add_argument("--newline", action="store_true")
    send.add_argument("--line-ending", choices=LINE_ENDINGS, default="cr")
    send.add_argument("--idle", type=float, default=0.8)
    send.add_argument("--max-wait", type=float, default=5.0)
    send.add_argument("--socket-timeout", type=float, default=0.2)
    send.set_defaults(func=run_send)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        result = args.func(args)
    except (OSError, serial.SerialException) as exc:
        sys.stderr.write(f"[串口桥] {exc}\n")
        result = 2
    except KeyboardInterrupt:
        result = 130
    if isinstance(result, int):
        raise SystemExit(result)


if __name__ == "__main__":
    main()
