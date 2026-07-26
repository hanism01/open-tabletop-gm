"""Full-display player controls: server identity injection and markup contracts."""
import importlib.util
import pathlib
import re
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

# Task 5 added the un-collapse to this branch, deliberately restating the
# constant rather than loosening it: #input-panel ships collapsed, .collapsed
# hides #input-body, and #input-body holds the dice-request badge and the
# player-control buttons. Without this line a bound player on the full display
# gets a shut panel and no way into any of it. The phone branch above has
# always done the same thing, which is why PHONE_CALL_SITE carries it too.
FULL_DISPLAY_CALL_SITE = """
  else if (GM_IDENTITY) {
    const ip = document.getElementById('input-panel');
    if (ip) ip.classList.remove('collapsed');
    if (_inputArrow) _inputArrow.textContent = '\u25bc';
    _initDicePad({ bind: GM_IDENTITY });
  }
"""

# Stable landmarks bracketing both call sites, used only to window the failure
# message: a bare assertIn against the whole template reports a 2.5MB haystack,
# which is not a diagnosable failure. The full-display call site sits ~600
# chars past the opening anchor, so a fixed-width window sliced from the anchor
# printed the phone block and a comment and never reached the offending line —
# hence the closing landmark, which is the last statement of the same block.
CALL_SITE_ANCHOR = "const _view = (_qp.get('view') || '').trim().toLowerCase();"
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


class InputPanelExpandsForABoundPlayer(unittest.TestCase):
    """#input-footer is inside #input-body, which .collapsed hides outright.

    The panel ships collapsed and only the phone branch un-collapsed it, so a
    bound player landing on "/" from an invite link saw a closed "Party Input"
    bar and none of the controls inside it. The other two auto-expands
    (staged-input arriving, the autorun countdown) do not fire on a fresh load
    with an empty queue, so the bound full display has to expand it itself.
    """

    def test_the_panel_still_ships_collapsed(self):
        # The precondition. If this ever stops being true the expand below
        # becomes dead code and should be reconsidered, not silently kept.
        self.assertIn('<div id="input-panel" class="collapsed">', MARKUP)
        self.assertIn("#input-panel.collapsed #input-body { display: none; }", MARKUP)

    def test_the_footer_sits_inside_the_collapsible_body(self):
        # Source-order proxy, not a parse: every test in this module asserts on
        # template text, there is no DOM here. #input-footer opens after
        # #input-body opens and before #input-panel's block ends at the
        # <!-- Character sheet modal --> that follows it.
        body_at = MARKUP.index('<div id="input-body">')
        footer_at = MARKUP.index('<div id="input-footer">')
        panel_block_end = MARKUP.index('<div id="sheet-modal">')
        self.assertLess(body_at, footer_at)
        self.assertLess(footer_at, panel_block_end)

    def test_the_bound_full_display_expands_the_panel(self):
        # Against the template. The previous form asserted
        # FULL_DISPLAY_CALL_SITE contained its own text, which passes against
        # an empty template — the same tautology caught in the arrow test.
        at = NORM_MARKUP.index(_norm("else if (GM_IDENTITY) {"))
        self.assertIn("if (ip) ip.classList.remove('collapsed');",
                      NORM_MARKUP[at:at + 300])

    def test_the_call_site_constant_still_demands_the_uncollapse(self):
        # Deliberately a self-check on the constant, and named as one: it is
        # what stops a future edit loosening FULL_DISPLAY_CALL_SITE back to a
        # bare _initDicePad call, which would silently un-pin the template.
        self.assertIn("if (ip) ip.classList.remove('collapsed');",
                      _norm(FULL_DISPLAY_CALL_SITE))

    def test_both_branches_expand_the_panel(self):
        # Two call sites, two expands — the phone's has always been there.
        self.assertEqual(NORM_MARKUP.count("if (ip) ip.classList.remove('collapsed');"), 2)


class DiceRequestBadgeVisibility(unittest.TestCase):
    """The badge is the only path from a GM request to the roll pad."""

    def test_badge_is_visible_in_both_views(self):
        # Was `body.input-only #dice-request-badge:not([hidden])`, so a bound
        # player on the full display recorded the request and rendered no cue.
        # The positive assertion alone is a substring of the old scoped rule;
        # the assertNotIn is what actually catches the regression.
        self.assertIn("\n  #dice-request-badge:not([hidden]) { display: flex; }", MARKUP)
        self.assertNotIn("body.input-only #dice-request-badge:not([hidden])", MARKUP)

    def test_badge_still_obeys_its_hidden_attribute(self):
        # showDiceRequestBadge / hideDiceRequestBadge drive [hidden]; unscoping
        # the visible rule must not have outranked the hidden one.
        self.assertIn("#dice-request-badge[hidden] { display: none !important; }", MARKUP)


