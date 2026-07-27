# Character Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-character invite links with one unguessable table URL that serves a character picker, so a device chooses its identity once, explicitly, and can always choose again.

**Architecture:** A four-word slug identifies the table. `GET /t/<slug>` renders a picker listing the roster with each character's claim state; tapping one `POST`s to `/claim`, which mints the same `gm_session` cookie `/j/<token>` mints today. `RevocationStore.active` — already keyed by `character.lower()` — remains the sole claim store. The session token gains a real `role` field so a characterless "display only" cookie is a first-class, narrowly-scoped identity rather than an empty-string ambiguity.

**Tech Stack:** Python 3.12, Flask (`display/gm-display-app.py`), stdlib-only token/slug modules (`display/tokens.py`, `display/table.py`), two vanilla-JS/CSS templates (`display/templates/index.html`, `display/templates/picker.html`), `unittest` run under pytest, pytest-playwright for `browser`-marked tests.

## Global Constraints

- No React, no build step, **no new runtime dependencies**. All front-end code lives in `display/templates/*.html`.
- Run tests with `python3 -m pytest tests -q` from the repo root. Baseline at the start of this plan, verified: **351 passed, 112 subtests passed**.
- `-m "not browser"` skips the Playwright suite. Browser tests run by default and pass in this environment today.
- TDD is mandatory: failing test first, minimal implementation, green, commit. **Commit after every task.**
- The table URL is `/t/<four-words-hyphenated>`. Four words drawn **independently, with replacement**, from a flat **2048-word** list. Unguessability rests on the rate limiter — `_rate_ok` (20/60s/IP, `display/gm-display-app.py:159-160`), charged **only on failing requests** at `/t/` and `/claim` — and on the tunnel being up only while a session is in play. Do **not** present the bit count as load-bearing anywhere in shipped code or docs; the limiter is the argument.
- Vocabulary is fantasy-flavoured, shipped as a plain data file.
- The slug lives for the campaign; `gm_table.py rotate` mints a new one, kills the old, **and regenerates the signing secret** so every existing cookie dies with the leaked URL (effective for a running server at its next restart). An unknown slug returns **404**, indistinguishable from a typo.
- **Remote play is tunnel-or-nothing.** `_ALLOWED_ORIGINS` (`display/gm-display-app.py:457-460`) covers localhost and `$GM_PUBLIC_HOST` only, and `_set_session_cookie` marks the cookie `Secure` for any non-loopback host — so a `--lan` player at `http://192.168.x.x:5001/t/<slug>` gets 403 on `/claim`, and even past that the browser drops the cookie over plain http. Pre-existing (`docs/REMOTE-PLAY.md:140` concedes it), but the picker is now the only entry path, so it is stated here rather than discovered at the table.
- Bare `/` keeps its current behaviour: 403 for an unauthenticated non-loopback peer. The picker adds exactly two public endpoints, `table` and `claim`.
- A taken character **never** names the person holding it. The app knows characters, not people.
- **A returning owner always wins, with no confirmation step.** A claim over DM-held control succeeds immediately.
- Claim enforcement is `RevocationStore.set_active`, which already revokes the prior sid for the same `player_id` (`display/tokens.py:213-222`). No new store file for claims.
- `player_id` is `character.lower()` everywhere.
- Character names are constrained server-side by `_CHAR_NAME_RE = re.compile(r"^\w[\w '\-]{0,48}\w$|^\w{1,2}$", re.UNICODE)` (`display/gm-display-app.py:213`).
- Error table (spec §"Error handling and edge cases"), implemented verbatim:

  | Situation | Behaviour |
  |---|---|
  | Unknown or rotated slug | 404, no distinction from a typo |
  | Cookie valid, character since released | Picker, with a note explaining why |
  | Cookie valid, sid revoked by a newer claim | Picker, with a note |
  | Two devices claim the same character | `set_active` revokes the older; it lands on the picker at its next request |
  | Character renamed in the roster | Claim orphans. The picker hides claims whose key is absent from the current roster |
  | Server restart mid-session | Nothing lost — cookies survive, `active` is persisted |
  | Claim attempt on a taken character | 409, roster refreshes |

- Read the **Spec corrections** section at the end of this document before starting. Several load-bearing claims in the spec are wrong about the current tree; the tasks below are written against reality.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `display/wordlist.txt` | The 2048-word fantasy vocabulary. One lowercase ASCII word per line. Data only. | Create |
| `display/table.py` | Slug minting, validation, persistence, rotation. Stdlib only. | Create |
| `display/tokens.py` | HMAC session tokens + `RevocationStore`. Gains `role` in the payload, `clear_active`, `DM_SID`; loses `mint_join` and the jti machinery. | Modify |
| `display/gm-display-app.py` | Flask app: gate, `/t/<slug>`, `/claim`, `index()`, `/player-input/dice` hardening. Loses `/j/<token>`. | Modify |
| `display/templates/picker.html` | The picker page. Self-contained; shares nothing with `index.html`. | Create |
| `display/templates/index.html` | The play surface. Identity resolution, layout preference, mode switcher. | Modify |
| `scripts/gm_table.py` | GM CLI: show / rotate / list / dm / release. | Create |
| `scripts/gm_invite.py` | The invite CLI. | Delete (Task 14) |
| `tests/test_table_slug.py` | Word list + `make_slug` + `TableStore`. | Create |
| `tests/test_picker.py` | `/t/<slug>`, `/claim`, the display role's endpoint set, roster states. | Create |
| `tests/test_gm_table.py` | The new CLI. | Create |
| `tests/test_browser_picker.py` | Picker in a real browser (`browser` marker). | Create |
| `tests/test_tokens.py` | Retargeted off `mint_join`/jti; new `role` coverage. | Modify |
| `tests/test_auth_gate.py` | One line: `/j/garbage` → `/t/garbage`. | Modify |
| `tests/test_full_display_controls.py` | Identity-resolver and mode-predicate contracts. | Modify |
| `tests/test_browser_player_controls.py` | `?char=` vehicle for the `__proto__` test. | Modify |
| `tests/test_join_route.py` | `/j/<token>`. | Delete (Task 14) |
| `tests/test_gm_invite.py` | The invite CLI. | Delete (Task 14) |
| `.gitignore` | Ignore `display/.table.json`. | Modify (Task 5) |

---

# Phase A — Independent fixes

These three ship green on their own, in this order, before any picker work. Each is worth landing even if the picker never does.

---

### Task 1: Delete the `?char=` identity fallback

The defect the redesign was born from. `display/templates/index.html:6366-6367` resolves the page's identity from the URL when the server sends nothing, and `index()` (`display/gm-display-app.py:1372`) sends `""` for every loopback browser. So at the shared display, "Phone Mode → Kara" writes `?char=Kara` into the URL, "Full Display" preserves it (`index.html:7376`), and the screen keeps acting as Kara with no way out. A GM revoke kills the cookie's authority while the parameter keeps driving.

Deleting the fallback means a hand-typed `/?char=Mira` URL stops binding anyone. That flow has no replacement until Task 9 lands `/claim`. This is the accepted cost, stated in the spec; do not soften it with a compatibility shim.

Independence caveat: unlike Tasks 2 and 3, this is not a pure standalone fix. It removes the only non-cookie binding path, and its replacement (`/claim`, Task 9) does not exist yet. In the interim a device binds only through a `/j/<token>` invite link, which keeps working until Task 14 — the GM mints links with `scripts/gm_invite.py` exactly as today. Ship it anyway; the defect it closes is live at the shared display.

**Files:**
- Modify: `display/templates/index.html:6345-6367`
- Modify: `tests/test_full_display_controls.py:90-93`
- Modify: `tests/test_browser_player_controls.py:70-84`

**Interfaces:**
- Consumes: `window.GM_BOUND_CHARACTER` — a JS string injected at `index.html:21`, `""` for any loopback or unauthenticated caller.
- Produces: `const GM_IDENTITY` — still a `const` string declared at the same place in the same `<script>` block, now derived from `window.GM_BOUND_CHARACTER` alone. `const _idParams` is gone. Tasks 11 and 12 both edit this region again.

- [ ] **Step 1: Retarget the source-pinning test**

In `tests/test_full_display_controls.py`, replace the body of `test_identity_prefers_server_value_over_url` (lines 91-93) and rename it:

```python
    def test_identity_comes_from_the_server_alone(self):
        # The URL is no longer an identity channel. ?char= used to win whenever
        # the server sent "" — which it does for every loopback browser
        # (gm-display-app.py index(), the _is_local() override) — so the shared
        # display kept acting as whoever Phone Mode last selected, with no way
        # to clear it. The server's injected value is now the only source.
        self.assertIn("const GM_IDENTITY = (window.GM_BOUND_CHARACTER || '').trim();", MARKUP)
        self.assertNotIn("_idParams", MARKUP)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_full_display_controls.py -q -k identity_comes_from_the_server_alone`
Expected: FAIL — the one-line form of the declaration is not in the template, and `_idParams` still is.

- [ ] **Step 3: Delete the fallback**

In `display/templates/index.html`, replace lines 6345-6367 (the comment block through the `GM_IDENTITY` declaration) with:

```javascript
// ── Who is this browser? ──────────────────────────────────────────────
// window.GM_BOUND_CHARACTER — the server's answer, from the gm_session
// cookie. Authoritative and sole: the cookie is httponly, so this injected
// constant is the only channel by which the page can learn its identity.
// "" for the GM console, for local browsers, and for anyone unclaimed.
//
// The URL is deliberately NOT an identity channel. ?char= / ?character=
// used to win whenever the server sent "" — which it does for every
// loopback browser — so "Phone Mode → Kara" then "Full Display" left the
// shared screen still acting as Kara: input posted as her, and her dice
// requests were consumed there instead of reaching her phone. Two clicks
// in, no click out. A GM revoke killed the cookie's authority while the
// parameter kept driving.
//
// localStorage['gm_player_name'] is deliberately NOT consulted here either.
// It is unvalidated free text from #dp-name, shared across every tab on this
// origin. Two reads of it remain downstream, neither an alternative to this
// resolver: _initDicePad's own #dp-name field falls back to it only when
// unbound, and _loadCharacterSheet's fallback chain reads it last.
// This constant is also the SSE subscription's character (_streamChar below).
const GM_IDENTITY = (window.GM_BOUND_CHARACTER || '').trim();
```

- [ ] **Step 4: Run the retargeted test**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: PASS (all of it — the other identity tests pin `_selectedChar`, `_streamChar` and the call sites, none of which changed).

- [ ] **Step 5: Retarget the browser `__proto__` test to a live vehicle**

`tests/test_browser_player_controls.py:70-84` reaches `__proto__` through `?char=__proto__`, which no longer resolves to anything. Left alone the test passes vacuously and its docstring becomes a lie. Replace the whole function with a version that drives the same guard through the roster path, which is the reachable route today:

```python
def test_proto_pollution_via_a_roster_name_does_not_enable_the_sheet(gm_display, context):
    # A bare bracket lookup, _playerData['__proto__'], resolves to
    # Object.prototype — truthy even against the empty-roster fixture — which
    # used to read as "ready", enable the Sheet button, and let
    # openSheet('__proto__') clear its own falsy guard and render a sheet built
    # from the prototype object. Object.hasOwn in both _sheetTargetFor and
    # openSheet's guard is the fix; this exercises both through the real DOM.
    #
    # The vehicle used to be ?char=__proto__. The URL is no longer an identity
    # channel, so the reachable route is now a roster-driven selection, which
    # is what a real click on a character tab does.
    page = gm_display.open(context)
    page.evaluate("() => { _selectedChar = '__proto__'; _syncPlayerControls(); }")
    expect(page.locator("#pc-sheet-btn")).to_be_disabled()

    page.evaluate("() => openSheet('__proto__')")
    expect(page.locator("#sheet-modal")).not_to_have_class("open")
```

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest tests -q`
Expected: PASS, 351 passed, 112 subtests passed. If `test_proto_pollution_via_a_roster_name_does_not_enable_the_sheet` fails, do **not** weaken it — `_syncPlayerControls` and `_sheetTargetFor` are the code under test and a red here is a real finding.

- [ ] **Step 7: Commit**

```bash
git add display/templates/index.html tests/test_full_display_controls.py tests/test_browser_player_controls.py
git commit -m "fix(display): the URL is no longer an identity channel

?char= won whenever the server sent '' — which it does for every loopback
browser — so Phone Mode then Full Display left the shared screen still
bound to a character with no way to clear it."
```

---

### Task 2: Harden `/player-input/dice`

`player_dice` (`display/gm-display-app.py:2197-2297`) is the only write endpoint that persists to the text log and broadcasts without calling `_rate_ok`. Compare `player_input` (`:2164-2165`), which does. It also never checks the resolved character: `_bound_character` at `:2211` returns `ident["character"]` for a player role, and after Task 6 a display-role identity resolves to `""` — a blank name would post `" rolls 1d20: [17] = 17"` into the narration feed and would match nothing in the pending-request correlation at `:2275-2278`.

Note for the browser suite: `tests/conftest.py:28-36` documents that every bound page in `tests/test_browser_player_controls.py` shares one `_rate_ok` bucket (keyed on the module's single `CF-Connecting-IP`), currently ~6 writes per module against a limit of 20/60s. Adding the limiter here makes dice rolls count. The module rolls twice; the new total is ~8. Do not add more bound page loads to that module without giving them their own `CF-Connecting-IP`.

**Files:**
- Modify: `display/gm-display-app.py:2209-2212`
- Test: `tests/test_csrf_rate.py`

**Interfaces:**
- Consumes: `_rate_ok(ip: str) -> bool` (`:169`), `_rate_key() -> str` (`:163`), `_bound_character(fallback: str = "") -> str` (`:517`), all present.
- Produces: `/player-input/dice` returns `429` with body `"Too Many Requests"` past 20 writes per 60s per IP, and `400` with JSON `{"error": "no character"}` when the resolved character is empty. Task 7 relies on the 400.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_csrf_rate.py`, inside `class CsrfRateTests` (read `tests/test_csrf_rate.py:22-58` first for `_player_headers` and the fixture shape, and reuse them):

```python
    def test_dice_is_rate_limited_like_every_other_write(self):
        # The only unthrottled write that persists to the log and broadcasts.
        h = self._player_headers(ip="203.0.113.77")
        body = {"spec": "1d20", "modifier": 0}
        codes = [self.client.post("/player-input/dice", headers=h, json=body).status_code
                 for _ in range(25)]
        self.assertIn(429, codes)

    def test_dice_rejects_an_empty_resolved_character(self):
        # A blank name would post " rolls 1d20: [17] = 17" into the narration
        # feed and would correlate against no pending request.
        h = self._player_headers(character="", ip="203.0.113.78")
        r = self.client.post("/player-input/dice", headers=h,
                             json={"character": "", "spec": "1d20"})
        # 400 is what this task produces; 403 is what Task 7 produces once a
        # characterless player cookie stops resolving at all. Both mean "no
        # blank roller reaches the log", which is the claim. Asserted as a
        # pair from the start so no later task has to edit this test.
        self.assertIn(r.status_code, (400, 403))
```

`_player_headers` mints a cookie via `tokens.mint_session(character.lower(), character, "c", secret=self.secret)` and sets it on `self.client`; a `character=""` call therefore mints a characterless session token directly — exactly the shape Task 7 later stops resolving, which is why the assertion accepts either status.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_csrf_rate.py -q`
Expected: FAIL — no 429 appears in 25 requests, and the empty-character POST returns 200 (neither 400 nor 403).

- [ ] **Step 3: Add the guards**

In `display/gm-display-app.py`, replace lines 2209-2211 (the blank line after the docstring through the `character = ...` assignment):

```python
    # The only write that persists to the log and broadcasts; it was the one
    # without a limiter. Same window as player_input (20/60s per IP).
    if not _rate_ok(_rate_key()):
        return "Too Many Requests", 429
    data = request.get_json(force=True, silent=True) or {}
    character = _bound_character(re.sub(r"[`\\$]", "", str(data.get("character", "Player"))[:50]).strip() or "Player")
    # A display-role identity resolves to "" here (see _bound_character). A
    # blank name would post " rolls 1d20: [17] = 17" into the narration feed
    # and would match nothing in the pending-request correlation below.
    if not character:
        return jsonify({"error": "no character"}), 400
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_csrf_rate.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest tests -q`
Expected: PASS, 353 passed. If `tests/test_browser_player_controls.py` reports a 429-shaped failure, the module has exceeded its shared bucket — give the offending page its own `CF-Connecting-IP` per the note in `tests/conftest.py:28-36`.

- [ ] **Step 6: Commit**

```bash
git add display/gm-display-app.py tests/test_csrf_rate.py
git commit -m "fix(display): rate-limit /player-input/dice and reject a blank roller

It was the only unthrottled write that persists to the log and broadcasts,
and it never checked the resolved name."
```

---

### Task 3: `RevocationStore.clear_active` and the `--revoke` leak

`gm_invite.py --revoke` (`scripts/gm_invite.py:39-47`) revokes the sid but leaves the `active` entry, so `gm_invite.py list` reports that player as active-but-revoked indefinitely (`scripts/gm_invite.py:53-55`). "Release a claim" needs to be `clear_active` + `revoke_sid`; `RevocationStore` has the second and not the first.

**Files:**
- Modify: `display/tokens.py:224-226` (append `clear_active` after `set_active`, before `active`)
- Modify: `scripts/gm_invite.py:39-47`
- Test: `tests/test_tokens.py`, `tests/test_gm_invite.py`

**Interfaces:**
- Consumes: `RevocationStore._load() -> dict` and `RevocationStore._save(data: dict) -> None` (`display/tokens.py:166-187`), the `self._lock` critical-section pattern from `set_active` (`:213-222`).
- Produces: `RevocationStore.clear_active(player_id: str) -> str | None` — removes `player_id` from `active`, returns the sid it removed (or `None` if there was none). It does **not** revoke. Tasks 9 and 13 both call it.

- [ ] **Step 1: Write the failing tests**

Append to `class RevocationStoreTests` in `tests/test_tokens.py` (after `test_set_active_same_sid_twice_does_not_self_revoke`, line 146):

```python
    def test_clear_active_removes_the_entry_and_returns_the_sid(self):
        self.store.set_active("kara", "s1")
        self.assertEqual(self.store.clear_active("kara"), "s1")
        self.assertNotIn("kara", self.store.active())

    def test_clear_active_on_an_unknown_player_is_a_no_op(self):
        self.assertIsNone(self.store.clear_active("nobody"))
        self.assertEqual(self.store.active(), {})

    def test_clear_active_does_not_revoke_on_its_own(self):
        # Release is clear_active + revoke_sid, two deliberate steps: dropping
        # a claim without revoking is how a rotate hands the seat back cleanly.
        self.store.set_active("kara", "s1")
        self.store.clear_active("kara")
        self.assertFalse(self.store.is_sid_revoked("s1"))
