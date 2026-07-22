"""Remote phone console contracts that precede its UI implementation."""
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
        "gm_display_app_remote_console", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class RemotePlayerConsoleContracts(unittest.TestCase):
    def test_player_console_has_persistent_base_screen_regions(self):
        markup = (REPO / "display" / "templates" / "index.html").read_text()

        for element_id in ("player-console", "player-roster", "message-dock", "dice-fab"):
            self.assertIn(f'id="{element_id}"', markup)
        self.assertNotIn('id="dp-tabs"', markup)

        dock_start = markup.index('id="message-dock"')
        fab_start = markup.index('id="dice-fab"')
        dock_markup = markup[dock_start:fab_start]
        self.assertIn('id="player-input-text"', dock_markup)
        self.assertIn('id="staged-queue"', dock_markup)

    def test_player_console_preserves_desktop_input_layout_and_has_no_missing_drawer_reference(self):
        markup = (REPO / "display" / "templates" / "index.html").read_text()

        self.assertRegex(
            markup,
            r"#player-console\s*\{\s*display:\s*flex;\s*flex-direction:\s*column;\s*gap:\s*9px;",
        )
        self.assertRegex(
            markup,
            r"#message-dock\s*\{\s*display:\s*flex;\s*flex-direction:\s*column;\s*gap:\s*9px;",
        )
        self.assertRegex(markup, r"#player-roster,\s*#dice-fab\s*\{\s*display:\s*none;")
        self.assertNotIn('aria-controls="dice-drawer"', markup)
        self.assertIn(
            'id="dice-fab" type="button" disabled aria-label="Dice roller available when the drawer loads"',
            markup,
        )

    def test_input_only_roster_opens_party_character_sheet_overlay(self):
        markup = (REPO / "display" / "templates" / "index.html").read_text()

        self.assertIn("function renderPlayerRoster(players)", markup)
        self.assertIn("button.textContent = player.name", markup)
        self.assertIn("openCharacterSheet(player.name)", markup)
        self.assertIn('id="player-sheet-overlay"', markup)
        self.assertIn('id="player-sheet-close"', markup)
        self.assertIn("function closePlayerSheet", markup)
        self.assertIn("_loadCharacterSheet(name)", markup)
        self.assertIn("bodyEl.innerHTML = _renderMarkdown(md)", markup)
        self.assertIn("renderPlayerRoster(payload.stats.players)", markup)

    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.tmp = tempfile.TemporaryDirectory()
        directory = pathlib.Path(cls.tmp.name)
        cls.secret = tokens.ensure_secret(directory / ".invite_secret")
        cls.mod._INVITE_SECRET = cls.secret
        cls.mod._REVOCATION = tokens.RevocationStore(directory / ".revoked.json")
        cls.mod._ALLOWED_ORIGINS = {ORIGIN, "http://localhost:5001"}
        cls.client = cls.mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.mod._staged.clear()
        self.mod._current_stats = {"players": [{"name": "Kara"}, {"name": "Tom"}]}

    def tearDown(self):
        self.client.delete_cookie("gm_session")

    def _login(self, character):
        token = tokens.mint_session(character.lower(), character, "c", secret=self.secret)
        self.client.set_cookie("gm_session", token)

    def test_bound_player_can_read_another_party_members_sheet(self):
        with tempfile.TemporaryDirectory() as root:
            characters = pathlib.Path(root) / "characters"
            characters.mkdir()
            (characters / "Tom.md").write_text("# Tom\nTOM-FULL-SHEET")
            previous = os.environ.get("GM_CAMPAIGN_ROOT")
            os.environ["GM_CAMPAIGN_ROOT"] = root
            try:
                self._login("Kara")
                response = self.client.get("/character/Tom", headers=TUNNEL)
            finally:
                if previous is None:
                    os.environ.pop("GM_CAMPAIGN_ROOT", None)
                else:
                    os.environ["GM_CAMPAIGN_ROOT"] = previous
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("TOM-FULL-SHEET", response.get_data(as_text=True))

    def test_character_sheet_rejects_invalid_or_non_party_names(self):
        self._login("Kara")
        self.assertEqual(self.client.get("/character/%40%40%40", headers=TUNNEL).status_code, 400)
        self.assertEqual(self.client.get("/character/NotInParty", headers=TUNNEL).status_code, 404)

    def test_character_sheet_rejects_everybody_action_alias(self):
        with tempfile.TemporaryDirectory() as root:
            characters = pathlib.Path(root) / "characters"
            characters.mkdir()
            (characters / "Everybody.md").write_text("This must not be readable")
            previous = os.environ.get("GM_CAMPAIGN_ROOT")
            os.environ["GM_CAMPAIGN_ROOT"] = root
            try:
                self._login("Kara")
                response = self.client.get("/character/Everybody", headers=TUNNEL)
            finally:
                if previous is None:
                    os.environ.pop("GM_CAMPAIGN_ROOT", None)
                else:
                    os.environ["GM_CAMPAIGN_ROOT"] = previous
        self.assertIn(response.status_code, (400, 404))
        self.assertNotIn("This must not be readable", response.get_data(as_text=True))

    def test_bound_player_stages_only_their_own_action(self):
        self._login("Kara")
        response = self.client.post(
            "/player-input/stage", headers=TUNNEL_ORIGIN,
            data=json.dumps({"character": "Tom", "text": "I attack"}),
            content_type="application/json")
        self.assertLess(response.status_code, 300, response.get_data(as_text=True))
        self.assertIn("Kara", self.mod._staged)
        self.assertNotIn("Tom", self.mod._staged)

if __name__ == "__main__":
    unittest.main()
