"""经过门禁的 SVDConv 调用与 ae350.h 双源验证公开接口。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from compatibility.svd_validation import SvdValidationResult, ValidationDiagnostic
from workbook_model import WorkbookModel, evaluate_integer_expression


@dataclass(frozen=True)
class SvdConvConfig:
    executable: Path
    invocation_prefix: tuple[str, ...] = ()
    timeout_seconds: float = 30.0
    generated_filename: str = "ae350.h"
    version_arguments: tuple[str, ...] = ("--version",)
    version_pattern: str = r"\bSVDConv\b.*\d"


@dataclass(frozen=True)
class HeaderOutputs:
    header_path: str
    register_count: int = 0
    field_count: int = 0
    field_macro_count: int = 0


@dataclass(frozen=True)
class HeaderEvidence:
    input_path: str
    input_sha256: str
    output_path: str
    evidence_path: str
    started_at: str
    completed_at: str
    svd_gate_passed: bool
    tool_path: str
    tool_version: str
    version_exit_code: int | None
    tool_invoked: bool
    command: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    log: str
    timed_out: bool
    cleanup_failed: bool
    error_evidence: tuple[str, ...]
    warning_evidence: tuple[str, ...]
    header_validation_executed: bool
    header_validation_passed: bool
    atomic_publication: bool
    validated_header_sha256: str
    output_sha256: str
    decision: str


@dataclass(frozen=True)
class HeaderResult:
    valid: bool
    can_continue: bool
    errors: tuple[ValidationDiagnostic, ...]
    warnings: tuple[ValidationDiagnostic, ...]
    outputs: HeaderOutputs
    evidence: HeaderEvidence

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "can_continue": self.can_continue,
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
            "outputs": asdict(self.outputs),
            "evidence": asdict(self.evidence),
        }


@dataclass(frozen=True)
class _ExpectedField:
    name: str
    low: int
    width: int


@dataclass(frozen=True)
class _ExpectedRegister:
    name: str
    offset: int
    fields: tuple[_ExpectedField, ...]
    array_base: str | None = None
    array_ordinal: int = 0
    array_count: int = 1


@dataclass(frozen=True)
class _ExpectedPeripheral:
    name: str
    registers: tuple[_ExpectedRegister, ...]


@dataclass(frozen=True)
class _HeaderRegister:
    name: str
    offset: int
    macro_name: str
    ordinal: int = 0
    array_count: int = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _diag(items, code, message, location=""):
    items.append(ValidationDiagnostic(code, message, location))


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(element, name):
    return next((item for item in element if _local(item.tag) == name), None)


def _children(element, name):
    return [item for item in element if _local(item.tag) == name]


def _text(element, name):
    item = _child(element, name)
    return "" if item is None else (item.text or "").strip()


def _integer(text):
    return int(text, 0)


def _expected_from_svd(path):
    root = ElementTree.parse(path).getroot()
    peripherals_element = _child(root, "peripherals")
    peripherals = []
    for peripheral in _children(peripherals_element, "peripheral") if peripherals_element is not None else ():
        registers_element = _child(peripheral, "registers")
        registers = []
        for register in _children(registers_element, "register") if registers_element is not None else ():
            fields_element = _child(register, "fields")
            fields = tuple(
                _ExpectedField(_text(field, "name"), _integer(_text(field, "bitOffset")), _integer(_text(field, "bitWidth")))
                for field in (_children(fields_element, "field") if fields_element is not None else ())
            )
            count_text = _text(register, "dim")
            count = _integer(count_text) if count_text else 1
            increment = _integer(_text(register, "dimIncrement")) if count_text else 0
            index_text = _text(register, "dimIndex")
            if count_text and index_text and "-" in index_text:
                first, last = index_text.split("-", 1)
                try:
                    indices = [str(value) for value in range(int(first), int(last) + 1)]
                except ValueError:
                    if len(first) == len(last) == 1 and first.isalpha() and last.isalpha():
                        indices = [chr(value) for value in range(ord(first), ord(last) + 1)]
                    else:
                        raise ValueError(f"无法展开 dimIndex：{index_text}")
            elif count_text and index_text:
                indices = [item.strip() for item in index_text.split(",")]
            else:
                indices = [str(index) for index in range(count)]
            name = _text(register, "name")
            offset = _integer(_text(register, "addressOffset"))
            registers.extend(
                _ExpectedRegister(
                    name.replace("%s", indices[index]), offset + increment * index, fields,
                    name.replace("%s", "") if count_text else None, index, count,
                )
                for index in range(count)
            )
        peripherals.append(_ExpectedPeripheral(_text(peripheral, "name"), tuple(registers)))
    return tuple(peripherals)


def _expected_from_model(model, svd_expected=()):
    expanded = model.validate_and_expand()
    svd_registers = {
        (peripheral.name.casefold(), register.name.casefold()): register
        for peripheral in svd_expected for register in peripheral.registers
    }
    result = []
    for peripheral in expanded.peripherals:
        registers = []
        for register in peripheral.registers:
            fields = []
            for field in register.fields:
                parts = field.bit_range.split(":")
                high, low = int(parts[0]), int(parts[-1])
                fields.append(_ExpectedField(field.name, low, high - low + 1))
            source = svd_registers.get((peripheral.name.casefold(), register.name.casefold()))
            registers.append(_ExpectedRegister(
                register.name, register.address_offset, tuple(fields),
                source.array_base if source else None,
                source.array_ordinal if source else 0,
                source.array_count if source else 1,
            ))
        result.append(_ExpectedPeripheral(peripheral.name, tuple(registers)))
    return tuple(result)


_STRUCT = re.compile(r"typedef\s+struct\s*\{(?P<body>.*?)\}\s*(?P<name>[A-Za-z_]\w*)_Type\s*;", re.S)
_DECL = re.compile(
    r"(?:(?:__(?:I|O|IO)M?)\s+)?(?:volatile\s+)?uint32_t\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:\[\s*(?P<count>\d+)\s*\])?\s*;"
)
_POS = re.compile(r"^\s*#define\s+(?P<name>[A-Za-z_]\w*)_Pos\s+\(?(?P<value>0[xX][0-9A-Fa-f]+|\d+)(?:U?L*)?\)?", re.M)
_MSK = re.compile(r"^\s*#define\s+(?P<name>[A-Za-z_]\w*)_Msk\s+(?P<value>[^\r\n/]+)", re.M)


def _mask_value(expression, positions):
    value = re.sub(r"(?<=[0-9A-Fa-f])[uUlL]+\b", "", expression.strip())
    value = re.sub(
        r"\b([A-Za-z_]\w*)_Pos\b",
        lambda match: str(positions.get(match.group(1).casefold(), -10_000)),
        value,
    )
    if not re.fullmatch(r"[\s()0-9a-fA-FxX|&~<>+\-*]+", value):
        raise ValueError(f"不支持的 Mask 表达式：{expression.strip()}")
    return evaluate_integer_expression(value)


def _parse_header(content):
    structures = {}
    for match in _STRUCT.finditer(content):
        offset = 0
        registers = []
        reserved = []
        for declaration in _DECL.finditer(match.group("body")):
            name = declaration.group("name")
            count = int(declaration.group("count") or "1")
            if name.upper().startswith("RESERVED"):
                reserved.append((offset, count * 4))
            else:
                registers.extend(
                    _HeaderRegister(f"{name}{index}" if count > 1 else name, offset + index * 4, name, index, count)
                    for index in range(count)
                )
            offset += count * 4
        structures[match.group("name").casefold()] = (tuple(registers), tuple(reserved))
    positions = {item.group("name").casefold(): int(item.group("value"), 0) for item in _POS.finditer(content)}
    masks = {}
    for item in _MSK.finditer(content):
        try:
            masks[item.group("name").casefold()] = _mask_value(item.group("value"), positions)
        except (SyntaxError, ValueError):
            continue
    return structures, positions, masks


def _accepted_register_names(peripheral, register):
    name = register.casefold()
    prefix = peripheral.casefold() + "_"
    return {name, name[len(prefix):] if name.startswith(prefix) else name}


def _compare_header(expected, source, structures, positions, masks, errors):
    for peripheral in expected:
        parsed = structures.get(peripheral.name.casefold())
        if parsed is None:
            _diag(errors, "HEADER_STRUCT_MISSING", f"头文件缺少 {source} 外设 {peripheral.name} 对应的结构体。", f"外设 {peripheral.name}")
            continue
        header_registers, reserved = parsed
        unmatched = list(header_registers)
        expected_offsets = {register.offset for register in peripheral.registers}
        required_gaps = []
        cursor = 0
        for register in sorted(peripheral.registers, key=lambda item: item.offset):
            if register.offset > cursor:
                required_gaps.append((cursor, register.offset - cursor))
            cursor = register.offset + 4
        if tuple(reserved) != tuple(required_gaps):
            _diag(errors, "HEADER_RESERVED_GAP_MISMATCH", f"头文件 RESERVED 布局与 {source} 不一致：期望 {required_gaps}，实际 {list(reserved)}。", f"外设 {peripheral.name}")
        expected_macro_fields = set()
        found_fields = set()
        register_names = set()
        for register in peripheral.registers:
            register_names.update(_accepted_register_names(peripheral.name, register.name))
        register_names.update(item.macro_name.casefold() for item in header_registers)
        array_mapping = {}
        for actual in header_registers:
            if actual.array_count <= 1 or actual.ordinal:
                continue
            slots = [item for item in header_registers if item.macro_name.casefold() == actual.macro_name.casefold()]
            candidates = [
                item for item in peripheral.registers
                if item.array_base is not None
                and item.array_base.casefold() == actual.macro_name.casefold()
                and item.array_count == actual.array_count
            ]
            if len(slots) == len(candidates) == actual.array_count:
                array_mapping.update({id(expected_item): slots[index] for index, expected_item in enumerate(candidates)})
        for register in peripheral.registers:
            names = _accepted_register_names(peripheral.name, register.name)
            actual = array_mapping.get(id(register))
            if actual not in unmatched:
                actual = next((item for item in unmatched if item.name.casefold() in names), None)
            location = f"外设 {peripheral.name}/寄存器 {register.name}"
            if actual is None:
                _diag(errors, "HEADER_REGISTER_MISSING", f"头文件缺少 {source} 中的寄存器。", location)
                continue
            unmatched.remove(actual)
            if actual.offset != register.offset:
                _diag(errors, "HEADER_REGISTER_OFFSET_MISMATCH", f"头文件寄存器偏移 {actual.offset:#x} 与 {source} 的 {register.offset:#x} 不一致。", location)
            for field in register.fields:
                macro_names = {actual.macro_name, *names}
                macro_stems = {
                    f"{peripheral.name}_{name}_{field.name}".casefold() for name in macro_names
                } | {f"{name}_{field.name}".casefold() for name in macro_names}
                stem = next((item for item in macro_stems if item in positions or item in masks), None)
                if stem is None:
                    _diag(errors, "HEADER_FIELD_MACRO_MISSING", f"头文件缺少 {source} 字段的 Pos/Mask 宏。", f"{location}/字段 {field.name}")
                    continue
                if stem in positions and stem in masks:
                    found_fields.add(stem)
                    expected_macro_fields.add(stem)
                if stem not in positions:
                    _diag(errors, "HEADER_POS_MISSING", f"头文件缺少 {source} 字段的 Pos 宏。", f"{location}/字段 {field.name}")
                elif positions[stem] != field.low:
                    _diag(errors, "HEADER_POS_MISMATCH", f"Pos={positions[stem]} 与 {source} 的 {field.low} 不一致。", f"{location}/字段 {field.name}")
                if stem not in masks:
                    _diag(errors, "HEADER_MASK_MISSING", f"头文件缺少 {source} 字段的 Mask 宏。", f"{location}/字段 {field.name}")
                else:
                    expected_mask = ((1 << field.width) - 1) << field.low
                    if masks[stem] != expected_mask:
                        _diag(errors, "HEADER_MASK_MISMATCH", f"Mask={masks[stem]:#x} 与 {source} 的 {expected_mask:#x} 不一致。", f"{location}/字段 {field.name}")
        macro_fields = {
            stem for stem in (set(positions) | set(masks))
            if any(
                stem.startswith(f"{peripheral.name}_{name}_".casefold())
                or stem.startswith(f"{name}_".casefold())
                for name in register_names
            )
        }
        expected_field_count = len(expected_macro_fields)
        if len(found_fields) != expected_field_count or len(macro_fields) != expected_field_count:
            _diag(errors, "HEADER_FIELD_COUNT_MISMATCH", f"头文件匹配到 {len(found_fields)} 个字段、实际含 {len(macro_fields)} 组字段宏，{source} 需要 {expected_field_count} 组。", f"外设 {peripheral.name}")
        for item in unmatched:
            if item.offset not in expected_offsets:
                _diag(errors, "HEADER_REGISTER_EXTRA", f"头文件存在 {source} 未定义的寄存器 {item.name}。", f"外设 {peripheral.name}")


def validate_header(header_path, svd_path, model: WorkbookModel | None) -> HeaderResult:
    """独立核对结构体布局、字段 Pos/Mask 与 SVD 和 WorkbookModel。"""
    started = _now()
    header = Path(header_path).resolve()
    svd = Path(svd_path).resolve()
    errors, warnings = [], []
    content = ""
    svd_expected = ()
    if not header.is_file():
        _diag(errors, "HEADER_FILE_MISSING", f"头文件不存在：{header}。")
    else:
        try:
            content = header.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _diag(errors, "HEADER_READ_FAILED", f"头文件读取失败：{exc}。")
    structures, positions, masks = _parse_header(content)
    if content and not structures:
        _diag(errors, "HEADER_STRUCT_MISSING", "头文件中没有可识别的 CMSIS 外设结构体。")
    if model is None:
        _diag(errors, "HEADER_MODEL_REQUIRED", "未提供 WorkbookModel，不能执行头文件双源验证。")
    if not svd.is_file():
        _diag(errors, "HEADER_SVD_MISSING", f"SVD 文件不存在：{svd}。")
    elif content:
        try:
            svd_expected = _expected_from_svd(svd)
            _compare_header(svd_expected, "SVD", structures, positions, masks, errors)
        except (OSError, ValueError, ElementTree.ParseError) as exc:
            _diag(errors, "HEADER_SVD_READ_FAILED", f"无法读取 SVD 作为头文件验证基准：{exc}。")
    if model is not None and content:
        try:
            _compare_header(_expected_from_model(model, svd_expected), "WorkbookModel", structures, positions, masks, errors)
        except (TypeError, ValueError) as exc:
            _diag(errors, "HEADER_MODEL_INVALID", f"WorkbookModel 无法用于头文件验证：{exc}。")
    register_count = sum(len(item[0]) for item in structures.values())
    field_names = set(positions) | set(masks)
    outputs = HeaderOutputs(str(header), register_count, len(field_names), len(positions) + len(masks))
    valid = not errors and bool(content) and model is not None and svd.is_file()
    evidence = HeaderEvidence(
        input_path=str(svd), input_sha256=hashlib.sha256(svd.read_bytes()).hexdigest() if svd.is_file() else "",
        output_path=str(header), evidence_path="", started_at=started, completed_at=_now(), svd_gate_passed=False,
        tool_path="", tool_version="", version_exit_code=None, tool_invoked=False, command=(), exit_code=None,
        stdout="", stderr="", log="", timed_out=False, cleanup_failed=False, error_evidence=(), warning_evidence=(),
        header_validation_executed=True, header_validation_passed=valid, atomic_publication=False,
        validated_header_sha256=hashlib.sha256(header.read_bytes()).hexdigest() if valid else "",
        output_sha256=hashlib.sha256(header.read_bytes()).hexdigest() if header.is_file() else "",
        decision="通过：头文件与 SVD/WorkbookModel 一致。" if valid else "阻断：头文件双源验证失败。",
    )
    return HeaderResult(valid, valid, tuple(errors), tuple(warnings), outputs, evidence)


class _WindowsJob:
    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC_LIMIT(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        limits = EXTENDED_LIMIT()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            kernel32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        if not kernel32.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
            kernel32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        self.handle = handle

    def close(self):
        if self.handle is not None:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
            kernel32.CloseHandle(self.handle)
            self.handle = None


def _terminate_process_tree(process, job=None):
    cleanup_failed = False
    if os.name == "nt":
        if job is not None and job.handle is not None:
            job.close()  # KILL_ON_JOB_CLOSE，不依赖 leader 是否仍存活。
        else:
            cleanup_failed = True
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:  # group 已完全退出也算清理完成
            pass
        except OSError:
            cleanup_failed = True
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            cleanup_failed = True
    return cleanup_failed


def _run(command, timeout):
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **options)
    job = None
    cleanup_failed = False
    try:
        job = _WindowsJob(process)
    except OSError:
        cleanup_failed = os.name == "nt"
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        if job is not None:
            job.close()
        return process.returncode, stdout, stderr, False, cleanup_failed
    except subprocess.TimeoutExpired as first:
        cleanup_failed = _terminate_process_tree(process, job) or cleanup_failed
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired as second:
            cleanup_failed = True
            try:
                process.kill()
            except OSError:
                pass
            stdout = second.stdout or first.stdout or ""
            stderr = second.stderr or first.stderr or ""
        return process.returncode, stdout, stderr, True, cleanup_failed


def _evidence_lines(stdout, stderr, log_text):
    raw_lines = (stdout + "\n" + stderr + "\n" + log_text).splitlines()
    lines = tuple(dict.fromkeys(line.strip() for line in raw_lines if line.strip()))
    def nonzero_summary(line, label):
        match = re.search(rf"(?:Found\s+)?(\d+)\s+{label}(?:\(s\))?", line, re.I)
        return bool(match and int(match.group(1)))
    def evidence(pattern, label):
        found = []
        for index, raw in enumerate(raw_lines):
            line = raw.strip()
            if re.search(pattern, line, re.I):
                detail = next((item.strip() for item in raw_lines[index + 1:] if item.strip()), "")
                found.append(f"{line} | {detail}" if detail else line)
            elif nonzero_summary(line, label):
                found.append(line)
        return tuple(dict.fromkeys(found))
    error_lines = evidence(r"\*\*\*\s*(ERROR|FATAL)|\bFATAL\b", "Error")
    warning_lines = evidence(r"\*\*\*\s*WARNING", "Warning")
    return error_lines, warning_lines


def write_result_evidence(path, payload):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _write_exclusive_staging(directory, prefix, raw):
    descriptor, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or not path.is_file():
            raise OSError("独占 staging 不是普通文件")
        return path
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _safe_generated_filename(value):
    return bool(value and value not in {".", ".."} and Path(value).name == value and "/" not in value and "\\" not in value and ":" not in value)


def _safe_candidate(path, directory):
    try:
        if path.resolve().parent != directory.resolve() or not path.is_file() or path.is_symlink():
            return False
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return not bool(attributes & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except OSError:
        return False


def generate_header(svd_path, model: WorkbookModel | None, svd_validation: SvdValidationResult, output_path, *, config: SvdConvConfig, evidence_path) -> HeaderResult:
    """仅在 #7 门禁通过后调用 SVDConv；验证临时产物后才原子发布。"""
    started = _now()
    svd = Path(svd_path).resolve()
    output = Path(output_path).resolve()
    evidence_file = Path(evidence_path).resolve()
    if evidence_file == output:
        raise ValueError("evidence_path 必须与 output_path 不同。")
    tool = Path(config.executable).resolve()
    errors, warnings = [], []
    version = stdout = stderr = log_text = ""
    version_exit = exit_code = None
    command = ()
    invoked = timed_out = cleanup_failed = validation_executed = validation_passed = published = False
    validated_header_hash = ""
    publication_backup = None
    error_evidence = warning_evidence = ()
    decision = ""
    outputs = HeaderOutputs(str(output))

    actual_hash = hashlib.sha256(svd.read_bytes()).hexdigest() if svd.is_file() else ""
    gate = bool(svd_validation.valid and svd_validation.can_continue)
    gate = gate and svd_validation.evidence.structural_check_passed
    gate = gate and svd_validation.evidence.consistency_check_passed
    gate = gate and svd_validation.evidence.compatibility_check_passed
    gate = gate and Path(svd_validation.evidence.input_path).resolve() == svd
    gate = gate and svd_validation.evidence.input_sha256 == actual_hash
    if not _safe_generated_filename(config.generated_filename):
        _diag(errors, "SVDCONV_FILENAME_INVALID", "generated_filename 必须是单个普通文件名，不能包含绝对路径、分隔符、. 或 ..。")
        decision = "阻断：生成文件名不安全，未调用工具。"
    elif not gate:
        _diag(errors, "HEADER_SVD_GATE_FAILED", "SVD 的兼容性、结构或 WorkbookModel 一致性门禁未全部通过；未调用 SVDConv，也未发布头文件。")
        decision = "阻断：SVD 验证门禁未通过，未调用工具。"
    elif not tool.is_file():
        _diag(errors, "SVDCONV_NOT_FOUND", f"SVDConv 不存在：{tool}。请配置绝对路径。")
        decision = "阻断：SVDConv 路径无效，未调用生成。"
    else:
        version_command = (str(tool), *config.invocation_prefix, *config.version_arguments)
        try:
            version_exit, version_stdout, version_stderr, version_timeout, version_cleanup_failed = _run(version_command, config.timeout_seconds)
            cleanup_failed = cleanup_failed or version_cleanup_failed
            version_text = version_stdout.strip() or version_stderr.strip()
            version_match = re.search(r"(?:SVDConv\s+|Header File Generator\s+V)(\d+(?:\.\d+)+)", version_text, re.I)
            version = f"SVDConv {version_match.group(1)}" if version_match else (version_text.splitlines()[0] if version_text else "")
        except OSError as exc:
            version_timeout = False
            _diag(errors, "SVDCONV_START_FAILED", f"无法启动 SVDConv：{exc}。")
        if version_timeout:
            _diag(errors, "SVDCONV_VERSION_TIMEOUT", f"SVDConv 版本查询超过 {config.timeout_seconds:g} 秒，已终止进程。")
        if cleanup_failed:
            _diag(errors, "SVDCONV_CLEANUP_FAILED", "SVDConv 进程树未能被可靠清理；拒绝继续并记录持久证据。")
        elif version_exit != 0 or not version or not re.search(config.version_pattern, version, re.I):
            _diag(errors, "SVDCONV_VERSION_FAILED", f"无法确认 SVDConv 版本（退出码 {version_exit}）；未执行生成。")
        if not errors:
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".ae350-header-", dir=output.parent) as temporary:
                temporary_path = Path(temporary)
                log_path = temporary_path / "svdconv.log"
                command = (
                    str(tool), *config.invocation_prefix, str(svd), "--generate=header", "--fields=macro",
                    "-o", str(temporary_path), "-b", str(log_path),
                )
                invoked = True
                try:
                    exit_code, stdout, stderr, timed_out, run_cleanup_failed = _run(command, config.timeout_seconds)
                    cleanup_failed = cleanup_failed or run_cleanup_failed
                except OSError as exc:
                    _diag(errors, "SVDCONV_START_FAILED", f"无法启动 SVDConv：{exc}。")
                log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
                error_evidence, warning_evidence = _evidence_lines(stdout, stderr, log_text)
                if timed_out:
                    _diag(errors, "SVDCONV_TIMEOUT", f"SVDConv 超过 {config.timeout_seconds:g} 秒，已终止并清理进程；旧头文件保持不变。")
                if cleanup_failed:
                    _diag(errors, "SVDCONV_CLEANUP_FAILED", "SVDConv 进程树未能被可靠清理；拒绝发布并记录持久证据。")
                if error_evidence:
                    _diag(errors, "SVDCONV_REPORTED_ERROR", "SVDConv 输出或日志包含 Error/Fatal；不使用错误白名单，拒绝发布。")
                if warning_evidence:
                    _diag(warnings, "SVDCONV_REPORTED_WARNING", f"已记录 {len(warning_evidence)} 条 Warning/汇总证据；继续以结构验证决定是否发布。")
                # SVDConv 以 1 表示“有 Warning、无 Error”；只有证据与该语义一致才可继续。
                if not timed_out and exit_code not in (0, 1):
                    _diag(errors, "SVDCONV_EXIT_FAILED", f"SVDConv 退出码为 {exit_code}；旧头文件保持不变。")
                elif exit_code == 1 and (error_evidence or not warning_evidence):
                    _diag(errors, "SVDCONV_EXIT_FAILED", "SVDConv 退出码 1 与日志中的纯 Warning 语义不一致；拒绝发布。")
                candidate = temporary_path / config.generated_filename
                if not _safe_candidate(candidate, temporary_path) and not errors:
                    _diag(errors, "SVDCONV_OUTPUT_UNSAFE", f"SVDConv 产物 {config.generated_filename} 不存在、不是普通文件或逃逸了临时目录。")
                if not errors:
                    staging = None
                    try:
                        # 候选只读取一次；之后仅验证并发布调用方独占创建的同目录 staging。
                        staging = _write_exclusive_staging(output.parent, ".ae350-validated-", candidate.read_bytes())
                        validation_executed = True
                        checked = validate_header(staging, svd, model)
                        validation_passed = checked.valid
                        errors.extend(checked.errors)
                        warnings.extend(checked.warnings)
                        outputs = HeaderOutputs(str(output), checked.outputs.register_count, checked.outputs.field_count, checked.outputs.field_macro_count)
                        if checked.valid:
                            validated_header_hash = _file_sha256(staging)
                            if output.is_file():
                                publication_backup = _write_exclusive_staging(output.parent, ".ae350-backup-", output.read_bytes())
                            os.replace(staging, output)
                            staging = None
                            try:
                                published = _file_sha256(output) == validated_header_hash
                            except OSError:
                                published = False
                            if not published:
                                if publication_backup is not None:
                                    try:
                                        os.replace(publication_backup, output)
                                        publication_backup = None
                                    except OSError as restore_error:
                                        _diag(
                                            errors, "HEADER_ROLLBACK_FAILED",
                                            f"发布校验失败且旧头文件恢复失败：{restore_error}。唯一备份保留在 {publication_backup}，请人工恢复。",
                                            str(publication_backup),
                                        )
                                else:
                                    try:
                                        output.unlink(missing_ok=True)
                                    except OSError as remove_error:
                                        _diag(errors, "HEADER_ROLLBACK_FAILED", f"首次发布校验失败且无法移除新头文件：{remove_error}。", str(output))
                                _diag(errors, "HEADER_PUBLISH_HASH_MISMATCH", "发布后读取失败或哈希与已验证 staging 不一致；已尝试恢复旧头文件。")
                    except OSError as exc:
                        _diag(errors, "HEADER_PUBLISH_FAILED", f"头文件 staging、验证或原子发布失败：{exc}；旧头文件保持不变。")
                    finally:
                        if staging is not None:
                            try:
                                staging.unlink()
                            except OSError:
                                pass
        if errors:
            decision = "阻断：工具兼容性、执行或头文件验证失败，未发布，旧头文件保持不变。"
        elif published:
            decision = "通过：SVDConv 退出成功且头文件通过 SVD/WorkbookModel 双重验证，已原子发布。"

    valid = not errors and published
    try:
        output_hash = _file_sha256(output) if output.is_file() else ""
    except OSError:
        output_hash = ""
    evidence = HeaderEvidence(
        input_path=str(svd), input_sha256=actual_hash, output_path=str(output), evidence_path=str(evidence_file),
        started_at=started, completed_at=_now(), svd_gate_passed=gate, tool_path=str(tool), tool_version=version,
        version_exit_code=version_exit, tool_invoked=invoked, command=tuple(command), exit_code=exit_code,
        stdout=stdout, stderr=stderr, log=log_text, timed_out=timed_out, cleanup_failed=cleanup_failed,
        error_evidence=tuple(error_evidence),
        warning_evidence=tuple(warning_evidence), header_validation_executed=validation_executed,
        header_validation_passed=validation_passed, atomic_publication=published,
        validated_header_sha256=validated_header_hash, output_sha256=output_hash, decision=decision,
    )
    result = HeaderResult(valid, valid, tuple(errors), tuple(warnings), outputs, evidence)
    try:
        write_result_evidence(evidence_file, result.to_json_dict())
    except OSError as evidence_error:
        _diag(errors, "HEADER_EVIDENCE_FAILED", f"最终证据原子落盘失败：{evidence_error}；正在回滚头文件。", str(evidence_file))
        if published:
            if publication_backup is not None:
                try:
                    os.replace(publication_backup, output)
                    publication_backup = None
                except OSError as restore_error:
                    _diag(
                        errors, "HEADER_ROLLBACK_FAILED",
                        f"证据落盘失败且旧头文件恢复失败：{restore_error}。唯一备份保留在 {publication_backup}，请人工恢复。",
                        str(publication_backup),
                    )
            else:
                try:
                    output.unlink(missing_ok=True)
                except OSError as remove_error:
                    _diag(errors, "HEADER_ROLLBACK_FAILED", f"证据落盘失败且无法移除首次生成的头文件：{remove_error}。", str(output))
        published = False
        decision = "阻断：最终 evidence 未能持久化；已回滚输出，未完成发布事务。"
        try:
            output_hash = _file_sha256(output) if output.is_file() else ""
        except OSError:
            output_hash = ""
        evidence = HeaderEvidence(
            input_path=str(svd), input_sha256=actual_hash, output_path=str(output), evidence_path=str(evidence_file),
            started_at=started, completed_at=_now(), svd_gate_passed=gate, tool_path=str(tool), tool_version=version,
            version_exit_code=version_exit, tool_invoked=invoked, command=tuple(command), exit_code=exit_code,
            stdout=stdout, stderr=stderr, log=log_text, timed_out=timed_out, cleanup_failed=cleanup_failed,
            error_evidence=tuple(error_evidence), warning_evidence=tuple(warning_evidence),
            header_validation_executed=validation_executed, header_validation_passed=validation_passed,
            atomic_publication=False, validated_header_sha256=validated_header_hash,
            output_sha256=output_hash, decision=decision,
        )
        return HeaderResult(False, False, tuple(errors), tuple(warnings), outputs, evidence)
    if publication_backup is not None and published:
        try:
            publication_backup.unlink()
        except OSError:
            pass
    return result


__all__ = [
    "HeaderEvidence", "HeaderOutputs", "HeaderResult", "SvdConvConfig",
    "generate_header", "validate_header", "write_result_evidence",
]