class TemplateAssertions:
    """assertIn against MARKUP, windowed to a named region.

    Mixin, deliberately not a TestCase — a bare assertIn against the 2.5MB
    template prints the whole template on failure, which is not a diagnosable
    message. Same reasoning as DiceRequestGating._assert_call_site above; this
    is the general form for pins that are not call sites. Confirmed live: the
    N4 mutation last round printed
    `AssertionError: 'const ready = ...' not found in '<!DOCTYPE html>...'`.
    """

    def assertInRegion(self, needle, anchor, span=800, until=None):
        # Uniqueness first. MARKUP.find takes the first match, so a future
        # duplicate anchor would silently window the wrong region and the
        # assertion would report on code it was never about — the same
        # silent-mistarget class _pad_body and _bind_derivation guard against.
        #
        # `until` ends the region on a terminator instead of a character
        # budget (review round 4). A fixed span cannot know where the construct
        # it is windowing ends, so it runs past the closing brace and a string
        # pinned as belonging to *this* function is satisfied by the next one.
        count = MARKUP.count(anchor)
        if count != 1:
            self.fail(f"region anchor {anchor!r} appears {count} times in the "
                      f"template; expected exactly one. Expected {needle!r} "
                      f"in its region.")
        at = MARKUP.index(anchor)
        if until is None:
            end = at + span
        else:
            end = MARKUP.find(until, at)
            if end == -1:
                self.fail(f"region terminator {until!r} never appears after "
                          f"anchor {anchor!r}; the region is unbounded.")
            end += len(until)
        region = MARKUP[at:end]
        if needle in region:
            return
        self.fail(f"not found in the {len(region)}-char region after {anchor!r}.\n"
                  f"  expected: {needle}\n"
                  f"  region:\n    {region}")


