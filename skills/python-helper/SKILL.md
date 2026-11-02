---
name: python-helper
description: Python quick reference for C/embedded-background engineers - idioms that replace C patterns, venv and pip freeze packaging, minimal pyproject.toml, breakpoints and logging, exception-to-C mapping, ctypes interop example. Use when writing or reviewing Python code, packaging a tool, debugging a script, or calling C from Python.
---

# python-helper

Quick reference tuned for readers coming from C and embedded firmware: every idiom below names the C habit it replaces.

## When to use

- Writing or reviewing Python where C habits leak in (manual index loops, hand-rolled cleanup).
- Setting up a venv, pinning dependencies, or starting a `pyproject.toml`.
- Reading a traceback, adding breakpoints or logging.
- Calling a C library from Python.

## Idioms (C habit → Python)

| Instead of (C habit) | Write (Python) |
|---|---|
| `for (i = 0; i < n; i++) ... a[i]` | `for i, item in enumerate(items):` |
| Two parallel arrays walked together | `for name, val in zip(names, values):` |
| Manual `fopen`/`fclose` pairing | `with open(path) as f:` — any context manager; no leak on exception |
| `sprintf` into a buffer | f-string: `f"{name}: {val:#04x}"` |
| Loop + `if` + append | list comprehension: `[x * 2 for x in xs if x > 0]` |
| Out-parameters for multiple returns | tuple unpacking: `ok, data = read_frame(buf)` |
| `#define` constant | module-level `UPPER_CASE` name (no preprocessor — it is just a name) |
| NULL check | `if obj is None:` (identity, not `==`) |
| `switch` | `match value:` (3.10+) or dict dispatch |

Gotchas that differ from C:

- Assignment never copies: `b = a` aliases the same list. Copy with `a.copy()` / `list(a)` / `copy.deepcopy(a)`.
- Integers are arbitrary precision — no overflow, but also no `uint8_t` wrap; use `& 0xFF` when a byte wrap is actually required.
- Default arguments are evaluated once at definition: `def f(x=[])` shares one list across all calls. Use `def f(x=None): x = x or []`.

## Packaging

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1        # POSIX: source .venv/bin/activate
pip install -r requirements.txt
pip freeze > requirements.txt     # pin only after the environment actually works
```

Minimal `pyproject.toml` (PEP 621) for an installable package:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "mytool"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []

[project.scripts]
mytool = "mytool.cli:main"
```

Then `pip install -e .` for an editable dev install. `uv pip ...` is a drop-in, faster pip where available.

## Debugging

- Breakpoint in code: `breakpoint()`. In pdb: `c` continue, `p expr` print, `l` list, `q` quit. Disable all of them with `PYTHONBREAKPOINT=0`.
- Post-mortem on a crash: `python -m pdb -c continue script.py` — you land in the exact failing frame with all locals intact.
- Logging configured once at entry (use `logging`, not bare `print`, in anything reusable):

  ```python
  import logging
  logging.basicConfig(
      level=logging.DEBUG,
      format="%(asctime)s %(levelname)s %(name)s: %(message)s",
  )
  log = logging.getLogger(__name__)
  log.debug("frame len=%d crc=%#04x", n, crc)   # lazy %-args, not f-strings
  ```

- Reading a traceback: bottom-up. The last line names the exception; the first frame that is *your* code (not the stdlib) is where to look. A `raise ... from e` chain reads oldest cause first.

Common exceptions ↔ C intuition:

| Exception | C intuition |
|---|---|
| `IndexError` | read/write past an array bound |
| `KeyError` | hash lookup miss |
| `TypeError` | wrong type passed where a specific one is required |
| `ValueError` | right type, out-of-domain value |
| `AttributeError` | `->member` on the wrong struct type |
| `FileNotFoundError` / `PermissionError` | `errno` ENOENT / EACCES |
| `RecursionError` | stack overflow |

## C interop — ctypes minimal example

```python
import ctypes

lib = ctypes.CDLL("./libcrc.so")            # Windows: ctypes.WinDLL("crc.dll")
lib.crc16_ccitt.argtypes = (ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t)
lib.crc16_ccitt.restype = ctypes.c_uint16

def crc16(data: bytes) -> int:
    buf = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    return lib.crc16_ccitt(buf, len(data))
```

Rules: always declare `argtypes`/`restype` — the default int marshaling silently truncates pointers. Pass `bytes` for `const char *`. On Windows, `ctypes.WinDLL(..., use_errno=True)` plus `ctypes.get_errno()` recovers `errno`. For anything beyond a handful of functions, generate bindings (cffi) instead of hand-writing large tables.
