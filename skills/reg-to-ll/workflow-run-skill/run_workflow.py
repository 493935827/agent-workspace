#!/usr/bin/env python3
"""Thin executable adapter for the stable workflow runner API."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow_runner import main


if __name__ == "__main__":
    raise SystemExit(main())
