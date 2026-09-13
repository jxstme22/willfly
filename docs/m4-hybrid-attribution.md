# M4-05 hybrid attribution checkpoint

Status: `IN_PROGRESS` as of 2026-09-14.

`run_factorial` now records a versioned cell for each architecture × LP-data ×
text-data combination. Every cell carries the dataset hash, config hash and
evidence references, and only the declared states `pass`, `inconclusive` or
`unavailable` are accepted. `review_factorial` checks that the full registered
grid is present, identities match, every cell has evidence references and no
cell is unavailable before returning `pass`.

This is an attribution and evidence-integrity boundary, not a result claim. A
cell’s scalar metric, cost and latency still need to come from the same
replay/prospective evaluator. Missing optional data remains an explicit
`unavailable` or `inconclusive` contribution; it cannot be converted into a
zero-cost advantage. The review does not promote a model or enable execution.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_hybrid.py
```

