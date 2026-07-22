# Remote Player Web Console (Player-Screen Features 1–3)

## Purpose

Give each remote player a single screen that holds all of their controls — no tab-hopping.
The player types and stages actions, sees the whole party's staged actions, rolls dice
(freely or on a GM-pushed request), and reads any character's full sheet, all without
leaving one persistent view. This covers only the **remote player's screen** in
`display/templates/index.html`'s `body.input-only` mode. The GM is the LLM agent whose
interface is the CLI; nothing here adds a GM-console browser UI.

## Scope

In scope: the phone / remote-player view (`?view=input`, `body.input-only`). Out of scope:
the GM/TV console layout (default body), the GM-side of dice requests (already exists as
`scripts/dice_player.py` / `display/send.py --dice-request` → `POST /dice-request`), and any
generative or server-side art/image work.

The current phone view is a three-tab stack (Move / Roll / Sheet), one section visible at a
time, built from `position:fixed` overlays with no grid. This spec replaces the tab
structure with one persistent base screen plus on-demand overlays.

## Layout — one screen, no tabs

The `#dp-tabs` tri-tab pattern is removed for the player view. The base screen, top to
bottom, is:

1. **Roster strip** — a compact horizontal row of party members (name + HP). Tapping a
   member opens that character's sheet as a slide-over overlay (Feature 1).
2. **Message dock** — the player's input textarea plus a Stage button, and below it the
   whole-party staged queue (Feature 3). This is the always-visible core of the screen.

Two controls sit as persistent affordances over the base:

- A **dice button/FAB** that opens the roller drawer (Feature 2), always available.
- When a GM roll request arrives, a **dismissible badge** appears; tapping it opens the
  same roller drawer pre-filled and locked to the GM's spec.

The roll pad and the character sheet are **overlays** (drawer / slide-over) over the base,
not tabs. Opening or closing an overlay never changes the base screen's content, so the
message dock and staged queue stay visible and intact throughout.

## Feature 1 — Tap a character → full sheet

A roster chip opens a **slide-over overlay** showing that character's complete sheet,
dismissible back to the base screen without navigation.

The overlay reuses the existing phone sheet pipeline: `_loadCharacterSheet` /
`_renderMarkdown` fetching markdown from `/character/<name>`, generalized to accept any
party member's name rather than only the phone's bound `?char=` character. The markdown
renderer (`#cp-body` path) is the canonical player-side sheet renderer for this work.

The GM console keeps its own richer HTML renderer (`#sheet-content`). Full unification of
the two renderers is explicitly deferred — both already render a complete sheet; this spec
does not touch the GM console. The player and GM sheets may therefore differ in styling,
not in completeness.

## Feature 2 — Dice roller drawer (player-opened and GM-pushed)

One compact roller lives in a **bottom drawer** that does not cover the base screen.

- **Player-initiated:** the dice button opens the drawer for a free roll — dice, modifier,
  advantage/disadvantage, label — using today's `#dice-pad` logic. The player may open,
  roll, and dismiss at any time.
- **GM-pushed:** a `dice_request` / `dice_pending` SSE event raises a dismissible badge for
  the targeted player. Tapping the badge opens the same drawer pre-filled and locked to the
  GM's spec via `_applyDiceRequest`.

The forced tab switch (`_setActiveTab('roll')`) is **removed**; a pushed request never
seizes the screen — it surfaces as the badge and waits for the player. Either path resolves
by the player tapping to roll; the result posts back to the GM through the existing
`/player-input/dice` flow, unchanged.

## Feature 3 — Always-visible message dock, whole-party staged queue

The message dock (textarea + Stage) and the party staged queue are pinned into the base
screen so they remain visible regardless of which overlay is open.

The staged queue shows **every** player's staged entry — an open table, no hidden
information. The current party-wide `#staged-queue` / `_stagedData` content is intended and
retained; the only change is that it no longer disappears when an overlay opens or when the
player was on a different tab.

The `#char-tabs` character picker (which lets a phone stage as any party member or
"Everybody") is **hidden for remote players**: a bound phone can only stage as its own
`?char=` identity. This aligns the affordance with the server's existing submit-side
binding (staged input is already bound to the authenticated character); it does not weaken
anything, since viewing the whole party's staged actions is the desired transparency. The
GM console retains the picker.

## Responsive behavior

Portrait phones (~375–430px) are the single-column base screen. Overlays render as
full-width slide-overs (sheet) and bottom drawers (roller), not side rails or columns —
there is no literal left/right split at phone width. The base screen and overlays share the
existing `body.input-only` viewport; overlays layer above it and are dismissible by an
explicit close control and by tapping outside the overlay.

## Verification

The features are mostly client-side JS in one template, so verification splits into
server-contract tests (automatable in the existing pytest/Flask suite) and client behavior
(browser-verified, as with the existing SSE gate).

**Server-contract tests (pytest):**

- `/character/<name>` returns the full sheet markdown for **any** party member, not only a
  requester's bound character — the data path Feature 1's slide-over depends on.
- A bound remote phone's staged submit is attributed to its authenticated `?char=` identity
  regardless of any character field in the request — it cannot stage as another character.
- The staged-queue broadcast (`_stagedData` snapshot over SSE) contains all players'
  entries, so every connected player receives the whole-party view.

**Browser-verified (manual, on a running display):**

- Removing `_setActiveTab('roll')`: a GM `dice_request` raises the badge and pre-fills the
  roller without switching the base screen; the player-initiated free roll still works.
- The message dock and staged queue stay present and correct across opening and closing the
  sheet and roller overlays.
- The `#char-tabs` picker is hidden in `body.input-only`; the roster strip, sheet
  slide-over, and roller drawer render within phone width without a horizontal split.
