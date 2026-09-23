#!/usr/bin/env python3
"""Passively identify the most likely UART baud rate from received bytes."""

import argparse
import math
import sys
import time
from dataclasses import dataclass

import serial


DEFAULT_BAUDS = (115200, 57600, 38400, 19200, 9600, 230400, 460800, 921600)


@dataclass(frozen=True)
class SampleScore:
    baud: int
    byte_count: int
    printable_ratio: float
    control_ratio: float
    score: float


def parse_bauds(value):
    try:
        bauds = tuple(dict.fromkeys(int(item.strip()) for item in value.split(",") if item.strip()))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("波特率列表必须是逗号分隔的正整数") from exc
    if not bauds or any(baud <= 0 for baud in bauds):
        raise argparse.ArgumentTypeError("波特率列表必须包含正整数")
    return bauds


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
    ) as connection:
        connection.reset_input_buffer()
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


def build_parser():
    parser = argparse.ArgumentParser(description="通过被动监听自动检测串口波特率")
    parser.add_argument("--port", required=True, help="串口，例如 COM11")
    parser.add_argument(
        "--bauds",
        type=parse_bauds,
        default=DEFAULT_BAUDS,
        help="候选波特率，使用英文逗号分隔",
    )
    parser.add_argument("--seconds", type=float, default=0.8, help="每个候选每轮监听秒数")
    parser.add_argument("--rounds", type=int, default=3, help="轮询候选波特率的轮数")
    parser.add_argument("--min-bytes", type=int, default=16, help="判定所需的最少接收字节数")
    return parser


def main():
    args = build_parser().parse_args()
    if args.seconds <= 0 or args.rounds <= 0 or args.min_bytes <= 0:
        raise SystemExit("seconds、rounds 和 min-bytes 必须大于 0")
    try:
        baud, scores, reason = detect_baud(
            args.port, args.bauds, args.seconds, args.rounds, args.min_bytes
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
    print("没有收到足够的可识别串口输出。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
