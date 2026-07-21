"""tests/test_csrf_rate.py — origin allow-list on writes, per-CF-IP rate buckets, input parity."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_display_app", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CsrfRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(cls.tmp.name)
        cls.secret = tokens.ensure_secret(d / ".invite_secret")
        cls.mod._INVITE_SECRET = cls.secret
        cls.mod._GM_SECRET = "test-gm-secret"
        cls.mod._REVOCATION = tokens.RevocationStore(d / ".revoked.json")
        cls.mod._ALLOWED_ORIGINS = {"https://game.example.com", "http://localhost:5001"}
        cls.client = cls.mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.mod._current_stats = {"players": [{"name": "Kara"}]}
        self.mod._rate_buckets = {}

    def _player_headers(self, character="Kara", ip="203.0.113.9", origin="https://game.example.com"):
        t = tokens.mint_session(character.lower(), character, "c", secret=self.secret)
        self.client.set_cookie("gm_session", t)
        h = {"CF-Connecting-IP": ip}
        if origin:
            h["Origin"] = origin
        return h

    def tearDown(self):
        self.client.delete_cookie("gm_session")

    def _stage(self, headers, text="hi"):
        return self.client.post("/player-input/stage", headers=headers,
                                data=json.dumps({"text": text}),
                                content_type="application/json")

    def test_bad_origin_rejected_even_with_valid_cookie(self):
        r = self._stage(self._player_headers(origin="https://evil.example"))
        self.assertEqual(r.status_code, 403)

    def test_good_origin_accepted(self):
        r = self._stage(self._player_headers())
        self.assertLess(r.status_code, 300, r.get_data(as_text=True))

    def test_gm_writes_bypass_origin_check(self):
        r = self.client.post("/stats", headers={"X-GM-Secret": "test-gm-secret"},
                             data=json.dumps({"players": [{"name": "Kara"}]}),
                             content_type="application/json")
        self.assertLess(r.status_code, 300)

    def test_rate_buckets_keyed_on_cf_ip_not_shared(self):
        h1 = self._player_headers(ip="203.0.113.1")
        for _ in range(25):
            self._stage(h1, "spam")
        blocked = self._stage(h1, "spam")
        self.assertEqual(blocked.status_code, 429)
        self.client.delete_cookie("gm_session")
        h2 = self._player_headers(ip="203.0.113.2")
        ok = self._stage(h2, "fresh")
        self.assertNotEqual(ok.status_code, 429)

    def test_player_input_sanitizes_and_validates_char(self):
        h = self._player_headers()
        r = self.client.post("/player-input", headers=h,
                             data=json.dumps({"text": "attack; rm -rf $(x) `y`"}),
                             content_type="application/json")
        self.assertLess(r.status_code, 300, r.get_data(as_text=True))
        entry = self.mod._input_queue[-1]
        for bad in (";", "$", "`", "(", ")"):
            self.assertNotIn(bad, entry["text"])


if __name__ == "__main__":
    unittest.main()
