# Model evaluation and promotion boundary

B8 adds a reproducible candidate-versus-active evaluator over explicit forward
windows and one untouched final-test partition. It pairs market/LP windows,
checks minimum counts, computes mean absolute error, hashes the full final-test
points, and requires the candidate to improve every paired forward and final
test window before producing a `qualified` decision. Missing or mismatched
partitions remain `inconclusive`.

`ModelRegistry` persists active-version history, consumes each final-test hash
once, records evaluations, supports guarded promotion, and permits rollback to
a recorded version. Training completion does not promote a model, and a failed
or inconclusive report cannot promote. Reports require an explicit evaluation
timestamp and dataset identity; no timing, quality, or financial result is
inferred.

The implementation is fixture-backed. Prospective forward windows, untouched
production holdout, calibration, resource scheduling and a live model release
remain open B8/B9/B10 gates.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_promotion.py
```
