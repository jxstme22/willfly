# Windows and WSL2 operator runbook

This runbook prepares a local, read-only Willfly research service in Ubuntu on
WSL2. The package supplies user-level systemd units for bounded capture,
watcher ticks, candidate training, forward evaluation, hypothetical shadow
evaluation and the dashboard. Installing the files does not start a service,
enable 24/7 operation, create a wallet, sign, fund or broadcast transactions.

## Prerequisites

Run these commands inside WSL2 Ubuntu. Keep the checkout, virtual environment
and SQLite state inside the Linux filesystem (`~/src`, for example) rather than
under `/mnt/c`; this avoids SQLite and file-permission surprises.

Install WSL2 and Ubuntu using Microsoft's supported installer, then confirm:

```text
python3.12 --version
systemctl --user show-environment
```

The second command requires systemd in WSL. If it is unavailable, add this to
`/etc/wsl.conf` as root in Ubuntu:

```ini
[boot]
systemd=true
```

From Windows PowerShell, apply that setting with `wsl --shutdown`, then start
Ubuntu again. The installation script does not edit `/etc/wsl.conf` and never
uses `sudo`.

For a 32 GB host, an optional `%UserProfile%\.wslconfig` budget that leaves
Windows headroom is:

```ini
[wsl2]
memory=28GB
processors=8
swap=8GB
localhostForwarding=true
```

The current laboratory is CPU and standard-library based. An RTX 4070 Ti is
not required or assumed; install a matching NVIDIA Windows/WSL driver only if
a later, separately benchmarked implementation uses CUDA. `nvidia-smi` output
is not an acceptance claim for model quality or whole-connectome fit.

## Install the user runtime

Clone the private repository and run:

```text
cd ~/src/willfly
bash deploy/wsl/install.sh
```

The installer checks Python 3.12, creates
`~/.local/share/willfly/venv`, performs the editable package install, creates
`~/.config/willfly/willfly.env` with mode 600, copies wrappers and installs
user units under `~/.config/systemd/user`. Package-index access may be needed
for the editable install's build requirements; the script does not install
system packages or contact a paid service.

Review the generated env file before any start command. The source manifest's
public RPC URL is intentionally visible in the repository. This release has
no credential-bearing transport, so do not paste wallet keys or provider
tokens into the env file or source JSON. Use a separately reviewed adapter
when a credentialed provider is eventually supported.

The installer leaves every unit stopped and disabled. A successful installer
run is preparation evidence only. Run the offline smoke path first:

```text
~/.local/share/willfly/bin/willflyctl smoke
```

It validates fixture and operator checks, the expected capture dry-run exit,
dashboard rendering and dry-run command construction without contacting RPC
or binding a socket.

## Configure bounded stages

Edit `~/.config/willfly/willfly.env` and keep all paths absolute.

Capture defaults to a checkpointed `backfill` pass. Set a recent explicit
`WILLFLY_CAPTURE_START_BLOCK` and keep `WILLFLY_CAPTURE_MAX_BLOCKS` bounded
(the example is 500 blocks). Each pass reads the current provider head, refuses
to scan beyond the bound, and lets the durable backfill checkpoint continue on
the next pass. A blank start block produces a `waiting` log line and no RPC
read. Set `WILLFLY_CAPTURE_MODE=capture` only for a fixed range, and set
`WILLFLY_CAPTURE_TO_BLOCK` as well.

The watcher records a timezone-aware heartbeat and schedules durable slots for
observation, labels, training and evaluation. Set
`WILLFLY_PIPELINE_CONFIG` to the reviewed
`configs/learning/pipeline-v0.1.json` copy to enable the concrete chain; its
separate `WILLFLY_PIPELINE_STATE_DB` stores stage runs and immutable artifact
identities. Leave `observation.from_block` and `to_block` unset until the
operator chooses a bounded range. Its default states are `waiting`; that is
deliberate when no stage callback has supplied current evidence. Personal
trades remain at zero and are not a trigger.

The pipeline callbacks run bounded subprocesses in dependency order:
capture/backfill → canonical market feedback and feedback store → MaleCNS
candidate training → evaluation/model-output → research-only signal snapshot.
Completed identities are reused after restart; interrupted runs are requeued.
Evaluation points are optional, but publication is still restricted to
manual-only `abstain` proposals while evaluation is waiting. No signer,
broadcast, promotion or LP path is reachable from the watcher.

Candidate training stays `waiting` until either `WILLFLY_TRAIN_CORPUS` or both
`WILLFLY_TRAIN_FEATURES` and `WILLFLY_TRAIN_PARTITIONS` are set. It calls the
existing bounded `scripts/train_malecns_feedback.py`, writes timestamped JSON
reports and atomically updates `WILLFLY_TRAIN_LATEST_REPORT`. Invalid or
insufficient evidence returns a waiting report without graph loading. The
training unit is capped at 24 GB RAM (20 GB high threshold), 8 CPU cores and a
two-hour wall clock budget; this leaves host headroom on a 32 GB machine.

