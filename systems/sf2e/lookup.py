#!/usr/bin/env python3
"""Look up records in the locally generated SF2e Foundry dataset."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from systems.paizo2e.lookup import find_records, format_record, load_dataset


DATA_PATH = Path(__file__).with_name("data") / "sf2e_foundry.json"
BUILD_COMMAND = "python3 systems/sf2e/build_foundry.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category", help="dataset category, or 'any'")
    parser.add_argument("query", help="record name to find")
    parser.add_argument("--all", action="store_true", help="show all matching records")
    args = parser.parse_args(argv)

    if not DATA_PATH.is_file():
        print(f"Dataset missing. Build it with: {BUILD_COMMAND}")
        return 1

    dataset = load_dataset(DATA_PATH)
    limit = None if args.all else 1
    records = find_records(dataset, args.category, args.query, limit=limit)
    if not records:
        print(f"No matches found for {args.query!r} in {args.category!r}.")
        return 0

    source = dataset.get("_meta", {}).get("source", {})
    source_sha = source.get("sha", "unknown") if isinstance(source, dict) else "unknown"
    print("\n\n".join(format_record(record, str(source_sha)) for record in records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