```

And in `tests/test_gm_invite.py`, replace `test_revoke_active_session` (lines 50-55):

```python
    def test_revoke_clears_the_active_entry_as_well_as_the_sid(self):
        # Leaving the active entry made `list` report that player
        # active-but-revoked forever, with no way to clear it.
        store = tokens.RevocationStore(self.display / ".revoked.json")
        store.set_active("kara", "sid-1")
        out = run_invite(self.display, "-c", "c", "--revoke", "Kara")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(store.is_sid_revoked("sid-1"))
        self.assertNotIn("kara", store.active())
        listing = run_invite(self.display, "-c", "c", "list")
        self.assertIn("no active players", listing.stdout)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_tokens.py tests/test_gm_invite.py -q`
Expected: FAIL — `AttributeError: 'RevocationStore' object has no attribute 'clear_active'` on three, and the CLI test fails on `assertNotIn("kara", store.active())`.

- [ ] **Step 3: Add `clear_active`**

In `display/tokens.py`, insert between `set_active` (ends line 222) and `active` (starts line 224):

```python
    def clear_active(self, player_id: str):
        """Drop player's claim. Returns the sid that was cleared, or None.

        Deliberately does not revoke: "release a claim" is clear_active +
        revoke_sid, two steps, because a rotate wants the first without the
        second. Leaving the active entry behind is what made `list` report a
        player active-but-revoked forever.
        """
        with self._lock:
            data = self._load()
            prior = data["active"].pop(player_id, None)
            if prior is not None:
                self._save(data)
            return prior
```

- [ ] **Step 4: Fix the CLI**

In `scripts/gm_invite.py`, replace lines 39-47:

```python
    if args.revoke:
        player_id = args.revoke.strip().lower()
        sid = store.active().get(player_id)
        if not sid:
            print(f"error: no active session for '{player_id}'", file=sys.stderr)
            return 1
        store.revoke_sid(sid)
        store.clear_active(player_id)
        print(f"revoked: {player_id}")
        return 0
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_tokens.py tests/test_gm_invite.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest tests -q`
Expected: PASS, 356 passed.

- [ ] **Step 7: Commit**

```bash
git add display/tokens.py scripts/gm_invite.py tests/test_tokens.py tests/test_gm_invite.py
git commit -m "fix(tokens): add clear_active; --revoke no longer leaks the active entry

Revoking the sid but leaving the active entry made \`list\` report that
player active-but-revoked with no way to clear it."
```

---

# Phase B — Foundations

---

### Task 4: The word list and `make_slug`

Four independent draws with replacement from one flat 2048-word list. **The security argument is the rate limiter, not the entropy:** `_RATE_MAX` is 20 requests per 60s keyed on `CF-Connecting-IP` (`display/gm-display-app.py:159-166`) — failures-only once Task 8 lands — against a tunnel that is up a few hours a week, which puts exhaustive guessing out of reach by orders of magnitude at this list size or a far smaller one. Do not present 44 bits as load-bearing in `table.py`'s docstring, in comments, or anywhere else; write the limiter argument down instead, so a future maintainer does not treat the word count as a security parameter. What the flat with-replacement draw buys is simplicity: no categorised sub-lists, no grammar machinery. The slug will not always read grammatically — `thoughtful-pandas-run-quietly` is a lucky draw, not a guarantee — and the owner has ruled nonsensical slugs are fine.

Do not hand-write the list into this plan. Author `display/wordlist.txt` directly as a data file and let the test assert its shape. The mechanical checks below (count, character class, length bounds, uniqueness) are everything a test can do for a list no human will read end to end; **they cannot catch an unfortunate pair of adjacent draws** — two innocent words that read badly together — so the list wants a human skim before it ships.

**Word list requirements:**
- Exactly 2048 lines, plus a trailing newline at EOF.
- One word per line, matching `^[a-z]{3,9}$` — lowercase ASCII only, no hyphens (the hyphen is the slug separator), 3-9 chars so a four-word slug stays under 40 characters.
- All 2048 distinct. Sorted ascending, so a duplicate is visible in review as adjacent identical lines.
- Fantasy-flavoured: creatures, materials, weather, terrain, colours, virtues, verbs of motion and craft. Avoid anything that could read as an insult or a slur when two draws land adjacent — this URL is spoken aloud over voice chat.
- No homophone pairs that a listener cannot disambiguate by ear (`night`/`knight`, `mail`/`male`). Pick one of each.

**Files:**
- Create: `display/wordlist.txt`
- Create: `display/table.py`
- Test: `tests/test_table_slug.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `display/table.py::WORDS_FILE: pathlib.Path` — `display/wordlist.txt`.
  - `display/table.py::SLUG_WORDS: int` = `4`.
  - `display/table.py::SLUG_RE: re.Pattern` — `^[a-z]{3,9}(?:-[a-z]{3,9}){3}$`.
  - `display/table.py::load_words(path: pathlib.Path = WORDS_FILE) -> list[str]`.
  - `display/table.py::make_slug(words: list[str] | None = None) -> str` — `secrets.choice` × 4, `"-".join`.
  Task 5 builds `TableStore` on these; Task 8 imports `SLUG_RE`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_table_slug.py`:

```python
"""tests/test_table_slug.py — the table slug: word list, minting, persistence."""
import pathlib
import re
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))

import table  # noqa: E402


class WordListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.words = table.load_words()

    def test_the_list_is_exactly_2048_words(self):
        # The shipped size, pinned as a hard equality so a truncated or
        # padded regeneration is loud. The security argument is the rate
        # limiter, not this number — see table.py's docstring.
        self.assertEqual(len(self.words), 2048)

    def test_every_word_is_lowercase_ascii_3_to_9_chars(self):
        bad = [w for w in self.words if not re.fullmatch(r"[a-z]{3,9}", w)]
        self.assertEqual(bad, [], f"{len(bad)} malformed word(s), first: {bad[:5]}")

    def test_every_word_is_distinct(self):
        self.assertEqual(len(set(self.words)), len(self.words))

    def test_the_list_is_sorted(self):
        # So a duplicate shows up in review as two adjacent identical lines.
        self.assertEqual(self.words, sorted(self.words))


class MakeSlugTests(unittest.TestCase):
    def test_slug_is_four_hyphenated_words(self):
        slug = table.make_slug()
        self.assertRegex(slug, table.SLUG_RE)
        self.assertEqual(len(slug.split("-")), table.SLUG_WORDS)

    def test_every_word_comes_from_the_list(self):
        words = set(table.load_words())
        for part in table.make_slug().split("-"):
            self.assertIn(part, words)

    def test_slugs_do_not_repeat(self):
        # Against a 2048^4 space, 200 draws colliding means the source is not
        # random.
        self.assertEqual(len({table.make_slug() for _ in range(200)}), 200)

    def test_draws_are_independent_so_a_word_may_repeat_within_a_slug(self):
        # With-replacement is the specified draw. Assert the mechanism allows
        # a repeat rather than waiting for one: choice() over the full list
        # four times, not a shuffle-and-take.
        tiny = ["alpha", "beta"]
        seen = {table.make_slug(tiny) for _ in range(200)}
        self.assertIn("alpha-alpha-alpha-alpha", seen)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_table_slug.py -q`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'table'`.

- [ ] **Step 3: Author the word list**

Create `display/wordlist.txt` meeting every bullet under "Word list requirements" above. Verify before moving on:

```bash
python3 - <<'PY'
import re, pathlib
w = pathlib.Path("display/wordlist.txt").read_text().split()
assert len(w) == 2048, len(w)
assert len(set(w)) == 2048
assert w == sorted(w)
assert all(re.fullmatch(r"[a-z]{3,9}", x) for x in w)
print("ok", w[0], w[-1])
PY
```

- [ ] **Step 4: Write `display/table.py`**

```python
"""
table.py — the table slug: one long, readable, unguessable path per campaign.

Four words drawn independently (with replacement) from a flat 2048-word list.
Unguessable in practice because of the rate limiter, not the raw count:
failed lookups are capped at 20/min per IP (_rate_ok, charged only on
failures) and the tunnel is only up while a session is in play, which puts
exhaustive guessing out of reach by orders of magnitude at this list size or
a far smaller one. Do not treat the bit count as load-bearing; the limiter
is the argument. Readable over voice chat, typeable on a phone.

Stdlib only (pathlib, re, secrets). The slug names the TABLE, never a
character: nothing in it binds identity, so there is nothing in it to clear.
"""
import pathlib
import re
import secrets

WORDS_FILE = pathlib.Path(__file__).with_name("wordlist.txt")
SLUG_WORDS = 4
SLUG_RE = re.compile(r"^[a-z]{3,9}(?:-[a-z]{3,9}){3}$")

_cache: list[str] | None = None


def load_words(path: pathlib.Path = WORDS_FILE) -> list[str]:
    """The vocabulary, read once and cached when it is the shipped file."""
    global _cache
    if path == WORDS_FILE and _cache is not None:
        return _cache
    words = path.read_text(encoding="utf-8").split()
    if path == WORDS_FILE:
        _cache = words
    return words


def make_slug(words: list[str] | None = None) -> str:
    """Four independent uniform draws, hyphen-joined.

    secrets.choice four times over the whole list — not a shuffle-and-take.
    With-replacement is the specified draw: simpler to reason about, and a
    repeated word inside a slug is harmless.
    """
    pool = words if words is not None else load_words()
    return "-".join(secrets.choice(pool) for _ in range(SLUG_WORDS))
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_table_slug.py -q`
Expected: PASS, 8 passed.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest tests -q`
Expected: PASS, 364 passed.

- [ ] **Step 7: Commit**

```bash
git add display/wordlist.txt display/table.py tests/test_table_slug.py
git commit -m "feat(table): 2048-word fantasy vocabulary and four-word slug minting"
```

---

### Task 5: `TableStore` — persistence and rotation

The slug lives for the campaign. It is minted on first read, persisted, and replaced only by `rotate()`. Comparison is constant-time: the slug is the shared secret and `/t/<slug>` is a public endpoint.

**Files:**
- Modify: `display/table.py` (append `TableStore`)
- Modify: `.gitignore`
- Test: `tests/test_table_slug.py` (append)

**Interfaces:**
- Consumes: `make_slug(words: list[str] | None = None) -> str` and `SLUG_RE` from Task 4, both in `display/table.py`.
- Produces:
  - `display/table.py::TableStore(path)` — file shape `{"slug": "<four-words>"}`.
  - `TableStore.slug() -> str` — the current slug, minting and persisting it on first call.
  - `TableStore.rotate() -> str` — mints a new slug, persists it, returns it. The old one stops matching immediately.
  - `TableStore.matches(candidate: str) -> bool` — constant-time compare against the current slug; `False` for anything not matching `SLUG_RE`.
  Task 8 constructs one as `_TABLE` in `display/gm-display-app.py`; Task 13 constructs one in `scripts/gm_table.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_table_slug.py`, before the `if __name__` block:

```python
class TableStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = pathlib.Path(self._tmp.name) / ".table.json"
        self.store = table.TableStore(self.path)

    def test_slug_is_minted_and_persisted_on_first_read(self):
        first = self.store.slug()
        self.assertRegex(first, table.SLUG_RE)
        self.assertTrue(self.path.exists())
        self.assertEqual(self.store.slug(), first)
        self.assertEqual(table.TableStore(self.path).slug(), first)

    def test_the_file_is_private(self):
        self.store.slug()
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_rotate_replaces_the_slug_and_kills_the_old_one(self):
        old = self.store.slug()
        new = self.store.rotate()
        self.assertNotEqual(old, new)
        self.assertEqual(self.store.slug(), new)
        self.assertFalse(self.store.matches(old))
        self.assertTrue(self.store.matches(new))

    def test_matches_rejects_malformed_candidates_without_touching_the_file(self):
        self.store.slug()
        for junk in ("", "x", "a-b-c", "one-two-three-four-five",
                     "ONE-TWO-THREE-FOUR", "one_two_three_four", "../../etc/passwd",
                     "one-two-three-four\n"):
            self.assertFalse(self.store.matches(junk), junk)

    def test_matches_rejects_a_non_string(self):
        self.store.slug()
        for junk in (None, 42, ["a"], {"a": 1}):
            self.assertFalse(self.store.matches(junk))

    def test_corrupt_store_fails_closed(self):
        self.path.write_text("not json {{{")
        with self.assertRaises(RuntimeError):
            self.store.slug()

    def test_a_stored_slug_that_no_longer_validates_is_replaced(self):
        # Hand-edited or written by an older format. Never serve it.
        self.path.write_text('{"slug": "NOT A SLUG"}')
        fresh = self.store.slug()
        self.assertRegex(fresh, table.SLUG_RE)
```

Add `import tempfile` to the imports at the top of the file.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_table_slug.py -q -k TableStore`
Expected: FAIL — `AttributeError: module 'table' has no attribute 'TableStore'`.

- [ ] **Step 3: Append `TableStore` to `display/table.py`**

Add `import hmac`, `import json`, `import os` and `import threading` to the imports, then append:

```python
class TableStore:
    """The campaign's current table slug: {"slug": "<four-words>"}.

    Same locked, atomically-rewritten pattern as tokens.RevocationStore: one
    critical section ending in a tmp-file write plus os.replace, so a rotate
    racing a read can never expose a half-written file. Mode 0600 — the slug
    is the shared secret that authorises a claim.
    """

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self._lock = threading.Lock()

    def _read(self) -> str:
        try:
            text = self.path.read_text()
        except FileNotFoundError:
            return ""
        except OSError as e:
            raise RuntimeError(f"table store {self.path} unreadable: {e}") from e
        try:
            data = json.loads(text)
        except ValueError as e:
            raise RuntimeError(f"table store {self.path} corrupt: {e}") from e
        if not isinstance(data, dict):
            raise RuntimeError(f"table store {self.path} corrupt: not an object")
        slug = data.get("slug", "")
        # A stored value that no longer validates (hand-edited, older format)
        # is treated as absent rather than served.
        return slug if isinstance(slug, str) and SLUG_RE.match(slug) else ""

    def _write(self, slug: str) -> None:
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"slug": slug}, indent=1))
        os.replace(tmp, self.path)

    def slug(self) -> str:
        """The current slug, minted and persisted on first call."""
        with self._lock:
            current = self._read()
            if not current:
                current = make_slug()
                self._write(current)
            return current

    def rotate(self) -> str:
        """Mint a new slug and persist it. The old one stops matching at once."""
        with self._lock:
            fresh = make_slug()
            self._write(fresh)
            return fresh

    def matches(self, candidate) -> bool:
        """Constant-time compare against the current slug.

        Shape-checked first so a malformed candidate never reaches the
        comparison, and so a 400-char path does not read the file at all.
        """
        if not isinstance(candidate, str) or not SLUG_RE.match(candidate):
            return False
        return hmac.compare_digest(self.slug(), candidate)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_table_slug.py -q`
Expected: PASS, 15 passed.

- [ ] **Step 5: Ignore the store file**

In `.gitignore`, after line 21 (`display/.revoked.json`):

```
display/.table.json
```

- [ ] **Step 6: Run the whole suite and commit**

Run: `python3 -m pytest tests -q`
Expected: PASS, 371 passed.

```bash
git add display/table.py tests/test_table_slug.py .gitignore
git commit -m "feat(table): TableStore persists and rotates the campaign slug"
```

---

### Task 6: `role` becomes a field in the token payload

A cookie carrying no character is a state this codebase has never had. `_mint` accepts `character=""` without validation (`display/tokens.py:84-93`) and `_resolve_identity` would resolve it to `{"role": "player", "character": ""}` (`display/gm-display-app.py:504-506`) — the same ambiguity this redesign exists to remove, reintroduced through the back door, and it would receive the full `_PLAYER_ENDPOINTS` set including `help_request` (which spawns a subprocess) and `get_character_sheet` (which serves every PC's sheet).

**Migration decision — cookies already in the wild carry no `role` field.** `verify()` defaults a missing `r` to `"player"`. That is safe *specifically because* every session token ever minted came from the `/j/<token>` route (`display/gm-display-app.py:1334-1336`), which mints from a join payload whose `character` was always a real name supplied on the `gm_invite.py mint` command line. No legacy cookie can be a characterless player. The belt-and-braces half of the decision goes into `_resolve_identity` in Task 7: a `player` payload with an empty `character` is rejected there, so even a hand-forged legacy-shaped token cannot become an anonymous player.

Note `_SHORT` (`display/tokens.py:79-80`) is documentation — `_mint` writes the short keys literally. Keep it in sync anyway; it is what `verify()`'s comment points readers at.

**Files:**
- Modify: `display/tokens.py:74-103` and `:141-150`
- Test: `tests/test_tokens.py`

**Interfaces:**
- Consumes: `_mint`, `mint_session`, `verify` as they stand at `display/tokens.py:84-150`.
- Produces:
  - `tokens.ROLES: tuple[str, ...]` = `("player", "display")` — the roles a *token* may carry. `local` and `gm` are identity roles produced without a token and never appear in a payload.
  - `tokens.mint_session(player_id, character, campaign, *, secret, role="player", ttl_s=SESSION_TTL_S, now=None) -> str`.
  - `tokens.verify(token, *, secret, kind, now=None) -> dict | None` — the returned dict gains `"role"`, always one of `ROLES`. Returns `None` if the payload carries an `r` outside `ROLES`.
  Task 7 reads `payload["role"]`; Task 9 calls `mint_session(..., role="display")`.

- [ ] **Step 1: Write the failing tests**

Append to `class TokenSignVerifyTests` in `tests/test_tokens.py` (after `test_minted_join_token_is_short`, line 105):

```python
    def test_session_defaults_to_the_player_role(self):
        t = tokens.mint_session("kara", "Kara", "c", secret=SECRET, now=1000)
        p = tokens.verify(t, secret=SECRET, kind="session", now=1000)
        self.assertEqual(p["role"], "player")

    def test_display_role_round_trips(self):
        t = tokens.mint_session("", "", "c", secret=SECRET, role="display", now=1000)
        p = tokens.verify(t, secret=SECRET, kind="session", now=1000)
        self.assertEqual(p["role"], "display")
        self.assertEqual(p["character"], "")

    def test_a_legacy_payload_with_no_role_reads_as_player(self):
        # Cookies minted before this field existed are still in the wild and
        # must keep working. Safe because every one of them came from
        # /j/<token>, which always carried a real character name.
        body = tokens._b64(tokens.json.dumps(
            {"k": "session", "p": "kara", "c": "Kara", "g": "c",
             "j": "x", "i": 1000, "t": 100},
            separators=(",", ":")).encode())
        t = body + "." + tokens._sign(body, SECRET)
        p = tokens.verify(t, secret=SECRET, kind="session", now=1000)
        self.assertEqual(p["role"], "player")

    def test_an_unknown_role_is_rejected_outright(self):
        body = tokens._b64(tokens.json.dumps(
            {"k": "session", "p": "kara", "c": "Kara", "g": "c",
             "j": "x", "r": "gm", "i": 1000, "t": 100},
            separators=(",", ":")).encode())
        t = body + "." + tokens._sign(body, SECRET)
        self.assertIsNone(tokens.verify(t, secret=SECRET, kind="session", now=1000))

    def test_a_non_string_role_is_rejected(self):
        body = tokens._b64(tokens.json.dumps(
            {"k": "session", "p": "kara", "c": "Kara", "g": "c",
             "j": "x", "r": 1, "i": 1000, "t": 100},
            separators=(",", ":")).encode())
        t = body + "." + tokens._sign(body, SECRET)
        self.assertIsNone(tokens.verify(t, secret=SECRET, kind="session", now=1000))

    def test_session_return_contract_carries_role(self):
        t = tokens.mint_session("kara", "Kara", "c", secret=SECRET, now=1000)
        p = tokens.verify(t, secret=SECRET, kind="session", now=1000)
        self.assertEqual(set(p), {"k", "player_id", "character", "campaign",
                                  "sid", "issued_at", "ttl_s", "role"})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_tokens.py -q`
Expected: FAIL — `KeyError: 'role'` on the first two and the last, and the two rejection tests return a dict instead of `None`.

- [ ] **Step 3: Add the field**

In `display/tokens.py`, replace lines 74-103:

```python
# Wire compression: full payload key -> short single-char wire key. "k" (kind)
# is unchanged; the nonce/id (jti|sid) is always serialized as "j" and mapped
# back to jti/sid by verify() from the requested kind. verify() reverses this
# table so its returned dict keeps the original full-name keys — no consumer
# (the gate, the /claim route, tests) changes.
_SHORT = {"player_id": "p", "character": "c", "campaign": "g",
          "role": "r", "issued_at": "i", "ttl_s": "t"}
