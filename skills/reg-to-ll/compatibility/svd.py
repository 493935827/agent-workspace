"""Deterministic, safe reproduction of the historical regtool SVD bytes."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from workbook_model import WorkbookModel, evaluate_integer_expression


@dataclass(frozen=True)
class CandidateOutput:
    sheet: str
    filename: str
    raw_bytes: bytes
    sha256: str


@dataclass(frozen=True)
class ByteMismatch:
    sheet: str
    filename: str
    reason: str
    first_offset: int | None
    expected_context: str
    actual_context: str
    expected_sha256: str
    actual_sha256: str
    xml_summary: str


@dataclass(frozen=True)
class ComparisonResult:
    matches: bool
    mismatches: tuple[ByteMismatch, ...]


def _hex(value, parameters=None):
    return hex(evaluate_integer_expression(value, parameters))


def _description(value):
    return escape((value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", ". "))


def _parameter_bounds(model):
    return {
        item.name: (
            evaluate_integer_expression(item.minimum if item.minimum is not None else item.minimum_raw),
            evaluate_integer_expression(item.maximum if item.maximum is not None else item.maximum_raw),
        )
        for item in model.parameters
    }


def _array_parts(expression, bounds):
    text = str(expression).strip().lower()
    if "+" not in text:
        return None
    base, dimension = (part.strip() for part in text.split("+", 1))
    name, increment = (part.strip() for part in dimension.split("*", 1))
    minimum, maximum = bounds[name]
    return base, name, int(increment), minimum, maximum


def _module_bytes(model, peripheral, bounds):
    width = model.project.data_width
    registers = peripheral.registers
    last = registers[-1]
    last_array = _array_parts(last.address_offset_raw, bounds)
    if last_array:
        base, _, increment, _, maximum = last_array
        block_size = _hex(base, {})
        block_size = hex(int(block_size, 16) + maximum * increment + width // 8)
    else:
        block_size = hex(evaluate_integer_expression(last.address_offset_raw) + width // 8)
    module = peripheral.name
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>', "", "<device>",
        f"\t<name>{escape(module.lower())}</name>", "\t<addressUnitBits>8</addressUnitBits>",
        f"\t<width>{width}</width>", f"\t<size>{width}</size>", "\t<peripherals>",
        f"\t\t<peripheral><!-- {escape(module.upper())}_START-->",
        f"\t\t\t<name>{escape(module.upper())}</name>",
        f"\t\t\t<description>{escape(module.upper())} module</description>",
        f"\t\t\t<groupName>{escape(module.upper())}</groupName>",
        "\t\t\t<baseAddress>0x00000000</baseAddress>", f"\t\t\t<size>{width}</size>",
        "\t\t\t<access>read-write</access>", "\t\t\t<resetValue>0x0</resetValue>",
        "\t\t\t<addressBlock>", "\t\t\t\t<offset>0x0</offset>",
        f"\t\t\t\t<size>{block_size}</size>", "\t\t\t\t<usage>registers</usage>",
        "\t\t\t</addressBlock>", "\t\t\t<registers>",
    ]
    for register in registers:
        name = escape(register.name.upper())
        address = register.address_offset_raw
        array = _array_parts(address, bounds)
        lines.append("\t\t\t\t<register>")
        if array:
            base, _, increment, minimum, maximum = array
            lines.extend((f"\t\t\t\t\t<dim>{maximum - minimum + 1}</dim>",
                          f"\t\t\t\t\t<dimIncrement>{increment}</dimIncrement>",
                          f"\t\t\t\t\t<dimIndex>{minimum}-{maximum}</dimIndex>",
                          f"\t\t\t\t\t<name>{name}%s</name>",
                          f"\t\t\t\t\t<displayName>{name}%s</displayName>"))
            address = hex(evaluate_integer_expression(base) + minimum * increment)
        else:
            lines.extend((f"\t\t\t\t\t<name>{name}</name>",
                          f"\t\t\t\t\t<displayName>{name}</displayName>"))
        reset = 0
        for field in register.fields:
            if field.name.upper().startswith(("RSV", "RESERVED")):
                continue
            low = int(field.bit_range.split(":")[-1])
            raw = field.reset_value_raw
            reset |= evaluate_integer_expression(0 if raw in (None, "") else raw) << low
        lines.extend((f"\t\t\t\t\t<description>{_description(register.description)}</description>",
                      f"\t\t\t\t\t<addressOffset>{escape(str(address).strip().lower())}</addressOffset>",
                      f"\t\t\t\t\t<size>{width}</size>", "\t\t\t\t\t<access>read-write</access>",
                      f"\t\t\t\t\t<resetValue>{hex(reset)}</resetValue>", "\t\t\t\t\t<fields>"))
        for field in register.fields:
            if field.name.upper().startswith(("RSV", "RESERVED")) or not field.name:
                continue
            parts = field.bit_range.split(":")
            high, low = (int(parts[0]), int(parts[-1]))
            lines.extend(("\t\t\t\t\t\t<field>",
                          f"\t\t\t\t\t\t\t<name>{escape(field.name.upper())}</name>",
                          f"\t\t\t\t\t\t\t<description>{_description(field.description)}</description>",
                          f"\t\t\t\t\t\t\t<bitOffset>{low}</bitOffset>",
                          f"\t\t\t\t\t\t\t<bitWidth>{high - low + 1}</bitWidth>",
                          "\t\t\t\t\t\t</field>"))
        lines.extend(("\t\t\t\t\t</fields>", "\t\t\t\t</register>"))
    lines.extend(("\t\t\t</registers>", f"\t\t</peripheral><!-- {escape(module.upper())}_END-->",
                  "\t</peripherals>", "</device>", ""))
    return ("\n".join(lines) + "\n").encode("utf-8")


def serialize_legacy_svd(model: WorkbookModel) -> tuple[CandidateOutput, ...]:
    """Serialize one deterministic legacy-compatible SVD per module."""
    if not model.peripherals or not model.project.data_width:
        raise ValueError("SVD 模型必须包含模块和 data width")
    # Validation is deliberately run through the shared safe-expression/layout
    # boundary.  Serialization retains the original array expression because
    # the legacy SVD represents it with CMSIS dim elements.
    model.validate_and_expand()
    bounds = _parameter_bounds(model)
    # regtool_cmd.py uses the basename before the first dot, then lower-cases
    # the worksheet name when it constructs ``<workbook>_<sheet>.svd``.
    workbook_prefix = Path(model.source.workbook).name.split(".", 1)[0]
    results = []
    for peripheral in model.peripherals:
        if "--" in peripheral.name or peripheral.name.endswith("-"):
            raise ValueError(f"模块名不能安全写入 XML 注释：{peripheral.name!r}")
        raw = _module_bytes(model, peripheral, bounds)
        filename = f"{workbook_prefix}_{peripheral.name.lower()}.svd"
        results.append(CandidateOutput(peripheral.name, filename, raw, hashlib.sha256(raw).hexdigest()))
    return tuple(results)


def _first_difference(expected, actual):
    for offset, pair in enumerate(zip(expected, actual)):
        if pair[0] != pair[1]:
            return offset
    return min(len(expected), len(actual)) if len(expected) != len(actual) else None


def _context(data, offset):
    if offset is None:
        return ""
    return data[max(0, offset - 16):offset + 17].decode("utf-8", errors="backslashreplace")


def _xml_summary(expected, actual):
    summaries = []
    for label, data in (("expected", expected), ("actual", actual)):
        try:
            root = ElementTree.fromstring(data)
            counts = Counter(element.tag for element in root.iter())
            summaries.append(f"{label}: root={root.tag}, elements={sum(counts.values())}, tags={dict(sorted(counts.items()))}")
        except ElementTree.ParseError as error:
            summaries.append(f"{label}: invalid XML ({error})")
    return "; ".join(summaries)


def compare_svd_outputs(candidates: Sequence[CandidateOutput], expected_outputs: Sequence) -> ComparisonResult:
    """Compare module filenames and bytes, returning actionable first-difference evidence."""
    actual = {item.sheet: item for item in candidates}
    expected = {item.sheet: item for item in expected_outputs}
    mismatches = []
    for sheet in sorted(actual.keys() | expected.keys()):
        left, right = expected.get(sheet), actual.get(sheet)
        expected_bytes = left.raw_bytes if left else b""
        actual_bytes = right.raw_bytes if right else b""
        filename = right.filename if right else (left.filename if left else "")
        offset = _first_difference(expected_bytes, actual_bytes)
        filenames_match = left is not None and right is not None and left.filename == right.filename
        if offset is None and filenames_match:
            continue
        mismatches.append(ByteMismatch(
            sheet, filename,
            ("missing expected module" if left is None else "missing candidate module" if right is None
             else "filename mismatch" if not filenames_match else "byte mismatch"),
            offset, _context(expected_bytes, offset), _context(actual_bytes, offset),
            hashlib.sha256(expected_bytes).hexdigest(), hashlib.sha256(actual_bytes).hexdigest(),
            _xml_summary(expected_bytes, actual_bytes),
        ))
    return ComparisonResult(not mismatches, tuple(mismatches))
