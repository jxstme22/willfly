# Willfly pipeline build context

This context is derived from the approved brain-signal handoff and the existing
Robinhood Chain Observatory implementation. It is a local build record, not a
claim of live availability.

```yaml
pipeline:
  ingestion_method: rpc-polling
  data_types:
    - program-events
    - transactions
    - account-state
    - token-transfers
    - wallet-positions
  storage: custom
  backfill_implemented: true
  restart_safe: true
product:
  signal_contract: configs/experiments/signal-contracts-v0.1.json
  execution_scope: manual_only
  signing_enabled: false
  funding_enabled: false
  biological_source: MaleCNS v1.0 candidate; provenance and checksum gate open
```

The pipeline stores block/slot-equivalent ordering, raw evidence and durable
checkpoints. The current implementation is EVM/Robinhood Chain-first despite
the generic data-pipeline terminology. Provider archive depth, sustained
completeness and biological-source download availability remain explicit gates.
