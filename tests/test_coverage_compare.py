from types import SimpleNamespace

from willfly import cli
from willfly.domain import RawEvent


def _event() -> RawEvent:
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": "fixture",
            "source_schema_version": "rpc-log.v0.1",
            "block_number": 10,
            "block_hash": "0x" + "1" * 64,
            "parent_hash": "0x" + "0" * 64,
            "transaction_hash": "0x" + "2" * 64,
            "log_index": 0,
            "event_time": "2026-09-14T06:00:00+00:00",
            "received_time": "2026-09-14T06:00:01+00:00",
            "payload": {"topics": [], "data": "0x"},
            "ingestion_run": "fixture",
            "canonical_status": "provisional",
        }
    )


def test_coverage_compare_checks_event_sets_beyond_anchor_identity(monkeypatch, tmp_path):
    event = _event()
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "_capture_context",
        lambda *_args: {
            "endpoint": "https://primary.example",
            "expected_chain": 4663,
            "addresses": ("0x" + "3" * 40,),
            "config_hash": "config-hash",
        },
    )
    monkeypatch.setattr(cli, "ReadOnlyRpcClient", lambda endpoint, expected_chain_id, **_kwargs: endpoint)
    monkeypatch.setattr(
        cli,
        "capture_once",
        lambda client, **kwargs: SimpleNamespace(to_block=kwargs["to_block"], events=(event,)),
    )
    result = cli._coverage_compare(
        config_path=tmp_path / "config.json",
        from_block=10,
        to_block=10,
        independent_rpc_url="https://independent.example",
        addresses=[],
        progress_db=tmp_path / "coverage.sqlite3",
    )
    assert result["status"] == "pass"
    assert result["range_complete"] is True
    assert result["report"]["matched_count"] == 1
    assert result["report"]["provider_independent"] is True
    assert result["signing"] is False and result["broadcast"] is False


def test_coverage_compare_reports_provider_timeout_as_degraded(monkeypatch, tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "_capture_context",
        lambda *_args: {
            "endpoint": "https://primary.example",
            "expected_chain": 4663,
            "addresses": ("0x" + "3" * 40,),
            "config_hash": "config-hash",
        },
    )
    monkeypatch.setattr(cli, "ReadOnlyRpcClient", lambda endpoint, expected_chain_id, **_kwargs: endpoint)
    monkeypatch.setattr(cli, "capture_once", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("budget")))
    result = cli._coverage_compare(
        config_path=tmp_path / "config.json",
        from_block=10,
        to_block=10,
        independent_rpc_url="https://independent.example",
        addresses=[],
        rpc_timeout_seconds=1,
        max_rpc_retries=0,
        max_runtime_seconds=1,
        progress_db=tmp_path / "coverage.sqlite3",
    )
    assert result["status"] == "degraded"
    assert "comparison" in result["provider_errors"]
    assert result["range_complete"] is False


def test_coverage_compare_persists_completed_chunks_for_resume(monkeypatch, tmp_path):
    event = _event()
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "_capture_context",
        lambda *_args: {
            "endpoint": "https://primary.example",
            "expected_chain": 4663,
            "addresses": ("0x" + "3" * 40,),
            "config_hash": "config-hash",
        },
    )
    monkeypatch.setattr(cli, "ReadOnlyRpcClient", lambda endpoint, expected_chain_id, **_kwargs: endpoint)
    calls = 0

    def partial_capture(_client, **kwargs):
        nonlocal calls
        calls += 1
        if kwargs["from_block"] == 11 and calls == 3:
            raise TimeoutError("header budget")
        chunk_event = RawEvent.from_dict(
            {
                **event.to_dict(),
                "block_number": kwargs["from_block"],
                "block_hash": "0x" + f"{kwargs['from_block']:064x}",
            }
        )
        return SimpleNamespace(to_block=kwargs["to_block"], events=(chunk_event,))

    monkeypatch.setattr(cli, "capture_once", partial_capture)
    progress = tmp_path / "coverage.sqlite3"
    first = cli._coverage_compare(
        config_path=tmp_path / "config.json",
        from_block=10,
        to_block=11,
        independent_rpc_url="https://independent.example",
        addresses=[],
        chunk_size=1,
        max_runtime_seconds=10,
        progress_db=progress,
    )
    assert first["status"] == "degraded"
    assert first["completed_chunks"] == 1

    monkeypatch.setattr(
        cli,
        "capture_once",
        lambda _client, **kwargs: SimpleNamespace(
            to_block=kwargs["to_block"],
            events=(
                RawEvent.from_dict(
                    {
                        **event.to_dict(),
                        "block_number": kwargs["from_block"],
                        "block_hash": "0x" + f"{kwargs['from_block']:064x}",
                    }
                ),
            ),
        ),
    )
    second = cli._coverage_compare(
        config_path=tmp_path / "config.json",
        from_block=10,
        to_block=11,
        independent_rpc_url="https://independent.example",
        addresses=[],
        chunk_size=1,
        max_runtime_seconds=10,
        progress_db=progress,
    )
    assert second["status"] == "pass"
    assert second["completed_chunks"] == 2
