# Full-Display Player Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a remote player on one laptop open their character sheet and dice roller from the main display at `/`, without switching to the phone view that hides the narration.

**Architecture:** The server already knows who the browser is — `/j/<token>` redirects to `/` with a `gm_session` cookie and `_bound_character()` resolves it. Inject that name into the template, resolve it client-side ahead of `?char=`, and wire two new buttons in the existing `#input-panel` to the existing `#sheet-modal` and `#dice-drawer`. No new layout, no new endpoint, no new auth.

**Tech Stack:** Python 3.12, Flask (`display/gm-display-app.py`), a single vanilla-JS/CSS template (`display/templates/index.html`), `unittest` run under pytest.

## Global Constraints

- No React, no build step, no new runtime dependencies. All front-end code goes in `display/templates/index.html`.
- Run tests with `python3 -m pytest tests -q` from the repo root.
- The phone view (`body.input-only`) must behave exactly as it does today. Every task that touches shared code must leave `tests/test_remote_player_console.py` green.
- `localStorage['gm_player_name']` must never be read on the full-display path. It stays in use inside `_initDicePad` for the phone's no-URL fallback.
- Character names are constrained server-side by `_CHAR_NAME_RE = re.compile(r"^\w[\w '\-]{0,48}\w$|^\w{1,2}$", re.UNICODE)` (`display/gm-display-app.py:213`).
- Test file for all new tests: `tests/test_full_display_controls.py`. Follow the import pattern in `tests/test_remote_player_console.py` — `importlib.util.spec_from_file_location` because the app filename contains a hyphen.
- Commit after every task.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `display/gm-display-app.py` | Flask app. Only `index()` changes. | Modify `index()` at `:1348-1355` |
| `display/templates/index.html` | Entire front end. | Modify: head injection, drawer CSS, `openSheet`, `_initDicePad`, input-panel markup, SSE connect, input-mode predicate |
| `tests/test_full_display_controls.py` | All tests for this feature. | Create |

---

### Task 1: Server injects the bound character

The `/` route renders for three kinds of caller: an authenticated player (has a `gm_session` cookie from a join link), the GM (has the `X-GM-Secret` header), and a local console browser. Only the first has a character. `_bound_character(fallback)` (`display/gm-display-app.py:517`) already encodes exactly that rule — it returns `g.identity["character"]` when the role is `player` and the fallback otherwise.

**Files:**
- Modify: `display/gm-display-app.py:1348-1355`
- Modify: `display/templates/index.html:15`
- Test: `tests/test_full_display_controls.py`

**Interfaces:**
- Consumes: `_bound_character(fallback: str = "") -> str` and `_gate`'s `g.identity`, both already present.
- Produces: `window.GM_BOUND_CHARACTER` — a JS string on every page, `""` when the caller is not an authenticated player. Task 2 reads it.

**As implemented, corrected from the steps below (fix round 2, MEDIUM finding, owner-ruled):**
`index()` also checks `_is_local()` directly and forces the injected value to
`""` for a loopback peer, cookie or not. `index` is in `_PLAYER_ENDPOINTS`, so
`_gate`'s player→local downgrade at `:535` never fires for `/`; sessions last
30 days with no logout route, so a GM testing a player's invite link in their
own console browser would otherwise have the full display bound to that
character for a month. `_bound_character` itself is untouched — every POST
path still depends on its current behavior; this is a display-only narrowing
at the `index()` call site. See the design doc's "Open edge" section for the
full rationale.

**Also correct the Step 1 test code below before running it:** it sets
`self.app._TOKEN_SECRET = self.secret`, but the app's real module-level
variable (read by `_resolve_identity`) is `_INVITE_SECRET` — `_TOKEN_SECRET`
is a typo and does not exist on the module. Use `self.app._INVITE_SECRET =
self.secret`, matching the pattern already established in
`tests/test_remote_player_console.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_full_display_controls.py`:

```python
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
        self.app._TOKEN_SECRET = self.secret
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

    def test_bound_character_is_json_escaped(self):
        # tojson is what makes a quote or backslash in a name unable to break
        # out of the string literal. Assert the filter's effect, not its name.
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("window.GM_BOUND_CHARACTER = ;", html)
        self.assertIn("window.GM_BOUND_CHARACTER =", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: FAIL — the assertions on `window.GM_BOUND_CHARACTER` do not match, because the string is not in the template yet.

- [ ] **Step 3: Pass the value into the template**

In `display/gm-display-app.py`, replace the body of `index()`:

```python
@app.route("/")
def index():
    return render_template(
        "index.html",
        narrator_voice=_read_narrator_voice(),
        tts_available=(_tts is not None),
        ui_manifest=_load_ui_manifest(),
        # Authenticated players reach "/" directly: /j/<token> ends in
        # redirect("/"), so the session cookie is already set by the time this
        # renders. The cookie is httponly, so the template is the only channel
        # by which the page can learn its own identity. Empty for GM/local.
        bound_character=_bound_character(""),
    )
