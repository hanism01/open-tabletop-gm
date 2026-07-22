"""Tests for shared PF2e/SF2e Foundry source helpers."""

import unittest

from systems.paizo2e.source import SourceSpec, dataset_metadata, write_dataset


class SourceContractTests(unittest.TestCase):
    def test_source_spec_uses_the_split_v14_foundry_pack_roots(self):
        pf2e = SourceSpec("pf2e", "packs/pf2e")
        sf2e = SourceSpec("sf2e", "packs/sf2e")
        self.assertEqual(pf2e.repo, sf2e.repo)
        self.assertEqual(pf2e.repo, "foundryvtt/pf2e")
        self.assertEqual(pf2e.ref, sf2e.ref)
        self.assertEqual(pf2e.ref, "v14-dev")

    def test_metadata_records_resolved_sha_and_record_provenance(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        meta = dataset_metadata(
            SourceSpec("pf2e", "packs/pf2e"), "abc123", {"actions": 2}
        )
        self.assertEqual(meta["source"]["sha"], "abc123")
        self.assertEqual(meta["system"], "pf2e")

        with TemporaryDirectory() as directory:
            out = Path(directory) / "dataset.json"
            write_dataset(out, {"_meta": meta, "actions": []})
            self.assertTrue(out.exists())
