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
- **Full envelope migration** — rewriting every existing SSE emitter + console
  JS onto the `{v, type, identity, payload}` envelope behind a compatibility
  shim. That is its own slice (Spec 2, event spine). Slice 0 fixes the envelope
  *schema* and tags player input + addressed feedback only.
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

### 2. Identity — two-token model (join link → session cookie)

The join link and the durable credential are **separate tokens**, because the
join URL lands in Cloudflare logs and browser history despite the redirect.

- New CLI: `scripts/gm_invite.py`. Given the active campaign's party, it mints
  one **join token** per player and prints one URL each:
  `https://game.<domain>/j/<join_token>`.
- **Join token** — HMAC-signed payload `{player_id, character, campaign, jti,
  issued_at}`, **single-use** and short TTL (default 72h). Consumed on first
  visit: `jti` is recorded so the link cannot be replayed.
- **Session token** — a *different* HMAC-signed token minted at `/j` after the
  join token verifies, carrying `{player_id, character, campaign, sid,
  issued_at}` with its own longer TTL (default 30 days). This is what the cookie
  holds; the join token is never stored client-side.
- Both signed with a per-host secret in `display/.invite_secret` (mode 0600,
  generated on first use via `secrets.token_hex`). `hmac` + constant-time
  compare — no new dependency. TTL is checked on **every** verify (`issued_at`
  vs now); expired tokens 403.
- Revocation list `display/.revoked.json` holds revoked `sid`s and consumed
  `jti`s. `gm_invite.py --revoke <player>` revokes their active session; reissue
  revokes the prior one. `--list` shows active players.
- `/j/<join_token>`: verify signature + TTL + not-yet-consumed → record `jti`
  consumed → mint session token → set **`HttpOnly; Secure; SameSite=Lax`**
  cookie → redirect to `/`. No token ever appears in page HTML.

### 3. Identity middleware — fail-closed, authoritative

Two audit-critical rules govern this section:

- **Fail-closed and authoritative.** A single `before_request` hook is the
  *only* authority on access for every state-changing route. The legacy
  `_token_ok()` (which returns `True` whenever the server runs without `--lan`,
  gm-display-app.py:385-388 — i.e. always, in tunnel mode) is **removed from
  the auth path**; write routes must not be reachable through any code path that
  fails open. Default posture: no valid identity → 403, no rate-limit
  fallthrough.
- **Never infer GM trust from `remote_addr` behind the tunnel.** cloudflared
  connects to `localhost:5001`, so `request.remote_addr` is `127.0.0.1` for
  *every* remote request — localhost-trust would hand any internet caller full
  GM access. Detection: a request carrying `CF-Connecting-IP` /
  `X-Forwarded-For` is tunnelled and therefore **untrusted**, regardless of
  `remote_addr`. The GM gets a **separate loopback-only credential** (a
  `.gm_secret` bearer token the local display/`send.py` sends), never IP
  inference. A tunnelled request presenting no player cookie is a player-auth
  failure → 403.

Identity resolution stashes `g.identity = {player_id, character} | None` (or a
`gm` marker for the authenticated local GM).

- **Attribution rule:** input endpoints derive `character` from `g.identity`,
  **not** from request body / query param. The self-declared `?character=` on
  `/stream` (gm-display-app.py:2463) and the body `character` fields on the
  input routes are ignored for authenticated players; only the authenticated GM
  may act on behalf of a named character.

### 3b. Message envelope — schema now, migration deferred

The canonical envelope is **defined here** so later renderers don't retrofit
routing, but the full migration of every existing SSE emitter is **out of scope
for this slice** (it touches all emitters + console JS — see Scope note). Slice 0
only tags player *input* and addressed feedback with identity.

```json
{ "v": 1, "type": "<event>", "identity": {"player_id": "...", "character": "Kara"},
  "payload": { ... } }
```

The event-spine slice (Spec 2) migrates existing untyped events onto this
envelope behind a compatibility shim.

### 4. Addressed delivery (de-risks the SME's SSE concern)

- The app already keeps a per-client SSE queue and a `queue→character` map
  (`_client_chars`, `_clients`). Add `_broadcast_to(character, payload)` that
  pushes only to matching client queues, alongside the existing fan-out
  `_broadcast`. This confirms server→**player** routing needs no transport
  rewrite — SSE-per-player-channel + POST-back is already the shape.
- `_broadcast_to` must **normalize the character identically** to registration
  (lowercased, `[:48]`) and push to **all** matching queues — a player may have
  more than one connected device.
- **SSE survives the tunnel + worker model — prove it first.** The pre-build
  prototype is a *live tunnel* test, not just in-app: it must confirm (a)
  Cloudflare does not buffer/compress the `text/event-stream` so events arrive
  in real time, and (b) Flask serves long-lived SSE concurrently — `app.run`
  needs `threaded=True` (or gunicorn with an async worker) or SSE connections
  block every other request. If either fails, transport is reconsidered before
  any further code.

### 5. Audit fixes folded in

- **CORS:** replace blanket `CORS(app)` with an allow-list = the tunnel origin
  (+ `localhost` for local dev). State-changing routes require a same-origin /
  identity check even on localhost.
- **`/player-input`:** route through `_sanitize_input` + `_char_ok` (parity
  with the stronger `/player-input/stage` path).
- **Token-in-HTML:** removed; identity is cookie-based (section 2).
- **`_token_ok()` fail-open:** removed from the auth path; `before_request` is
  the sole, fail-closed authority (section 3).
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
| token lib | sign/verify join + session tokens, TTL, revocation, `jti`/`sid` | `hmac`, `secrets` |
| `/j/<join_token>` route | verify + consume join token, mint session cookie, redirect | token lib |
| `before_request` identity | authoritative fail-closed resolve of `g.identity`; tunnel-aware GM trust | token lib, `.gm_secret` |
| GM loopback credential | `.gm_secret` bearer for local GM/`send.py`; never IP-inferred | `secrets` |
| `_broadcast_to` | addressed server→player SSE delivery, normalized, all devices | `_client_chars` |
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
- **Fail-closed:** a tunnelled request (carries `CF-Connecting-IP`, no cookie)
  cannot reach any write route or the GM path — 403. Explicitly assert the
  removed `_token_ok()` fail-open path is unreachable.
- **GM loopback:** local GM with `.gm_secret` gets GM access; the same request
  shape arriving with a tunnel header does not.
- **Rejection:** unauthenticated and tampered-token requests to every write
  route return 403.
- **Join token:** single-use (second visit to a consumed link 403s) and
  TTL-expired join/session tokens 403.
- **Addressed delivery:** `_broadcast_to` reaches only the matching client
  queue(s), across multiple devices for one character (the pre-build prototype,
  promoted to a kept test).
- **Live SSE over tunnel:** manual check that events stream in real time
  end-to-end through cloudflared (buffering/threading gate).
- **Revocation:** a revoked session and a consumed join token both 403.
- **Regression:** existing localhost GM-display flows (chunk, stats, stream
  replay) unchanged.

## Open risks

- Cloudflare account / named-tunnel setup is a one-time manual step; documented,
  not automated.
- Cookie-based identity assumes players don't share a browser profile; adequate
  for a private group, noted in docs.
