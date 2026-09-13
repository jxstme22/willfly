"""Regression coverage for the interrupted DeepSeek ancestry audit."""

from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from willfly.domain import RawEvent
from willfly.adapters.robinhood_rpc import RpcLog
from willfly.ingest.backfill import BackfillCheckpointStore
from willfly.ingest.canonicalize import canonicalize_events
from willfly.ingest.runner import backfill_to_store, capture_to_store, checkpoint_source, filter_identity
from willfly.ingest.supervisor import redact_endpoint, redact_error
from willfly.storage import AncestryAnchor, BlockHeader, RawBatchStore, anchor_evidence_record


ROOT = Path(__file__).resolve().parents[1]
V4 = "0x8366a39cc670b4001a1121b8f6a443a643e40951"


def _hash(number: int) -> str:
    return "0x" + f"{number:064x}"


def _source() -> str:
    return checkpoint_source("capture", 4663, _filter_hash())


def _filter_hash() -> str:
    return filter_identity(chain_id=4663, addresses=[V4])


def _anchor(
    height: int,
    block_hash: str,
    *,
    qualification: str = "independent_header_cross_check",
    config_identity: str | None = None,
    evidence: tuple[str, ...] | None = None,
    source: str | None = None,
) -> AncestryAnchor:
    config = config_identity or _filter_hash()
    if evidence is None:
        evidence = (
            anchor_evidence_record(
                "independent_header_cross_check",
                chain_id=4663,
                config_identity=config,
                height=height,
                block_hash=block_hash,
                primary_endpoint="fixture.primary",
                independent_endpoint="fixture.secondary",
                read_methods=["eth_chainId", "eth_getBlockByNumber"],
                verification="performed_rpc_cross_check",
                trust_policy="distinct_configured_endpoints_operator_assumption",
                finality_status="not_verified",
                primary_header={"number": height, "hash": block_hash},
                external_header={"number": height, "hash": block_hash},
            ),
        )
    return AncestryAnchor(
        chain_id=4663,
        height=height,
        block_hash=block_hash,
        qualification=qualification,
        evidence=evidence,
        config_identity=config,
        source=source or _source(),
        recorded_at="2026-09-14T00:00:00Z",
    )


def _event(number: int, block_hash: str, parent_hash: str | None, index: int = 0) -> RawEvent:
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": "fixture.ancestry-repair",
            "source_schema_version": "fixture.v1",
            "block_number": number,
            "block_hash": block_hash,
            "parent_hash": parent_hash,
            "transaction_hash": _hash(10000 + number + index),
            "log_index": index,
            "event_time": "2026-09-14T00:00:00Z",
            "received_time": "2026-09-14T00:00:01Z",
            "payload": {},
            "ingestion_run": "ancestry-repair",
            "canonical_status": "provisional",
        }
    )


def test_anchor_states_are_fail_closed_for_unverified_false_genesis_and_unreached_anchor():
    h99, h100, h101, h150 = (_hash(number) for number in (99, 100, 101, 150))
    headers = [
        BlockHeader(99, h99, _hash(98)),
        BlockHeader(100, h100, h99),
        BlockHeader(101, h101, h100),
    ]
    unverified = _anchor(100, h100, qualification="operator_declared_unverified")
    result = canonicalize_events(
        [_event(101, h101, h100)],
        tip_hash=h101,
        headers=headers,
        anchor=unverified,
        expected_chain_id=4663,
        expected_config_identity=_filter_hash(),
    )
    assert result.anchor_state == "unverified"
    assert result.is_resolved is False
    assert not result.canonical_events and not result.orphaned_events

    false_genesis = _anchor(
        100,
        h100,
        qualification="genesis",
        evidence=(
            anchor_evidence_record(
                "genesis_header",
                chain_id=4663,
                config_identity=_filter_hash(),
                height=100,
                block_hash=h100,
                parent_hash=h99,
            ),
        ),
    )
    result = canonicalize_events([_event(101, h101, h100)], tip_hash=h101, headers=headers, anchor=false_genesis)
    assert result.anchor_state == "unqualified"
    assert result.is_resolved is False

    malformed = _anchor(100, h100, evidence=("operator said this is safe",))
    result = canonicalize_events([_event(101, h101, h100)], tip_hash=h101, headers=headers, anchor=malformed)
    assert result.anchor_state == "unqualified"
    assert result.is_resolved is False

    # The anchor exists in evidence, but a disconnected selected tip never
    # reaches it. This must not be reported as resolved.
    disconnected = canonicalize_events(
        [_event(150, h150, None)],
        tip_hash=h150,
        headers=[*headers, BlockHeader(150, h150, None)],
        anchor=_anchor(100, h100),
    )
    assert disconnected.anchor_state == "unqualified"
    assert disconnected.is_resolved is False


