#!/usr/bin/env python3
"""Identify the UART baud rate: passive listening or active Enter probing."""

import argparse
import sys
import time
from pathlib import Path

import serial

# Share the scoring core with the bridge's online re-scan (scripts/serial_baud_scan.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from serial_baud_scan import DEFAULT_BAUDS, SampleScore, rank_samples, score_sample


def parse_bauds(value):
    try:
        bauds = tuple(dict.fromkeys(int(item.strip()) for item in value.split(",") if item.strip()))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("波特率列表必须是逗号分隔的正整数") from exc
    if not bauds or any(baud <= 0 for baud in bauds):
        raise argparse.ArgumentTypeError("波特率列表必须包含正整数")
    return bauds


def parse_probe(value):
    """Turn a CLI escape string like ``\\r`` or ``help\\r`` into probe bytes."""
    # latin-1 round-trips the UTF-8 bytes that unicode_escape re-mapped, so
    # non-ASCII probes (e.g. ``复位\\r``) reach the device unchanged.
    return value.encode("utf-8").decode("unicode_escape").encode("latin-1")


def sample_baud(port, baud, seconds):
    """Open one candidate in read-only usage: no bytes or break signals are sent."""
    collected = bytearray()
    deadline = time.monotonic() + seconds
    with serial.Serial(
        port=port,
        baudrate=baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=min(0.1, seconds),
        write_timeout=0.1,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
        # Hold DTR/RTS low: opening the port must not reset boards that wire
        # these lines to reset/boot mode during "passive" detection.
        rts=False,
        dtr=False,
    ) as connection:
        connection.reset_input_buffer()
        while time.monotonic() < deadline:
            waiting = connection.in_waiting
            chunk = connection.read(min(max(waiting, 1), 4096))
            if chunk:
                collected.extend(chunk)
    return bytes(collected)


def probe_baud(port, baud, seconds, probe=b"\r", attempts=2):
    """Open one candidate, submit probe bytes, and collect the device reply.

    Unlike sample_baud this writes to the device; it suits shells that answer
    Enter with a prompt but stay silent otherwise. Opening the port may also
    reset boards wired to DTR/RTS, and their boot banner helps identification.
    """
    collected = bytearray()
    window = seconds / max(1, attempts)
    with serial.Serial(
        port=port,
        baudrate=baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=min(0.1, max(window, 0.01)),
        write_timeout=0.1,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    ) as connection:
        connection.reset_input_buffer()
        for _ in range(max(1, attempts)):
            connection.write(probe)
            deadline = time.monotonic() + window
            while time.monotonic() < deadline:
                waiting = connection.in_waiting
                chunk = connection.read(min(max(waiting, 1), 4096))
                if chunk:
                    collected.extend(chunk)
    return bytes(collected)


def detect_baud(port, bauds, seconds, rounds, min_bytes, sampler=sample_baud):
    samples = {baud: bytearray() for baud in bauds}
    for _ in range(rounds):
        for baud in bauds:
            samples[baud].extend(sampler(port, baud, seconds))

    return rank_samples(samples, min_bytes)


def detect_baud_active(port, bauds, seconds, rounds, min_bytes,
                       probe=b"\r", attempts=2, prober=probe_baud):
    samples = {baud: bytearray() for baud in bauds}
    for _ in range(rounds):
        for baud in bauds:
            samples[baud].extend(prober(port, baud, seconds, probe, attempts))

    return rank_samples(samples, min_bytes)


def build_parser():
    parser = argparse.ArgumentParser(description="自动检测串口波特率（被动监听或主动探测）")
    parser.add_argument("--port", required=True, help="串口，例如 COM11")
    parser.add_argument(
        "--bauds",
        type=parse_bauds,
        default=DEFAULT_BAUDS,
        help="候选波特率，使用英文逗号分隔",
    )
    parser.add_argument("--seconds", type=float, default=None,
                        help="每个候选每轮监听秒数（默认：被动 0.8，主动 0.5）")
    parser.add_argument("--rounds", type=int, default=3, help="轮询候选波特率的轮数")
    parser.add_argument("--min-bytes", type=int, default=None,
                        help="判定所需的最少接收字节数（默认：被动 16，主动 4）")
    parser.add_argument("--active", action="store_true",
                        help="主动探测：向设备发送探测字节并监听应答；适合带提示符但不主动输出日志的设备")
    parser.add_argument("--probe", default="\\r",
                        help="主动模式的探测字节，支持转义（默认 \\r；例如 \\n 或 help\\r）")
    parser.add_argument("--attempts", type=int, default=2, help="主动模式每个候选每轮的探测次数")
    return parser


def main():
    args = build_parser().parse_args()
    seconds = args.seconds if args.seconds is not None else (0.5 if args.active else 0.8)
    min_bytes = args.min_bytes if args.min_bytes is not None else (4 if args.active else 16)
    if args.seconds is not None and args.seconds <= 0:
        raise SystemExit("seconds 必须大于 0")
    if args.rounds <= 0 or args.min_bytes is not None and args.min_bytes <= 0:
        raise SystemExit("rounds 和 min-bytes 必须大于 0")
    if args.attempts <= 0:
        raise SystemExit("attempts 必须大于 0")
    try:
        if args.active:
            baud, scores, reason = detect_baud_active(
                args.port, args.bauds, seconds, args.rounds, min_bytes,
                probe=parse_probe(args.probe), attempts=args.attempts,
            )
        else:
            baud, scores, reason = detect_baud(
                args.port, args.bauds, seconds, args.rounds, min_bytes
            )
    except KeyboardInterrupt:
        return 130
    except (OSError, serial.SerialException) as exc:
        print(f"无法打开串口 {args.port}：{exc}", file=sys.stderr)
        return 4

    if baud is not None:
        print(baud)
        return 0

    received = sorted(
        (item for item in scores if item.byte_count),
        key=lambda item: item.score,
        reverse=True,
    )
    if reason == "ambiguous":
        summary = "、".join(
            f"{item.baud}（{item.byte_count} 字节）" for item in received[:3]
        )
        print(f"检测结果不够明确：{summary}", file=sys.stderr)
        return 3
    if args.active:
        print("没有收到可识别的设备应答。请确认设备会对回车输出提示符，或改用被动模式。", file=sys.stderr)
    else:
        print("没有收到足够的可识别串口输出。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
