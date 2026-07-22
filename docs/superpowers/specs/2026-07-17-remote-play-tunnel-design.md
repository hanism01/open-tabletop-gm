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
  `jti`s. All reads/writes go through a module-level `threading.Lock` + atomic
  temp-file rename (the pattern already used for `_persist_tail`) so concurrent
  `/j` hits cannot double-consume a `jti`. Consume-and-check is one locked
  critical section. `gm_invite.py --revoke <player>` revokes their active
  session; reissue revokes the prior one. `--list` shows active players.
- `/j/<join_token>`: verify signature + TTL + not-yet-consumed → record `jti`
  consumed → mint session token → set **`HttpOnly; Secure; SameSite=Lax`**
  cookie → redirect to `/`. No token ever appears in page HTML.

### 3. Identity middleware — fail-closed, authoritative

Rules governing this section:

- **Fail-closed and authoritative over reads *and* writes.** A single
  `before_request` hook is the *only* access authority, and it covers **every
  identity-bearing route including `GET /stream`** — not just state-changing
  ones. `/stream` today (gm-display-app.py:2456-2535) replays the full text log,
  stats, staged inputs, and dice state to anyone who connects, and registers the
  client under an attacker-supplied `?character=` (line 2463) with no identity
  check — so a tunnelled stranger registering as `kara` would receive Kara's
  addressed feedback. Fix: `before_request` gates `/stream`; a cookieless
  tunnelled stream is rejected; the bound character comes from `g.identity`,
  never `request.args`. The legacy `_token_ok()` (returns `True` whenever the
  server runs without `--lan`, lines 385-388 — i.e. always, in tunnel mode) is
  **removed from the auth path**. Default: no valid identity → 403, no
  rate-limit fallthrough.
- **`.gm_secret` is the sole GM gate; header detection is advisory only.** The
  app **cannot** cryptographically distinguish a genuine cloudflared hop from a
  direct `localhost:5001` connection, so GM trust rests entirely on a
  loopback-only bearer secret `display/.gm_secret` (mode 0600) presented in a
  named header (section 5). `remote_addr == 127.0.0.1` grants **nothing** on its
  own. `CF-Connecting-IP` / `X-Forwarded-For` presence is used only as
  defense-in-depth to *downgrade* a request to untrusted — never to upgrade one.
  (Safe direction: a client cannot strip the `CF-Connecting-IP` Cloudflare
  injects at its edge.)
- **Kill the second localhost-trust path.** `_device_ok` auto-approves any
  request from `127.0.0.1`/`::1` (line 287) — i.e. every tunnelled request. This
  slice removes that localhost auto-approve (or deletes `_device_ok` as dead
  code); device state must never be inferred from `remote_addr`.

Identity resolution stashes `g.identity = {player_id, character} | None` (or a
`gm` marker for the authenticated local GM).

- **Attribution rule:** input *and stream* endpoints derive `character` from
  `g.identity`, **not** from request body / query param. The self-declared
  `?character=` on `/stream` and the body `character` fields on the input routes
  are ignored for authenticated players; only the authenticated GM may act on
  behalf of a named character.

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
- **SSE survives the tunnel — prove it first.** The pre-build prototype is a
  *live tunnel* test: confirm Cloudflare does not buffer/compress the
  `text/event-stream` so events arrive in real time. (Flask concurrency is
  already handled — `app.run(threaded=True)` at gm-display-app.py:2601 — so no
  worker change is needed; only the edge-buffering behaviour is unverified.) If
  it fails, transport is reconsidered before any further code.

### 5. Audit fixes folded in

- **GM auth header:** the GM credential is sent as a single named header
  `X-GM-Secret` carrying `.gm_secret`. `send.py` (currently `X-DND-Token`,
  send.py:118) and `check_input.py` (currently `X-Token`, check_input.py:91)
  are both updated to this header and the server verifies it with
  `hmac.compare_digest`. Reconciling the two inconsistent legacy headers is part
  of this slice.
- **CORS + CSRF:** replace blanket `CORS(app)` with an allow-list = the tunnel
  origin (+ `localhost` for dev). Because auth is now cookie-based, every write
  route additionally enforces an explicit **`Origin`/`Referer` allow-list
  check** (SameSite=Lax alone does not stop top-level form POSTs). No valid
  origin → 403.
- **Rate limiting:** key `_rate_ok` on `CF-Connecting-IP` (falling back to
  `remote_addr` only for local dev). Keyed on `remote_addr` it is always
  `127.0.0.1` behind the tunnel — one shared bucket lets one player DoS all and
  removes per-IP brute-force protection.
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
| CORS + CSRF + rate-limit fixes | origin allow-list on writes, `CF-Connecting-IP` rate key | existing sanitizers |
| `/stream` guard | gate read path, bind character from `g.identity` | `before_request` |
| device auto-approve removal | kill `_device_ok` localhost trust | — |
| GM header reconciliation | `X-GM-Secret` in `send.py` + `check_input.py` | `.gm_secret` |
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
- **Fail-closed (reads too):** a tunnelled request (carries `CF-Connecting-IP`,
  no cookie) cannot reach any write route, the GM path, **or `GET /stream`** —
  403. A cookie'd player cannot register the stream under a different
  character's name via `?character=`. Explicitly assert the removed
  `_token_ok()` fail-open path is unreachable.
- **No IP-inferred trust:** a tunnelled request with `remote_addr` 127.0.0.1
  gets neither GM access nor device auto-approval; `_device_ok` localhost
  auto-approve is gone.
- **Rate limit isolation:** two players behind the tunnel (distinct
  `CF-Connecting-IP`) do not share one bucket.
- **CSRF:** a write POST with a disallowed `Origin` is rejected even with a
  valid cookie.
- **jti race:** concurrent `/j` on the same join token consumes it exactly once
  (one 200, the rest 403).
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
