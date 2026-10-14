#!/usr/bin/env python3
"""Pick or wait for a serial port: --pick-now chooses an attached USB port."""

import argparse
import json
import re
import sys
import time

from serial.tools import list_ports


def port_map(enumerator=None):
    return {port.device.upper(): port for port in (enumerator or list_ports.comports)()}


def natural_port_key(device):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", device.upper())]


def candidate_rank(port):
    text = f"{port.description} {port.hwid}".upper()
    has_usb_id = port.vid is not None and port.pid is not None
    is_bluetooth = "BTHENUM" in text or "BLUETOOTH" in text
    return (not has_usb_id, is_bluetooth, natural_port_key(port.device))


def choose_port(candidates):
    return min(candidates, key=candidate_rank)


def usb_serial_ports(enumerator=None):
    """Attached USB serial ports: VID/PID present, Bluetooth excluded."""
    return [
        port
        for port in port_map(enumerator).values()
        if port.vid is not None and port.pid is not None and not candidate_rank(port)[1]
    ]


def pick_attached_port(enumerator=None):
    """Best already-attached USB serial port, or None when none is suitable."""
    candidates = usb_serial_ports(enumerator)
    if not candidates:
        return None
    return choose_port(candidates)


def detect_next_port(timeout, interval, enumerator=None):
    initial = port_map(enumerator)
    initial_names = set(initial)
    removed_initial = set()
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        current = port_map(enumerator)
        current_names = set(current)
        removed_initial.update(initial_names - current_names)
        candidate_names = (current_names - initial_names) | (current_names & removed_initial)
        if candidate_names:
            return choose_port([current[name] for name in candidate_names])
        time.sleep(interval)
    return None


def build_parser():
    parser = argparse.ArgumentParser(description="检测串口：选择已接入的 USB 串口，或等待下一次接入")
    parser.add_argument("--timeout", type=float, default=120.0, help="等待超时秒数")
    parser.add_argument("--interval", type=float, default=0.4, help="扫描间隔秒数")
    parser.add_argument("--list-json", action="store_true", help="以 JSON 输出当前串口")
    parser.add_argument("--pick-now", action="store_true",
                        help="选择一个当前已接入的 USB 串口（排除蓝牙），而不是等待新插入")
    return parser


def main():
    args = build_parser().parse_args()
    if args.list_json:
        for port in sorted(port_map().values(), key=lambda item: natural_port_key(item.device)):
            print(
                json.dumps(
                    {
                        "device": port.device,
                        "description": port.description,
                        "hwid": port.hwid,
                        "vid": port.vid,
                        "pid": port.pid,
                    },
                    ensure_ascii=True,
                )
            )
        return 0
    if args.timeout <= 0 or args.interval <= 0:
        raise SystemExit("timeout 和 interval 必须大于 0")
    if args.pick_now:
        candidates = usb_serial_ports()
        if not candidates:
            # 标准输出保持机器可读；exit 5 表示当前没有可自动选择的 USB 串口。
            print("没有检测到已接入的 USB 串口。", file=sys.stderr)
            return 5
        best = choose_port(candidates)
        if len(candidates) > 1:
            names = "、".join(sorted(port.device for port in candidates))
            print(f"检测到多个 USB 串口：{names}；已选择 {best.device}", file=sys.stderr)
        print(best.device)
        return 0
    try:
        detected = detect_next_port(args.timeout, args.interval)
    except KeyboardInterrupt:
        return 130
    if detected is None:
        return 1
    # 标准输出只返回机器可读的端口号；中文提示由 PowerShell 菜单负责。
    print(detected.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
