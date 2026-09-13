import json

import pytest

from willfly.adapters.source_manifest import validate_source_manifest


def test_pinned_source_manifest_validates_abi_hashes_and_open_gates():
    report = validate_source_manifest("configs/sources/robinhood-chain-v0.1.json")
    assert report["chain_id"] == 4663
    assert report["status"] == "ready_with_open_gates"
    assert report["abi_reports"]["uniswap_v4"]["sha256"]
    assert len(report["abi_reports"]["pons_v2"]["event_families"]) == 4
    assert report["open_gates"]


def test_source_manifest_rejects_credentialed_endpoint_and_bad_abi_hash(tmp_path):
    payload = json.loads(open("configs/sources/robinhood-chain-v0.1.json", encoding="utf-8").read())
    payload["chain"]["rpc_url"] = "https://user:secret@example.invalid/rpc"
    path = tmp_path / "source.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="credential-free"):
        validate_source_manifest(path)
    payload["chain"]["rpc_url"] = "https://rpc.mainnet.chain.robinhood.com"
    payload["protocols"]["uniswap_v4"]["abi_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="ABI hash"):
        validate_source_manifest(path)
