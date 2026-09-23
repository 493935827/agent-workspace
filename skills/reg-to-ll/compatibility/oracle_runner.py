"""容器内的最小进程包装器；不包含或替代任何 regtool 生成逻辑。"""

from __future__ import annotations

import argparse
import base64
import importlib.metadata
import json
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--package", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    command = arguments.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("missing legacy command")

    environment = {
        "HOME": "/home/oracle",
        "LANG": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TEMP": "/tmp",
        "TMP": "/tmp",
    }
    completed = subprocess.run(
        command,
        cwd="/output",
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    evidence = {
        "python_version": os.sys.version.split()[0],
        "dependency_versions": {
            package: importlib.metadata.version(package)
            for package in sorted(arguments.package)
        },
        "stdout_base64": base64.b64encode(completed.stdout).decode("ascii"),
        "stderr_base64": base64.b64encode(completed.stderr).decode("ascii"),
        "exit_code": completed.returncode,
    }
    arguments.evidence.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
