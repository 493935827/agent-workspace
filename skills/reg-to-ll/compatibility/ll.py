"""Validated, traceable LL-driver generation from the unified workbook model."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from compatibility.header import HeaderResult, validate_header
from compatibility.svd_validation import ValidationDiagnostic
from workbook_model import WorkbookModel


@dataclass(frozen=True)
class LlOutputs:
    driver_path: str
    peripheral_count: int = 0
    register_count: int = 0
    field_count: int = 0
    api_count: int = 0


@dataclass(frozen=True)
class LlEvidence:
    model_source: str
    svd_path: str
    svd_sha256: str
    header_path: str
    header_sha256: str
    header_gate_valid: bool
    header_gate_hash_matched: bool
    model_checked: bool
    svd_checked: bool
    header_checked: bool
    output_path: str
    output_sha256: str
    evidence_path: str
    started_at: str
    completed_at: str
    validation_executed: bool
    validation_passed: bool
    atomic_publication: bool
    decision: str


@dataclass(frozen=True)
class LlResult:
    valid: bool
    can_continue: bool
    errors: tuple[ValidationDiagnostic, ...]
    warnings: tuple[ValidationDiagnostic, ...]
    outputs: LlOutputs
    evidence: LlEvidence

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
class _Api:
    name: str
    peripheral: str
    register: str
    field: str
    operation: str
    source: str
    mask: str
    position: str
    member: str
    access: str
    readable: bool
    write_mode: str = ""
    write_behavior: str = ""
    neutral_masks: tuple[str, ...] = ()


_SPECIAL_WRITES = {
    "clear": "Clear",
    "set": "Set",
    "zeroToClear": "Clear",
    "zeroToSet": "Set",
    "oneToClear": "Clear",
    "oneToSet": "Set",
    "oneToToggle": "Toggle",
    "zeroToToggle": "Toggle",
    "modify": "Write",
}
_READABLE = {"read-only", "read-write", "read-writeOnce"}
_WRITABLE = {"write-only", "read-write", "writeOnce", "read-writeOnce"}
_FUNCTION = re.compile(
    r"(?P<doc>/\*\*.*?\*/\s*)?__STATIC_INLINE\s+(?P<return>void|uint32_t)\s+"
    r"(?P<name>LL_[A-Za-z0-9_]+)\s*\((?P<params>[^)]*)\)\s*\{(?P<body>.*?)\}", re.S
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _try_hash(path: Path):
    try:
        return _hash(path)
    except OSError:
        return ""


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


def _model_fields(model: WorkbookModel):
    for peripheral in model.validate_and_expand().peripherals:
        for register in peripheral.registers:
            for field in register.fields:
                if _reserved(field.name):
                    continue
                yield peripheral, register, field


def _reserved(name):
    upper = (name or "").upper()
    return upper.startswith(("RSV", "RESERVED"))


def _neutral_write(field):
    """Return the whole-register neutral value kind proven by CMSIS modifiedWriteValues."""
    behavior = field.access.modified_write_values or ""
    if behavior.startswith("oneTo"):
        return "zero"
    if behavior.startswith("zeroTo"):
        return "one"
    return None


def _expected_apis(model: WorkbookModel, svd_path=None, header_path=None, errors=None):
    expected = []
    svd_fields = _svd_fields(Path(svd_path)) if svd_path is not None else {}
    header_content = Path(header_path).read_text(encoding="utf-8", errors="replace") if header_path is not None else ""
    for peripheral, register, field in _model_fields(model):
        prefix = f"LL_{peripheral.name}_{register.name}"
        suffix = field.name
        svd_definition = svd_fields.get((peripheral.name.casefold(), register.name.casefold(), field.name.casefold()))
        macro_register = svd_definition[2] if svd_definition else register.name
        svd_member = svd_definition[3] if svd_definition else register.name
        candidates = [macro_register, register.name]
        macro_prefix = peripheral.name + "_"
        candidates.extend(item[len(macro_prefix):] for item in tuple(candidates) if item.casefold().startswith(macro_prefix.casefold()))
        macro_register = next((item for item in candidates if f"{peripheral.name}_{item}_{field.name}_Pos" in header_content), macro_register)
        member_base = svd_member.split("[", 1)[0]
        member_candidates = [member_base, register.name]
        member_candidates.extend(item[len(macro_prefix):] for item in tuple(member_candidates) if item.casefold().startswith(macro_prefix.casefold()))
        actual_member = next((item for item in member_candidates if re.search(rf"\b{re.escape(item)}\s*(?:\[|;)", header_content)), member_base)
        member = svd_member.replace(member_base, actual_member, 1)
        mask = f"{peripheral.name}_{macro_register}_{field.name}_Msk"
        position = f"{peripheral.name}_{macro_register}_{field.name}_Pos"
        source = f"{field.source.workbook}:{field.source.sheet}:{field.source.row}"
        access = field.access.cmsis_access
        readable = access in _READABLE
        register_fields = [item for item in register.fields if not _reserved(item.name)]
        read_sensitive = any(item.access.read_action in {"clear", "set"} for item in register_fields)
        neutral_masks = []
        for other in register_fields:
            if other.name == field.name:
                continue
            if (other.access.modified_write_values or "").startswith("zeroTo"):
                other_svd = svd_fields.get((peripheral.name.casefold(), register.name.casefold(), other.name.casefold()))
                other_macro = other_svd[2] if other_svd else register.name
                neutral_masks.append(f"{peripheral.name}_{other_macro}_{other.name}_Msk")
        if access in _READABLE:
            expected.append(_Api(f"{prefix}_Get{suffix}", peripheral.name, register.name, field.name, "Get", source, mask, position, member, access, True))
        if access in _WRITABLE:
            behavior = field.access.modified_write_values or ""
            operation = _SPECIAL_WRITES.get(behavior, "Set")
            direct = not readable or bool(behavior) or read_sensitive
            if direct:
                unsafe = [
                    item.name for item in register_fields
                    if item.name != field.name and item.access.cmsis_access in _WRITABLE
                    and _neutral_write(item) is None
                ]
                if unsafe and errors is not None:
                    _diag(errors, "LL_DIRECT_WRITE_UNSAFE", f"字段 {field.name} 的整寄存器直写无法为邻接可写字段 {', '.join(unsafe)} 证明中性值；拒绝生成。", f"{peripheral.name}/{register.name}/{field.name}")
            expected.append(_Api(
                f"{prefix}_{operation}{suffix}", peripheral.name, register.name, field.name, operation, source,
                mask, position, member, access, readable, "direct" if direct else "modify", behavior, tuple(neutral_masks),
            ))
    return tuple(expected)


def _svd_fields(path: Path):
    result = {}
    root = ElementTree.parse(path).getroot()
    peripherals = _child(root, "peripherals")
    for periph in _children(peripherals, "peripheral") if peripherals is not None else ():
        peripheral_name = _text(periph, "name")
        registers = _child(periph, "registers")
        for register in _children(registers, "register") if registers is not None else ():
            register_name = _text(register, "name")
            count_text = _text(register, "dim")
            count = int(count_text, 0) if count_text else 1
            index_text = _text(register, "dimIndex")
            if count_text and index_text and "-" in index_text:
                first, last = index_text.split("-", 1)
                try:
                    indices = [str(value) for value in range(int(first), int(last) + 1)]
                except ValueError:
                    indices = [chr(value) for value in range(ord(first), ord(last) + 1)]
            elif count_text and index_text:
                indices = [item.strip() for item in index_text.split(",")]
            else:
                indices = [str(index) for index in range(count)]
            expanded_names = [register_name.replace("%s", indices[index]) for index in range(count)]
            macro_register = register_name.replace("%s", "")
            fields = _child(register, "fields")
            for field in _children(fields, "field") if fields is not None else ():
                if _reserved(_text(field, "name")):
                    continue
                for ordinal, expanded_name in enumerate(expanded_names):
                    result[(peripheral_name.casefold(), expanded_name.casefold(), _text(field, "name").casefold())] = (
                        _text(field, "access") or _text(register, "access"), _text(field, "modifiedWriteValues") or None,
                        macro_register, f"{macro_register}[{ordinal}]" if count_text else register_name,
                    )
    return result


def _cross_check_sources(model, svd_path, header_path, gate, errors):
    svd, header = Path(svd_path).resolve(), Path(header_path).resolve()
    if not gate.valid or not gate.can_continue:
        _diag(errors, "LL_HEADER_GATE_FAILED", "ae350.h 未通过 #8 验证门禁，禁止生成或发布 LL Driver。")
        return False, False, False
    if not gate.evidence.svd_gate_passed:
        _diag(errors, "LL_SVD_GATE_FAILED", "头文件证据未证明 #7 SVD 验证门禁通过，禁止生成或发布 LL Driver。", str(svd))
        return False, False, False
    if not gate.evidence.header_validation_executed or not gate.evidence.header_validation_passed or not gate.evidence.atomic_publication:
        _diag(errors, "LL_HEADER_PUBLICATION_UNPROVEN", "头文件证据未证明经过结构验证和原子发布，禁止生成 LL Driver。", str(header))
        return False, False, False
    if gate.evidence.input_sha256 != _hash(svd):
        _diag(errors, "LL_SVD_GATE_STALE", "SVD 内容与头文件门禁所验证的输入哈希不一致；请重新执行 #7/#8。", str(svd))
        return False, False, False
    expected_hash = gate.evidence.validated_header_sha256 or gate.evidence.output_sha256
    if not expected_hash or _hash(header) != expected_hash:
        _diag(errors, "LL_HEADER_GATE_STALE", "ae350.h 内容与验证证据哈希不一致；请重新执行头文件验证。", str(header))
        return False, False, False
    live = validate_header(header, svd, model)
    if not live.valid:
        _diag(errors, "LL_HEADER_REVALIDATION_FAILED", "ae350.h 实时三方复核失败；禁止生成 LL Driver。", str(header))
        errors.extend(live.errors)
        return True, False, False
    try:
        svd_fields = _svd_fields(svd)
    except (OSError, ElementTree.ParseError) as exc:
        _diag(errors, "LL_SVD_READ_FAILED", f"无法读取 SVD：{exc}。", str(svd))
        return True, False, True
    model_keys = set()
    for peripheral, register, field in _model_fields(model):
        key = (peripheral.name.casefold(), register.name.casefold(), field.name.casefold())
        model_keys.add(key)
        actual = svd_fields.get(key)
        expected = (field.access.cmsis_access, field.access.modified_write_values)
        if actual is None:
            _diag(errors, "LL_SVD_FIELD_MISSING", "SVD 缺少 WorkbookModel 字段，无法建立 API 追溯。", "/".join(key))
        elif actual[:2] != expected:
            _diag(errors, "LL_SVD_ACCESS_MISMATCH", f"SVD 权限/特殊写语义 {actual[:2]} 与 WorkbookModel {expected} 不一致。", "/".join(key))
    for key in set(svd_fields) - model_keys:
        _diag(errors, "LL_SVD_FIELD_EXTRA", "SVD 存在 WorkbookModel 未定义字段，无法建立 API 追溯。", "/".join(key))
    return True, True, True


def _body(api: _Api):
    register = f"{api.peripheral}x->{api.member}"
    shifted = f"((value << {api.position}) & {api.mask})"
    if api.operation == "Get":
        return f"    return ((READ_REG({register}) & {api.mask}) >> {api.position});"
    if api.write_mode == "direct":
        written = f"((~{shifted}) & {api.mask})" if api.write_behavior.startswith("zeroTo") else shifted
        if api.neutral_masks:
            written = f"({written} | {' | '.join(api.neutral_masks)})"
        return f"    WRITE_REG({register}, {written});"
    return f"    MODIFY_REG({register}, {api.mask}, {shifted});"


def _render(model, apis):
    peripherals = tuple(model.validate_and_expand().peripherals)
    guard = "__LL_GENERATED_H" if len(peripherals) != 1 else f"__LL_{peripherals[0].name.upper()}_H"
    lines = [
        f"#ifndef {guard}\n#define {guard}\n\n", '#include "ae350.h"\n\n',
        '#ifdef __cplusplus\nextern "C" {\n#endif\n\n',
    ]
    for api in apis:
        readable = api.operation == "Get"
        lines.extend([
            "/**\n", f" * @brief {api.operation} {api.peripheral}.{api.register}.{api.field}.\n",
            f" * @param {api.peripheral}x {api.peripheral} peripheral instance.\n",
            *( [] if readable else [" * @param value Field value.\n"] ),
            f" * @source {api.source}\n", f" * @trace SVD:{api.peripheral}/{api.register}/{api.field}\n",
            f" * @trace ae350.h:{api.mask},{api.position}\n",
            " * @retval Field value.\n" if readable else " * @retval None.\n", " */\n",
            f"__STATIC_INLINE {'uint32_t' if readable else 'void'} {api.name}({api.peripheral}_Type *{api.peripheral}x"
            f"{'' if readable else ', uint32_t value'})\n{{\n{_body(api)}\n}}\n\n",
        ])
    lines.extend(['#ifdef __cplusplus\n}\n#endif\n\n', f"#endif /* {guard} */\n"])
    return "".join(lines)


def validate_ll(driver_path, model, svd_path, header_path, header_gate):
    started = _now()
    path = Path(driver_path).resolve()
    svd, header = Path(svd_path).resolve(), Path(header_path).resolve()
    errors, warnings = [], []
    model_checked, svd_checked, header_checked = _cross_check_sources(model, svd, header, header_gate, errors)
    content = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    if not content:
        _diag(errors, "LL_FILE_MISSING", f"LL Driver 不存在或为空：{path}。")
    peripherals = tuple(model.validate_and_expand().peripherals)
    guard = "__LL_GENERATED_H" if len(peripherals) != 1 else f"__LL_{peripherals[0].name.upper()}_H"
    structure_tokens = (f"#ifndef {guard}", f"#define {guard}", f"#endif /* {guard} */", '#include "ae350.h"', 'extern "C"')
    if content and (any(token not in content for token in structure_tokens) or content.count('extern "C"') != 1):
        _diag(errors, "LL_STRUCTURE_INVALID", "LL Driver 缺少 include、头文件保护或 C++ 兼容结构。", str(path))
    expected = {api.name: api for api in _expected_apis(model, svd, header, errors)}
    matches = list(_FUNCTION.finditer(content))
    actual = {match.group("name"): match for match in matches}
    for name in sorted({match.group("name") for match in matches if sum(item.group("name") == match.group("name") for item in matches) > 1}):
        _diag(errors, "LL_API_DUPLICATE", f"LL Driver 重复定义 API {name}。", name)
    raw_names = set(re.findall(r"\b(LL_[A-Za-z0-9_]+)\s*\(", content))
    for name in sorted(expected.keys() - actual.keys()):
        _diag(errors, "LL_API_MISSING", f"LL Driver 缺少期望 API {name}。", name)
    for name in sorted(raw_names - expected.keys()):
        operation = next((part for part in ("Get", "Set", "Clear", "Toggle", "Write") if f"_{part}" in name), "")
        code = "LL_API_ACCESS_MISMATCH" if operation else "LL_API_EXTRA"
        _diag(errors, code, f"LL Driver 存在未获统一访问语义授权的 API {name}。", name)
    for name in sorted(expected.keys() & actual.keys()):
        api, match = expected[name], actual[name]
        doc, body, params = match.group("doc") or "", match.group("body"), match.group("params")
        required_trace = (f"@source {api.source}", f"SVD:{api.peripheral}/{api.register}/{api.field}", api.mask, api.position)
        if "@brief" not in doc or "@retval" not in doc or any(item not in doc for item in required_trace):
            _diag(errors, "LL_DOXYGEN_TRACE_INVALID", f"API {name} 的 Doxygen 或三方追溯信息不完整。", name)
        expected_return = "uint32_t" if api.operation == "Get" else "void"
        compact_params = re.sub(r"\s+", "", params)
        expected_first = f"{api.peripheral}_Type*{api.peripheral}x"
        needs_value = api.operation != "Get"
        expected_signature = expected_first + (",uint32_tvalue" if needs_value else "")
        if match.group("return") != expected_return or compact_params != expected_signature:
            _diag(errors, "LL_API_SIGNATURE_INVALID", f"API {name} 的返回值或参数不符合 LL 约定。", name)
        documented_params = re.findall(r"@param\s+([A-Za-z_]\w*)\b", doc)
        expected_params = [f"{api.peripheral}x"] + (["value"] if needs_value else [])
        if documented_params != expected_params:
            _diag(errors, "LL_DOXYGEN_PARAM_MISMATCH", f"API {name} 的 @param 应严格为 {expected_params}，实际为 {documented_params}。", name)
        macro = "READ_REG" if api.operation == "Get" else ("WRITE_REG" if api.write_mode == "direct" else "MODIFY_REG")
        if macro not in body or api.mask not in body or api.position not in body or f"{api.peripheral}x->{api.member}" not in body:
            _diag(errors, "LL_CMSIS_MACRO_INVALID", f"API {name} 未按统一语义使用 {macro} 和 Pos/Mask。", name)
        if api.write_mode == "direct" and ("MODIFY_REG" in body or "READ_REG" in body):
            _diag(errors, "LL_FORBIDDEN_RMW", f"API {name} 的访问/副作用语义禁止读取或读改写。", name)
        if re.sub(r"\s+", "", body) != re.sub(r"\s+", "", _body(api)):
            _diag(errors, "LL_BODY_MISMATCH", f"API {name} 的函数体与统一访问语义要求的完整表达式不一致。", name)
    registers = sum(len(item.registers) for item in peripherals)
    fields = sum(len(item.fields) for p in peripherals for item in p.registers)
    outputs = LlOutputs(str(path), len(peripherals), registers, fields, len(actual))
    valid = bool(content) and not errors
    evidence = LlEvidence(
        str(model.source.workbook), str(svd), _hash(svd), str(header), _hash(header), header_gate.valid,
        bool(header_gate.valid and _hash(header) in {header_gate.evidence.validated_header_sha256, header_gate.evidence.output_sha256}),
        model_checked, svd_checked, header_checked, str(path), _hash(path), "", started, _now(), True, valid, False,
        "通过：LL Driver 的结构、API、访问语义与三方追溯一致。" if valid else "阻断：LL Driver 验证失败。",
    )
    return LlResult(valid, valid, tuple(errors), tuple(warnings), outputs, evidence)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_ll_evidence(path, payload):
    """Atomically persist a machine-readable LL result payload."""
    _write_json(Path(path).resolve(), payload)


def generate_ll(model, svd_path, header_path, header_gate, output_path, *, evidence_path=None):
    started = _now()
    output = Path(output_path).resolve()
    evidence_file = Path(evidence_path or output.with_suffix(".result.json")).resolve()
    svd, header = Path(svd_path).resolve(), Path(header_path).resolve()
    errors, warnings = [], []
    protected = {svd, header}
    if output in protected or evidence_file in protected or evidence_file == output:
        _diag(errors, "LL_PATH_COLLISION", "LL 输出、evidence、SVD 与 ae350.h 必须使用互不相同的路径；未写入任何文件。")
        peripherals = tuple(model.validate_and_expand().peripherals)
        outputs = LlOutputs(str(output), len(peripherals), sum(len(p.registers) for p in peripherals), sum(len(r.fields) for p in peripherals for r in p.registers), 0)
        evidence = LlEvidence(
            str(model.source.workbook), str(svd), _hash(svd), str(header), _hash(header), header_gate.valid, False,
            False, False, False, str(output), _hash(output), str(evidence_file), started, _now(), False, False, False,
            "阻断：输出路径冲突，未执行生成或发布。",
        )
        return LlResult(False, False, tuple(errors), (), outputs, evidence)
    model_checked, svd_checked, header_checked = _cross_check_sources(model, svd, header, header_gate, errors)
    apis = _expected_apis(model, svd, header, errors) if not errors else ()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = None
    checked = None
    if not errors:
        fd, temporary = tempfile.mkstemp(prefix=".ll-validated-", suffix=".h", dir=output.parent)
        staging = Path(temporary)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(_render(model, apis))
            stream.flush()
            os.fsync(stream.fileno())
        checked = validate_ll(staging, model, svd, header, header_gate)
        errors.extend(checked.errors)
        warnings.extend(checked.warnings)
    valid = not errors and checked is not None and checked.valid
    peripherals = tuple(model.validate_and_expand().peripherals)
    outputs = LlOutputs(str(output), len(peripherals), sum(len(p.registers) for p in peripherals), sum(len(r.fields) for p in peripherals for r in p.registers), len(apis) if valid else 0)
    evidence = LlEvidence(
        str(model.source.workbook), str(svd), _hash(svd), str(header), _hash(header), header_gate.valid,
        bool(header_gate.valid and _hash(header) in {header_gate.evidence.validated_header_sha256, header_gate.evidence.output_sha256}),
        model_checked, svd_checked, header_checked, str(output), "", str(evidence_file),
        started, _now(), checked is not None, valid, False,
        "待发布：LL Driver staging 已验证。" if valid else "阻断：门禁或 LL Driver 验证失败，未发布，旧文件保持不变。",
    )
    result = LlResult(valid, valid, tuple(errors), tuple(warnings), outputs, evidence)
    if not valid:
        try:
            _write_json(evidence_file, result.to_json_dict())
        finally:
            if staging is not None:
                staging.unlink(missing_ok=True)
        return result

    backup = None
    published = False
    validated_hash = _hash(staging)
    try:
        if output.is_file():
            fd, temporary = tempfile.mkstemp(prefix=".ll-backup-", suffix=".h", dir=output.parent)
            backup = Path(temporary)
            with os.fdopen(fd, "wb") as stream:
                stream.write(output.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(staging, output)
        staging = None
        published = True
        try:
            published_hash = _hash(output)
        except OSError as exc:
            _diag(errors, "LL_PUBLISH_HASH_MISMATCH", f"发布后无法读取 LL Driver：{exc}；正在回滚。", str(output))
            raise OSError("published LL Driver could not be hashed") from exc
        if published_hash != validated_hash:
            _diag(errors, "LL_PUBLISH_HASH_MISMATCH", "发布后的 LL Driver 哈希与已验证 staging 不一致；正在回滚。", str(output))
            raise OSError("published LL Driver hash mismatch")
        evidence = LlEvidence(
            str(model.source.workbook), str(svd), _hash(svd), str(header), _hash(header), header_gate.valid,
            True, model_checked, svd_checked, header_checked, str(output), published_hash, str(evidence_file),
            started, _now(), True, True, True, "通过：LL Driver 通过三方验证，产物与证据已原子发布。",
        )
        result = LlResult(True, True, (), tuple(warnings), outputs, evidence)
        _write_json(evidence_file, result.to_json_dict())
        if backup is not None:
            try:
                backup.unlink()
            except OSError:
                pass
            backup = None
    except OSError as exc:
        errors.append(ValidationDiagnostic("LL_PUBLICATION_FAILED", f"证据或 LL Driver 原子发布失败：{exc}。", str(output)))
        if published:
            try:
                if backup is not None:
                    os.replace(backup, output)
                    backup = None
                else:
                    output.unlink(missing_ok=True)
            except OSError as rollback_error:
                errors.append(ValidationDiagnostic("LL_ROLLBACK_FAILED", f"发布失败后无法恢复旧 LL Driver：{rollback_error}。", str(backup or output)))
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
        if backup is not None and not published:
            backup.unlink(missing_ok=True)
    if errors:
        evidence = LlEvidence(
            str(model.source.workbook), str(svd), _hash(svd), str(header), _hash(header), header_gate.valid,
            bool(header_gate.valid and _hash(header) in {header_gate.evidence.validated_header_sha256, header_gate.evidence.output_sha256}),
            model_checked, svd_checked, header_checked, str(output), _try_hash(output), str(evidence_file),
            started, _now(), True, False, False, "阻断：发布事务失败；已尝试恢复旧 LL Driver。",
        )
        result = LlResult(False, False, tuple(errors), tuple(warnings), outputs, evidence)
        try:
            _write_json(evidence_file, result.to_json_dict())
        except OSError:
            pass
    return result


__all__ = ["LlEvidence", "LlOutputs", "LlResult", "generate_ll", "validate_ll", "write_ll_evidence"]
