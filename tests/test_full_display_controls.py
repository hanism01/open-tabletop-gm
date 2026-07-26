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
    _initDicePad({ bind: GM_IDENTITY });
  }
"""

FULL_DISPLAY_CALL_SITE = (
    "else if (GM_IDENTITY) { _initDicePad({ bind: GM_IDENTITY }); }")

# Stable landmarks bracketing both call sites, used only to window the failure
# message: a bare assertIn against the whole template reports a 2.5MB haystack,
# which is not a diagnosable failure. The full-display call site sits ~600
# chars past the opening anchor, so a fixed-width window sliced from the anchor
# printed the phone block and a comment and never reached the offending line —
# hence the closing landmark, which is the last statement of the same block.
CALL_SITE_ANCHOR = "const _inputMode = _qp.get('view') === 'input'"
CALL_SITE_END = "_initModeSwitcher(_inputMode);"


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

    def _pad_code(self):
        """_pad_body with whole-line `//` comments dropped.

        For assertions about what the pad *does*, where the prose explaining
        why it does not do something else would otherwise trip a substring
        match. Trailing comments are left in place deliberately: a line like
        `const x = GM_IDENTITY; // ...` is code and should still trip.
        """
        return "\n".join(line for line in self._pad_body().splitlines()
                         if not line.strip().startswith("//"))

    def _assert_call_site(self, snippet):
        """Assert `snippet` appears in the template, ignoring whitespace.

        On failure, print the expected snippet next to the whole call-site
        block (CALL_SITE_ANCHOR through CALL_SITE_END) — never the whole
        template, and never a fixed-width window that stops short of the
        line that actually differs.
        """
        needle = _norm(snippet)
        if needle in NORM_MARKUP:
            return
        anchor_at = NORM_MARKUP.find(_norm(CALL_SITE_ANCHOR))
        if anchor_at == -1:
            self.fail(f"call-site anchor {CALL_SITE_ANCHOR!r} is gone from the "
                      f"template; expected call site was:\n  {needle}")
        end_at = NORM_MARKUP.find(_norm(CALL_SITE_END), anchor_at)
        end_at = (end_at + len(_norm(CALL_SITE_END))) if end_at != -1 else (anchor_at + 1200)
        actual = NORM_MARKUP[anchor_at:end_at]
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

    def test_init_takes_only_a_bind_option(self):
        self.assertIn("function _initDicePad(opts) {", MARKUP)
        # Task 4b removed opts.requests. Both call sites always wanted the
        # DM-request handlers, so the flag was invariantly true and the three
        # `if (_wantRequests)` guards never varied. What actually keeps the
        # GM's own screen clear of their own dice requests is the *call-site*
        # guard — the unbound full display never calls _initDicePad at all
        # (pinned by test_the_pad_is_called_from_exactly_two_call_sites and
        # test_full_display_inits_the_pad_only_with_an_identity).
        self.assertNotIn("opts.requests", MARKUP)
        self.assertNotIn("_wantRequests", MARKUP)

    def test_all_three_request_handlers_install_whenever_the_pad_runs(self):
        # The remaining contract: initialising the pad installs all three
        # handlers, unconditionally. Each is pinned as a statement standing
        # alone at the function's own indent level, so re-gating one behind a
        # fresh `if (...)` on the same line fails here rather than passing on
        # a substring match.
        body = self._pad_body()
        for assignment in ("window._onDiceRequest = _applyDiceRequest;",
                           "window._onDiceRequestCancelled = _onDiceRequestCancelled;",
                           "window._onDicePendingSnapshot = _onDicePendingSnapshot;"):
            self.assertIn(f"\n  {assignment}", body,
                          f"{assignment!r} is not an ungated top-level statement of _initDicePad")

    def test_the_pad_is_called_from_exactly_two_call_sites(self):
        # A third call site is how the unbound full display would regain the
        # DM-request handlers — a GM who requests a roll would then lock and
        # badge their own screen. Neither of the two legitimate sites may be
        # duplicated or joined by an unguarded top-level call; the guard on
        # each is pinned separately (see the two tests below).
        #
        # DO NOT RELAX THIS COUNT. test_full_display_inits_the_pad_only_with
        # _an_identity asserts the full-display snippet appears in the
        # template, which a *commented-out* call site would still satisfy —
        # this count is the only test that catches that, because _call_sites()
        # skips commented occurrences. The two are mutually load-bearing.
        sites = self._call_sites()
        self.assertEqual(
            len(sites), 2,
            "expected exactly two _initDicePad(...) call sites (phone mode and "
            f"the full display's bound-player branch), found {len(sites)}: {sites}")

    def test_phone_call_site_stays_guarded_by_input_mode(self):
        # The phone's own call site, pinned whole. It must not have moved or
        # been re-guarded. As of Task 4b it passes `{ bind: GM_IDENTITY }`:
        # _initDicePad no longer reads the URL itself, and GM_IDENTITY is the
        # one resolver that reads ?char=/?character= (server value first).
        self._assert_call_site(PHONE_CALL_SITE)

    def test_full_display_inits_the_pad_only_with_an_identity(self):
        # HIGH 1 fix: the identity must come from the call site, not from an
        # unconditional read of GM_IDENTITY inside _initDicePad itself.
        #
        # `else if (GM_IDENTITY)` verbatim also pins the *polarity* of the
        # guard: `if (!GM_IDENTITY)` would be the unbound GM console installing
        # its own request handlers, which is the entire reason this gate exists.
        #
        # This is a substring assertion, so it stays green against a
        # commented-out call site. What rejects that is
        # test_the_pad_is_called_from_exactly_two_call_sites, which counts only
        # uncommented occurrences — do not relax that count without replacing
        # this pin with something that parses.
        self._assert_call_site(FULL_DISPLAY_CALL_SITE)

    def test_the_two_call_sites_form_one_if_else_chain(self):
        # Both snippets above are asserted independently, so on their own they
        # do not pin that the full-display branch is the phone branch's `else`.
        # A re-chained `if (_fabOnly) { _initFab(); } else if (GM_IDENTITY)
        # { _initDicePad(...) }` contains both snippets verbatim while
        # behaviourally dropping the pad for a bound full display and
        # double-initialising it on a phone. The gap between the two must
        # therefore hold nothing executable: no statement terminator and no
        # further `if (`.
        phone, full = _norm(PHONE_CALL_SITE), _norm(FULL_DISPLAY_CALL_SITE)
        phone_at = NORM_MARKUP.find(phone)
        full_at = NORM_MARKUP.find(full)
        self.assertNotEqual(phone_at, -1, "phone call site missing")
        self.assertNotEqual(full_at, -1, "full-display call site missing")
        self.assertLess(phone_at, full_at, "full-display branch precedes the phone branch")
        between = NORM_MARKUP[phone_at + len(phone):full_at]
        self.assertNotIn(";", between,
                         f"a statement sits between the two branches: {between!r}")
        self.assertNotIn("if (", between,
                         f"another `if (` sits between the two branches: {between!r}")

    BIND_DECLARATION = "const _bound = "

    def _bind_derivation(self):
        """The `const _bound = ...;` statement, up to its own semicolon.

        Asserting against this slice rather than the whole template keeps a
        failure message down to one readable line. Uniqueness is asserted for
        the same reason _pad_body asserts it: a second matching declaration
        would otherwise be silently ignored by MARKUP.index.
        """
        self.assertEqual(
            MARKUP.count(self.BIND_DECLARATION), 1,
            f"expected exactly one {self.BIND_DECLARATION!r} statement")
        start = MARKUP.index(self.BIND_DECLARATION)
        return MARKUP[start:MARKUP.index(";", start) + 1]

    def test_binding_derivation_consults_only_the_bind_option(self):
        self.assertEqual(
            self._bind_derivation(),
            "const _bound = ((opts && opts.bind) || '').trim();")

    def test_the_pad_never_reads_the_url(self):
        # Task 4b: _initDicePad takes its binding from the call site alone.
        # Reading ?char= here as well made the URL operand *win* over
        # opts.bind and truncated it to 24 chars, while _CHAR_NAME_RE permits
        # 50. Once Task 7 routes ?char=X&view=full to the full-display branch,
        # GM_IDENTITY would hold the full name and #dp-name a 24-char slice,
        # so _applyDiceRequest's case-insensitive match of #dp-name against
        # the GM's target list would silently never fire for a 25+ char name.
        code = self._pad_code()
        for url_read in ("URLSearchParams", "location.search", "_qp"):
            self.assertNotIn(url_read, code,
                             f"_initDicePad still reads the URL via {url_read!r}")

    def test_the_pad_keeps_the_phone_localstorage_last_resort(self):
        # Reached only when nothing binds this browser — a phone opened with
        # no ?char= and no session cookie. Still the correct behaviour, and
        # dropping the URL read must not have taken it with it. The
        # full-display path cannot reach it: that branch requires a non-empty
        # GM_IDENTITY, which is exactly what it passes as opts.bind.
        body = self._pad_body()
        self.assertIn("nameEl.value = localStorage.getItem('gm_player_name') || '';", body)

    def test_bind_operand_is_not_truncated(self):
        # Fix round 2 (Important finding): _CHAR_NAME_RE permits names up to
        # 50 chars and scripts/gm_invite.py applies no length cap when
        # minting a join token, so opts.bind (the caller's resolved identity)
        # must survive intact. Truncating it here would desync #dp-name's
        # value from the GM_IDENTITY used elsewhere (_selectedChar,
        # _loadCharacterSheet), so a GM request for the player's full name
        # would silently fail to match on their own screen — the exact harm
        # HIGH 1 was about, reintroduced via a different path. Stated
        # separately from the exact-equality test above so the *reason*
        # survives any future re-statement of the derivation.
        derivation = self._bind_derivation()
        bind_operand = derivation[derivation.index("opts.bind"):]
        # Every spelling of a length cap, not just the one that was there:
        # `.substring(0, 24)` and `.substr(0, 24)` truncate identically.
        for truncator in (".slice(", ".substring(", ".substr("):
            self.assertNotIn(truncator, bind_operand)

    def test_binding_derivation_never_reads_gm_identity_directly(self):
        # The binding must arrive as opts.bind from the caller, never by
        # _initDicePad reaching for GM_IDENTITY itself: the guard that decides
        # whether this browser has an identity at all lives at the call site,
        # and reading the resolver here would install the pad's binding even
        # on a path that deliberately declined to pass one. Asserted against
        # _pad_code: the comment explaining this very rule names GM_IDENTITY.
        self.assertNotIn("GM_IDENTITY", self._pad_code())


class SseStreamIdentity(unittest.TestCase):
    def test_stream_character_comes_from_the_one_identity_resolver(self):
        # _streamChar used to re-derive the character from the URL alone, a
        # second identity resolver with its own precedence. GM_IDENTITY is a
        # dependency-free const declared far above connect(), so the SSE
        # subscription can just use it.
        #
        # Consolidation only — /stream's own handler passes the param through
        # _bound_character, which discards it for an authenticated player in
        # favour of the session cookie's character, so the param decides
        # anything only for a local/GM browser, where GM_IDENTITY resolves from
        # the very same URL params. (The plan's Task 7 rationale — that
        # _phone_present stays false for invite-link players — is wrong for
        # that reason.)
        self.assertIn("const _streamChar = GM_IDENTITY;", MARKUP)
        # _sp existed only to feed _streamChar.
        self.assertNotIn("const _sp = ", MARKUP)

    def test_identity_resolver_is_declared_above_the_stream_char(self):
        # The dependency the assertion above relies on. A future edit that
        # moved the resolver below connect() would make _streamChar a
        # ReferenceError at load (const, temporal dead zone) — silent-ish in
        # a browser but total: the whole script block would stop executing.
        self.assertLess(MARKUP.index("const GM_IDENTITY ="),
                        MARKUP.index("const _streamChar ="))


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