def test_projection_only_orphans_competing_blocks_inside_proven_interval():
    h99, h100, h100_fork, h101, h102 = (_hash(number) for number in (199, 200, 201, 202, 203))
    events = [
        _event(99, h99, _hash(198)),
        _event(100, h100_fork, h99, 1),
        _event(101, h101, h100),
        _event(102, h102, h101),
    ]
    result = canonicalize_events(
        events,
        tip_hash=h101,
        headers=[BlockHeader(99, h99, _hash(198)), BlockHeader(100, h100, h99), BlockHeader(101, h101, h100)],
        anchor=_anchor(100, h100),
    )
    assert [event.block_hash for event in result.orphaned_events] == [h100_fork]
    assert [event.block_hash for event in result.unresolved_events] == [h99, h102]
    assert result.proven_height_range == (100, 101)


def test_bounded_projection_persists_scope_and_restart_distinctions(tmp_path: Path):
    h99, h100, h100_fork, h101, h102 = (_hash(number) for number in (299, 300, 301, 302, 303))
    source = _source()
    records = [
        _event(99, h99, _hash(298)),
        _event(100, h100_fork, h99, 1),
        _event(101, h101, h100),
        _event(102, h102, h101),
    ]
    store_path = tmp_path / "store"
    with RawBatchStore(store_path) as store:
        store.publish(records, source=source, partition_date="2026-09-14")
        store.persist_headers(
            [BlockHeader(99, h99, _hash(298)), BlockHeader(100, h100, h99), BlockHeader(101, h101, h100)]
        )
        store.save_ancestry_anchor(_anchor(100, h100))
        first = store.rebuild_canonical_projection(source=source, tip_hash=h101)
        assert first.is_resolved
    with RawBatchStore(store_path) as store:
        second = store.rebuild_canonical_projection(source=source, tip_hash=h101)
        states = {
            row["block_hash"]: row["canonical_status"]
            for row in store.list_canonical_projection(source)
        }
    assert second.proven_height_range == (100, 101)
    assert states[h100_fork] == "orphaned"
    assert states[h99] == "unresolved"
    assert states[h102] == "unresolved"


class _HeaderClient:
    def __init__(self, headers: dict[int, BlockHeader]) -> None:
        self.headers = headers

    def check_chain(self) -> int:
        return 4663

    def block_number(self) -> int:
        return max(self.headers)

    def block(self, block_number: int) -> dict[str, object]:
        header = self.headers[block_number]
        return {
            "number": hex(header.number),
            "hash": header.block_hash,
            "parentHash": header.parent_hash,
            "timestamp": hex(header.timestamp or 0),
        }

    def logs(self, *, address, from_block: int, to_block: int, max_range: int = 2000):
        return []

    def resolve_log_time(self, log, headers):
        return log


class _EvolvingClient(_HeaderClient):
    def __init__(self, headers: dict[int, BlockHeader], logs_by_block: dict[int, list[RpcLog]] | None = None) -> None:
        super().__init__(headers)
        self.logs_by_block = logs_by_block or {}

    def logs(self, *, address, from_block: int, to_block: int, max_range: int = 2000):
        return [
            log
            for block_number in range(from_block, to_block + 1)
            for log in self.logs_by_block.get(block_number, [])
        ]


def _rpc_log(block_number: int, block_hash: str, index: int = 0) -> RpcLog:
    return RpcLog(
        block_number=block_number,
        block_hash=block_hash,
        transaction_hash=_hash(10_000 + block_number + index),
        log_index=index,
        payload={"address": V4, "topics": [], "data": "0x"},
        block_timestamp=1_700_000_000 + block_number,
    )


