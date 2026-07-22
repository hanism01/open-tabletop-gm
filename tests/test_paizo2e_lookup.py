"""Tests for shared PF2e/SF2e lookup commands."""

from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import sys

from systems.paizo2e.lookup import find_records, format_record


class Paizo2eLookupTests(unittest.TestCase):
    def test_lookup_prefers_exact_name_and_never_crosses_system_dataset(self):
        pf = {"actions": [{"name": "Stride", "index": "stride"}]}
        sf = {"actions": [{"name": "Boost", "index": "boost"}]}

        self.assertEqual(find_records(pf, "actions", "stride")[0]["name"], "Stride")
        self.assertEqual(find_records(sf, "actions", "stride"), [])

    def test_lookup_returns_exact_match_before_sorted_substring_matches(self):
        dataset = {
            "actions": [
                {"name": "Strider", "source_path": "packs/actions/z.yml"},
                {"name": "Stride", "source_path": "packs/actions/b.yml"},
                {"name": "Stride Away", "source_path": "packs/actions/a.yml"},
                {"name": "Stride", "source_path": "packs/actions/a.yml"},
            ]
        }

        found = find_records(dataset, "actions", "stride", limit=4)

        self.assertEqual(
            [(record["name"], record["source_path"]) for record in found],
            [
                ("Stride", "packs/actions/a.yml"),
                ("Stride", "packs/actions/b.yml"),
                ("Stride Away", "packs/actions/a.yml"),
                ("Strider", "packs/actions/z.yml"),
            ],
        )

    def test_any_category_searches_only_the_given_dataset(self):
        dataset = {
            "actions": [{"name": "Stride", "source_path": "packs/actions/stride.yml"}],
            "spells": [{"name": "Longstrider", "source_path": "packs/spells/longstrider.yml"}],
        }

        found = find_records(dataset, "any", "stride", limit=2)

        self.assertEqual([record["name"] for record in found], ["Stride", "Longstrider"])

    def test_singular_category_aliases_match_generated_plural_categories(self):
        dataset = {"spells": [{"name": "Fireball", "source_path": "packs/spells/fireball.yml"}]}

        found = find_records(dataset, "spell", "fireball")

        self.assertEqual([record["name"] for record in found], ["Fireball"])

    def test_format_record_includes_play_relevant_fields_and_provenance(self):
        text = format_record(
            {
                "name": "Stride",
                "category": "actions",
                "traits": ["move"],
                "level": 1,
                "description": "Move up to your Speed.",
                "source_path": "packs/pf2e/actions/stride.yml",
            },
            "1234567890abcdef",
        )

        self.assertIn("Stride", text)
        self.assertIn("Category: actions", text)
        self.assertIn("Traits: move", text)
        self.assertIn("Level: 1", text)
        self.assertIn("Move up to your Speed.", text)
        self.assertIn("packs/pf2e/actions/stride.yml", text)
        self.assertIn("1234567890ab", text)

    def test_system_wrappers_reference_only_their_own_dataset(self):
        from systems.pf2e.lookup import DATA_PATH as pf2e_data_path
        from systems.sf2e.lookup import DATA_PATH as sf2e_data_path

        self.assertTrue(str(pf2e_data_path).endswith("pf2e_foundry.json"))
        self.assertTrue(str(sf2e_data_path).endswith("sf2e_foundry.json"))

    def test_missing_dataset_prints_the_matching_builder_command(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "systems/pf2e/lookup.py", "actions", "stride"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), "Dataset missing. Build it with: python3 systems/pf2e/build_foundry.py")


if __name__ == "__main__":
    unittest.main()
