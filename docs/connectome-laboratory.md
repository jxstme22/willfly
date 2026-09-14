# Fixed-connectome laboratory

B4 now provides a deterministic local experiment runner around the verified
directed graph. It resets recurrent state at episode boundaries, fits only a
linear readout, and binds resumable checkpoints to the graph hash, experiment
configuration hash, and ordered sample hash. A changed graph or dataset cannot
silently resume an old run.

Each run compares the real `fly` graph with shuffled-wiring, random-weight,
no-state and ordinary feature-only controls under the same train/held-out
partitions. It reports held-out mean absolute error and predictions for each
control; it does not convert that metric into a trading claim or promote a
model. With too few qualified training examples or no held-out examples it
returns `waiting` and records the reason.

The checked-in config targets the verified MaleCNS manifest and its bounded
20,000-edge subset. The implementation can consume actual labelled samples
from the feedback pipeline. `build_training_samples_from_feedback` accepts
only eligible matured examples and requires both a feature map and an explicit
partition per prediction, reporting missing inputs as exclusions rather than
inventing rows or assigning holdouts. Tests use a tiny graph and deterministic
fixture labels to verify mechanics only. Windows/WSL2 resource benchmarks,
live zero-trade learning, forward evaluation and model promotion remain open.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_laboratory.py
```

When causal labels are available, `scripts/train_malecns_feedback.py` is the
bounded integration entrypoint. It takes an explicit feedback cutoff, feature
map, train/validation/test assignment, MaleCNS partition and seed list; with
insufficient labels it exits successfully with a `waiting` report and does not
load or train the graph.

```text
.venv/bin/python scripts/train_malecns_feedback.py \
  --feedback-dir /path/to/feedback-store \
  --features /path/to/features.json \
  --partitions /path/to/partitions.json \
  --as-of-time 2026-09-14T00:06:00Z \
  --seeds 7,17,27
```

The completed result for one selected seed can be carried into the signal
boundary without hand-copying predictions. First save the training JSON
report, then provide a typed prediction-template bundle and an explicit action
map:

```text
.venv/bin/willfly model-output \
  --experiment-report /path/to/training-report.json \
  --templates /path/to/prediction-templates.json \
  --output /path/to/model-output.json \
  --model-id male-cns-readout \
  --model-version candidate-v2 \
  --run-ref run:malecns-feedback-seed-7 \
  --as-of-time 2026-09-14T00:06:00Z \
  --run-id malecns-feedback-1-100000-seed-7 \
  --actions /path/to/actions.json
.venv/bin/willfly signal-build \
  --input /path/to/model-output.json \
  --output /path/to/signals.json
```

`model-output` selects the named `fly` metric from the hash-bound experiment
report and carries graph, seed-run and resource lineage into `training_state`.
Experiment prediction rows carry their `validation`/`test` partition;
final-test rows are retained in the report but are not exported as signal
outputs. It never derives an action, confidence, calibration or economic
readiness. A waiting experiment writes an empty output list, so the following
signal build cannot display a fabricated prediction.