def test_rejected_anchor_does_not_poison_capture_and_corrected_retry_succeeds(tmp_path: Path):
    root, tip = _hash(300), _hash(301)
    client = _HeaderClient({1: BlockHeader(1, root, None, 1_700_000_001), 2: BlockHeader(2, tip, root, 1_700_000_002)})
    store_path = tmp_path / "store"
    with RawBatchStore(store_path) as store:
        with pytest.raises(ValueError, match="configuration identity"):
            capture_to_store(
                client,
                store,
                addresses=[V4],
                from_block=1,
                to_block=2,
                run_id="bad-anchor",
                anchor=_anchor(1, root, config_identity="WRONG"),
            )
        source = _source()
        assert store.get_ancestry_anchor(source) is None
        assert store.get_canonical_checkpoint(source) is None

        manifest = capture_to_store(
            client,
            store,
            addresses=[V4],
            from_block=1,
            to_block=2,
            run_id="corrected-anchor",
            anchor=_anchor(1, root),
        )
        assert manifest.header_evidence["ancestry_anchor_state"] == "qualified"
        assert store.get_ancestry_anchor(source) is not None


def test_capture_and_backfill_share_genesis_qualification(tmp_path: Path):
    genesis, tip = _hash(400), _hash(401)
    headers = {0: BlockHeader(0, genesis, None, 1_700_000_000), 1: BlockHeader(1, tip, genesis, 1_700_000_001)}
    capture_path = tmp_path / "capture"
    backfill_path = tmp_path / "backfill"
    with RawBatchStore(capture_path) as store:
        captured = capture_to_store(
            _HeaderClient(headers), store, addresses=[V4], from_block=0, to_block=1, run_id="capture-genesis"
        )
    with RawBatchStore(backfill_path) as store:
        with BackfillCheckpointStore(tmp_path / "backfill-checkpoints.sqlite3") as checkpoints:
            backfilled = backfill_to_store(
                _HeaderClient(headers),
                store,
                addresses=[V4],
                start_block=0,
                target_block=1,
                run_id="backfill-genesis",
                checkpoint_store=checkpoints,
            )
    assert captured.header_evidence["ancestry_anchor_state"] == "qualified"
    assert backfilled.header_evidence["ancestry_anchor_state"] == "qualified"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chain_id", True),
        ("height", 100.9),
        ("source", None),
        ("config_identity", None),
        ("evidence", "x"),
        ("evidence", [None]),
        ("recorded_at", None),
    ],
)
def test_anchor_from_dict_rejects_coercive_or_malformed_json(field: str, value: object):
    valid = _anchor(100, _hash(500)).to_dict()
    valid[field] = value
    with pytest.raises(ValueError):
        AncestryAnchor.from_dict(valid)


