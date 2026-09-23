"""在固定 OCI 容器中运行未修改的历史 regtool，并收集兼容性证据。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
import zipfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree


class OracleStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class OracleOutput:
    sheet: str
    filename: str
    raw_bytes: bytes
    sha256: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "sheet": self.sheet,
            "filename": self.filename,
            "raw_bytes_base64": base64.b64encode(self.raw_bytes).decode("ascii"),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class OracleResult:
    status: OracleStatus
    reason: str
    python_version: str
    dependency_versions: Mapping[str, str]
    stdout: str
    stderr: str
    exit_code: int | None
    outputs: tuple[OracleOutput, ...]

    def to_json_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["outputs"] = [output.to_json_dict() for output in self.outputs]
        return result


class _UnavailableError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_member(member: str) -> PurePosixPath:
    path = PurePosixPath(member)
    if (
        not member
        or "\\" in member
        or ":" in member
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise _UnavailableError(f"fixture 中包含不安全路径: {member!r}")
    return path


def _extract_verified_archive(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for item in archive.infolist():
            relative = _safe_member(item.filename)
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise _UnavailableError(f"fixture 中不允许符号链接: {item.filename!r}")
            target = destination.joinpath(*relative.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _workbook_sheet_names(workbook: Path) -> list[str]:
    try:
        with zipfile.ZipFile(workbook) as archive:
            xml = archive.read("xl/workbook.xml")
        root = ElementTree.fromstring(xml)
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise _UnavailableError(f"无法读取内置工作簿元数据: {exc}") from exc
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    return [element.attrib["name"] for element in root.findall(f".//{namespace}sheet")]


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise _UnavailableError(f"缺少 {description}: {path.name}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise _UnavailableError(f"无法读取 {description}: {exc}") from exc
    if not isinstance(value, dict):
        raise _UnavailableError(f"{description} 根节点必须是对象")
    return value


def _unavailable(reason: str) -> OracleResult:
    return OracleResult(OracleStatus.UNAVAILABLE, reason, "", {}, "", "", None, ())


def _failed(
    reason: str,
    *,
    python_version: str = "",
    dependencies: Mapping[str, str] | None = None,
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = None,
    outputs: tuple[OracleOutput, ...] = (),
) -> OracleResult:
    return OracleResult(
        OracleStatus.FAILED,
        reason,
        python_version,
        dependencies or {},
        stdout,
        stderr,
        exit_code,
        outputs,
    )


def _process_options() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        taskkill = str(Path(system_root) / "System32" / "taskkill.exe")
        try:
            subprocess.run(
                [taskkill, "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            # 最后仍会 kill 直接子进程；Docker 容器另由 kill/rm -f 双重清理。
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _engine_prefix(executable: str) -> list[str]:
    # Windows CreateProcess 不能直接启动测试用 .cmd；正式 Docker 是 docker.exe。
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", executable]
    return [executable]


def _bounded_command(command: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
        **_process_options(),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        raise _UnavailableError(
            f"Docker 控制命令在 {timeout:g} 秒内未完成: "
            f"{stderr.decode('utf-8', errors='replace')}"
        )
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _verify_image(engine: str, image: str, lock_sha: str) -> None:
    completed = _bounded_command(
        [*_engine_prefix(engine), "image", "inspect", image], timeout=10
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise _UnavailableError(
            f"Docker 固定镜像 {image!r} 不可用；请按 fixture SOURCE.md 构建。{detail}"
        )
    try:
        inspected = json.loads(completed.stdout.decode("utf-8"))
        actual = inspected[0]["Config"]["Labels"]["org.regtool.oracle.lock"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise _UnavailableError("Docker 镜像缺少可核验的环境锁标签") from exc
    if actual != lock_sha:
        raise _UnavailableError("Docker 镜像环境锁与 fixture 不匹配，请重新构建固定镜像")


def _mount(source: Path, destination: str, *, readonly: bool = False) -> str:
    value = f"type=bind,src={source},dst={destination}"
    return value + (",readonly" if readonly else "")


def _run_container(
    engine: str,
    image: str,
    platform: str,
    source_dir: Path,
    output_dir: Path,
    packages: Mapping[str, str],
    legacy_command: Sequence[str],
    timeout: float,
) -> tuple[bool, bool, bytes, bytes]:
    container_name = f"regtool-oracle-{uuid.uuid4().hex}"
    runner = Path(__file__).with_name("oracle_runner.py").resolve()
    command = [
        *_engine_prefix(engine),
        "run",
        "--name",
        container_name,
        "--rm",
        "--platform",
        platform,
        "--network",
        "none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--memory=256m",
        "--cpus=1",
        "--user=65532:65532",
        "--workdir=/output",
        "--mount",
        _mount(source_dir, "/oracle", readonly=True),
        "--mount",
        _mount(output_dir, "/output"),
        "--mount",
        _mount(runner, "/harness/oracle_runner.py", readonly=True),
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--tmpfs",
        "/home/oracle:rw,noexec,nosuid,nodev,size=16m",
        image,
        "python",
        "/harness/oracle_runner.py",
        "--evidence=/output/oracle-result.json",
    ]
    for package in sorted(packages):
        command.append(f"--package={package}")
    command.extend(["--", *legacy_command])
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
        **_process_options(),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return False, True, stdout, stderr
    except subprocess.TimeoutExpired:
        # 先杀容器，从而终止容器内完整 PID namespace；再无条件清理宿主 CLI 进程树。
        container_stopped = False
        try:
            killed = _bounded_command(
                [*_engine_prefix(engine), "kill", container_name], timeout=5
            )
            container_stopped = killed.returncode == 0
        except _UnavailableError:
            pass
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        try:
            removed = _bounded_command(
                [*_engine_prefix(engine), "rm", "-f", container_name], timeout=5
            )
            container_stopped = container_stopped or removed.returncode == 0
        except _UnavailableError:
            pass
        return True, container_stopped, stdout, stderr


def run_oracle(
    manifest_path: str | Path,
    *,
    workbook_path: str | Path | None = None,
    timeout_seconds: float = 30,
) -> OracleResult:
    """在哈希固定的 Oracle 环境中运行 fixture 或指定工作簿。"""
    manifest_path = Path(manifest_path).resolve()
    requested_workbook = Path(workbook_path).resolve() if workbook_path is not None else None
    if not 0 < timeout_seconds <= 60:
        return _unavailable("timeout_seconds 必须大于 0 且不超过 60")
    try:
        manifest = _read_json(manifest_path, "Oracle manifest")
        archive_config = manifest["archive"]
        workbook_config = manifest["workbook"]
        module_range = manifest["modules"]
        environment = manifest["environment"]
        output_mapping = manifest["outputs"]
        legacy_command = manifest["command"]
        if not isinstance(output_mapping, dict) or not output_mapping:
            raise _UnavailableError("manifest outputs 必须覆盖全部模块工作表")
        if not isinstance(legacy_command, list) or not all(
            isinstance(item, str) for item in legacy_command
        ):
            raise _UnavailableError("manifest command 必须是字符串数组")

        archive_path = manifest_path.parent / archive_config["filename"]
        archive_bytes = archive_path.read_bytes()
        if _sha256(archive_bytes) != archive_config["sha256"]:
            raise _UnavailableError("原始 regtool ZIP 哈希不匹配；fixture 已被改动")

        lock_path = manifest_path.parent / environment["lockfile"]
        lock_bytes = lock_path.read_bytes()
        lock_sha = _sha256(lock_bytes)
        if lock_sha != environment["lockfile_sha256"]:
            raise _UnavailableError("环境锁文件哈希不匹配")
        lock = _read_json(lock_path, "环境锁文件")
        platform = lock["platform"]
        packages = lock["packages"]
        if not isinstance(packages, dict) or not all(
            isinstance(name, str) and isinstance(version, str)
            for name, version in packages.items()
        ):
            raise _UnavailableError("环境锁 packages 必须是精确版本映射")
        requirements_path = manifest_path.parent / lock["requirements_file"]
        if _sha256(requirements_path.read_bytes()) != lock["requirements_sha256"]:
            raise _UnavailableError("依赖 requirements 文件哈希与环境锁不匹配")

        engine = shutil.which("docker")
        if engine is None:
            raise _UnavailableError(
                "Docker 不可用：Oracle 只允许在固定 OCI 容器内运行，未回退到宿主 Python"
            )
        image = environment["image"]
        _verify_image(engine, image, lock_sha)

        with tempfile.TemporaryDirectory(prefix="regtool-oracle-") as temporary:
            sandbox = Path(temporary)
            source_dir = sandbox / "source"
            output_dir = sandbox / "output"
            source_dir.mkdir()
            output_dir.mkdir()
            if os.name != "nt":
                output_dir.chmod(0o777)
            _extract_verified_archive(archive_path, source_dir)
            workbook_member = _safe_member(workbook_config["member"])
            workbook = source_dir.joinpath(*workbook_member.parts)
            if not workbook.is_file() or _sha256(workbook.read_bytes()) != workbook_config["sha256"]:
                raise _UnavailableError("内置示例工作簿缺失或哈希不匹配")

            if requested_workbook is not None:
                if not requested_workbook.is_file():
                    raise _UnavailableError(f"请求工作簿不存在：{requested_workbook}")
                requested_member = _safe_member(
                    (workbook_member.parent / requested_workbook.name).as_posix()
                )
                workbook = source_dir.joinpath(*requested_member.parts)
                workbook.write_bytes(requested_workbook.read_bytes())
                original_argument = "/oracle/" + workbook_member.as_posix()
                requested_argument = "/oracle/" + requested_member.as_posix()
                if legacy_command.count(original_argument) != 1:
                    raise _UnavailableError("manifest command 未唯一引用内置示例工作簿")
                legacy_command = [
                    requested_argument if item == original_argument else item
                    for item in legacy_command
                ]

            sheets = _workbook_sheet_names(workbook)
            try:
                folded = [item.casefold() for item in sheets]
                first = folded.index(module_range["after"].casefold()) + 1
                last = folded.index(module_range["before"].casefold())
            except ValueError as exc:
                raise _UnavailableError("工作簿缺少模块范围边界工作表") from exc
            modules = sheets[first:last]
            if requested_workbook is not None:
                prefix = requested_workbook.name.split(".", 1)[0]
                output_mapping = {
                    sheet: f"{prefix}_{sheet.lower()}.svd" for sheet in modules
                }
            elif modules != list(output_mapping):
                raise _UnavailableError(
                    f"manifest 未按顺序覆盖全部模块工作表: workbook={modules!r}, "
                    f"manifest={list(output_mapping)!r}"
                )

            timed_out, container_stopped, engine_stdout, engine_stderr = _run_container(
                engine,
                image,
                platform,
                source_dir,
                output_dir,
                packages,
                legacy_command,
                timeout_seconds,
            )
            if timed_out:
                cleanup = (
                    "已终止容器及宿主进程树"
                    if container_stopped
                    else "宿主进程树已清理，但 Docker 未确认容器停止，请立即检查 Docker daemon"
                )
                return _failed(
                    f"Oracle 命令超过 {timeout_seconds:g} 秒；{cleanup}",
                    stderr=engine_stderr.decode("utf-8", errors="replace"),
                )
            evidence_path = output_dir / "oracle-result.json"
            if not evidence_path.is_file():
                return _failed(
                    "容器未产生环境与进程证据",
                    stdout=engine_stdout.decode("utf-8", errors="replace"),
                    stderr=engine_stderr.decode("utf-8", errors="replace"),
                )
            evidence = _read_json(evidence_path, "容器运行证据")
            python_version = evidence["python_version"]
            dependency_versions = evidence["dependency_versions"]
            if python_version != lock["python"] or dependency_versions != packages:
                return _failed(
                    "容器实际解释器/依赖版本与环境锁不一致",
                    python_version=python_version,
                    dependencies=dependency_versions,
                )
            stdout = base64.b64decode(evidence["stdout_base64"], validate=True).decode(
                "utf-8", errors="replace"
            )
            stderr = base64.b64decode(evidence["stderr_base64"], validate=True).decode(
                "utf-8", errors="replace"
            )
            exit_code = evidence["exit_code"]
            outputs: list[OracleOutput] = []
            for sheet in modules:
                relative = _safe_member(output_mapping[sheet])
                output_path = output_dir.joinpath(*relative.parts)
                if not output_path.is_file():
                    return _failed(
                        f"Oracle 未为工作表 {sheet} 生成 {relative}",
                        python_version=python_version,
                        dependencies=dependency_versions,
                        stdout=stdout,
                        stderr=stderr,
                        exit_code=exit_code,
                        outputs=tuple(outputs),
                    )
                raw_bytes = output_path.read_bytes()
                outputs.append(OracleOutput(sheet, relative.as_posix(), raw_bytes, _sha256(raw_bytes)))
            status = OracleStatus.PASSED if exit_code == 0 else OracleStatus.FAILED
            reason = "" if status is OracleStatus.PASSED else "原始 Oracle 以非零退出码结束"
            return OracleResult(
                status,
                reason,
                python_version,
                dependency_versions,
                stdout,
                stderr,
                exit_code,
                tuple(outputs),
            )
    except _UnavailableError as exc:
        return _unavailable(str(exc))
    except (KeyError, TypeError, ValueError) as exc:
        return _unavailable(f"Oracle manifest/证据不完整或无效: {exc}")
    except (OSError, zipfile.BadZipFile) as exc:
        return _unavailable(str(exc))


def _default_manifest() -> Path:
    return Path(__file__).parents[1] / "tests" / "fixtures" / "regtool260415" / "manifest.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=_default_manifest())
    parser.add_argument("--workbook", type=Path)
    parser.add_argument("--timeout", type=float, default=30)
    arguments = parser.parse_args(argv)
    result = run_oracle(
        arguments.manifest,
        workbook_path=arguments.workbook,
        timeout_seconds=arguments.timeout,
    )
    # JSON 保持纯 ASCII，避免 Windows 控制台代码页破坏中文诊断；JSON 解码后仍是原中文。
    print(json.dumps(result.to_json_dict(), ensure_ascii=True, sort_keys=True))
    return 0 if result.status is OracleStatus.PASSED else 2


if __name__ == "__main__":
    raise SystemExit(main())
