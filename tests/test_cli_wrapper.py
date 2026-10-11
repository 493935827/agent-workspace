"""Windows entry point must preserve the CLI result for callers."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows .cmd wrapper")
def test_windows_wrapper_preserves_argument_error(tmp_path: Path) -> None:
    wrapper = Path(__file__).resolve().parents[1] / "scripts" / "agentctl.cmd"
    result = subprocess.run(
        [str(wrapper), "--doctor"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 2
    assert "required: COMMAND" in result.stderr