def _rpc_handler(headers: dict[int, BlockHeader]):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            method = request["method"]
            if method == "eth_chainId":
                result: object = "0x1237"
            elif method == "eth_getBlockByNumber":
                block_number = int(request["params"][0], 16)
                header = headers.get(block_number)
                result = None if header is None else {
                    "number": hex(header.number),
                    "hash": header.block_hash,
                    "parentHash": header.parent_hash,
                    "timestamp": hex(header.timestamp or 0),
                }
            else:
                result = None
            payload = json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def test_qualify_anchor_cli_performs_two_rpc_identity_checks(tmp_path: Path):
    config_path = ROOT / "configs/sources/robinhood-chain-v0.1.json"
    block_hash = _hash(600)
    header = BlockHeader(600, block_hash, _hash(599), 1_700_000_600)
    mismatch = BlockHeader(600, _hash(601), _hash(599), 1_700_000_600)
    servers: list[ThreadingHTTPServer] = []
    threads: list[threading.Thread] = []
    try:
        for fixture_headers in ({600: header}, {600: header}, {600: mismatch}):
            server = ThreadingHTTPServer(("127.0.0.1", 0), _rpc_handler(fixture_headers))
            server.daemon_threads = True
            servers.append(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
    except OSError as exc:
        for server in servers:
            server.shutdown()
            server.server_close()
        pytest.skip(f"sandbox disallows loopback fixture servers: {exc}")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    primary_url = f"http://127.0.0.1:{servers[0].server_port}/rpc/CANARY?api_key=CANARY"
    secondary_url = f"http://127.0.0.1:{servers[1].server_port}/archive/CANARY?token=CANARY"
    mismatch_url = f"http://127.0.0.1:{servers[2].server_port}/mirror/CANARY?secret=CANARY"
    config["chain"]["rpc_url"] = primary_url
    fixture_config = tmp_path / "source.json"
    fixture_config.write_text(json.dumps(config), encoding="utf-8")
    store_path = tmp_path / "store"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    command = [
        sys.executable, "-m", "willfly.cli", "qualify-anchor",
        "--config", str(fixture_config), "--height", "600", "--block-hash", block_hash,
        "--independent-rpc-url", secondary_url, "--address", V4,
        "--recorded-at", "2026-09-14T00:00:00Z", "--store-dir", str(store_path),
    ]
    try:
        completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stderr + completed.stdout
        assert "CANARY" not in completed.stdout
        result = json.loads(completed.stdout)
        assert result["status"] == "qualified"
        assert result["anchor_state"] == "qualified"
        with RawBatchStore(store_path) as store:
            anchor = store.get_ancestry_anchor(result["source"])
            assert anchor is not None
            assert anchor.qualification == "independent_header_cross_check"
            assert store.get_header(block_hash) is not None
            evidence = json.loads(anchor.evidence[0].split("willfly.anchor-evidence.v1:", 1)[1])
            assert evidence["verification"] == "performed_rpc_cross_check"
            assert evidence["read_methods"] == ["eth_chainId", "eth_getBlockByNumber"]
            assert "CANARY" not in json.dumps(anchor.to_dict())

        rejected_command = list(command)
        endpoint_index = rejected_command.index("--independent-rpc-url") + 1
        rejected_command[endpoint_index] = mismatch_url
        rejected = subprocess.run(rejected_command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False)
        assert rejected.returncode == 2
        with RawBatchStore(store_path) as store:
            assert store.get_ancestry_anchor(result["source"]) is not None
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)


def test_backfill_selects_fresh_tip_after_replacement(tmp_path: Path):
    root, old_tip, new_tip = _hash(700), _hash(701), _hash(702)
    old_client = _EvolvingClient(
        {0: BlockHeader(0, root, None, 1_700_000_000), 1: BlockHeader(1, old_tip, root, 1_700_000_001)},
        {1: [_rpc_log(1, old_tip)]},
    )
    new_client = _EvolvingClient(
        {0: BlockHeader(0, root, None, 1_700_000_000), 1: BlockHeader(1, new_tip, root, 1_700_000_001)},
        {1: [_rpc_log(1, new_tip, 1)]},
    )
    store_path = tmp_path / "store"
    with RawBatchStore(store_path) as store:
        with BackfillCheckpointStore(tmp_path / "old-checkpoints.sqlite3") as checkpoints:
            first = backfill_to_store(
                old_client, store, addresses=[V4], start_block=0, target_block=1,
                run_id="old-tip", checkpoint_store=checkpoints,
            )
        with BackfillCheckpointStore(tmp_path / "replacement-checkpoints.sqlite3") as checkpoints:
            second = backfill_to_store(
                new_client, store, addresses=[V4], start_block=0, target_block=1,
                run_id="new-tip", checkpoint_store=checkpoints,
            )
        statuses = {row["block_hash"]: row["canonical_status"] for row in store.list_canonical_projection(second.checkpoint_source)}
    assert first.header_evidence["canonical_tip_hash"] == old_tip
    assert second.header_evidence["canonical_tip_hash"] == new_tip
    assert second.header_evidence["header_count"] == 2
    assert statuses[old_tip] == "orphaned"
    assert statuses[new_tip] == "canonical"