class PlayerControlButtons(TemplateAssertions, unittest.TestCase):
    SYNC = "function _syncPlayerControls() {"

    _DIV_TAG = re.compile(r'<div\b|</div>')

    def _footer(self):
        # Depth-counted, not "up to the first </div>": #input-footer's own
        # children are flat today, but a truncation on the first closing tag
        # silently shortens the haystack the moment any child nests a div,
        # turning every assertNotIn below into a false pass (review finding
        # #4 — a nested div made assertNotIn('aria-disabled', ...) pass even
        # with an aria-disabled attribute present, just past the truncation).
        start = MARKUP.index('<div id="input-footer">')
        depth = 0
        for m in self._DIV_TAG.finditer(MARKUP, start):
            depth += -1 if m.group() == '</div>' else 1
            if depth == 0:
                return MARKUP[start:m.end()]
        raise AssertionError("no matching close tag found for #input-footer")

    def test_both_buttons_live_in_the_input_footer(self):
        footer = self._footer()
        self.assertIn('id="pc-sheet-btn"', footer)
        self.assertIn('id="pc-dice-btn"', footer)

    def test_both_buttons_are_hidden_in_the_phone_view(self):
        # The phone has roster chips for the sheet and a dice FAB for the pad.
        self.assertIn(
            "body.input-only #pc-sheet-btn, body.input-only #pc-dice-btn "
            "{ display: none !important; }", MARKUP)

    def test_dice_button_is_hidden_when_the_pad_was_never_initialised(self):
        self.assertIn("_pcDiceBtn.style.display = window._openDiceDrawer ? '' : 'none';", MARKUP)

    HELPER = "function _sheetTargetFor() {"
    # The helper's own extent, not a character budget. `span=300` reached ~130
    # chars into _syncPlayerControls, so a string pinned as belonging to the
    # helper could have been satisfied from inside the sync (review round 4).
    HELPER_END = "\n}\n"

    def test_sheet_button_resolves_who_and_excludes_everybody(self):
        # 'Everybody' is a staging alias, not a character: openSheet('Everybody')
        # hits its _playerData guard and dead-clicks.
        self.assertInRegion(
            "const who = GM_IDENTITY || (_selectedChar !== 'Everybody' ? _selectedChar : '');",
            self.HELPER, until=self.HELPER_END)

    def test_the_readiness_rule_is_written_exactly_once(self):
        # Review D1. Two copies — one in the sync, one in the click handler —
        # could drift, and the drift that matters is silent: a sync that
        # enables on a looser rule than the handler accepts is the dead click
        # this control has been fixed for twice. Counting, not just asserting
        # presence, is what makes a re-duplication fail here.
        self.assertEqual(MARKUP.count("_playerData[who]"), 1)
        self.assertEqual(MARKUP.count("Object.hasOwn(_playerData, who)"), 1)
        self.assertEqual(
            MARKUP.count("const who = GM_IDENTITY || "
                         "(_selectedChar !== 'Everybody' ? _selectedChar : '');"), 1)
        self.assertInRegion(
            "return { who, ready: !!(who && Object.hasOwn(_playerData, who) && _playerData[who]) };",
                            self.HELPER, until=self.HELPER_END)

    # The click handler's extent, same reasoning as HELPER_END. Its true extent
    # is 381 chars, so the old span=400 here and span=500 below both ran past
    # the closing brace into `if (_pcDiceBtn) {` (review round 5).
    HANDLER = "_pcSheetBtn.addEventListener('click'"
    HANDLER_END = "\n}\n"

    def test_both_the_sync_and_the_handler_go_through_the_helper(self):
        self.assertEqual(MARKUP.count("const { who, ready } = _sheetTargetFor();"), 2)
        self.assertInRegion("const { who, ready } = _sheetTargetFor();", self.SYNC, span=300)
        self.assertInRegion("const { who, ready } = _sheetTargetFor();",
                            self.HANDLER, until=self.HANDLER_END)

    def test_sheet_button_ships_disabled(self):
        # Review M1: the fail-safe default. Between HTML parse and the first
        # _syncPlayerControls() the button would otherwise be live and dead-
        # click, and it would stay that way permanently if anything threw
        # earlier in the inline script. #pc-dice-btn already got this right
        # with style="display:none". The sync enables it when data is real.
        # Windowed by the footer slice itself rather than a fixed span: the
        # button sat 551 chars past the <div id="input-footer"> anchor, so one
        # more comment line would have broken a span=600 window and failed for
        # the wrong reason (review D4).
        self.assertIn('<button id="pc-sheet-btn" type="button" disabled', self._footer())

    def test_dice_button_ships_hidden(self):
        # Review F4, and the mirror of test_sheet_button_ships_disabled — which
        # cites this attribute as prior art while nothing actually pinned it.
        # Measured: removing style="display:none" from the tag left the entire
        # suite green (336 passed / 6 deselected, and 6 passed in the browser
        # harness). Same fail-safe reason as the sheet button:
        # window._openDiceDrawer does not exist until _initDicePad has run, and
        # a Dice button that opens nothing is worse than no Dice button.
        #
        # The browser harness cannot cover this and this test is not redundant
        # with it: on an unbound display #input-panel is still collapsed so the
        # button has no box either way, and on a bound display
        # _syncPlayerControls() has already rewritten .style.display by the time
        # the page has loaded. The shipped attribute only governs the window
        # before the first sync — which is also the permanent state if anything
        # earlier in the inline script throws.
        self.assertIn('<button id="pc-dice-btn" type="button" style="display:none"',
                      self._footer())

    def test_the_static_disabled_state_carries_its_own_explanation(self):
        # If the script never runs, the shipped attributes are all the user
        # gets, so they must not claim the sheet is one click away.
        footer = self._footer()
        self.assertIn('title="No character sheet available yet"', footer)
        self.assertIn('aria-label="Sheet — no character sheet available yet"', footer)
        self.assertNotIn('title="Open your character sheet"', footer)

    def test_sheet_button_is_disabled_until_the_character_has_sheet_data(self):
        # Review finding 3: enabling on a truthy GM_IDENTITY alone is a silent
        # dead click. _playerData is empty until updateStats merges the first
        # SSE `stats` frame, and stays empty forever if the DM never ran
        # /gm load — while both syncs that matter (the top-level one and the
        # one after the pad-init block) run before any frame arrives.
        self.assertInRegion(
            "return { who, ready: !!(who && Object.hasOwn(_playerData, who) && _playerData[who]) };",
                            self.HELPER, until=self.HELPER_END)
        self.assertInRegion("_pcSheetBtn.disabled = !ready;", self.SYNC, span=300)

    REASON = "const reason = ready ?"
    # The reason block runs to the end of _syncPlayerControls, and that is the
    # bound these pins want: same reasoning as HELPER_END and HANDLER_END. The
    # region is 356 chars, so the span=400 that used to sit here overran the
    # enclosing function by 44 and could have been satisfied from the next one.
    REASON_END = "\n}\n"

    def test_the_disabled_sheet_button_says_why_it_is_disabled(self):
        self.assertInRegion("Pick a character tab first", self.REASON, until=self.REASON_END)
        self.assertInRegion("No sheet data for ", self.REASON, until=self.REASON_END)

    def test_the_reason_reaches_the_accessible_name_not_only_the_tooltip(self):
        # Review M2: `title` on a *disabled* control is rendered at the UA's
        # discretion, so it cannot be the only channel. A disabled button's
        # accessible name is not discretionary — assistive tech still reaches
        # it and reads it — so the same string goes there too.
        self.assertInRegion("_pcSheetBtn.title = reason;", self.REASON, until=self.REASON_END)
        self.assertInRegion(
            "_pcSheetBtn.setAttribute('aria-label', `Sheet — ${reason}`);",
            self.REASON, until=self.REASON_END)

    def test_the_accessible_name_still_starts_with_the_visible_label(self):
        # WCAG 2.5.3 label-in-name: voice control users say "click Sheet", so
        # an aria-label that does not contain the visible label breaks them.
        self.assertInRegion("`Sheet — ${reason}`", self.REASON, until=self.REASON_END)

    # Every receiver that names this button outright, either quote style,
    # tolerant of whitespace around the dot and inside the call. Anchored on a
    # *call expression* rather than on proximity: prose discussing the rule
    # mentions the attribute and the button, but does not spell out a whole
    # setAttribute call, so this does not have to be run over blanked source.
    ARIA_DISABLED_WRITE = re.compile(
        r"""(?:_pcSheetBtn"""
        r"""|(?:getElementById|querySelector)\(\s*['"]#?pc-sheet-btn['"]\s*\))"""
        r"""\s*\.\s*setAttribute\(\s*['"]aria-disabled['"]""")

    def test_aria_disabled_is_not_duplicated_onto_the_native_attribute(self):
        # Considered and declined. `disabled` already maps to the same
        # accessible state; ARIA-in-HTML's first rule is to use the native
        # attribute, and adding aria-disabled beside it changes nothing about
        # tooltip delivery — the actual M2 concern — while adding a second
        # source of truth to keep in sync.
        #
        # Two directions, no proximity scan. Rounds 4 and 5 both went to a scan
        # (first over CSS selectors, then over a hand-blanked copy of the
        # template) because the attribute can be set from markup or from
        # script, and both times the scan read the template's own prose as if
        # it were code. The measure of how narrow that footing was: today's
        # single occurrence of the attribute is in a comment, 238 chars from a
        # `#pc-sheet-btn` mention later in the same paragraph, against a
        # 160-char window that needs the match to *end* inside it — so 90
        # characters of prose stood between the rule and a failure about a
        # defect that does not exist. (Re-wrapping alone could not have closed
        # that: the three `\n  // ` line prefixes in between are worth 15
        # characters even if the whole paragraph collapsed onto one line. It
        # takes an edit to the words.) Blanking the prose first only moved the
        # fragility — and on the current template it moved it far enough that
        # the scan matched nothing at all, since the only occurrence sits in a
        # comment the blanker erased.
        #
        # THE TRADE, STATED PLAINLY (review F3). The retired scan was not a
        # weaker detector than this pair — it was a stronger one. It caught any
        # syntax whatever within 160 chars of a mention of this button. Four
        # forms were checked against both; the old scan caught all four, and
        # this pair catches three of them:
        #
        #   1. aria-disabled="true" on the tag           — caught (footer)
        #   2. _pcSheetBtn.setAttribute('aria-disabled'  — caught (regex)
        #   3. _pcSheetBtn.setAttribute("aria-disabled"  — caught (regex)
        #   4. getElementById('pc-sheet-btn')
        #        .setAttribute('aria-disabled', ...)     — caught (regex)
        #
        # Forms 3 and 4 were missed by the first version of this replacement
        # (one exact single-quoted string) and are why the regex exists.
        #
        # Still not covered, and not worth a lexer to cover:
        #   - an alias: `const b = _pcSheetBtn; b.setAttribute('aria-disabled', …)`
        #   - a property write: `_pcSheetBtn.ariaDisabled = 'true'`
        #   - any other receiver expression — `.closest(…)`, a NodeList loop,
        #     an element handed in as a function parameter
        #   - a computed attribute name: `setAttribute('aria-' + 'disabled', …)`
        #
        # That residue is the price of not reading prose as code. The browser
        # harness can assert the rendered attribute directly if any of it ever
        # matters — that is a DOM question, and it is the right tool for it.
        self.assertNotIn('aria-disabled', self._footer())
        # findall, not assertNotIn against MARKUP: a failing assertNotIn prints
        # its whole haystack, and the haystack here is the 2.5MB template — the
        # same undiagnosable failure TemplateAssertions exists to avoid. The
        # matched text is the whole diagnosis and it goes in the message.
        hits = self.ARIA_DISABLED_WRITE.findall(MARKUP)
        self.assertEqual(
            hits, [],
            f"{hits} — an aria-disabled write targeting #pc-sheet-btn appears "
            "in the template. `disabled` already carries that accessible "
            "state; a second source of truth for it has to be kept in sync by "
            "hand.")

    def test_the_disabled_button_stays_hoverable(self):
        # #stage-btn:disabled and #dm-help-btn:disabled both set
        # pointer-events: none, which suppresses hit-testing and with it any
        # tooltip. This rule deliberately does not.
        #
        # This pins the button's *own* rule and nothing else. Whether some
        # broader rule elsewhere in the cascade hands it pointer-events: none
        # is a question about the computed style, which no source-string test
        # can answer; the hand-rolled selector scan that used to sit here
        # tried, and got it wrong in both directions (round 4 — see the
        # report). getComputedStyle answers it in one line, so it belongs to
        # the browser-harness task.
        self.assertIn("#pc-sheet-btn:disabled { opacity: 0.35; cursor: default; }", MARKUP)

    def test_player_data_is_declared_above_the_sync(self):
        # `const _playerData = {}` — reading it from _syncPlayerControls before
        # its declaration would be a temporal-dead-zone ReferenceError, and the
        # top-level _syncPlayerControls() call runs at parse-order position.
        self.assertLess(MARKUP.index("const _playerData = {}"),
                        MARKUP.index("function _syncPlayerControls"))

    def test_controls_resync_when_player_data_is_wiped(self):
        # payload.clear deletes every _playerData key. Without a re-sync the
        # Sheet button stays enabled against data that is gone.
        wipe = "for (const key of Object.keys(_playerData)) delete _playerData[key];"
        idx = MARKUP.index(wipe)
        self.assertIn("_syncPlayerControls();", MARKUP[idx:idx + 200])

    def test_sheet_button_opens_the_resolved_character(self):
        # Re-derives the same gate as the sync rather than trusting the
        # button's attribute state, so a click that somehow lands before or
        # against a stale sync still cannot reach openSheet's warn-and-return.
        self.assertInRegion("if (ready) openSheet(who);",
                            self.HANDLER, until=self.HANDLER_END)

    def test_both_click_handlers_stop_propagation(self):
        # Review finding 2: the reason the brief gave for these calls — that a
        # bubbling click would reach #input-panel-header's collapse toggle — is
        # impossible. The header div *closes* before #input-body opens, and
        # #input-footer is inside #input-body, so the header is a sibling of
        # these buttons and never sees their clicks (pinned by
        # test_the_panel_header_is_not_an_ancestor_of_the_footer).
        #
        # They still earn their keep: two document-level close-on-outside-click
        # handlers (the TTS voice menu and the mode-switcher menu) would
        # otherwise fire, so opening the Phone Mode picker and then clicking
        # Sheet would leave that menu open behind the modal.
        start = MARKUP.index("const _pcSheetBtn")
        block = MARKUP[start:MARKUP.index("\n_syncPlayerControls();", start)]
        self.assertEqual(block.count("e.stopPropagation();"), 2)

    @staticmethod
    def _char_tabs():
        start = MARKUP.index("function _buildCharTabs")
        return MARKUP[start:MARKUP.index("\n}", start)]

    def test_controls_resync_when_the_character_tab_changes(self):
        # Sliced to the click handler, not to the whole function. A bare
        # `assertIn(..., tabs)` is satisfied by the trailing re-sync below and
        # stays green with the per-click one deleted — mutation-checked.
        tabs = self._char_tabs()
        handler_at = tabs.index("btn.addEventListener('click'")
        handler = tabs[handler_at:tabs.index("});", handler_at)]
        self.assertIn("_syncPlayerControls();", handler)

    def test_controls_resync_when_the_roster_rebuilds_the_tabs(self):
        # _buildCharTabs's identity seed can move _selectedChar the first time
        # a roster arrives, which changes the Sheet button's target.
        tabs = self._char_tabs()
        handler_at = tabs.index("btn.addEventListener('click'")
        after_loop = tabs[tabs.index("});", handler_at):]
        self.assertIn("_syncPlayerControls();", after_loop)

    def test_controls_resync_after_the_pad_is_initialised(self):
        # window._openDiceDrawer does not exist until _initDicePad has run,
        # which happens below _buildCharTabs([]). Without a re-sync here the
        # Dice button stays hidden until the first SSE stats payload arrives.
        pad_block_end = MARKUP.index("_initModeSwitcher(_inputMode);")
        after = MARKUP[pad_block_end:pad_block_end + 600]
        self.assertIn("_syncPlayerControls();", after)


