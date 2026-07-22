"""tests/test_attribution.py — character comes from identity, not request data (spec §3)."""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402

TUNNEL = {"CF-Connecting-IP": "203.0.113.9"}
ORIGIN = "https://game.example.com"
TUNNEL_ORIGIN = dict(TUNNEL, Origin=ORIGIN)


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_display_app", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AttributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(cls.tmp.name)
        cls.secret = tokens.ensure_secret(d / ".invite_secret")
        cls.mod._INVITE_SECRET = cls.secret
        cls.mod._GM_SECRET = "test-gm-secret"
        cls.mod._REVOCATION = tokens.RevocationStore(d / ".revoked.json")
        cls.mod._ALLOWED_ORIGINS = {ORIGIN, "http://localhost:5001"}
        cls.client = cls.mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.mod._staged.clear()
        self.mod._current_stats = {"players": [{"name": "Kara"}, {"name": "Tom"}]}

    def _login(self, character):
        t = tokens.mint_session(character.lower(), character, "c", secret=self.secret)
        self.client.set_cookie("gm_session", t)

    def tearDown(self):
        self.client.delete_cookie("gm_session")

    def test_stage_ignores_body_character_for_players(self):
        self._login("Kara")
        r = self.client.post("/player-input/stage", headers=TUNNEL_ORIGIN,
                             data=json.dumps({"character": "Tom", "text": "I attack"}),
                             content_type="application/json")
        self.assertLess(r.status_code, 300, r.get_data(as_text=True))
        self.assertIn("Kara", self.mod._staged)
        self.assertNotIn("Tom", self.mod._staged)

    def test_skip_ignores_body_character_for_players(self):
        self._login("Kara")
        # skip_input stages with ready=True and calls _check_auto_trigger, which
        # would otherwise immediately clear _staged once len(_staged) >= threshold
        # (default _expected_count is 1). Raise the threshold so the staged entry
        # survives long enough to assert attribution.
        prev_threshold = self.mod._autorun_threshold
        self.mod._autorun_threshold = 99
        try:
            r = self.client.post("/player-input/skip", headers=TUNNEL_ORIGIN,
                                 data=json.dumps({"character": "Tom"}),
                                 content_type="application/json")
            self.assertLess(r.status_code, 300, r.get_data(as_text=True))
            self.assertIn("Kara", self.mod._staged)
            self.assertNotIn("Tom", self.mod._staged)
        finally:
            self.mod._autorun_threshold = prev_threshold

    def test_two_players_attributed_independently(self):
        for character, text in (("Kara", "kara acts"), ("Tom", "tom acts")):
            self._login(character)
            self.client.post("/player-input/stage", headers=TUNNEL_ORIGIN,
                             data=json.dumps({"character": "Everybody", "text": text}),
                             content_type="application/json")
            self.client.delete_cookie("gm_session")
        self.assertEqual(self.mod._staged["Kara"]["text"], "kara acts")
        self.assertEqual(self.mod._staged["Tom"]["text"], "tom acts")

    def test_stream_ignores_query_character_for_players(self):
        self._login("Kara")
        r = self.client.get("/stream?character=Tom", headers=TUNNEL)
        self.assertEqual(r.status_code, 200)
        chars = list(self.mod._client_chars.values())
        self.assertIn("kara", chars)
        self.assertNotIn("tom", chars)
        r.close()

    def test_effects_expire_bound_for_players(self):
        # Tom holds a Bless effect. Kara, logged in, tries to expire it by
        # naming Tom as owner. The bind rewrites owner→Kara, so Tom's effect
        # must survive — a player cannot expire a teammate's effect.
        self.mod._current_stats = {"players": [
            {"name": "Kara", "effects": []},
            {"name": "Tom", "effects": [{"name": "Bless"}]},
        ]}
        self._login("Kara")
        r = self.client.post("/effects/expire", headers=TUNNEL_ORIGIN,
                             data=json.dumps({"owner": "Tom", "name": "Bless"}),
                             content_type="application/json")
        self.assertLess(r.status_code, 300, r.get_data(as_text=True))
        tom = next(p for p in self.mod._current_stats["players"] if p["name"] == "Tom")
        tom_effects = [e.get("name") for e in tom.get("effects", [])]
        self.assertIn("Bless", tom_effects)

    def test_character_sheet_bound_for_players(self):
        # Distinct on-disk sheets for Kara and Tom. Logged in as Kara, a GET for
        # /character/Tom must resolve to Kara's own sheet (bind), never Tom's.
        # Assert on real bytes: identical to /character/Kara, containing Kara's
        # marker and not Tom's — not a vacuous 404==404.
        with tempfile.TemporaryDirectory() as root:
            chars = pathlib.Path(root) / "characters"
            chars.mkdir(parents=True)
            (chars / "Kara.md").write_text("# Kara secret sheet\nKARA-ONLY")
            (chars / "Tom.md").write_text("# Tom secret sheet\nTOM-ONLY")
            prev = os.environ.get("GM_CAMPAIGN_ROOT")
            os.environ["GM_CAMPAIGN_ROOT"] = root
            try:
                self._login("Kara")
                r_tom = self.client.get("/character/Tom", headers=TUNNEL)
                r_kara = self.client.get("/character/Kara", headers=TUNNEL)
            finally:
                if prev is None:
                    os.environ.pop("GM_CAMPAIGN_ROOT", None)
                else:
                    os.environ["GM_CAMPAIGN_ROOT"] = prev
        self.assertEqual(r_tom.status_code, 200, r_tom.get_data(as_text=True))
        self.assertEqual(r_tom.get_data(), r_kara.get_data())
        body = r_tom.get_data(as_text=True)
        self.assertIn("KARA-ONLY", body)
        self.assertNotIn("TOM-ONLY", body)

    def test_local_console_can_still_name_characters(self):
        # local role still goes through the device gate — present a device id
        # (with _REQUIRE_APPROVAL False, any non-empty id is approved)
        r = self.client.post("/player-input/stage",
                             headers={"X-DND-Device": "test-device", "Origin": ORIGIN},
                             data=json.dumps({"character": "Tom", "text": "gm staged"}),
                             content_type="application/json")
        self.assertLess(r.status_code, 300, r.get_data(as_text=True))
        self.assertIn("Tom", self.mod._staged)


if __name__ == "__main__":
    unittest.main()