def test_backfill_noop_resume_revalidates_tip_and_reports_unavailable(tmp_path: Path):
    root, old_tip, new_tip = _hash(710), _hash(711), _hash(712)
    store_path = tmp_path / "store"
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    old_client = _EvolvingClient(
        {0: BlockHeader(0, root, None, 1_700_000_000), 1: BlockHeader(1, old_tip, root, 1_700_000_001)},
        {1: [_rpc_log(1, old_tip)]},
    )
    new_client = _EvolvingClient(
        {0: BlockHeader(0, root, None, 1_700_000_000), 1: BlockHeader(1, new_tip, root, 1_700_000_001)},
        {1: [_rpc_log(1, new_tip, 1)]},
    )
    with RawBatchStore(store_path) as store:
        with BackfillCheckpointStore(checkpoint_path) as checkpoints:
            backfill_to_store(old_client, store, addresses=[V4], start_block=0, target_block=1, run_id="resume-a", checkpoint_store=checkpoints)
            resumed = backfill_to_store(new_client, store, addresses=[V4], start_block=0, target_block=1, run_id="resume-b", checkpoint_store=checkpoints)
            unchanged = backfill_to_store(new_client, store, addresses=[V4], start_block=0, target_block=1, run_id="resume-b-unchanged", checkpoint_store=checkpoints)
    assert resumed.header_evidence["header_count"] == 2
    assert resumed.header_evidence["canonical_tip_hash"] == new_tip
    assert resumed.header_evidence["coverage_state"] == "repaired"
    assert resumed.acknowledged_range == (0, 1)
    assert resumed.event_count == 1
    assert unchanged.header_evidence["header_count"] == 1
    assert unchanged.header_evidence["coverage_state"] == "complete"
    assert unchanged.acknowledged_range == (0, 1)
    with RawBatchStore(store_path) as store:
        source = resumed.checkpoint_source
        events = store.events_for_source(source)
        statuses = {row["block_hash"]: row["canonical_status"] for row in store.list_canonical_projection(source)}
    assert {event.block_hash for event in events} == {old_tip, new_tip}
    assert statuses[old_tip] == "orphaned"
    assert statuses[new_tip] == "canonical"

    class UnavailableClient(_EvolvingClient):
        def block(self, block_number: int):
            raise TimeoutError("tip unavailable")

    with RawBatchStore(store_path) as store:
        with BackfillCheckpointStore(checkpoint_path) as checkpoints:
            unavailable = backfill_to_store(UnavailableClient({}), store, addresses=[V4], start_block=0, target_block=1, run_id="resume-c", checkpoint_store=checkpoints)
    assert unavailable.header_evidence["header_count"] == 0
    assert unavailable.header_evidence["canonical_tip_hash"] is None
    assert unavailable.header_evidence["ancestry_anchor_state"] == "unavailable"
    assert unavailable.header_evidence["coverage_state"] == "needs_repair"
    assert unavailable.errors
    with RawBatchStore(store_path) as store:
        assert store.get_canonical_checkpoint(unavailable.checkpoint_source)["state"] == "needs_repair"


def test_replacement_replay_failure_leaves_checkpoint_needing_repair(tmp_path: Path):
    root, old_tip, new_tip = _hash(715), _hash(716), _hash(717)
    store_path = tmp_path / "store"
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    old_client = _EvolvingClient(
        {0: BlockHeader(0, root, None, 1_700_000_000), 1: BlockHeader(1, old_tip, root, 1_700_000_001)},
        {1: [_rpc_log(1, old_tip)]},
    )
    with RawBatchStore(store_path) as store:
        with BackfillCheckpointStore(checkpoint_path) as checkpoints:
            backfill_to_store(
                old_client, store, addresses=[V4], start_block=0, target_block=1,
                run_id="replay-failure-a", checkpoint_store=checkpoints,
            )

    class FailingReplacementClient(_EvolvingClient):
        def logs(self, *, address, from_block: int, to_block: int, max_range: int = 2000):
            raise RuntimeError("replacement provider failed")

    replacement = FailingReplacementClient(
        {0: BlockHeader(0, root, None, 1_700_000_000), 1: BlockHeader(1, new_tip, root, 1_700_000_001)},
        {1: [_rpc_log(1, new_tip, 1)]},
    )
    with RawBatchStore(store_path) as store:
        with BackfillCheckpointStore(checkpoint_path) as checkpoints:
            with pytest.raises(RuntimeError, match="replacement provider failed"):
                backfill_to_store(
                    replacement, store, addresses=[V4], start_block=0, target_block=1,
                    run_id="replay-failure-b", checkpoint_store=checkpoints,
                )
        checkpoint = store.get_canonical_checkpoint(checkpoint_source("backfill", 4663, _filter_hash()))
    assert checkpoint is not None
    assert checkpoint["state"] == "needs_repair"
    assert checkpoint["repair_reason"] == "bounded lineage replay failed; coverage remains incomplete"


