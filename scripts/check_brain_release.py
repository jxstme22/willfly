"""Print the current brain-product capability matrix without network calls."""

from __future__ import annotations

import json
from pathlib import Path

from willfly.release.check import build_brain_release_report


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(build_brain_release_report(root).to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
