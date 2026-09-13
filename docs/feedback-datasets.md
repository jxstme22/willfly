# Causal feedback and label maturation

B3 records predictions before outcomes exist, then joins them only after an
outcome's `label_available_at` is at or before the dataset cutoff. The durable
`FeedbackStore` keeps prediction payloads immutable, permits evidence-backed
outcome revisions, and maintains a queue state of `waiting`, `ready`,
`unresolved`, or `missing`.

Observed market and simulated counterfactual outcomes are first-class inputs;
they do not require a personal trade. Actual manual outcomes remain distinct
through the signal contract's `action_id`. Delayed labels, missing numeric
targets, invalidated/fork-revised outcomes, target mismatches, expired
predictions, and self-label references remain visible but are not eligible for
training.

This is a causal fixture-backed implementation. It does not claim a live
zero-personal-trade interval, model quality, or automatic retraining. Those
remain B4/B9 and operational acceptance gates.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_feedback_store.py
```
