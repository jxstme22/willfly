# Manual action linkage and feedback

B7 links externally reported `ManualAction` records to B2 public-wallet
activities. When a transaction hash is supplied, it must match exactly along
with wallet/instrument/direction compatibility. Without a hash, one and only
one compatible activity in a declared time window may match. Amount alone never
links an action. Zero candidates remain `pending`; multiple candidates remain
`ambiguous`; incompatible evidence is retained without a false match.

Links preserve the user's override and manual-only execution scope. The local
API exposes the reported action and link state at `GET /actions`; the dashboard
uses the same status in its signal view. Actual manual outcomes remain
`actual_manual` records with an action ID, while market observations and
counterfactuals remain separate outcome kinds.

This is fixture-backed linkage evidence. It does not create a Zenith control
connection, broadcast a transaction, or claim a live manual-feedback cycle.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_action_linking.py
```
