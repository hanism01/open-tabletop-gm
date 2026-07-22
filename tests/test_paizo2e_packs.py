"""Tests for Foundry pack categorization and document normalization."""

import json
import unittest

from systems.paizo2e.packs import normalize_document, pack_category, strip_foundry_markup


class PackCategoryTests(unittest.TestCase):
    def test_maps_bestiaries_to_creatures_and_excludes_media(self):
        self.assertEqual(pack_category("packs/sf2e/alien-core/alien.yaml"), "creatures")
        self.assertEqual(pack_category("packs/pf2e/monster-bestiary/ogre.yaml"), "creatures")
        self.assertEqual(pack_category("packs/pf2e/spells/fireball.yaml"), "spells")
        self.assertIsNone(pack_category("packs/pf2e/spells/logo.webp"))
        for suffix in (".png", ".jpg", ".mp3", ".ogg"):
            with self.subTest(suffix=suffix):
                self.assertIsNone(pack_category(f"packs/pf2e/spells/logo{suffix}"))
        self.assertIsNone(pack_category("packs/pf2e/unsupported/example.yaml"))
        self.assertIsNone(pack_category("packs/pf2e/spells/../assets/x.yaml"))
        self.assertIsNone(pack_category("packs/pf2e/spells/README.md"))
        self.assertEqual(pack_category("packs/pf2e/spells/fireball.yml"), "spells")
        self.assertEqual(pack_category("packs/pf2e/spells/fireball.json"), "spells")

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
  internalOnly: should-not-be-exported
"""
        record = normalize_document(raw, "packs/pf2e/actions/stride.yaml", "actions")
        self.assertEqual(record["name"], "Stride")
        self.assertEqual(record["index"], "stride")
        self.assertEqual(record["category"], "actions")
        self.assertEqual(record["description"], "Move up to your Speed.")
        self.assertEqual(record["traits"], ["move"])
        self.assertIsNone(record["level"])
        self.assertTrue(record["source_path"].endswith("stride.yaml"))
        self.assertNotIn("internalOnly", record)

    def test_replaces_uuid_and_check_markup_and_removes_other_tokens(self):
        text = (
            '<p>@UUID[Compendium.pf2e.feats-srd.Item.abc]{Power Attack}</p>'
            '<p>@Check[type:athletics|dc:20]{Climb}</p>'
            '<p>@Template[type:burst|distance:10]</p>'
        )
        self.assertEqual(strip_foundry_markup(text), "Power Attack\n\nClimb")

    def test_handles_balanced_tokens_and_html_entities(self):
        text = (
            '<p data-note="a > b">@UUID[Compendium.pf2e.actionspf2e.Item.abc]'
            "{Strike &amp; Step}</p><p>@Damage[2d6[fire]] R&amp;D</p>"
        )
        self.assertEqual(strip_foundry_markup(text), "Strike & Step\n\nR&D")

    def test_preserves_spaced_uuid_and_damage_labels(self):
        text = "@UUID[Compendium.pf2e.Item.abc] {A Label} @Damage[2d6[fire]] {Burn}"
        self.assertEqual(strip_foundry_markup(text), "A Label")

    def test_removes_damage_label_without_consuming_following_text(self):
        text = "@Damage[2d6[fire]] {Burn} now"
        self.assertEqual(strip_foundry_markup(text), "now")

    def test_decodes_html_entities_exactly_once(self):
        self.assertEqual(strip_foundry_markup("&amp;lt;b&amp;gt;"), "&lt;b&gt;")

    def test_returns_none_only_for_nameless_documents(self):
        self.assertIsNone(normalize_document("type: action", "packs/pf2e/actions/nope.yaml", "actions"))

    def test_rejects_non_mapping_and_unparseable_documents(self):
        with self.assertRaises(ValueError):
            normalize_document("- name: Not a document", "packs/pf2e/actions/nope.yaml", "actions")
        with self.assertRaises(ValueError):
            normalize_document("name: [", "packs/pf2e/actions/nope.yaml", "actions")
        with self.assertRaises(ValueError):
            normalize_document("name: valid-yaml-but-not-json", "packs/pf2e/actions/nope.json", "actions")

    def test_normalizes_malformed_values_to_json_safe_shapes(self):
        raw = """name: Strange Data
type: [action]
system:
  description: &recursive
    value: '<p>Safe &amp; sound.</p>'
    self: *recursive
  traits:
    value: [move, 7]
  level:
    value: {not: scalar}
"""
        record = normalize_document(raw, "packs/pf2e/actions/strange.yaml", "actions")
        self.assertEqual(record["type"], "")
        self.assertEqual(record["traits"], [])
        self.assertIsNone(record["level"])
        self.assertEqual(record["description"], "Safe & sound.")
        json.dumps(record)


if __name__ == "__main__":
    unittest.main()
