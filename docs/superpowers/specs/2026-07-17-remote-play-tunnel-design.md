# Spec 1 — Remote Play: Tunnel + Per-Player Binding (Slice 0)

**Date:** 2026-07-17
**Fork:** github.com/hanism01/open-tabletop-gm
**Status:** Design — awaiting review

## Goal

Let a group play over the internet, with every input and every piece of
feedback correctly attributed to the player who sent it. This is the
foundation slice: it establishes the network boundary and the identity /
message envelope that all later console features (live tool-turn feedback,
click-to-roll, inline graphics) build on.

**Definition of done:** From two different devices on two different networks,
Kara and Tom each open their own join link, submit an action, and the GM sees
`[Kara]: ...` and `[Tom]: ...` correctly attributed — with no shared secret
in page HTML, no self-declared character param, and no open inbound port on
the host.

## Non-goals (this slice)

- Console rendering of new event types (Spec 2).
- Click-to-roll UI, inline graphics, asset search (later specs).
- Hardened multi-tenant hosting. This targets a private group behind a tunnel,
  not a public SaaS. "Distinguish players" here means correct **attribution**;
  the signed token doubles as the access gate that keeps strangers out.

## Threat model (why this slice is security-shaped)

The GM agent is a local `claude` process with tool and filesystem access on the
host. Player text enters its context. Over the internet, an unauthenticated
request to a write endpoint is an attempt to drive that agent. Therefore:
every state-changing request must carry a verifiable identity, and anything
unverified is rejected — not merely rate-limited.

This slice also closes the audit HIGH/MEDIUM findings that make the current LAN
mode unfit for internet exposure (token embedded in HTML, wide-open CORS,
weakly-sanitized `/player-input`, `--tls` cert-server directory exposure).

## Architecture

### 1. Transport boundary — Cloudflare Tunnel

