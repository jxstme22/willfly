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
  --observed-at 2026-09-14T00:00:00Z
.venv/bin/willfly watcher-status --state-db /path/to/watcher.sqlite3
```

Pass `--observation-state`, `--training-state` and `--evaluation-state` only
when those integrations have current evidence. The default is `waiting`; a
large gap between explicit ticks is persisted as an outage interval. The
default personal-trade count is zero, so personal activity is not required to
advance the scheduler state.

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

## Safety boundary

There is intentionally no signer, transaction builder, funding command or
automatic execution service in this release. Do not freeze the repository
config as a substitute for the real observation window, and do not promote
controlled inputs or bounded probes into the 14-day, 200-launch or 99%-healthy
acceptance gates.