class DiceButtonIsFreeRollOnly(unittest.TestCase):
    """The Dice button must never replay a request the player dismissed.

    _diceRequestDismissBtn adds to _dismissedRequestIds and hides the badge but
    leaves _pendingDiceRequest set. Passing it into the free-roll hook would
    mean: player declines a Stealth check, clicks Dice for a d6, and gets a pad
    locked to the GM's 1d20 spec whose Roll posts the dismissed request_id.
    """

    def test_open_hook_is_exposed_and_takes_no_request(self):
        self.assertIn("window._openDiceDrawer = () => openDiceDrawer();", MARKUP)

    def test_dice_button_calls_the_hook_with_no_argument(self):
        self.assertIn("if (window._openDiceDrawer) window._openDiceDrawer();", MARKUP)

    def test_the_hook_never_names_the_pending_request(self):
        start = MARKUP.index("window._openDiceDrawer =")
        self.assertNotIn("_pendingDiceRequest", MARKUP[start:MARKUP.index(";", start)])

    def test_a_pending_request_is_replayed_only_from_the_badge(self):
        self.assertEqual(MARKUP.count("openDiceDrawer(_pendingDiceRequest)"), 1)
        idx = MARKUP.index("openDiceDrawer(_pendingDiceRequest)")
        self.assertIn("_diceRequestOpenBtn.addEventListener", MARKUP[idx - 200:idx])


