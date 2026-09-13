# MaleCNS v1.0 verification checkpoint

Date: 14 September 2026

Status: `SUBSET_VERIFIED_WHOLE_RELEASE_GATE_OPEN`

The user-selected source is the official MaleCNS v1.0 release from HHMI
Janelia, Cambridge, MRC LMB and Google Research. The Google overview, Janelia
project page and official download page are provenance references; the CC BY
4.0 deed is the license reference.

## Release and artifact checks

| Artifact | Bytes | SHA-256 | Result |
|---|---:|---|---|
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 1,051,241,946 | `e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1` | verified |
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 14,483,314 | `2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2` | verified |

The GCS transport probe returned `application/octet-stream`, the expected
content lengths, stable ETags and provider MD5/CRC32C headers. SHA-256 was
computed locally before the loader opened either artifact. The connectivity
table contains 151,856,684 rows with exactly `body_pre:int64`,
`body_post:int64` and `weight:int64`. The annotation table contains 211,577
rows and the required `bodyId`, `type`, `status` and `somaSide` columns.

`body_pre` is treated as presynaptic and `body_post` as postsynaptic. The
published table has no measured sign column; the loader therefore uses an
explicit positive sign assumption and records that assumption in its report.
Raw integer strengths use the frozen
`log1p(raw_weight)/log1p(10000)` transform. This is a model preprocessing
choice, not a claim about synaptic physiology.

## Actual graph smoke run

Command:

```text
.venv/bin/python scripts/verify_malecns_release.py --max-edges 20000
```

Result: the first 20,000 release-order edges produced 10,868 nodes, preserved
directed `source_to_target` graph orientation, and drove a three-step
`SparseReservoir` episode. The resulting graph hash was
`eb5dfdda9aa560520e947bd6311304056d2263b97668c5272cd6262c631dd6e9`; all three
states contained nonzero values. This is actual MaleCNS data driving recurrent
computation, not a synthetic graph.

The smoke graph is deliberately a bounded subset. It is not whole-CNS
coverage, not a pretrained executable financial model, and not evidence of
biological memory, trading skill or financial advantage. Full-release graph
execution, resource benchmarking and model comparison remain separate gates.

## Provenance

- [Google Research overview](https://blog.google/innovation-and-ai/technology/research/male-fruit-fly-brain-map/)
- [HHMI Janelia Male CNS project](https://www.janelia.org/project-team/flyem/male-cns-connectome)
- [Official MaleCNS download page](https://male-cns.janelia.org/download/)
- [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/)

The executable boundary is in
`src/willfly/models/connectome/ingest.py`; raw artifacts remain under ignored
`data/connectome/` and are not part of the repository checkpoint.
