# Observed wallet accounting

B5 now reconciles the B2 wallet observation into an exact-atomic report. Only
canonical confirmed swaps with verified route evidence affect reconciled
per-asset deltas. Failed, pending, unknown, orphaned and unresolved activity is
retained as an audit line and, when it has asset deltas, reported separately as
residuals. LP ownership comes from the observer's lifecycle state; it is not
treated as a spot cash fill.

The report is a read-only evidence view. It does not substitute for the
validated quote/accounting gate in M2, and it does not estimate USD value,
profitability, or a recommendation when marks or exit evidence are missing.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_accounting.py
```
