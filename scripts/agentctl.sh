#!/usr/bin/env sh
# Run agentctl from this workspace without a global install.
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -x "$HERE/../.venv/bin/python" ]; then
  exec "$HERE/../.venv/bin/python" -m agentctl "$@"
fi
exec python -m agentctl "$@"