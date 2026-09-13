# M4 connectome provenance and matched-control checkpoint

Status: M4-01 and M4-02 are `IN_PROGRESS` as of 2026-09-14.

The selected MaleCNS v1.0 artifact is pinned by source URL, license, SHA-256,
byte count, row count, schema and a declared presynaptic-to-postsynaptic
orientation. The bounded loader validates Feather columns and positive integer
weights, applies the fixed `log1p(weight)/log1p(10000)` transform, preserves
integer body IDs as strings and reports the selected subset as not whole-CNS
coverage. The release has no measured synapse sign column, so the positive sign
assumption is explicit in the manifest and model report.

Graph orientation now changes the reservoir edge direction used in state
dynamics; it is not metadata-only. Non-finite or zero edge weights are rejected,
and reservoir states reject non-finite values. The checkpointable experiment
keeps the fly graph fixed while running shuffled-wiring, random-weight,
no-state and ordinary controls over the same partitioned samples.

Fixture evidence validates provenance, direction, normalization, saturation
stability, checkpoint identity and control construction. Actual whole-release
training, five-seed chronological evaluation, measured PC resource requirements,
and any biological or financial advantage remain open. Loading a connectome is
not a pretrained financial model.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_neural.py tests/test_laboratory.py
```

