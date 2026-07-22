# Remote Player One-Screen Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the remote phone Move/Roll/Sheet tabs with one persistent player screen: roster + sheet slide-over, always-visible party message dock, and a non-hijacking dice drawer for free and GM-requested rolls.

**Architecture:** The GM stays an LLM using the existing `scripts/dice_player.py` and `display/send.py --dice-request` CLI paths. Only `body.input-only` changes: it becomes a persistent base screen plus a sheet slide-over and dice bottom drawer. The existing Flask dice, character-sheet, staged-input, and SSE protocols remain authoritative.

**Tech Stack:** Python 3.12, Flask/SSE, unittest/pytest, vanilla HTML/CSS/JavaScript.

**Spec:** `docs/superpowers/specs/2026-07-21-remote-player-console-design.md`.

---

## Execution Status — 2026-07-22

- **Task 1 — complete and approved.** Contract coverage and the server-side party-sheet access correction landed in `6b0d118`, `8374dd1`, and `d881514`.
- **Task 2 — complete and approved.** The persistent phone base (roster placeholder, message dock, and intentionally disabled pre-drawer FAB) landed in `f254124`, `1e53e7c`, and `25674c8`.
- **Task 3 — implementation complete; review follow-up paused.** The roster sheet overlay landed in `84a74d6`; its lifecycle/accessibility hardening landed in `b7168ff` (stale-response guard, focus trap, scroll/focus restoration). The focused suite passed 8 tests and the full suite passed 207 tests. Re-run Task 3 spec and code-quality reviews before treating this task as approved.
- **Tasks 4–5 — pending.** No dice-drawer behavior or final browser/documentation work has started.

Work is intentionally paused here at the user’s request. This status records implementation progress only; public documentation must wait until the affected behavior has completed review and browser proof.

---

## Completion Rubric

| Requirement | Evidence |
|---|---|
| No GM browser controls | Existing CLI request paths unchanged; no new GM-console markup |
| No request hijack | `_applyDiceRequest` has no `_setActiveTab('roll')`; it raises a badge only |
| One roller | FAB opens editable `#dice-pad`; badge opens same prefilled/locked drawer |
| Persistent context | Textarea and whole-party `#staged-queue` survive sheet/drawer open-close |
| Full sheets | Any roster member opens markdown sheet slide-over |
| Identity | Bound player cannot stage as another character; whole party remains visible |
| Responsive | 375px/430px single column; slide-over/drawer have close, Escape, touch targets |
| Regression | `python3 -m pytest tests -q` passes |

### Task 1: Lock Down Existing Server and Client Contracts

**Files:**
- Create: `tests/test_remote_player_console.py`
- Modify: `tests/test_attribution.py`
- Modify: `display/gm-display-app.py` only if a test demonstrates a server gap

- [ ] **Step 1: Write failing contract tests.**

```python
def test_bound_remote_player_can_fetch_any_valid_party_sheet(self):
    self.client.set_cookie("gm_session", self.kara_session)
    response = self.client.get("/character/Tom", headers=TUNNEL)
    self.assertEqual(response.status_code, 200)
    self.assertIn("Tom", response.get_data(as_text=True))

def test_bound_stage_ignores_spoofed_character(self):
    self.client.set_cookie("gm_session", self.kara_session)
    self.client.post("/player-input/stage", headers=TUNNEL,
                     json={"character": "Tom", "text": "I move"})
    self.assertIn("Kara", self.mod._staged)
    self.assertNotIn("Tom", self.mod._staged)

```

- [ ] **Step 2: Verify red.**

Run: `python3 -m pytest tests/test_remote_player_console.py tests/test_attribution.py -q`

Expected: FAIL because the server-contract test module/functions do not exist.

- [ ] **Step 3: Apply only necessary server correction.**

If `/character/<name>` rejects a valid party sheet for a bound player, permit any validated party member while preserving campaign path resolution and rejecting arbitrary names. Keep `stage_input` identity binding unchanged.

- [ ] **Step 4: Verify server contracts.**

Run: `python3 -m pytest tests/test_remote_player_console.py tests/test_attribution.py -q`

Expected: PASS. Task 4 introduces the dice-tab test immediately before changing dice
behavior, keeping this server-contract task fully green.

- [ ] **Step 5: Commit.**

```bash
git add tests/test_remote_player_console.py tests/test_attribution.py display/gm-display-app.py
git commit -m "test: define remote player console contracts"
```

