#!/usr/bin/env python3
"""Wait for the next attached or reattached serial port and print its name."""

import argparse
import json
import re
import time

from serial.tools import list_ports


def port_map():
    return {port.device.upper(): port for port in list_ports.comports()}


def natural_port_key(device):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", device.upper())]


def candidate_rank(port):
    text = f"{port.description} {port.hwid}".upper()
    has_usb_id = port.vid is not None and port.pid is not None
    is_bluetooth = "BTHENUM" in text or "BLUETOOTH" in text
    return (not has_usb_id, is_bluetooth, natural_port_key(port.device))


def choose_port(candidates):
    return min(candidates, key=candidate_rank)


def detect_next_port(timeout, interval):
    initial = port_map()
    initial_names = set(initial)
    removed_initial = set()
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        current = port_map()
        current_names = set(current)
        removed_initial.update(initial_names - current_names)
        candidate_names = (current_names - initial_names) | (current_names & removed_initial)
        if candidate_names:
            return choose_port([current[name] for name in candidate_names])
        time.sleep(interval)
    return None


def build_parser():
    parser = argparse.ArgumentParser(description="检测下一次接入或重新接入的串口")
    parser.add_argument("--timeout", type=float, default=120.0, help="等待超时秒数")
    parser.add_argument("--interval", type=float, default=0.4, help="扫描间隔秒数")
    parser.add_argument("--list-json", action="store_true", help="以 JSON 输出当前串口")
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
