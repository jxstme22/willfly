import pytest
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from willfly.api.server import ReadOnlyStore, _route, create_server
from willfly.domain import Launch


TOKEN = "0x1111111111111111111111111111111111111111"


def _launch(state: str, token: str = TOKEN) -> Launch:
    return Launch(4663, token, None, None, ("launch:1",), None, None, "2026-09-13T00:00:00Z", "unknown", (), state)


def test_read_only_api_paginates_and_rejects_unknown_routes():
    store = ReadOnlyStore(
        launches=(_launch("active"), _launch("non_graduate", "0x" + "2" * 40)),
        quality_state="degraded",
    )
    page, status = _route(store, "/launches?limit=1")
    assert status == 200
    assert page["total"] == 2
    assert page["next_cursor"] == "1"
    next_page, status = _route(store, "/launches?cursor=1&limit=1")
    assert status == 200
    assert len(next_page["items"]) == 1
    health, status = _route(store, "/health")
    assert status == 200
    assert health["quality_state"] == "degraded"
    missing, status = _route(store, "/trade")
    assert status == 404
    assert missing["status"] == "error"
    with pytest.raises(ValueError, match="EVM address"):
        _route(store, "/tokens/not-an-address/timeline")


def test_read_only_api_search_sort_and_filter_are_applied_before_pagination():
    store = ReadOnlyStore(
        launches=(
            _launch("graduated", "0x" + "2" * 40),
            _launch("active", "0x" + "1" * 40),
            _launch("unknown", "0x" + "3" * 40),
        ),
        quality_state="stale",
    )
    page, status = _route(store, "/launches?q=0x&sort=token&direction=desc&limit=2")
    assert status == 200
    assert [item["token"] for item in page["items"]] == ["0x" + "3" * 40, "0x" + "2" * 40]
    assert page["total"] == 3
    assert page["next_cursor"] == "2"
    filtered, status = _route(store, "/launches?lifecycle=active&search=0x111")
    assert status == 200
    assert filtered["total"] == 1
    with pytest.raises(ValueError, match="unsupported sort"):
        _route(store, "/launches?sort=made_up")


def test_evidence_reference_with_slash_round_trips_through_route():
    store = ReadOnlyStore(evidence={"source/raw/1": {"kind": "raw_event", "status": "canonical"}})
    payload, status = _route(store, "/evidence/source%2Fraw%2F1")
    assert status == 200
    assert payload["status"] == "canonical"


def test_signal_as_of_time_is_used_when_projection_is_empty():
    store = ReadOnlyStore(signal_as_of_time="2026-09-14T06:10:00Z")
    payload, status = _route(store, "/signals")
    assert status == 200
    assert payload["as_of_time"] == "2026-09-14T06:10:00Z"
    health, status = _route(store, "/health")
    assert status == 200
    assert health["details"]["signal_monitor_state"] == "waiting_no_published_signal"


def test_http_surface_rejects_post_as_read_only():
    try:
        server = create_server(store=ReadOnlyStore(), host="127.0.0.1", port=0)
    except PermissionError:
        pytest.skip("loopback socket binding is unavailable in this sandbox")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(f"http://127.0.0.1:{server.server_port}/launches", method="POST")
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)  # nosec B310 - local test server
        assert error.value.code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_surface_refreshes_published_training_snapshot():
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return {"training_state": {"status": f"refresh-{calls}"}, "signal_provenance": None}

    try:
        server = create_server(store=ReadOnlyStore(signal_loader=loader), host="127.0.0.1", port=0)
    except PermissionError:
        pytest.skip("loopback socket binding is unavailable in this sandbox")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/training", timeout=2) as response:
            first = response.read().decode()
        with urlopen(f"http://127.0.0.1:{server.server_port}/training", timeout=2) as response:
            second = response.read().decode()
        assert '"status": "refresh-1"' in first
        assert '"status": "refresh-2"' in second
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