### Task 2: Build the Persistent Phone Base Screen

**Files:**
- Modify: `display/templates/index.html:1840-2065,3000-3220`
- Modify: `tests/test_remote_player_console.py`

- [ ] **Step 1: Write failing layout tests.**

```python
def test_phone_has_base_roster_message_dock_and_dice_fab(self):
    html = TEMPLATE.read_text()
    for ident in ('player-console', 'player-roster', 'message-dock', 'dice-fab'):
        self.assertIn(f'id="{ident}"', html)
    self.assertNotIn('id="dp-tabs"', html)

def test_message_dock_owns_existing_input_and_party_queue(self):
    html = TEMPLATE.read_text()
    dock = html[html.index('id="message-dock"'):html.index('id="dice-fab"')]
    self.assertIn('id="player-input-text"', dock)
    self.assertIn('id="staged-queue"', dock)
```

- [ ] **Step 2: Verify red.**

Run: `python3 -m pytest tests/test_remote_player_console.py -q -k 'base or dock'`

Expected: FAIL because the three-tab markup remains.

- [ ] **Step 3: Implement the base only for `body.input-only`.**

```html
<section id="player-console" aria-label="Player console">
  <div id="player-roster" role="list" aria-label="Party roster"></div>
  <section id="message-dock" aria-label="Party actions">…existing textarea, Stage, staged queue…</section>
  <button id="dice-fab" type="button" aria-controls="dice-drawer">Roll dice</button>
</section>
```

Remove `#dp-tabs` and the `data-active-tab` visibility rules. Scope new flex-column CSS to `body.input-only`; hide `#char-tabs` only there, leaving the GM console unchanged.

- [ ] **Step 4: Verify green and commit.**

Run: `python3 -m pytest tests/test_remote_player_console.py -q -k 'base or dock'`

```bash
git add display/templates/index.html tests/test_remote_player_console.py
git commit -m "feat: add persistent remote player base screen"
```

### Task 3: Roster and Character-Sheet Slide-Over

**Files:**
- Modify: `display/templates/index.html`
- Modify: `tests/test_remote_player_console.py`

- [ ] **Step 1: Write failing safe-renderer tests.**

```python
def test_roster_uses_safe_buttons_and_existing_sheet_loader(self):
    html = TEMPLATE.read_text()
    self.assertIn("function renderPlayerRoster(players)", html)
    self.assertIn("button.textContent = player.name", html)
    self.assertIn("openCharacterSheet(player.name)", html)
    self.assertIn('_loadCharacterSheet(name)', html)

def test_sheet_overlay_has_close_and_focus_restore(self):
    html = TEMPLATE.read_text()
    self.assertIn('id="player-sheet-overlay"', html)
    self.assertIn('id="player-sheet-close"', html)
    self.assertIn("closePlayerSheet", html)
```

- [ ] **Step 2: Verify red.**

Run: `python3 -m pytest tests/test_remote_player_console.py -q -k 'roster or sheet'`

Expected: FAIL because no roster renderer or overlay exists.

- [ ] **Step 3: Implement roster and overlay.**

Render existing `stats.players` as `createElement('button')` roster chips. Reuse `_loadCharacterSheet` and `_renderMarkdown` with a requested roster name; do not create a second markdown renderer. Add a full-width phone slide-over, explicit close, backdrop click, Escape, and focus restoration to `#player-console`.

- [ ] **Step 4: Verify green and commit.**

Run: `python3 -m pytest tests/test_remote_player_console.py -q -k 'roster or sheet'`

```bash
git add display/templates/index.html tests/test_remote_player_console.py
git commit -m "feat: add remote player roster sheet overlay"
```

### Task 4: One Dice Drawer for Free and Prescribed Rolls

**Files:**
- Modify: `display/templates/index.html:2059-2385,6700-7180`
- Modify: `tests/test_remote_player_console.py`

- [ ] **Step 1: Write failing dice behavior tests.**

```python
def test_request_shows_badge_without_navigation_or_auto_open(self):
    body = function_source(TEMPLATE.read_text(), "_applyDiceRequest")
    self.assertIn("showDiceRequestBadge(req)", body)
    self.assertNotIn("_setActiveTab", body)
    self.assertNotIn("openDiceDrawer()", body)

def test_fab_and_badge_target_the_same_dice_drawer(self):
    html = TEMPLATE.read_text()
    self.assertIn('id="dice-drawer"', html)
    self.assertIn("function openDiceDrawer", html)
    self.assertIn("request_id: _activeRequestId || undefined", html)
    self.assertIn("function _setLocked", html)
```

