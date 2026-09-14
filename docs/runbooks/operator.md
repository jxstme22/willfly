# Read-only operator setup

This is the reproducible local handoff for macOS, Linux and Windows through
WSL2. It prepares the research service only. It does not create a wallet,
sign, fund, broadcast, buy data access or enable LP.

## Install in a fresh environment

On Windows, install WSL2 and a supported Linux distribution using the normal
Microsoft installer, then run the remaining commands inside that distribution.
Keep the repository and its virtual environment inside the WSL filesystem for
predictable file and SQLite behavior. On macOS or Linux, run the same commands
from a terminal.

```text
git clone <private-repository-url> willfly
cd willfly
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock -r requirements-export.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/willfly operator-check
.venv/bin/python -m pytest
```

`operator-check` is offline. It checks Python 3.12, package/config presence,
fixture integrity, read-only mode and the disabled LP gate. Its
`network_probe` remains `not_run`; use a separately bounded capture when live
source evidence is explicitly required.

To inspect controlled signal output, pass a validated
`willfly.signal-snapshot.v0.1` JSON bundle to the local server:

```text
.venv/bin/willfly serve --check --signals-file /path/to/signals.json
```

To show active model and promotion history, attach an existing registry:

```text
.venv/bin/willfly serve --check \
  --signals-file /path/to/signals.json \
  --model-registry /path/to/models.sqlite3 \
  --initial-active-version active-v1
```

The registry must already exist; this inspection command does not initialize
one. Model promotion and rollback remain separate explicit local commands.

The bundle is display-only. Research-only or unsupported readiness remains an
abstain state in the inbox, and no signal file can enable signing or broadcast.
Include optional `manual_actions` and `wallet_activities` arrays to inspect
conservative action links in the same fresh-process dashboard/API run.

## Run the durable learning watcher tick

The watcher is a restart-safe scheduler state store. It does not claim that a
daemon is running and it does not invent market observations, labels, training
or evaluation. Record an explicit heartbeat with the feedback store attached:

```text
.venv/bin/willfly watcher-tick \
  --state-db /path/to/watcher.sqlite3 \
  --feedback-dir /path/to/feedback \
  --observed-at 2026-09-14T00:00:00Z \
  --schedule --execute-pending
.venv/bin/willfly watcher-status --state-db /path/to/watcher.sqlite3
```

Pass `--observation-state`, `--training-state` and `--evaluation-state` only
when those integrations have current evidence. The default is `waiting`; a
large gap between explicit ticks is persisted as an outage interval. The
default personal-trade count is zero, so personal activity is not required to
advance the scheduler state.

`--execute-pending` without a pipeline config runs only local bounded
callbacks: label maturation is performed against the feedback store, while
observation, training and evaluation remain waiting. To run the concrete
restart-safe chain, provide the reviewed pipeline config and a separate
pipeline state database:

```text
.venv/bin/willfly watcher-tick \
  --state-db /path/to/watcher.sqlite3 \
  --feedback-dir /path/to/feedback \
  --pipeline-config configs/learning/pipeline-v0.1.json \
  --pipeline-state-db /path/to/pipeline.sqlite3 \
  --observed-at 2026-09-14T00:00:00Z \
  --schedule --execute-pending
```

The concrete callbacks are dependency ordered: bounded capture/backfill,
canonical market-feedback build, bounded MaleCNS candidate training, then
model-output/evaluation and research-only signal publication. Each stage uses
an immutable artifact identity, atomic `latest` alias, idempotency key,
subprocess timeout/resource budget and crash-recovery record. A missing block
range, corpus, templates/actions or evaluation points stays `waiting`; no
stage signs, broadcasts, promotes or enables LP.

The dashboard can point at the pipeline's `signals-latest.json`. The server
reloads that file on every GET, so the read-only UI reflects the newest valid
published snapshot without restarting the HTTP process.

## Start a controlled shadow replay

The repository shadow config is deliberately unfrozen. To begin a real
prospective window, copy it to an operator-controlled path, inspect the values,
and freeze it exactly once immediately before the first observation:

```text
cp configs/shadow/config.json /path/to/operator-shadow.json
.venv/bin/willfly shadow-freeze \
  --config /path/to/operator-shadow.json \
  --start-time 2026-09-14T00:00:00Z
.venv/bin/willfly shadow --config /path/to/operator-shadow.json
```

The current source scheduler/recorder is not yet a 24/7 production daemon, so
the frozen config command remains a gate and does not claim that the
prospective window has started. For a bounded controlled-source integration,
use `shadow-run` with an explicit SQLite path and atomic units:

```text
.venv/bin/willfly shadow-run \
  --config /path/to/operator-shadow.json \
  --state-db /path/to/operator-shadow.sqlite \
  --input /path/to/observations.json \
  --fixed-entry-atomic 50 \
  --initial-cash-atomic 100
```

Repeat the command to resume after a stop. The same input prefix is
idempotent; changed config/capital identity and newly out-of-order observations
fail closed. The result is hypothetical and `not_submitted` even when a
modeled fill is recorded.

## Back up and restore local state

Stop writers before taking a backup. The state bundle snapshots SQLite files
through SQLite's backup API, copies other explicitly named paths, records each
file's size and SHA-256, and publishes the archive atomically. It never replaces
an existing archive or restore destination:

```text
.venv/bin/willfly state-backup \
  --output /path/to/willfly-state.tar.gz \
  --source observatory=/path/to/observatory \
  --source feedback=/path/to/feedback \
  --source watcher=/path/to/watcher.sqlite3 \
  --source shadow=/path/to/shadow.sqlite
.venv/bin/willfly state-restore \
  --archive /path/to/willfly-state.tar.gz \
  --destination /path/to/restored-state
```

The restore destination contains `manifest.json` and the named paths under
`state/`. Archive members are restricted to regular files/directories, and
restored SQLite files pass `PRAGMA quick_check` before publication. Config
files remain source-controlled inputs and should be copied separately when
their hashes are part of a run identity.

## Bounded live capture

Use a disposable store for a small RPC probe and keep the output run manifest
for review:

```text
.venv/bin/willfly capture \
  --from-block BLOCK --to-block BLOCK \
  --store-dir /path/to/capture-store \
  --source live-readonly
```

An empty acknowledged range is valid evidence of that range and does not
represent a launch or trade. A missing ancestry anchor, source gap or open
launch-source gate must remain visible in the manifest.

For an independent bounded coverage check, use a separate read-only RPC and
retain the JSON result with the capture manifest:

```text
.venv/bin/willfly coverage-compare \
  --config configs/sources/robinhood-chain-v0.1.json \
  --from-block BLOCK --to-block BLOCK \
  --independent-rpc-url https://robinhood-rpc.publicnode.com \
  --rpc-timeout-seconds 5 \
  --max-rpc-retries 0 \
  --max-runtime-seconds 90
```

This compares event logical keys and requested-range completion across both
providers. It is stronger than an anchor-header identity check, but remains a
bounded coverage sample and does not establish finality or archive
completeness. The RPC, retry and whole-run budgets are explicit; a timeout is
reported as `degraded` and must not be summarized as a coverage pass.

## Safety boundary

There is intentionally no signer, transaction builder, funding command or
automatic execution service in this release. Do not freeze the repository
config as a substitute for the real observation window, and do not promote
controlled inputs or bounded probes into the 14-day, 200-launch or 99%-healthy
acceptance gates.
