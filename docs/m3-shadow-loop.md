# M3 prospective shadow loop checkpoint

Status: M3-01 and M3-02 are `IN_PROGRESS` as of 2026-09-14. M3-03 remains
open because its duration, launch-count and healthy-availability gates require
actual prospective evidence.

The shadow store now binds a persistent run to supplied config/source/feature/
policy identities. Restarting without the recorded identity, or with a changed
identity, fails closed. Observations, decisions and last-received/last-decision
checkpoints are published in one SQLite transaction. Observation identity is
unique, so a duplicate delivery with changed prediction data returns the
original hypothetical decision instead of creating a second action.

When `model_execution=True`, the runner independently requotes the fixed-ticket
entry or the reconciled token inventory at the supplied execution delay. It
stores modeled fill status, exact input/output amounts, output asset and quote
source reference alongside the proposal. Missing state, unsupported hooks and
reverts remain non-positions; `execution_state` remains `not_submitted`. The
default mode remains proposal-only for callers that have not supplied a
modeled execution request.

The local checks cover restart identity, atomic persistence, changed-prediction
deduplication, shared cash, filled entry/exit inventory, missing-entry handling,
stale/contradictory health and read-only API behavior. The loop does not submit,
sign or fund transactions.

## Controlled-source integration

`willfly shadow-run` consumes a JSON object with an `observations` array. Each
item contains an `observation` (`observation_id`, asset, received time, quality
state and optional source references), a prediction (`model_id`, expected return
and uncertainty in basis points, and an as-of time), and optional decision time
and independent quote inputs. Quotes are passed through the same modeled fill
path as the Python runner; absent state remains `missing_state`.

The command requires a frozen config, an explicit SQLite state path and explicit
atomic capital units:

```text
.venv/bin/willfly shadow-run \
  --config /path/to/frozen-shadow.json \
  --state-db /path/to/shadow.sqlite \
  --input /path/to/observations.json \
  --fixed-entry-atomic 50 \
  --initial-cash-atomic 100
```

The output reports processed versus duplicate observations, health states,
missed deadlines, action and modeled-fill counts, durable checkpoints and
modeled positions. The SQLite store also keeps cumulative health/action/fill
counters in the same transaction as each new observation, so a stopped process
can resume without losing availability accounting. A repeated prefix is safe
to resume; a changed run identity
or out-of-order new observation fails closed. This controlled path was run on
2026-09-14 with two synthetic observations: one healthy `enter`, one delayed
healthy observation classified as `stale`/`watch`, one missed decision, and no
modeled position. That is integration evidence, not prospective market
evidence and not a claim about model quality or returns.

The separate `willfly shadow` command remains a gate check. The repository
config is intentionally unfrozen, so it returns `shadow_config_not_frozen`
until an operator explicitly starts the real observation window.

To freeze a config explicitly, use `shadow-freeze` with a timezone-aware start
time. This mutates only the supplied local config and refuses to overwrite an
already frozen file:

```text
.venv/bin/willfly shadow-freeze \
  --config /path/to/shadow.json \
  --start-time 2026-09-14T00:00:00Z
```

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_shadow.py tests/test_api.py
```
