# M2-03 causal horizon labels

The existing forward-label builder now has an explicit adapter into the
versioned `OutcomeRecord` contract. Each label keeps its observed event time,
horizon, availability time, status, numeric target and source references.
Observed, censored and unresolved states are preserved; an observed label
without availability is rejected. The adapter uses `observed_market` and
never creates an actual-manual action link.

This connects M2-03 labels to B3's maturation queue, but does not close the
M2 economic or live-source gates. Causal split manifests still govern
partitioning and future leakage; fixture evidence does not replace the
required observed examples.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_labels.py tests/test_feedback_store.py
```
