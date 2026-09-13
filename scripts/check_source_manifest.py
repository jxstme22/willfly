"""Check the pinned source declarations without contacting providers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from willfly.adapters.source_manifest import validate_source_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path, default=Path("configs/sources/robinhood-chain-v0.1.json"), nargs="?")
    args = parser.parse_args()
    print(json.dumps(validate_source_manifest(args.manifest), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
