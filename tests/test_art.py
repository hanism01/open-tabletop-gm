"""Tests for the campaign art-search helpers."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.art import (
    ArtValidationError,
    art_path,
    build_search_query,
    delete_record,
    find_records,
    list_records,
    normalize_candidate,
    parse_duckduckgo_lite_results,
    save_record,
    update_record,
    validate_public_https_url,
)
from scripts import art


class BuildSearchQueryTests(unittest.TestCase):
    def test_defaults_to_a_deviantart_site_search(self):
        self.assertEqual(
            build_search_query("blackwater keep"),
            "blackwater keep site:deviantart.com",
        )

    def test_web_source_leaves_query_unrestricted(self):
        self.assertEqual(build_search_query("blackwater keep", source="web"), "blackwater keep")


class ArtCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary_root = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_root.name)
        (self.root / "campaigns" / "ashfall").mkdir(parents=True)
        self.environment = patch.dict(os.environ, {"GM_CAMPAIGN_ROOT": str(self.root)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary_root.cleanup()

    def test_search_defaults_to_deviantart_domain_query(self):
        from io import StringIO
        from contextlib import redirect_stdout

        with patch("scripts.art.fetch_search_results", return_value=[]) as fetch:
            with redirect_stdout(StringIO()):
                self.assertEqual(art.main(["search", "--campaign", "ashfall", "--query", "blackwater keep"]), 0)

        self.assertEqual(fetch.call_args.args, ("blackwater keep site:deviantart.com",))

    def test_save_without_a_search_cache_returns_malformed_status(self):
        from io import StringIO
        from contextlib import redirect_stderr, redirect_stdout

        stderr = StringIO()
        with redirect_stderr(stderr), redirect_stdout(StringIO()):
            status = art.main(
                ["save", "--campaign", "ashfall", "--candidate", "0", "--as", "keep", "--kind", "place"]
            )

        self.assertEqual(status, 2)
        self.assertIn("search cache", stderr.getvalue().lower())

    def test_expired_or_future_cache_cannot_be_saved_and_current_cache_is_consumed(self):
        from io import StringIO
        from contextlib import redirect_stderr, redirect_stdout

        cache = self.root / "campaigns" / "ashfall" / ".art_search_cache.json"
        candidate = {
            "title": "Blackwater Keep",
            "image_url": "https://images.example.com/keep.jpg",
            "source_url": "https://artist.example.com/keep",
        }
        cache.write_text(json.dumps({"created_at": "2000-01-01T00:00:00Z", "candidates": [candidate]}))
        with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
            self.assertEqual(
                art.main(["save", "--campaign", "ashfall", "--candidate", "0", "--as", "keep", "--kind", "place"]),
                2,
            )
        self.assertTrue(cache.exists())

        future = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
        cache.write_text(json.dumps({"created_at": future, "candidates": [candidate]}))
        with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
            self.assertEqual(
                art.main(["save", "--campaign", "ashfall", "--candidate", "0", "--as", "keep", "--kind", "place"]),
                2,
            )
        self.assertTrue(cache.exists())

        current = datetime.now(timezone.utc).isoformat()
        cache.write_text(json.dumps({"created_at": current, "candidates": [candidate]}))
        with redirect_stdout(StringIO()):
            self.assertEqual(
                art.main(["save", "--campaign", "ashfall", "--candidate", "0", "--as", "keep", "--kind", "place", "--tags", "ruin,fortress"]),
                0,
            )
        self.assertFalse(cache.exists())
        self.assertEqual(list_records("ashfall")[0]["tags"], ["ruin", "fortress"])

    def test_crud_commands_return_compact_json(self):
        save_record(
            "ashfall",
            {
                "id": "keep", "kind": "place", "title": "Blackwater Keep",
                "source_url": "https://artist.example.com/keep",
            },
        )
        from io import StringIO
        from contextlib import redirect_stdout

        def run(argv):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(art.main(argv), 0)
            return json.loads(output.getvalue())

        self.assertEqual(run(["find", "--campaign", "ashfall", "--query", "blackwater"])[0]["id"], "keep")
        self.assertEqual(run(["list", "--campaign", "ashfall", "--kind", "place"])[0]["id"], "keep")
        self.assertEqual(
            run(["update", "--campaign", "ashfall", "--id", "keep", "--title", "Blackwater Citadel"])["title"],
            "Blackwater Citadel",
        )
        self.assertEqual(run(["show", "--campaign", "ashfall", "--id", "keep"])["id"], "keep")
        self.assertEqual(run(["delete", "--campaign", "ashfall", "--id", "keep"]), {"deleted": "keep"})

    def test_one_off_show_and_hide_use_display_hook(self):
        with patch("scripts.art.post_display_art") as post:
            self.assertEqual(
                art.main([
                    "show", "--url", "https://images.example.com/keep.jpg",
                    "--source-url", "https://artist.example.com/keep", "--title", "Blackwater Keep",
                ]),
                0,
            )
            self.assertEqual(art.main(["hide"]), 0)

        self.assertEqual(post.call_args_list[0].args[0]["title"], "Blackwater Keep")
        self.assertEqual(post.call_args_list[1].args[0], {"action": "hide"})

    def test_saved_record_show_dispatches_a_complete_display_payload(self):
        save_record(
            "ashfall",
            {
                "id": "keep", "kind": "place", "title": "Blackwater Keep",
                "image_url": "https://images.example.com/keep.jpg",
                "source_url": "https://artist.example.com/keep", "creator": "A. Artist",
            },
        )
        from io import StringIO
        from contextlib import redirect_stdout

        with patch("scripts.art.post_display_art") as post, redirect_stdout(StringIO()):
            self.assertEqual(art.main(["show", "--campaign", "ashfall", "--id", "keep"]), 0)

        self.assertEqual(
            post.call_args.args[0],
            {
                "title": "Blackwater Keep", "category": "place", "kind": "place",
                "image_url": "https://images.example.com/keep.jpg",
                "source_url": "https://artist.example.com/keep", "creator": "A. Artist",
                "alt": "Blackwater Keep",
            },
        )

    def test_direct_script_execution_can_import_the_scripts_package(self):
        environment = {**os.environ, "GM_CAMPAIGN_ROOT": str(self.root)}
        result = subprocess.run(
            [sys.executable, "scripts/art.py", "list", "--campaign", "ashfall"],
            cwd=Path(__file__).parents[1], env=environment, text=True, capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])


class CandidateNormalizationTests(unittest.TestCase):
    def test_retains_attribution_fields_and_adds_source_host(self):
        candidate = normalize_candidate(
            {
                "title": "Blackwater Keep",
                "image_url": "https://images.deviantart.net/keep.jpg",
                "thumbnail_url": "https://images.deviantart.net/keep-thumb.jpg",
                "source_url": "https://www.deviantart.com/artist/art/Blackwater-Keep-1",
                "creator": "artist",
            }
        )

        self.assertEqual(candidate["title"], "Blackwater Keep")
        self.assertEqual(candidate["image_url"], "https://images.deviantart.net/keep.jpg")
        self.assertEqual(candidate["thumbnail_url"], "https://images.deviantart.net/keep-thumb.jpg")
        self.assertEqual(
            candidate["source_url"],
            "https://www.deviantart.com/artist/art/Blackwater-Keep-1",
        )
        self.assertEqual(candidate["creator"], "artist")
        self.assertEqual(candidate["source_host"], "www.deviantart.com")


class PublicUrlValidationTests(unittest.TestCase):
    def test_rejects_non_public_or_non_https_urls(self):
        for value in (
            "http://example.com/art.jpg",
            "https://127.0.0.1/art.jpg",
            "https://localhost/art.jpg",
            "https://foo.localhost/art.jpg",
            "https://10.0.0.1/art.jpg",
            "https://127.0.0.1.nip.io/art.jpg",
            "https://2130706433/art.jpg",
            "https://0177.0.0.1/art.jpg",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ArtValidationError):
                    validate_public_https_url(value)

    def test_rejects_malformed_dns_hostnames(self):
        for value in (
            "https://exa mple.com/art.jpg",
            "https://-bad.example/art.jpg",
            "https://example..com/art.jpg",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ArtValidationError):
                    validate_public_https_url(value)


class DuckDuckGoLiteParsingTests(unittest.TestCase):
    def test_keeps_result_open_through_nested_non_result_divs(self):
        html = """
        <div class="result">
          <div class="result__body">
            <a class="result-link" href="https://example.com/page">A result</a>
          </div>
          <img src="https://example.com/thumb.jpg">
        </div>
        """

        result = parse_duckduckgo_lite_results(html)

        self.assertEqual(result[0]["image_url"], "https://example.com/thumb.jpg")
        self.assertEqual(result[0]["thumbnail_url"], "https://example.com/thumb.jpg")

    def test_parses_lite_table_result_markup(self):
        html = """
        <table><tr><td>
          <a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.deviantart.com%2Fartist%2Fart%2FBlackwater-Keep-1">Blackwater Keep</a>
          <img src="https://images.deviantart.net/keep-thumb.jpg">
        </td></tr></table>
        """

        self.assertEqual(
            parse_duckduckgo_lite_results(html),
            [
                {
                    "title": "Blackwater Keep",
                    "image_url": "https://images.deviantart.net/keep-thumb.jpg",
                    "thumbnail_url": "https://images.deviantart.net/keep-thumb.jpg",
                    "source_url": "https://www.deviantart.com/artist/art/Blackwater-Keep-1",
                    "creator": "",
                    "source_host": "www.deviantart.com",
                }
            ],
        )


class CampaignArtPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_root = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_root.name)
        (self.root / "campaigns" / "ashfall").mkdir(parents=True)
        self.environment = patch.dict(os.environ, {"GM_CAMPAIGN_ROOT": str(self.root)})
        self.environment.start()
        self.record = {
            "id": "blackwater-keep",
            "kind": "place",
            "title": "Blackwater Keep",
            "aliases": ["The Keep", "blackwater"],
            "tags": ["fortress", "ruin"],
            "image_url": "https://images.example.com/blackwater.jpg",
            "source_url": "https://artist.example.com/art/blackwater",
            "creator": "A. Artist",
        }

    def tearDown(self):
        self.environment.stop()
        self.temporary_root.cleanup()

    def test_saves_campaign_record_and_finds_it_by_query(self):
        saved = save_record("ashfall", self.record)

        stored_path = self.root / "campaigns" / "ashfall" / "art.json"
        self.assertEqual(art_path("ashfall"), stored_path.resolve())
        self.assertTrue(stored_path.exists())
        self.assertEqual(
            json.loads(stored_path.read_text()),
            {"version": 1, "records": [saved]},
        )
        self.assertEqual(find_records("ashfall", "keep"), [saved])
        self.assertEqual(saved["source_host"], "artist.example.com")
        self.assertIn("saved_at", saved)

    def test_rejects_invalid_kind_and_duplicate_id(self):
        with self.assertRaises(ArtValidationError):
            save_record("ashfall", {**self.record, "kind": "item"})

        save_record("ashfall", self.record)
        with self.assertRaises(ArtValidationError):
            save_record("ashfall", self.record)

    def test_normalizes_aliases_and_tags_before_applying_the_item_cap(self):
        saved = save_record(
            "ashfall",
            {
                **self.record,
                "aliases": ["  The Keep  ", "the keep", ""] * 10,
                "tags": ["ruin", "RUIN", ""],
            },
        )

        self.assertEqual(saved["aliases"], ["The Keep"])
        self.assertEqual(saved["tags"], ["ruin"])

    def test_updates_and_deletes_a_record(self):
        save_record("ashfall", self.record)

        updated = update_record(
            "ashfall", "blackwater-keep", {"title": "Blackwater Citadel", "status": "approved"}
        )

        self.assertEqual(updated["title"], "Blackwater Citadel")
        self.assertEqual(updated["status"], "approved")
        self.assertTrue(delete_record("ashfall", "blackwater-keep"))
        self.assertEqual(list_records("ashfall"), [])
        self.assertFalse(delete_record("ashfall", "blackwater-keep"))

    def test_finds_aliases_and_all_searchable_fields_case_insensitively(self):
        save_record("ashfall", self.record)

        for query in ("BLACKWATER-KEEP", "blackwater keep", "THE KEEP", "PLACE", "FORTRESS"):
            with self.subTest(query=query):
                self.assertEqual(len(find_records("ashfall", query)), 1)

    def test_writes_atomically_without_leaving_a_temporary_file(self):
        save_record("ashfall", self.record)

        self.assertFalse((self.root / "campaigns" / "ashfall" / "art.json.tmp").exists())

    def test_missing_file_lists_no_records_and_corrupt_file_is_rejected(self):
        self.assertEqual(list_records("ashfall"), [])
        (self.root / "campaigns" / "ashfall" / "art.json").write_text("not json")

        with self.assertRaises(ArtValidationError):
            list_records("ashfall")

    def test_parses_canonical_result_links_and_image_fields_deterministically(self):
        html = """
        <div class="result">
          <a class="result-link" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.deviantart.com%2Fartist%2Fart%2FBlackwater-Keep-1">Blackwater <b>Keep</b></a>
          <img class="result__icon__img" src="https://images.deviantart.net/keep-thumb.jpg">
        </div>
        <div class="result">
          <a class="result-link" href="https://www.deviantart.com/artist/art/No-Image">No Image</a>
        </div>
        """

        self.assertEqual(
            parse_duckduckgo_lite_results(html),
            [
                {
                    "title": "Blackwater Keep",
                    "image_url": "https://images.deviantart.net/keep-thumb.jpg",
                    "thumbnail_url": "https://images.deviantart.net/keep-thumb.jpg",
                    "source_url": "https://www.deviantart.com/artist/art/Blackwater-Keep-1",
                    "creator": "",
                    "source_host": "www.deviantart.com",
                },
                {
                    "title": "No Image",
                    "image_url": "",
                    "thumbnail_url": "",
                    "source_url": "https://www.deviantart.com/artist/art/No-Image",
                    "creator": "",
                    "source_host": "www.deviantart.com",
                },
            ],
        )