Forward evaluation stays `waiting` until the points bundle, candidate and
active versions and dataset hash are all supplied. It calls `model-evaluate`
and never calls `model-promote`. Set `WILLFLY_EVALUATION_RECORD=1` only when
the explicitly configured local registry should receive the evaluation record;
promotion and rollback remain manual, reviewable commands.

Shadow evaluation consumes a frozen, operator-controlled input file. Copy and
inspect the repository config, freeze it exactly once, then set its path and
the input path in the env file:

```text
cp configs/shadow/config.json ~/.config/willfly/operator-shadow.json
~/.local/share/willfly/venv/bin/willfly shadow-freeze \
  --config ~/.config/willfly/operator-shadow.json \
  --start-time 2026-09-14T00:00:00Z
```

The shadow unit runs `shadow-run` with atomic units and a restart-safe SQLite
checkpoint. It remains hypothetical and `not_submitted`, even for modeled
fills. No service freezes a config or fabricates observations.

## Start, stop and inspect

`willflyctl start` starts one immediate pass and then arms the corresponding
timer. With no names it starts only the dashboard, watcher and capture. The
single `pipeline` target starts the dashboard plus the restart-safe watcher
pipeline; use it after reviewing the pipeline range and paths:

```text
~/.local/share/willfly/bin/willflyctl start
~/.local/share/willfly/bin/willflyctl start pipeline
~/.local/share/willfly/bin/willflyctl start train evaluate shadow
~/.local/share/willfly/bin/willflyctl status all
```

The unit map is:

| Name | Process | Timer | Default resource cap |
| --- | --- | --- | --- |
| `dashboard` | local HTTP GET dashboard | none | 1 GB / 1 CPU |
| `capture` | bounded read-only backfill/capture | 60 seconds | 1 GB / 1 CPU |
| `watcher` | restart-safe scheduler tick | 60 seconds | 512 MB / 1 CPU |
| `pipeline` | dashboard plus concrete watcher callbacks | 60 seconds | watcher + stage budgets |
| `train` | candidate feedback training | 15 minutes | 24 GB / 8 CPU |
| `evaluate` | forward candidate evaluation | 15 minutes | 4 GB / 4 CPU |
| `shadow` | hypothetical shadow replay | 60 seconds | 1 GB / 1 CPU |

Stop writers before changing configs or state:

```text
~/.local/share/willfly/bin/willflyctl stop all
~/.local/share/willfly/bin/willflyctl status all
```

The control command uses only `systemctl --user`. It refuses backup and
restore when a known writer is active, and it refuses to claim status when the
user systemd bus cannot be inspected. This makes a manual `stop` plus a
status check part of the recovery record.

The dashboard binds to `127.0.0.1:8000` by default. Open that address from a
Windows browser after the dashboard unit reports active. Changing the host to
an address reachable from the LAN is an explicit operator decision requiring
firewall review.

For detailed logs:

```text
journalctl --user -u willfly-capture.service -n 100 --no-pager
journalctl --user -u willfly-train.service -n 100 --no-pager
tail -f ~/.local/state/willfly/logs/watcher.log
```

Wrappers rotate each service log at 10 MiB and retain five numbered files.
Systemd timers use `Persistent=true`, so a missed timer is caught up after the
user session returns. SQLite checkpoints, shadow decision IDs and atomic JSON
report publication make an interrupted pass restartable; they do not turn a
timer into elapsed uptime evidence.

## Backup and restore

Stop all writers and verify status before taking a bundle. The default backup
set includes existing observatory, feedback, watcher, shadow, model-registry
and training paths; explicit `--source NAME=PATH` values can be used for a
different state layout.

```text
~/.local/share/willfly/bin/willflyctl stop all
~/.local/share/willfly/bin/willflyctl backup \
  --output ~/willfly-backups/state-2026-09-14.tar.gz
```

The underlying `state-backup` command snapshots SQLite through SQLite's backup
API, excludes transient WAL/SHM sidecars, records file hashes and refuses to
replace an existing archive. Restore always targets a new directory and
refuses an existing destination:

```text
~/.local/share/willfly/bin/willflyctl restore \
  --archive ~/willfly-backups/state-2026-09-14.tar.gz \
  --destination ~/willfly-restore-2026-09-14
```

Restored SQLite files pass `PRAGMA quick_check` before publication. Review the
manifest and copy selected state into an operator-chosen active layout only
after stopping writers again. Config files are separate inputs and should be
backed up or versioned separately when their hashes participate in a run
identity.

## Recovery and evidence boundaries

After a WSL restart, inspect `willflyctl status all`, then start the stages
whose env inputs are still valid. A failed or waiting oneshot does not erase a
checkpoint; inspect its JSON report and private log before retrying. If a
configuration contract changes intentionally, use a new watcher/shadow state
database so the prior lineage remains unambiguous.

The package and smoke path prove syntax, offline command wiring and safe local
state handling. They do not prove a fresh PC installation, real RPC coverage,
GPU fit, automatic training progress, 24/7 availability, a 14-day shadow
window, profitability or execution readiness. Those require operator-run,
time-stamped evidence after the service is actually started with reviewed
inputs.