_ID_FULL = {"join": "jti", "session": "sid"}

# The roles a TOKEN may carry. "local" and "gm" are identity roles produced by
# the gate without a token and must never appear in a payload — a cookie that
# claims one is a forgery attempt, so verify() rejects it rather than
# downgrading it.
ROLES = ("player", "display")


def _mint(kind: str, id_key: str, player_id: str, character: str, campaign: str,
          *, secret: str, ttl_s: int, role: str = "player", now=None) -> str:
    if role not in ROLES:
        raise ValueError(f"unknown token role: {role!r}")
    wire = {
        "k": kind, "p": player_id, "c": character.strip(), "g": campaign,
        "r": role,
        "j": secrets.token_hex(8),
        "i": int(now if now is not None else time.time()),
        "t": int(ttl_s),
    }
    body = _b64(json.dumps(wire, separators=(",", ":")).encode())
    return body + "." + _sign(body, secret)


def mint_join(player_id, character, campaign, *, secret, ttl_s=JOIN_TTL_S, now=None):
    return _mint("join", "jti", player_id, character, campaign,
                 secret=secret, ttl_s=ttl_s, now=now)


def mint_session(player_id, character, campaign, *, secret, role="player",
                 ttl_s=SESSION_TTL_S, now=None):
    return _mint("session", "sid", player_id, character, campaign,
                 secret=secret, ttl_s=ttl_s, role=role, now=now)
```

Then replace lines 141-150 (the return block of `verify`):

```python
    # A payload minted before this field existed reads as "player". Safe
    # because every session token in the wild came from /j/<token>, which
    # minted from a join payload whose character was always a real name.
    # The other half of that argument is in _resolve_identity, which rejects
    # a player payload with an empty character.
    role = wire.get("r", "player")
    if role not in ROLES:
        return None
    # Map short wire keys back to the full-name return contract callers rely on.
    return {
        "k": wire.get("k"),
        "player_id": wire.get("p"),
        "character": wire.get("c"),
        "campaign": wire.get("g"),
        "role": role,
        _ID_FULL[kind]: wire.get("j"),
        "issued_at": issued,
        "ttl_s": ttl,
    }
```

- [ ] **Step 4: Fix the collateral assertion**

`tests/test_tokens.py::test_verify_returns_full_name_keys_only` (line 86) asserts the exact key set for a *join* token. Add `"role"` to its expected set:

```python
        self.assertEqual(set(p), {"k", "player_id", "character", "campaign",
                                  "jti", "issued_at", "ttl_s", "role"})
```

(Task 2's `test_dice_rejects_an_empty_resolved_character` already accepts `(400, 403)`, so nothing else moves: a `character=""` session still verifies at this layer — it stops *resolving* in Task 7.)

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_tokens.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite and commit**

Run: `python3 -m pytest tests -q`
Expected: PASS, 377 passed.

```bash
git add display/tokens.py tests/test_tokens.py
git commit -m "feat(tokens): role is a real field in the session payload

A characterless cookie used to resolve to {role: player, character: ''} and
receive the full player endpoint set. Legacy cookies with no role field read
as player, which is safe because every one of them came from /j/<token>."
```

---

### Task 7: The display role in `_resolve_identity`, `_bound_character` and `_gate`

`_gate` (`display/gm-display-app.py:525-552`) is the sole access authority. It gains a display subset: read-only endpoints plus `stream` plus `player_input`. `player_input` is in for one reason — the picker's "Create a character with the DM" entry drops the device into the existing narration loop, and posting there is that loop. A display identity's posts land as `"Party"`, which is the route's existing characterless default (`display/gm-display-app.py:2176-2179`). `help_request` (subprocess) and `get_character_sheet` (every PC's sheet) stay out.

**Files:**
- Modify: `display/gm-display-app.py:463-473`, `:494-522`, `:525-552`, `:2167`
- Test: `tests/test_picker.py` (create)

**Interfaces:**
- Consumes: `tokens.verify(...)` returning `"role"` in `("player", "display")` (Task 6); `RevocationStore.is_sid_revoked(sid) -> bool`; `_is_local() -> bool` (`:486`); `_is_tunnelled() -> bool` (`:476`); `table.TableStore(path)` (Task 5, test fixture only — the app does not touch it until Task 8).
- Produces:
  - `_DISPLAY_ENDPOINTS: set[str]` = `{"index", "stream", "srd_lookup", "audio_sfx", "player_input"}`.
  - `_resolve_identity()` returns `{"role": "display", "player_id": "", "character": ""}` for a display cookie, `{"role": "player", "player_id": ..., "character": ...}` for a player cookie with a **non-empty** character, and falls through to the existing local/None handling otherwise.
  - `_bound_character(fallback: str = "") -> str` returns `""` for a display identity (it must not honour a client-supplied name), `ident["character"]` for a player, `fallback` otherwise.
  Tasks 8, 9 and 11 all depend on these three.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_picker.py`:

```python
"""tests/test_picker.py — the display role, the table URL, and claiming."""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import table  # noqa: E402
import tokens  # noqa: E402

TUNNEL = {"CF-Connecting-IP": "203.0.113.9"}
ORIGIN = {"Origin": "http://localhost:5001"}


def _import_app():
    # The module's file name contains a hyphen, so it cannot be imported by
    # name. Registered in sys.modules before exec so Flask's get_root_path()
    # finds mod.__file__ and resolves templates (render_template on GET /).
    spec = importlib.util.spec_from_file_location(
        "gm_display_app_picker", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class PickerTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(cls.tmp.name)
        cls.secret = tokens.ensure_secret(d / ".invite_secret")
        cls.mod._INVITE_SECRET = cls.secret
        cls.mod._GM_SECRET = "test-gm-secret"
        cls.mod._REVOCATION = tokens.RevocationStore(d / ".revoked.json")
        # setattr on the module: the app does not define _TABLE until Task 8.
        # Harmless before then, an override after — either way the tests
        # never touch the developer's real display/.table.json.
        cls.mod._TABLE = table.TableStore(d / ".table.json")
        cls.client = cls.mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.mod._REVOCATION.path.write_text('{"sid": [], "active": {}}')
        with self.mod._stats_lock:
            self.mod._current_stats.clear()
            self.mod._current_stats["players"] = [
                {"name": "Kara"}, {"name": "Tom"}, {"name": "Zed"}]
        self.addCleanup(self.client.delete_cookie, "gm_session")

    def player_cookie(self, character="Kara"):
        t = tokens.mint_session(character.lower(), character, "c", secret=self.secret)
        self.client.set_cookie("gm_session", t)
        return t

    def display_cookie(self):
        t = tokens.mint_session("", "", "c", secret=self.secret, role="display")
        self.client.set_cookie("gm_session", t)
        return t


class DisplayRoleGate(PickerTestBase):
    def test_display_cookie_reaches_the_display_endpoints(self):
        self.display_cookie()
        r = self.client.get("/stream", headers=TUNNEL)
        self.assertEqual(r.status_code, 200)
        r.close()

    def test_display_cookie_cannot_reach_player_only_endpoints(self):
        # help_request spawns a subprocess; get_character_sheet serves every
        # PC's sheet; player_dice writes to the narration log under a name.
        self.display_cookie()
        self.assertEqual(
            self.client.post("/help-request", headers={**TUNNEL, **ORIGIN},
                             json={}).status_code, 403)
        self.assertEqual(
            self.client.get("/character/Kara", headers=TUNNEL).status_code, 403)
        self.assertEqual(
            self.client.post("/player-input/dice", headers={**TUNNEL, **ORIGIN},
                             json={"spec": "1d20"}).status_code, 403)

    def test_display_cookie_cannot_reach_gm_endpoints(self):
        self.display_cookie()
        for path in ("/chunk", "/stats", "/player-input/drain"):
            r = self.client.post(path, headers={**TUNNEL, **ORIGIN}, json={})
            self.assertEqual(r.status_code, 403, path)

    def test_display_posts_land_as_party_not_as_a_client_supplied_name(self):
        self.display_cookie()
        r = self.client.post("/player-input", headers={**TUNNEL, **ORIGIN},
                             json={"character": "Kara", "text": "I look around"})
        self.assertEqual(r.status_code, 204)
        with self.mod._input_lock:
            self.assertEqual(self.mod._input_queue[-1]["character"], "Party")

    def test_a_local_browser_with_a_display_cookie_is_downgraded_to_local(self):
        # A GM who picked "Display only" on their own console must not lose
        # their console. index() already forces role=local for a loopback
        # peer; the gate has to agree or the console 403s on its own routes.
        self.display_cookie()
        r = self.client.post("/clear", headers=ORIGIN, json={})
        self.assertNotEqual(r.status_code, 403)

    def test_a_characterless_player_cookie_does_not_resolve(self):
        # The exact back door this redesign exists to close: _mint accepts
        # character="" and the old _resolve_identity handed it the full
        # player endpoint set.
        t = tokens.mint_session("", "", "c", secret=self.secret)
        self.client.set_cookie("gm_session", t)
        self.assertEqual(self.client.get("/stream", headers=TUNNEL).status_code, 403)

    def test_a_player_cookie_is_unaffected(self):
        self.player_cookie("Kara")
        r = self.client.get("/stream", headers=TUNNEL)
        self.assertEqual(r.status_code, 200)
        r.close()
        self.assertEqual(
            self.client.get("/character/Kara", headers=TUNNEL).status_code, 404)


if __name__ == "__main__":
    unittest.main()
```

(`/character/Kara` returns 404 for a player because the fixture writes no sheet file — the point of the assertion is that the gate let the request reach the handler.)

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_picker.py -q`
Expected: FAIL — the display cookie resolves as an anonymous *player* under the current `_resolve_identity`, so: `/help-request`, `/character/Kara` and `/player-input/dice` come back non-403; the `/player-input` post lands under the client-supplied name, not `"Party"`; and the characterless player cookie streams 200 where 403 is expected.

- [ ] **Step 3: Add `_DISPLAY_ENDPOINTS`**

In `display/gm-display-app.py`, after line 473 (the close of `_PLAYER_ENDPOINTS`):

```python
# A display-role cookie carries no character. It gets reads plus the SSE
# stream plus player_input — the last so the picker's "Create a character
# with the DM" entry can reach the narration loop that already exists; those
# posts land as "Party" (see _bound_character and the player_input route).
# Deliberately excluded: help_request (spawns a subprocess) and
# get_character_sheet (serves every PC's sheet).
_DISPLAY_ENDPOINTS = {"index", "stream", "srd_lookup", "audio_sfx", "player_input"}
```

- [ ] **Step 4: Teach `_resolve_identity` and `_bound_character` about the role**

Replace `display/gm-display-app.py:494-522`:

```python
def _resolve_identity():
    cookie = request.cookies.get("gm_session")
    if cookie:
        payload = tokens.verify(cookie, secret=_INVITE_SECRET, kind="session")
        try:
            revoked = bool(payload) and _REVOCATION.is_sid_revoked(payload.get("sid", ""))
        except RuntimeError:
            # corrupt/unreadable revocation store: cannot confirm good standing,
            # so fail closed. Local console must not brick itself.
            return {"role": "local"} if _is_local() else None
        if payload and not revoked:
            role = payload["role"]
            character = payload["character"] or ""
            # The other half of verify()'s legacy-cookie default. A payload
            # with role "player" and no character is either a forgery or a
            # mint that should never have happened; either way it must not
            # become an anonymous holder of _PLAYER_ENDPOINTS.
            if role == "player" and character:
                return {"role": "player", "player_id": payload["player_id"],
                        "character": character}
            if role == "display":
                return {"role": "display", "player_id": "", "character": ""}
        # invalid/expired/revoked cookie: local console must not brick itself
        return {"role": "local"} if _is_local() else None
    header = request.headers.get("X-GM-Secret", "")
    if header and not _is_tunnelled() and hmac.compare_digest(header, _GM_SECRET):
        return {"role": "gm"}
    if _is_local():
        return {"role": "local"}
    return None


def _bound_character(fallback: str = "") -> str:
    """Authenticated players act only as themselves; local/gm may name anyone.

    A display identity holds no character and must never be allowed to supply
    one: the fallback here is client-controlled on every write route, so
    returning it would let the shared screen post, roll and stream as any PC.
    """
    ident = getattr(g, "identity", None) or {}
    role = ident.get("role")
    if role == "player":
        return ident["character"]
    if role == "display":
        return ""
    return fallback
```

- [ ] **Step 5: Extend the gate**

Replace `display/gm-display-app.py:534-544` (from `role = g.identity["role"]` through the player fail-closed line):

```python
    role = g.identity["role"]
    # Un-brick the local console. A GM who opened a picker link in their own
    # browser keeps their console: for a player that only applies outside
    # _PLAYER_ENDPOINTS (index is inside it, which is why index() checks
    # _is_local() directly); for a display cookie it applies everywhere,
    # because a loopback browser has no use for a display identity and would
    # otherwise 403 on its own routes.
    if _is_local() and role in ("player", "display"):
        if role == "display" or endpoint not in _PLAYER_ENDPOINTS:
            g.identity = {"role": "local"}
            role = "local"
    if role == "gm":
        return None
    if endpoint in _GM_ENDPOINTS:
        return jsonify({"error": "forbidden"}), 403
    if role == "player" and endpoint not in _PLAYER_ENDPOINTS:
        return jsonify({"error": "forbidden"}), 403
    if role == "display" and endpoint not in _DISPLAY_ENDPOINTS:
        return jsonify({"error": "forbidden"}), 403
```

- [ ] **Step 6: Let a display post land as "Party"**

In `display/gm-display-app.py`, replace line 2167:

```python
    # _bound_character returns "" for a display identity — it must not honour
    # the client-supplied name. "Party" is this route's existing characterless
    # default, so a display-only device's post reads the way a characterless
    # console post has always read.
    character = _bound_character(str(data.get("character", "Party"))[:50]) or "Party"
```

- [ ] **Step 7: Run the tests**

Run: `python3 -m pytest tests/test_picker.py -q`
Expected: PASS, 7 passed.

- [ ] **Step 8: Run the whole suite and commit**

Run: `python3 -m pytest tests -q`
Expected: PASS, 384 passed. `tests/test_auth_gate.py` must be entirely green — the player and local paths are byte-identical.

```bash
git add display/gm-display-app.py tests/test_picker.py
git commit -m "feat(gate): the display role is a real role with its own endpoint set

