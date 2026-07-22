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
**Ask:** when a roll is called for, the GM configures it for the occasion (dice, modifier,
adv/dis, label, DC, target player) and pushes it; the targeted player gets a pre-filled,
locked dice roller in a small modal/drawer that does not cover the screen, taps to roll,
and the result returns to the GM.

**SME second opinion (corrected):** there is **no GM-console UI to build** — the GM here is
the LLM agent, and its interface is the CLI. Configuring + pushing a targeted roll already
exists: `scripts/dice_player.py <spec> --player <name> --label ... --dc ...` (or
`display/send.py --dice-request`) POSTs `/dice-request`, which stores the request and
broadcasts `dice_pending` over SSE. The earlier "popover off each party card" framing
assumed a human GM clicking a browser console; that does not apply.

The **only new work is player-side.** The pre-fill/lock is already built
(`_applyDiceRequest`) but it **force-switches the player's whole screen to the Roll tab** —
a hijack that contradicts "doesn't cover the screen." Replace the forced switch with a
dismissible badge/FAB that opens a compact, non-covering roller over whatever pane the
player is on.

**Acceptance criteria:**
- The GM configures and pushes a targeted roll via the existing CLI — no new GM-console UI.
- The targeted player receives the pre-filled, locked roller as a badge/notification, not a
  forced tab switch.
- Tapping the badge opens a compact modal/drawer that does not obscure the main view; the
  player taps to roll and the result returns to the GM.
- Dismissible without leaving the current pane.

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

## 4. LLM-driven campaign art library + display image
**Ask:** let the GM LLM find and show reference art in the web display, then save
recurring images for places, NPCs, and generic creature archetypes. This is a GM tool
workflow, not a human-operated search console and not a generative-image feature.

**Proposed KISS workflow:**
```
art search --query "Blackwater Keep" [--source deviantart|web]
  → GM selects a normalized result
  → art show --url <result-url>                 # one-off scene art
  → art save --candidate N --as blackwater-keep --kind place
  → art show --id blackwater-keep                # recurring art
```

Search uses lightweight `lite.duckduckgo.com` result scraping and defaults to
`--source deviantart`, adding a `site:deviantart.com` constraint to the query. The GM
can explicitly choose `--source web` for wider results. DeviantArt is a source
preference, not a separate scraper or UI. GenAI/image generation is explicitly out of
scope.

**Persistence:** save a campaign-owned `art.json` alongside the campaign's world,
state, NPC, and session files. Each record has a stable ID, title/aliases, kind
(`place`, `npc`, or `creature`), tags, selected image URL, thumbnail URL, canonical
source URL, and available creator/attribution text. Store links and metadata, rather
than automatically downloading or rehosting artwork. A future opt-in shared art library
is deferred; no image is silently promoted between campaigns.

**Display behavior:** `art show` pushes a single image event through SSE. The display
renders a non-obstructive image panel/overlay with accessible alt text and a
caption/source link; it survives browser reconnects and has a clear failure state for
blocked or broken third-party images. `art hide` removes the active image.

**Acceptance criteria:**
- The GM LLM has documented `art search`, `save`, `find`, `list`, `update`, `show`,
  `hide`, and `delete` commands; there is no operator search UI and no GenAI fallback.
- Default DeviantArt-restricted search and explicit `--source web` search return capped,
  normalized DuckDuckGo Lite candidate lists, including source URLs and available
  attribution.
- Saved `place`, `npc`, and `creature` records survive campaign reload and can be
  recalled by ID, name, or alias.
- All connected and reconnected display clients receive the same active image, caption,
  and source link without covering player inputs or breaking responsive phone layouts.
- The initial version does not automatically fetch, download, or rehost third-party
  art. If fetching/caching is later added, it must reject private/local URLs and enforce
  redirect, content-type, size, timeout, and rate limits.
- Tests cover DeviantArt query construction, result normalization, campaign persistence
  and recall, authenticated display pushes/SSE replay, and malicious URL rejection.

---

## Cross-cutting notes / flags (from the SME pass)
- **The GM is the LLM agent, not a human at a console.** Anything framed as a "GM-side UI"
  should be a CLI/tool the agent invokes (like `dice_player.py`), never a browser control.
  These three features are entirely about the **remote player's** screen.
- **Phone width ~375–430px:** the right rail needs a responsive breakpoint, not a straight
  column split. Below the breakpoint, fall back to stacking/drawers.
- **Right-side contention:** all three features want the same space — define a stacking
  priority (e.g. message box pinned; sheet and dice as overlays/drawers).
- **Remove the dice-request tab-hijack** rather than layering a new modal over it.
- **Reconcile the two sheet renderers** (`#sheet-content` vs `#cp-body`) before feature 1.
- **`#char-tabs` impersonation affordance:** the UI lets a bound phone pick any party member
  when staging. The server binds identity (Task 5), so this is not exploitable, but the UI
  is misleading — align the affordance with the enforced binding (ties to feature 3).
- **Art-library scope:** art belongs to the current campaign in v1. A global/shared library
  is deliberately deferred; that avoids cross-campaign ownership, duplicate, attribution,
  and deletion rules until there is a concrete need.

_Full SME notes captured in session scratchpad `ux-sme-review.md` at time of writing._
