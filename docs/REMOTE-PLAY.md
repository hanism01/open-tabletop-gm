# Remote Play

How to run a session where players connect over the internet instead of a shared LAN,
using a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
in front of the display companion.

## 1. What you get

- **Internet play, no open ports.** `cloudflared` opens an outbound-only tunnel from your
  machine to Cloudflare's edge; nobody port-forwards or exposes `localhost:5001` directly.
  The tunnel is the sole way in — the display still binds to `127.0.0.1` only.
- **Per-player join links.** Each player gets their own signed, single-use link
  (`https://game.<domain>/j/<token>`) minted by `scripts/gm_invite.py`. Opening it sets a
  session cookie that binds that browser to that character for the rest of the session.
- **No shared secrets with players.** Players never see or need `X-GM-Secret`; only the GM
  console (local, loopback) and GM CLI scripts use it.
- **One-screen phone console.** A joined player lands on a single persistent screen:
  party roster (tap a member for their full sheet as a slide-over), the whole-party
  message dock, and a dice FAB for free rolls. GM roll requests sent with
  `scripts/dice_player.py` raise a dismissible badge instead of hijacking the screen.

LAN mode (`bash display/start-display.sh --lan` / `--lan --tls`, documented in the main
[README](../README.md#display-companion)) is **legacy** under this setup (spec §5) — it's
still there for same-room play where a tunnel is unnecessary overhead, but it does not
provide per-player identity or revocation. Prefer remote play (this doc) whenever players
are not physically in the room, even on a shared home network.

## 2. One-time setup

1. Install cloudflared:
   ```bash
   brew install cloudflared
   ```
2. Authenticate with your Cloudflare account (opens a browser):
   ```bash
   cloudflared login
   ```
3. Create the named tunnel:
   ```bash
   cloudflared tunnel create gm-display
   ```
   This writes a credentials JSON file under `~/.cloudflared/<TUNNEL-UUID>.json` and prints
   the tunnel's UUID.
4. Route your hostname to the tunnel:
   ```bash
   cloudflared tunnel route dns gm-display game.<domain>
   ```
5. Copy the example config and fill in your tunnel UUID and hostname:
   ```bash
   cp display/tunnel/config.yml.example ~/.cloudflared/config.yml
   ```
   Edit `~/.cloudflared/config.yml`: set `credentials-file` to the JSON path from step 3,
   and `hostname` under `ingress` to `game.<domain>`.
6. Export the public host — **required**. This value feeds two things: the `https://`
   links `gm_invite.py` prints, and the server's CORS/CSRF allow-list
   (`_ALLOWED_ORIGINS` in `display/gm-display-app.py`). Without it, the server only trusts
   `http://localhost:5001` as an Origin, and every write from a tunnelled player browser
   gets rejected with `403 {"error": "bad origin"}`.
   ```bash
   export GM_PUBLIC_HOST=game.<domain>
   ```
   Set this in the same shell (or export it from your shell profile) before starting both
   the display and the tunnel each session — it's read once at process start.

## 3. Each session

1. Start the tunnel (this also starts the display if it isn't already running):
   ```bash
   bash display/tunnel/start-tunnel.sh
   ```
2. Mint a join link per player:
   ```bash
   python3 scripts/gm_invite.py -c <campaign> mint Kara Tom --host game.<domain>
   ```
   Prints one `https://game.<domain>/j/<token>` link per character. `--host` defaults to
   `$GM_PUBLIC_HOST` if set, so once `GM_PUBLIC_HOST` is exported you can omit it:
   ```bash
   python3 scripts/gm_invite.py -c <campaign> mint Kara Tom
   ```
3. Send each player their own link **privately** (DM, not a group channel) — anyone who
   opens a link claims that character's session; the token is single-use.

## 4. Verify SSE streams live (do this on first setup — spec gate)

Before relying on this for a real session, confirm events actually stream instead of
arriving in delayed bursts:

1. Open a join link on a phone that's off your Wi-Fi (cellular data), so traffic genuinely
   crosses the tunnel.
2. From the GM console, stage input with `python3 display/send.py` (or type in the console
   UI).
3. The update should appear on the phone within ~2 seconds.

If events only arrive in bursts, something between the edge and the browser is buffering
the SSE stream. Check:

- The response actually carries `Content-Type: text/event-stream` all the way to the
  client:
  ```bash
  curl -N https://game.<domain>/stream -H "Cookie: gm_session=<your-session-cookie>"
  ```
  (grab the cookie value from the browser devtools after opening a join link).
- No `Cache-Control`-stripping proxy sits in front of the tunnel (a corporate/ISP
  transparent proxy on the player's network can do this — try a different network to
  isolate it).
- `disableChunkedEncoding: false` is set in `~/.cloudflared/config.yml` (it's in
  `config.yml.example` by default).

This is a manual, GM-run check — it needs a real Cloudflare tunnel and two devices on two
networks, so it cannot be automated in CI. Do it once per new tunnel setup, and again if
streaming behavior looks wrong in a live session.

## 5. Revoking / reissuing

Revoke a player's active session (their next request gets `403`):
```bash
python3 scripts/gm_invite.py -c <campaign> --revoke Kara
```
List currently active players and whether their session is revoked:
```bash
python3 scripts/gm_invite.py -c <campaign> list
```
Reissuing a link for the same character (`mint` again) auto-revokes the character's prior
session the first time the new link is used — you don't need to `--revoke` before
reissuing. Join links are single-use (consumed on first open) and expire after 72 hours
(`--ttl-hours`, default 72) if never opened.

## 6. Threat model & limits

- **Private-group posture.** This is designed for a GM sending links to a small, known
  group of players, not for public/anonymous access. Anyone who obtains a live join link
  before it's used can claim that character's session — treat links like passwords.
- **Cookie identity assumes per-player browser profiles.** A player's session cookie
  (`gm_session`) is what binds a browser to a character. If two players share one browser
  profile (e.g. a shared tablet), they will collide on the same identity. Use separate
  devices or browser profiles per player.
- **Local console trust.** Requests from `127.0.0.1`/`::1` with no proxy headers
  (`CF-Connecting-IP`, `X-Forwarded-For`) are treated as the GM's local console and bypass
  the join-link/secret checks — this keeps the loopback GM browser usable without its own
  cookie. A `--lan` player (not tunnelled, not loopback) gets nothing under this rule; LAN
  players should use join links like remote players. Residual risk: a header-stripping
  reverse proxy running on the host itself would appear local to this check — don't run
  one on the display host.
- **Secrets.** Two HMAC signing secrets live in `display/`, created on first run with mode
  `0600`:
  - `display/.invite_secret` — signs join links and player session cookies.
  - `display/.gm_secret` — the `X-GM-Secret` value GM CLI scripts (`send.py`,
    `check_input.py`, `push_stats.py`, `autorun_wait.py`) send to prove they're the GM.
  Both are gitignored. Never commit them, and never paste their contents into chat/issues.
  If either leaks, delete the file and restart the display — a fresh secret is generated
  on next boot, invalidating all outstanding links/sessions/GM CLI auth until re-synced.
- **Rate-limit key is client-supplied.** The per-IP rate limiter keys off
  `CF-Connecting-IP`, which a direct (non-tunnelled) or LAN caller could forge to dodge
  limits. This is a spec-mandated tradeoff — the identity gate above, not the rate
  limiter, is the actual security boundary.
