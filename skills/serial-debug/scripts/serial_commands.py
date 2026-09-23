"""Reproducible command grammar and bounded byte-stream presentation, without Qt."""
import codecs
from collections import deque
import json

HELP = '''Commands: help | clear | status | serial.list | serial.close | serial.reconnect
serial.open {"port":"COM10","baudrate":57600}
serial.configure {"baudrate":115200,"bytesize":8,"stopbits":1,"parity":"N"}
send {"data":"help","encoding":"utf-8","newline":"cr","chardelay":0.005}
send.hex {"data":"AA 55 01 02 FF"}
agent.acquire | agent.heartbeat | agent.release | agent.takeover
Grammar: action followed by an optional JSON object. JSON quotes and escapes apply.
TX written means driver acceptance, not device command success.'''


def parse_command(text):
    pieces = text.strip().split(None, 1)
    if not pieces:
        raise ValueError('Enter an action; use help for examples')
    params = json.loads(pieces[1]) if len(pieces) == 2 else {}
    if not isinstance(params, dict):
        raise ValueError('Command parameters must be a JSON object')
    return pieces[0], params


def format_command(action, params):
    return action + (' ' + json.dumps(params, ensure_ascii=False, allow_nan=False) if params else '')


class StreamBuffer:
    def __init__(self, capacity=262144):
        self.capacity = capacity
        self.chunks = deque()
        self.raw_size = 0
        self.dropped = 0
        self.encoding = 'utf-8'
        self.decoders = {}

    def append(self, direction, data):
        decoder = self.decoders.setdefault(direction, codecs.getincrementaldecoder(self.encoding)(errors='replace'))
        text = decoder.decode(data)
        self.chunks.append((direction, data))
        self.raw_size += len(data)
        while self.raw_size > self.capacity:
            old_direction, old = self.chunks.popleft()
            removed = min(len(old), self.raw_size - self.capacity)
            if removed < len(old):
                self.chunks.appendleft((old_direction, old[removed:]))
            self.raw_size -= removed
            self.dropped += removed
        return text

    def clear(self):
        self.chunks.clear()
        self.raw_size = 0
        self.decoders.clear()

    def render(self, mode='text', encoding='utf-8'):
        decoders = {}
        result = []
        # Join adjacent same-direction blocks; a read block is not a protocol frame.
        groups = []
        for direction, data in self.chunks:
            if groups and groups[-1][0] == direction:
                groups[-1][1].extend(data)
            else:
                groups.append((direction, bytearray(data)))
        for direction, data in groups:
            if mode == 'hex':
                text = data.hex(' ').upper()
            else:
                decoder = decoders.setdefault(direction, codecs.getincrementaldecoder(encoding)(errors='replace'))
                text = decoder.decode(data)
            if text:
                result.append(f'[{direction.upper()}] {text}')
        return '\n'.join(result)
