"""M1-05/M1-06 causal projection persistence and local inspection tests."""

from __future__ import annotations

from threading import Thread
from urllib.request import urlopen

import pytest

from willfly.api.server import ReadOnlyStore, _route, create_server
from willfly.domain import Launch, RawEvent
from willfly.features.projections import LifecycleRevision, ObservatoryProjection, materialize_observatory_projection
from willfly.storage import RawBatchStore


TOKEN = "0x1111111111111111111111111111111111111111"
BLOCK = "0x" + "22" * 32
TX = "0x" + "33" * 32


def _launch() -> Launch:
    # This is deliberately a mutable-looking current record; only a dated
    # LifecycleRevision may put graduation into a causal projection.
    return Launch(4663, TOKEN, None, None, ("launch:1",), None, None, "2026-09-13T00:00:00Z", "observed", (), "graduated")


def _raw(status: str) -> RawEvent:
    block_hash = BLOCK if status == "canonical" else "0x" + "55" * 32
    transaction_hash = TX if status == "canonical" else "0x" + "66" * 32
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": "fixture.observatory",
            "source_schema_version": "fixture.v0.1",
            "block_number": 10,
            "block_hash": block_hash,
            "parent_hash": "0x" + "44" * 32,
            "transaction_hash": transaction_hash,
            "log_index": 0 if status == "canonical" else 1,
            "event_time": "2026-09-13T00:00:01Z",
            "received_time": "2026-09-13T00:00:02Z",
            "payload": {"event": "TokenLaunched"},
            "ingestion_run": "projection-test",
            "canonical_status": status,
        }
    )


def test_projection_is_as_of_and_orphan_evidence_becomes_an_explicit_exclusion(tmp_path):
    active = LifecycleRevision(TOKEN, "active", "2026-09-13T00:00:03Z", ("lifecycle:active",))
    future_graduation = LifecycleRevision(TOKEN, "graduated", "2026-09-13T00:10:00Z", ("lifecycle:graduated",))
    first = materialize_observatory_projection(
        as_of_time="2026-09-13T00:05:00Z",
        launches=[_launch()],
        pools=[],
        raw_events=[_raw("canonical"), _raw("orphaned")],
        trades=[],
        lifecycle_revisions=[active, future_graduation],
    )
    assert first.discovery.launches[0].lifecycle_state == "active"
    assert first.discovery.canonical_event_count == 1
    assert first.exclusions[0]["reason"] == "noncanonical_raw_evidence"

    later = materialize_observatory_projection(
        as_of_time="2026-09-13T00:15:00Z",
        launches=[_launch()],
        pools=[],
        raw_events=[_raw("canonical"), _raw("orphaned")],
        trades=[],
        lifecycle_revisions=[active, future_graduation],
    )
    assert first.discovery.launches[0].lifecycle_state == "active"
    assert later.discovery.launches[0].lifecycle_state == "graduated"

    with RawBatchStore(tmp_path / "store") as store:
        first_record = store.save_snapshot(first, source="fixture-observatory")
        later_record = store.save_snapshot(later, source="fixture-observatory", replaces_snapshot_id=first_record.snapshot_id)
        assert later_record.replaces_snapshot_id == first_record.snapshot_id
    with RawBatchStore(tmp_path / "store") as reopened:
        restored = ObservatoryProjection.from_dict(reopened.load_snapshot(first_record.snapshot_id))
        records = reopened.list_snapshots(source="fixture-observatory")
    assert restored.to_dict() == first.to_dict()
    assert [record.snapshot_id for record in records] == [first_record.snapshot_id, later_record.snapshot_id]


def test_fresh_store_loads_persisted_projection_into_http_and_dashboard(tmp_path):
    projection = materialize_observatory_projection(
        as_of_time="2026-09-13T00:05:00Z",
        launches=[_launch()],
        pools=[],
        raw_events=[_raw("canonical"), _raw("orphaned")],
        trades=[],
        lifecycle_revisions=[LifecycleRevision(TOKEN, "non_graduate", "2026-09-13T00:00:03Z", ("lifecycle:non-graduate",))],
    )
    store_path = tmp_path / "store"
    with RawBatchStore(store_path) as store:
        record = store.save_snapshot(projection, source="fixture-observatory")
    with RawBatchStore(store_path) as store:
        api_store = ReadOnlyStore.from_persisted_snapshot(store, record.snapshot_id)
    launches, status = _route(api_store, "/launches?limit=1")
    assert status == 200
    assert launches["items"][0]["lifecycle_state"] == "non_graduate"
    exclusions, status = _route(api_store, "/exclusions")
    assert status == 200
    assert exclusions["total"] == 1
    evidence_key = next(iter(projection.evidence))
    evidence, status = _route(api_store, "/evidence/" + evidence_key)
    assert status == 200
    assert evidence["canonical_status"] == "canonical"

    try:
        server = create_server(store=api_store, host="127.0.0.1", port=0)
    except PermissionError:
        # Some managed test sandboxes prohibit binding even loopback sockets.
        # The route and dashboard rendering above remain deterministic there.
        pytest.skip("loopback socket binding is unavailable in this sandbox")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=2) as response:  # nosec B310 - local test server
            page = response.read().decode()
        assert "Willfly Observatory" in page
        assert "non_graduate" in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
