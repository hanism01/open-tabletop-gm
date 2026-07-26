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


def _norm(text):
    """Collapse every run of whitespace to one space.

    Lets a multi-line source snippet be asserted against the template without
    pinning its indentation or line breaks.
    """
    return " ".join(text.split())


NORM_MARKUP = _norm(MARKUP)

# The two — and only two — places _initDicePad is called, each pinned together
# with the guard that governs it. Asserted verbatim (whitespace-normalised)
# rather than by inferring JavaScript block structure, because the text itself
# pins polarity, guard identifier, argument object and nesting all at once:
# `if (!GM_IDENTITY)` cannot slip through, and there is no parser to be
# confused by a multi-line condition, a brace-less `if`, `if (X){` with no
# space, or a brace inside a string literal.
#
# Whitespace normalisation makes this tolerant of pure re-indentation and of
# re-wrapping — including the file's dominant `} else if (X) {` style, which
# still contains both snippets as substrings. What it will not tolerate is a
# change to the statement text or the nesting, e.g. wrapping the call in an
# extra `if (padEl) { ... }`. That fails loudly, naming expected and actual
# text, which is the intended outcome for a call-site contract: the contract
# should be re-stated deliberately, not silently re-derived.
PHONE_CALL_SITE = """
  if (_inputMode) {
    document.body.classList.add('input-only');
    const ip = document.getElementById('input-panel');
    if (ip) ip.classList.remove('collapsed');
    _initDicePad({ requests: true });
  }
"""

FULL_DISPLAY_CALL_SITE = (
    "else if (GM_IDENTITY) { _initDicePad({ requests: true, bind: GM_IDENTITY }); }")

# Stable landmark immediately above both call sites, used only to window the
# failure message: a bare assertIn against the whole template reports a 2.5MB
# haystack, which is not a diagnosable failure.
CALL_SITE_ANCHOR = "const _inputMode = _qp.get('view') === 'input'"


class DiceRequestGating(unittest.TestCase):
    # Exact declaration, not the `function _initDicePad` prefix: a future
    # `function _initDicePadButton(...)` declared earlier in the same script
    # would otherwise silently re-target every slice taken from here.
    PAD_SIGNATURE = "function _initDicePad(opts) {"

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
        self.assertEqual(
            MARKUP.count(self.PAD_SIGNATURE), 1,
            f"expected exactly one {self.PAD_SIGNATURE!r} declaration")
        start = MARKUP.index(self.PAD_SIGNATURE)
        end = MARKUP.index("\n}\n", start) + len("\n}\n")
        return MARKUP[start:end]

    def _assert_call_site(self, snippet):
        """Assert `snippet` appears in the template, ignoring whitespace.

        On failure, print the expected snippet next to the actual text at
        CALL_SITE_ANCHOR — never the whole template.
        """
        needle = _norm(snippet)
        if needle in NORM_MARKUP:
            return
        anchor_at = NORM_MARKUP.find(_norm(CALL_SITE_ANCHOR))
        if anchor_at == -1:
            self.fail(f"call-site anchor {CALL_SITE_ANCHOR!r} is gone from the "
                      f"template; expected call site was:\n  {needle}")
        actual = NORM_MARKUP[anchor_at:anchor_at + len(needle) + 400]
        self.fail("call site not found (whitespace-insensitive).\n"
                  f"  expected: {needle}\n"
                  f"  actual region after {CALL_SITE_ANCHOR!r}:\n    {actual}")

    @staticmethod
    def _call_sites():
        """Every line that calls _initDicePad(...), as (line number, text).

        Excludes the function's own declaration and any occurrence sitting
        after a `//` on its line or inside a JS/HTML block comment.
        """
        sites = []
        idx = 0
        while True:
            idx = MARKUP.find("_initDicePad(", idx)
            if idx == -1:
                return sites
            line_start = MARKUP.rfind("\n", 0, idx) + 1
            line_end = MARKUP.index("\n", idx)
            line = MARKUP[line_start:line_end]
            stripped = line.strip()
            before = line[:idx - line_start]
            commented = "//" in before or stripped.startswith(("*", "<!--"))
            if not stripped.startswith("function _initDicePad") and not commented:
                sites.append((MARKUP.count("\n", 0, idx) + 1, stripped))
            idx = line_end

    def test_init_takes_a_requests_option(self):
        self.assertIn("function _initDicePad(opts) {", MARKUP)
        self.assertIn("const _wantRequests = !(opts && opts.requests === false);", MARKUP)

    def test_all_three_request_handlers_are_gated(self):
        body = self._pad_body()
        self.assertIn("if (_wantRequests) window._onDiceRequest = _applyDiceRequest;", body)
        self.assertIn("if (_wantRequests) window._onDiceRequestCancelled = _onDiceRequestCancelled;", body)
        self.assertIn("if (_wantRequests) window._onDicePendingSnapshot = _onDicePendingSnapshot;", body)

    def test_the_pad_is_called_from_exactly_two_call_sites(self):
        # A third call site is how the unbound full display would regain the
        # DM-request handlers — a GM who requests a roll would then lock and
        # badge their own screen. Neither of the two legitimate sites may be
        # duplicated or joined by an unguarded top-level call; the guard on
        # each is pinned separately (see the two tests below).
        sites = self._call_sites()
        self.assertEqual(
            len(sites), 2,
            "expected exactly two _initDicePad(...) call sites (phone mode and "
            f"the full display's bound-player branch), found {len(sites)}: {sites}")

    def test_phone_call_site_stays_guarded_by_input_mode(self):
        # The phone's own call site, pinned whole. Task 4 must not have moved
        # or re-guarded it: the phone view has to behave exactly as before.
        self._assert_call_site(PHONE_CALL_SITE)

    def test_full_display_inits_the_pad_only_with_an_identity(self):
        # HIGH 1 fix: the identity must come from the call site, not from an
        # unconditional read of GM_IDENTITY inside _initDicePad itself.
        #
        # `else if (GM_IDENTITY)` verbatim also pins the *polarity* of the
        # guard: `if (!GM_IDENTITY)` would be the unbound GM console installing
        # its own request handlers, which is the entire reason this gate exists.
        self._assert_call_site(FULL_DISPLAY_CALL_SITE)

    @staticmethod
    def _bind_derivation():
        """The `const _bound = ...;` statement, up to its own semicolon.

        Asserting against this slice rather than the whole template keeps a
        failure message down to one readable line.
        """
        start = MARKUP.index("const _bound = (_qp.get('char')")
        return MARKUP[start:MARKUP.index(";", start) + 1]

    def test_binding_derivation_consults_the_bind_option(self):
        self.assertEqual(
            self._bind_derivation(),
            "const _bound = (_qp.get('char') || _qp.get('character') || '')"
            ".trim().slice(0, 24) || ((opts && opts.bind) || '').trim();")

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
        derivation = self._bind_derivation()
        bind_operand = derivation[derivation.index("opts.bind"):]
        # Every spelling of a length cap, not just the one that was there:
        # `.substring(0, 24)` and `.substr(0, 24)` truncate identically.
        for truncator in (".slice(", ".substring(", ".substr("):
            self.assertNotIn(truncator, bind_operand)

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
