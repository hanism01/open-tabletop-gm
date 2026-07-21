"""Tests for the campaign art-search helpers."""

import unittest

from scripts.art import (
    ArtValidationError,
    build_search_query,
    normalize_candidate,
    parse_duckduckgo_lite_results,
    validate_public_https_url,
)


class BuildSearchQueryTests(unittest.TestCase):
    def test_defaults_to_a_deviantart_site_search(self):
        self.assertEqual(
            build_search_query("blackwater keep"),
            "blackwater keep site:deviantart.com",
        )

    def test_web_source_leaves_query_unrestricted(self):
        self.assertEqual(build_search_query("blackwater keep", source="web"), "blackwater keep")


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
