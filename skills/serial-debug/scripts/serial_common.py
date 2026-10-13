"""UI-independent serial text, alert and macro rules shared by Tk and Qt."""
import math
import re

class AnsiLogParser:
    """Incremental SGR styling for an append-only log, not a cursor terminal."""

    COLORS = ("#000000", "#800000", "#008000", "#808000", "#000080", "#800080", "#008080", "#c0c0c0",
              "#808080", "#ff0000", "#00ff00", "#ffff00", "#0000ff", "#ff00ff", "#00ffff", "#ffffff")
    DEFAULT = (None, None, False, False, False, False, False, False)

    def __init__(self):
        self.reset()

    def reset(self):
        self.style = list(self.DEFAULT)  # foreground, background, bold, dim, italic, underline, reverse, strike
        self.state = "text"
        self.sequence = ""
        self.last_cr = False

    @classmethod
    def indexed_color(cls, value):
        if value < 16:
            return cls.COLORS[value]
        if value < 232:
            value -= 16
            levels = (0, 95, 135, 175, 215, 255)
            rgb = (levels[value // 36], levels[value // 6 % 6], levels[value % 6])
        else:
            rgb = (8 + (value - 232) * 10,) * 3
        return "#%02x%02x%02x" % rgb

    def apply_sgr(self):
        try:
            values = [int(part) if part else 0 for part in self.sequence.split(";")]
        except ValueError:
            return
        i = 0
        while i < len(values):
            value = values[i]
            if value == 0:
                self.style = list(self.DEFAULT)
            elif value in (1, 2, 3, 4, 7, 9):
                self.style[{1: 2, 2: 3, 3: 4, 4: 5, 7: 6, 9: 7}[value]] = True
            elif value == 22:
                self.style[2] = self.style[3] = False
            elif value in (23, 24, 27, 29):
                self.style[{23: 4, 24: 5, 27: 6, 29: 7}[value]] = False
            elif 30 <= value <= 37:
                self.style[0] = self.COLORS[value - 30]
            elif 40 <= value <= 47:
                self.style[1] = self.COLORS[value - 40]
            elif 90 <= value <= 97:
                self.style[0] = self.COLORS[value - 90 + 8]
            elif 100 <= value <= 107:
                self.style[1] = self.COLORS[value - 100 + 8]
            elif value in (39, 49):
                self.style[0 if value == 39 else 1] = None
            elif value in (38, 48):
                color = None
                if i + 2 < len(values) and values[i + 1] == 5:
                    index = values[i + 2]
                    if 0 <= index <= 255:
                        color = self.indexed_color(index)
                    i += 2
                elif i + 4 < len(values) and values[i + 1] == 2:
                    rgb = values[i + 2:i + 5]
                    if all(0 <= component <= 255 for component in rgb):
                        color = "#%02x%02x%02x" % tuple(rgb)
                    i += 4
                else:
                    break  # An incomplete extended color must not become unrelated attributes.
                if color is not None:
                    self.style[0 if value == 38 else 1] = color
            i += 1

    def feed(self, text):
        spans = []
        buffer = []

        def flush():
            if buffer:
                spans.append(("".join(buffer), tuple(self.style)))
                buffer.clear()

        for char in text:
            if self.state == "string":
                if char == "\x07":
                    self.state = "text"
                elif char == "\x1b":
                    self.state = "string_escape"
                continue
            if self.state == "string_escape":
                self.state = "text" if char == "\\" else "string"
                continue
            if self.state == "escape":
                if char == "[":
                    self.state = "csi"
                    self.sequence = ""
                elif char in "]PX^_":
                    self.state = "string"
                elif " " <= char <= "/":
                    self.state = "escape_intermediate"
                else:
                    self.state = "text"
                continue
            if self.state == "escape_intermediate":
                if "0" <= char <= "~":
                    self.state = "text"
                continue
            if self.state == "csi":
                if "@" <= char <= "~":
                    if char == "m":
                        self.apply_sgr()
                    self.state = "text"
                    self.sequence = ""
                elif char == "\x1b":
                    self.state = "escape"
                elif len(self.sequence) < 256 and " " <= char <= "?":
                    self.sequence += char
                else:
                    self.state = "text"
                    self.sequence = ""
                continue
            if char == "\x1b":
                flush()
                self.state = "escape"
            elif char == "\r":
                buffer.append("\n")
                self.last_cr = True
            elif char == "\n":
                if not self.last_cr:
                    buffer.append(char)
                self.last_cr = False
            elif char == "\x08" or char == "\x7f":
                # Backspace and delete are erase requests from the device; keep
                # them as markers so the session can edit the affected line.
                flush()
                buffer.append(char)
            elif char == "\t" or ord(char) >= 32 and char != "\x7f":
                buffer.append(char)
                self.last_cr = False
            # Ignore nonprinting C0 controls, including BEL, in the log view.
        flush()
        return spans


class AlertMonitor:
    """One-shot conditions over decoded RX text; timestamps use a monotonic clock."""

    DEFAULTS = {"enabled": False, "keywords": "", "seconds": 0.0,
                "lines": 0, "idle": 0.0, "sound": True, "popup": True,
                "windows": False, "taskbar": False}

    @classmethod
    def validate(cls, options):
        result = dict(cls.DEFAULTS)
        for key in ("enabled", "sound", "popup", "windows", "taskbar"):
            if key in options:
                if type(options[key]) is not bool:
                    raise ValueError("开关值无效")
                result[key] = options[key]
        result["keywords"] = str(options.get("keywords", "")).strip()
        for key in ("seconds", "lines", "idle"):
            value = float(options.get(key, 0))
            if not math.isfinite(value) or value < 0 or (key == "lines" and not value.is_integer()):
                raise ValueError("时间必须是非负数字，行数必须是非负整数。")
            result[key] = int(value) if key == "lines" else value
        if result["enabled"] and not any(result[k] for k in ("keywords", "seconds", "lines", "idle")):
            raise ValueError("请至少设置一个提醒条件。")
        return result

    def __init__(self):
        self.options = dict(self.DEFAULTS)
        self.reset()

    def reset(self, now=None):
        self.started = now
        self.last_rx = None
        self.count = 0
        self.tail = ""
        self.fired = set()

    def check(self, now, text="", received=False):
        if not self.options["enabled"] or self.started is None:
            return []
        reasons = []

        def fire(key, reason):
            if key not in self.fired:
                self.fired.add(key)
                reasons.append(reason)

        if received:
            self.last_rx = now
            self.count += text.count("\n")
            words = [word.strip() for word in self.options["keywords"].splitlines() if word.strip()]
            combined = self.tail + text
            for word in words:
                if word in combined:
                    fire("keywords", f"匹配提示词：{word}")
                    break
            keep = max((len(word) for word in words), default=1) - 1
            self.tail = combined[-keep:] if keep else ""
        if self.options["lines"] and self.count >= self.options["lines"]:
            fire("lines", f"累计收到 {self.count} 行打印")
        if self.options["seconds"] and now - self.started >= self.options["seconds"]:
            fire("seconds", f"计时已达到 {self.options['seconds']:g} 秒")
        idle_since = self.last_rx if self.last_rx is not None else self.started
        if self.options["idle"] and now - idle_since >= self.options["idle"]:
            fire("idle", f"已连续 {self.options['idle']:g} 秒没有收到数据")
        return reasons


def parse_macro_line(line, default_delay):
    port, delay = None, default_delay
    if re.match(r"^\s*\[(?:port|delay)\s*=", line, re.IGNORECASE):
        match = re.match(r"^\s*\[([^]]*)\][ \t]?(.*)$", line)
        if not match:
            raise ValueError("行设置缺少 ]，示例：[port=COM34, delay=500] status")
        seen = set()
        for option in match[1].split(","):
            key, separator, value = option.strip().partition("=")
            key, value = key.strip().lower(), value.strip()
            if not separator or key not in ("port", "delay") or key in seen:
                raise ValueError("行设置仅支持 port 和 delay，且不能重复")
            seen.add(key)
            if key == "port":
                if not value:
                    raise ValueError("port 不能为空")
                port = value
            else:
                if not value.isascii() or not value.isdecimal() or not 0 <= int(value) <= 60000:
                    raise ValueError("delay 必须为 0 到 60000 毫秒")
                delay = int(value)
        line = match[2]
    return port, delay, line

