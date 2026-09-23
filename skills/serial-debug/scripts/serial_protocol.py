"""Bounded, newline-delimited JSON protocol shared by all managed clients."""
import base64
import json
import re

VERSION = 1
MAX_MESSAGE = 262144
MAX_PAYLOAD = 65536


class ActionError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def encode(message):
    data = json.dumps(message, ensure_ascii=True, allow_nan=False).encode() + b'\n'
    if len(data) > MAX_MESSAGE:
        raise ActionError('too_large', 'Message exceeds 256 KiB')
    return data


def read_message(stream):
    line = stream.readline(MAX_MESSAGE + 1)
    if not line:
        raise EOFError()
    if len(line) > MAX_MESSAGE or not line.endswith(b'\n'):
        raise ActionError('too_large', 'Message exceeds 256 KiB or lacks a boundary')
    try:
        value = json.loads(line, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (ValueError, UnicodeError) as exc:
        raise ActionError('invalid_message', str(exc)) from exc
    if not isinstance(value, dict):
        raise ActionError('invalid_message', 'Expected JSON object')
    return value


def payload(action, params):
    data = params.get('data', '')
    if not isinstance(data, str):
        raise ActionError('invalid_input', 'data must be a string')
    try:
        if action == 'send.hex':
            if not re.fullmatch(r'(?:\s*[0-9a-fA-F]{2})*\s*', data):
                raise ValueError('HEX requires complete byte pairs, for example AA 55 01')
            result = bytes.fromhex(data)
        elif params.get('format') == 'base64':
            result = base64.b64decode(data, validate=True)
        else:
            encoding = params.get('encoding', 'utf-8')
            if encoding not in ('utf-8', 'ascii'):
                raise ValueError('encoding must be utf-8 or ascii')
            ending = {'none': '', 'cr': '\r', 'lf': '\n', 'crlf': '\r\n'}[params.get('newline', 'none')]
            result = (data + ending).encode(encoding)
    except (ValueError, KeyError, UnicodeError) as exc:
        raise ActionError('invalid_input', str(exc)) from exc
    if len(result) > MAX_PAYLOAD:
        raise ActionError('too_large', 'Send exceeds 64 KiB')
    return result
