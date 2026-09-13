"""Verify and smoke-run the user-selected MaleCNS v1.0 release.

This command requires local artifacts supplied from the official download URLs.
It never treats the dataset as a pretrained financial model and never writes
the downloaded data into Git.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from willfly.models.connectome import (
    ConnectomeManifest,
    load_connectome_graph,
    validate_connectome_annotations,
)
from willfly.models.reservoir import SparseReservoir


def verify(manifest_path: Path, data_root: Path, max_edges: int) -> dict[str, object]:
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = ConnectomeManifest.from_dict(manifest_payload)
    annotation = manifest_payload["annotation_companion"]
    annotation_path = data_root / Path(annotation["source_url"]).name
    annotation_report = validate_connectome_annotations(
        annotation_path,
        expected_sha256=annotation["source_sha256"],
        expected_bytes=annotation["artifact_bytes"],
    )
    graph_path = data_root / Path(manifest.source_url).name
    graph, graph_report = load_connectome_graph(graph_path, manifest, max_edges=max_edges)
    reservoir = SparseReservoir(graph, decay=0.9, input_scale=1.0)
    states = reservoir.run_episode(
        "malecns-v1.0-smoke",
        [{graph.nodes[0]: 1.0}, {graph.nodes[0]: 0.0}, {graph.nodes[0]: 0.5}],
    )
    return {
        "release_id": manifest.release_id,
        "dataset_id": manifest.dataset_id,
        "annotation": annotation_report,
        "graph": graph_report,
        "reservoir_smoke": {
            "graph_hash": reservoir.graph_hash,
            "steps": len(states),
            "nonzero_state_values": sum(any(value != 0.0 for value in state.values) for state in states),
            "input_node": graph.nodes[0],
        },
        "model_boundary": "actual MaleCNS graph subset drives the smoke reservoir; no pretrained financial model or whole-CNS claim",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("configs/connectome/male-cns-v1.0.json"))
    parser.add_argument("--data-root", type=Path, default=Path("data/connectome/male-cns-v1.0"))
    parser.add_argument("--max-edges", type=int, default=20_000)
    args = parser.parse_args()
    print(json.dumps(verify(args.manifest, args.data_root, args.max_edges), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