class ShippedSourceComments(unittest.TestCase):
    def test_dice_pad_comment_no_longer_denies_a_full_display_opener(self):
        self.assertNotIn("Nothing opens it on the full display yet", MARKUP)

    def test_no_plan_task_numbers_in_shipped_source(self):
        # Plan task numbers are meaningless to anyone reading the template
        # after the plan is gone.
        self.assertEqual(re.findall(r"Task \d", MARKUP), [])


class CollapseArrowStaysInSync(unittest.TestCase):
    """#input-toggle-arrow is the panel's only open/closed affordance.

    Convention set by the header's own toggle: collapsed reads ▲ ("click to
    open"), expanded reads ▼. An un-collapse that leaves the arrow at ▲ makes
    the first header click read as a no-op — it collapses the panel and sets ▲
    again, so the control gives no state feedback until the second click.
    """

    def test_the_toggle_sets_the_convention(self):
        self.assertIn(
            "_inputArrow.textContent = _inputPanel.classList.contains('collapsed') "
            "? '▲' : '▼';", MARKUP)

    def test_the_bound_full_display_updates_the_arrow(self):
        # Against the template, not against FULL_DISPLAY_CALL_SITE — asserting
        # the constant contains its own text is a tautology.
        at = NORM_MARKUP.index(_norm("else if (GM_IDENTITY) {"))
        self.assertIn("if (_inputArrow) _inputArrow.textContent = '▼';",
                      NORM_MARKUP[at:at + 300])

    def test_only_the_phone_uncollapse_may_skip_the_arrow(self):
        # The phone is the one exception: its header is hidden outright, so
        # there is no arrow to keep in sync.
        self.assertIn("body.input-only #input-panel-header { display: none !important; }", MARKUP)
        sites, idx = [], 0
        while True:
            idx = MARKUP.find("classList.remove('collapsed')", idx)
            if idx == -1:
                break
            # (preceding text, the site itself) — the discriminator has to come
            # from *before* the site. Review M3: the previous version keyed on
            # "_initDicePad({ bind: GM_IDENTITY });" appearing in a fixed
            # 120-char window after the site, which both branches satisfy once
            # the arrow line is gone (removing it pulls the call into the
            # window), so swapping which branch carries the arrow still passed.
            sites.append((MARKUP[max(0, idx - 300):idx], MARKUP[idx:idx + 160]))
            idx += 1
        self.assertEqual(len(sites), 4, f"expected four un-collapse sites, found {len(sites)}")
        without_arrow = [s for s in sites if "_inputArrow.textContent = '▼';" not in s[1]]
        self.assertEqual(
            len(without_arrow), 1,
            "exactly one un-collapse — the phone branch, whose header is hidden — "
            f"may skip the arrow update; found {len(without_arrow)}: {without_arrow}")
        self.assertIn("document.body.classList.add('input-only');", without_arrow[0][0],
                      "the un-collapse that skips the arrow is not the phone branch")


