from willfly.evaluation.replay_audit import run_replay_audit
from willfly.evaluation.replay_bundle import write_replay_bundle
from willfly.evaluation.splits import LabelReference, SplitManifest, SplitWindow, build_split_manifest
from willfly.replay.execution import PoolQuote, simulate_fill
from willfly.replay.scheduler import ReplayEvent, ReplayTick


def test_replay_audit_records_determinism_cost_stress_and_unsupported_paths(tmp_path):
    events = [ReplayEvent("event", "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z", {})]
    ticks = [ReplayTick("tick", "2026-01-01T00:00:02Z")]
    fills = [
        simulate_fill(PoolQuote("pool", "ETH", "TOKEN", 1000, 1000, 30, "2026-01-01T00:00:00Z"), input_atomic=10, submitted_at="2026-01-01T00:00:01Z"),
        simulate_fill(None, input_atomic=10, submitted_at="2026-01-01T00:00:01Z"),
    ]
    audit = run_replay_audit(events, ticks, fills=fills, data_charge_atomic=7)
    assert audit.deterministic is True
    assert audit.exact_fill_count == 0
    assert audit.approximate_fill_count == 1
    assert audit.failed_fill_count == 1
    assert audit.failure_reasons == ("missing_historical_state",)
    assert audit.data_charge_atomic == 7
    assert audit.evidence_state == "inconclusive"
    assert "insufficient_observed_transaction_examples" in audit.residual_discrepancies
    assert {scenario.name for scenario in audit.cost_scenarios} == {"base", "stressed"}


def test_replay_bundle_hashes_evidence_and_blocks_profitability_claim_without_sample(tmp_path):
    split = build_split_manifest(
        [LabelReference("label", "group", "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z", "2026-01-01T00:00:00Z")],
        [SplitWindow("train", "2026-01-01T00:00:00Z", "2026-01-01T00:02:00Z")],
    )
    audit = run_replay_audit([], [])
    bundle = write_replay_bundle(
        output_dir=tmp_path,
        bundle_name="replay-v0.1",
        dataset_rows=[{"id": "row-1", "amount": "12345678901234567890"}],
        labels=[{"record_id": "label", "status": "censored"}],
        split_manifest=split,
        audit=audit,
        accounting_summary={"balances": {"ETH": 1000}},
    )
    assert len(bundle.dataset_hash) == 64
    assert bundle.profitability_claim_status == "inconclusive"
    assert (tmp_path / "replay-v0.1" / "manifest.json").is_file()
    assert (tmp_path / "replay-v0.1" / "accounting.json").is_file()
