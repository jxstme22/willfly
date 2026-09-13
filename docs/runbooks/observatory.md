# Observatory v0.1 local runbook

This runbook operates Willfly in read-only mode. It does not configure a
signer, broadcast a transaction, buy provider credits, or claim complete
launch history while the source gate is open.

## Clean local verification

```text
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,export]'
.venv/bin/python -m pytest
.venv/bin/willfly fixture-check
.venv/bin/willfly doctor
```

The doctor command is healthy for local configuration but strict mode remains
non-zero while Pons creation/archive evidence is unverified.

## Capture, recovery and audit

Use bounded ranges only. The recorder writes durable batches, filter-bound
checkpoints and a run manifest under the store directory. `--dry-run` prints a
plan and exits 3 without RPC reads or writes:

```text
willfly capture --from-block BLOCK --to-block BLOCK --store-dir data/observatory
willfly backfill --from-block BLOCK --to-block BLOCK --store-dir data/observatory --page-size 500
willfly capture --from-block BLOCK --to-block BLOCK --dry-run
willfly audit --expected expected.json --observed observed.json
```

Each run manifest records run ID, chain/filter/ABI/config hashes, operator
start/stop, provider identity, attempted and acknowledged ranges, header
evidence, errors and retained batches (`<store>/runs/<run-id>.json`). Empty
ranges are acknowledged with header evidence and no batch. Changing `--address`
changes the filter hash and checkpoint namespace, so a changed filter cannot
inherit a prior cursor. The backfill checkpoint is committed only after a page
is published; a provider range error reduces the next request size; malformed
or out-of-range data fails closed. Run `audit --provider-independent` only when
the expected interval came from a genuinely separate source.

## Export and inspect

```text
willfly export --records records.json --output-dir artifacts/datasets --dataset-name timeline
willfly serve --check
```

Parquet sidecars contain schema version, source-config hashes, logical keys,
record hashes, gaps and quality metadata. Re-import with the storage export
verifier before using a dataset for features or replay. The inspection API is
GET-only and binds to `127.0.0.1` by default; no trading route is present.

## Release gate

Before calling this a full v0.1 release, attach the recorder coverage audit,
72-hour gap/recovery evidence, a non-graduate launch sample and the current
provider/archive verdict. If any are missing, label the bundle a partial
pool-only prototype and preserve the explicit unknowns.