- Flask stays bound to `localhost:5001` (unchanged default). No inbound port.
- `cloudflared` runs a named tunnel mapping a public hostname
  (`game.<domain>`) → `http://localhost:5001`. TLS terminates at the Cloudflare
  edge, so the local `--tls` path and its `:8080` cert-server (audit HIGH #1)
  are **not used** in tunnel mode and stay off.
- Deliverable: `display/tunnel/` with a `cloudflared` config template and a
  `start-tunnel.sh` that boots the tunnel alongside the display, plus a
  `docs/REMOTE-PLAY.md` setup guide (one-time `cloudflared login` + tunnel
  create, then a single command each session).

### 2. Identity — signed per-player join links

- New CLI: `scripts/gm_invite.py`. Given the active campaign's party, it mints
  one signed token per player and prints one join URL each:
  `https://game.<domain>/j/<token>`.
- Token = HMAC-signed, self-contained payload
  `{player_id, character, campaign, issued_at, version}`, signed with a
  per-host secret in `display/.invite_secret` (mode 0600, generated on first
  use via `secrets.token_hex`). Uses `hmac` + constant-time compare — no new
  dependency.
- Server-side revocation list `display/.revoked_invites.json` (token ids). A
  reissue for a player revokes their prior token. `gm_invite.py --revoke
  <player>` and `--list` round out the CLI.
- `/j/<token>` verifies the signature and revocation, sets a
  **`HttpOnly; Secure; SameSite=Lax`** cookie carrying the token, then
  redirects to `/`. Every subsequent request reads identity from the cookie.
  The token never appears in page HTML.

### 3. Identity middleware + message envelope

- A `before_request` hook resolves the caller's identity once per request from
  (a) the invite cookie, or (b) localhost with no cookie → the trusted GM
  display (full access, no character binding). Result is stashed on Flask `g`
  as `g.identity = {player_id, character} | None`.
- **Canonical envelope** for every client↔server message, defined here so no
  later slice retrofits it:

  ```json
  { "v": 1, "type": "<event>", "identity": {"player_id": "...", "character": "Kara"},
    "payload": { ... } }
  ```

  Server→client SSE events and client→server input both carry `identity`.
  Existing untyped events are migrated behind a compatibility shim so the
  current console keeps working during transition.
- **Attribution rule:** input endpoints derive `character` from `g.identity`,
  **not** from request body / query param. The self-declared `?character=` on
  `/stream` (line 2463) and the body `character` fields on the input routes are
  ignored for authenticated players and used only for the trusted localhost GM
  display.

### 4. Addressed delivery (de-risks the SME's SSE concern)

- The app already keeps a per-client SSE queue and a `queue→character` map
  (`_client_chars`, `_clients`). Add `_broadcast_to(character, payload)` that
  pushes only to matching client queues, alongside the existing fan-out
  `_broadcast`. This confirms server→**player** routing needs no transport
  rewrite — SSE-per-player-channel + POST-back is already the shape.
- A throwaway prototype test proves round-trip addressed delivery
  (player A connects, server addresses A, only A's queue receives it) **before**
  the rest of the slice is built. If it fails, transport is reconsidered before
  any further code.

### 5. Audit fixes folded in

- **CORS:** replace blanket `CORS(app)` with an allow-list = the tunnel origin
  (+ `localhost` for local dev). State-changing routes require a same-origin /
  identity check even on localhost.
- **`/player-input`:** route through `_sanitize_input` + `_char_ok` (parity
  with the stronger `/player-input/stage` path).
- **Token-in-HTML:** removed; identity is cookie-based (section 2).
- **`--tls`/`:8080`:** unused in tunnel mode; documented as LAN-only legacy.

## Data flow

```
gm_invite.py ──prints──▶ per-player links (one each)
Player opens /j/<token> ─▶ verify+revocation ─▶ set cookie ─▶ redirect /
Player POST /player-input (cookie) ─▶ before_request ─▶ g.identity
   ─▶ sanitize ─▶ queue tagged [character] ─▶ GM turn context
GM issues feedback for Kara ─▶ _broadcast_to("Kara", envelope) ─▶ only Kara's SSE
Unauthenticated request ─▶ before_request ─▶ 403 (no rate-limit fallthrough)
```

## Components (each independently testable)

| Unit | Responsibility | Depends on |
| --- | --- | --- |
| `scripts/gm_invite.py` | mint / revoke / list signed player tokens | invite secret, campaign party |
| invite token lib | sign, verify, revocation check | `hmac`, `secrets` |
| `/j/<token>` route | verify link, set cookie, redirect | invite token lib |
| `before_request` identity | resolve `g.identity` from cookie / localhost | invite token lib |
| `_broadcast_to` | addressed server→player SSE delivery | `_client_chars` |
| CORS + sanitize fixes | close audit findings | existing sanitizers |
| tunnel config + docs | expose localhost over the internet | cloudflared |

## Error handling

- Invalid / expired / revoked token → `/j` returns 403 with a plain "ask your
  GM for a new link" page. No stack traces, no token echo.
- Missing / malformed cookie on a write route → 403.
- Tunnel down → localhost play unaffected; docs cover restart.
- Invite secret missing → generated on first `gm_invite` run; never logged.

## Testing

- **Attribution:** simulate two cookie'd clients; assert each input is tagged
  with the correct character regardless of body/query params.
- **Rejection:** unauthenticated and tampered-token requests to every write
  route return 403.
- **Addressed delivery:** `_broadcast_to` reaches only the matching client
  queue (the pre-build prototype, promoted to a kept test).
- **Revocation:** a revoked token's link and cookie both 403.
- **Regression:** existing localhost GM-display flows (chunk, stats, stream
  replay) unchanged.

## Open risks

- Cloudflare account / named-tunnel setup is a one-time manual step; documented,
  not automated.
- Cookie-based identity assumes players don't share a browser profile; adequate
  for a private group, noted in docs.
