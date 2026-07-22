"""Tests for shared PF2e/SF2e lookup commands."""

from __future__ import annotations

import unittest
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from systems.paizo2e.lookup import find_records, format_record, load_dataset


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

    def test_irregular_singular_category_aliases_match_generated_categories(self):
        dataset = {
            "classes": [{"name": "Wizard", "source_path": "packs/classes/wizard.yml"}],
            "ancestries": [{"name": "Human", "source_path": "packs/ancestries/human.yml"}],
        }

        self.assertEqual([record["name"] for record in find_records(dataset, "class", "wizard")], ["Wizard"])
        self.assertEqual([record["name"] for record in find_records(dataset, "ancestry", "human")], ["Human"])

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
        from systems.pf2e import lookup

        output = io.StringIO()
        with TemporaryDirectory() as temporary, patch.object(
            lookup, "DATA_FILE", Path(temporary) / "missing.json"
        ), redirect_stdout(output):
            exit_code = lookup.main(["actions", "stride"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue().strip(), "Dataset missing. Build it with: python3 systems/pf2e/build_foundry.py")

    def test_load_dataset_rejects_invalid_dataset_shapes(self):
        invalid_datasets = [
            [],
            {"_meta": []},
            {"_meta": {"source": []}},
            {"_meta": {"source": {"sha": 42}}},
            {"_meta": {"source": {"sha": "abc"}}, "actions": {}},
        ]

        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "dataset.json"
            for payload in invalid_datasets:
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_dataset(path)

    def test_malformed_dataset_reports_a_concise_cli_error(self):
        from systems.sf2e import lookup

        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "malformed.json"
            path.write_text("{", encoding="utf-8")
            output = io.StringIO()
            with patch.object(lookup, "DATA_FILE", path), redirect_stdout(output):
                exit_code = lookup.main(["actions", "boost"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue().strip(), "Dataset error: invalid JSON")

    def test_wrong_dataset_shape_reports_a_concise_cli_error(self):
        from systems.pf2e import lookup

        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "wrong-shape.json"
            path.write_text("[]", encoding="utf-8")
            output = io.StringIO()
            with patch.object(lookup, "DATA_FILE", path), redirect_stdout(output):
                exit_code = lookup.main(["actions", "stride"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue().strip(), "Dataset error: dataset must be a JSON object")


if __name__ == "__main__":
    unittest.main()