A characterless cookie no longer resolves to an anonymous player holding
help_request and get_character_sheet."
```

---

# Phase C — Routes and the picker page

---

### Task 8: `GET /t/<slug>` and the roster state helper

Three outcomes: invalid slug → 404; a cookie that resolves to `player` or `display` → `redirect("/")`; otherwise the picker.

A loopback browser is a deliberate exception to the second rule in one direction: `index()` forces `role: "local"` for any loopback peer whatever the cookie says (`display/gm-display-app.py:1364-1372`), so a claim made from the GM's own machine does not change what `/` renders. The picker still shows and `/claim` still works there — it just does not bind the local page. That is the pre-existing rule, not a new one.

**Files:**
- Modify: `display/gm-display-app.py` (import `table` + `_TABLE` after `_REVOCATION` at `:56`, `_PUBLIC_ENDPOINTS` at `:466`, new helpers and route immediately above `index()`)
- Modify: `display/tokens.py` (add `DM_SID`, guard `set_active`)
- Test: `tests/test_picker.py` (append), `tests/test_tokens.py` (append)

**Interfaces:**
- Consumes: `table.TableStore(path)` with `.slug() -> str`, `.rotate() -> str`, `.matches(candidate) -> bool` (Task 5); `_rate_ok(ip) -> bool` / `_rate_key() -> str`; `_REVOCATION.active() -> dict`, `.is_sid_revoked(sid) -> bool`; `g.identity` from `_gate`, roles `player | display | local | gm` (Task 7); the `PickerTestBase` fixture in `tests/test_picker.py` (Task 7) with `player_cookie(character)`, `display_cookie()`, a three-name roster, and a `cls.mod._TABLE` already pointed at a temp directory (a plain setattr until this task defines the real one).
- Produces:
  - `tokens.DM_SID: str` = `"dm"` — the sentinel stored in `active[player_id]` when the DM holds a character. A real sid is `secrets.token_hex(8)` (16 chars), so it can never collide. It is a **label, not a gate**: nothing in the request path reads it — only `_roster_states`, `/claim`'s transition label (Task 9) and `scripts/gm_table.py` (Task 13) do.
  - `display/gm-display-app.py::_TABLE: table.TableStore` — module-level, at `display/.table.json`.
  - `display/gm-display-app.py::_roster_states() -> list[dict]` — `[{"name": str, "state": "free" | "taken" | "dm"}, ...]`, one row per current roster character, in roster order. Claims whose key is absent from the roster are ignored.
  - Flask endpoint `table` at `/t/<slug>`, in `_PUBLIC_ENDPOINTS`. **Rate-limit contract:** the bucket is charged only on a failing lookup (bad or rotated slug); successful requests are free. Task 9's `/claim` follows the same contract.
  Task 9 calls `_roster_states()` and `_TABLE.matches()`; Task 10 renders the rows; Task 13 opens the same store from the CLI.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_picker.py`, before the `if __name__` block:

```python
class RosterStates(PickerTestBase):
    def test_an_unclaimed_character_is_free(self):
        rows = {r["name"]: r["state"] for r in self.mod._roster_states()}
        self.assertEqual(rows, {"Kara": "free", "Tom": "free", "Zed": "free"})

    def test_a_live_claim_is_taken(self):
        self.mod._REVOCATION.set_active("kara", "sid-live")
        rows = {r["name"]: r["state"] for r in self.mod._roster_states()}
        self.assertEqual(rows["Kara"], "taken")

    def test_a_revoked_claim_is_free_again(self):
        self.mod._REVOCATION.set_active("kara", "sid-old")
        self.mod._REVOCATION.revoke_sid("sid-old")
        rows = {r["name"]: r["state"] for r in self.mod._roster_states()}
        self.assertEqual(rows["Kara"], "free")

    def test_a_dm_held_character_is_dm(self):
        self.mod._REVOCATION.set_active("tom", tokens.DM_SID)
        rows = {r["name"]: r["state"] for r in self.mod._roster_states()}
        self.assertEqual(rows["Tom"], "dm")

    def test_a_claim_for_a_name_no_longer_in_the_roster_is_hidden(self):
        # Renaming a PC orphans their claim (BACKLOG). The picker must not
        # show "Gilda is taken" for someone who left the party.
        self.mod._REVOCATION.set_active("gilda", "sid-orphan")
        self.assertNotIn("Gilda", [r["name"] for r in self.mod._roster_states()])

    def test_a_corrupt_revocation_store_reads_as_all_free_not_a_500(self):
        self.mod._REVOCATION.path.write_text("not json {{{")
        try:
            rows = {r["name"]: r["state"] for r in self.mod._roster_states()}
        finally:
            self.mod._REVOCATION.path.write_text('{"sid": [], "active": {}}')
        self.assertEqual(set(rows.values()), {"free"})


class TableRoute(PickerTestBase):
    def test_an_unknown_slug_is_404(self):
        r = self.client.get("/t/never-was-a-slug", headers=TUNNEL)
        self.assertEqual(r.status_code, 404)

    def test_a_rotated_slug_is_404(self):
        old = self.mod._TABLE.slug()
        self.mod._TABLE.rotate()
        self.assertEqual(self.client.get(f"/t/{old}", headers=TUNNEL).status_code, 404)

    def test_a_malformed_slug_is_404_not_a_500(self):
        for junk in ("x", "a-b-c", "ONE-TWO-THREE-FOUR", "one_two_three_four"):
            r = self.client.get(f"/t/{junk}", headers=TUNNEL)
            self.assertEqual(r.status_code, 404, junk)

    def test_a_valid_slug_serves_the_picker(self):
        r = self.client.get(f"/t/{self.mod._TABLE.slug()}", headers=TUNNEL)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Kara", r.get_data(as_text=True))

    def test_a_valid_cookie_skips_the_picker(self):
        self.player_cookie("Kara")
        r = self.client.get(f"/t/{self.mod._TABLE.slug()}", headers=TUNNEL)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/")

    def test_a_display_cookie_also_skips_the_picker(self):
        self.display_cookie()
        r = self.client.get(f"/t/{self.mod._TABLE.slug()}", headers=TUNNEL)
        self.assertEqual(r.status_code, 302)

    def test_a_revoked_cookie_lands_on_the_picker_with_a_note(self):
        t = self.player_cookie("Kara")
        sid = tokens.verify(t, secret=self.secret, kind="session")["sid"]
        self.mod._REVOCATION.revoke_sid(sid)
        r = self.client.get(f"/t/{self.mod._TABLE.slug()}", headers=TUNNEL)
        self.assertEqual(r.status_code, 200)
        self.assertIn("released or taken over", r.get_data(as_text=True))

    def test_the_picker_never_names_who_holds_a_character(self):
        # The app knows characters, not people, and this design keeps it that
        # way. A taken row says "on another device", nothing more.
        self.mod._REVOCATION.set_active("kara", "sid-live")
        body = self.client.get(f"/t/{self.mod._TABLE.slug()}",
                               headers=TUNNEL).get_data(as_text=True)
        self.assertIn("on another device", body)
        self.assertNotIn("sid-live", body)

    def test_failing_lookups_are_rate_limited(self):
        # Failures charge the bucket, so an attacker — who only ever makes
        # failing requests — is capped at 20 guesses a minute. This is the
        # whole brute-force argument; the word count is not load-bearing.
        h = {"CF-Connecting-IP": "203.0.113.55"}
        codes = [self.client.get("/t/never-was-a-slug", headers=h).status_code
                 for _ in range(25)]
        self.assertIn(429, codes)

    def test_valid_requests_never_charge_the_bucket(self):
        # Players tunnelling from one house share one CF-Connecting-IP and
        # therefore one 20/60s bucket, and a session start plus an initiative
        # round already spends ~15 of it. A 429 on a dice roll mid-combat is
        # a trust break, so success must be free — only failures pay.
        h = {"CF-Connecting-IP": "203.0.113.56"}
        slug = self.mod._TABLE.slug()
        codes = [self.client.get(f"/t/{slug}", headers=h).status_code
                 for _ in range(25)]
        self.assertEqual(set(codes), {200})

    def test_the_slug_is_not_echoed_into_the_404(self):
        r = self.client.get("/t/aaaa-bbbb-cccc-dddd", headers=TUNNEL)
        self.assertNotIn("aaaa-bbbb-cccc-dddd", r.get_data(as_text=True))

    def test_bare_slash_still_403s_an_unauthenticated_remote_peer(self):
        # The picker introduces no public way to reach the play surface.
        # Adding "table" and "claim" to _PUBLIC_ENDPOINTS must not have
        # loosened "index", which stays inside _PLAYER_ENDPOINTS.
        self.assertEqual(self.client.get("/", headers=TUNNEL).status_code, 403)
```

And append to `class RevocationStoreTests` in `tests/test_tokens.py`:

```python
    def test_set_active_never_adds_the_dm_sentinel_to_the_revoked_list(self):
        # A returning owner always wins: claiming a DM-held character replaces
        # the sentinel. Appending "dm" to the revoked sid list would grow the
        # file forever and make is_sid_revoked("dm") true for every table.
        self.store.set_active("kara", tokens.DM_SID)
        self.store.set_active("kara", "s1")
        self.assertFalse(self.store.is_sid_revoked(tokens.DM_SID))
        self.assertEqual(self.store.active()["kara"], "s1")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_picker.py tests/test_tokens.py -q`
Expected: FAIL — `AttributeError: module has no attribute 'DM_SID'` / `'_TABLE'` / `'_roster_states'`, and 404s on `/t/...`.

- [ ] **Step 3: Add the DM sentinel**

In `display/tokens.py`, after `SESSION_TTL_S = 30 * 86400` (line 26):

```python
# Sentinel stored in RevocationStore.active[player_id] when the DM is running
# that character. A real sid is secrets.token_hex(8) — 16 hex chars — so this
# can never collide with one. "Control" (who is driving right now) and
# "ownership" (whose character it is) are different facts; this records only
# the first, which is why a returning owner reclaiming costs nothing.
DM_SID = "dm"
```

And in `set_active` (line 218), replace the condition:

```python
            if prior and prior != sid and prior != DM_SID and prior not in data["sid"]:
```

- [ ] **Step 4: Wire the table store, open the two public endpoints, add the roster helper**

In `display/gm-display-app.py`, after line 56 (`_REVOCATION = ...`):

```python
import table  # noqa: E402
_TABLE = table.TableStore(_IDENTITY_DIR / ".table.json")
```

Then replace `_PUBLIC_ENDPOINTS` (line 466):

```python
_PUBLIC_ENDPOINTS = {"join", "table", "claim", "ping", "health", "static"}
```

