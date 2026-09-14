#!/usr/bin/env bash
set -Eeuo pipefail

# Common entrypoint for systemd and manual WSL2 runs. Every operation is
# read-only with respect to chain state; local SQLite/report files are explicit
# operator state. Environment values become fixed command arguments; no
# arbitrary command hook is supported.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    shift
fi
SERVICE="${1:-}"

usage() {
    cat <<'EOF'
Usage: run-service.sh [--dry-run] capture|watcher|train|evaluate|shadow|dashboard

The dry-run mode prints the bounded command and does not contact a provider or
write state. Normal mode is intended for user-level systemd units.
EOF
}

case "$SERVICE" in
    capture|watcher|train|evaluate|shadow|dashboard) ;;
    *) usage >&2; exit 2 ;;
esac

ENV_FILE="${WILLFLY_ENV_FILE:-$HOME/.config/willfly/willfly.env}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

PROJECT_DIR="${WILLFLY_PROJECT_DIR:-$(cd -- "$SCRIPT_DIR/../.." && pwd -P)}"
VENV_DIR="${WILLFLY_VENV:-$HOME/.local/share/willfly/venv}"
PYTHON_BIN="${WILLFLY_PYTHON:-$VENV_DIR/bin/python}"
if [[ -n "${WILLFLY_BIN:-}" ]]; then
    WILLFLY_COMMAND=("$WILLFLY_BIN")
else
    WILLFLY_COMMAND=("$PYTHON_BIN" -m willfly)
fi
STATE_DIR="${WILLFLY_STATE_DIR:-$HOME/.local/state/willfly}"
LOG_DIR="${WILLFLY_LOG_DIR:-$STATE_DIR/logs}"

die() {
    printf 'willfly %s: %s\n' "$SERVICE" "$*" >&2
    exit 2
}

require_value() {
    local name="$1"
    local value="${!name:-}"
    [[ -n "$value" ]] || die "$name must be set in $ENV_FILE"
}

valid_integer() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

now_utc() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

print_waiting() {
    local reason="$1"
    printf '{"service":"%s","status":"waiting","reason":"%s"}\n' "$SERVICE" "$reason"
}

rotate_log() {
    local path="$LOG_DIR/$SERVICE.log"
    local max_bytes="${WILLFLY_LOG_MAX_BYTES:-10485760}"
    local backups="${WILLFLY_LOG_BACKUPS:-5}"
    mkdir -p "$LOG_DIR"
    if [[ -f "$path" ]] && [[ "$(wc -c < "$path")" -ge "$max_bytes" ]]; then
        local index
        for (( index=backups-1; index>=1; index-- )); do
            if [[ -e "$path.$index" ]]; then
                mv -f -- "$path.$index" "$path.$((index+1))"
            fi
        done
        mv -f -- "$path" "$path.1"
    fi
    # Keep service logs private because paths and local experiment metadata may
    # be present even though credentials are not supported.
    umask 077
    exec >>"$path" 2>&1
}

