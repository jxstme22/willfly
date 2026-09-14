#!/usr/bin/env bash
set -Eeuo pipefail

# Prepare a WSL2 user installation. This script never uses sudo, creates no
# wallet material, and does not start or enable a service.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${WILLFLY_PROJECT_DIR:-$(cd -- "$SCRIPT_DIR/../.." && pwd -P)}"
RUNTIME_DIR="${WILLFLY_RUNTIME_DIR:-$HOME/.local/share/willfly}"
STATE_DIR="${WILLFLY_STATE_DIR:-$HOME/.local/state/willfly}"
CONFIG_DIR="${WILLFLY_CONFIG_DIR:-$HOME/.config/willfly}"
ENV_FILE="${WILLFLY_ENV_FILE:-$CONFIG_DIR/willfly.env}"
PYTHON_BIN="${WILLFLY_PYTHON:-python3.12}"

die() {
    printf 'willfly install: %s\n' "$*" >&2
    exit 2
}

usage() {
    cat <<'EOF'
Usage: deploy/wsl/install.sh [--dry-run]

Prepares the Python 3.12 environment, explicit env file, runtime wrappers and
user-level systemd unit files. Nothing is started or enabled automatically.
EOF
}

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    shift
fi
[[ $# -eq 0 ]] || { usage; exit 2; }

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    die "$PYTHON_BIN was not found; install Python 3.12 inside WSL2 Ubuntu first"
fi
PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
[[ "$PYTHON_VERSION" == "3.12" ]] || die "Python 3.12 is required (found $PYTHON_VERSION)"

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
VENV_DIR="${WILLFLY_VENV:-$RUNTIME_DIR/venv}"

if (( DRY_RUN )); then
    printf 'would prepare project=%s\n' "$PROJECT_DIR"
    printf 'would create venv=%s\n' "$VENV_DIR"
    printf 'would write env=%s\n' "$ENV_FILE"
    printf 'would install user units=%s\n' "$UNIT_DIR"
    printf 'would leave all services stopped and disabled\n'
    exit 0
fi

[[ -d "$PROJECT_DIR" ]] || die "project directory does not exist: $PROJECT_DIR"
[[ -f "$PROJECT_DIR/pyproject.toml" ]] || die "pyproject.toml is missing under $PROJECT_DIR"

for directory in "$RUNTIME_DIR" "$STATE_DIR" "$CONFIG_DIR" "$UNIT_DIR"; do
    if [[ -e "$directory" && ! -d "$directory" ]]; then
        die "path exists but is not a directory: $directory"
    fi
    mkdir -p "$directory"
done

if [[ -e "$ENV_FILE" && -L "$ENV_FILE" ]]; then
    die "refusing a symlink env file: $ENV_FILE"
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    mkdir -p "$(dirname -- "$VENV_DIR")"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
VENV_VERSION="$($VENV_DIR/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
[[ "$VENV_VERSION" == "3.12" ]] || die "existing venv is not Python 3.12: $VENV_DIR"

if [[ "${WILLFLY_SKIP_PACKAGE_INSTALL:-0}" != "1" ]]; then
    # Editable install keeps the source/config paths explicit. Build isolation
    # may need package-index access on a fresh machine; no package is bundled
    # or downloaded silently by this repository.
    "$VENV_DIR/bin/python" -m pip install --no-deps -e "$PROJECT_DIR"
fi

if [[ ! -f "$ENV_FILE" ]]; then
    TEMP_ENV="$(mktemp "$CONFIG_DIR/.willfly.env.XXXXXX")"
    sed \
        -e "s|^WILLFLY_PROJECT_DIR=.*|WILLFLY_PROJECT_DIR=\"$PROJECT_DIR\"|" \
        -e "s|^WILLFLY_VENV=.*|WILLFLY_VENV=\"$VENV_DIR\"|" \
        -e "s|^WILLFLY_STATE_DIR=.*|WILLFLY_STATE_DIR=\"$STATE_DIR\"|" \
        -e "s|^WILLFLY_PYTHON=.*|WILLFLY_PYTHON=\"$VENV_DIR/bin/python\"|" \
        -e "s|^WILLFLY_BIN=.*|WILLFLY_BIN=\"$VENV_DIR/bin/willfly\"|" \
        -e "s|^WILLFLY_LOG_DIR=.*|WILLFLY_LOG_DIR=\"$STATE_DIR/logs\"|" \
        -e "s|^WILLFLY_SOURCE_CONFIG=.*|WILLFLY_SOURCE_CONFIG=\"$PROJECT_DIR/configs/sources/robinhood-chain-v0.1.json\"|" \
        -e "s|^WILLFLY_WATCHER_CONFIG=.*|WILLFLY_WATCHER_CONFIG=\"$PROJECT_DIR/configs/learning/watcher-v0.1.json\"|" \
        -e "s|^WILLFLY_PIPELINE_CONFIG=.*|WILLFLY_PIPELINE_CONFIG=\"$PROJECT_DIR/configs/learning/pipeline-v0.1.json\"|" \
        -e "s|^WILLFLY_SHADOW_CONFIG=.*|WILLFLY_SHADOW_CONFIG=\"$PROJECT_DIR/configs/shadow/config.json\"|" \
        -e "s|^WILLFLY_OBSERVATORY_DIR=.*|WILLFLY_OBSERVATORY_DIR=\"$STATE_DIR/observatory\"|" \
        -e "s|^WILLFLY_FEEDBACK_DIR=.*|WILLFLY_FEEDBACK_DIR=\"$STATE_DIR/feedback\"|" \
        -e "s|^WILLFLY_WATCHER_DB=.*|WILLFLY_WATCHER_DB=\"$STATE_DIR/watcher.sqlite3\"|" \
        -e "s|^WILLFLY_PIPELINE_STATE_DB=.*|WILLFLY_PIPELINE_STATE_DB=\"$STATE_DIR/pipeline.sqlite3\"|" \
        -e "s|^WILLFLY_SHADOW_DB=.*|WILLFLY_SHADOW_DB=\"$STATE_DIR/shadow.sqlite3\"|" \
        -e "s|^WILLFLY_MODEL_REGISTRY=.*|WILLFLY_MODEL_REGISTRY=\"$STATE_DIR/models.sqlite3\"|" \
        -e "s|^WILLFLY_SIGNALS_FILE=.*|WILLFLY_SIGNALS_FILE=\"$PROJECT_DIR/data/pipeline/signals-latest.json\"|" \
        -e "s|^WILLFLY_TRAIN_MANIFEST=.*|WILLFLY_TRAIN_MANIFEST=\"$PROJECT_DIR/configs/connectome/male-cns-v1.0.json\"|" \
        -e "s|^WILLFLY_TRAIN_DATA_ROOT=.*|WILLFLY_TRAIN_DATA_ROOT=\"$STATE_DIR/connectome\"|" \
        -e "s|^WILLFLY_TRAIN_REPORT_DIR=.*|WILLFLY_TRAIN_REPORT_DIR=\"$STATE_DIR/training\"|" \
        -e "s|^WILLFLY_TRAIN_LATEST_REPORT=.*|WILLFLY_TRAIN_LATEST_REPORT=\"$STATE_DIR/training/candidate-latest.json\"|" \
        -e "s|^WILLFLY_TRAIN_CHECKPOINT_DIR=.*|WILLFLY_TRAIN_CHECKPOINT_DIR=\"$STATE_DIR/training/checkpoints\"|" \
        -e "s|^WILLFLY_EVALUATION_REPORT_DIR=.*|WILLFLY_EVALUATION_REPORT_DIR=\"$STATE_DIR/evaluation\"|" \
        -e "s|^WILLFLY_EVALUATION_LATEST_REPORT=.*|WILLFLY_EVALUATION_LATEST_REPORT=\"$STATE_DIR/evaluation/evaluation-latest.json\"|" \
        "$SCRIPT_DIR/willfly.env.example" > "$TEMP_ENV"
    chmod 600 "$TEMP_ENV"
    mv -- "$TEMP_ENV" "$ENV_FILE"
else
    chmod 600 "$ENV_FILE"
fi

mkdir -p "$RUNTIME_DIR/bin" "$STATE_DIR/logs"
install -m 0755 "$SCRIPT_DIR/run-service.sh" "$RUNTIME_DIR/bin/run-service.sh"
install -m 0755 "$SCRIPT_DIR/willflyctl" "$RUNTIME_DIR/bin/willflyctl"
install -m 0755 "$SCRIPT_DIR/smoke.sh" "$RUNTIME_DIR/bin/smoke.sh"

for unit in "$SCRIPT_DIR/systemd/"*.service "$SCRIPT_DIR/systemd/"*.timer; do
    install -m 0644 "$unit" "$UNIT_DIR/$(basename -- "$unit")"
done

if command -v systemctl >/dev/null 2>&1 && systemctl --user daemon-reload >/dev/null 2>&1; then
    printf 'systemd user units loaded; no unit was started or enabled\n'
else
    printf 'systemd user bus is unavailable; unit files were copied for later use\n'
fi

printf 'Prepared Willfly WSL2 runtime under %s\n' "$RUNTIME_DIR"
printf 'Review %s, then run %s/bin/willflyctl start ...\n' "$ENV_FILE" "$RUNTIME_DIR"
printf 'No service was started; this is not 24/7 operation evidence.\n'