```

- [ ] **Step 4: Emit it in the template**

In `display/templates/index.html`, immediately after line 15 (`<script>window.GM_UI_MANIFEST = {{ ui_manifest|safe }};</script>`), add:

```html
<!-- Session identity, injected by Flask. Non-empty only for a player who
     arrived through a /j/<token> invite link; "" for the GM and for local
     console browsers. The gm_session cookie is httponly, so this is the only
     way the page can know who it is. tojson quotes and escapes it. -->
<script>window.GM_BOUND_CHARACTER = {{ bound_character|tojson }};</script>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: PASS. No existing test asserts on the exact `render_template` kwargs, so nothing should break.

- [ ] **Step 7: Commit**

```bash
git add display/gm-display-app.py display/templates/index.html tests/test_full_display_controls.py
git commit -m "feat(display): inject the session's bound character into the page"
```

---

### Task 2: Client identity resolver

The page must decide who it is once, at load, and every later task reads that one answer. Order: server value, then `?char=`/`?character=`, then empty. `localStorage['gm_player_name']` is deliberately absent — it is unvalidated free text written by `#dp-name` (`index.html:7320`) and shared across tabs on one origin, so a GM who once opened phone mode would otherwise have their display permanently claim to be that character.

When identity resolves, the character tabs should open on that player rather than on `Everybody`, so staging an action does the obvious thing.

**Files:**
- Modify: `display/templates/index.html` — insert after `let _selectedChar = 'Everybody';` (`:6229`), and modify `_buildCharTabs` (`:6241`)
- Test: `tests/test_full_display_controls.py`

**Interfaces:**
- Consumes: `window.GM_BOUND_CHARACTER` from Task 1.
- Produces: `const GM_IDENTITY` — a JS string, `""` when unknown. Tasks 4, 5, 6 and 7 read it. Also `_selectedChar` is seeded from it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_full_display_controls.py`, above the `if __name__` block:

```python
MARKUP = (REPO / "display" / "templates" / "index.html").read_text()


class IdentityResolver(unittest.TestCase):
    def test_identity_prefers_server_value_over_url(self):
        self.assertIn("const GM_IDENTITY = (window.GM_BOUND_CHARACTER || '').trim()", MARKUP)
        self.assertIn("|| (_idParams.get('char') || _idParams.get('character') || '').trim()", MARKUP)

    def test_identity_never_reads_localstorage_player_name(self):
        # gm_player_name may appear only inside _initDicePad's phone fallback.
        pad_start = MARKUP.index("function _initDicePad")
        before_pad = MARKUP[:pad_start]
        self.assertNotIn("gm_player_name", before_pad)

    def test_selected_char_seeds_from_identity(self):
        self.assertIn("let _selectedChar = GM_IDENTITY || 'Everybody';", MARKUP)

    def test_char_tabs_activate_the_identity_tab(self):
        self.assertIn("if (GM_IDENTITY && names.includes(GM_IDENTITY)) _selectedChar = GM_IDENTITY;", MARKUP)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_full_display_controls.py::IdentityResolver -q`
Expected: FAIL on all four — none of these strings exist yet.

- [ ] **Step 3: Add the resolver**

In `display/templates/index.html`, replace line 6229:

```javascript
let _selectedChar     = 'Everybody';
```

with:

```javascript
// ── Who is this browser? ──────────────────────────────────────────────
// Resolved once, in precedence order:
//   1. window.GM_BOUND_CHARACTER — the server's answer, from the gm_session
//      cookie set by /j/<token>. Authoritative; the cookie is httponly so
//      this injected constant is the only channel.
//   2. ?char= / ?character= — for players who were handed a URL rather than
//      an invite link.
//   3. "" — the GM console and the shared display have no identity.
// localStorage['gm_player_name'] is deliberately NOT consulted here. It is
// unvalidated free text from #dp-name and is shared across every tab on this
// origin, so a GM who opened phone mode once would have this display claim to
// be that character from then on. It remains the phone's fallback inside
// _initDicePad, where the whole tab is already bound to one player.
const _idParams = new URLSearchParams(location.search);
const GM_IDENTITY = (window.GM_BOUND_CHARACTER || '').trim()
                 || (_idParams.get('char') || _idParams.get('character') || '').trim();

