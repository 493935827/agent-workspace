"""Allow `python -m agentctl` (the zero-install offline entry point)."""
from agentctl.cli import main

if __name__ == "__main__":
    raise SystemExit(main())