class StopPropagationHasARealTarget(unittest.TestCase):
    """Why the two e.stopPropagation() calls exist (review finding 2)."""

    def test_the_panel_header_is_not_an_ancestor_of_the_footer(self):
        # Structural, not merely ordering: the header's own closing tag sits
        # immediately before #input-body opens, and #input-footer is inside
        # #input-body. So the brief's stated mechanism — a footer click
        # bubbling into the header's collapse toggle — cannot happen.
        self.assertIn('<span id="input-toggle-arrow">▲</span>\n'
                      '  </div>\n'
                      '  <div id="input-body">', MARKUP)
        self.assertLess(MARKUP.index('<div id="input-body">'),
                        MARKUP.index('<div id="input-footer">'))

    def test_nothing_else_toggles_the_collapsed_class(self):
        # If a delegated/document-level collapse toggle ever appears, the
        # sibling argument above stops being the whole story.
        self.assertEqual(MARKUP.count("classList.toggle('collapsed')"), 1)

    def test_the_two_outside_click_closers_still_exist(self):
        # These are what the stopPropagation calls actually suppress: without
        # them, opening the Phone Mode picker and clicking Sheet leaves the
        # menu open behind the modal.
        self.assertEqual(MARKUP.count("document.addEventListener('click', () => {"), 2)
        self.assertIn("document.querySelectorAll('.tts-voice-menu')"
                      ".forEach(m => { m.hidden = true; });", MARKUP)


