# Causal feedback and label maturation

B3 records predictions before outcomes exist, then joins them only after an
outcome's `label_available_at` is at or before the dataset cutoff. The durable
`FeedbackStore` keeps prediction payloads immutable, permits evidence-backed
outcome revisions, and maintains a queue state of `waiting`, `ready`,
`unresolved`, or `missing`.

Observed market and simulated counterfactual outcomes are first-class inputs;
they do not require a personal trade. Actual manual outcomes remain distinct
through the dataset's `outcome_id` and `action_id` lineage as well as the
signal contract's `action_id`. Delayed labels, missing numeric
targets, invalidated/fork-revised outcomes, target mismatches, expired
predictions, and self-label references remain visible but are not eligible for
training.

If more than one eligible outcome exists for the same prediction, the feedback
dataset retains every outcome for audit but the training adapter excludes all
of them with `multiple_eligible_outcomes_for_prediction`. This prevents an
observed-market result, a manual action result and a simulated counterfactual
from being collapsed into one ambiguous training row.

This is a causal fixture-backed implementation. It does not claim a live
zero-personal-trade interval, model quality, or automatic retraining. Those
remain B4/B9 and operational acceptance gates.

Typed bundles can be imported into the durable store without credentials:

```text
.venv/bin/willfly feedback-import \
  --bundle /path/to/feedback.json \
  --feedback-dir /path/to/feedback-store \
  --as-of-time 2026-09-14T00:06:00Z
.venv/bin/willfly feedback-status \
  --feedback-dir /path/to/feedback-store \
  --as-of-time 2026-09-14T00:06:00Z
```

The importer is idempotent, records outcome revisions, re-matures the queue
at the explicit cutoff and reports `ready` only when an eligible numeric label
exists. An empty, delayed or unresolved bundle remains visible as waiting or
unresolved.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_feedback_store.py
```
