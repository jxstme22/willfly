# M4 connectome provenance and matched-control checkpoint

Status: M4-01 and M4-02 are `IN_PROGRESS` as of 2026-09-14.

The selected MaleCNS v1.0 artifact is pinned by source URL, license, SHA-256,
byte count, row count, schema and a declared presynaptic-to-postsynaptic
orientation. The bounded loader validates Feather columns and positive integer
weights, applies the fixed `log1p(weight)/log1p(10000)` transform, preserves
integer body IDs as strings and reports the selected subset as not whole-CNS
coverage. The release has no measured synapse sign column, so the positive sign
assumption is explicit in the manifest and model report.

The loader also supports contiguous release-order row partitions. The
partition range is derived from the manifest row count, so a bounded experiment
can sample beyond the first rows without inventing a biological node filter.
Every run records its row window, selected edge/node counts and graph hash.

Graph orientation now changes the reservoir edge direction used in state
dynamics; it is not metadata-only. Non-finite or zero edge weights are rejected,
and reservoir states reject non-finite values. The checkpointable experiment
keeps the fly graph fixed while running shuffled-wiring, random-weight,
no-state and ordinary controls over the same partitioned samples.

The random-weight control assigns deterministic independent positive weights
with the source graph's mean preserved. This keeps edge count, orientation and
mean scale matched even when a release partition has a degenerate constant
weight distribution; it is not described as a matched marginal-distribution
control.

Fixture evidence validates provenance, direction, normalization, saturation
stability, checkpoint identity and control construction. Actual whole-release
training, five-seed chronological evaluation, measured PC resource requirements,
and any biological or financial advantage remain open. Loading a connectome is
not a pretrained financial model.

## Actual resource benchmark

Command:

```text
.venv/bin/python scripts/benchmark_malecns.py \
  --max-edges 20000 --max-edges 100000 --partition-count 1
.venv/bin/python scripts/benchmark_malecns.py \
  --max-edges 20000 --partition-count 4 --partition-index 1
```

On the 2026-09-14 host run, the first partition loaded 20,000 edges in 2.30s
and 100,000 edges in 20.17s, with process peak RSS 111,542,272 bytes. The
nonzero partition (release rows 37,964,171–75,928,342) loaded 20,000 edges in
5.51s with process peak RSS 360,611,840 bytes. Each run drove a three-step
reservoir episode. These are measured loading/reservoir resources, not
readout-training or whole-release resources; the small dense readout solver is
not applied to these 10k–38k-node states. A follow-on controlled training run
uses the bounded dual ridge solver on a 100,000-edge four-way partition and is
reported below; whole-release training and five-seed chronological holdouts
remain open.

## Actual partition training

Command:

```text
.venv/bin/python scripts/train_malecns_partition.py \
  --max-edges 100000 --partition-count 4 --partition-index 1 --sample-count 6
```

The actual run completed in 5.08s wall time (1.76s laboratory time), selected
99,095 nodes and produced fly, shuffled-wiring, random-weights, no-state and
ordinary outputs with 4 training and 2 controlled holdout samples. Process
peak RSS was 415,186,944 bytes. The random-weight graph hash was distinct from
the fly graph after the mean-preserving independent-weight control fix. The
inputs and targets are controlled synthetic rows, so equal holdout metrics do
not indicate a financial or biological result. Real qualified labels, more
samples, five seeds, chronological windows and whole-release resource
acceptance remain open.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_neural.py tests/test_laboratory.py
```
