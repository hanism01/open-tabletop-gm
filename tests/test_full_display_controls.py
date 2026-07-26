"""Full-display player controls: server identity injection and markup contracts."""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402

TUNNEL = {"CF-Connecting-IP": "203.0.113.9"}


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_display_app_full_controls", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class BoundCharacterInjection(unittest.TestCase):
    def setUp(self):
        self.app = _import_app()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.secret = tokens.ensure_secret(pathlib.Path(self.tmp.name) / "secret")
        self.app._INVITE_SECRET = self.secret
        self.client = self.app.app.test_client()

    def _session_cookie(self, character):
        token = tokens.mint_session("p1", character, "camp", secret=self.secret)
        self.client.set_cookie("gm_session", token)

    def test_local_console_gets_empty_bound_character(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('window.GM_BOUND_CHARACTER = ""', html)

    def test_authenticated_player_gets_their_character(self):
        self._session_cookie("Mira")
        html = self.client.get("/", headers=TUNNEL).get_data(as_text=True)
        self.assertIn('window.GM_BOUND_CHARACTER = "Mira"', html)

    def test_local_browser_with_join_cookie_gets_empty_bound_character(self):
        # A GM testing a player's invite link in their own console browser is
        # loopback, holding a valid session cookie. _gate's un-brick downgrade
        # never fires for "/" (index is in _PLAYER_ENDPOINTS), and sessions
        # last 30 days with no logout route, so index() must narrow this
        # itself: a local peer never gets a bound character, cookie or not.
        self._session_cookie("Mira")
        html = self.client.get("/").get_data(as_text=True)  # no tunnel headers => loopback
        self.assertIn('window.GM_BOUND_CHARACTER = ""', html)

    @staticmethod
    def _bound_character_line(html):
        # Up to the statement's own semicolon, so the *real* closing
        # </script> tag (which follows on the same line) is never mistaken
        # for a breakout inside the assigned value.
        start = html.index("window.GM_BOUND_CHARACTER")
        return html[start:html.index(";", start) + 1]

    def test_bound_character_with_apostrophe_is_json_escaped(self):
        # "Mira O'Neil" is legal under _CHAR_NAME_RE (apostrophes are allowed)
        # and still needs escaping so it can't terminate the JS string literal.
        self._session_cookie("Mira O'Neil")
        html = self.client.get("/", headers=TUNNEL).get_data(as_text=True)
        line = self._bound_character_line(html)
        self.assertIn("Mira O", line)
        self.assertNotIn("'", line)
        self.assertIn("\\u0027", line)

    def test_bound_character_with_script_breakout_attempt_is_json_escaped(self):
        # _CHAR_NAME_RE is not on this path: join-token characters come from
        # raw argv (scripts/gm_invite.py) with no validation before minting.
        # A name containing "</script>" must not be able to break out of the
        # <script> block it's rendered into.
        self._session_cookie("Kara</script><script>alert(1)</script>")
        html = self.client.get("/", headers=TUNNEL).get_data(as_text=True)
        line = self._bound_character_line(html)
        self.assertNotIn("</script>", line)
        self.assertIn("\\u003c", line)


MARKUP = (REPO / "display" / "templates" / "index.html").read_text()


class IdentityResolver(unittest.TestCase):
    def test_identity_prefers_server_value_over_url(self):
        self.assertIn("const GM_IDENTITY = (window.GM_BOUND_CHARACTER || '').trim()", MARKUP)
        self.assertIn("|| (_idParams.get('char') || _idParams.get('character') || '').trim()", MARKUP)

    def test_identity_never_reads_localstorage_player_name(self):
        # The identity resolver itself must never consult gm_player_name —
        # it is unvalidated free text shared across every tab on this origin.
        resolver_start = MARKUP.index("const _idParams")
        resolver_end = MARKUP.index("let _selectedChar", resolver_start)
        resolver_block = MARKUP[resolver_start:resolver_end]
        self.assertNotIn("gm_player_name", resolver_block)

    def test_render_player_roster_only_called_under_input_only_guard(self):
        # The remaining gm_player_name read lives in _loadCharacterSheet's
        # localStorage fallback, reachable only via a roster chip built by
        # renderPlayerRoster. That call must stay gated to the phone view —
        # this would fail if someone later called it unguarded.
        call_idx = MARKUP.index("renderPlayerRoster(payload.stats.players)")
        preceding = MARKUP[:call_idx]
        guard_idx = preceding.rfind("if (document.body.classList.contains('input-only'))")
        self.assertNotEqual(guard_idx, -1, "renderPlayerRoster call is not preceded by an input-only guard")
        between = MARKUP[guard_idx:call_idx]
        # Nothing closes the guard's block before the call itself.
        self.assertNotIn('}', between)

    def test_selected_char_seeds_from_identity(self):
        self.assertIn("let _selectedChar     = GM_IDENTITY || 'Everybody';", MARKUP)

    def test_char_tabs_activate_the_identity_tab(self):
        self.assertIn("if (GM_IDENTITY && names.includes(GM_IDENTITY)) _selectedChar = GM_IDENTITY;", MARKUP)


class DiceDrawerOutsidePhoneView(unittest.TestCase):
    def _css_block(self, selector):
        start = MARKUP.index(selector)
        return MARKUP[start:MARKUP.index("}", start) + 1]

    def test_open_drawer_is_not_scoped_to_input_only(self):
        self.assertIn("#dice-drawer.open {", MARKUP)
        self.assertNotIn("body.input-only #dice-drawer.open {", MARKUP)

    def test_drawer_panel_is_not_scoped_to_input_only(self):
        self.assertIn("#dice-drawer-panel {", MARKUP)
        self.assertNotIn("body.input-only #dice-drawer-panel {", MARKUP)

    def test_body_scroll_lock_stays_phone_only(self):
        # The full display scrolls #text-scroll, not body. Fixing body there
        # would jump the narration to the top every time the drawer opens.
        self.assertIn("body.input-only.dice-drawer-open {", MARKUP)

    def test_wide_screens_get_a_centred_panel(self):
        self.assertIn("body:not(.input-only) #dice-drawer-panel {", MARKUP)


if __name__ == "__main__":
    unittest.main()
