"""Tests for Foundry pack categorization and document normalization."""

import unittest

from systems.paizo2e.packs import normalize_document, pack_category, strip_foundry_markup


class PackCategoryTests(unittest.TestCase):
    def test_maps_bestiaries_to_creatures_and_excludes_media(self):
        self.assertEqual(pack_category("packs/sf2e/alien-core/alien.yaml"), "creatures")
        self.assertEqual(pack_category("packs/pf2e/spells/fireball.yaml"), "spells")
        self.assertIsNone(pack_category("packs/pf2e/assets/logo.webp"))

    def test_maps_direct_pack_directories(self):
        expected = {
            "actions": "actions",
            "ancestries": "ancestries",
            "backgrounds": "backgrounds",
            "classes": "classes",
            "conditions": "conditions",
            "creatures": "creatures",
            "equipment": "equipment",
            "feats": "feats",
            "hazards": "hazards",
            "items": "items",
            "rules": "rules",
            "spells": "spells",
            "vehicles": "vehicles",
        }
        for directory, category in expected.items():
            with self.subTest(directory=directory):
                self.assertEqual(
                    pack_category(f"packs/pf2e/{directory}/example.yaml"), category
                )


class DocumentNormalizationTests(unittest.TestCase):
    def test_normalizes_a_foundry_action_with_source_provenance(self):
        raw = """name: Stride
type: action
system:
  description:
    value: '<p>Move up to your Speed.</p>'
  traits:
    value: [move]
"""
        record = normalize_document(raw, "packs/pf2e/actions/stride.yaml", "actions")
        self.assertEqual(record["name"], "Stride")
        self.assertEqual(record["index"], "stride")
        self.assertEqual(record["category"], "actions")
        self.assertEqual(record["description"], "Move up to your Speed.")
        self.assertEqual(record["traits"], ["move"])
        self.assertIsNone(record["level"])
        self.assertTrue(record["source_path"].endswith("stride.yaml"))

    def test_replaces_uuid_and_check_markup_and_removes_other_tokens(self):
        text = (
            '<p>@UUID[Compendium.pf2e.feats-srd.Item.abc]{Power Attack}</p>'
            '<p>@Check[type:athletics|dc:20]{Climb}</p>'
            '<p>@Template[type:burst|distance:10]</p>'
        )
        self.assertEqual(strip_foundry_markup(text), "Power Attack\n\nClimb")

    def test_rejects_nameless_and_non_mapping_yaml(self):
        self.assertIsNone(normalize_document("type: action", "packs/pf2e/actions/nope.yaml", "actions"))
        self.assertIsNone(normalize_document("- name: Not a document", "packs/pf2e/actions/nope.yaml", "actions"))


if __name__ == "__main__":
    unittest.main()
