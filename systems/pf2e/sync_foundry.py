"""Check or synchronize the local PF2e Foundry dataset."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from systems.paizo2e.source import needs_rebuild, resolve_ref
from systems.pf2e.build_foundry import OUTPUT_PATH, SPEC, main as build_main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report whether a rebuild is needed")
    args = parser.parse_args()
    try:
        stale = needs_rebuild(OUTPUT_PATH, SPEC, resolve_ref(SPEC))
    except Exception:
        if args.check:
            print("Unverifiable.")
            return
        raise
    if args.check:
        print("Stale." if stale else "Up to date.")
    elif stale:
        build_main()


if __name__ == "__main__":
    main()
