# Remote Play — Player Screen Backlog

**Goal:** one screen per remote player holding all features — no tab-hopping. New
features live on the **right side** and must not overlap existing controls.

> **Status 2026-07:** items 1–3 shipped as the one-screen console (`body.input-only`
> roster + sheet slide-over + message dock + dice drawer). The "Current UI reality"
> below describes the pre-console tab layout and is retained as historical context.
> Item 3's "own messages only" ask was superseded by the approved spec, which keeps
> the whole-party queue visible (attribution stays server-enforced).

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
**Ask:** the player has an on-demand dice roller they can open anytime to roll freely.
Additionally, when a roll is called for, the GM configures it for the occasion (dice,
modifier, adv/dis, label, DC, target player) and pushes it; the targeted player gets that
same roller pre-filled and locked to the GM's spec, in a small modal/drawer that does not
cover the screen. Either way the player taps to roll and the result returns to the GM.

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
- The player can open the dice roller on their own at any time and roll freely.
- The GM configures and pushes a targeted roll via the existing CLI — no new GM-console UI.
- The targeted player receives that same roller pre-filled and locked as a badge/notification,
  not a forced tab switch.
- The roller opens as a compact modal/drawer that does not obscure the main view; the player
  taps to roll and the result returns to the GM.
- Dismissible without leaving the current pane.

## 3. Always-visible message box + whole-party staged messages
**Ask:** an always-visible text box the player types into, showing **every** player's staged
messages inline — an open table, no secret info.

**SME second opinion (corrected):** mostly exists already (`#staged-queue` + textarea,
co-located). The party-wide staged view is **intended**, not a leak — everyone sees what
everyone has staged. The only real gap: the box disappears when the player leaves the Move
tab. Pin the textarea + the whole-party staged queue so they stay visible across all panes.

**Acceptance criteria:**
- Message box is always visible on the player screen, across every pane.
- Shows all players' staged messages (the whole party), not filtered to one player.
- The server still binds who can submit as whom (Task 5 binds staged input to the
  authenticated character); transparency of viewing does not weaken submit-side identity.

## 4. LLM-driven campaign art library + display image
**Shipped:** implemented — `scripts/art.py` has all subcommands (search/save/find/list/
update/delete/show/hide), the `/art` route exists in `display/gm-display-app.py`, and
usage is documented in SKILL-commands.md and SKILL-scripts.md.

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

## 5. Table View — large-text shared-screen mode
**Issue:** the shared web display is too small to read comfortably from across a room.
Add a Table View mode for TV/projector use, keeping the existing atmospheric presentation
while making narration the primary visual element.

**Approved direction:** **B · Inline Scene Card.** Table View uses substantially larger
narration text in the central reading area. When the GM shows scene art, render it as a
bounded inline card between narration blocks with an image, caption, creator attribution,
and explicit source link. It scrolls with narration rather than becoming a modal, floating
overlay, or permanent sidebar.

**Out of scope:** a persistent art sidebar (it makes narration too narrow), a fullscreen
art modal (it hides the scene text), and a phone-only interpretation of the mode.

**Acceptance criteria:**
- A clearly named Table View toggle/mode is available on the shared desktop display and
  persists per browser.
- Default Table View narration is legible at room distance: larger type, generous line
  height, and a restrained line length without sacrificing contrast.
- The existing party rail and bottom Party Input stay visible and usable; upper-right
  controls remain reachable.
- Scene art appears inline in the central narration flow, never covering GM text or fixed
  controls, and uses a bounded `object-fit: contain` presentation.
- The mobile layout remains responsive: no permanent side rail; art stays in flow above
  narration and the persistent composer.
- The mode respects existing text-size preferences and does not introduce page-level zoom
  or break sheet/dice drawers.

## 6. Fork documentation audit — compare against parent `open-tabletop-gm`
**Ask:** produce a complete, maintainable explanation of how this fork differs from its
parent repository, [`Bobby-Gray/open-tabletop-gm`](https://github.com/Bobby-Gray/open-tabletop-gm).
This is the upstream comparison baseline. Do not use `claude-dnd-skill` as the fork-diff
baseline; it is a related Claude-specific ancestor, not this repository's configured
parent remote.

**Scope:** audit every user-, contributor-, and GM-facing document in the repository.
Document differences that affect installation, configuration, commands, security,
campaign data, display/remote play, systems, model support, and GM operating behavior.
Create one canonical “Differences from parent upstream” index, then link to focused
documentation rather than duplicating entire guides.

**Must cover:**
- LLM-agnostic operation and any supported agent/model setup differences.
- Remote-play authentication, Cloudflare Tunnel guidance, player identity, and GM-secret
  behavior.
- Campaign art: DeviantArt-first DuckDuckGo Lite search, campaign-local `art.json`,
  attribution/source retention, GM-LLM CLI workflow, inline display behavior, and the
  explicit exclusion of GenAI, downloads, proxies, and rehosting.
- GM workflow/prompt rules, including player-safe narration before **every** tool call,
  granular player agency, player-owned PC rolls, spoiler boundaries, and durable-state
  recording.
- System-module, display, and data-path differences that affect porting or contribution.

**Acceptance criteria:**
- The documentation names `Bobby-Gray/open-tabletop-gm` as the parent comparison target
  and gives its remote/URL; terminology is consistent across README, CHANGELOG,
  CONTRIBUTING, SKILL files, docs, and command references.
- A contributor can identify every intentional fork divergence, its rationale, affected
  files/workflow, and whether it is suitable to propose upstream.
- User documentation describes only implemented behavior; commands and security claims
  are verified against code and tests.
- A repeatable documentation-audit checklist or script detects stale parent references,
  Claude-only assumptions, missing command documentation, and undocumented new top-level
  scripts/features.
- The task updates release notes and versioning guidance so downstream users can assess
  upgrade and compatibility impact.

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