def test_partial_backfill_replays_replacement_after_cursor_boundary(tmp_path: Path):
    root, old_tip, new_tip, quiet = (_hash(number) for number in (730, 731, 732, 733))
    store_path = tmp_path / "store"
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    old_client = _EvolvingClient(
        {
            0: BlockHeader(0, root, None, 1_700_000_000),
            1: BlockHeader(1, old_tip, root, 1_700_000_001),
            2: BlockHeader(2, quiet, old_tip, 1_700_000_002),
        },
        {1: [_rpc_log(1, old_tip)]},
    )

    class InterruptedClient(_EvolvingClient):
        def logs(self, *, address, from_block: int, to_block: int, max_range: int = 2000):
            if from_block == 2:
                raise RuntimeError("interrupted before partial page")
            return super().logs(address=address, from_block=from_block, to_block=to_block, max_range=max_range)

    with RawBatchStore(store_path) as store:
        with BackfillCheckpointStore(checkpoint_path) as checkpoints:
            with pytest.raises(RuntimeError, match="interrupted"):
                backfill_to_store(
                    InterruptedClient(old_client.headers, old_client.logs_by_block),
                    store,
                    addresses=[V4], start_block=0, target_block=2, run_id="partial-a",
                    page_size=1, checkpoint_store=checkpoints,
                )

    replacement = _EvolvingClient(
        {
            0: BlockHeader(0, root, None, 1_700_000_000),
            1: BlockHeader(1, new_tip, root, 1_700_000_001),
            2: BlockHeader(2, quiet, new_tip, 1_700_000_002),
        },
        {1: [_rpc_log(1, new_tip, 1)]},
    )
    with RawBatchStore(store_path) as store:
        with BackfillCheckpointStore(checkpoint_path) as checkpoints:
            manifest = backfill_to_store(
                replacement, store, addresses=[V4], start_block=0, target_block=2,
                run_id="partial-b", page_size=1, checkpoint_store=checkpoints,
            )
        statuses = {row["block_hash"]: row["canonical_status"] for row in store.list_canonical_projection(manifest.checkpoint_source)}
        events = store.events_for_source(manifest.checkpoint_source)
    assert manifest.header_evidence["canonical_tip_hash"] == quiet
    assert manifest.acknowledged_range == (0, 2)
    assert manifest.header_evidence["coverage_state"] == "repaired"
    assert {event.block_hash for event in events} == {old_tip, new_tip}
    assert statuses[old_tip] == "orphaned"
    assert statuses[new_tip] == "canonical"


