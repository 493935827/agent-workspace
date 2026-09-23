"""Stable, machine-readable Excel/Feishu -> SVD -> header -> LL workflow."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from compatibility.header import SvdConvConfig, generate_header
from compatibility.ll import generate_ll
from compatibility.oracle import OracleStatus, run_oracle
from compatibility.svd import compare_svd_outputs, serialize_legacy_svd
from compatibility.svd_validation import validate_svd
from input_convergence import load_feishu_workbook_model, load_local_workbook_model


STAGE_NAMES = (
    "input-convergence",
    "svd-generation",
    "svd-parity",
    "svd-validation",
    "header-generation",
    "ll-generation",
)


@dataclass(frozen=True)
class StageDiagnostic:
    code: str
    message: str
    location: str = ""


@dataclass(frozen=True)
class StageOutcome:
    ok: bool
    errors: tuple[StageDiagnostic, ...] = ()
    warnings: tuple[StageDiagnostic, ...] = ()
    outputs: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, *, outputs=None, warnings=(), evidence=None):
        return cls(True, (), tuple(warnings), outputs or {}, evidence or {})

    @classmethod
    def failure(cls, *errors, warnings=(), outputs=None, evidence=None):
        return cls(False, tuple(errors), tuple(warnings), outputs or {}, evidence or {})


class EvidenceCollisionError(ValueError):
    """The workflow evidence target would overwrite an input or stage artifact."""


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    errors: tuple[StageDiagnostic, ...] = ()
    warnings: tuple[StageDiagnostic, ...] = ()
    outputs: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    generated_this_run: bool = False
    available: bool = False
    validated: bool = False
    cache_hit: bool = False

    def to_json_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
            "outputs": dict(self.outputs),
            "evidence": dict(self.evidence),
            "generated_this_run": self.generated_this_run,
            "available": self.available,
            "validated": self.validated,
            "cache_hit": self.cache_hit,
        }


@dataclass(frozen=True)
class WorkflowRequest:
    workbook_path: Path
    output_directory: Path
    oracle_manifest: Path
    svdconv_path: Path
    source: str = "local"
    feishu_snapshot: Path | None = None
    peripheral: str | None = None
    timeout_seconds: float = 30.0
    evidence_path: Path | None = None
    force: bool = False
    full_rebuild: bool = False
    state_path: Path | None = None

    def __post_init__(self):
        if self.source not in {"local", "feishu"}:
            raise ValueError("source 必须是 local 或 feishu")
        if self.source == "feishu" and self.feishu_snapshot is None:
            raise ValueError("Feishu 输入必须提供 feishu_snapshot")
        if self.evidence_path is not None:
            _validate_evidence_path(self)
        if self.state_path is not None:
            _validate_state_path(self)


@dataclass(frozen=True)
class WorkflowResult:
    valid: bool
    can_continue: bool
    errors: tuple[StageDiagnostic, ...]
    warnings: tuple[StageDiagnostic, ...]
    outputs: Mapping[str, Any]
    evidence: Mapping[str, Any]
    stages: tuple[StageResult, ...]

    def to_json_dict(self):
        return {
            "valid": self.valid,
            "can_continue": self.can_continue,
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
            "outputs": dict(self.outputs),
            "evidence": dict(self.evidence),
            "stages": [item.to_json_dict() for item in self.stages],
        }


StageAction = Callable[[WorkflowRequest, dict[str, Any]], StageOutcome]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _diagnostics(items):
    return tuple(StageDiagnostic(item.code, item.message, getattr(item, "location", "")) for item in items)


def _atomic_write(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _published_path(path: str, staging: Path, output_directory: Path) -> str:
    candidate = Path(path)
    try:
        relative = candidate.resolve().relative_to(staging.resolve())
    except (OSError, ValueError):
        return path
    return str((output_directory.resolve() / relative).resolve())


def _published_value(value: Any, staging: Path, output_directory: Path) -> Any:
    if isinstance(value, Mapping):
        return {key: _published_value(item, staging, output_directory) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_published_value(item, staging, output_directory) for item in value)
    if isinstance(value, list):
        return [_published_value(item, staging, output_directory) for item in value]
    if isinstance(value, str):
        return _published_path(value, staging, output_directory)
    return value


def _publish_staged_tree(staging: Path, output_directory: Path, stale_paths=(), state_update=None):
    """Publish complete candidate files and roll back caught interruptions/errors."""
    files = sorted((path for path in staging.rglob("*") if path.is_file()), key=lambda path: str(path))
    destinations = {
        output_directory.resolve() / candidate.relative_to(staging): candidate
        for candidate in files
    }
    stale = tuple(sorted(
        (Path(path).resolve() for path in stale_paths if Path(path).resolve() not in destinations),
        key=str,
    ))
    state_destination = Path(state_update[0]).resolve() if state_update else None
    backups = {
        destination: destination.read_bytes() if destination.is_file() else None
        for destination in (*destinations, *stale, *((state_destination,) if state_destination else ()))
    }
    try:
        for destination in stale:
            destination.unlink(missing_ok=True)
        for destination, candidate in destinations.items():
            _atomic_write(destination, candidate.read_bytes())
        if state_update:
            _atomic_write(state_destination, state_update[1])
    except BaseException:
        for destination, previous in reversed(tuple(backups.items())):
            if previous is None:
                destination.unlink(missing_ok=True)
            else:
                _atomic_write(destination, previous)
        raise


def _normalize_staged_evidence(staging: Path, output_directory: Path):
    for name in ("header-result.json", "ll-result.json"):
        path = staging / name
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload = _published_value(payload, staging, output_directory)
        _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))


def _managed_artifact_paths(entries: Mapping[str, Any], output_directory: Path) -> set[Path]:
    root = output_directory.resolve()
    managed = set()
    for entry in entries.values():
        if not _valid_cache_entry(entry):
            continue
        for raw_path in entry["artifact_hashes"]:
            path = Path(raw_path).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                continue
            if path != root:
                managed.add(path)
    return managed


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
    except OSError:
        return ""


def _state_path(request: WorkflowRequest) -> Path:
    return (request.state_path or (request.output_directory / ".workflow-state.json")).resolve()


def _validate_state_path(request: WorkflowRequest):
    state = _state_path(request)
    protected = {request.workbook_path.resolve(), request.oracle_manifest.resolve(), request.svdconv_path.resolve()}
    if request.feishu_snapshot is not None:
        protected.add(request.feishu_snapshot.resolve())
    if request.evidence_path is not None:
        protected.add(request.evidence_path.resolve())
    output_directory = request.output_directory.resolve()
    reserved = {output_directory / "header-result.json", output_directory / "ll-result.json", output_directory / "ae350.h"}
    generated_pattern = state.parent == output_directory and (
        state.suffix.casefold() == ".svd"
        or (state.name.casefold().startswith("ll_") and state.suffix.casefold() == ".h")
    )
    if state in protected or state == output_directory or state in reserved or generated_pattern:
        raise EvidenceCollisionError(f"workflow state 路径与输入、证据或输出目录冲突：{state}")


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _manifest_bundle(request: WorkflowRequest) -> Mapping[str, str]:
    """Bind an oracle manifest to local lock/archive files that define its tool environment."""
    manifest = request.oracle_manifest.resolve()
    hashes = {str(manifest): _sha256(manifest)}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return hashes

    def visit(item):
        if isinstance(item, Mapping):
            for value in item.values():
                visit(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                visit(value)
        elif isinstance(item, str):
            candidate = (manifest.parent / item).resolve()
            if candidate.is_file():
                hashes[str(candidate)] = _sha256(candidate)
    visit(payload)
    return dict(sorted(hashes.items()))


def _action_version(action: StageAction) -> str:
    try:
        source = inspect.getsource(action)
    except (OSError, TypeError):
        source = f"{getattr(action, '__module__', '')}:{getattr(action, '__qualname__', type(action).__qualname__)}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _implementation_versions(name: str) -> Mapping[str, str]:
    files = {
        "input-convergence": ("input_convergence.py", "workbook_model.py"),
        "svd-generation": ("compatibility/svd.py", "workbook_model.py"),
        "svd-parity": ("compatibility/oracle.py", "compatibility/svd.py"),
        "svd-validation": ("compatibility/svd_validation.py",),
        "header-generation": ("compatibility/header.py",),
        "ll-generation": ("compatibility/ll.py",),
    }[name]
    root = Path(__file__).resolve().parent
    return {relative: _sha256(root / relative) for relative in files}


def _stage_inputs(name: str, request: WorkflowRequest) -> Mapping[str, Any]:
    common = {"source": request.source}
    if name == "input-convergence":
        return {**common, "workbook_name": request.workbook_path.name,
                "workbook_sha256": _sha256(request.workbook_path),
                "feishu_snapshot_sha256": _sha256(request.feishu_snapshot) if request.feishu_snapshot else ""}
    if name == "svd-generation":
        return {"peripheral": request.peripheral or "", "output_directory": str(request.output_directory.resolve())}
    if name == "svd-parity":
        return {"oracle_environment_versions": _manifest_bundle(request), "timeout_seconds": request.timeout_seconds}
    if name == "header-generation":
        return {"svdconv_path": str(request.svdconv_path.resolve()),
                "svdconv_sha256": _sha256(request.svdconv_path),
                "svdconv_version": f"sha256:{_sha256(request.svdconv_path)}",
                "timeout_seconds": request.timeout_seconds}
    return {}


def _artifact_hashes(value: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    def visit(item):
        if isinstance(item, Mapping):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)
        elif isinstance(item, str):
            path = Path(item)
            if path.is_file():
                result[str(path.resolve())] = _sha256(path)
    visit(value)
    return dict(sorted(result.items()))


def _artifacts_match(hashes: Mapping[str, str]) -> bool:
    return all(_sha256(Path(path)) == expected and bool(expected) for path, expected in hashes.items())


def _valid_cache_entry(entry: Any) -> bool:
    if not isinstance(entry, Mapping) or not isinstance(entry.get("key"), str):
        return False
    hashes = entry.get("artifact_hashes")
    result = entry.get("result")
    if not isinstance(hashes, Mapping) or not all(isinstance(path, str) and isinstance(value, str)
                                                  for path, value in hashes.items()):
        return False
    if not isinstance(result, Mapping) or result.get("status") != "success":
        return False
    if not isinstance(result.get("outputs"), Mapping) or not isinstance(result.get("evidence"), Mapping):
        return False
    for key in ("errors", "warnings"):
        diagnostics = result.get(key)
        if not isinstance(diagnostics, list):
            return False
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, Mapping):
                return False
            if not all(isinstance(diagnostic.get(field), str) for field in ("code", "message", "location")):
                return False
    return all(isinstance(result.get(key), bool)
               for key in ("generated_this_run", "available", "validated", "cache_hit"))


def _load_state(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if value.get("schema_version") == 1 and isinstance(value.get("stages"), dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _cached_result(name: str, entry: Mapping[str, Any]) -> StageResult:
    data = entry["result"]
    errors = tuple(StageDiagnostic(**item) for item in data.get("errors", ()))
    warnings = tuple(StageDiagnostic(**item) for item in data.get("warnings", ()))
    evidence = dict(data.get("evidence", {}))
    return StageResult(name, "success", errors, warnings, data.get("outputs", {}), evidence,
                       generated_this_run=False, available=True, validated=True, cache_hit=True)


def _validate_evidence_path(request: WorkflowRequest, generated_paths=()):
    evidence = request.evidence_path.resolve()
    inputs = {
        request.workbook_path.resolve(): "workbook",
        request.oracle_manifest.resolve(): "oracle manifest",
        request.svdconv_path.resolve(): "SVDConv tool",
    }
    if request.feishu_snapshot is not None:
        inputs[request.feishu_snapshot.resolve()] = "Feishu snapshot"
    if evidence in inputs:
        raise EvidenceCollisionError(f"evidence 路径与 {inputs[evidence]} 冲突：{evidence}")

    output_directory = request.output_directory.resolve()
    fixed_outputs = {
        output_directory / "header-result.json",
        output_directory / "ll-result.json",
        output_directory / "ae350.h",
    }
    candidates = fixed_outputs | {Path(path).resolve() for path in generated_paths}
    generated_pattern = (
        evidence.parent == output_directory
        and (evidence.suffix.casefold() == ".svd"
             or (evidence.name.casefold().startswith("ll_") and evidence.suffix.casefold() == ".h"))
    )
    if evidence == output_directory or evidence in candidates or generated_pattern:
        raise EvidenceCollisionError(f"evidence 路径与工作流保留输出冲突：{evidence}")


def write_workflow_result(path, result: WorkflowResult):
    raw = json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    _atomic_write(Path(path).resolve(), raw)


def _input_action(request, context):
    if request.source == "local":
        model = load_local_workbook_model(request.workbook_path)
    else:
        model = load_feishu_workbook_model(request.feishu_snapshot, request.workbook_path)
    # Input convergence intentionally neutralizes source locations so local and
    # Feishu models compare equal.  Legacy SVD filenames, however, are part of
    # the byte-parity contract and must retain the actual workbook basename.
    model = replace(
        model,
        source=replace(model.source, workbook=str(request.workbook_path.resolve())),
    )
    context["model"] = model
    return StageOutcome.success(
        outputs={"source": request.source, "workbook_path": str(request.workbook_path.resolve())},
        evidence={"model_source": model.source.workbook, "peripheral_count": len(model.peripherals)},
    )


def _svd_generation_action(request, context):
    model = context["model"]
    candidates = serialize_legacy_svd(model)
    if request.peripheral:
        selected = next((item for item in candidates if item.sheet.casefold() == request.peripheral.casefold()), None)
        if selected is None:
            return StageOutcome.failure(StageDiagnostic("WORKFLOW_PERIPHERAL_NOT_FOUND", f"工作簿中没有外设：{request.peripheral}"))
    elif len(candidates) == 1:
        selected = candidates[0]
    else:
        return StageOutcome.failure(StageDiagnostic("WORKFLOW_PERIPHERAL_REQUIRED", "工作簿包含多个外设，请用 --peripheral 选择一个用于头文件和 LL Driver。"))
    if request.evidence_path is not None:
        _validate_evidence_path(
            request,
            (request.output_directory.resolve() / item.filename for item in candidates),
        )
    paths = []
    for candidate in candidates:
        path = request.output_directory.resolve() / candidate.filename
        _atomic_write(path, candidate.raw_bytes)
        paths.append(str(path))
        if candidate is selected:
            context["svd_path"] = path
    peripheral = next(item for item in model.peripherals if item.name.casefold() == selected.sheet.casefold())
    context["selected_model"] = replace(model, peripherals=(peripheral,))
    context["candidates"] = candidates
    context["selected"] = selected
    return StageOutcome.success(
        outputs={"svd_path": str(context["svd_path"]), "svd_paths": paths, "peripheral": selected.sheet},
        evidence={"sha256": selected.sha256, "candidate_count": len(candidates)},
    )


def _svd_parity_action(request, context):
    oracle = run_oracle(
        request.oracle_manifest,
        workbook_path=request.workbook_path,
        timeout_seconds=request.timeout_seconds,
    )
    context["oracle"] = oracle
    if oracle.status is not OracleStatus.PASSED:
        return StageOutcome.failure(
            StageDiagnostic("SVD_ORACLE_FAILED", oracle.reason or f"Oracle 状态为 {oracle.status.value}"),
            evidence={"status": oracle.status.value, "exit_code": oracle.exit_code, "stdout": oracle.stdout, "stderr": oracle.stderr},
        )
    comparison = compare_svd_outputs(context["candidates"], oracle.outputs)
    context["comparison"] = comparison
    if not comparison.matches:
        errors = tuple(StageDiagnostic("SVD_PARITY_MISMATCH", item.reason, item.filename) for item in comparison.mismatches)
        return StageOutcome.failure(*errors, evidence={"matches": False, "mismatch_count": len(errors)})
    return StageOutcome.success(
        evidence={"matches": True, "oracle_python": oracle.python_version, "oracle_exit_code": oracle.exit_code,
                  "candidate_sha256": context["selected"].sha256},
    )


def _svd_validation_action(request, context):
    result = validate_svd(context["svd_path"], context["selected_model"], compatibility=context["comparison"])
    context["svd_validation"] = result
    outcome = StageOutcome.success if result.valid and result.can_continue else StageOutcome.failure
    return outcome(
        *_diagnostics(result.errors),
        warnings=_diagnostics(result.warnings),
        outputs=asdict(result.outputs), evidence=asdict(result.evidence),
    )


def _header_action(request, context):
    output = request.output_directory.resolve() / "ae350.h"
    evidence = request.output_directory.resolve() / "header-result.json"
    result = generate_header(
        context["svd_path"], context["selected_model"], context["svd_validation"], output,
        config=SvdConvConfig(request.svdconv_path, timeout_seconds=request.timeout_seconds), evidence_path=evidence,
    )
    context["header_result"] = result
    context["header_path"] = output
    outcome = StageOutcome.success if result.valid and result.can_continue else StageOutcome.failure
    return outcome(*_diagnostics(result.errors), warnings=_diagnostics(result.warnings),
                   outputs=asdict(result.outputs), evidence=asdict(result.evidence))


def _ll_action(request, context):
    peripheral = context["selected"].sheet.lower()
    output = request.output_directory.resolve() / f"ll_{peripheral}.h"
    evidence = request.output_directory.resolve() / "ll-result.json"
    result = generate_ll(context["selected_model"], context["svd_path"], context["header_path"],
                         context["header_result"], output, evidence_path=evidence)
    outcome = StageOutcome.success if result.valid and result.can_continue else StageOutcome.failure
    return outcome(*_diagnostics(result.errors), warnings=_diagnostics(result.warnings),
                   outputs=asdict(result.outputs), evidence=asdict(result.evidence))


DEFAULT_ACTIONS: Mapping[str, StageAction] = {
    "input-convergence": _input_action,
    "svd-generation": _svd_generation_action,
    "svd-parity": _svd_parity_action,
    "svd-validation": _svd_validation_action,
    "header-generation": _header_action,
    "ll-generation": _ll_action,
}


def _restore_default_context(name: str, request: WorkflowRequest, context: dict[str, Any], stage: StageResult):
    """Rehydrate only ephemeral objects; cached artifacts are never rewritten."""
    if name == "input-convergence":
        _input_action(request, context)
    elif name == "svd-generation":
        candidates = serialize_legacy_svd(context["model"])
        peripheral = stage.outputs.get("peripheral", "")
        selected = next(item for item in candidates if item.sheet.casefold() == str(peripheral).casefold())
        context["candidates"] = candidates
        context["selected"] = selected
        context["svd_path"] = Path(stage.outputs["svd_path"])
        model_peripheral = next(item for item in context["model"].peripherals if item.name.casefold() == selected.sheet.casefold())
        context["selected_model"] = replace(context["model"], peripherals=(model_peripheral,))
    elif name == "svd-parity":
        context["comparison"] = SimpleNamespace(matches=True, mismatches=())
    elif name == "svd-validation":
        context["svd_validation"] = validate_svd(
            context["svd_path"], context["selected_model"], compatibility=context["comparison"]
        )
    elif name == "header-generation":
        header_path = Path(stage.outputs.get("header_path", request.output_directory / "ae350.h"))
        digest = _sha256(header_path)
        context["header_path"] = header_path
        context["header_result"] = SimpleNamespace(
            valid=True, can_continue=True,
            evidence=SimpleNamespace(validated_header_sha256=digest, output_sha256=digest),
        )


class WorkflowRunner:
    """Run mandatory stages in order and return one stable result contract."""

    def __init__(self, stage_actions: Mapping[str, StageAction] | None = None):
        self._actions = dict(DEFAULT_ACTIONS if stage_actions is None else stage_actions)
        missing = [name for name in STAGE_NAMES if name not in self._actions]
        if missing:
            raise ValueError(f"缺少工作流阶段：{', '.join(missing)}")

    def run(self, request: WorkflowRequest) -> WorkflowResult:
        output_parent = request.output_directory.resolve().parent
        output_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".workflow-run-", dir=output_parent) as staging_text:
            staging = Path(staging_text).resolve()
            execution_request = replace(request, output_directory=staging)
            return self._run_staged(request, execution_request, staging)

    def _run_staged(
        self,
        request: WorkflowRequest,
        execution_request: WorkflowRequest,
        staging: Path,
    ) -> WorkflowResult:
        started = _now()
        context: dict[str, Any] = {}
        stages = []
        failed_name = None
        state_path = _state_path(request)
        _validate_state_path(request)
        durable_state = _load_state(state_path)
        durable_entries = durable_state.get("stages", {})
        previous_state = {} if request.force or request.full_rebuild else durable_state
        previous_entries = previous_state.get("stages", {})
        next_entries: dict[str, Any] = {}
        upstream_key = "workflow-v1"
        downstream_invalidated = bool(request.force or request.full_rebuild)
        for name in STAGE_NAMES:
            if failed_name:
                stages.append(StageResult(name, "not-run", evidence={"reason": f"blocked-by:{failed_name}"},
                                          generated_this_run=False, available=False, validated=False))
                continue
            base_key = _json_hash({"stage": name, "upstream_key": upstream_key, "inputs": _stage_inputs(name, request),
                                   "action_version": _action_version(self._actions[name]),
                                   "tool_versions": _implementation_versions(name)})
            cached = previous_entries.get(name, {})
            cache_entry_valid = _valid_cache_entry(cached)
            cached_hashes = cached.get("artifact_hashes", {}) if cache_entry_valid else {}
            key = _json_hash({"base_key": base_key, "output_content_hashes": cached_hashes})
            hit = bool(cache_entry_valid and not downstream_invalidated
                       and cached.get("key") == key and _artifacts_match(cached_hashes))
            if hit:
                try:
                    stage = _cached_result(name, cached)
                    if self._actions[name] is DEFAULT_ACTIONS.get(name):
                        _restore_default_context(name, request, context, stage)
                except Exception:
                    hit = False
                    downstream_invalidated = True
                if hit:
                    stages.append(stage)
                    next_entries[name] = cached
                    upstream_key = key
                    continue
            downstream_invalidated = True
            try:
                outcome = self._actions[name](execution_request, context)
                if not isinstance(outcome, StageOutcome):
                    raise TypeError("stage action 必须返回 StageOutcome")
                if outcome.ok and outcome.errors:
                    outcome = StageOutcome.failure(
                        *outcome.errors,
                        warnings=outcome.warnings,
                        outputs=outcome.outputs,
                        evidence=outcome.evidence,
                    )
            except EvidenceCollisionError:
                raise
            except Exception as exc:
                outcome = StageOutcome.failure(StageDiagnostic("WORKFLOW_STAGE_EXCEPTION", f"阶段 {name} 异常：{exc}"))
            status = "success" if outcome.ok else "failed"
            if self._actions[name] is DEFAULT_ACTIONS.get(name):
                _normalize_staged_evidence(staging, request.output_directory)
            staged_artifact_hashes = {
                path: digest
                for path, digest in _artifact_hashes({"outputs": outcome.outputs, "evidence": outcome.evidence}).items()
                if Path(path).resolve().is_relative_to(staging)
            }
            artifact_hashes = {
                _published_path(path, staging, request.output_directory): digest
                for path, digest in staged_artifact_hashes.items()
            }
            if str(state_path) in artifact_hashes:
                raise EvidenceCollisionError(f"workflow state 路径与阶段产物冲突：{state_path}")
            key = _json_hash({"base_key": base_key, "output_content_hashes": artifact_hashes})
            if artifact_hashes:
                available = all(Path(path).is_file() for path in staged_artifact_hashes)
            elif cached_hashes:
                available = all(Path(path).is_file() for path in cached_hashes)
            else:
                available = bool(outcome.ok)
            outputs = _published_value(dict(outcome.outputs), staging, request.output_directory)
            evidence = _published_value(dict(outcome.evidence), staging, request.output_directory)
            stage = StageResult(name, status, outcome.errors, outcome.warnings, outputs, evidence,
                                generated_this_run=bool(outcome.ok), available=available, validated=bool(outcome.ok))
            stages.append(stage)
            if outcome.ok:
                next_entries[name] = {
                    "key": key,
                    "artifact_hashes": artifact_hashes,
                    "result": stage.to_json_dict(),
                }
                upstream_key = key
            if not outcome.ok:
                failed_name = name
        if failed_name is not None:
            truthful_stages = []
            for stage in stages:
                if not stage.generated_this_run and stage.status != "failed":
                    truthful_stages.append(stage)
                    continue
                durable = durable_entries.get(stage.name, {})
                retained = _valid_cache_entry(durable) and _artifacts_match(durable.get("artifact_hashes", {}))
                old = _cached_result(stage.name, durable) if retained else None
                evidence = dict(stage.evidence)
                evidence.update({"candidate_published": False, "retained_previous": bool(retained)})
                truthful_stages.append(replace(
                    stage,
                    outputs=dict(old.outputs) if old else {},
                    evidence=evidence,
                    generated_this_run=False,
                    available=bool(retained),
                    validated=bool(retained),
                    cache_hit=False,
                ))
            stages = truthful_stages
        if failed_name is None:
            previous_managed = _managed_artifact_paths(durable_entries, request.output_directory)
            next_managed = _managed_artifact_paths(next_entries, request.output_directory)
            state_raw = json.dumps({"schema_version": 1, "stages": next_entries}, ensure_ascii=False,
                                   indent=2, sort_keys=True).encode("utf-8")
            _publish_staged_tree(
                staging,
                request.output_directory,
                previous_managed - next_managed,
                state_update=(state_path, state_raw),
            )
        errors = tuple(item for stage in stages for item in stage.errors)
        warnings = tuple(item for stage in stages for item in stage.warnings)
        outputs = {stage.name: dict(stage.outputs) for stage in stages if stage.outputs}
        completed = [stage.name for stage in stages if stage.status == "success"]
        valid = failed_name is None
        stage_evidence = {stage.name: dict(stage.evidence) for stage in stages}
        return WorkflowResult(
            valid, valid, errors, warnings, outputs,
            {"started_at": started, "completed_at": _now(), "source": request.source,
             "stage_order": list(STAGE_NAMES), "completed_stages": completed,
             "failed_stage": failed_name or "", "stage_evidence": stage_evidence,
             "state_path": str(state_path), "full_rebuild": bool(request.force or request.full_rebuild),
             "cache_hits": [stage.name for stage in stages if stage.cache_hit]},
            tuple(stages),
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--source", choices=("local", "feishu"), default="local")
    parser.add_argument("--feishu-snapshot", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--oracle-manifest", required=True, type=Path)
    parser.add_argument("--svdconv", required=True, type=Path)
    parser.add_argument("--peripheral")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--state", type=Path, help="持久增量状态（默认 output-dir/.workflow-state.json）")
    parser.add_argument("--force", "--full-rebuild", dest="full_rebuild", action="store_true",
                        help="忽略缓存并重新执行所有阶段")
    args = parser.parse_args(argv)
    evidence_safe = True
    try:
        request = WorkflowRequest(
            workbook_path=args.workbook,
            output_directory=args.output_dir,
            oracle_manifest=args.oracle_manifest,
            svdconv_path=args.svdconv,
            source=args.source,
            feishu_snapshot=args.feishu_snapshot,
            peripheral=args.peripheral,
            timeout_seconds=args.timeout,
            evidence_path=args.evidence,
            state_path=args.state,
            full_rebuild=args.full_rebuild,
        )
        result = WorkflowRunner().run(request)
    except EvidenceCollisionError as exc:
        evidence_safe = False
        error = StageDiagnostic("WORKFLOW_EVIDENCE_COLLISION", str(exc))
        stages = tuple(StageResult(name, "failed" if index == 0 else "not-run", (error,) if index == 0 else (),
                                   evidence={} if index == 0 else {"reason": f"blocked-by:{STAGE_NAMES[0]}"})
                       for index, name in enumerate(STAGE_NAMES))
        result = WorkflowResult(False, False, (error,), (), {}, {"started_at": _now(), "completed_at": _now(),
                                "source": args.source, "stage_order": list(STAGE_NAMES), "completed_stages": [],
                                "failed_stage": STAGE_NAMES[0],
                                "stage_evidence": {stage.name: dict(stage.evidence) for stage in stages}}, stages)
    except Exception as exc:
        error = StageDiagnostic("WORKFLOW_INPUT_INVALID", f"工作流参数无效：{exc}")
        stages = tuple(StageResult(name, "failed" if index == 0 else "not-run", (error,) if index == 0 else (),
                                   evidence={} if index == 0 else {"reason": f"blocked-by:{STAGE_NAMES[0]}"})
                       for index, name in enumerate(STAGE_NAMES))
        result = WorkflowResult(False, False, (error,), (), {}, {"started_at": _now(), "completed_at": _now(),
                                "source": args.source, "stage_order": list(STAGE_NAMES), "completed_stages": [],
                                "failed_stage": STAGE_NAMES[0],
                                "stage_evidence": {stage.name: dict(stage.evidence) for stage in stages}}, stages)
    if evidence_safe:
        write_workflow_result(args.evidence, result)
    print(json.dumps(result.to_json_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.valid else 1


__all__ = [
    "STAGE_NAMES", "EvidenceCollisionError", "StageDiagnostic", "StageOutcome", "StageResult", "WorkflowRequest",
    "WorkflowResult", "WorkflowRunner", "write_workflow_result",
]


if __name__ == "__main__":
    raise SystemExit(main())