Add `_roster_states` immediately above the `@app.route("/")` decorator (`:1352` in the pre-plan tree; Task 7's gate edits have shifted it — anchor on the decorator, not the number):

```python
def _roster_states() -> list[dict]:
    """One row per roster character: {"name": str, "state": free|taken|dm}.

    Ownership and control are separate facts and only the second lives here.
    "taken" means some device holds a live session; "dm" means the DM is
    running the character this session (or permanently — same mechanism, no
    separate concept). Claims keyed on a name that is no longer in the roster
    are dropped: renaming a PC orphans their claim, and the picker must not
    offer "taken" against someone who left the party.

    A corrupt revocation store reads as all-free rather than raising: the
    picker is the door back in, and bricking it is worse than showing a
    character as available and letting set_active sort it out.
    """
    with _stats_lock:
        names = [p["name"] for p in _current_stats.get("players", []) if p.get("name")]
    try:
        active = _REVOCATION.active()
        revoked = {sid for sid in active.values() if _REVOCATION.is_sid_revoked(sid)}
    except RuntimeError:
        active, revoked = {}, set()
    rows = []
    for name in names:
        sid = active.get(name.lower())
        if sid == tokens.DM_SID:
            state = "dm"
        elif sid and sid not in revoked:
            state = "taken"
        else:
            state = "free"
        rows.append({"name": name, "state": state})
    return rows
```

- [ ] **Step 5: Add the route**

Immediately after `_roster_states`, before `index()`:

```python
@app.route("/t/<slug>")
def table_page(slug):
    """The table URL: the picker, or straight through to play.

    The secret is the address and the address names the table, never a
    character — nothing in it binds identity, so there is nothing in it to
    clear, share wrongly, or fail to drop. An unknown slug is a 404,
    indistinguishable from a typo, and never echoes what was tried.
    """
    if not _TABLE.matches(slug):
        # Failures charge the rate bucket; successes never do. Players behind
        # one tunnel share one CF-Connecting-IP and therefore one 20/60s
        # bucket, and a session start plus an initiative round already spends
        # ~15 of it — a mistyped slug must not 429 a dice roll mid-combat.
        # Brute force is unaffected: an attacker only ever makes failing
        # requests, so every guess still pays.
        if not _rate_ok(_rate_key()):
            return "Too Many Requests", 429
        return "Not Found", 404
    ident = getattr(g, "identity", None) or {}
    if ident.get("role") in ("player", "display"):
        return redirect("/")
    # A cookie that is present but did not resolve means the seat went away
    # while this device was holding it: released by the GM, or revoked by a
    # newer claim on the same character. Say so rather than showing a bare
    # picker that looks like a first visit.
    stale = bool(request.cookies.get("gm_session"))
    return render_template(
        "picker.html",
        slug=slug,
        rows=_roster_states(),
        notice=("Your seat was released or taken over. Pick again."
                if stale else ""),
    )
```

Flask derives the endpoint name from the function, so `table_page` would register as `table_page`, not `table`. Register it explicitly so `_PUBLIC_ENDPOINTS` matches: change the decorator to

```python
@app.route("/t/<slug>", endpoint="table")
```

- [ ] **Step 6: Stub the template so the route can render**

Create `display/templates/picker.html` with just enough to satisfy the route tests; Task 10 replaces it wholesale:

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Pick a character</title></head>
<body>
<p id="picker-notice">{{ notice }}</p>
<ul id="picker-roster">
{% for row in rows %}
  <li data-state="{{ row.state }}">{{ row.name }}{% if row.state == 'taken' %} — on another device{% elif row.state == 'dm' %} — run by the DM{% endif %}</li>
{% endfor %}
</ul>
</body></html>
```

- [ ] **Step 7: Run the tests**

Run: `python3 -m pytest tests/test_picker.py tests/test_tokens.py -q`
Expected: PASS.

- [ ] **Step 8: Run the whole suite and commit**

Run: `python3 -m pytest tests -q`
Expected: PASS, 403 passed.

```bash
git add display/tokens.py display/gm-display-app.py display/templates/picker.html tests/test_picker.py tests/test_tokens.py
git commit -m "feat(picker): GET /t/<slug> serves the roster, or redirects a bound device"
```

---

### Task 9: `POST /claim`

Does exactly what the second half of `/j/<token>` does today (`display/gm-display-app.py:1334-1348`): `mint_session()` → `set_active(player_id, sid)` → `set_cookie()`. `set_active` already revokes any previous session for the same character, so one-device-per-character is enforced by existing, tested code (`display/tokens.py:213-222`, `tests/test_tokens.py:135-146`).

Two obligations beyond the mint:

- **Every successful character claim broadcasts.** The GM is an LLM agent driving CLI tools; it will never poll `gm_table.py list`. A claim changes where that character's sheet and dice requests route, so a mis-tap on a DM-held row would otherwise silently reroute a PC and nobody would learn until a request went missing. The existing `_broadcast` plumbing carries `{"claim": {"character": ..., "from": "free"|"dm"|"reclaim"}}` to every SSE client; `index.html`'s handler ignores unknown keys, so no front-end task is required for it to be safe, and the DM console can grow a renderer later.
- **The rate bucket is charged only on failures** (bad slug, unknown character, 409) — same contract as `/t/<slug>` (Task 8). The Origin failure is deliberately *not* charged: a hostile page could otherwise drain the household's shared bucket with cross-origin POSTs it cannot even read the responses of.

`claim` is in `_PUBLIC_ENDPOINTS`, which means `_gate` returns before its CSRF Origin check (`display/gm-display-app.py:545-551`). The route therefore performs that check itself. Do not remove `claim` from `_PUBLIC_ENDPOINTS` to get the check for free — an unclaimed device has no identity, so the gate would 403 it before the handler runs.

**LAN limitation, stated plainly:** remote play is tunnel-or-nothing. `_ALLOWED_ORIGINS` (`:457-460`) covers localhost and `$GM_PUBLIC_HOST` only, so a `--lan` player at `http://192.168.1.20:5001/t/<slug>` gets 403 from this route's Origin check; and `_set_session_cookie` sets `Secure` for any non-loopback host, so even past the Origin check the cookie is dropped over plain http and the device loops picker → `/` → 403 → picker. Pre-existing (`docs/REMOTE-PLAY.md:140` concedes it), but the picker is now the only entry path, so it must not be discovered at the table.

**Files:**
- Modify: `display/gm-display-app.py` (cookie helper above the join route; the route after `table_page`)
- Test: `tests/test_picker.py` (append)

**Interfaces:**
- Consumes: `_TABLE.matches(slug) -> bool`, `_roster_states() -> list[dict]`, `tokens.mint_session(player_id, character, campaign, *, secret, role="player", ...)`, `tokens.verify(...)["sid"]`, `_REVOCATION.set_active(player_id, sid) -> str | None` (returns the prior sid), `tokens.DM_SID`, `_ALLOWED_ORIGINS` (`:458-460`), `_rate_ok` / `_rate_key`, `_broadcast(payload: dict)`, `_active_campaign_name() -> Optional[str]` (`:1972-1976` — do not write a fourth copy of the campaign-stamp read; `player_dice` already inlines a third at `:2254`).
- Produces:
  - `_set_session_cookie(resp, token) -> None` — sets `gm_session` with `max_age=tokens.SESSION_TTL_S`, `httponly=True`, `samesite="Lax"`, `secure` off only for localhost. `/j/<token>` is switched to it in this task.
  - Flask endpoint `claim` at `POST /claim`, body `{"slug": str, "character": str}`. `200 {"ok": true, "character": str, "role": "player"|"display"}` on success; `403 {"error": "bad origin"}` (uncharged); `404 {"error": "not found"}` for a bad slug or an unknown character (charged); `409 {"error": "taken"}` for a live claim by another device (charged); `429` when a failure finds the bucket full.
  - SSE event `{"claim": {"character": str, "from": "free"|"dm"|"reclaim"}}` on every successful *character* claim. Display-only claims broadcast nothing — they change no routing.
  Task 10's picker JS posts to it; Task 15 drives it in a browser.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_picker.py`, before the `if __name__` block:

```python
class ClaimRoute(PickerTestBase):
    def _claim(self, character, slug=None, headers=None):
        return self.client.post(
            "/claim",
            headers={**TUNNEL, **ORIGIN, **(headers or {})},
            json={"slug": slug if slug is not None else self.mod._TABLE.slug(),
                  "character": character})

    def _sid_of(self, response):
        cookie = next(c for c in response.headers.getlist("Set-Cookie")
                      if c.startswith("gm_session="))
        raw = cookie.split("gm_session=", 1)[1].split(";", 1)[0]
        return tokens.verify(raw, secret=self.secret, kind="session")

    def test_claiming_a_free_character_mints_a_player_cookie(self):
        r = self._claim("Kara")
        self.assertEqual(r.status_code, 200)
        p = self._sid_of(r)
        self.assertEqual(p["character"], "Kara")
        self.assertEqual(p["role"], "player")
        self.assertEqual(self.mod._REVOCATION.active()["kara"], p["sid"])

    def test_the_cookie_is_httponly_and_samesite_lax(self):
        cookie = next(c for c in self._claim("Kara").headers.getlist("Set-Cookie")
                      if c.startswith("gm_session="))
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_a_second_device_claiming_the_same_character_is_409(self):
        self._claim("Kara")
        self.client.delete_cookie("gm_session")
        r = self._claim("Kara")
        self.assertEqual(r.status_code, 409)

    def test_claiming_a_dm_held_character_succeeds_and_drops_dm_control(self):
        # A returning owner always wins, with no confirmation step — that is
        # the point of separating ownership from control.
        self.mod._REVOCATION.set_active("tom", tokens.DM_SID)
        r = self._claim("Tom")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.mod._REVOCATION.active()["tom"], self._sid_of(r)["sid"])

    def test_reclaiming_after_a_release_works(self):
        first = self._claim("Kara")
        sid = self._sid_of(first)["sid"]
        self.mod._REVOCATION.clear_active("kara")
        self.mod._REVOCATION.revoke_sid(sid)
        self.client.delete_cookie("gm_session")
        self.assertEqual(self._claim("Kara").status_code, 200)

    def test_claiming_display_only_mints_a_characterless_display_cookie(self):
        r = self._claim("")
        self.assertEqual(r.status_code, 200)
        p = self._sid_of(r)
        self.assertEqual(p["role"], "display")
        self.assertEqual(p["character"], "")
        self.assertEqual(self.mod._REVOCATION.active(), {})

    def test_an_unknown_character_is_404(self):
        self.assertEqual(self._claim("Gilda").status_code, 404)

    def test_a_bad_slug_is_404_and_mints_nothing(self):
        r = self._claim("Kara", slug="never-was-a-slug")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.mod._REVOCATION.active(), {})

    def test_a_foreign_origin_is_403(self):
        r = self._claim("Kara", headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.mod._REVOCATION.active(), {})

    def test_failing_claims_are_rate_limited(self):
        # Same contract as /t/: failures charge the bucket, successes never
        # do. These are all bad-slug failures, so the 429 appears.
        h = {"CF-Connecting-IP": "203.0.113.66", **ORIGIN}
        codes = [self.client.post("/claim", headers=h,
                                  json={"slug": "never-was-a-slug",
                                        "character": "Kara"}).status_code
                 for _ in range(25)]
        self.assertIn(429, codes)

    def test_a_claim_broadcasts_the_character_and_the_transition(self):
        # The GM is an LLM agent driving CLI tools; it will never poll
        # `gm_table.py list`. A claim reroutes the character's sheet and dice
        # requests, so the table hears about it over the existing SSE stream.
        events = []
        orig = self.mod._broadcast
        self.mod._broadcast = events.append
        try:
            self.mod._REVOCATION.set_active("tom", tokens.DM_SID)
            self.assertEqual(self._claim("Tom").status_code, 200)
        finally:
            self.mod._broadcast = orig
        claims = [e["claim"] for e in events if "claim" in e]
        self.assertEqual(claims, [{"character": "Tom", "from": "dm"}])

    def test_a_display_only_claim_broadcasts_nothing(self):
        # It changes no routing: no player_id, no active entry, nothing for
        # the table to react to.
        events = []
        orig = self.mod._broadcast
        self.mod._broadcast = events.append
        try:
            self.assertEqual(self._claim("").status_code, 200)
        finally:
            self.mod._broadcast = orig
        self.assertEqual([e for e in events if "claim" in e], [])

    def test_the_older_device_is_revoked_when_a_claim_is_forced_through(self):
        # Two devices, same character: set_active revokes the older, which
        # lands on the picker at its next request. Exercised through the store
        # rather than the 409 path, which is the picker's first line of
        # defence, not the enforcement.
        first = self._claim("Kara")
        old_sid = self._sid_of(first)["sid"]
        self.mod._REVOCATION.set_active("kara", "sid-newer")
        self.assertTrue(self.mod._REVOCATION.is_sid_revoked(old_sid))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_picker.py -q -k ClaimRoute`
Expected: FAIL — 405/404 on `POST /claim`.

- [ ] **Step 3: Extract the cookie helper**

In `display/gm-display-app.py`, add immediately above the `@app.route("/j/<path:token>")` decorator (`:1328` in the pre-plan tree; Task 7's gate edits have shifted it — anchor on the decorator):

```python
def _set_session_cookie(resp, token: str) -> None:
    """Attach a gm_session cookie. Secure only off-localhost: Chrome/Safari
    drop Secure cookies on plain http, which would break local dev; behind the
    tunnel the page is https."""
    resp.set_cookie("gm_session", token, max_age=tokens.SESSION_TTL_S,
                    httponly=True, samesite="Lax",
                    secure=not request.host.startswith(("localhost", "127.0.0.1")))
```

Replace the tail of the `join` route — from `resp = redirect("/")` through its `return resp` (the `resp.set_cookie(...)` block between them) — with:

```python
    resp = redirect("/")
    _set_session_cookie(resp, session_token)
    return resp
```

- [ ] **Step 4: Add the route**

Immediately after `table_page`:

```python
@app.route("/claim", methods=["POST"])
def claim():
    """Bind this device to a character, or to nothing (display only).

    Holding the table URL is the authorisation; no credential is typed by
    anyone. This is the second half of the old /j/<token> route, unchanged:
    mint_session -> set_active -> set_cookie. set_active already revokes any
    previous session for the same character, so one-device-per-character is
    enforced by existing, tested code.

    "claim" is in _PUBLIC_ENDPOINTS — an unclaimed device has no identity, so
    the gate would 403 it before this runs — which also means the gate's CSRF
    Origin check does not fire. It is done here instead.

    Rate limiting follows the /t/ contract: only failures charge the bucket.
    The Origin failure is deliberately uncharged — a hostile page could
    otherwise drain the household's shared CF-Connecting-IP bucket with
    cross-origin POSTs it cannot even read the responses of.
    """
    origin = request.headers.get("Origin") or request.headers.get("Referer", "")
    if not any(origin == o or origin.startswith(o + "/") for o in _ALLOWED_ORIGINS):
        return jsonify({"error": "bad origin"}), 403
    data = request.get_json(force=True, silent=True) or {}
    if not _TABLE.matches(data.get("slug")):
        if not _rate_ok(_rate_key()):
            return "Too Many Requests", 429
        return jsonify({"error": "not found"}), 404
    character = str(data.get("character", ""))[:50].strip()
    # Only ever a payload field — nothing reads it back for authorisation.
    campaign = re.sub(r"[^A-Za-z0-9_-]", "", _active_campaign_name() or "")[:50]

    if not character:
        # "Display only" — the shared screen's explicit choice. No player_id,
        # no entry in `active`: it claims nothing, so there is nothing to
        # release and nothing to broadcast. Its unbound state becomes a
        # chosen state.
        token = tokens.mint_session("", "", campaign, secret=_INVITE_SECRET,
                                    role="display")
        resp = jsonify({"ok": True, "character": "", "role": "display"})
        _set_session_cookie(resp, token)
        return resp

    row = next((r for r in _roster_states() if r["name"] == character), None)
    if row is None:
        if not _rate_ok(_rate_key()):
            return "Too Many Requests", 429
        return jsonify({"error": "not found"}), 404
    # "dm" is control, not ownership: a returning owner always wins, with no
    # confirmation step. Only a live device claim blocks. Note DM_SID is a
    # label, not a gate — letting the claim through here is the entirety of
    # "the owner wins"; nothing else reads it on the request path.
    if row["state"] == "taken":
        if not _rate_ok(_rate_key()):
            return "Too Many Requests", 429
        return jsonify({"error": "taken"}), 409

    player_id = character.lower()
    try:
        token = tokens.mint_session(player_id, character, campaign,
                                    secret=_INVITE_SECRET)
        sid = tokens.verify(token, secret=_INVITE_SECRET, kind="session")["sid"]
        prior = _REVOCATION.set_active(player_id, sid)
    except RuntimeError as e:
        # Corrupt/unreadable revocation store: fail closed as a plain 403,
        # never surface as a 500.
        return jsonify({"error": str(e)}), 403
    # The GM is an LLM agent driving CLI tools and will never poll
    # `gm_table.py list`; a claim reroutes this character's sheet and dice
    # requests, so the table hears about it — most of all the DM console,
    # which otherwise learns nothing when a mis-tap on a DM-held row silently
    # takes a PC over.
    _broadcast({"claim": {"character": character,
                          "from": ("dm" if prior == tokens.DM_SID
                                   else "reclaim" if prior else "free")}})
    resp = jsonify({"ok": True, "character": character, "role": "player"})
    _set_session_cookie(resp, token)
    return resp
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_picker.py -q`
Expected: PASS, 13 more than after Task 8.

- [ ] **Step 6: Run the whole suite and commit**

Run: `python3 -m pytest tests -q`
Expected: PASS, 416 passed. `tests/test_join_route.py` must still be green — `/j` is unchanged apart from the cookie helper.

```bash
git add display/gm-display-app.py tests/test_picker.py
git commit -m "feat(picker): POST /claim binds a device to a character or to nothing

Holding the table URL is the authorisation. set_active already enforces
one-device-per-character; a returning owner beats DM control with no
confirmation step."
```

---

### Task 10: The picker page

Self-contained: its own `<style>`, its own `<script>`, nothing shared with `index.html`. It renders four kinds of row plus two non-character entries. Rows carry their state in `data-state` so both the CSS and the tests read one source.

Copy, exactly:

| State | Row text | Tappable |
|---|---|---|
| `free` | the name alone | yes |
| `taken` | `<name>` + `on another device` | no |
| `dm` | `<name>` + `run by the DM` | yes — a returning owner always wins |
| — | `Create a character with the DM` | yes (claims nothing; mints a display cookie) |
| — | `Display only` | yes (mints a display cookie) |

**Files:**
- Modify: `display/templates/picker.html` (replace the Task 8 stub)
- Test: `tests/test_picker.py` (append)

**Interfaces:**
- Consumes: template variables `slug: str`, `rows: list[dict]` with keys `name` and `state` in `("free", "taken", "dm")`, `notice: str` — all three passed by `table_page` (Task 8). `POST /claim` with `{"slug", "character"}` returning 200/404/409/429 (Task 9).
- Produces: no server-side interface. Task 15 drives `#picker-roster li[data-state]`, `button.pick[data-character]`, `#pick-display`, `#pick-create` and `#picker-error` in a browser.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_picker.py`:

```python
PICKER = (REPO / "display" / "templates" / "picker.html").read_text()


class PickerTemplate(unittest.TestCase):
    def test_free_rows_are_buttons_and_taken_rows_are_not(self):
        # The state has to reach the DOM, not just the CSS: a disabled-looking
        # row that is still clickable is the failure mode here.
        self.assertIn('data-state="{{ row.state }}"', PICKER)
        self.assertIn("{% if row.state == 'taken' %}", PICKER)

    def test_the_three_labels_are_present_verbatim(self):
        self.assertIn("on another device", PICKER)
        self.assertIn("run by the DM", PICKER)
        self.assertIn("Display only", PICKER)
        self.assertIn("Create a character with the DM", PICKER)

    def test_the_page_never_renders_a_holder(self):
        # The app has only ever known characters, not people, and the picker
        # does not change that. Nothing but row.name may be interpolated.
        for forbidden in ("row.sid", "row.player_id", "row.device", "active["):
            self.assertNotIn(forbidden, PICKER)

    def test_a_conflict_refreshes_the_roster(self):
        self.assertIn("res.status === 409", PICKER)
        self.assertIn("location.reload()", PICKER)

    def test_success_goes_straight_to_play(self):
        self.assertIn("location.href = '/'", PICKER)

    def test_the_slug_is_posted_back_not_read_from_the_url(self):
        # The page is served at /t/<slug>; reading it back off location would
        # work, but the server-injected value is the one the server validated.
        self.assertIn("const SLUG =", PICKER)
        self.assertNotIn("location.pathname", PICKER)

    def test_rows_are_escaped(self):
        # Jinja autoescaping is on for .html templates; assert no |safe
        # anywhere near a roster name.
        self.assertNotIn("|safe", PICKER)

    def test_the_notice_slot_exists(self):
        self.assertIn('id="picker-notice"', PICKER)


class PickerRendering(PickerTestBase):
    def test_taken_rows_render_disabled_and_free_rows_render_tappable(self):
        self.mod._REVOCATION.set_active("kara", "sid-live")
        self.mod._REVOCATION.set_active("tom", tokens.DM_SID)
        body = self.client.get(f"/t/{self.mod._TABLE.slug()}",
                               headers=TUNNEL).get_data(as_text=True)
        self.assertIn('data-state="taken"', body)
        self.assertIn('data-state="dm"', body)
        self.assertIn('data-state="free"', body)
        self.assertIn('data-character="Zed"', body)
        self.assertNotIn('data-character="Kara"', body)   # taken: no button
        self.assertIn('data-character="Tom"', body)       # dm: reclaimable
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_picker.py -q -k "PickerTemplate or PickerRendering"`
Expected: FAIL — the stub has no buttons, no script, no labels.

- [ ] **Step 3: Write the page**

Replace `display/templates/picker.html` entirely:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Pick a character</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; padding: 24px 16px 48px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #14100a; color: #f0e2bd;
  }
  h1 { font-size: 1.35rem; font-weight: 600; margin: 0 0 4px; letter-spacing: 0.01em; }
  .sub { margin: 0 0 20px; font-size: 0.9rem; color: rgba(240,226,189,0.6); }
  #picker-notice:empty { display: none; }
  #picker-notice {
    margin: 0 0 18px; padding: 10px 12px; border-radius: 8px;
    background: rgba(220,180,90,0.14); border: 1px solid rgba(220,180,90,0.35);
    font-size: 0.9rem;
  }
  #picker-error:empty { display: none; }
  #picker-error {
    margin: 14px 0 0; padding: 10px 12px; border-radius: 8px;
    background: rgba(200,70,60,0.16); border: 1px solid rgba(200,70,60,0.4);
    font-size: 0.9rem;
  }
  ul { list-style: none; margin: 0; padding: 0; }
  li { margin: 0 0 10px; }
  .pick, .row-static {
    display: flex; align-items: center; justify-content: space-between;
    width: 100%; box-sizing: border-box;
    min-height: 56px; padding: 12px 16px;
    border-radius: 10px; border: 1px solid rgba(220,180,90,0.3);
    background: rgba(255,255,255,0.04); color: inherit;
    font: inherit; text-align: left;
  }
  .pick { cursor: pointer; }
  .pick:hover, .pick:focus-visible { background: rgba(220,180,90,0.16); }
  .row-static { opacity: 0.5; }
  .note { font-size: 0.82rem; color: rgba(240,226,189,0.65); margin-left: 12px; }
  .divider { margin: 24px 0 12px; font-size: 0.78rem; letter-spacing: 0.08em;
             text-transform: uppercase; color: rgba(240,226,189,0.45); }
</style>
</head>
<body>
<h1>Pick a character</h1>
<p class="sub">Tap the one you are playing. You can change this later.</p>
<p id="picker-notice">{{ notice }}</p>

<ul id="picker-roster">
{% for row in rows %}
  <li data-state="{{ row.state }}">
  {% if row.state == 'taken' %}
    <span class="row-static"><span>{{ row.name }}</span><span class="note">on another device</span></span>
  {% elif row.state == 'dm' %}
    <button class="pick" type="button" data-character="{{ row.name }}"><span>{{ row.name }}</span><span class="note">run by the DM</span></button>
  {% else %}
    <button class="pick" type="button" data-character="{{ row.name }}"><span>{{ row.name }}</span></button>
  {% endif %}
  </li>
{% endfor %}
</ul>

<p class="divider">Or</p>
<ul>
  <li><button class="pick" id="pick-create" type="button" data-character=""><span>Create a character with the DM</span></button></li>
  <li><button class="pick" id="pick-display" type="button" data-character=""><span>Display only</span></button></li>
</ul>

<p id="picker-error"></p>

<script>
// The slug the server validated, not one re-read off location: the page is
// served at /t/<slug>, but the server-injected value is the authoritative one.
const SLUG = {{ slug|tojson }};
const _err = document.getElementById('picker-error');

async function _claim(character) {
  _err.textContent = '';
  let res;
  try {
    res = await fetch('/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slug: SLUG, character: character })
    });
  } catch (e) {
    _err.textContent = 'Could not reach the table. Check your connection and try again.';
    return;
  }
  if (res.ok) { location.href = '/'; return; }
  if (res.status === 409) {
    // Someone else got there first. The roster is stale, so re-render it.
    location.reload();
    return;
  }
  if (res.status === 429) {
    _err.textContent = 'Too many tries. Wait a minute and try again.';
    return;
  }
  if (res.status === 404) {
    _err.textContent = 'This table link is no longer valid — ask your DM for the new one.';
    return;
  }
  _err.textContent = 'That did not work. Ask your DM.';
}

document.querySelectorAll('button.pick').forEach(btn => {
  btn.addEventListener('click', () => _claim(btn.dataset.character || ''));
});
</script>
</body>
</html>
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_picker.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite and commit**

Run: `python3 -m pytest tests -q`
Expected: PASS, 425 passed.

```bash
git add display/templates/picker.html tests/test_picker.py
git commit -m "feat(picker): the roster page, four states plus create and display-only"
```

---

# Phase D — The play surface

---

### Task 11: `window.GM_SESSION` replaces `window.GM_BOUND_CHARACTER`

Today `""` means both "you are the GM console" and "you are nobody". `role` is the channel that has never existed, and its absence is why the page could not distinguish the GM's console from an anonymous viewer and therefore could not offer either one the right controls.

**Files:**
- Modify: `display/gm-display-app.py` — the whole `index()` view (`:1352-1373` in the pre-plan tree; Tasks 7-9 insert code above it, so anchor on `@app.route("/")`, not the numbers)
- Modify: `display/templates/index.html:17-21` (drift-free — above every earlier template edit) and the `GM_IDENTITY` declaration (locate by the anchor text Task 1 wrote)
- Test: `tests/test_full_display_controls.py:25-84`, `tests/test_picker.py`

**Interfaces:**
- Consumes: `_is_local() -> bool`, `_bound_character`, `g.identity` with roles `player | display | local | gm` (Task 7).
- Produces:
  - `index()` passes `gm_session={"character": str, "role": str, "claimed": bool}` to `render_template`.
  - `window.GM_SESSION` — a JS object on every page. `role` is one of `"player" | "local" | "display"`. `character` is `""` unless `role === "player"`. `claimed` is `true` only for `role === "player"`.
  - `const GM_IDENTITY` — unchanged name and type (`string`), now derived from `window.GM_SESSION.character`. Task 12's call sites (`if (_inputMode) { ... _initDicePad({ bind: GM_IDENTITY }); }` and `else if (GM_IDENTITY) {`) keep using it verbatim.
  - `const GM_ROLE` — a `string`, one of the three roles. Task 12 does not use it; it exists so the page can stop inferring role from an empty string, and Task 15 asserts on it.
  - `const _streamChar = GM_IDENTITY;` (`display/templates/index.html:7123`) is **unchanged and must stay unchanged**. `/stream?character=` keeps carrying a name as a routing key, and that is already safe: `_bound_character` discards the argument outright for an authenticated player (`display/gm-display-app.py:2691`) and, after Task 7, returns `""` for a display identity. Because `GM_IDENTITY` now comes from `GM_SESSION`, the client passes the session's character rather than anything read off the URL — which is the spec's requirement, satisfied by the existing line. `tests/test_full_display_controls.py:455` pins it.

- [ ] **Step 1: Write the failing tests**

In `tests/test_full_display_controls.py`, replace the five methods of `class BoundCharacterInjection` (lines 38-84) with:

```python
    def test_local_console_is_the_local_role_with_no_character(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('"role": "local"', html)
        self.assertIn('"character": ""', html)
        self.assertIn('"claimed": false', html)

    def test_authenticated_player_gets_their_character_and_the_player_role(self):
        self._session_cookie("Mira")
        html = self.client.get("/", headers=TUNNEL).get_data(as_text=True)
        self.assertIn('"character": "Mira"', html)
        self.assertIn('"role": "player"', html)
        self.assertIn('"claimed": true', html)

    def test_local_browser_with_a_player_cookie_is_still_local(self):
        # Sessions last 30 days and there is no logout route. A GM who opens a
        # player's picker link in their own console browser must not have
        # their full display bound to that character for a month. index()
        # checks _is_local() directly because _gate's downgrade only fires for
        # endpoints outside _PLAYER_ENDPOINTS, and index is inside that set.
        self._session_cookie("Mira")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('"role": "local"', html)
        self.assertIn('"character": ""', html)

    def test_a_display_cookie_is_the_display_role(self):
        token = tokens.mint_session("", "", "camp", secret=self.secret, role="display")
        self.client.set_cookie("gm_session", token)
        html = self.client.get("/", headers=TUNNEL).get_data(as_text=True)
        self.assertIn('"role": "display"', html)
        self.assertIn('"character": ""', html)
        self.assertIn('"claimed": false', html)

    def test_the_character_is_json_escaped(self):
        # tojson is what makes a quote or a </script> in a name unable to
        # break out of the object literal.
        self._session_cookie('Ka"ra</script>')
        html = self.client.get("/", headers=TUNNEL).get_data(as_text=True)
        self.assertNotIn("</script><", html.split("window.GM_SESSION")[1][:400])
        self.assertIn("\\u003c", html.split("window.GM_SESSION")[1][:400])
```

And in `class IdentityResolver`, replace `test_identity_comes_from_the_server_alone` (retargeted in Task 1):

```python
    def test_identity_comes_from_the_server_session_object_alone(self):
        self.assertIn("const GM_IDENTITY = ((window.GM_SESSION && window.GM_SESSION.character) || '').trim();", MARKUP)
        self.assertIn("const GM_ROLE = (window.GM_SESSION && window.GM_SESSION.role) || 'local';", MARKUP)
        self.assertNotIn("_idParams", MARKUP)
        self.assertNotIn("GM_BOUND_CHARACTER", MARKUP)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_full_display_controls.py -q -k "BoundCharacterInjection or IdentityResolver"`
Expected: FAIL — `"role"` is not in the HTML and `GM_BOUND_CHARACTER` still is.

- [ ] **Step 3: Build the session object server-side**

In `display/gm-display-app.py`, replace the whole `index()` view — from its `@app.route("/")` decorator through the closing parenthesis of the `render_template(...)` call (`:1352-1373` in the pre-plan tree; Tasks 7-9 have shifted it — anchor on the decorator) — with:

```python
@app.route("/")
def index():
    # The URL stops being a control surface, so the template's injected
    # identity has to carry the one thing the page could never see: whether
    # "no character" means "you are the GM console" or "you are nobody".
    #
    # _is_local() is checked directly rather than through _bound_character
    # because the two must diverge here: _gate's un-brick downgrade only fires
    # for endpoints outside _PLAYER_ENDPOINTS, and index is in that set, so it
    # never runs for "/". Sessions last SESSION_TTL_S (30 days) and there is
    # no logout route, so without this a GM who opens a player's picker link
    # in their own console browser — just to check it works — would have their
    # full display bound to that character for a month.
    ident = getattr(g, "identity", None) or {}
    role = ident.get("role", "")
    if _is_local() or role in ("gm", "local"):
        gm_session = {"character": "", "role": "local", "claimed": False}
    elif role == "player":
        gm_session = {"character": _bound_character(""), "role": "player",
                      "claimed": True}
    else:
        gm_session = {"character": "", "role": "display", "claimed": False}
    return render_template(
        "index.html",
        narrator_voice=_read_narrator_voice(),
        tts_available=(_tts is not None),
        ui_manifest=_load_ui_manifest(),
        gm_session=gm_session,
    )
```

- [ ] **Step 4: Inject it into the template**

In `display/templates/index.html`, replace lines 17-21:

```html
<!-- Session identity, injected by Flask. The gm_session cookie is httponly,
     so this is the only way the page can know who it is.
       character — "" unless role is "player"
       role      — "player" | "local" | "display"
       claimed   — true only for "player"
     Before this object existed the page received a bare name, and "" meant
     both "you are the GM console" and "you are nobody" — which is why it
     could offer neither one the right controls. tojson escapes it. -->
<script>window.GM_SESSION = {{ gm_session|tojson }};</script>
```

- [ ] **Step 5: Read it in the resolver**

In `display/templates/index.html`, in the comment block Task 1 wrote, change the first paragraph's first line from `window.GM_BOUND_CHARACTER — the server's answer` to `window.GM_SESSION — the server's answer`, and replace the declaration line:

```javascript
const GM_IDENTITY = ((window.GM_SESSION && window.GM_SESSION.character) || '').trim();
const GM_ROLE = (window.GM_SESSION && window.GM_SESSION.role) || 'local';
```

Then check for any other reader:

```bash
grep -n "GM_BOUND_CHARACTER" display/templates/index.html tests/
```

Expected: no matches. Any that appear are comments left over from Task 1 — reword them to name `GM_SESSION`.

- [ ] **Step 6: Run the tests**

Run: `python3 -m pytest tests/test_full_display_controls.py tests/test_picker.py -q`
Expected: PASS.

- [ ] **Step 7: Run the whole suite and commit**

Run: `python3 -m pytest tests -q`
Expected: PASS, 425 passed (no net change — five injection tests replaced five, one resolver test replaced one).

```bash
git add display/gm-display-app.py display/templates/index.html tests/test_full_display_controls.py
git commit -m "feat(display): inject a session object with a real role

'' used to mean both 'you are the GM console' and 'you are nobody', which is
why the page could offer neither the right controls."
```

---

### Task 12: Phone versus full display becomes a layout preference

The button that produced the original defect stops having a decision to make. Phone and full are a `localStorage` preference now: the same person can switch freely, there is nothing to preserve across the toggle and nothing to drop. The Phone Mode dropdown — a character picker that rewrote the URL — goes away entirely; the picker at `/t/<slug>` is the only place identity is chosen.

The four tests this deletes are all pinned to the URL mechanism and have no claim left once the mechanism is gone. Delete them; do not re-anchor them onto the new predicate, which Step 1 covers directly.

**Files:**
- Modify: `display/templates/index.html` — the `#phone-mode-menu` CSS (`:2485-2531`), its theme overrides (`:2851-2861`, `:3092-3096`) — these pre-6345 ranges are drift-free and stay numeric; the `_modeSwitcherCachePlayers(...)` call inside the SSE `stats` handler; the mode predicate (from the `// ── Input-only mode for mobile players` comment through `_initModeSwitcher(_inputMode);` and its block's closing brace); the mode switcher (from the `// ── Mode switcher` comment through the closing brace of `_initModeSwitcher`). **Everything past line 6345 has drifted under Tasks 1 and 11 — locate those regions by anchor text, never by number.**
- Modify: `tests/test_full_display_controls.py:201`, `:998-1004`, `:1007-1043`
- Test: `tests/test_full_display_controls.py`

**Interfaces:**
- Consumes: `const GM_IDENTITY` (a string, `""` when unbound) and `const GM_ROLE` from Task 11; `_initDicePad(opts)` where `opts.bind` is the only binding source; `_initModeSwitcher(inputMode)`; `_inputArrow`.
- Produces:
  - `localStorage['gm-layout']` — `"phone"` or `"full"`, absent means "decide from the viewport".
  - `const _inputMode` — a boolean, still the name the two `_initDicePad` call sites and `_initModeSwitcher(_inputMode)` read. `PHONE_CALL_SITE` and `FULL_DISPLAY_CALL_SITE` in `tests/test_full_display_controls.py:171-193` stay byte-identical.
  - `#phone-mode-btn` and `#full-mode-btn` keep their ids (all their CSS is keyed on them) and become plain toggles: write the preference, `location.reload()`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_full_display_controls.py`, replace `class ModePredicate` (lines 1007-1043) entirely:

```python
class LayoutPreference(unittest.TestCase):
    def _predicate_block(self):
        start = MARKUP.index(CALL_SITE_ANCHOR)
        end = MARKUP.index(CALL_SITE_END, start)
        return MARKUP[start:end]

    def test_the_layout_is_read_from_localstorage_not_the_url(self):
        # Phone vs full is a layout preference, not an identity. The URL used
        # to carry ?view= and ?char=, which is how "Phone Mode -> Kara" then
        # "Full Display" left a shared screen still acting as Kara.
        block = self._predicate_block()
        self.assertIn("localStorage.getItem('gm-layout')", block)
        for url_read in ("_qp", "URLSearchParams", "location.search",
                         "'view'", "'char'", "'character'"):
            self.assertNotIn(url_read, block, url_read)

    def test_an_explicit_preference_beats_the_viewport(self):
        block = self._predicate_block()
        self.assertIn("_stored === 'phone'", block)
        self.assertIn("_stored !== 'full'", block)

    def test_the_viewport_default_uses_the_templates_own_breakpoint(self):
        # 700px is the template's real phone breakpoint (there is no 430px
        # query); pinned so the JS default and the CSS never disagree.
        self.assertIn("matchMedia('(max-width: 700px)')", self._predicate_block())
        self.assertIn("@media (max-width: 700px)", MARKUP)

    def test_both_buttons_write_the_preference_and_reload(self):
        self.assertIn("localStorage.setItem('gm-layout', 'full');", MARKUP)
        self.assertIn("localStorage.setItem('gm-layout', 'phone');", MARKUP)
        self.assertEqual(MARKUP.count("location.reload();"), 2)

    def test_the_phone_mode_character_dropdown_is_gone(self):
        # It was a second way to choose an identity, and the one that wrote
        # ?char= into the URL. /t/<slug> is now the only picker.
        for gone in ("phone-mode-menu", "_modePlayersCache",
                     "_modeSwitcherCachePlayers", "pm-opt", "pm-header",
                     "Bind this device to"):
            self.assertNotIn(gone, MARKUP, gone)

    def test_neither_button_touches_the_url(self):
        start = MARKUP.index("function _initModeSwitcher")
        end = MARKUP.index("// ── One place that knows how to talk to", start)
        block = MARKUP[start:end]
        for url_write in ("new URL(", "searchParams", "location.href ="):
            self.assertNotIn(url_write, block, url_write)
```

Also update the outside-click closer count at `tests/test_full_display_controls.py:998-1004` — one of the two closers existed only to shut the Phone Mode menu:

```python
    def test_the_one_outside_click_closer_still_exists(self):
        # The TTS voice menu's. The Phone Mode menu's went with the menu.
        self.assertEqual(MARKUP.count("document.addEventListener('click', () => {"), 1)
        self.assertIn("document.querySelectorAll('.tts-voice-menu')"
                      ".forEach(m => { m.hidden = true; });", MARKUP)
```

And retarget the diagnostic window constant at line 201:

```python
CALL_SITE_ANCHOR = "const _stored = (localStorage.getItem('gm-layout') || '').trim();"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_full_display_controls.py -q`
Expected: FAIL — `ValueError: substring not found` from `CALL_SITE_ANCHOR` (which now windows several `DiceRequestGating` tests too), plus every `LayoutPreference` assertion.

- [ ] **Step 3: Replace the mode predicate**

In `display/templates/index.html`, replace the region starting at the line beginning `// ── Input-only mode for mobile players` and ending at the closing `}` of the block whose last statement is `_initModeSwitcher(_inputMode);` (this was `:7275-7321` before the plan started; Tasks 1 and 11 have shifted it — a literal line-range cut here would take part of the SSE handler with it, so anchor on the text) with:

```javascript
// ── Layout: phone versus full display ────────────────────────────────────
// A preference, not an identity. Stored per-browser in
// localStorage['gm-layout'] ("phone" | "full"; absent = decide from the
// viewport). The same person can switch freely: there is nothing to preserve
// across the toggle and nothing to drop.
//
// This used to be driven by ?view= and ?char=, and ?char= alone implied the
// phone view. That is how "Phone Mode -> Kara" then "Full Display" left the
// shared display still acting as Kara — the toggle carried a binding, so it
// had a decision to make and made the wrong one. It no longer has one.
{
  const _stored = (localStorage.getItem('gm-layout') || '').trim();
  // 700px is the template's own phone breakpoint (see the @media rule far
  // above); an explicit preference always beats it.
  const _inputMode = _stored === 'phone'
    || (_stored !== 'full' && window.matchMedia('(max-width: 700px)').matches);
  if (_inputMode) {
    document.body.classList.add('input-only');
    const ip = document.getElementById('input-panel');
    if (ip) ip.classList.remove('collapsed');
    _initDicePad({ bind: GM_IDENTITY });
  }
  // Full display: a bound player gets the same pad and the same DM-request
  // handling, so they can roll without giving up the narration. An unbound
  // display (GM console, shared screen, display-only device) initialises
  // nothing — it has no character to roll as, and installing the request
  // handlers there would badge the GM with their own requests.
  // The panel is expanded here for the same reason the phone branch does it
  // above. #input-panel ships with class="collapsed", and .collapsed hides
  // #input-body outright — which holds the roll pad's request badge and the
  // Sheet and Dice buttons. The only other auto-expands are staged input
  // arriving and the autorun countdown, neither of which fires on a fresh
  // load with an empty queue, so a player landing here from the picker would
  // otherwise get a shut "Party Input" bar with no way to reach any of it.
  // The arrow goes with it: the phone branch can skip that because
  // body.input-only hides #input-panel-header outright, but here the header
  // is visible, and an expanded panel still showing the collapsed glyph makes
  // the first header click read as a no-op.
  else if (GM_IDENTITY) {
    const ip = document.getElementById('input-panel');
    if (ip) ip.classList.remove('collapsed');
    if (_inputArrow) _inputArrow.textContent = '▼';
    _initDicePad({ bind: GM_IDENTITY });
  }
  _initModeSwitcher(_inputMode);
}
```

- [ ] **Step 4: Replace the mode switcher**

Replace the region starting at the line beginning `// ── Mode switcher ───` and ending at the closing `}` of `function _initModeSwitcher` — the line immediately before the `// ── One place that knows how to talk to /character/<name>` comment (`:7327-7443` pre-plan; anchor on the text) — with:

```javascript
// ── Layout switcher ───────────────────────────────────────────────────────
// One button, both directions, no menu. It writes localStorage['gm-layout']
// and reloads — the reload is deliberate: body.input-only gates ~40 CSS rules
// and two init branches, and re-running the whole load is cheaper to reason
// about than unwinding them live.
//
// This used to be a character picker that navigated to ?view=input&char=<Name>,
// which is the mechanism the character picker at /t/<slug> replaces. Choosing
// an identity is not a layout concern and no longer lives here.
//
// Each branch writes its own setItem/reload pair rather than sharing a helper:
// two lines, and the test that pins them wants each direction named.
function _initModeSwitcher(inputMode) {
  const btn = document.createElement('button');
  btn.type = 'button';
  if (inputMode) {
    btn.id = 'full-mode-btn';
    btn.title = 'Switch to the full display (read the narration on this device)';
    btn.textContent = '👁 Full Display';
    btn.addEventListener('click', e => {
      e.stopPropagation();
      localStorage.setItem('gm-layout', 'full');
      location.reload();
    });
  } else {
    btn.id = 'phone-mode-btn';
    btn.title = 'Switch this device to the phone input layout';
    btn.textContent = '📱 Phone Mode';
    btn.addEventListener('click', e => {
      e.stopPropagation();
      localStorage.setItem('gm-layout', 'phone');
      location.reload();
    });
  }
  document.body.appendChild(btn);
}
```

- [ ] **Step 5: Delete the menu's CSS and the cache call**

- Delete the line `_modeSwitcherCachePlayers(payload.stats.players);` inside the SSE `stats` handler (`:7160` pre-plan; find it by text).
- Delete the `#phone-mode-menu` rule blocks at `:2485-2531` (`#phone-mode-menu`, `.open`, `.pm-header`, `.pm-opt`, `.pm-opt:hover`, `.pm-empty`).
- Delete the light-theme overrides at `:2851-2861` (`:root[data-theme="light"] #phone-mode-menu` and its four descendants).
- Delete the system-theme override at `:3092-3096` (`:root:not([data-theme]) #phone-mode-menu` and `.pm-opt`).
- Keep every `#phone-mode-btn` and `#full-mode-btn` rule — both ids survive.

Verify:

```bash
grep -c "phone-mode-menu\|pm-opt\|pm-header\|pm-empty\|_modePlayersCache\|_modeSwitcherCachePlayers" display/templates/index.html
```

Expected: `0`.

- [ ] **Step 6: Run the tests**

Run: `python3 -m pytest tests/test_full_display_controls.py tests/test_remote_player_console.py -q`
Expected: PASS. `PHONE_CALL_SITE` and `FULL_DISPLAY_CALL_SITE` must still match verbatim — if they do not, the replacement in Step 3 changed statement text or nesting inside those two branches and must be corrected, not the constants.

- [ ] **Step 7: Run the whole suite and commit**

Run: `python3 -m pytest tests -q`
Expected: PASS, 428 passed (three `ModePredicate` tests deleted, six `LayoutPreference` tests added).

```bash
git add display/templates/index.html tests/test_full_display_controls.py
git commit -m "feat(display): phone vs full is a layout preference, not an identity

The toggle used to carry a character binding through the URL, which is how
two clicks left a shared screen acting as a player with no way out."
```

---

# Phase E — Retire the invite-link model

---

### Task 13: `scripts/gm_table.py`

The GM's control surface for the table and for claims. Replaces `gm_invite.py`, which Task 14 deletes.

**`rotate` must actually revoke.** Swapping the slug alone would leave every already-minted `gm_session` cookie valid for `SESSION_TTL_S` (30 days, `display/tokens.py:26`) — none of them contains the slug. The spec names `rotate` as the mitigation for a leaked URL, and a display-only session holds no `active` entry and no recorded sid, so there would be no command that evicts a stranger who took the URL off a screen share and tapped "Display only". Therefore `rotate` also regenerates `.invite_secret`: every cookie dies, everyone re-taps from the new URL, which is the intent after a leak. (Chosen over a per-token epoch integer: fewer moving parts across `table.py` / `tokens.py` / the gate.) One operational caveat, stated in the CLI's output: the running app loaded `_INVITE_SECRET` at import (`display/gm-display-app.py:54`), so the secret half of a rotate takes effect at the next app start — the slug half is immediate, because `TableStore` re-reads its file per request, so no *new* claims can happen against the old URL from the moment rotate returns.

**Files:**
- Create: `scripts/gm_table.py`
- Test: `tests/test_gm_table.py`

**Interfaces:**
- Consumes: `table.TableStore(path)` with `.slug() -> str` and `.rotate() -> str` (Tasks 4-5); `tokens.ensure_secret(path) -> str` (`display/tokens.py:39`); `tokens.RevocationStore(path)` with `.active() -> dict`, `.is_sid_revoked(sid) -> bool`, `.revoke_sid(sid) -> None`, `.set_active(player_id, sid) -> str | None`, `.clear_active(player_id) -> str | None` (Task 3); `tokens.DM_SID` (Task 8).
- Produces: a CLI with `--display-dir` (tests override it, same as `gm_invite.py` did) and five subcommands: `show`, `rotate`, `list`, `dm <CHARACTER>`, `release <CHARACTER>`. `rotate` replaces both the slug and `.invite_secret`, invalidating every existing session token, and prints a restart reminder to stderr. Exit 0 on success, 1 on a stated error printed to stderr with no traceback.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gm_table.py`:

```python
"""tests/test_gm_table.py — the GM's table CLI: show, rotate, list, dm, release."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import table  # noqa: E402
import tokens  # noqa: E402

SCRIPT = REPO / "scripts" / "gm_table.py"


def run_table(display_dir, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--display-dir", str(display_dir), *args],
        capture_output=True, text=True)


class GmTableTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.display = pathlib.Path(self._tmp.name)

    def _store(self):
        return tokens.RevocationStore(self.display / ".revoked.json")

    def test_show_mints_a_slug_on_first_run_and_is_stable(self):
        first = run_table(self.display, "show")
        self.assertEqual(first.returncode, 0, first.stderr)
        slug = first.stdout.strip().rsplit("/t/", 1)[1]
        self.assertRegex(slug, table.SLUG_RE)
        self.assertIn(slug, run_table(self.display, "show").stdout)

    def test_show_prints_a_full_url_with_the_given_host(self):
        out = run_table(self.display, "show", "--host", "game.example.com")
        self.assertTrue(out.stdout.strip().startswith("https://game.example.com/t/"))

    def test_localhost_gets_http_not_https(self):
        out = run_table(self.display, "show", "--host", "localhost:5001")
        self.assertTrue(out.stdout.strip().startswith("http://localhost:5001/t/"))

    def test_rotate_replaces_the_slug(self):
        old = run_table(self.display, "show").stdout.strip()
        new = run_table(self.display, "rotate").stdout.strip()
        self.assertNotEqual(old, new)
        self.assertEqual(run_table(self.display, "show").stdout.strip(), new)

    def test_rotate_regenerates_the_secret_killing_every_cookie(self):
        # The whole point of rotate as a leak mitigation: cookies do not
        # contain the slug, so swapping the slug alone would leave every
        # minted session valid for 30 days — including a display-only session
        # with no active entry and no recorded sid, which no other command
        # can evict. Verified against the on-disk secret, i.e. the state the
        # server holds after its next start.
        old_secret = tokens.ensure_secret(self.display / ".invite_secret")
        cookie = tokens.mint_session("kara", "Kara", "c", secret=old_secret)
        out = run_table(self.display, "rotate")
        self.assertEqual(out.returncode, 0, out.stderr)
        new_secret = (self.display / ".invite_secret").read_text().strip()
        self.assertNotEqual(new_secret, old_secret)
        self.assertIsNone(tokens.verify(cookie, secret=new_secret, kind="session"))
        self.assertIn("restart", out.stderr.lower())

    def test_list_reports_free_and_claimed_and_dm(self):
        store = self._store()
        store.set_active("kara", "sid-1")
        store.set_active("tom", tokens.DM_SID)
        out = run_table(self.display, "list").stdout
        self.assertIn("kara", out)
        self.assertIn("claimed", out)
        self.assertIn("tom", out)
        self.assertIn("DM", out)

    def test_list_with_nothing_claimed_says_so(self):
        self.assertIn("no claims", run_table(self.display, "list").stdout)

    def test_release_clears_the_claim_and_revokes_the_sid(self):
        store = self._store()
        store.set_active("kara", "sid-1")
        out = run_table(self.display, "release", "Kara")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(store.is_sid_revoked("sid-1"))
        self.assertNotIn("kara", store.active())

    def test_release_of_an_unclaimed_character_errors(self):
        out = run_table(self.display, "release", "Nobody")
        self.assertEqual(out.returncode, 1)
        self.assertIn("error:", out.stderr)

    def test_dm_takes_control_and_revokes_the_holding_device(self):
        store = self._store()
        store.set_active("kara", "sid-1")
        out = run_table(self.display, "dm", "Kara")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(store.active()["kara"], tokens.DM_SID)
        self.assertTrue(store.is_sid_revoked("sid-1"))

    def test_release_of_a_dm_held_character_clears_without_revoking_the_sentinel(self):
        store = self._store()
        store.set_active("kara", tokens.DM_SID)
        run_table(self.display, "release", "Kara")
        self.assertNotIn("kara", store.active())
        self.assertFalse(store.is_sid_revoked(tokens.DM_SID))

    def test_a_corrupt_store_surfaces_a_plain_error_not_a_traceback(self):
        (self.display / ".revoked.json").write_text("not json {{{")
        out = run_table(self.display, "list")
        self.assertEqual(out.returncode, 1)
        self.assertIn("error:", out.stderr)
        self.assertNotIn("Traceback", out.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_gm_table.py -q`
Expected: FAIL — `can't open file '.../scripts/gm_table.py'`, returncode 2 on every case.

- [ ] **Step 3: Write the CLI**

Create `scripts/gm_table.py`:

```python
#!/usr/bin/env python3
"""
gm_table.py — the table URL and the claims on it.

Usage:
    python3 scripts/gm_table.py show    [--host game.example.com]
    python3 scripts/gm_table.py rotate  [--host game.example.com]
    python3 scripts/gm_table.py list
    python3 scripts/gm_table.py dm      <CHARACTER>
    python3 scripts/gm_table.py release <CHARACTER>

The table URL is one long, readable, unguessable path that names the TABLE,
never a character — anyone holding it can claim any free character, which
among a known group is the intent. `rotate` is the mitigation when it leaks:
it replaces the slug AND regenerates the signing secret, so every existing
session cookie dies too (at the app's next start — the process holds the old
secret in memory; the old URL stops matching immediately).

Ownership ("Aldric belongs to a person") is not stored here and is not the
GM's to change with this tool. Only CONTROL is: `dm` takes it, `release`
drops it, and a player reclaiming through the picker always wins.
"""
import argparse
import os
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "display"))
import table  # noqa: E402
import tokens  # noqa: E402


def _url(host: str, slug: str) -> str:
    scheme = "http" if host.startswith(("localhost", "127.0.0.1")) else "https"
    return f"{scheme}://{host}/t/{slug}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--display-dir", default=str(_REPO / "display"),
                    help="where .table.json / .revoked.json live (tests override)")
    ap.add_argument("--host", default=os.environ.get("GM_PUBLIC_HOST", "localhost:5001"))
    ap.add_argument("command", choices=["show", "rotate", "list", "dm", "release"])
    ap.add_argument("character", nargs="?")
    args = ap.parse_args()

    display = pathlib.Path(args.display_dir)
    tbl = table.TableStore(display / ".table.json")
    store = tokens.RevocationStore(display / ".revoked.json")

    if args.command == "show":
        print(_url(args.host, tbl.slug()))
        return 0

    if args.command == "rotate":
        # A leaked URL is mitigated only if existing cookies die with it:
        # cookies do not contain the slug, so swapping the slug alone leaves
        # every minted gm_session valid for SESSION_TTL_S (30 days) —
        # including a display-only session with no active entry and no
        # recorded sid, which `release` cannot evict. Regenerating the
        # signing secret invalidates them all; everyone re-taps from the new
        # URL, which is the intent after a leak.
        (display / ".invite_secret").unlink(missing_ok=True)
        tokens.ensure_secret(display / ".invite_secret")
        print(_url(args.host, tbl.rotate()))
        print("note: restart the display app — it holds the old signing "
              "secret in memory; the old URL is dead immediately, old "
              "cookies die at the restart", file=sys.stderr)
        return 0

    if args.command == "list":
        active = store.active()
        if not active:
            print("no claims")
            return 0
        for player_id, sid in sorted(active.items()):
            if sid == tokens.DM_SID:
                print(f"{player_id}: run by the DM")
            elif store.is_sid_revoked(sid):
                print(f"{player_id}: claimed (revoked — will land on the picker)")
            else:
                print(f"{player_id}: claimed")
        return 0

    if not args.character:
        print(f"error: {args.command} needs a character name", file=sys.stderr)
        return 1
    player_id = args.character.strip().lower()

    if args.command == "dm":
        # set_active revokes whatever device held it, which is exactly "the
        # DM takes over". Ownership is untouched: the player reclaims through
        # the picker with no confirmation step.
        store.set_active(player_id, tokens.DM_SID)
        print(f"{player_id}: run by the DM")
        return 0

    # release
    sid = store.clear_active(player_id)
    if sid is None:
        print(f"error: no claim on '{player_id}'", file=sys.stderr)
        return 1
    if sid != tokens.DM_SID:
        store.revoke_sid(sid)
    print(f"released: {player_id}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_gm_table.py -q`
Expected: PASS, 12 passed.

- [ ] **Step 5: Run the whole suite and commit**

Run: `python3 -m pytest tests -q`
Expected: PASS, 440 passed.

```bash
git add scripts/gm_table.py tests/test_gm_table.py
git commit -m "feat(cli): gm_table.py — show/rotate the table URL, list/dm/release claims"
```

---

### Task 14: Delete the invite-link model

Everything that only existed to serve `/j/<token>` goes. This is the task with the test deletions in it; do them explicitly and per file, not by deleting whatever turns red.

Line numbers in both tables below are from the **pre-plan tree**: Tasks 3, 6 and 8 have appended tests to `tests/test_tokens.py` since, so everything past `:105` has shifted. Locate every test by name, not by number.

**Deletions — exactly these, nothing else:**

| File | What | Count |
|---|---|---|
| `tests/test_join_route.py` | whole file | 6 |
| `tests/test_gm_invite.py` | whole file | 6 |
| `tests/test_tokens.py:17-23` | `test_join_roundtrip` | 1 |
| `tests/test_tokens.py:102-105` | `test_minted_join_token_is_short` | 1 |
| `tests/test_tokens.py:116-119` | `test_jti_single_use` | 1 |
| `tests/test_tokens.py:121-128` | `test_jti_concurrent_consume_exactly_once` | 1 |
| | **total** | **16** |

**Retargets in `tests/test_tokens.py` — 14, none of them deletions.** Eleven mint or verify with `kind="join"` and move to `kind="session"` / `mint_session`. **These are the signature-verification suite and must not be deleted:**

| Line | Test | Change |
|---|---|---|
| 37 | `test_tampered_token_rejected` | `mint_join` → `mint_session`, `kind="join"` → `kind="session"` |
| 43 | `test_wrong_secret_rejected` | same |
| 47 | `test_wrong_kind_rejected` | `mint_session(...)`, then `verify(..., kind="join")` → `None` (inverted) |
| 51 | `test_ttl_expiry` | `mint_join` → `mint_session`, both `kind=` args |
| 56 | `test_garbage_rejected` | `kind="join"` → `kind="session"` |
| 60 | `test_non_ascii_sig_does_not_raise` | `kind="join"` → `kind="session"` |
| 65 | `test_non_hex_sig_rejected` | `kind="join"` → `kind="session"` |
| 68 | `test_oversized_token_rejected` | `kind="join"` → `kind="session"` |
| 72 | `test_nonpositive_ttl_rejected` | `mint_join` → `mint_session`, `kind=` |
| 76 | `test_bool_ttl_and_issued_rejected` | wire `"k": "join"` → `"session"`, `kind=` |
| 86 | `test_verify_returns_full_name_keys_only` | `mint_join` → `mint_session`; expected key set `jti` → `sid`, `JOIN_TTL_S` → `SESSION_TTL_S`; rename to `test_verify_returns_full_name_keys_only_for_a_session` |
| 148 | `test_corrupt_store_fails_closed` | `consume_jti("j1")` → `revoke_sid("s1")` |
| 153 | `test_missing_store_file_is_legitimate_empty` | `is_jti_consumed("j1")` → `is_sid_revoked("s1")` |
| 157 | `test_persistence_across_instances` | drop the two `jti` lines, keep the `sid` ones |

**One-line retarget elsewhere:** `tests/test_auth_gate.py:74` asserts `self.client.get("/j/garbage", headers=TUNNEL).status_code == 403`. Replace with `self.assertEqual(self.client.get("/t/garbage", headers=TUNNEL).status_code, 404)  # route runs, slug invalid`.

**Files:**
- Delete: `scripts/gm_invite.py`, `tests/test_join_route.py`, `tests/test_gm_invite.py`
- Modify: `display/tokens.py` (drop `mint_join`, `JOIN_TTL_S`, `consume_jti`, `is_jti_consumed`, the `jti` list, `_ID_FULL`), `display/gm-display-app.py` (drop `join`, `_JOIN_DENIED_HTML`), `tests/test_tokens.py`, `tests/test_auth_gate.py`

**Interfaces:**
- Consumes: `POST /claim` (Task 9) and `GET /t/<slug>` (Task 8) as the sole way a device acquires a cookie; `scripts/gm_table.py` (Task 13) as the sole GM CLI.
- Produces: `tokens.verify(token, *, secret, kind, now=None)` now accepts only `kind="session"` — passing anything else returns `None`, because no minter produces another kind. `RevocationStore`'s file shape becomes `{"sid": [...], "active": {...}}`; a pre-existing `"jti"` key on disk is ignored, not an error.

- [ ] **Step 1: Retarget `tests/test_tokens.py`**

Apply all 14 retargets and the 4 deletions from the tables above. Run:

```bash
python3 -m pytest tests/test_tokens.py -q
```

Expected: PASS, 34 passed. (The file started at 28 and gained 3 in Task 3, 6 in Task 6 and 1 in Task 8, so 38 − 4 deletions = 34.) Nothing in `tokens.py` has changed yet, so the retargeted `mint_session` tests pass against it as it stands.

- [ ] **Step 2: Retarget `tests/test_auth_gate.py:74` and delete the two dead test files**

```bash
git rm tests/test_join_route.py tests/test_gm_invite.py scripts/gm_invite.py
```

Then edit `tests/test_auth_gate.py:74` as specified above.

- [ ] **Step 3: Run to confirm the deletions and the retarget are clean**

Run: `python3 -m pytest tests -q`
Expected: PASS, 424 passed (440 − 4 in Step 1 − 12 for the two deleted files). Nothing is red yet: `/j` still exists and `/t/garbage` already returns 404. If `test_public_endpoints_open_when_tunnelled` returns 403 rather than 404, `table` is missing from `_PUBLIC_ENDPOINTS` — fix that, not the test.

- [ ] **Step 4: Delete the join route**

In `display/gm-display-app.py`:
- Delete `_JOIN_DENIED_HTML` (lines 58-62).
- Delete the entire `join` view (lines 1328-1349 as they stand after Task 9's cookie-helper edit), keeping `_set_session_cookie` above it.
- Remove `"join"` from `_PUBLIC_ENDPOINTS` so it reads `{"table", "claim", "ping", "health", "static"}`.

Verify nothing else references either:

```bash
grep -rn "_JOIN_DENIED_HTML\|/j/\|mint_join\|consume_jti\|is_jti_consumed\|JOIN_TTL_S" display scripts tests
```

Expected: no matches.

- [ ] **Step 5: Delete the join machinery from `display/tokens.py`**

- Delete `JOIN_TTL_S` (line 25).
- Delete `mint_join` (lines 96-98 as they stand after Task 6).
- Delete `_ID_FULL` and replace its one use in `verify`'s return dict with the literal `"sid"`; add `if kind != "session": return None` immediately after the existing `wire.get("k") != kind` check, so an unknown kind cannot reach a `KeyError`.
- Delete `consume_jti` and `is_jti_consumed`.
- In `_load`, drop `"jti": list(data.get("jti", []))` from the returned dict. A pre-existing `"jti"` key on disk is simply not carried forward on the next save.
- Update the module docstring (lines 1-14): one token kind, not two; `session` only; drop the "single-use invite link" line and the `consume_jti` mention in `RevocationStore`'s docstring at `:158`.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest tests -q`
Expected: PASS, 424 passed (440 − 16).

- [ ] **Step 7: Update the docs that name the old model**

```bash
grep -rn "gm_invite\|/j/<token>\|invite link" README.md docs/ CLAUDE.md BACKLOG.md systems/ 2>/dev/null
```

For each hit outside `docs/superpowers/` (which is a historical record and must not be rewritten), replace the invite-link description with the table URL and `scripts/gm_table.py`. Do not invent new documentation sections; only correct statements that are now false. `CHANGELOG.md` is deliberately absent from the grep even though its `:18` entry describes `gm_invite.py` — a changelog records what shipped when, and history is not rewritten.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat!: replace invite links with the table URL and character picker

/j/<token>, scripts/gm_invite.py, mint_join and the single-use jti machinery
are gone. The signature-verification suite in test_tokens.py is retargeted to
session tokens, not deleted."
```

---

### Task 15: The picker in a real browser

The source-string suite cannot see a row that renders but is not clickable, a claim that sets a cookie the next request does not honour, or a returning device that still gets the picker. These execute the page.

**Files:**
- Create: `tests/test_browser_picker.py`
- Modify: `tests/conftest.py` (add a `TableStore` to the fixture)

**Interfaces:**
- Consumes: the `gm_display` fixture in `tests/conftest.py:89-136` — `GmDisplay(mod, base_url, secret)` with `.session_cookie(character)` and `.open(context, character="")`; `TUNNEL_HEADERS = {"CF-Connecting-IP": "203.0.113.9"}` (`tests/conftest.py:37`); `mod._TABLE`, `mod._REVOCATION`, `mod._current_stats`, `mod._stats_lock`; `tokens.DM_SID`.
- Produces: no interface. Terminal task.

- [ ] **Step 1: Give the fixture a table store**

In `tests/conftest.py`, add `import table  # noqa: E402` beside the existing `import tokens` (line 17), and inside the `gm_display` fixture after `mod._REVOCATION = ...` (line 102):

```python
    mod._TABLE = table.TableStore(directory / ".table.json")
```

Also replace `mod._current_stats = {}` (line 118) with a real roster, since the picker has nothing to render without one — and add a note so the existing comment stays true:

```python
    # No sheet data: _playerData stays empty, which is the state the Sheet
    # button's readiness rule is about. A roster is still needed — the picker
    # renders from _current_stats["players"] — but a name with no sheet file
    # is exactly the shape those tests already assume.
    mod._current_stats = {"players": [{"name": "Kara"}, {"name": "Tom"},
                                      {"name": "Zed"}]}
```

Run `python3 -m pytest tests -q` before writing anything else. If `tests/test_browser_player_controls.py::test_unbound_display_offers_neither_control` or `test_sheet_button_stays_disabled_with_an_identity_but_no_sheet_data` turns red, the roster change gave `_playerData` content it did not have — revert to `{}` and instead set the roster inside `tests/test_browser_picker.py` only, via `gm_display.mod._current_stats`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_browser_picker.py`:

```python
"""The character picker, asserted in a real browser.

Marked `browser`, so `python3 -m pytest tests -q -m "not browser"` runs the
rest of the suite without them. Setup, same as
tests/test_browser_player_controls.py:

    pip install pytest-playwright
    playwright install chromium
"""
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402

pytest.importorskip(
    "playwright.sync_api",
    reason="browser harness: pip install pytest-playwright && playwright install chromium")
from playwright.sync_api import expect  # noqa: E402

pytestmark = pytest.mark.browser


@pytest.fixture
def clean_claims(gm_display):
    gm_display.mod._REVOCATION.path.write_text('{"sid": [], "active": {}}')
    yield
    gm_display.mod._REVOCATION.path.write_text('{"sid": [], "active": {}}')


def _table_url(gm_display):
    return f"{gm_display.base_url}/t/{gm_display.mod._TABLE.slug()}"


def test_the_picker_renders_every_roster_state(gm_display, context, clean_claims):
    gm_display.mod._REVOCATION.set_active("kara", "sid-live")
    gm_display.mod._REVOCATION.set_active("tom", tokens.DM_SID)
    page = context.new_page()
    page.goto(_table_url(gm_display), wait_until="load")

    expect(page.locator("li[data-state='taken']")).to_contain_text("on another device")
    expect(page.locator("li[data-state='dm']")).to_contain_text("run by the DM")
    # Free is tappable, taken is not — the state has to reach the DOM, not
    # just the styling.
    expect(page.locator("button.pick[data-character='Zed']")).to_be_visible()
    expect(page.locator("button.pick[data-character='Kara']")).to_have_count(0)
    # A taken character never names the person holding it.
    assert "sid-live" not in page.content()


def test_claiming_a_character_lands_on_play_bound_to_it(gm_display, context, clean_claims):
    context.set_extra_http_headers({"CF-Connecting-IP": "203.0.113.31"})
    page = context.new_page()
    page.goto(_table_url(gm_display), wait_until="load")
    page.click("button.pick[data-character='Zed']")
    page.wait_for_url(f"{gm_display.base_url}/")
    assert page.evaluate("() => GM_SESSION.character") == "Zed"
    assert page.evaluate("() => GM_SESSION.role") == "player"
    assert page.evaluate("() => GM_IDENTITY") == "Zed"


def test_a_returning_device_never_sees_the_picker(gm_display, context, clean_claims):
    context.set_extra_http_headers({"CF-Connecting-IP": "203.0.113.32"})
    context.add_cookies([gm_display.session_cookie("Kara")])
    page = context.new_page()
    page.goto(_table_url(gm_display), wait_until="load")
    page.wait_for_url(f"{gm_display.base_url}/")
    assert page.locator("#picker-roster").count() == 0


def test_display_only_binds_nothing_and_claims_nothing(gm_display, context, clean_claims):
    context.set_extra_http_headers({"CF-Connecting-IP": "203.0.113.33"})
    page = context.new_page()
    page.goto(_table_url(gm_display), wait_until="load")
    page.click("#pick-display")
    page.wait_for_url(f"{gm_display.base_url}/")
    assert page.evaluate("() => GM_SESSION.role") == "display"
    assert page.evaluate("() => GM_SESSION.character") == ""
    assert gm_display.mod._REVOCATION.active() == {}


def test_claiming_a_taken_character_refreshes_the_roster(gm_display, context, clean_claims):
    context.set_extra_http_headers({"CF-Connecting-IP": "203.0.113.34"})
    page = context.new_page()
    page.goto(_table_url(gm_display), wait_until="load")
    # Someone else claims Zed while this picker is open.
    gm_display.mod._REVOCATION.set_active("zed", "sid-elsewhere")
    page.click("button.pick[data-character='Zed']")
    # 409 -> reload -> Zed is now a taken row, not a button.
    expect(page.locator("li[data-state='taken']")).to_contain_text("Zed")
    expect(page.locator("button.pick[data-character='Zed']")).to_have_count(0)


def test_an_unknown_slug_is_a_404_page(gm_display, context):
    page = context.new_page()
    response = page.goto(f"{gm_display.base_url}/t/never-was-a-slug",
                         wait_until="load")
    assert response.status == 404
    assert "never-was-a-slug" not in page.content()
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python3 -m pytest tests/test_browser_picker.py -q`
Expected: FAIL before Step 1's fixture edit is in place (`AttributeError: _TABLE`). With Step 1 applied they should go green immediately — Tasks 8-11 already built everything they exercise. **If any of them is red, that is a real defect in the picker, not a test to soften.** In particular, a red `test_claiming_a_character_lands_on_play_bound_to_it` means `/claim`'s cookie is not being honoured on the following `GET /`; check `_set_session_cookie`'s `secure` flag against the fixture's `http://127.0.0.1:<port>` base URL.

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m pytest tests -q`
Expected: PASS, 430 passed.

Then confirm the non-browser path is independently green:

Run: `python3 -m pytest tests -q -m "not browser"`
Expected: PASS, 413 passed (17 `browser`-marked tests: 11 in `tests/test_browser_player_controls.py`, 6 here).

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_browser_picker.py
git commit -m "test(picker): drive the roster, claiming and the 409 bounce in a browser"
```

---

## Spec corrections

Written after checking every claim in `docs/superpowers/specs/2026-07-26-character-picker-design.md` against the tree at commit `734c9df`. The tasks above are written against reality; these are the divergences.

1. **`test_full_display_controls.py` (73) does not "survive untouched".** `tests/test_full_display_controls.py:91-93` pins the `?char=` fallback verbatim as source text, so Task 1 turns it red on its first edit. Task 12 additionally deletes three of its tests (`ModePredicate`), retargets `CALL_SITE_ANCHOR` (`:201`, which windows several `DiceRequestGating` tests), and retargets the outside-click closer count (`:1002`). Task 11 replaces the five `BoundCharacterInjection` tests. Net: **73 → 76**, with 9 methods rewritten.

2. **`test_auth_gate.py` is 16 tests, not 15, and it does not survive untouched either.** Line 74 asserts `GET /j/garbage → 403`, which dies with the join route. One-line retarget in Task 14.

3. **"Six tests in `test_tokens.py`, retargeted one word each" undercounts by more than half.** Eleven tests mint with `mint_join` *or* pass `kind="join"` without minting (`test_garbage_rejected`, `test_non_ascii_sig_does_not_raise`, `test_non_hex_sig_rejected`, `test_oversized_token_rejected`, `test_bool_ttl_and_issued_rejected` are the five the spec missed). Three more use `consume_jti` / `is_jti_consumed` incidentally and retarget to `sid` (`test_corrupt_store_fails_closed`, `test_missing_store_file_is_legitimate_empty`, `test_persistence_across_instances`). **14 retargets, not 6.** The spec's instruction that these must not be deleted is correct and is honoured — Task 14 lists each one and its exact change.

4. **"The four jti tests in `test_tokens.py`" is two.** Only `test_jti_single_use` and `test_jti_concurrent_consume_exactly_once` are about the jti mechanism; the other three that touch it are about corruption, missing files and persistence, and retarget rather than die. Total genuine deletions are **16, not "roughly 18"**: 6 (`test_join_route.py`) + 6 (`test_gm_invite.py`) + 2 jti + `test_join_roundtrip` + `test_minted_join_token_is_short`.

5. **`test_browser_player_controls.py` (11) survives only vacuously.** `test_proto_pollution_via_char_param_does_not_enable_the_sheet` (`:70-84`) reaches `__proto__` through `?char=`, which Task 1 removes. Left alone it passes while testing nothing. Task 1 re-anchors it onto the roster path, which is the same defect through the route that is still reachable.

6. **`test_auth_gate.py` is 16, `test_remote_player_console.py` is 20, `test_browser_player_controls.py` is 11 — verified.** The last two do survive untouched.

7. **The roster table's "not tappable" for DM-run rows contradicts "a returning owner always wins, with no confirmation step" — resolved in favour of the invariant, owner-ruled.** The picker cannot tell an owner from a stranger (it has no identity to check), so a non-tappable DM row would make a GM CLI command the only way back, and the returning-owner property the ownership/control split exists to deliver would not exist. So: **a DM-held row renders greyed with `run by the DM` and is tappable**; `/claim` succeeds on it and DM control drops immediately; only a *live device* claim is non-tappable and returns 409. Two arguments close it. First, a tappable DM row grants no capability a `free` row does not already grant — any device holding the table URL can claim any unclaimed character, so making DM rows inert would defend one row class against a threat model that leaves every other row open. Second, `active[player_id] == DM_SID` is a **label, not a gate**: nothing in the request path reads it — only `_roster_states`, `/claim`'s broadcast transition, and `scripts/gm_table.py` do — so there is no enforcement to preserve by making the row inert. And the mis-tap that a tappable row does permit is covered: every successful claim broadcasts `{"claim": {...}}`, so the DM console hears about it the moment it happens.

8. **"Run by the DM this session" and "Permanent party NPC" are one state, not two.** The spec says so itself ("through the same mechanism. No separate concept") and then gives them different rows with different copy. `active[player_id] == DM_SID` is the only fact available, so the picker shows one label, `run by the DM`, for both.

9. **The provisional claim does not auto-resolve.** "When a sheet appears bearing a name, the provisional claim resolves to it" has no reliable signal to fire on: `/stats` merges players by name and does not distinguish "new PC just created" from "roster reloaded", and any heuristic that guesses would mis-bind a device to someone else's character — the exact failure class this redesign exists to remove. **"Create a character with the DM" mints the same `display`-role cookie as "Display only";** `_DISPLAY_ENDPOINTS` includes `player_input`, so the device can talk to the DM in the narration loop that already exists, and its posts land as `"Party"` (the route's existing characterless default). When the sheet exists, the player reopens the table URL and taps their new name, which is now a free row. This is the "no new plumbing" reading of the spec and it costs one extra tap.

10. **The spec's role enum mixes two different things.** `"player" | "local" | "display"` is what `window.GM_SESSION.role` carries, and that is correct — but `local` is never in a token. `tokens.ROLES` is `("player", "display")`; `local` and `gm` are produced by `_resolve_identity` without a cookie, and a payload claiming either is rejected outright as a forgery attempt.

11. **The spec's entropy framing is not load-bearing, and the plan does not repeat it.** The spec justifies the slug on "44 bits, seventeen trillion combinations". The real defence is the rate limiter — `_rate_ok` at 20/60s per IP, charged only on failing requests after this plan, against a tunnel that is up a few hours a week — which puts guessing out of reach by orders of magnitude at 2048 words or far fewer. The plan ships the spec's flat 2048 list with replacement (owner-confirmed, including that slugs will usually *not* read grammatically — the spec's example `thoughtful-pandas-run-quietly` parses as adjective-noun-verb-adverb, which four independent draws from one flat list do not produce on purpose), but every shipped docstring and comment names the limiter, not the bit count, as the argument — so a future change to the list size is not mistaken for a security change.

12. **`display/gm-display-app.py:1372` sends `""` for a local browser — confirmed**, and the reason in the shipped comment (`:1359-1371`) is accurate. One consequence the spec does not draw out: a **loopback browser cannot hold a picker identity at all**. `index()` overrides any cookie for a local peer, so a GM who claims a character on their own machine still renders as `role: "local"`. The picker and `/claim` both work from loopback; only `/` ignores the result. That is pre-existing and deliberate, but it means a TV physically attached to the GM's machine cannot be a claimed display — it has to reach the server over the network.

13. **`/player-input/dice` is not quite "the only unthrottled write".** `/queue/consumed`, `/dice-request/<id>` (DELETE) and `/device/approve` are also unthrottled. It *is* the only unthrottled write that both persists to the text log and broadcasts, which is the property that matters and which the spec's sentence is otherwise right about.

14. **"`rotate` mints a new one and kills the old" is false without touching the secret.** Session cookies do not contain the slug, so swapping the slug alone leaves every minted cookie valid for 30 days — including a display-only session with no `active` entry and no recorded sid, which no release command can evict. The spec's posture section names `rotate` as the mitigation for a leaked URL; for that sentence to be true, Task 13 makes `rotate` regenerate `.invite_secret` as well. New URL kills new claims immediately; old cookies die at the app's next start (the process holds the old secret in memory until then).

## Things I could not settle

- **Whether `player_input` belongs in `_DISPLAY_ENDPOINTS`.** It is the minimum that makes "Create a character with the DM" work without new plumbing, and it means a display-only shared screen can post into the narration queue as "Party". Inside the table-URL trust boundary and rate-limited, that reads acceptable; it is a real widening of what a characterless device can do, and it is the single line most worth a skeptical read.
- **The `"dm"` sentinel's blast radius.** It is stored in a field whose other values are 16-char hex nonces and is filtered out of `set_active`'s revocation list (Task 8, with its own test). It is a label, not a gate — the readers are `_roster_states`, `/claim`'s broadcast transition, and `scripts/gm_table.py` (`list`, `release`), all of which special-case it; nothing in the request path reads it. I have not traced whether any *future* consumer of `RevocationStore.active()` would treat it as a sid.
- **The word list's content.** The plan specifies its shape and asserts it mechanically, but "fantasy-flavoured, no accidental slurs when two draws land adjacent, no homophone pairs" is a judgment the test cannot make. It wants a human read before it ships.
