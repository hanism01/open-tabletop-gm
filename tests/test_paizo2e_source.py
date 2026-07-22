"""Tests for shared PF2e/SF2e Foundry source helpers."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from systems.paizo2e import source
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
        meta = dataset_metadata(
            SourceSpec("pf2e", "packs/pf2e"), "abc123", {"actions": 2}
        )
        self.assertEqual(meta["source"]["sha"], "abc123")
        self.assertEqual(meta["system"], "pf2e")

        with TemporaryDirectory() as directory:
            out = Path(directory) / "dataset.json"
            out.write_text('{"old":true}\n', encoding="utf-8")
            write_dataset(out, {"_meta": meta, "actions": []})
            self.assertTrue(out.exists())
            self.assertEqual(
                json.loads(out.read_text(encoding="utf-8")),
                {"_meta": meta, "actions": []},
            )
            self.assertEqual(
                out.read_text(encoding="utf-8"),
                '{"_meta":' + json.dumps(meta, separators=(",", ":")) + ',"actions":[]}\n',
            )

    def test_write_dataset_preserves_destination_and_cleans_up_on_failure(self):
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            out = directory_path / "dataset.json"
            out.write_text('{"old":true}\n', encoding="utf-8")

            with self.assertRaises(TypeError):
                write_dataset(out, {"not_serializable": {"set"}})

            self.assertEqual(out.read_text(encoding="utf-8"), '{"old":true}\n')
            self.assertEqual(list(directory_path.iterdir()), [out])

    def test_tree_at_sha_rejects_truncated_response(self):
        spec = SourceSpec("pf2e", "packs/pf2e")
        with patch.object(source, "_github_json", return_value={"truncated": True, "tree": []}):
            with self.assertRaisesRegex(RuntimeError, "truncated"):
                source.tree_at_sha(spec, "abc123")

    def test_tree_at_sha_rejects_a_non_list_tree(self):
        spec = SourceSpec("pf2e", "packs/pf2e")
        with patch.object(source, "_github_json", return_value={"truncated": False, "tree": {}}):
            with self.assertRaisesRegex(RuntimeError, "tree"):
                source.tree_at_sha(spec, "abc123")