- [ ] **Step 2: Verify red.**

Run: `python3 -m pytest tests/test_remote_player_console.py -q -k dice`

Expected: FAIL because the old handler switches tabs and no drawer/badge APIs exist.

- [ ] **Step 3: Implement drawer, FAB, and badge.**

Move existing `#dice-pad` into a bottom drawer with backdrop and explicit close. `#dice-fab` opens an editable free pad. `_applyDiceRequest` must retain current prefill, DC label, `_activeRequestId`, and `_setLocked` behavior, then call `showDiceRequestBadge(req)` and return; it must not open/navigate. The badge is dismissible without cancelling server state; tapping it opens the same drawer. Matching cancellation hides badge, clears ID, and unlocks. Preserve `/player-input/dice` payload and server randomness.

- [ ] **Step 4: Verify green and commit.**

Run: `python3 -m pytest tests/test_remote_player_console.py -q -k dice`

```bash
git add display/templates/index.html tests/test_remote_player_console.py
git commit -m "feat: add non-hijacking remote dice drawer"
```

### Task 5: Responsive Context Preservation and Browser Proof

**Files:**
- Modify: `display/templates/index.html`
- Modify: `tests/test_remote_player_console.py`
- Modify: `docs/REMOTE-PLAY.md`
- Modify: `display/README.md`

- [ ] **Step 1: Write failing responsive/a11y contracts.**

```python
def test_phone_overlays_preserve_message_dock_and_party_queue(self):
    html = TEMPLATE.read_text()
    self.assertIn("body.input-only #message-dock", html)
    self.assertIn("body.input-only #dice-drawer", html)
    self.assertIn("body.input-only #player-sheet-overlay", html)
    self.assertIn("max-width: 430px", html)
    self.assertIn("body.input-only #char-tabs { display: none", html)
```

- [ ] **Step 2: Verify red.**

Run: `python3 -m pytest tests/test_remote_player_console.py -q -k 'overlay or phone'`

Expected: FAIL until scoped overlay and responsive styles exist.

- [ ] **Step 3: Implement responsive and focus rules.**

At 375–430px keep one base column. Drawer/sheet may use fixed overlay shells, but `#message-dock` stays in the base flow with safe-area padding. Give FAB, badge, roster chips, and close controls 44px touch targets. Escape closes topmost overlay and returns focus to its invoking control. Do not add a phone side rail.

- [ ] **Step 4: Verify automated checks.**

Run: `python3 -m pytest tests/test_remote_player_console.py tests/test_attribution.py -q`

Expected: PASS.

- [ ] **Step 5: Perform browser proof.**

Run: `bash display/start-display.sh`; at `http://localhost:5001/?view=input&char=Kara`, test 375px and 430px widths:

1. Roster, message dock, full party queue, and FAB are visible without tabs.
2. Tom sheet opens/closes without losing a message draft.
3. FAB gives a free editable roll.
4. `python3 scripts/dice_player.py d20+5 --player Kara --label "Stealth" --dc 15` raises a badge without navigation; badge opens locked drawer; roll resolves request.
5. Remote spoofed staged character remains attributed to Kara.

- [ ] **Step 6: Document verified behavior, run full suite, and commit.**

Run:

```bash
python3 -m pytest tests -q
rg -n "dice_player.py|dice FAB|whole-party|slide-over" docs/REMOTE-PLAY.md display/README.md
git diff --check
```

Document that the LLM GM uses existing CLI tools, the phone has no tabs, and the player gets free-roll FAB plus request badge/drawer. Then commit:

```bash
git add display/templates/index.html tests/test_remote_player_console.py tests/test_attribution.py docs/REMOTE-PLAY.md display/README.md
git commit -m "feat: complete one-screen remote player console"
```

## Plan Self-Review

- Tasks 2–5 map directly to spec Features 1–3 and the responsive rules.
- Each code task starts red, verifies the failure, implements minimally, verifies green, and commits.
- Existing CLI request configuration, server roll endpoint, whole-party visibility, and desktop display are explicitly preserved.
- The plan intentionally does not unify the GM and player sheet renderers; it reuses the complete player markdown renderer as specified.
