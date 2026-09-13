import pytest

from willfly.api.server import ReadOnlyStore, _route
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