def test_requalification_preserves_old_boundary_crossing_namespace(tmp_path: Path):
    old_source = _source()
    new_source = checkpoint_source("capture-requal-v2", 4663, _filter_hash())
    old_anchor_hash, fork_hash, fork_tip = _hash(720), _hash(721), _hash(722)
    headers = [
        BlockHeader(10, old_anchor_hash, _hash(719)),
        BlockHeader(10, fork_hash, _hash(719)),
        BlockHeader(11, fork_tip, fork_hash),
    ]
    with RawBatchStore(tmp_path / "store") as store:
        old_anchor = _anchor(10, old_anchor_hash)
        store.persist_headers(headers)
        store.save_ancestry_anchor(old_anchor)
        store.publish([_event(11, fork_tip, fork_hash)], source=old_source, partition_date="2026-09-14")
        old_result = store.rebuild_canonical_projection(source=old_source, tip_hash=fork_tip)
        assert old_result.anchor_state == "boundary_crossed"
        new_anchor = _anchor(10, fork_hash, source=new_source)
        store.save_requalified_ancestry_anchor(
            new_anchor,
            supersedes_source=old_source,
            reason="observed fork crosses the old bounded anchor boundary",
        )
        store.publish([_event(11, fork_tip, fork_hash, index=1)], source=new_source, partition_date="2026-09-14")
        new_result = store.rebuild_canonical_projection(source=new_source, tip_hash=fork_tip)
        link = store.get_anchor_supersession(old_source)
        old_checkpoint = store.get_canonical_checkpoint(old_source)
    assert new_result.is_resolved
    assert new_result.anchor_state == "qualified"
    assert link is not None and link["successor_source"] == new_source
    assert old_checkpoint["anchor_state"] == "boundary_crossed"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:CANARY@example.com/rpc/CANARY?api_key=CANARY",
        "https://example.com/path/CANARY?token=CANARY",
        "https://public.example/rpc",
    ],
)
def test_exportable_endpoint_and_error_provenance_redact_credentials(endpoint: str):
    safe = redact_endpoint(endpoint)
    assert "CANARY" not in safe
    assert "/rpc" not in safe
    assert "?" not in safe
    error = redact_error(RuntimeError(f"provider failed at {endpoint}"))
    assert error is not None
    assert "CANARY" not in error


def test_run_manifest_persists_redacted_provider_endpoint(tmp_path: Path):
    client = _HeaderClient({0: BlockHeader(0, _hash(800), None, 1_700_000_000)})
    with RawBatchStore(tmp_path / "store") as store:
        manifest = capture_to_store(
            client,
            store,
            addresses=[V4],
            from_block=0,
            to_block=0,
            run_id="redacted-manifest",
            provider_endpoint="https://user:CANARY@example.com/path/CANARY?api_key=CANARY",
        )
    assert manifest.provider_endpoint == "https://example.com"
    stored = json.loads((tmp_path / "store" / "runs" / "redacted-manifest.json").read_text(encoding="utf-8"))
    assert stored["provider_endpoint"] == "https://example.com"
    assert "CANARY" not in json.dumps(stored)

    with RawBatchStore(tmp_path / "backfill-store") as store:
        with BackfillCheckpointStore(tmp_path / "backfill-checkpoints.sqlite3") as checkpoints:
            backfill_manifest = backfill_to_store(
                _HeaderClient({0: BlockHeader(0, _hash(801), None, 1_700_000_000)}),
                store,
                addresses=[V4],
                start_block=0,
                target_block=0,
                run_id="redacted-backfill-manifest",
                provider_endpoint="https://user:CANARY@example.com/path/CANARY?api_key=CANARY",
                checkpoint_store=checkpoints,
            )
    assert backfill_manifest.provider_endpoint == "https://example.com"


def test_nested_anchor_evidence_requires_strict_types_and_supported_resolution():
    anchor = _anchor(1, _hash(810))
    header = BlockHeader(1, _hash(810), _hash(809))
    original = json.loads(anchor.evidence[0].split("willfly.anchor-evidence.v1:", 1)[1])
    cases = []
    for path, value in ((["height"], True), (["height"], 1.5), (["chain_id"], True)):
        record = json.loads(json.dumps(original))
        record[path[0]] = value
        cases.append(record)
    for nested, value in (("primary_header", {"number": True, "hash": _hash(810)}),
                          ("external_header", {"number": 1, "hash": _hash(810), "parent_hash": True}),
                          ("primary_header", [1, _hash(810)])):
        record = json.loads(json.dumps(original))
        record[nested] = value
        cases.append(record)
    for record in cases:
        malformed = replace(
            anchor,
            evidence=(anchor_evidence_record(record.pop("kind"), **record),),
        )
        result = canonicalize_events(
            [_event(1, _hash(810), _hash(809))],
            tip_hash=_hash(810),
            headers=[header],
            anchor=malformed,
        )
        assert result.anchor_state == "unqualified"
        assert result.is_resolved is False

    valid = canonicalize_events(
        [_event(1, _hash(810), _hash(809))],
        tip_hash=_hash(810),
        headers=[header],
        anchor=anchor,
    )
    assert valid.is_resolved
    assert replace(valid, anchor_state="unrecognized").is_resolved is False
    assert replace(valid, proven_height_range=None).is_resolved is False
