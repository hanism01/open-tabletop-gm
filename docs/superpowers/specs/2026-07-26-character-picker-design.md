# Character picker — design

_2026-07-26_

## Why

A device decides which character it acts as. Today that decision arrives two ways
that the code cannot tell apart: a `gm_session` cookie minted from a `/j/<token>`
invite link, and a `?char=` parameter in the URL. Nothing records which one a given
binding came from, so nothing can decide whether clearing it is allowed.

The concrete failure: at the shared display, "Phone Mode → Kara" then "Full Display"
leaves a screen that looks normal but still acts as Kara — input posts as her, and
her dice requests are consumed there instead of reaching her phone. Two clicks in,
no click out.

The narrow cause is one expression (`display/templates/index.html:6366`):

```js
const GM_IDENTITY = (window.GM_BOUND_CHARACTER || '').trim()
                 || (_idParams.get('char') || _idParams.get('character') || '').trim();
```

`display/gm-display-app.py:1372` sends `""` for a local browser, so the GM console
always falls through to the URL parameter. A GM revoke (`scripts/gm_invite.py --revoke`)
kills the cookie's authority while the parameter keeps driving.

**That line is fixed separately and first** — see "Ships independently" below. This
spec is not that fix. This spec replaces the invite-link model with one that makes
the class of bug unreachable, and is justified on its own merits as a usability
change, not as a security patch.

## What changes

Invite links are replaced by a **character picker** served from a **table URL**.

### The table URL

One long, human-readable, unguessable path identifies the table:

```
/t/thoughtful-pandas-run-quietly
```

Four words drawn from a 2048-word list shipped as a plain data file — 44 bits, or
roughly seventeen trillion combinations, against a limiter that permits 20 requests
per minute per IP. Readable over voice chat, typeable on a phone, memorable enough
that a latecomer does not need it re-pasted. Vocabulary is fantasy-flavoured so the
URL reads like the game.

The slug lives for the campaign. `gm_table.py rotate` mints a new one and kills the
old. An unknown slug returns 404, indistinguishable from a typo.

This is the Jitsi posture: the secret is the address, and the address names the
**table**, never a character. Nothing in it binds identity, so there is nothing in it
to clear, share wrongly, or fail to drop.

Bare `/` returns to its current behaviour — 403 for an unauthenticated non-loopback
peer. The picker introduces no public endpoint.

### The picker

Opening the table URL:

1. **Invalid slug** → 404.
2. **Valid session cookie already present** → skip the picker entirely, straight to
   play. This is the common case after the first visit.
3. **Otherwise** → the roster, each character showing its state.

Roster rows:

| State | Row shows | Tappable |
|---|---|---|
| Unclaimed | the name | yes |
| Claimed by another device | "on another device" | no |
| Run by the DM this session | "run by the DM tonight" | no |
| Permanent party NPC | "run by the DM" | no |

Plus two entries that are not characters:

- **Create a character with the DM** — drops the device into the existing
  player-input / narration loop with a provisional claim. No new plumbing: character
  creation is a conversation the app already supports. When a sheet appears bearing a
  name, the provisional claim resolves to it.
- **Display only** — the shared screen's explicit choice. Its unbound state becomes a
  chosen state rather than an accident.

A taken character never names the person holding it. The app has only ever known
characters, not people, and this design does not change that.

### Claiming

```
POST /claim   { character }
```

Requires a valid table slug, an allow-listed `Origin`, and passes `_rate_ok`. On
success it does exactly what the second half of the `/j/<token>` route does today:

```
mint_session()  →  set_active(player_id, sid)  →  set_cookie()
```

`RevocationStore.set_active` already revokes any previous session for the same
character, so one-device-per-character is enforced by existing, tested code.

No credential is typed by anyone. Holding the table URL is the authorisation.

## Ownership and control

Two independent facts, which the current code conflates into one field.

**Ownership** — "Aldric belongs to a person." Durable across sessions, restarts, lost
phones, and a week away from the table. Changed only by the GM.

**Control** — "something is driving Aldric right now." A device holding a session
cookie, or the DM. Exactly one at a time, or nobody.

They come apart in the case that motivated the split: a player misses a week and gives
permission for the DM to run their character. The claim is suspended; ownership is
untouched. Next week the player reclaims and the DM's control drops the moment the
claim lands. **A returning owner always wins, with no confirmation step** — that is the
point of separating the two.

A character who is never claimed by a device is a permanent party NPC through the same
mechanism. No separate concept.

### Storage

One store, not two. `RevocationStore` (`display/tokens.py`) already keys `active` by
`player_id`, which is `character.lower()` everywhere in the codebase. The picker adds
no new file.

`RevocationStore` gains one method it currently lacks:

```python
clear_active(player_id)   # ~8 lines
```

"Release a claim" is `clear_active` + `revoke_sid`. This also fixes a present-day
defect: `gm_invite.py --revoke` revokes the sid but leaves the `active` entry, so
`list` reports that player active-but-revoked indefinitely.