class ModePredicate(unittest.TestCase):
    def _predicate_block(self):
        # Same CALL_SITE_ANCHOR/CALL_SITE_END pair used by DiceRequestGating's
        # diagnostic slice above — windowed so a false-positive substring
        # match elsewhere in the 7,000-line template (e.g. inside a comment)
        # can't pass this test.
        start = MARKUP.index(CALL_SITE_ANCHOR)
        end = MARKUP.index(CALL_SITE_END, start)
        return MARKUP[start:end]

    def _full_display_handler(self):
        # 'full-mode-btn' only appears once (the Full Display button built
        # for the phone view); the first appendChild(btn) after it closes
        # the same click handler.
        start = MARKUP.index("btn.id = 'full-mode-btn';")
        end = MARKUP.index("document.body.appendChild(btn);", start)
        return MARKUP[start:end]

    def test_explicit_view_full_beats_a_char_param(self):
        self.assertIn("_view !== 'full' &&", self._predicate_block())

    def test_view_is_read_once_and_case_normalized(self):
        # Both clauses must compare against the same lowercased/trimmed
        # read, not call _qp.get('view') a second time — a capital-F
        # ?view=Full must not silently fall through to the char/character
        # shorthand.
        self.assertIn("(_qp.get('view') || '').trim().toLowerCase()", self._predicate_block())
        self.assertEqual(self._predicate_block().count("_qp.get('view')"), 1,
                          "view should be read once into _view, not re-read per clause")

    def test_full_display_button_keeps_the_binding(self):
        handler = self._full_display_handler()
        # Both assertions matter: 'view' alone lands on ?view=full with no
        # binding, which for a URL-bound (cookie-less) player resolves
        # GM_IDENTITY to "" and silently drops their dice pad and sheet.
        self.assertIn("if (bound) url.searchParams.set('char', bound);", handler)
        self.assertIn("url.searchParams.set('view', 'full');", handler)


if __name__ == "__main__":
    unittest.main()
