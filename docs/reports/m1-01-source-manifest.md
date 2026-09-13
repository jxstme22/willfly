# M1-01 source-manifest verification

Status: IN_PROGRESS with explicit live/history gates open

Date: 14 September 2026

The pinned Robinhood Chain source manifest now has an offline validator. The
validator checks the declared read-only mode, chain ID `4663`, credential-free
HTTPS/WSS endpoint shapes, the pinned Uniswap V4 and Pons V2 ABI file hashes,
the exact supported event-family sets, and the recorded bounded probe identity.
It does not contact providers or turn a bounded probe into a completeness claim.

The validator passed against
`configs/sources/robinhood-chain-v0.1.json`:

- Uniswap V4 ABI SHA-256: `bc1687a0f93e85047e3096030496779de3c868a126185329ebc09d429d28268f`;
- Pons V2 ABI SHA-256: `5d4bd5911e07f74fffb48c8856ab599f21be1a3c0be1b9a964c845b725f03223`;
- observed chain ID: `4663`;
- status: `ready_with_open_gates`.

The source remains non-deployable for production capture until the existing
gates are closed: historical Pons code at the documented creation block,
non-graduate window coverage, provider history/limit measurement, and the
M1-07 72-hour completeness audit. No signer, broadcast endpoint, provider key,
or paid source was added.

Reproduction:

```text
.venv/bin/python scripts/check_source_manifest.py
.venv/bin/python -m pytest -q tests/test_source_manifest.py
```
