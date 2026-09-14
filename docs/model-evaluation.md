# Model evaluation and promotion boundary

B8 adds a reproducible candidate-versus-active evaluator over explicit forward
windows and one untouched final-test partition. It pairs market/LP windows,
checks minimum counts, computes mean absolute error, hashes the full final-test
points, and requires the candidate to improve every paired forward and final
test window before producing a `qualified` decision. Missing or mismatched
partitions remain `inconclusive`.

Each report now retains candidate and active scores separately and requires the
two models to share the same observed-at/source/target evidence grid in every
paired window. A row mismatch is an explicit inconclusive reason, not a
silently dropped comparison.

`ModelRegistry` persists active-version history, consumes each final-test hash
once, records evaluations, supports guarded promotion, and permits rollback to
a recorded version. Training completion does not promote a model, and a failed
or inconclusive report cannot promote. Reports require an explicit evaluation
timestamp and dataset identity; no timing, quality, or financial result is
inferred.

The local CLI can evaluate a versioned point bundle and optionally record the
report without changing the active model:

```text
.venv/bin/willfly model-evaluate \
  --points /path/to/prediction-points.json \
  --candidate-version candidate-v2 \
  --active-version active-v1 \
  --evaluated-at 2026-09-14T00:00:00Z \
  --dataset-hash DATASET_HASH \
  --registry /path/to/models.sqlite3 --record
.venv/bin/willfly model-status \
  --registry /path/to/models.sqlite3 --initial-active-version active-v1
```

`--record` consumes the final-test identity in the registry but never promotes
the candidate. Promotion remains a separate guarded operation after review.

The connectome laboratory can feed the signal boundary through the explicit
`willfly model-output` command. It selects one seed/model metric from a
`connectome-experiment.v0.1` result, preserves the experiment report hash and
graph/run metadata, and emits the existing model-output schema for
`signal-build`. The action map is still operator-supplied; no score is turned
into a trade instruction automatically.

The implementation is fixture-backed. Prospective forward windows, untouched
production holdout, calibration, resource scheduling and a live model release
remain open B8/B9/B10 gates.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_promotion.py
```
