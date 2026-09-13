from dataclasses import dataclass

import pytest

from willfly.storage.export import ExportUnavailable, export_records, verify_export


@dataclass(frozen=True)
class Row:
    id: int
    amount: str


def test_export_requires_optional_arrow_runtime(tmp_path):
    try:
        manifest = export_records(
            [Row(1, "90071992547409931234567890")],
            output_dir=tmp_path,
            dataset_name="timeline",
        )
    except ExportUnavailable:
        pytest.skip("pyarrow is an optional export dependency")
    assert manifest.row_count == 1
    rows = verify_export(tmp_path, "timeline")
    assert rows[0]["amount"] == "90071992547409931234567890"
    assert rows[0]["id"] == 1
