# Public-wallet observer

The B2 observer is a read-only derived layer over route-aware trade evidence
and causal LP observations. It records public activities with exact signed
atomic deltas, transaction status, canonicality status, source references and
explicit route uncertainty. It never uses a private key and never broadcasts
transactions.

`WalletObservationStore` persists current activities in SQLite and keeps prior
payloads in an immutable revision table. Replaying the same activity is an
idempotent duplicate; a fork reconciliation can replace its current
canonicality while retaining the previous payload for audit. Cursor writes bind
to a filter identity and refuse silent filter or lineage changes by returning a
`needs_repair` state.

Position state is derived only from confirmed LP lifecycle records. Open and
resize add liquidity, remove subtracts it, collect does not change ownership,
and unknown/orphaned/unresolved records make the affected position unknown.
Unknown swap routes remain activity evidence but never become verified position
or training facts. All views use separate event and arrival cutoffs.

Focused evidence:

```text
.venv/bin/python -m pytest -q tests/test_wallet_observer.py
```

Typed read-only activity bundles can be imported and projected without a
wallet key:

```text
.venv/bin/willfly wallet-import \
  --bundle /path/to/wallet-activities.json \
  --wallet-dir /path/to/wallet-store
.venv/bin/willfly wallet-status \
  --wallet-dir /path/to/wallet-store \
  --wallet 0x... \
  --as-of-time 2026-09-14T00:00:00Z \
  --arrival-cutoff 2026-09-14T00:00:00Z
```

Import is idempotent and retains revised payloads. An empty or incomplete
bundle returns explicit missingness and no positions; unsupported routes never
become verified position or training facts.

This is implementation and fixture evidence. Live wallet coverage, provider
availability, and prospective learning acceptance remain open gates.
