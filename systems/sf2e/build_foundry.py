"""Build the local SF2e Foundry dataset."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from systems.paizo2e.source import SourceSpec, build_dataset


SPEC = SourceSpec("sf2e", "packs/sf2e")
OUTPUT_PATH = Path(__file__).with_name("data") / "sf2e_foundry.json"


def main() -> bool:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild even when current")
    args = parser.parse_args()
    return build_dataset(SPEC, OUTPUT_PATH, force=args.force)


if __name__ == "__main__":
    main()
