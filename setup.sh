#!/usr/bin/env bash
# One command to get a NIDS assignment running.
#
#   ./setup.sh --local            on your own machine, using public data
#   ./setup.sh --nrp              on NRP's JupyterHub, using the in-cluster mirror
#   ./setup.sh --local --modules ASN,BGP
#
# A launcher, nothing more: every option is passed straight to
# `scripts/nids-setup.py setup`, which is where the work happens and which
# setup.cmd calls the same way on Windows. Run `./setup.sh --help` for the options.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# python3 on most Unixes; python where only that exists. Windows uses setup.cmd.
PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [[ -z "$PY" ]]; then
    echo "error: no Python found on PATH. Install Python 3.11 or newer." >&2
    exit 1
fi

exec "$PY" "$HERE/scripts/nids-setup.py" setup "$@"
