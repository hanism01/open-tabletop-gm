# Player controls on the full display

Date: 2026-07-25
Status: approved, not yet implemented

## Problem

A remote player with one laptop cannot read the narration and use their dice
roller at the same time. The dice pad and the markdown character sheet live
only in the phone view (`body.input-only`), which hides `#text-scroll`, the
sidebar, and every ambient layer. Reaching the dice roller therefore means
giving up the GM's text.

This is fine for in-person play with a phone in hand and a shared screen on the
wall. It is the wrong trade for remote play on a single machine, which is the
case this design serves.

## Scope

In: making the character sheet and the dice roller reachable from the full
display at `/`, for the player bound to that browser session.

Out: any change to the phone view's layout or behaviour. Any new authentication.
A second roll surface competing with the phone (see "Open edge" below).

## Approach

The controls appear as two buttons in the existing `#input-panel` and open the
existing `#sheet-modal` and `#dice-drawer` as overlays over the narration. No
new layout, no responsive breakpoint, no second copy of the player console.

The alternatives considered and rejected were a persistent right rail (costs
narration width and needs real layout work) and making `body.input-only`
two-pane at desktop widths (rewrites a large block of working CSS).

## Identity

The browser does not need to guess who the player is. `/j/<token>`
(`display/gm-display-app.py:1327`) ends in `redirect("/")`, so a player joining
by invite link lands on the **full display** holding a valid `gm_session`
cookie. `_gate` (`:525`) already populates `g.identity`, `index` is already in
`_PLAYER_ENDPOINTS`, and `_bound_character` (`:517`) already computes the
answer. Invite links are the actual distribution mechanism for this project, so
this path carries the weight.

The cookie is `httponly=True` (`:1346`), so JavaScript cannot read it.
Template injection is the channel.

### Server

`index()` (`gm-display-app.py:1349`) passes `bound_character=_bound_character("")`
into `render_template`. It returns `""` for the GM and for local console
browsers, and the character name for an authenticated player.

### Client

Resolve once at load, in order:

1. The server-injected value.
2. `?char=` / `?character=` from the URL.
3. Empty.

`localStorage['gm_player_name']` is **not** consulted on the full display. It is
written by a free-text field (`index.html:7320`) with no validation against the
roster and is shared across tabs on one origin, so a GM who opens phone mode
once would otherwise have their full display silently claim to be that
character from then on. It stays in place for the phone view, where it is the
legitimate no-URL fallback.

When identity resolves, `_selectedChar` (`index.html:6229`) seeds to it instead
of `'Everybody'`.

### Why not `_selectedChar` alone

The character tabs mean "speak as", not "I am". Using them as identity fails
three ways: the default `'Everybody'` is not a character, so `openSheet` hits
its `_playerData` guard (`:5093`) and dead-clicks on the very first state a user
sees; `/roll` (`gm-display-app.py:2197`) never applies `_char_ok`, so a roll
would write the literal line `Everybody rolls 1d20+3` into the narration; and on
the GM's machine, flipping tabs to voice different PCs would silently re-aim the
dice pad.

`_bound_character` already overwrites the client-supplied character on
`player_input` (`:2153`), `player_dice` (`:2197`), `roll_pref` (`:1930`), and
the `help_request` owner (`:1838`). Mirroring that same precedence in the client
keeps one rule in both layers.

## Controls

Two buttons in `#input-footer`, beside Stage.

- **Sheet** — opens `#sheet-modal` for the resolved identity, falling back to
  `_selectedChar` when no identity resolves.
- **Dice** — opens `#dice-drawer`.

When no identity resolves *and* `_selectedChar` is `'Everybody'`, Sheet is
disabled and Dice falls through to the drawer's existing `#dp-name` free-text
field. The GM's display is unchanged in every respect that matters to them.

## Splitting `_initDicePad`

`_initDicePad` (`index.html:7295–7705`) is not mode-agnostic. It installs the
roll UI and the dice-request machinery together: `_applyDiceRequest`,
`window._onDiceRequest` (`:7637`), `_setLocked`, and
`window._onDicePendingSnapshot` (`:7704`). Calling it wholesale on the full
display means a GM who requests a roll from a player locks and badges their own
screen.

Split it so the roll UI initialises independently of the request handlers. The
full display installs request handling only when identity resolves.

## Unified character sheet

There are two sheet renderers reading two different sources:

- `openSheet` (`index.html:5099`) renders the live SSE `stats` payload — HP, AC,
  class icon, ability scores, and whatever `p.sheet` carries. It reflects
  current combat state.
- `_loadCharacterSheet` (`:7158`) fetches `/character/<name>`
  (`gm-display-app.py:2389`) and renders the authored markdown file from disk —
  spells, inventory, features.

Neither alone is what a player means by "my character sheet". Unify: `openSheet`
keeps its live header, then fetches `/character/<name>` and renders the markdown
below it. A missing or 404 sheet degrades to the live header plus a quiet note;
it is not an error state. Sidebar player cards and the new Sheet button share
this one path.

`/character/<name>` deliberately does not rewrite the requested character, so a
bound player can still read another party member's sheet. That stays true.

## Supporting fixes

**SSE identity.** The full display connects to `/stream` with no `?character=`
(`index.html:6883`), so `_phone_present` (`gm-display-app.py:987`) stays false
for a player rolling from the full display, and the server keeps listing them in
`onscreen_targets` (`:2338`). Pass `?character=` on connect when identity
resolves.

**Input-mode predicate.** `index.html:7039` is
`_qp.get('view') === 'input' || _qp.has('char') || _qp.has('character')`, so
`?char=Mira&view=full` is forced back into the phone view. Let an explicit
`view=full` win, and have the "Full Display" button navigate to
`?view=full&char=<Name>` instead of stripping the query string. The binding then
lives in the URL: bookmarkable, per-tab, no cross-tab contamination.

## Testing

Follows the pattern in `tests/test_remote_player_console.py`: markup and source
assertions against `display/templates/index.html`, plus Flask route tests
against the app module.

Server:

- `index()` renders with `bound_character` set to the session's character for a
  player token, and to `""` for GM and local roles.
- The value is HTML-escaped into the template.

Client (source assertions):

- The identity resolver reads the injected constant before `?char=`, and never
  reads `gm_player_name` on the full-display path.
- `_selectedChar` seeds from resolved identity rather than `'Everybody'`.
- Sheet and Dice buttons exist in `#input-footer`.
- Sheet is disabled when identity is empty and `_selectedChar` is `'Everybody'`.
- The dice-request handlers are installed separately from the roll UI.
- `openSheet` fetches `/character/<name>` and renders below the live header.
- The `/stream` URL carries `?character=` when identity resolves.
- `view=full` overrides `char=` in the input-mode predicate.

## Open edge

If the full display becomes a legitimate roll surface, a future on-screen roller
plus a connected phone could both answer one dice request. Nothing consumes
`onscreen_targets` client-side today, so this is inert. The SSE `?character=`
fix above is what makes the server able to tell the difference when it matters.

One accepted inconsistency: a GM who opens a join link in their console browser
gets a `/` that claims to be that character, because `index` is in
`_PLAYER_ENDPOINTS` and so the player→local downgrade at `:535` does not apply.
This already happens to their POSTs, so the display now merely agrees with the
server.
