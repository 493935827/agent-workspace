"""CMSIS-SVD 结构与 WorkbookModel 一致性的稳定验证入口。"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from workbook_model import WorkbookModel


@dataclass(frozen=True)
class ValidationDiagnostic:
    code: str
    message: str
    location: str = ""


@dataclass(frozen=True)
class ValidationOutputs:
    peripheral_count: int = 0
    register_count: int = 0
    field_count: int = 0


@dataclass(frozen=True)
class ValidationEvidence:
    input_path: str
    file_exists: bool
    input_size: int | None
    input_sha256: str
    started_at: str
    completed_at: str
    structural_check_executed: bool
    structural_check_passed: bool
    consistency_check_executed: bool
    consistency_check_passed: bool
    compatibility_check_executed: bool
    compatibility_check_passed: bool
    model_source: str


@dataclass(frozen=True)
class SvdValidationResult:
    valid: bool
    can_continue: bool
    errors: tuple[ValidationDiagnostic, ...]
    warnings: tuple[ValidationDiagnostic, ...]
    outputs: ValidationOutputs
    evidence: ValidationEvidence

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
class _Field:
    name: str
    low: int
    width: int
    access: str | None


@dataclass(frozen=True)
class _Register:
    name: str
    address: int
    size: int
    access: str | None
    reset: int | None
    fields: tuple[_Field, ...]


@dataclass(frozen=True)
class _Peripheral:
    name: str
    base_address: int
    registers: tuple[_Register, ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element, name):
    return [child for child in element if _local_name(child.tag) == name]


def _child(element, name):
    return next(iter(_children(element, name)), None)


def _text(element, name):
    child = _child(element, name)
    return None if child is None else (child.text or "").strip()


def _diagnostic(errors, code, message, location=""):
    errors.append(ValidationDiagnostic(code, message, location))


def _required(element, name, errors, location):
    value = _text(element, name)
    if value is None or not value:
        _diagnostic(errors, "SVD_REQUIRED_NODE_MISSING", f"缺少必需 XML 节点 {name}；请补充后重新生成 SVD。", location)
        return None
    return value


def _access(value, errors, location):
    allowed = {"read-only", "write-only", "read-write", "writeOnce", "read-writeOnce"}
    if value is not None and value not in allowed:
        _diagnostic(errors, "SVD_ACCESS_INVALID", f"access“{value}”不是 CMSIS-SVD 支持的取值。", location)
    return value


def _integer(text, errors, *, code, label, location, minimum=0):
    if text is None:
        return None
    try:
        value = int(text, 0)
    except (TypeError, ValueError):
        _diagnostic(errors, code, f"{label}“{text}”不是有效整数；可使用十进制或 0x 十六进制。", location)
        return None
    if value < minimum:
        _diagnostic(errors, code, f"{label}必须不小于 {minimum}，当前为 {value}。", location)
        return None
    return value


def _dimension_indices(text, count):
    if text is None:
        return [str(index) for index in range(count)]
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) == 1 and "-" in parts[0]:
        first, last = parts[0].split("-", 1)
        try:
            values = [str(value) for value in range(int(first), int(last) + 1)]
        except ValueError:
            values = []
        if len(values) == count:
            return values
    return parts


def _parse_structure(root, errors):
    if _local_name(root.tag) != "device":
        _diagnostic(errors, "SVD_ROOT_INVALID", "XML 根节点必须是 device。", "/")
        return (), ValidationOutputs()
    _required(root, "name", errors, "device")
    address_unit = _integer(
        _required(root, "addressUnitBits", errors, "device"), errors,
        code="SVD_NUMERIC_INVALID", label="addressUnitBits", location="device", minimum=1,
    )
    default_width = _integer(
        _required(root, "width", errors, "device"), errors,
        code="SVD_NUMERIC_INVALID", label="width", location="device", minimum=1,
    )
    peripherals_element = _child(root, "peripherals")
    if peripherals_element is None:
        _diagnostic(errors, "SVD_REQUIRED_NODE_MISSING", "缺少必需 XML 节点 peripherals；SVD 中没有可验证的外设。", "device")
        return (), ValidationOutputs()

    device_access = _access(_text(root, "access"), errors, "device")
    device_reset = _integer(_text(root, "resetValue"), errors, code="SVD_NUMERIC_INVALID", label="resetValue", location="device")
    peripherals = []
    register_count = field_count = 0
    for peripheral_element in _children(peripherals_element, "peripheral"):
        name = _required(peripheral_element, "name", errors, "peripheral") or "<未命名外设>"
        location = f"外设 {name}"
        base = _integer(
            _required(peripheral_element, "baseAddress", errors, location), errors,
            code="SVD_NUMERIC_INVALID", label="baseAddress", location=location,
        )
        registers_element = _child(peripheral_element, "registers")
        if registers_element is None:
            _diagnostic(errors, "SVD_REQUIRED_NODE_MISSING", "缺少必需 XML 节点 registers。", location)
            continue
        peripheral_size = _integer(_text(peripheral_element, "size"), errors, code="SVD_NUMERIC_INVALID", label="size", location=location, minimum=1)
        peripheral_access = _access(_text(peripheral_element, "access"), errors, location) or device_access
        peripheral_reset = _integer(_text(peripheral_element, "resetValue"), errors, code="SVD_NUMERIC_INVALID", label="resetValue", location=location)
        if peripheral_reset is None:
            peripheral_reset = device_reset
        registers = []
        occupied_addresses = set()
        for register_element in _children(registers_element, "register"):
            register_name = _required(register_element, "name", errors, location) or "<未命名寄存器>"
            register_location = f"{location}/寄存器 {register_name}"
            address = _integer(
                _required(register_element, "addressOffset", errors, register_location), errors,
                code="SVD_REGISTER_ADDRESS_INVALID", label="addressOffset", location=register_location,
            )
            size = _integer(
                _text(register_element, "size") or (str(peripheral_size) if peripheral_size else None) or (str(default_width) if default_width else None),
                errors, code="SVD_NUMERIC_INVALID", label="size", location=register_location, minimum=1,
            )
            if address is not None and size and address % max(1, size // max(1, address_unit or 8)):
                _diagnostic(errors, "SVD_REGISTER_ADDRESS_INVALID", f"addressOffset {address:#x} 未按 {size // max(1, address_unit or 8)} 字节对齐。", register_location)
            access = _access(_text(register_element, "access"), errors, register_location) or peripheral_access
            reset_text = _text(register_element, "resetValue")
            reset = _integer(reset_text, errors, code="SVD_NUMERIC_INVALID", label="resetValue", location=register_location)
            if reset_text is None:
                reset = peripheral_reset
            if reset is not None and size is not None and reset >= (1 << size):
                _diagnostic(errors, "SVD_NUMERIC_INVALID", f"resetValue {reset:#x} 超出 {size} 位寄存器范围。", register_location)
            fields_element = _child(register_element, "fields")
            if fields_element is None:
                _diagnostic(errors, "SVD_REQUIRED_NODE_MISSING", "缺少必需 XML 节点 fields。", register_location)
                fields_elements = []
            else:
                fields_elements = _children(fields_element, "field")
            fields = []
            occupied_bits = set()
            for field_element in fields_elements:
                field_name = _required(field_element, "name", errors, register_location) or "<未命名字段>"
                field_location = f"{register_location}/字段 {field_name}"
                low = _integer(
                    _required(field_element, "bitOffset", errors, field_location), errors,
                    code="SVD_FIELD_RANGE_INVALID", label="bitOffset", location=field_location,
                )
                width = _integer(
                    _required(field_element, "bitWidth", errors, field_location), errors,
                    code="SVD_FIELD_RANGE_INVALID", label="bitWidth", location=field_location, minimum=1,
                )
                if low is not None and width is not None:
                    bits = set(range(low, low + width))
                    if size is not None and low + width > size:
                        _diagnostic(errors, "SVD_FIELD_RANGE_INVALID", f"位范围 [{low + width - 1}:{low}] 超出 {size} 位寄存器。", field_location)
                    if occupied_bits & bits:
                        _diagnostic(errors, "SVD_FIELD_RANGE_INVALID", "位范围与同一寄存器中的其他字段重叠。", field_location)
                    occupied_bits |= bits
                    field_access = _access(_text(field_element, "access"), errors, field_location) or access
                    fields.append(_Field(field_name, low, width, field_access))
            dim_text = _text(register_element, "dim")
            dim = _integer(dim_text, errors, code="SVD_NUMERIC_INVALID", label="dim", location=register_location, minimum=1) if dim_text is not None else 1
            increment = _integer(_text(register_element, "dimIncrement"), errors, code="SVD_NUMERIC_INVALID", label="dimIncrement", location=register_location, minimum=1) if dim_text is not None else 0
            indices = _dimension_indices(_text(register_element, "dimIndex"), dim or 0)
            if dim is not None and len(indices) != dim:
                _diagnostic(errors, "SVD_NUMERIC_INVALID", f"dimIndex 数量 {len(indices)} 与 dim {dim} 不一致。", register_location)
            if dim_text is not None and "%s" not in register_name:
                _diagnostic(errors, "SVD_REQUIRED_NODE_MISSING", "数组寄存器 name 必须包含 %s 占位符。", register_location)
            if address is not None and size is not None and dim is not None and increment is not None:
                for index, suffix in enumerate(indices):
                    expanded_address = address + index * increment
                    expanded_name = register_name.replace("%s", suffix)
                    expanded_location = f"{location}/寄存器 {expanded_name}"
                    if expanded_address in occupied_addresses:
                        _diagnostic(errors, "SVD_REGISTER_ADDRESS_INVALID", f"addressOffset {expanded_address:#x} 与同一外设中的其他寄存器重复。", expanded_location)
                    occupied_addresses.add(expanded_address)
                    registers.append(_Register(expanded_name, expanded_address, size, access, reset, tuple(fields)))
                    register_count += 1
                    field_count += len(fields)
        if base is not None:
            peripherals.append(_Peripheral(name, base, tuple(registers)))
    return tuple(peripherals), ValidationOutputs(len(peripherals), register_count, field_count)


def _key(name):
    return name.casefold()


def _expected_register_names(peripheral_name, register_name):
    names = {_key(register_name)}
    prefix = peripheral_name + "_"
    if register_name.casefold().startswith(prefix.casefold()):
        names.add(_key(register_name[len(prefix):]))
    return names


def _aggregate_access(fields):
    readable = any(item.access.cmsis_access in {"read-write", "read-only", "writeOnce"} for item in fields)
    writable = any(item.access.cmsis_access in {"read-write", "write-only", "writeOnce"} for item in fields)
    return "read-write" if readable and writable else "read-only" if readable else "write-only" if writable else "read-write"


def _compare_model(peripherals, model, errors):
    actual_peripherals = {_key(item.name): item for item in peripherals}
    for expected_peripheral in model.validate_and_expand().peripherals:
        actual_peripheral = actual_peripherals.pop(_key(expected_peripheral.name), None)
        location = f"外设 {expected_peripheral.name}"
        if actual_peripheral is None:
            _diagnostic(errors, "SVD_PERIPHERAL_MISSING", "SVD 缺少工作簿中的外设。", location)
            continue
        unmatched = list(actual_peripheral.registers)
        for expected_register in expected_peripheral.registers:
            accepted_names = _expected_register_names(expected_peripheral.name, expected_register.name)
            actual_register = next((item for item in unmatched if _key(item.name) in accepted_names), None)
            register_location = f"{location}/寄存器 {expected_register.name}"
            if actual_register is None:
                _diagnostic(errors, "SVD_REGISTER_MISSING", "SVD 缺少工作簿中的寄存器。", register_location)
                continue
            unmatched.remove(actual_register)
            if actual_register.address != expected_register.address_offset:
                _diagnostic(errors, "SVD_REGISTER_ADDRESS_MISMATCH", f"地址不一致：工作簿为 {expected_register.address_offset:#x}，SVD 为 {actual_register.address:#x}。", register_location)
            expected_access = expected_register.access.cmsis_access if expected_register.access else _aggregate_access(expected_register.fields)
            if actual_register.access != expected_access:
                _diagnostic(errors, "SVD_REGISTER_ACCESS_MISMATCH", f"access 不一致：工作簿为 {expected_access}，SVD 为 {actual_register.access or '未定义'}。", register_location)
            expected_reset = expected_register.reset_value_raw
            if actual_register.reset != expected_reset:
                _diagnostic(errors, "SVD_REGISTER_RESET_MISMATCH", f"复位值不一致：工作簿为 {expected_reset:#x}，SVD 为 {actual_register.reset!r}。", register_location)
            actual_fields = {_key(item.name): item for item in actual_register.fields}
            for expected_field in expected_register.fields:
                field_location = f"{register_location}/字段 {expected_field.name}"
                actual_field = actual_fields.pop(_key(expected_field.name), None)
                if actual_field is None:
                    _diagnostic(errors, "SVD_FIELD_MISSING", "SVD 缺少工作簿中的字段。", field_location)
                    continue
                parts = expected_field.bit_range.split(":")
                high, low = int(parts[0]), int(parts[-1])
                if (actual_field.low, actual_field.width) != (low, high - low + 1):
                    _diagnostic(errors, "SVD_FIELD_RANGE_MISMATCH", f"位范围不一致：工作簿为 [{high}:{low}]，SVD 为 [{actual_field.low + actual_field.width - 1}:{actual_field.low}]。", field_location)
                if actual_field.access != expected_field.access.cmsis_access:
                    _diagnostic(errors, "SVD_FIELD_ACCESS_MISMATCH", f"access 不一致：工作簿为 {expected_field.access.cmsis_access}，SVD 为 {actual_field.access or '未定义'}。", field_location)
            for item in actual_fields.values():
                _diagnostic(errors, "SVD_FIELD_EXTRA", "SVD 中存在工作簿未定义的字段。", f"{register_location}/字段 {item.name}")
        for item in unmatched:
            _diagnostic(errors, "SVD_REGISTER_EXTRA", "SVD 中存在工作簿未定义的寄存器。", f"{location}/寄存器 {item.name}")
    for item in actual_peripherals.values():
        _diagnostic(errors, "SVD_PERIPHERAL_EXTRA", "SVD 中存在工作簿未定义的外设。", f"外设 {item.name}")


def validate_svd(svd_path, model: WorkbookModel | None, *, compatibility=None) -> SvdValidationResult:
    """实际解析并验证 SVD；任何必需检查缺失或失败都会阻断下游。"""
    started = _now()
    path = Path(svd_path).resolve()
    errors = []
    warnings = []
    exists = path.is_file()
    raw = b""
    structural_executed = consistency_executed = False
    structural_passed = consistency_passed = False
    outputs = ValidationOutputs()
    peripherals = ()
    if not exists:
        _diagnostic(errors, "SVD_FILE_MISSING", f"SVD 文件不存在：{path}。请先生成文件再验证。")
    else:
        try:
            raw = path.read_bytes()
            structural_executed = True
            before = len(errors)
            root = ElementTree.fromstring(raw)
            peripherals, outputs = _parse_structure(root, errors)
            structural_passed = len(errors) == before
        except (OSError, ElementTree.ParseError) as exc:
            structural_executed = True
            _diagnostic(errors, "SVD_XML_INVALID", f"XML 读取或解析失败：{exc}。请检查标签闭合和文件编码。")

    if model is None:
        _diagnostic(errors, "SVD_MODEL_REQUIRED", "未提供 WorkbookModel，无法实际执行 Excel→SVD 一致性检查。")
    elif structural_passed:
        consistency_executed = True
        before = len(errors)
        try:
            _compare_model(peripherals, model, errors)
        except (TypeError, ValueError) as exc:
            _diagnostic(errors, "SVD_MODEL_INVALID", f"WorkbookModel 无法用于一致性检查：{exc}")
        consistency_passed = len(errors) == before

    compatibility_executed = compatibility is not None
    compatibility_passed = bool(getattr(compatibility, "matches", False)) if compatibility_executed else False
    if not compatibility_executed:
        _diagnostic(errors, "SVD_COMPATIBILITY_REQUIRED", "未提供兼容性检查结果，无法确认历史输出兼容性。")
    elif not compatibility_passed:
        mismatch_count = len(getattr(compatibility, "mismatches", ()))
        _diagnostic(errors, "SVD_COMPATIBILITY_FAILED", f"历史输出兼容性检查失败（{mismatch_count} 处差异）；请查看兼容性证据。")

    evidence = ValidationEvidence(
        str(path), exists, len(raw) if exists else None,
        hashlib.sha256(raw).hexdigest() if exists else "", started, _now(),
        structural_executed, structural_passed,
        consistency_executed, consistency_passed,
        compatibility_executed, compatibility_passed,
        model.source.workbook if model is not None else "",
    )
    valid = not errors and structural_passed and consistency_passed and compatibility_passed
    return SvdValidationResult(valid, valid, tuple(errors), tuple(warnings), outputs, evidence)


__all__ = [
    "SvdValidationResult", "ValidationDiagnostic", "ValidationEvidence",
    "ValidationOutputs", "validate_svd",
]
