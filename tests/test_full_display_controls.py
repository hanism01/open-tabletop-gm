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
        # Positive-only would still pass if an unscoped duplicate appeared later,
        # which is the regression this rule exists to prevent.
        self.assertNotIn("\n  .dice-drawer-open {", MARKUP)
        self.assertNotIn("body:not(.input-only).dice-drawer-open", MARKUP)

    def test_wide_screens_get_a_centred_panel(self):
        self.assertIn("body:not(.input-only) #dice-drawer-panel {", MARKUP)


class DiceRequestGating(unittest.TestCase):
    def _pad_body(self):
        # Bounded to the function's own extent, not to end-of-file: the
        # function currently happens to be the last thing in the script, so
        # slicing to end-of-file happened to equal its body — but Task 5 is
        # expected to add full-display code (very likely referencing
        # GM_IDENTITY) after this point in the same <script> block, which
        # must NOT be swept into this slice. Every `}` inside the function
        # body is indented (nested); only the function's own closing brace
        # sits alone on an unindented line, so that's an unambiguous landmark
        # for its true end.
        start = MARKUP.index("function _initDicePad")
        end = MARKUP.index("\n}\n", start) + len("\n}\n")
        return MARKUP[start:end]

    def test_init_takes_a_requests_option(self):
        self.assertIn("function _initDicePad(opts) {", MARKUP)
        self.assertIn("const _wantRequests = !(opts && opts.requests === false);", MARKUP)

    def test_all_three_request_handlers_are_gated(self):
        body = self._pad_body()
        self.assertIn("if (_wantRequests) window._onDiceRequest = _applyDiceRequest;", body)
        self.assertIn("if (_wantRequests) window._onDiceRequestCancelled = _onDiceRequestCancelled;", body)
        self.assertIn("if (_wantRequests) window._onDicePendingSnapshot = _onDicePendingSnapshot;", body)

    def test_full_display_inits_the_pad_only_with_an_identity(self):
        self.assertIn(
            "else if (GM_IDENTITY) { _initDicePad({ requests: true, bind: GM_IDENTITY }); }",
            MARKUP)

    @staticmethod
    def _guard_condition_for_call(text, call_idx):
        # Return the condition text of the `if (...)`/`else if (...)` that
        # structurally governs the _initDicePad( call at call_idx, or None
        # if the call is not nested in one. Scoped by indentation, not by
        # counting braces: this codebase's convention (relied on already by
        # the MEDIUM-4 fix in test_remote_player_console.py) is that a
        # block's own closing `}` sits alone on a line at the same
        # indentation as the `if` that opened it, one level shallower than
        # the block's contents. Walking upward and stopping at the first
        # strictly-shallower line — rather than counting every `{`/`}`
        # character in the file — cannot be confused by a brace character
        # sitting inside an unrelated string/comment (that line's *content*
        # is irrelevant; only its indentation and whether it is `if (`/
        # `else if (`/a bare `}` is examined), which is what made the
        # previous brace-depth walk fragile.
        line_start = text.rfind('\n', 0, call_idx) + 1
        line_end = text.index('\n', call_idx)
        call_line = text[line_start:line_end]
        indent = len(call_line) - len(call_line.lstrip(' '))
        trimmed = call_line.strip()
        if trimmed.startswith("if (") or trimmed.startswith("else if ("):
            # Guard and call share one line: `if (X) { _initDicePad(...); }`.
            return trimmed[trimmed.index('(') + 1:trimmed.index(') {')]

        pos = line_start
        while pos > 0:
            prev_end = pos - 1
            prev_start = text.rfind('\n', 0, prev_end) + 1
            prev_line = text[prev_start:prev_end]
            prev_trimmed = prev_line.strip()
            if prev_trimmed:
                prev_indent = len(prev_line) - len(prev_line.lstrip(' '))
                if prev_indent < indent:
                    if prev_trimmed == '}':
                        return None  # the enclosing block already closed
                    if prev_trimmed.startswith("if (") or prev_trimmed.startswith("else if ("):
                        return prev_trimmed[prev_trimmed.index('(') + 1:prev_trimmed.index(') {')]
                    return None  # shallower, but not a guard or a close
            pos = prev_start
        return None

    def test_gm_display_without_identity_installs_no_request_handlers(self):
        # The unbound full display must not call _initDicePad at all: a GM who
        # requests a roll would otherwise lock and badge their own screen.
        #
        # Every `_initDicePad(` call site (excluding the function definition
        # itself) must be governed by an `if`/`else if` whose *condition*
        # names _inputMode or GM_IDENTITY specifically — not just "some
        # enclosing if", which a Task 5 shape like `if (fab) { _initDicePad
        # (...) }` would satisfy without actually gating on view/identity.
        # See _guard_condition_for_call for why this is indentation-scoped
        # rather than a brace-depth walk.
        idx = 0
        calls = []
        while True:
            idx = MARKUP.find("_initDicePad(", idx)
            if idx == -1:
                break
            line_start = MARKUP.rfind('\n', 0, idx) + 1
            line_end = MARKUP.index('\n', idx)
            line = MARKUP[line_start:line_end].strip()
            if not line.startswith("function _initDicePad"):
                calls.append(idx)
            idx = line_end
        self.assertTrue(calls, "expected at least one _initDicePad(...) call site")
        for call_idx in calls:
            condition = self._guard_condition_for_call(MARKUP, call_idx)
            self.assertIsNotNone(
                condition,
                f"_initDicePad( call at offset {call_idx} is not governed by "
                f"any if/else-if guard")
            self.assertTrue(
                "_inputMode" in condition or "GM_IDENTITY" in condition,
                f"_initDicePad( call at offset {call_idx} is guarded by "
                f"{condition!r}, which names neither _inputMode nor GM_IDENTITY")

    def test_full_display_inits_the_pad_only_with_an_identity(self):
        # HIGH 1 fix: the identity must come from the call site, not from an
        # unconditional read of GM_IDENTITY inside _initDicePad itself.
        self.assertIn(
            "else if (GM_IDENTITY) { _initDicePad({ requests: true, bind: GM_IDENTITY }); }",
            MARKUP)

    def test_binding_derivation_consults_the_bind_option(self):
        self.assertIn(
            "(_qp.get('char') || _qp.get('character') || '').trim().slice(0, 24) "
            "|| ((opts && opts.bind) || '').trim();",
            MARKUP)

    def test_bind_operand_is_not_truncated(self):
        # Fix round 2 (Important finding): _CHAR_NAME_RE permits names up to
        # 50 chars and scripts/gm_invite.py applies no length cap when
        # minting a join token, so opts.bind (the full display's
        # server-authoritative identity) must survive intact. Truncating it
        # here would desync #dp-name's value from the GM_IDENTITY used
        # elsewhere (_selectedChar, _loadCharacterSheet), so a GM request for
        # the player's full name would silently fail to match on their own
        # screen — the exact harm HIGH 1 was about, reintroduced via a
        # different path.
        derivation_start = MARKUP.index("const _bound = (_qp.get('char')")
        derivation_end = MARKUP.index(";", derivation_start) + 1
        derivation = MARKUP[derivation_start:derivation_end]
        bind_operand_start = derivation.index("opts.bind")
        self.assertNotIn(".slice(", derivation[bind_operand_start:])

    def test_binding_derivation_never_reads_gm_identity_directly(self):
        # A remote player who opens /?view=input (phone branch, no `bind`
        # passed) must not be silently bound to GM_IDENTITY — only the URL
        # param or an explicit opts.bind may set _bound inside _initDicePad.
        body = self._pad_body()
        self.assertNotIn("GM_IDENTITY", body)


class DiceBadgeDrawerStacking(unittest.TestCase):
    def test_badge_is_suppressed_while_drawer_is_open(self):
        # #dice-pending-badge is fixed at z-index 60, above the drawer's
        # z-index 30 backdrop. On the full display, once a bound player's pad
        # is live, a GM dice request would otherwise float the badge above
        # the drawer while it's open, reading as a broken modal.
        self.assertIn(".dice-drawer-open #dice-pending-badge { display: none !important; }", MARKUP)


class DpNameLockedAffordance(unittest.TestCase):
    def test_dp_name_locked_style_is_not_scoped_to_input_only(self):
        # The readonly attribute (set in JS) blocks editing on every view;
        # the dimmed affordance should match on the full display too.
        self.assertIn("#dp-name.locked {", MARKUP)
        self.assertNotIn("body.input-only #dp-name.locked", MARKUP)


if __name__ == "__main__":
    unittest.main()