## What the page receives

The URL stops being a control surface. Six meaningful forms today collapse to one.

The template's injected identity changes shape:

```js
// today — "" means both "you are the GM console" and "you are nobody"
window.GM_BOUND_CHARACTER = "Kara";

// after
window.GM_SESSION = {
  character: "Kara",   // "" when unclaimed
  role: "player",      // "player" | "local" | "display"
  claimed: true
};
```

`role` is the channel that has never existed. Its absence is why the page could not
distinguish the GM's console from an anonymous viewer, and therefore could not offer
either one the right controls.

**Phone versus full display becomes a layout preference**, stored in `localStorage`,
not an identity. The same person can switch freely: there is nothing to preserve
across the toggle and nothing to drop. The button that produced the original defect
stops having a decision to make.

`/stream?character=` keeps carrying a name as a routing key. That is already safe —
`_bound_character` discards the argument outright for an authenticated player — and
the client will pass `GM_SESSION.character` rather than reading the URL.

## The display role is a real role

A cookie carrying no character is a state this codebase has never had, and naïvely
minting one is unsafe. `tokens._mint` accepts `character=""` without validation, and
`_resolve_identity` would resolve it to `{"role": "player", "character": ""}` — the
same ambiguity this redesign exists to remove, reintroduced through the back door.
Worse, that identity receives the full `_PLAYER_ENDPOINTS` set, including
`help_request` (which spawns a subprocess) and `get_character_sheet` (which serves
every PC's sheet).

Therefore:

- `role` becomes a field in the token payload, and `verify()`'s return contract grows
  it.
- `_gate` gains a `_DISPLAY_ENDPOINTS` subset — read-only endpoints plus `stream`.

**This contradicts an earlier claim that `_gate` is untouched.** It is touched, and
the spec is explicit about it.

## Error handling and edge cases

| Situation | Behaviour |
|---|---|
| Unknown or rotated slug | 404, no distinction from a typo |
| Cookie valid, character since released | Picker, with a note explaining why |
| Cookie valid, sid revoked by a newer claim | Picker, with a note |
| Two devices claim the same character | `set_active` revokes the older; it lands on the picker at its next request |
| Character renamed in the roster | Claim orphans. The picker hides claims whose key is absent from the current roster |
| Server restart mid-session | Nothing lost — cookies survive, `active` is persisted |
| Claim attempt on a taken character | 409, roster refreshes |

## Ships independently, before this

Three fixes that stand on their own and should not wait for the picker:

1. **Delete the `?char=` fallback** at `index.html:6366`. This closes the defect the
   redesign was born from.
2. **`/player-input/dice` rejects an empty resolved character** and gains `_rate_ok`.
   It is currently the only unthrottled write that persists to the log and broadcasts,
   and it does not check the resolved name — a blank one would post
   `" rolls 1d20: [17]"` into the narration feed.
3. **`RevocationStore.clear_active`**, plus the `gm_invite.py --revoke` fix above.

## Testing

**Survives untouched.** Any test that mints with `mint_session` — `test_auth_gate.py`
(15), `test_remote_player_console.py` (20), `test_full_display_controls.py` (73),
`test_browser_player_controls.py` (11). These assert on identity resolution, the gate,
and `_bound_character`, all of which outlive the token mechanism.

**Retargeted, one word each.** Six tests in `test_tokens.py` that assert on `verify()`
via `mint_join` — tampering, wrong secret, wrong kind, TTL expiry, non-positive TTL,
full-name-key contract. `verify()` survives; only the minting helper changes. **These
must not be deleted** — they are the signature-verification suite.

**Genuinely dies.** `test_join_route.py` (6), `test_gm_invite.py` (6), the four jti
tests in `test_tokens.py`, `test_join_roundtrip`, `test_minted_join_token_is_short`.
Roughly 18 tests.

**New coverage.** Slug validation and rotation; claim of a free character; claim of a
taken character; release and the bounce that follows; the display role's endpoint set;
`clear_active`; the provisional-claim resolution when a created character's sheet
appears. Browser-level: the picker renders each roster state, and a returning device
with a valid cookie never sees it.

## Out of scope

- The character-creation *conversation* itself. The picker opens a door to a loop that
  already works; how the DM guides sheet authoring is not specified here.
- Retiring the `X-DND-Device` approval layer. It becomes fully dead once every device
  holds a cookie — tracked in `BACKLOG.md`.
- The remaining unguarded `_playerData` bracket lookups — also in `BACKLOG.md`.

## Posture

This changes the security posture deliberately, and the owner has accepted it:

- The table URL is a reusable shared secret rather than a per-character single-use
  link. Anyone holding it can claim any free character. Among a known group that is
  the intent; the URL, not the person, is the trust boundary.
- URLs leak the way URLs leak — screen shares, chat history, browser sync. `rotate` is
  the mitigation.
- Over the tunnel, holding the URL grants the narration replay, stats, art, and PC
  sheets. The tunnel is only up while a session is in play.
