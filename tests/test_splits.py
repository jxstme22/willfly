import pytest

from willfly.evaluation.splits import LabelReference, SplitLeakageError, SplitWindow, build_split_manifest


def _ref(record_id: str, group: str, observed: str, horizon: str) -> LabelReference:
    return LabelReference(record_id, group, observed, horizon, observed)


def test_split_manifest_is_chronological_and_purges_groups_and_overlapping_horizons():
    windows = (
        SplitWindow("train", "2026-01-01T00:00:00Z", "2026-01-01T00:10:00Z"),
        SplitWindow("validation", "2026-01-01T00:10:00Z", "2026-01-01T00:20:00Z"),
    )
    manifest = build_split_manifest(
        [
            _ref("train-a", "wallet-a", "2026-01-01T00:01:00Z", "2026-01-01T00:12:00Z"),
            _ref("train-b", "wallet-c", "2026-01-01T00:02:00Z", "2026-01-01T00:03:00Z"),
            _ref("validation-overlap", "wallet-b", "2026-01-01T00:10:00Z", "2026-01-01T00:12:00Z"),
            _ref("validation-group", "wallet-c", "2026-01-01T00:13:00Z", "2026-01-01T00:14:00Z"),
        ],
        windows,
    )
    assert manifest.partitions == {"train": ("train-b",), "validation": ("validation-overlap",)}
    assert {item.reason for item in manifest.exclusions} == {"label_exceeds_partition_end", "group_reused_across_partitions"}
    assert len(manifest.manifest_hash) == 64


def test_future_derived_feature_is_rejected_before_manifest_creation():
    with pytest.raises(SplitLeakageError):
        LabelReference("future", "wallet", "2026-01-01T00:01:00Z", "2026-01-01T00:02:00Z", "2026-01-01T00:01:01Z")