run_cmd() {
    if (( DRY_RUN )); then
        printf '+'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

prepare_parent() {
    (( DRY_RUN )) || mkdir -p "$@"
}

rpc_head() {
    local config_path="$1"
    "$PYTHON_BIN" - "$config_path" <<'PY'
import json
import sys
from pathlib import Path

from willfly.adapters.robinhood_rpc import ReadOnlyRpcClient

config_path = Path(sys.argv[1])
payload = json.loads(config_path.read_text(encoding="utf-8"))
chain = payload.get("chain", {})
endpoint = chain.get("rpc_url")
chain_id = chain.get("chain_id", 4663)
if not isinstance(endpoint, str) or not endpoint.startswith(("http://", "https://")):
    raise SystemExit("source manifest RPC endpoint must be HTTP(S)")
client = ReadOnlyRpcClient(endpoint, expected_chain_id=int(chain_id))
client.check_chain()
print(client.block_number())
PY
}

capture() {
    require_value WILLFLY_SOURCE_CONFIG
    local mode="${WILLFLY_CAPTURE_MODE:-backfill}"
    local start="${WILLFLY_CAPTURE_START_BLOCK:-}"
    local max_blocks="${WILLFLY_CAPTURE_MAX_BLOCKS:-500}"
    valid_integer "$max_blocks" || die "WILLFLY_CAPTURE_MAX_BLOCKS must be a non-negative integer"
    (( max_blocks > 0 )) || die "WILLFLY_CAPTURE_MAX_BLOCKS must be positive"
    valid_integer "$start" || {
        (( DRY_RUN )) || print_waiting "capture_start_block_not_configured"
        (( DRY_RUN )) || return 0
        start="0"
    }
    prepare_parent "${WILLFLY_OBSERVATORY_DIR:-$STATE_DIR/observatory}"
    local head
    if [[ "$mode" == "backfill" ]]; then
        if (( DRY_RUN )); then
            head='${RPC_HEAD}'
        else
            head="$(rpc_head "$WILLFLY_SOURCE_CONFIG")"
            valid_integer "$head" || die "RPC head was not an integer"
            if (( head < start )); then
                print_waiting "capture_start_block_is_ahead_of_provider_head"
                return 0
            fi
            if (( head - start + 1 > max_blocks )); then
                print_waiting "capture_window_exceeded_set_a_recent_start_block_or_raise_the_explicit_bound"
                return 0
            fi
        fi
        run_cmd "${WILLFLY_COMMAND[@]}" backfill \
            --config "$WILLFLY_SOURCE_CONFIG" \
            --from-block "$start" \
            --to-block "$head" \
            --store-dir "${WILLFLY_OBSERVATORY_DIR:-$STATE_DIR/observatory}" \
            --source "${WILLFLY_CAPTURE_SOURCE:-live-readonly}" \
            --page-size "${WILLFLY_CAPTURE_PAGE_SIZE:-2000}"
    elif [[ "$mode" == "capture" ]]; then
        local finish="${WILLFLY_CAPTURE_TO_BLOCK:-}"
        valid_integer "$finish" || {
            (( DRY_RUN )) || print_waiting "capture_to_block_not_configured"
            (( DRY_RUN )) || return 0
            finish='${CAPTURE_TO_BLOCK}'
        }
        if (( DRY_RUN )); then
            run_cmd "${WILLFLY_COMMAND[@]}" capture --config "$WILLFLY_SOURCE_CONFIG" --from-block "$start" --to-block "$finish" --store-dir "${WILLFLY_OBSERVATORY_DIR:-$STATE_DIR/observatory}" --source "${WILLFLY_CAPTURE_SOURCE:-live-readonly}"
        else
            (( finish >= start )) || die "WILLFLY_CAPTURE_TO_BLOCK must be >= WILLFLY_CAPTURE_START_BLOCK"
            (( finish - start + 1 <= max_blocks )) || die "fixed capture range exceeds WILLFLY_CAPTURE_MAX_BLOCKS"
            run_cmd "${WILLFLY_COMMAND[@]}" capture --config "$WILLFLY_SOURCE_CONFIG" --from-block "$start" --to-block "$finish" --store-dir "${WILLFLY_OBSERVATORY_DIR:-$STATE_DIR/observatory}" --source "${WILLFLY_CAPTURE_SOURCE:-live-readonly}"
        fi
    else
        die "WILLFLY_CAPTURE_MODE must be backfill or capture"
    fi
}

watcher() {
    require_value WILLFLY_WATCHER_CONFIG
    local state_db="${WILLFLY_WATCHER_DB:-$STATE_DIR/watcher.sqlite3}"
    local feedback_dir="${WILLFLY_FEEDBACK_DIR:-$STATE_DIR/feedback}"
    prepare_parent "$(dirname -- "$state_db")" "$feedback_dir"
    local -a command=("${WILLFLY_COMMAND[@]}" watcher-tick
        --config "$WILLFLY_WATCHER_CONFIG"
        --state-db "$state_db"
        --feedback-dir "$feedback_dir"
        --observed-at "$(now_utc)"
        --schedule
        --execute-pending)
    for pair in \
        "WILLFLY_WATCHER_OBSERVATION_STATE:--observation-state" \
        "WILLFLY_WATCHER_TRAINING_STATE:--training-state" \
        "WILLFLY_WATCHER_EVALUATION_STATE:--evaluation-state"; do
        local name="${pair%%:*}"
        local option="${pair#*:}"
        local value="${!name:-}"
        [[ -n "$value" ]] && command+=("$option" "$value")
    done
    run_cmd "${command[@]}"
}

write_waiting_report() {
    local report_dir="$1"
    local latest="$2"
    local reason="$3"
    (( DRY_RUN )) && { printf '{"service":"%s","status":"waiting","reason":"%s"}\n' "$SERVICE" "$reason"; return; }
    mkdir -p "$report_dir"
    mkdir -p "$(dirname -- "$latest")"
    local temp
    temp="$(mktemp "$report_dir/.waiting.XXXXXX")"
    printf '{"service":"%s","status":"waiting","reason":"%s"}\n' "$SERVICE" "$reason" > "$temp"
    chmod 600 "$temp"
    mv -f -- "$temp" "$latest"
}

publish_report() {
    local report_dir="$1"
    local latest="$2"
    local command_name="$3"
    shift 3
    (( DRY_RUN )) && { run_cmd "$@"; return; }
    mkdir -p "$report_dir"
    mkdir -p "$(dirname -- "$latest")"
    local temp
    temp="$(mktemp "$report_dir/.${command_name}.XXXXXX")"
    if ! "$@" > "$temp"; then
        cat "$temp"
        rm -f -- "$temp"
        return 1
    fi
    chmod 600 "$temp"
    local stamped="$report_dir/${command_name}-$(date -u '+%Y%m%dT%H%M%SZ')-$$.json"
    mv -- "$temp" "$stamped"
    local latest_temp
    latest_temp="$(mktemp "$report_dir/.latest.XXXXXX")"
    cp -- "$stamped" "$latest_temp"
    chmod 600 "$latest_temp"
    mv -- "$latest_temp" "$latest"
    cat "$stamped"
}

train() {
    local report_dir="${WILLFLY_TRAIN_REPORT_DIR:-$STATE_DIR/training}"
    local latest="${WILLFLY_TRAIN_LATEST_REPORT:-$report_dir/candidate-latest.json}"
    local corpus="${WILLFLY_TRAIN_CORPUS:-}"
    local features="${WILLFLY_TRAIN_FEATURES:-}"
    local partitions="${WILLFLY_TRAIN_PARTITIONS:-}"
    if [[ -z "$corpus" && ( -z "$features" || -z "$partitions" ) ]]; then
        write_waiting_report "$report_dir" "$latest" "training_input_not_configured"
        return 0
    fi
    require_value WILLFLY_TRAIN_MANIFEST
    require_value WILLFLY_TRAIN_DATA_ROOT
    require_value WILLFLY_FEEDBACK_DIR
    local cutoff="${WILLFLY_TRAIN_AS_OF_TIME:-$(now_utc)}"
    local checkpoint_dir="${WILLFLY_TRAIN_CHECKPOINT_DIR:-$report_dir/checkpoints}"
    prepare_parent "$report_dir" "$checkpoint_dir"
    local -a command=("$PYTHON_BIN" "$PROJECT_DIR/scripts/train_malecns_feedback.py"
        --manifest "$WILLFLY_TRAIN_MANIFEST"
        --data-root "$WILLFLY_TRAIN_DATA_ROOT"
        --feedback-dir "$WILLFLY_FEEDBACK_DIR"
        --as-of-time "$cutoff"
        --max-edges "${WILLFLY_TRAIN_MAX_EDGES:-100000}"
        --partition-index "${WILLFLY_TRAIN_PARTITION_INDEX:-1}"
        --partition-count "${WILLFLY_TRAIN_PARTITION_COUNT:-4}"
        --seeds "${WILLFLY_TRAIN_SEEDS:-7,17,27}"
        --checkpoint-dir "$checkpoint_dir"
        --max-training-examples "${WILLFLY_TRAIN_MAX_EXAMPLES:-100000}")
    if [[ -n "$corpus" ]]; then
        command+=(--corpus "$corpus")
    else
        command+=(--features "$features" --partitions "$partitions")
    fi
    publish_report "$report_dir" "$latest" candidate "${command[@]}"
}

evaluate() {
    local report_dir="${WILLFLY_EVALUATION_REPORT_DIR:-$STATE_DIR/evaluation}"
    local latest="${WILLFLY_EVALUATION_LATEST_REPORT:-$report_dir/evaluation-latest.json}"
    local points="${WILLFLY_EVALUATION_POINTS:-}"
    local candidate="${WILLFLY_EVALUATION_CANDIDATE_VERSION:-}"
    local active="${WILLFLY_EVALUATION_ACTIVE_VERSION:-}"
    local dataset_hash="${WILLFLY_EVALUATION_DATASET_HASH:-}"
    if [[ -z "$points" || -z "$candidate" || -z "$active" || -z "$dataset_hash" ]]; then
        write_waiting_report "$report_dir" "$latest" "evaluation_input_not_configured"
        return 0
    fi
    local cutoff="${WILLFLY_EVALUATION_AS_OF_TIME:-$(now_utc)}"
    prepare_parent "$report_dir"
    local -a command=("${WILLFLY_COMMAND[@]}" model-evaluate
        --points "$points"
        --candidate-version "$candidate"
        --active-version "$active"
        --evaluated-at "$cutoff"
        --dataset-hash "$dataset_hash"
        --minimum-forward-windows "${WILLFLY_EVALUATION_MIN_WINDOWS:-2}"
        --minimum-points-per-window "${WILLFLY_EVALUATION_MIN_POINTS:-2}")
    if [[ "${WILLFLY_EVALUATION_RECORD:-0}" == "1" ]]; then
        require_value WILLFLY_MODEL_REGISTRY
        command+=(--registry "$WILLFLY_MODEL_REGISTRY" --record)
    fi
    publish_report "$report_dir" "$latest" evaluation "${command[@]}"
}

shadow() {
    require_value WILLFLY_SHADOW_CONFIG
    local input="${WILLFLY_SHADOW_INPUT:-}"
    local state_db="${WILLFLY_SHADOW_DB:-$STATE_DIR/shadow.sqlite3}"
    if [[ -z "$input" ]]; then
        print_waiting "shadow_input_not_configured"
        return 0
    fi
    if (( ! DRY_RUN )) && [[ ! -f "$input" ]]; then
        print_waiting "shadow_input_does_not_exist"
        return 0
    fi
    prepare_parent "$(dirname -- "$state_db")"
    local -a command=("${WILLFLY_COMMAND[@]}" shadow-run
        --config "$WILLFLY_SHADOW_CONFIG"
        --state-db "$state_db"
        --input "$input"
        --fixed-entry-atomic "${WILLFLY_SHADOW_FIXED_ENTRY_ATOMIC:-50}"
        --initial-cash-atomic "${WILLFLY_SHADOW_INITIAL_CASH_ATOMIC:-100}"
        --max-positions "${WILLFLY_SHADOW_MAX_POSITIONS:-3}")
    run_cmd "${command[@]}"
}

dashboard() {
    local -a command=("${WILLFLY_COMMAND[@]}" serve
        --host "${WILLFLY_DASHBOARD_HOST:-127.0.0.1}"
        --port "${WILLFLY_DASHBOARD_PORT:-8000}"
        --store-dir "${WILLFLY_OBSERVATORY_DIR:-$STATE_DIR/observatory}")
    [[ -n "${WILLFLY_SIGNALS_FILE:-}" ]] && command+=(--signals-file "$WILLFLY_SIGNALS_FILE")
    if [[ -n "${WILLFLY_MODEL_REGISTRY:-}" && -n "${WILLFLY_INITIAL_ACTIVE_VERSION:-}" ]]; then
        command+=(--model-registry "$WILLFLY_MODEL_REGISTRY" --initial-active-version "$WILLFLY_INITIAL_ACTIVE_VERSION")
    fi
    run_cmd "${command[@]}"
}

if (( ! DRY_RUN )); then
    rotate_log
    printf 'started service=%s at=%s\n' "$SERVICE" "$(now_utc)"
fi

case "$SERVICE" in
    capture) capture ;;
    watcher) watcher ;;
    train) train ;;
    evaluate) evaluate ;;
    shadow) shadow ;;
    dashboard) dashboard ;;
esac
