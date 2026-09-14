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

On a resumed backfill, the runner checks the current target and acknowledged
cursor-boundary headers before inheriting the checkpoint. A changed lineage
invalidates the derived projection and replays the bounded requested range
before acknowledging completion; raw events from both branches remain stored.
An unavailable probe or failed replay leaves the canonical checkpoint in
`needs_repair` and does not claim completed coverage. An unchanged completed
cursor still revalidates the current target tip.

### Bounded ancestry qualification

Capture and backfill never treat an arbitrary oldest header as a trusted root.
For a bounded window, qualify an anchor by declaring its height/hash and
providing a second configured RPC endpoint. The CLI reads `eth_chainId` and
`eth_getBlockByNumber` from both the primary endpoint in the source manifest and
the independent endpoint, then records the matching headers, endpoint
identities, read methods and the explicit operator trust assumption. This is
an anchor-header identity check only; it does not compare event coverage
between providers, and finality is not verified by this command:

```text
willfly qualify-anchor --config configs/sources/robinhood-chain-v0.1.json \
  --height BLOCK --block-hash 0x... \
  --independent-rpc-url https://independent.example/rpc \
  --store-dir data/observatory --source capture
```

The command writes only local evidence/header metadata after read-only RPC
queries; it never signs or broadcasts. `operator_declared_unverified`, old
offline evidence bundles, malformed responses, mismatched chain/config, false
genesis and unavailable or identical endpoints fail closed without changing the
trusted anchor. A successful anchor is then picked up by later capture/backfill
runs in the same source/config namespace. The resulting run manifest and
canonical checkpoint expose the anchor state for review. Code hashes and
deployment receipts alone are not accepted as ancestry/finality evidence.

Exported endpoint provenance is origin-only: userinfo, path tokens, query
parameters and credentials are omitted. The configured URL is retained only in
memory for the transport and is never copied into anchor evidence, run
manifests or CLI error output.

If a later observed fork crosses the bounded anchor, do not overwrite the old
source. Preserve its raw batches and unresolved/boundary-crossing checkpoint,
then qualify a new source namespace and link it to the old one:

```text
willfly qualify-anchor --config configs/sources/robinhood-chain-v0.1.json \
  --height BLOCK --block-hash 0x... \
  --independent-rpc-url https://independent.example/rpc \
  --source capture-requal-v2 \
  --supersedes-source capture:4663:FILTERHASH \
  --supersession-reason "observed fork crosses the old bounded anchor boundary" \
  --store-dir data/observatory
```

The supersession link is immutable and requires the old anchor to exist. Run
subsequent capture/backfill operations with the new source namespace; both
namespaces remain inspectable for audit and recovery.

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
