"""Tests for shared PF2e/SF2e Foundry source helpers."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from systems.paizo2e import source
from systems.paizo2e.source import (
    SourceSpec,
    build_dataset,
    dataset_metadata,
    needs_rebuild,
    write_dataset,
)


class SourceContractTests(unittest.TestCase):
    def test_needs_rebuild_for_missing_changed_and_matching_source_sha(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / "dataset.json"
            self.assertTrue(needs_rebuild(out, "new-sha"))

            write_dataset(out, {"_meta": dataset_metadata(
                SourceSpec("pf2e", "packs/pf2e"), "old-sha", {}
            )})
            self.assertTrue(needs_rebuild(out, "new-sha"))

            write_dataset(out, {"_meta": dataset_metadata(
                SourceSpec("pf2e", "packs/pf2e"), "new-sha", {}
            )})
            self.assertFalse(needs_rebuild(out, "new-sha"))

    def test_build_dataset_selects_candidate_documents_and_writes_metadata(self):
        spec = SourceSpec("pf2e", "packs/pf2e")
        tree = [
            {"path": "packs/pf2e/actions/stride.yaml", "type": "blob", "sha": "a"},
            {"path": "packs/pf2e/spells/fireball.json", "type": "blob", "sha": "b"},
            {"path": "packs/pf2e/actions/logo.webp", "type": "blob", "sha": "media"},
            {"path": "packs/pf2e/actions/readme.md", "type": "blob", "sha": "readme"},
            {"path": "packs/sf2e/actions/stride.yaml", "type": "blob", "sha": "other"},
            {"path": "packs/pf2e/actions", "type": "tree", "sha": "directory"},
        ]
        documents = {
            "a": "name: Stride\ntype: action\n",
            "b": "name: Fireball\ntype: spell\n",
        }
        with TemporaryDirectory() as directory:
            out = Path(directory) / "dataset.json"
            with (
                patch.object(source, "resolve_ref", return_value="resolved-sha"),
                patch.object(source, "tree_at_sha", return_value=tree),
                patch.object(source, "blob_text", side_effect=lambda _spec, sha: documents[sha]) as fetch,
            ):
                self.assertTrue(build_dataset(spec, out))

            self.assertEqual([call.args[1] for call in fetch.call_args_list], ["a", "b"])
            dataset = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(dataset["_meta"], dataset_metadata(
                spec, "resolved-sha", {"actions": 1, "spells": 1}
            ))
            self.assertEqual(dataset["actions"][0]["name"], "Stride")
            self.assertEqual(dataset["spells"][0]["name"], "Fireball")

    def test_build_dataset_preserves_existing_output_when_fetch_fails(self):
        spec = SourceSpec("pf2e", "packs/pf2e")
        with TemporaryDirectory() as directory:
            out = Path(directory) / "dataset.json"
            old_bytes = b'{"old":true}\n'
            out.write_bytes(old_bytes)
            with (
                patch.object(source, "resolve_ref", return_value="resolved-sha"),
                patch.object(source, "tree_at_sha", return_value=[
                    {"path": "packs/pf2e/actions/stride.yaml", "type": "blob", "sha": "a"},
                ]),
                patch.object(source, "blob_text", side_effect=RuntimeError("network failed")),
            ):
                with self.assertRaisesRegex(RuntimeError, "network failed"):
                    build_dataset(spec, out)
            self.assertEqual(out.read_bytes(), old_bytes)

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
