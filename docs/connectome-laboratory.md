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
from the feedback pipeline; tests use a tiny graph and deterministic fixture
labels to verify mechanics only. Windows/WSL2 resource benchmarks, live
zero-trade learning, forward evaluation and model promotion remain open.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_laboratory.py
```
