"""Tests for shared PF2e/SF2e Foundry source helpers."""

import json
from io import BytesIO, StringIO
from pathlib import Path
from contextlib import redirect_stdout
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from systems.paizo2e import source
from systems.paizo2e.source import (
    SourceSpec,
    build_dataset,
    dataset_metadata,
    needs_rebuild,
    write_dataset,
)


class SourceContractTests(unittest.TestCase):
    @staticmethod
    def archive(members):
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        return ZipFile(BytesIO(buffer.getvalue()))

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
        archive = self.archive({
            "pf2e-resolved-sha/packs/pf2e/actions/stride.yaml": "name: Stride\ntype: action\n",
            "pf2e-resolved-sha/packs/pf2e/spells/fireball.json": "{\"name\": \"Fireball\", \"type\": \"spell\"}",
            "pf2e-resolved-sha/packs/pf2e/actions/logo.webp": "media",
            "pf2e-resolved-sha/packs/pf2e/actions/readme.md": "readme",
            "pf2e-resolved-sha/packs/sf2e/actions/stride.yaml": "name: Other",
        })
        with TemporaryDirectory() as directory:
            out = Path(directory) / "dataset.json"
            with (
                patch.object(source, "resolve_ref", return_value="resolved-sha"),
                patch.object(source, "source_archive", return_value=archive) as fetch,
                patch.object(source, "_github_json", side_effect=AssertionError("no REST blob calls")),
            ):
                self.assertTrue(build_dataset(spec, out))

            fetch.assert_called_once_with(spec, "resolved-sha")
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
                patch.object(source, "source_archive", side_effect=RuntimeError("network failed")),
            ):
                with self.assertRaisesRegex(RuntimeError, "network failed"):
                    build_dataset(spec, out)
            self.assertEqual(out.read_bytes(), old_bytes)

    def test_build_dataset_preserves_existing_output_for_malformed_selected_document(self):
        spec = SourceSpec("pf2e", "packs/pf2e")
        archive = self.archive({
            "repo-sha/packs/pf2e/actions/bad.yaml": "name: [",
        })
        with TemporaryDirectory() as directory:
            out = Path(directory) / "dataset.json"
            old_bytes = b'{"old":true}\n'
            out.write_bytes(old_bytes)
            with (
                patch.object(source, "resolve_ref", return_value="resolved-sha"),
                patch.object(source, "source_archive", return_value=archive),
            ):
                with self.assertRaisesRegex(ValueError, "packs/pf2e/actions/bad.yaml"):
                    build_dataset(spec, out)
            self.assertEqual(out.read_bytes(), old_bytes)

    def test_build_dataset_skips_fresh_output_without_fetching_archive(self):
        spec = SourceSpec("pf2e", "packs/pf2e")
        with TemporaryDirectory() as directory:
            out = Path(directory) / "dataset.json"
            write_dataset(out, {"_meta": dataset_metadata(spec, "resolved-sha", {})})
            with (
                patch.object(source, "resolve_ref", return_value="resolved-sha"),
                patch.object(source, "source_archive") as fetch,
            ):
                self.assertFalse(build_dataset(spec, out))
            fetch.assert_not_called()

    def test_build_dataset_force_fetches_and_rebuilds_fresh_output(self):
        spec = SourceSpec("pf2e", "packs/pf2e")
        archive = self.archive({"repo/packs/pf2e/actions/stride.yaml": "name: Stride"})
        with TemporaryDirectory() as directory:
            out = Path(directory) / "dataset.json"
            write_dataset(out, {"_meta": dataset_metadata(spec, "resolved-sha", {})})
            with (
                patch.object(source, "resolve_ref", return_value="resolved-sha"),
                patch.object(source, "source_archive", return_value=archive) as fetch,
            ):
                self.assertTrue(build_dataset(spec, out, force=True))
            fetch.assert_called_once()

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


class WrapperControlFlowTests(unittest.TestCase):
    @staticmethod
    def run_cli(module, *arguments):
        output = StringIO()
        with patch.object(sys, "argv", [module.__file__, *arguments]), redirect_stdout(output):
            module.main()
        return output.getvalue()

    def test_build_wrappers_forward_force(self):
        from systems.pf2e import build_foundry as pf2e_build
        from systems.sf2e import build_foundry as sf2e_build

        for module in (pf2e_build, sf2e_build):
            with self.subTest(system=module.SPEC.system), patch.object(
                module, "build_dataset", return_value=True
            ) as build:
                self.run_cli(module, "--force")
                build.assert_called_once_with(module.SPEC, module.OUTPUT_PATH, force=True)

    def test_sync_check_reports_exact_statuses(self):
        from systems.pf2e import sync_foundry as pf2e_sync
        from systems.sf2e import sync_foundry as sf2e_sync

        for module in (pf2e_sync, sf2e_sync):
            with self.subTest(system=module.SPEC.system, state="fresh"), patch.object(
                module, "resolve_ref", return_value="sha"
            ), patch.object(module, "needs_rebuild", return_value=False):
                self.assertEqual(self.run_cli(module, "--check"), "Up to date.\n")
            with self.subTest(system=module.SPEC.system, state="stale"), patch.object(
                module, "resolve_ref", return_value="sha"
            ), patch.object(module, "needs_rebuild", return_value=True):
                self.assertEqual(self.run_cli(module, "--check"), "Stale.\n")
            with self.subTest(system=module.SPEC.system, state="error"), patch.object(
                module, "resolve_ref", side_effect=RuntimeError("offline")
            ):
                self.assertEqual(self.run_cli(module, "--check"), "Unverifiable.\n")

    def test_sync_only_invokes_builder_when_stale(self):
        from systems.pf2e import sync_foundry as pf2e_sync
        from systems.sf2e import sync_foundry as sf2e_sync

        for module in (pf2e_sync, sf2e_sync):
            with self.subTest(system=module.SPEC.system, state="fresh"), patch.object(
                module, "resolve_ref", return_value="sha"
            ), patch.object(module, "needs_rebuild", return_value=False), patch.object(
                module, "build_main"
            ) as build:
                self.run_cli(module)
                build.assert_not_called()
            with self.subTest(system=module.SPEC.system, state="stale"), patch.object(
                module, "resolve_ref", return_value="sha"
            ), patch.object(module, "needs_rebuild", return_value=True), patch.object(
                module, "build_main"
            ) as build:
                self.run_cli(module)
                build.assert_called_once_with()
