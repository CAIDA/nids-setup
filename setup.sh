#!/usr/bin/env bash
# One command to get a NIDS assignment running.
#
#   ./setup.sh --local            on your own machine, using public data
#   ./setup.sh --nrp              on NRP's JupyterHub, using the in-cluster mirror
#   ./setup.sh --local --modules ASN,BGP
#
# It runs three steps, each of which is also a subcommand you can run on its own:
#
#   clone   scripts/clone-nids-repos.sh   the module repos, listed in the registry
#   env     nids-setup.py env             one Python environment for all of them
#   data    nids-setup.py data            each module's data files, into its data/
#
# Re-running is safe: every step skips what is already done.
set -euo pipefail

MODE=""
MODULES=""
RELEASE="r1"
ROOT=""
PYTHON=""
SKIP_ENV=0
SKIP_DATA=0

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d'
    cat <<'USAGE'
Options:
  --local              set up on your own machine (public data)
  --nrp                set up on NRP's JupyterHub (in-cluster mirror, hub-provided Python)
  --modules A,B        only these modules (default: everything in the release)
  --release TIER       which release tier to set up (default: r1)
  --root DIR           where the module repos go (default: the parent of this checkout)
  --python EXE         interpreter to build the environment with (not the one that
                       runs this script)
  --skip-env           do not build a Python environment
  --skip-data          do not download data
  -h, --help           this text
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --local) MODE="local"; shift ;;
        --nrp) MODE="nrp"; shift ;;
        --modules) MODULES="$2"; shift 2 ;;
        --release) RELEASE="$2"; shift 2 ;;
        --root) ROOT="$2"; shift 2 ;;
        --python) PYTHON="$2"; shift 2 ;;
        --skip-env) SKIP_ENV=1; shift ;;
        --skip-data) SKIP_DATA=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ -z "$MODE" ]]; then
    echo "error: say where you are running -- --local or --nrp" >&2
    echo "       (--local uses public data; --nrp uses the in-cluster mirror)" >&2
    exit 2
fi

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ -n "$ROOT" ]] || ROOT="$(dirname -- "$HERE")"
# --python names the interpreter the *environment* is built with; the driver below is
# whatever python3 is on PATH, and needs only the standard library.
PY="python3"

# The hub image already provides the notebook packages, and its kernel is the one
# JupyterHub spawns, so a venv there would be ignored at best.
if [[ "$MODE" == "nrp" && $SKIP_ENV -eq 0 ]]; then
    SKIP_ENV=1
    ENV_NOTE="skipped on NRP -- the hub image already provides the packages"
fi

SELECT=(--release "$RELEASE")
[[ -z "$MODULES" ]] || SELECT=(--modules "$MODULES")

echo "=============================================================="
echo " NIDS setup -- ${MODE}, release ${RELEASE}${MODULES:+, modules $MODULES}"
echo " repos go in: $ROOT"
echo "=============================================================="

echo
echo "--- 1/3  cloning module repositories -------------------------"
if ! bash "$HERE/scripts/clone-nids-repos.sh" "${SELECT[@]}" --root "$ROOT"; then
    echo
    echo "Stopping: the module repositories did not clone, so there is nothing to build" >&2
    echo "an environment for or to download data into. Fix the errors above and re-run;" >&2
    echo "this script picks up where it left off." >&2
    exit 1
fi

echo
echo "--- 2/3  building the Python environment ---------------------"
if [[ $SKIP_ENV -eq 1 ]]; then
    echo "${ENV_NOTE:-skipped (--skip-env)}"
else
    ENV_ARGS=(env --release "$RELEASE")
    [[ -z "$MODULES" ]] || ENV_ARGS=(env $(printf -- '--assignment %s ' ${MODULES//,/ }))
    [[ -z "$PYTHON" ]] || ENV_ARGS+=(--python "$PYTHON")
    "$PY" "$HERE/scripts/nids-setup.py" "${ENV_ARGS[@]}"
fi

echo
echo "--- 3/3  staging data ----------------------------------------"
if [[ $SKIP_DATA -eq 1 ]]; then
    echo "skipped (--skip-data)"
else
    DATA_ARGS=(--root "$ROOT" data --release "$RELEASE")
    [[ -z "$MODULES" ]] || DATA_ARGS=(--root "$ROOT" data $(printf -- '--assignment %s ' ${MODULES//,/ }))
    [[ "$MODE" == "nrp" ]] && DATA_ARGS+=(--nrp)
    "$PY" "$HERE/scripts/nids-setup.py" "${DATA_ARGS[@]}"
fi

echo
echo "=============================================================="
echo " Done. Next:"
if [[ $SKIP_ENV -eq 0 ]]; then
    echo "   source $HERE/.venv/bin/activate"
    echo "   jupyter lab $ROOT"
else
    echo "   open a module's notebook in JupyterHub"
fi
echo "=============================================================="
