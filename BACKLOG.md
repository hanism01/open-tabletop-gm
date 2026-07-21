# Remote Play — Player Screen Backlog

**Goal:** one screen per remote player holding all features — no tab-hopping. New
features live on the **right side** and must not overlap existing controls.

**Current UI reality** (UX/UI SME pass over `display/templates/index.html`): there is
**no CSS grid** — everything is `position:fixed` overlays. The phone view
(`body.input-only`) is a **vertical single-column stack** with a top 3-tab bar
(Move / Roll / Sheet), one section visible at a time. There is **no stats panel and no
structural right side on phone today** — a right rail must be built, and at phone widths
(~375–430px) it needs a **responsive breakpoint, not a literal column split**. The three
items below compete for the same new right-side space and need a stacking priority.

---

## 1. Tap a character → full character sheet
**Ask:** tapping a character in the stats panel opens the complete character sheet (the
full phone-interface version), not a summary.

**SME second opinion:** premise needs groundwork — there is no tap-a-character stats panel
on phone yet, and two competing "full sheet" renderers exist: rich HTML `#sheet-content`
(GM console) vs plain-markdown `#cp-body` (phone). Reconcile to one renderer first.
Placement: a mini roster strip in the right rail; tap opens a slide-over overlay reusing
the existing markdown fetch (not a new tab).

**Acceptance criteria:**
- Player can tap any party member and see that character's full sheet.
- A single sheet renderer is used across console and phone (no divergence).
- Opens as a non-navigating overlay/slide-over and closes back to the same screen.
- Lives on the right side; no overlap with existing controls.

## 2. Pushable, non-covering dice roller
**Ask:** a button opens the dice roller in a small modal/panel that does not cover the
screen; the GM configures a requested roll and pushes it to the applicable player.

**SME second opinion:** the player-side pre-fill/lock is already built (`_applyDiceRequest`)
but it **force-switches the player's tab to Roll** — screen-hijack, which contradicts
"doesn't cover the screen." Replace the forced switch with a right-rail badge/FAB that opens
a compact drawer. The GM side needs a small popover off each party card to configure and
target the roll (a separate build from the player-side fix).

**Acceptance criteria:**
- Dice roller opens in a compact drawer/panel that does not obscure the main view.
- GM can configure a roll (dice, modifier, reason) and push it to a specific player.
- The targeted player receives a pre-filled roll prompt as a badge/notification — not a
  forced tab switch.
- Lives on the right side; no overlap.

## 3. Always-visible player message box + own staged messages
**Ask:** an always-visible text box the player types into, showing all of that player's
staged messages inline.

**SME second opinion:** mostly exists already (`#staged-queue` + textarea, co-located) but
it disappears when the player leaves the Move tab and currently shows the **whole party's**
staged entries — a GM-console leak into the player view. Pin this player's **own filtered**
entries + textarea in the right rail across all panes.

**Acceptance criteria:**
- Message box is always visible on the player screen, across every pane.
- Shows only that player's staged messages, not the whole party's.
- Reflects the server-enforced identity binding (Task 5 already binds staged input to the
  authenticated character).
- Lives on the right side; no overlap.

---

## Cross-cutting notes / flags (from the SME pass)
- **Phone width ~375–430px:** the right rail needs a responsive breakpoint, not a straight
  column split. Below the breakpoint, fall back to stacking/drawers.
- **Right-side contention:** all three features want the same space — define a stacking
  priority (e.g. message box pinned; sheet and dice as overlays/drawers).
- **Remove the dice-request tab-hijack** rather than layering a new modal over it.
- **Reconcile the two sheet renderers** (`#sheet-content` vs `#cp-body`) before feature 1.
- **`#char-tabs` impersonation affordance:** the UI lets a bound phone pick any party member
  when staging. The server binds identity (Task 5), so this is not exploitable, but the UI
  is misleading — align the affordance with the enforced binding (ties to feature 3).

_Full SME notes captured in session scratchpad `ux-sme-review.md` at time of writing._