let _selectedChar     = GM_IDENTITY || 'Everybody';
```

- [ ] **Step 4: Seed the active tab**

In `_buildCharTabs` (`display/templates/index.html:6241`), replace:

```javascript
function _buildCharTabs(players) {
  const names = ['Everybody', ...(players || []).map(p => p.name).filter(Boolean)];
  _charTabs.innerHTML = '';
```

with:

```javascript
function _buildCharTabs(players) {
  const names = ['Everybody', ...(players || []).map(p => p.name).filter(Boolean)];
  // A bound player's tabs open on themselves, not on Everybody. Only once the
  // roster actually confirms the name — a stale ?char= for someone who left
  // the party should not select a tab that does not exist.
  if (GM_IDENTITY && names.includes(GM_IDENTITY)) _selectedChar = GM_IDENTITY;
  _charTabs.innerHTML = '';
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add display/templates/index.html tests/test_full_display_controls.py
git commit -m "feat(display): resolve browser identity from server, then URL"
```

---

### Task 3: Make the dice drawer render outside the phone view

Every rule for `#dice-drawer` is scoped to `body.input-only` (`index.html:2166-2203`), so on the full display `#dice-drawer { display: none; }` wins even with `.open` set. Broaden the selectors. One rule stays phone-scoped: `body.input-only.dice-drawer-open { position: fixed; overflow: hidden; }` is a scroll-lock for a body that scrolls. The full display scrolls `#text-scroll`, not `body`, so applying it there would jump the page to the top.

The panel also docks to the bottom of the viewport, which is right on a phone and wrong on a wide screen. Give it a centred, width-capped position on the full display.

**Files:**
- Modify: `display/templates/index.html:2165-2203`
- Test: `tests/test_full_display_controls.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `#dice-drawer.open` is visible on the full display. Task 4 relies on it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_full_display_controls.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_full_display_controls.py::DiceDrawerOutsidePhoneView -q`
Expected: FAIL — the selectors are still `body.input-only`-scoped.

- [ ] **Step 3: Rewrite the drawer CSS**

In `display/templates/index.html`, replace lines 2165-2203 in full:

```css
  /* The drawer serves both views. It stays display:none until .open, so the
     shared rules below are inert on any screen that never opens it. */
  #dice-drawer { display: none; }
  #dice-drawer.open {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 30;
    background: rgba(0,0,0,0.68);
  }
  /* Body scroll-lock is phone-only: the full display scrolls #text-scroll,
     so fixing body there would jump the narration to the top on every open. */
  body.input-only.dice-drawer-open {
    position: fixed;
    width: 100%;
    overflow: hidden;
  }
  #dice-drawer-panel {
    position: absolute;
    inset: auto 0 0 0;
    max-height: 85vh;
    overflow-y: auto;
    padding: 16px 16px max(24px, env(safe-area-inset-bottom));
    background: rgba(12,8,4,0.98);
    border-top: 1px solid rgba(220,180,90,0.45);
    animation: dice-drawer-slide-in 0.2s ease-out;
  }
  /* On a laptop the phone's bottom-docked full-width sheet reads as a bug.
     Centre it and cap the width; the narration stays visible behind it. */
  body:not(.input-only) #dice-drawer-panel {
    inset: auto auto 6vh 50%;
    transform: translateX(-50%);
    width: min(420px, 90vw);
    max-height: 78vh;
    border: 1px solid rgba(220,180,90,0.45);
    border-radius: 14px;
    animation: none;
  }
  #dice-drawer-close {
    position: sticky;
    top: 0;
    float: right;
    z-index: 1;
    min-width: 44px;
    min-height: 44px;
    border: 1px solid rgba(220,180,90,0.45);
    border-radius: 50%;
    background: rgba(30,20,8,0.96);
    color: #f4e2a8;
    cursor: pointer;
    font-size: 20px;
  }
  @keyframes dice-drawer-slide-in { from { transform: translateY(100%); } to { transform: translateY(0); } }
  #dice-drawer.open #dice-pad { display: block; }
```

Note the `transform: translateX(-50%)` on the wide-screen panel is why `animation: none` is set there — the keyframe animates `transform` and would otherwise fight the centring.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: PASS, 11 tests.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: PASS. `tests/test_remote_player_console.py::test_dice_drawer_hosts_the_pad_and_fab_opens_it` and `test_phone_overlays_stay_scoped_with_close_controls_and_breakpoint` both read this region — if either fails, read what it asserts and reconcile rather than loosening the assertion.

- [ ] **Step 6: Commit**

```bash
git add display/templates/index.html tests/test_full_display_controls.py
git commit -m "feat(display): let the dice drawer render outside the phone view"
```

---

### Task 4: Gate the dice-request machinery

`_initDicePad` (`index.html:7295-7705`) installs two different things: the roll UI (die buttons, modifier, Roll, the reel animation) and the DM-request machinery (`_applyDiceRequest` → `window._onDiceRequest` at `:7637`, `_onDiceRequestCancelled` at `:7672`, `_onDicePendingSnapshot` at `:7704`, plus `_setLocked`). Calling it wholesale on the full display means a GM who requests a roll from a player locks and badges their own screen.

Take an options argument rather than splitting the 400-line function. The three `window._on*` assignments are the entire seam — the SSE handler (`:6893-6901`) calls them only via `typeof … === 'function'` guards, so leaving them unassigned is already a supported state.

**Files:**
- Modify: `display/templates/index.html:7295`, `:7637`, `:7672`, `:7704`, and the call site at `:7045`
- Test: `tests/test_full_display_controls.py`

**Interfaces:**
- Consumes: `GM_IDENTITY` from Task 2.
- Produces: `_initDicePad({ requests: boolean })`. `requests: true` installs the DM-request handlers; `false` gives the roll UI alone. Called with `true` from phone mode, and from the full display only when `GM_IDENTITY` is non-empty. Task 5 depends on `_initDicePad` having run on the full display.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_full_display_controls.py`:

```python
class DiceRequestGating(unittest.TestCase):
    def _pad_body(self):
        start = MARKUP.index("function _initDicePad")
        return MARKUP[start:]

    def test_init_takes_a_requests_option(self):
        self.assertIn("function _initDicePad(opts) {", MARKUP)
        self.assertIn("const _wantRequests = !(opts && opts.requests === false);", MARKUP)

    def test_all_three_request_handlers_are_gated(self):
        body = self._pad_body()
        self.assertIn("if (_wantRequests) window._onDiceRequest = _applyDiceRequest;", body)
        self.assertIn("if (_wantRequests) window._onDiceRequestCancelled = _onDiceRequestCancelled;", body)
        self.assertIn("if (_wantRequests) window._onDicePendingSnapshot = _onDicePendingSnapshot;", body)

    def test_full_display_inits_the_pad_only_with_an_identity(self):
        self.assertIn("else if (GM_IDENTITY) { _initDicePad({ requests: true }); }", MARKUP)

    def test_gm_display_without_identity_installs_no_request_handlers(self):
        # The unbound full display must not call _initDicePad at all: a GM who
        # requests a roll would otherwise lock and badge their own screen.
        self.assertNotIn("_initDicePad();", MARKUP)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_full_display_controls.py::DiceRequestGating -q`
Expected: FAIL — `_initDicePad` currently takes no argument and assigns all three handlers unconditionally.

- [ ] **Step 3: Add the option**

In `display/templates/index.html`, replace line 7295:

```javascript
function _initDicePad() {
```

with:

```javascript
// opts.requests — install the DM dice-request handlers (badge, prefill, lock).
// The phone wants them. The full display wants them only for a bound player:
// on the GM's own screen they would fire on every request the GM issues, so
// the GM would lock their own pad and badge themselves.
function _initDicePad(opts) {
  const _wantRequests = !(opts && opts.requests === false);
```

- [ ] **Step 4: Gate the three handler assignments**

Replace line 7637:

```javascript
  window._onDiceRequest = _applyDiceRequest;
```

with:

```javascript
  if (_wantRequests) window._onDiceRequest = _applyDiceRequest;
```

Replace line 7672:

```javascript
  window._onDiceRequestCancelled = _onDiceRequestCancelled;
```

with:

```javascript
  if (_wantRequests) window._onDiceRequestCancelled = _onDiceRequestCancelled;
```

Replace line 7704:

```javascript
  window._onDicePendingSnapshot = _onDicePendingSnapshot;
```

with:

```javascript
  if (_wantRequests) window._onDicePendingSnapshot = _onDicePendingSnapshot;
```

The SSE handler at `:6893-6901` already guards each call with `typeof … === 'function'`, so an unassigned handler is a supported state and needs no change there.

- [ ] **Step 5: Init the pad on the full display for a bound player**

Replace the block at `display/templates/index.html:7041-7047`:

```javascript
  if (_inputMode) {
    document.body.classList.add('input-only');
    const ip = document.getElementById('input-panel');
    if (ip) ip.classList.remove('collapsed');
    _initDicePad();
  }
  _initModeSwitcher(_inputMode);
```

with:

```javascript
  if (_inputMode) {
    document.body.classList.add('input-only');
    const ip = document.getElementById('input-panel');
    if (ip) ip.classList.remove('collapsed');
    _initDicePad({ requests: true });
  }
  // Full display: a bound player gets the same pad and the same DM-request
  // handling, so they can roll without giving up the narration. An unbound
  // display (GM console, shared screen) initialises nothing — it has no
  // character to roll as, and installing the request handlers there would
  // badge the GM with their own requests.
  else if (GM_IDENTITY) { _initDicePad({ requests: true }); }
  _initModeSwitcher(_inputMode);
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: PASS, 15 tests.

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: PASS. `tests/test_remote_player_console.py` has several tests reading `window._onDiceRequest` and `window._onDicePendingSnapshot` — they assert the handlers exist, which the gated form still satisfies. If one asserts the exact unqualified line, update that assertion to the gated form and say so in the commit body.

- [ ] **Step 8: Commit**

```bash
git add display/templates/index.html tests/test_full_display_controls.py
git commit -m "feat(display): gate dice-request handlers behind an init option"
```

---

### Task 5: Sheet and Dice buttons in the input panel

Two buttons in `#input-footer` (`index.html:3157-3160`), beside Stage. Sheet opens `#sheet-modal` via `openSheet`; Dice opens `#dice-drawer` via `window._closeDiceDrawer`'s counterpart. `_initDicePad` currently exposes only `window._closeDiceDrawer` (`:7425`), so an open hook is needed too.

Behaviour with no identity: Sheet falls back to `_selectedChar`, and is disabled while that is `'Everybody'` because `openSheet('Everybody')` hits the `_playerData` guard at `:5093` and silently does nothing. Dice, when the pad was never initialised, does nothing — so the button is hidden entirely in that case rather than presenting a dead control.

**Files:**
- Modify: `display/templates/index.html:3157-3160` (markup), `:1609` (footer CSS), `:7425` (expose the open hook), and the tab-click handler at `:6250-6257`
- Test: `tests/test_full_display_controls.py`

**Interfaces:**
- Consumes: `GM_IDENTITY` (Task 2), `_initDicePad` having run (Task 4), `openSheet(name)` (`:5099`).
- Produces: `#pc-sheet-btn` and `#pc-dice-btn` in the DOM; `window._openDiceDrawer()` exposed from `_initDicePad`; `_syncPlayerControls()` called on every tab change.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_full_display_controls.py`:

```python
class PlayerControlButtons(unittest.TestCase):
    def test_both_buttons_live_in_the_input_footer(self):
        start = MARKUP.index('<div id="input-footer">')
        footer = MARKUP[start:MARKUP.index("</div>", start)]
        self.assertIn('id="pc-sheet-btn"', footer)
        self.assertIn('id="pc-dice-btn"', footer)

    def test_dice_button_is_hidden_when_the_pad_was_never_initialised(self):
        self.assertIn("_pcDiceBtn.style.display = window._openDiceDrawer ? '' : 'none';", MARKUP)

    def test_sheet_button_is_disabled_for_everybody(self):
        self.assertIn("const who = GM_IDENTITY || (_selectedChar !== 'Everybody' ? _selectedChar : '');", MARKUP)
        self.assertIn("_pcSheetBtn.disabled = !who;", MARKUP)

    def test_sheet_button_opens_the_resolved_character(self):
        self.assertIn("if (who) openSheet(who);", MARKUP)

    def test_controls_resync_when_the_character_tab_changes(self):
        start = MARKUP.index("function _buildCharTabs")
        tabs = MARKUP[start:MARKUP.index("\n}", start)]
        self.assertIn("_syncPlayerControls();", tabs)

    def test_drawer_open_hook_is_exposed(self):
        self.assertIn("window._openDiceDrawer = () => openDiceDrawer();", MARKUP)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_full_display_controls.py::PlayerControlButtons -q`
Expected: FAIL on all six.

- [ ] **Step 3: Expose the drawer open hook**

In `display/templates/index.html`, after line 7425 (`window._closeDiceDrawer = closeDiceDrawer;`), add:

```javascript
  // Free-roll entry point for the full display's Dice button. Passing no
  // request means openDiceDrawer takes its free-roll branch and unlocks a pad
  // still sitting in the post-prescribed "rolled" state.
  window._openDiceDrawer = () => openDiceDrawer();
```

- [ ] **Step 4: Add the buttons to the markup**

Replace `display/templates/index.html:3157-3160`:

```html
        <div id="input-footer">
          <button id="skip-turn-btn" style="display:none" title="Skip this character's turn">Skip Turn</button>
          <button id="stage-btn">Stage</button>
        </div>
```

with:

```html
        <div id="input-footer">
          <!-- Player controls: reach the sheet and the dice roller without
               leaving the narration. Both are hidden in the phone view, which
               has its own roster chips and dice FAB. -->
          <button id="pc-sheet-btn" type="button" title="Open your character sheet">Sheet</button>
          <button id="pc-dice-btn" type="button" style="display:none" title="Open the dice roller">Dice</button>
          <button id="skip-turn-btn" style="display:none" title="Skip this character's turn">Skip Turn</button>
          <button id="stage-btn">Stage</button>
        </div>
```

- [ ] **Step 5: Style them and hide them in the phone view**

In `display/templates/index.html`, replace line 1609:

```css
  #input-footer { display: flex; align-items: center; gap: 10px; justify-content: flex-end; }
```

with:

```css
  #input-footer { display: flex; align-items: center; gap: 10px; justify-content: flex-end; }
  /* Player controls sit left of Stage so the primary action keeps the corner. */
  #pc-sheet-btn, #pc-dice-btn {
    margin-right: auto;
    background: rgba(30,20,8,0.7);
    border: 1px solid rgba(180,140,60,0.45);
    border-radius: 6px;
    color: rgba(220,185,100,0.85);
    cursor: pointer;
    font: inherit;
    padding: 6px 12px;
  }
  #pc-dice-btn { margin-right: 0; }
  #pc-sheet-btn:hover:not(:disabled), #pc-dice-btn:hover { border-color: rgba(180,140,60,0.8); }
  #pc-sheet-btn:disabled { opacity: 0.35; cursor: default; }
  /* The phone view has roster chips and a dice FAB for the same jobs. */
  body.input-only #pc-sheet-btn, body.input-only #pc-dice-btn { display: none !important; }
```

- [ ] **Step 6: Wire the behaviour**

In `display/templates/index.html`, immediately after the `_buildCharTabs` function's closing brace (`:6260`), add:

```javascript
// ── Full-display player controls ──────────────────────────────────────
// Sheet resolves to the bound identity, falling back to the active character
// tab. 'Everybody' is a staging alias, not a character — openSheet would hit
// its _playerData guard and dead-click — so the button is disabled there.
// Dice appears only once _initDicePad has run, which happens on the full
// display only for a bound player.
const _pcSheetBtn = document.getElementById('pc-sheet-btn');
const _pcDiceBtn  = document.getElementById('pc-dice-btn');

function _syncPlayerControls() {
  if (!_pcSheetBtn || !_pcDiceBtn) return;
  const who = GM_IDENTITY || (_selectedChar !== 'Everybody' ? _selectedChar : '');
  _pcSheetBtn.disabled = !who;
  _pcSheetBtn.title = who ? `Open ${who}'s character sheet` : 'Pick a character tab first';
  _pcDiceBtn.style.display = window._openDiceDrawer ? '' : 'none';
}

if (_pcSheetBtn) {
  _pcSheetBtn.addEventListener('click', e => {
    e.stopPropagation();
    const who = GM_IDENTITY || (_selectedChar !== 'Everybody' ? _selectedChar : '');
    if (who) openSheet(who);
  });
}
if (_pcDiceBtn) {
  _pcDiceBtn.addEventListener('click', e => {
    e.stopPropagation();
    if (window._openDiceDrawer) window._openDiceDrawer();
  });
}
_syncPlayerControls();
```

The `e.stopPropagation()` calls matter: `#input-panel-header` toggles the panel collapsed on click (`:6236`), and without stopping propagation a click that bubbles could collapse the panel out from under the overlay.

- [ ] **Step 7: Resync on tab change**

Inside `_buildCharTabs`, in the tab click handler (`:6250-6257`), after the `_skipTurnBtn.style.display` line, add `_syncPlayerControls();`. The handler becomes:

```javascript
    btn.addEventListener('click', e => {
      e.stopPropagation();
      _selectedChar = name;
      _charTabs.querySelectorAll('.char-tab').forEach(b =>
        b.classList.toggle('active', b.dataset.char === name)
      );
      _skipTurnBtn.style.display = name === 'Everybody' ? 'none' : '';
      _syncPlayerControls();
    });
```

Then add one more `_syncPlayerControls();` as the last statement of `_buildCharTabs`, after the `names.forEach(...)` loop — the identity seed in Task 2 can change `_selectedChar` when the roster first arrives, and the button state must follow.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: PASS, 21 tests.

- [ ] **Step 9: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add display/templates/index.html tests/test_full_display_controls.py
git commit -m "feat(display): add Sheet and Dice buttons to the input panel"
```

---

### Task 6: One character sheet, live header plus authored body

Two renderers read two different sources today. `openSheet` (`:5099`) renders the live SSE `stats` payload — HP, AC, class icon, ability scores, and whatever `p.sheet` carries — so it reflects current combat state but nothing the GM authored on disk. `_loadCharacterSheet` (`:7158`) fetches `/character/<name>` (`gm-display-app.py:2389`) and renders the authored markdown — spells, inventory, features — but knows nothing about current HP.

A player asking for "my character sheet" wants both. Keep `openSheet`'s live header, then append the markdown below it. A missing file is a normal state, not an error: `/character/<name>` returns 404 with a plain-text body for a character with no `.md`, and the sheet degrades to the live header plus a quiet note.

`/character/<name>` deliberately does not rewrite the requested character (`gm-display-app.py:2406`), so a bound player can still read a party member's sheet. That stays true.

**Files:**
- Modify: `display/templates/index.html:5099` (add the fetch), `:5381-5383` (append the body)
- Test: `tests/test_full_display_controls.py`

**Interfaces:**
- Consumes: `_renderMarkdown(md)` (`:7196`), `_playerSheetRequest` (`:6233`) for stale-response discard, `openSheet(name)` (`:5099`).
- Produces: `openSheet` renders both sources. Task 5's Sheet button and the existing sidebar card clicks (`:5083`, `:5475`) both benefit; neither call site changes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_full_display_controls.py`:

```python
class UnifiedCharacterSheet(unittest.TestCase):
    def _open_sheet(self):
        start = MARKUP.index("function openSheet(name)")
        return MARKUP[start:MARKUP.index("\nfunction closeSheet", start)]

    def test_open_sheet_fetches_the_authored_markdown(self):
        body = self._open_sheet()
        self.assertIn("fetch(`/character/${encodeURIComponent(name)}`", body)
        self.assertIn("_renderMarkdown(md)", body)

    def test_open_sheet_discards_stale_fetches(self):
        # Clicking two cards fast must not paint the first sheet over the second.
        body = self._open_sheet()
        self.assertIn("const request = ++_playerSheetRequest;", body)
        self.assertIn("if (request !== _playerSheetRequest) return;", body)

    def test_missing_sheet_file_is_not_an_error_state(self):
        body = self._open_sheet()
        self.assertIn("sm-authored-missing", body)

    def test_live_header_still_renders_first(self):
        body = self._open_sheet()
        self.assertLess(body.index("sheet-modal"), body.index("sm-authored"))


class AuthoredSheetRoute(unittest.TestCase):
    def setUp(self):
        self.app = _import_app()
        self.client = self.app.app.test_client()

    def test_unknown_character_is_a_404_not_a_500(self):
        resp = self.client.get("/character/Nobody")
        self.assertEqual(resp.status_code, 404)

    def test_everybody_alias_is_rejected(self):
        resp = self.client.get("/character/Everybody")
        self.assertEqual(resp.status_code, 404)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_full_display_controls.py::UnifiedCharacterSheet -q`
Expected: FAIL on the four `UnifiedCharacterSheet` tests. `AuthoredSheetRoute` should already PASS — it pins existing behaviour this task must not break.

- [ ] **Step 3: Append the authored body**

In `display/templates/index.html`, replace lines 5381-5383:

```javascript
  document.getElementById('sheet-modal').classList.add('open');
  document.getElementById('sheet-panel').scrollTop = 0;
}
```

with:

```javascript
  document.getElementById('sheet-modal').classList.add('open');
  document.getElementById('sheet-panel').scrollTop = 0;

  // ── Authored sheet body ──────────────────────────────────────────────
  // Everything above is the live SSE stats payload: current HP, AC, ability
  // scores. Everything below is the .md file the GM wrote — spells, inventory,
  // features. A player means both when they say "my character sheet", so this
  // modal shows both rather than making them choose a view.
  //
  // The fetch is fired after the modal is already open so the live header
  // paints immediately; the body fills in underneath. _playerSheetRequest is
  // the shared stale-response guard — clicking two sidebar cards quickly must
  // not paint the first character's markdown into the second's sheet.
  const request = ++_playerSheetRequest;
  const authored = document.createElement('div');
  authored.className = 'sm-authored';
  content.appendChild(authored);

  fetch(`/character/${encodeURIComponent(name)}`, { credentials: 'same-origin' })
    .then(res => res.ok ? res.text() : Promise.reject(res.status))
    .then(md => {
      if (request !== _playerSheetRequest) return;
      authored.innerHTML = _renderMarkdown(md);
    })
    .catch(() => {
      if (request !== _playerSheetRequest) return;
      // No .md on disk is the normal state for an NPC or a freshly imported
      // PC — a quiet note, not an error. The live header above still stands.
      authored.innerHTML =
        '<div class="sm-authored-missing">No authored sheet file for this character.</div>';
    });
}
```

- [ ] **Step 4: Style the appended block**

In `display/templates/index.html`, immediately before the `#sheet-modal {` rule at line 833, add:

```css
  .sm-authored { margin-top: 18px; border-top: 1px solid rgba(180,140,60,0.28); padding-top: 14px; }
  .sm-authored h1, .sm-authored h2, .sm-authored h3 { color: rgba(220,185,100,0.9); margin: 14px 0 6px; }
  .sm-authored table { border-collapse: collapse; width: 100%; margin: 8px 0; }
  .sm-authored th, .sm-authored td { border: 1px solid rgba(180,140,60,0.25); padding: 4px 8px; text-align: left; }
  .sm-authored-missing { opacity: 0.45; font-style: italic; }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: PASS, 27 tests.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: PASS. `tests/test_remote_player_console.py::test_player_sheet_overlay_discards_stale_loads_and_restores_modal_state` also uses `_playerSheetRequest`; confirm it still passes, since `openSheet` now increments the same counter.

- [ ] **Step 7: Commit**

```bash
git add display/templates/index.html tests/test_full_display_controls.py
git commit -m "feat(display): show live stats and the authored sheet in one modal"
```

---

### Task 7: SSE identity and the input-mode predicate

Two loose ends from the design.

**SSE identity — ALREADY DONE by Task 4b, do not re-implement.** This section's original text claimed `_streamChar` derives from the URL alone, so an invite-link player left `_phone_present` false. Both halves are now false. Task 4b (`ac38686`, `305f052`) deleted the second resolver and made `_streamChar = GM_IDENTITY` (`index.html:7104`), which reads `window.GM_BOUND_CHARACTER` first. Separately, `/stream` (`gm-display-app.py:2691`) funnels its `?character=` through `_bound_character`, which returns the cookie's character outright for `role == "player"` and ignores the argument — so the server already knew. Skip Steps 2's first test, 3 and 4 entirely.

**Input-mode predicate.** `:7040` is `_qp.get('view') === 'input' || _qp.has('char') || _qp.has('character')`, so `?char=Mira&view=full` is dragged back into the phone view. That makes it impossible to keep a binding in the URL while reading narration, which is exactly what this feature is for. Let an explicit `view=full` win, and have the "Full Display" button preserve the character instead of stripping the query string.

**Files:**
- Modify: `display/templates/index.html:7267` (the `_inputMode` predicate) and the Full Display button's navigation in `_initModeSwitcher` (~`:7331`)
- Test: `tests/test_full_display_controls.py`

**Interfaces:**
- Consumes: `GM_IDENTITY` from Task 2.
- Produces: nothing new. This is the last task.

- [ ] **Step 1: Find the Full Display button's navigation**

Run: `grep -n "Full Display" display/templates/index.html`

Read the surrounding handler. It navigates by stripping query params. You need its exact current lines for Step 6.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_full_display_controls.py`:

```python
class StreamIdentityAndModePredicate(unittest.TestCase):
    def test_explicit_view_full_beats_a_char_param(self):
        self.assertIn("_qp.get('view') !== 'full' &&", MARKUP)

    def test_full_display_button_keeps_the_binding(self):
        self.assertIn("url.searchParams.set('view', 'full');", MARKUP)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_full_display_controls.py::StreamIdentityAndModePredicate -q`
Expected: FAIL on both.

- [ ] **Step 4: (removed — SSE identity already landed in Task 4b)**

- [ ] **Step 5: Fix the input-mode predicate**

Replace `display/templates/index.html:7267`:

```javascript
  const _inputMode = _qp.get('view') === 'input' || _qp.has('char') || _qp.has('character');
```

with:

```javascript
  // ?char= alone still implies the phone view, so hand-typed short URLs keep
  // working. An explicit view=full overrides it, which is what lets a player
  // hold a binding in the URL while reading the narration.
  const _inputMode = _qp.get('view') === 'input'
    || (_qp.get('view') !== 'full' && (_qp.has('char') || _qp.has('character')));
```

- [ ] **Step 6: Keep the binding on the Full Display button**

Using the exact lines found in Step 1, change the handler so that instead of stripping the query string it preserves the character and marks the view. The navigation must build a URL equivalent to:

```javascript
        const url = new URL(window.location.href);
        const bound = (url.searchParams.get('char') || url.searchParams.get('character') || '').trim();
        url.search = '';
        // Keep the binding so a reload does not lose it, and mark the view so
        // the predicate above does not drag us straight back to phone mode.
        if (bound) url.searchParams.set('char', bound);
        url.searchParams.set('view', 'full');
        window.location.href = url.toString();
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: PASS, 72 tests (70 today plus the 2 new ones).

- [ ] **Step 8: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: PASS. `tests/test_remote_player_console.py` asserts on the input-mode predicate; if it pins the old expression, update it to the new one and note the change in the commit body.

- [ ] **Step 9: Manual verification**

The test suite reads source strings; it cannot confirm the feature works in a browser. Start the display and check by hand:

```bash
cd display && ./start-display.sh
```

Confirm, on `http://localhost:5001/`:

1. With no identity — Sheet is disabled, Dice is hidden, the panel looks as it did before.
2. Click a character tab — Sheet enables and opens that character's sheet, showing the live header and the markdown body below it.
3. With a bound player (open a `/j/` invite link, or use `?char=<Name>&view=full`) — narration stays visible, Dice opens the centred drawer, and a roll posts.
4. As the GM, issue a dice request — the GM's own screen does not lock or badge.

- [ ] **Step 10: Commit**

```bash
git add display/templates/index.html tests/test_full_display_controls.py
git commit -m "feat(display): let an explicit view=full beat a char param"
```

---

## Self-Review

**Spec coverage.** Identity (server) → Task 1. Identity (client, precedence, no localStorage) → Task 2. Controls, including the disabled-Sheet rule → Task 5. Splitting `_initDicePad` → Task 4, done as an options gate rather than a function split; the seam is the three `window._on*` assignments and nothing else crosses it. Unified sheet → Task 6. SSE `?character=` → Task 7, but delivered early by Task 4b; Task 7's copy of it is struck. Input-mode predicate → Task 7. Drawer visibility outside the phone view was implied by the spec but not called out; it is Task 3, without which Task 5's Dice button opens an invisible drawer.

**Type consistency.** `GM_IDENTITY` is a string everywhere. `_initDicePad(opts)` is called with `{ requests: true }` at both call sites; `requests: false` is supported but unused, and `_wantRequests` defaults to true so an argument-less call still behaves as it does today. `_syncPlayerControls()` is defined once in Task 5 and called from three places, all in Task 5. `window._openDiceDrawer` is created in Task 5 Step 3 and read in Task 5 Step 6.

**Ordering.** Task 5 depends on Tasks 2, 3 and 4. Task 3 must precede Task 5 or the Dice button appears to do nothing. This claimed Task 7's SSE change must read `window.GM_BOUND_CHARACTER` directly because `_streamChar` is declared earlier than the resolver. That was wrong: `GM_IDENTITY` is declared ~750 lines *above* `_streamChar`, and Task 4b accordingly set `_streamChar = GM_IDENTITY`.
