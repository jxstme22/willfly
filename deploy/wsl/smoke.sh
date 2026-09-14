#!/usr/bin/env bash
set -Eeuo pipefail

# Offline smoke path for a fresh checkout. It deliberately avoids binding a
# socket because restricted CI/sandbox hosts may deny loopback sockets; the
# actual dashboard service is checked by the unit and can be started in WSL2.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${WILLFLY_PROJECT_DIR:-$(cd -- "$SCRIPT_DIR/../.." && pwd -P)}"
PYTHON_BIN="${WILLFLY_PYTHON:-python3.12}"
RUNNER="$SCRIPT_DIR/run-service.sh"

die() { printf 'willfly smoke: %s\n' "$*" >&2; exit 1; }

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "$PYTHON_BIN was not found"
[[ -f "$PROJECT_DIR/pyproject.toml" ]] || die "project directory is invalid: $PROJECT_DIR"

export PYTHONPATH="$PROJECT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON_BIN" -m willfly fixture-check --manifest "$PROJECT_DIR/tests/fixtures/manifest.json"
"$PYTHON_BIN" -m willfly operator-check \
    --config "$PROJECT_DIR/configs/sources/robinhood-chain-v0.1.json" \
    --shadow-config "$PROJECT_DIR/configs/shadow/config.json" \
    --manifest "$PROJECT_DIR/tests/fixtures/manifest.json"

set +e
capture_plan="$(mktemp /tmp/willfly-capture-plan.XXXXXX)"
"$PYTHON_BIN" -m willfly capture \
    --config "$PROJECT_DIR/configs/sources/robinhood-chain-v0.1.json" \
    --from-block 0 --to-block 0 --dry-run >"$capture_plan"
capture_rc=$?
set -e
rm -f -- "$capture_plan"
[[ "$capture_rc" -eq 3 ]] || die "capture dry-run returned $capture_rc (expected 3)"

"$PYTHON_BIN" - <<'PY'
from willfly.features.discovery import DiscoverySnapshot
from willfly.ui.dashboard import render_dashboard

snapshot = DiscoverySnapshot(
    as_of_time="2026-09-14T00:00:00Z",
    launches=(),
    pools=(),
    canonical_event_count=0,
    unknown_lifecycle_count=0,
    missingness=("smoke",),
    quality_state="unknown",
    lineage=("smoke:offline",),
)
html = render_dashboard(
    snapshot,
    training_state={"status": "waiting", "reason": "smoke"},
    model_state={"status": "unknown", "reason": "smoke"},
)
assert "Observatory" in html
assert "Missingness" in html
assert "smoke" in html
print("dashboard render: ok")
PY

temp_dir="$(mktemp -d /tmp/willfly-wsl-smoke.XXXXXX)"
trap 'rm -rf -- "$temp_dir"' EXIT
export WILLFLY_PROJECT_DIR="$PROJECT_DIR"
export WILLFLY_PYTHON="$PYTHON_BIN"
export WILLFLY_VENV="${WILLFLY_VENV:-$temp_dir/venv}"
unset WILLFLY_BIN
export WILLFLY_STATE_DIR="$temp_dir/state"
export WILLFLY_LOG_DIR="$temp_dir/logs"
export WILLFLY_ENV_FILE="$temp_dir/operator.env"
export WILLFLY_SOURCE_CONFIG="$PROJECT_DIR/configs/sources/robinhood-chain-v0.1.json"
export WILLFLY_WATCHER_CONFIG="$PROJECT_DIR/configs/learning/watcher-v0.1.json"
export WILLFLY_SHADOW_CONFIG="$PROJECT_DIR/configs/shadow/config.json"
export WILLFLY_CAPTURE_START_BLOCK=0
export WILLFLY_CAPTURE_MAX_BLOCKS=500
"$RUNNER" --dry-run capture
"$RUNNER" --dry-run watcher
"$RUNNER" --dry-run train
"$RUNNER" --dry-run evaluate
"$RUNNER" --dry-run shadow
"$RUNNER" --dry-run dashboard

printf 'WSL2 offline smoke: passed\n'
