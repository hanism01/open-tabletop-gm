# Remote Play Slice 0 — Tunnel + Per-Player Binding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Internet play through a Cloudflare Tunnel with cryptographically bound per-player identity: signed join links → session cookies, fail-closed auth on every identity-bearing route including `GET /stream`, addressed SSE delivery.

**Architecture:** A new stdlib-only token library (`display/tokens.py`) signs join and session tokens with HMAC and tracks consumed `jti`s / revoked `sid`s in a locked, atomically-written JSON file. `scripts/gm_invite.py` mints/revokes/lists. In `gm-display-app.py`, a single `before_request` hook becomes the sole access authority (resolving `g.identity` from the session cookie or the GM `X-GM-Secret` header), the legacy fail-open `_token_ok`/`_device_ok` localhost-trust paths are removed, and `_broadcast_to` adds addressed SSE. Tunnel config + docs make cloudflared the transport.

**Tech Stack:** Python 3.12, Flask, flask-cors (allow-list), stdlib `hmac`/`secrets`/`threading`, cloudflared, unittest via pytest runner.

**Spec:** `docs/superpowers/specs/2026-07-17-remote-play-tunnel-design.md` — the authority when this plan is ambiguous.

## Global Constraints

- No new Python dependencies: token lib uses `hmac`, `secrets`, `json`, `threading` only.
- Secrets files `display/.invite_secret` and `display/.gm_secret`: mode `0600`, generated via `secrets.token_hex(32)` on first use, never logged or echoed.
- All token comparisons use `hmac.compare_digest`.
- Join token TTL default **72h**; session token TTL default **30 days**; TTL checked on **every** verify; expired → reject.
- Fail-closed: no valid identity → **403**, no rate-limit fallthrough, no stack traces, no token echo.
- `remote_addr` grants nothing: no GM trust, no device approval from `127.0.0.1`.
- `CF-Connecting-IP` / `X-Forwarded-For` presence may only **downgrade** trust (mark request tunnelled), never upgrade.
- Character normalization everywhere: `character.strip().lower()[:48]` — must match existing `/stream` registration normalization exactly.
- GM header is `X-GM-Secret` (replaces both `X-DND-Token` and `X-Token`).
- Test runner: `python -m pytest tests -q` from repo root (venv needs `flask`, `flask-cors`, `pyyaml`, `pytest`).
- Existing localhost GM-display flows (chunk, stats, stream replay) must keep passing — run the full suite every task.
- Commit after every task; branch `remote-play-slice0`.

---

## Reference — current code facts (verified 2026-07-18)

- `gm-display-app.py` (2601 lines): `_token_ok` L383-388 (checks `X-DND-Token` vs `_lan_token`, returns True when `_lan_token is None` i.e. non-`--lan` mode — fail-open), `_device_ok` L275-301 (auto-approves `127.0.0.1`/`::1` at L287-290), `_rate_ok` L162-170 (keyed on caller-passed ip), `_sanitize_input` L209-213, `_char_ok` L216-222, `CORS(app)` L393 (wide open), `_clients` L819 / `_client_chars` L825, `_broadcast` L1095-1105, `/player-input` `player_input()` L1924-1958 (weak ad-hoc regex L1941, no `_char_ok`), `/player-input/stage` `stage_input()` L2255-2294 (full sanitize+char_ok path), `/player-input/drain` `drain_player_input()` L2437, `/stream` `stream()` L2456-2566 (binds `?character=`/`?char=` lowercased at ~L2463, full replay to anyone), `app.run(host, port=5001, threaded=True, ...)` L2601.
- `send.py`: sets `X-DND-Token` at L118 inside `_post()` L109-159; token read from `display/.token` by `_read_token()` L94; posts `/chunk`, `/stats`, `/health`, `/dice-request`.
- `check_input.py`: sets `X-Token` (mismatched legacy header) at L91; POSTs `/player-input/drain`; falls back to reading `.input_queue` file when HTTP fails.
- Existing tests import the app via `importlib.util.spec_from_file_location` (see `tests/test_milestone_counter.py::_import_app`) and monkeypatch `cls.mod._token_ok = lambda: True` — these patches must be migrated to the new auth model.
- Line numbers above are pre-change references; re-verify with Grep before each Edit.

## Trust model (implements spec §3 — read before any auth task)

Three identity classes resolved by ONE `before_request` hook, stashed in `g.identity`:

| class | how established | may access |
| --- | --- | --- |
| `gm` | `X-GM-Secret` header matches `display/.gm_secret` (constant-time) **and** request is not tunnelled | everything |
| `player` | valid, unrevoked session cookie | `PLAYER_ENDPOINTS` only |
| `local` | request is **not tunnelled** (no `CF-Connecting-IP`/`X-Forwarded-For` header) **and** `remote_addr` is loopback (`127.0.0.1`/`::1`) | everything except `GM_ENDPOINTS` |
| none | anything else (tunnelled without cookie, or non-loopback without cookie — e.g. a `--lan` stranger) | `PUBLIC_ENDPOINTS` only → otherwise 403 |

- "Tunnelled" = `CF-Connecting-IP` or `X-Forwarded-For` present. Header presence only ever **downgrades** (a tunnelled request can never be `gm` or `local`); absence never upgrades: a non-tunnelled, non-loopback request (LAN mode, ssh -R, misc proxies) gets **no** trust — LAN players now use join links too. Residual accepted risk: a header-stripping reverse proxy *on the host itself* would look local; documented in Task 10.
- A valid player cookie on a **local loopback** request only binds identity for `PLAYER_ENDPOINTS`; for other endpoints the request still counts as `local` (a GM who opened a join link in their console browser must not brick the console).
- Device approval (`_device_ok`) is **bypassed for `role == "player"`** — a signed cookie is strictly stronger identity than the device-id ritual. The gate never derives device state from `remote_addr` (Task 4 removes that branch).
- Endpoint sets keyed on Flask `request.endpoint` (function names, stable across URL changes):
  - `PUBLIC_ENDPOINTS = {"join", "ping", "health", "static"}`
  - `GM_ENDPOINTS = {"chunk", "stats", "drain_player_input", "dice_request"}` (the routes driven by `send.py`/`check_input.py` — they carry the header)
  - `PLAYER_ENDPOINTS = {"index", "stream", "srd_lookup", "player_input", "stage_input", "ready_input", "unstage_input", "skip_input", "player_dice", "narration_pref", "roll_pref", "tts_synthesize", "tts_voice", "audio_toggle", "audio_sfx", "effects_expire", "help_request", "dice_request_status", "get_character_sheet"}` (the phone-companion page fetches `skip`, `audio-toggle`, `effects/expire`, `voice`, `audio/sfx/<name>` — verified in `index.html` JS)
  - Everything else (console controls: `clear`, `device_approve`, `device_deny`, `submit_now`, `queue_consumed`, `dice_request_cancel`, …) is implicitly local-or-gm.
- For `player` identity, `character` is ALWAYS `g.identity["character"]`; body/query `character` fields are ignored. `local`/`gm` may still pass explicit `character` (GM console acts on behalf of characters — spec §3 attribution rule).

---

### Task 1: Token library `display/tokens.py`

**Files:**
- Create: `display/tokens.py`
- Test: `tests/test_tokens.py`

**Interfaces:**
- Produces (later tasks import from `display/tokens.py`):
  - `ensure_secret(path: pathlib.Path) -> str` — read hex secret; create with `secrets.token_hex(32)` + chmod 0600 if missing.
  - `mint_join(player_id, character, campaign, *, secret, ttl_s=72*3600, now=None) -> str`
  - `mint_session(player_id, character, campaign, *, secret, ttl_s=30*86400, now=None) -> str`
  - `verify(token, *, secret, kind, now=None) -> dict | None` — signature + kind + TTL; returns payload dict or None. Does NOT check revocation.
  - `class RevocationStore(path)` with methods `consume_jti(jti) -> bool` (locked check-and-set; False if already consumed), `is_jti_consumed(jti) -> bool`, `revoke_sid(sid)`, `is_sid_revoked(sid) -> bool`, `set_active(player_id, sid) -> str | None` (records new active sid, returns the PRIOR sid it auto-revoked, if any), `active() -> dict`
- Token wire format: `base64.urlsafe_b64encode(json_payload).rstrip("=") + "." + hmac_sha256_hexdigest`. Payload keys: `{"k": "join"|"session", "player_id", "character", "campaign", "jti"|"sid", "issued_at", "ttl_s"}`. `jti`/`sid` = `secrets.token_hex(16)`. Signature over the exact b64 segment; compare with `hmac.compare_digest`.
- Store file JSON shape: `{"jti": [...], "sid": [...], "active": {player_id: sid}}`. All mutations under one `threading.Lock`, written tmp-file + `os.replace` (same pattern as `_persist_tail`).

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_tokens.py — HMAC token lib: sign/verify, TTL, single-use jti, revocation."""
import pathlib
import sys
import tempfile
import threading
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))

import tokens  # noqa: E402

SECRET = "ab" * 32


class TokenSignVerifyTests(unittest.TestCase):
    def test_join_roundtrip(self):
        t = tokens.mint_join("kara", "Kara", "camp1", secret=SECRET, now=1000)
        p = tokens.verify(t, secret=SECRET, kind="join", now=1000)
        self.assertEqual(p["player_id"], "kara")
        self.assertEqual(p["character"], "Kara")
        self.assertEqual(p["campaign"], "camp1")
        self.assertIn("jti", p)

    def test_session_roundtrip_has_sid(self):
        t = tokens.mint_session("kara", "Kara", "camp1", secret=SECRET, now=1000)
        p = tokens.verify(t, secret=SECRET, kind="session", now=1000)
        self.assertIn("sid", p)

    def test_tampered_token_rejected(self):
        t = tokens.mint_join("kara", "Kara", "camp1", secret=SECRET, now=1000)
        body, sig = t.rsplit(".", 1)
        bad = body + "." + ("0" * len(sig))
        self.assertIsNone(tokens.verify(bad, secret=SECRET, kind="join", now=1000))

    def test_wrong_secret_rejected(self):
        t = tokens.mint_join("kara", "Kara", "camp1", secret=SECRET, now=1000)
        self.assertIsNone(tokens.verify(t, secret="cd" * 32, kind="join", now=1000))

    def test_wrong_kind_rejected(self):
        t = tokens.mint_join("kara", "Kara", "camp1", secret=SECRET, now=1000)
        self.assertIsNone(tokens.verify(t, secret=SECRET, kind="session", now=1000))

    def test_ttl_expiry(self):
        t = tokens.mint_join("kara", "Kara", "camp1", secret=SECRET, now=1000, ttl_s=100)
        self.assertIsNotNone(tokens.verify(t, secret=SECRET, kind="join", now=1099))
        self.assertIsNone(tokens.verify(t, secret=SECRET, kind="join", now=1101))

    def test_garbage_rejected(self):
        for junk in ("", "not-a-token", "a.b", "..", "aGk." + "0" * 64):
            self.assertIsNone(tokens.verify(junk, secret=SECRET, kind="join", now=0))


class RevocationStoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = tokens.RevocationStore(pathlib.Path(self.dir.name) / "revoked.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_jti_single_use(self):
        self.assertTrue(self.store.consume_jti("j1"))
        self.assertFalse(self.store.consume_jti("j1"))
        self.assertTrue(self.store.is_jti_consumed("j1"))

    def test_jti_concurrent_consume_exactly_once(self):
        results = []
        def worker():
            results.append(self.store.consume_jti("race"))
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(results.count(True), 1)

    def test_sid_revocation(self):
        self.assertFalse(self.store.is_sid_revoked("s1"))
        self.store.revoke_sid("s1")
        self.assertTrue(self.store.is_sid_revoked("s1"))

    def test_set_active_revokes_prior(self):
        self.assertIsNone(self.store.set_active("kara", "s1"))
        prior = self.store.set_active("kara", "s2")
        self.assertEqual(prior, "s1")
        self.assertTrue(self.store.is_sid_revoked("s1"))
        self.assertFalse(self.store.is_sid_revoked("s2"))

    def test_persistence_across_instances(self):
        self.store.consume_jti("j1")
        self.store.revoke_sid("s1")
        again = tokens.RevocationStore(self.store.path)
        self.assertTrue(again.is_jti_consumed("j1"))
        self.assertTrue(again.is_sid_revoked("s1"))


class SecretFileTests(unittest.TestCase):
    def test_ensure_secret_creates_0600_and_is_stable(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / ".invite_secret"
            s1 = tokens.ensure_secret(p)
            self.assertEqual(len(s1), 64)  # token_hex(32)
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(tokens.ensure_secret(p), s1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_tokens.py -q` (venv with flask/flask-cors/pyyaml/pytest)
Expected: FAIL — `ModuleNotFoundError: No module named 'tokens'`

- [ ] **Step 3: Implement `display/tokens.py`**

```python
"""
tokens.py — HMAC-signed join/session tokens for remote play (Slice 0).

Stdlib only (hmac, secrets, json, threading). Two token kinds:
  join    — single-use invite link payload, short TTL (default 72h)
  session — durable cookie credential, longer TTL (default 30 days)

Wire format: base64url(json payload, no padding) + "." + hex HMAC-SHA256.
Verification checks signature (constant-time), kind, and TTL on EVERY call.
Revocation (consumed jtis, revoked sids) lives in RevocationStore — a locked,
atomically-rewritten JSON file (same tmp+os.replace pattern as _persist_tail).
"""
import base64
import hmac
import hashlib
import json
import os
import pathlib
import secrets
import threading
import time

JOIN_TTL_S = 72 * 3600
SESSION_TTL_S = 30 * 86400


def ensure_secret(path: pathlib.Path) -> str:
    path = pathlib.Path(path)
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_hex(32)
    path.write_text(value)
    os.chmod(path, 0o600)
    return value


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str, secret: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def _mint(kind: str, id_key: str, player_id: str, character: str, campaign: str,
          *, secret: str, ttl_s: int, now=None) -> str:
    payload = {
        "k": kind, "player_id": player_id, "character": character,
        "campaign": campaign, id_key: secrets.token_hex(16),
        "issued_at": int(now if now is not None else time.time()),
        "ttl_s": int(ttl_s),
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return body + "." + _sign(body, secret)


def mint_join(player_id, character, campaign, *, secret, ttl_s=JOIN_TTL_S, now=None):
    return _mint("join", "jti", player_id, character, campaign,
                 secret=secret, ttl_s=ttl_s, now=now)


def mint_session(player_id, character, campaign, *, secret, ttl_s=SESSION_TTL_S, now=None):
    return _mint("session", "sid", player_id, character, campaign,
                 secret=secret, ttl_s=ttl_s, now=now)


def verify(token, *, secret, kind, now=None):
    """Return the payload dict, or None. Checks signature, kind, TTL — not revocation."""
    if not isinstance(token, str) or token.count(".") != 1:
        return None
    body, sig = token.rsplit(".", 1)
    if not body or not hmac.compare_digest(_sign(body, secret), sig):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("k") != kind:
        return None
    issued = payload.get("issued_at")
    ttl = payload.get("ttl_s")
    if not isinstance(issued, int) or not isinstance(ttl, int):
        return None
    current = now if now is not None else time.time()
    if current > issued + ttl:
        return None
    return payload


class RevocationStore:
    """Consumed jtis, revoked sids, and the active sid per player.

    File shape: {"jti": [...], "sid": [...], "active": {player_id: sid}}.
    Every mutation is one locked critical section ending in an atomic
    tmp-file + os.replace rewrite, so concurrent consume_jti cannot
    double-spend a join token.
    """

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        return {"jti": list(data.get("jti", [])),
                "sid": list(data.get("sid", [])),
                "active": dict(data.get("active", {}))}

    def _save(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        os.replace(tmp, self.path)

    def consume_jti(self, jti: str) -> bool:
        with self._lock:
            data = self._load()
            if jti in data["jti"]:
                return False
            data["jti"].append(jti)
            self._save(data)
            return True

    def is_jti_consumed(self, jti: str) -> bool:
        with self._lock:
            return jti in self._load()["jti"]

    def revoke_sid(self, sid: str) -> None:
        with self._lock:
            data = self._load()
            if sid not in data["sid"]:
                data["sid"].append(sid)
                self._save(data)

    def is_sid_revoked(self, sid: str) -> bool:
        with self._lock:
            return sid in self._load()["sid"]

    def set_active(self, player_id: str, sid: str):
        """Record player's new active sid; revoke and return the prior one."""
        with self._lock:
            data = self._load()
            prior = data["active"].get(player_id)
            if prior and prior not in data["sid"]:
                data["sid"].append(prior)
            data["active"][player_id] = sid
            self._save(data)
            return prior

    def active(self) -> dict:
        with self._lock:
            return self._load()["active"]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_tokens.py -q`
Expected: all pass

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest tests -q` — expect 83 existing + new all green.

```bash
git add display/tokens.py tests/test_tokens.py
git commit -m "feat(remote): HMAC join/session token lib with locked revocation store"
```

---

### Task 2: `scripts/gm_invite.py` — mint / revoke / list

**Files:**
- Create: `scripts/gm_invite.py`
- Test: `tests/test_gm_invite.py`

**Interfaces:**
- Consumes: `display/tokens.py` — `ensure_secret`, `mint_join`, `verify`, `RevocationStore` (exact signatures in Task 1).
- Produces: CLI only. `python3 scripts/gm_invite.py -c <campaign> mint <Character> [<Character> ...] [--host game.example.com] [--ttl-hours 72]` → prints one line per player: `<Character>: https://<host>/j/<join_token>`. `--revoke <Character>` revokes that player's active session. `list` prints active players. `player_id` = `character.strip().lower()` (this slug is the identity key everywhere).
- Secret path: `display/.invite_secret` relative to repo (resolve via `pathlib.Path(__file__).resolve().parent.parent / "display"`). Store path: `display/.revoked.json`. Host default: env `GM_PUBLIC_HOST`, else `localhost:5001` with `http://` scheme (https for anything else).
- Never print or log the secret; errors go to stderr, exit 1.

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_gm_invite.py — invite CLI mints verifiable links, revokes, lists."""
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402

SCRIPT = REPO / "scripts" / "gm_invite.py"


def run_invite(display_dir, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--display-dir", str(display_dir), *args],
        capture_output=True, text=True)


class GmInviteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.display = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_mint_prints_verifiable_link_per_player(self):
        out = run_invite(self.display, "-c", "camp1", "mint", "Kara", "Tom",
                         "--host", "game.example.com")
        self.assertEqual(out.returncode, 0, out.stderr)
        links = dict(re.findall(r"^(\w+): (\S+)$", out.stdout, re.M))
        self.assertEqual(set(links), {"Kara", "Tom"})
        secret = (self.display / ".invite_secret").read_text().strip()
        token = links["Kara"].rsplit("/j/", 1)[1]
        p = tokens.verify(token, secret=secret, kind="join")
        self.assertEqual(p["character"], "Kara")
        self.assertEqual(p["player_id"], "kara")
        self.assertEqual(p["campaign"], "camp1")
        self.assertTrue(links["Kara"].startswith("https://game.example.com/j/"))

    def test_secret_created_0600_and_not_printed(self):
        out = run_invite(self.display, "-c", "c", "mint", "Kara")
        secret_file = self.display / ".invite_secret"
        self.assertEqual(secret_file.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(secret_file.read_text().strip(), out.stdout + out.stderr)

    def test_revoke_active_session(self):
        store = tokens.RevocationStore(self.display / ".revoked.json")
        store.set_active("kara", "sid-1")
        out = run_invite(self.display, "-c", "c", "--revoke", "Kara")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(store.is_sid_revoked("sid-1"))

    def test_revoke_unknown_player_errors(self):
        out = run_invite(self.display, "-c", "c", "--revoke", "Nobody")
        self.assertEqual(out.returncode, 1)

    def test_list_shows_active_players(self):
        tokens.RevocationStore(self.display / ".revoked.json").set_active("kara", "s1")
        out = run_invite(self.display, "-c", "c", "list")
        self.assertIn("kara", out.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_gm_invite.py -q`
Expected: FAIL (script missing → returncode 2, assertions fail)

- [ ] **Step 3: Implement `scripts/gm_invite.py`**

```python
#!/usr/bin/env python3
"""
gm_invite.py — mint / revoke / list signed remote-play invite links (Slice 0).

Usage:
    python3 scripts/gm_invite.py -c <campaign> mint Kara Tom [--host game.example.com] [--ttl-hours 72]
    python3 scripts/gm_invite.py -c <campaign> --revoke Kara
    python3 scripts/gm_invite.py -c <campaign> list

Each mint prints one join URL per character. Join links are single-use and
expire (default 72h). The signing secret lives in display/.invite_secret
(created on first run, mode 0600, never printed).
"""
import argparse
import os
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "display"))
import tokens  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-c", "--campaign", required=True)
    ap.add_argument("--display-dir", default=str(_REPO / "display"),
                    help="where .invite_secret / .revoked.json live (tests override)")
    ap.add_argument("--host", default=os.environ.get("GM_PUBLIC_HOST", "localhost:5001"))
    ap.add_argument("--ttl-hours", type=float, default=72.0)
    ap.add_argument("--revoke", metavar="CHARACTER")
    ap.add_argument("command", nargs="?", choices=["mint", "list"])
    ap.add_argument("characters", nargs="*")
    args = ap.parse_args()

    display = pathlib.Path(args.display_dir)
    store = tokens.RevocationStore(display / ".revoked.json")

    if args.revoke:
        player_id = args.revoke.strip().lower()
        sid = store.active().get(player_id)
        if not sid:
            print(f"error: no active session for '{player_id}'", file=sys.stderr)
            return 1
        store.revoke_sid(sid)
        print(f"revoked: {player_id}")
        return 0

    if args.command == "list":
        active = store.active()
        if not active:
            print("no active players")
        for player_id, sid in sorted(active.items()):
            revoked = " (revoked)" if store.is_sid_revoked(sid) else ""
            print(f"{player_id}{revoked}")
        return 0

    if args.command == "mint":
        if not args.characters:
            print("error: mint needs at least one character name", file=sys.stderr)
            return 1
        secret = tokens.ensure_secret(display / ".invite_secret")
        scheme = "http" if args.host.startswith(("localhost", "127.0.0.1")) else "https"
        for character in args.characters:
            character = character.strip()
            token = tokens.mint_join(
                character.lower(), character, args.campaign,
                secret=secret, ttl_s=int(args.ttl_hours * 3600))
            print(f"{character}: {scheme}://{args.host}/j/{token}")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_gm_invite.py -q`
Expected: all pass

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest tests -q`

```bash
git add scripts/gm_invite.py tests/test_gm_invite.py
git commit -m "feat(remote): gm_invite CLI — mint/revoke/list signed join links"
```

---

### Task 3: `/j/<join_token>` route — consume join token, set session cookie

**Files:**
- Modify: `display/gm-display-app.py` (imports near top; new route near `index()` — grep `def index()`)
- Test: `tests/test_join_route.py`

**Interfaces:**
- Consumes: `tokens.verify/mint_session/RevocationStore` (Task 1).
- Produces: module globals used by Task 4: `_INVITE_SECRET = tokens.ensure_secret(_DISPLAY_DIR / ".invite_secret")`, `_GM_SECRET = tokens.ensure_secret(_DISPLAY_DIR / ".gm_secret")`, `_REVOCATION = tokens.RevocationStore(_DISPLAY_DIR / ".revoked.json")`. Cookie name: `gm_session`. Route function name MUST be `join` (endpoint sets in Task 4 depend on it).

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_join_route.py — /j/<token>: verify, single-use consume, cookie, 403 page."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_display_app", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class JoinRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(cls.tmp.name)
        cls.secret = tokens.ensure_secret(d / ".invite_secret")
        cls.mod._INVITE_SECRET = cls.secret
        cls.mod._REVOCATION = tokens.RevocationStore(d / ".revoked.json")
        cls.client = cls.mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _join_token(self, character="Kara", **kw):
        return tokens.mint_join(character.lower(), character, "camp1",
                                secret=self.secret, **kw)

    def test_valid_join_sets_cookie_and_redirects(self):
        r = self.client.get(f"/j/{self._join_token()}")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/")
        cookie = next(c for c in r.headers.getlist("Set-Cookie") if c.startswith("gm_session="))
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        raw = cookie.split("gm_session=", 1)[1].split(";", 1)[0]
        p = tokens.verify(raw, secret=self.secret, kind="session")
        self.assertEqual(p["character"], "Kara")
        self.assertIn("sid", p)

    def test_join_token_single_use(self):
        t = self._join_token("Tom")
        self.assertEqual(self.client.get(f"/j/{t}").status_code, 302)
        second = self.client.get(f"/j/{t}")
        self.assertEqual(second.status_code, 403)
        self.assertNotIn(t, second.get_data(as_text=True))  # no token echo

    def test_tampered_and_expired_join_403(self):
        t = self._join_token("Zed")
        body, sig = t.rsplit(".", 1)
        self.assertEqual(self.client.get(f"/j/{body}.{'0' * len(sig)}").status_code, 403)
        old = self._join_token("Old", now=0, ttl_s=1)
        self.assertEqual(self.client.get(f"/j/{old}").status_code, 403)

    def test_reissue_revokes_prior_session(self):
        r1 = self.client.get(f"/j/{self._join_token('Kara')}")
        raw1 = [c for c in r1.headers.getlist("Set-Cookie") if "gm_session=" in c][0]
        sid1 = tokens.verify(raw1.split("gm_session=", 1)[1].split(";")[0],
                             secret=self.secret, kind="session")["sid"]
        self.client.get(f"/j/{self._join_token('Kara')}")
        self.assertTrue(self.mod._REVOCATION.is_sid_revoked(sid1))

    def test_denied_page_is_plain_no_traceback(self):
        r = self.client.get("/j/garbage")
        self.assertEqual(r.status_code, 403)
        text = r.get_data(as_text=True)
        self.assertIn("ask your GM", text)
        self.assertNotIn("Traceback", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_join_route.py -q`
Expected: FAIL — 404 on `/j/...` (route missing) and AttributeError on `_INVITE_SECRET`

- [ ] **Step 3: Implement**

In `gm-display-app.py`:
1. Near the top imports add `import tokens` and `from flask import g, redirect` (extend the existing `from flask import ...` line — grep `from flask import`).
2. After `_DISPLAY_DIR` is defined (grep `_DISPLAY_DIR =`), add:

```python
# ── Remote-play identity (Slice 0) ───────────────────────────────────────────
# NB: _DISPLAY_DIR (L38) is a plain str — wrap it once.
_IDENTITY_DIR = pathlib.Path(_DISPLAY_DIR)
_INVITE_SECRET = tokens.ensure_secret(_IDENTITY_DIR / ".invite_secret")
_GM_SECRET = tokens.ensure_secret(_IDENTITY_DIR / ".gm_secret")
_REVOCATION = tokens.RevocationStore(_IDENTITY_DIR / ".revoked.json")

_JOIN_DENIED_HTML = (
    "<!doctype html><html><body style='font-family:sans-serif;text-align:center;"
    "padding-top:4em'><h2>This join link is not valid</h2>"
    "<p>It may have expired or already been used — ask your GM for a new link.</p>"
    "</body></html>")
```

3. Add the route (place next to `def index()`):

```python
@app.route("/j/<path:token>")
def join(token):
    payload = tokens.verify(token, secret=_INVITE_SECRET, kind="join")
    if payload is None or not _REVOCATION.consume_jti(payload["jti"]):
        return _JOIN_DENIED_HTML, 403
    session_token = tokens.mint_session(
        payload["player_id"], payload["character"], payload["campaign"],
        secret=_INVITE_SECRET)
    sid = tokens.verify(session_token, secret=_INVITE_SECRET, kind="session")["sid"]
    _REVOCATION.set_active(payload["player_id"], sid)
    resp = redirect("/")
    # Secure only off-localhost: Chrome/Safari drop Secure cookies on plain
    # http, which would break local dev; behind the tunnel the page is https.
    resp.set_cookie("gm_session", session_token, max_age=tokens.SESSION_TTL_S,
                    httponly=True, samesite="Lax",
                    secure=not request.host.startswith(("localhost", "127.0.0.1")))
    return resp
```

4. `pathlib` is already imported (verify with grep; add if not). Ensure `import pathlib` sits above the new globals.

- [ ] **Step 4: Gitignore the secrets**

Append to `.gitignore` (the app now mints real secrets on every import, including test runs):

```
display/.invite_secret
display/.gm_secret
display/.revoked.json
```

Verify: `git status --short` shows no secret files after a test run.

- [ ] **Step 5: Add the concurrent-join race test** — append to `tests/test_join_route.py`:

```python
    def test_concurrent_join_consumes_exactly_once(self):
        import threading
        t = self._join_token("Race")
        codes = []
        def hit():
            codes.append(self.mod.app.test_client().get(f"/j/{t}").status_code)
        threads = [threading.Thread(target=hit) for _ in range(6)]
        for th in threads: th.start()
        for th in threads: th.join()
        self.assertEqual(codes.count(302), 1)
        self.assertEqual(codes.count(403), 5)
```

- [ ] **Step 6: Run tests to verify pass**

Run: `python -m pytest tests/test_join_route.py -q` → pass; then `python -m pytest tests -q` → all green.

- [ ] **Step 7: Commit**

```bash
git add display/gm-display-app.py tests/test_join_route.py .gitignore
git commit -m "feat(remote): /j join route — single-use invite consume, session cookie"
```

---

### Task 4: Fail-closed `before_request` identity gate; kill `_token_ok` fail-open and `_device_ok` localhost trust

**Files:**
- Modify: `display/gm-display-app.py` (middleware after the globals from Task 3; `_token_ok` def ~L383 and ALL its call sites; `_device_ok` ~L275)
- Modify: `tests/test_milestone_counter.py`, `tests/test_display_robustness.py` (replace `_token_ok` monkeypatch with GM header)
- Test: `tests/test_auth_gate.py`

**Interfaces:**
- Consumes: `_INVITE_SECRET`, `_GM_SECRET`, `_REVOCATION`, cookie `gm_session` (Task 3).
- Produces: `g.identity` = `{"role": "gm"}` | `{"role": "local"}` | `{"role": "player", "player_id", "character"}` | `None`; helper `_is_tunnelled()`; endpoint sets `_PUBLIC_ENDPOINTS`, `_GM_ENDPOINTS`, `_PLAYER_ENDPOINTS` (values in the Trust model section above — copy exactly). Tasks 5-7 extend the same `_gate()` function.

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_auth_gate.py — fail-closed identity gate (spec §3)."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402

TUNNEL = {"CF-Connecting-IP": "203.0.113.9"}


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_display_app", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AuthGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(cls.tmp.name)
        cls.secret = tokens.ensure_secret(d / ".invite_secret")
        cls.mod._INVITE_SECRET = cls.secret
        cls.mod._GM_SECRET = "test-gm-secret"
        cls.mod._REVOCATION = tokens.RevocationStore(d / ".revoked.json")
        cls.client = cls.mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _cookie_for(self, character="Kara"):
        t = tokens.mint_session(character.lower(), character, "c", secret=self.secret)
        return t, tokens.verify(t, secret=self.secret, kind="session")["sid"]

    # -- fail-closed over reads AND writes ------------------------------------
    def test_tunnelled_cookieless_stream_403(self):
        r = self.client.get("/stream", headers=TUNNEL)
        self.assertEqual(r.status_code, 403)

    def test_tunnelled_cookieless_writes_403(self):
        # every write route (spec Testing: "rejection ... every write route")
        for path in ("/player-input", "/player-input/stage", "/player-input/ready",
                     "/player-input/unstage", "/player-input/skip", "/player-input/dice",
                     "/player-input/drain", "/player-input/submit-now",
                     "/stats", "/chunk", "/clear", "/effects/expire", "/audio-toggle",
                     "/narration-pref", "/roll-pref", "/tts", "/dice-request",
                     "/device/approve", "/device/deny"):
            r = self.client.post(path, headers=TUNNEL, data="{}",
                                 content_type="application/json")
            self.assertEqual(r.status_code, 403, path)

    def test_non_loopback_untunnelled_is_not_local(self):
        # --lan stranger: no proxy headers, non-loopback peer → nothing
        r = self.client.post("/clear", environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
                             data="{}", content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_public_endpoints_open_when_tunnelled(self):
        self.assertEqual(self.client.get("/ping", headers=TUNNEL).status_code, 200)
        self.assertEqual(self.client.get("/health", headers=TUNNEL).status_code, 200)
        self.assertEqual(self.client.get("/j/garbage", headers=TUNNEL).status_code, 403)  # route runs, token invalid

    # -- no IP-inferred trust -------------------------------------------------
    def test_tunnel_header_blocks_gm_secret(self):
        h = dict(TUNNEL, **{"X-GM-Secret": "test-gm-secret"})
        r = self.client.post("/chunk", headers=h, data="{}",
                             content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_token_ok_fail_open_is_gone(self):
        self.assertFalse(hasattr(self.mod, "_token_ok"))

    def test_device_localhost_autoapprove_gone(self):
        if hasattr(self.mod, "_device_ok"):
            self.mod._REQUIRE_APPROVAL = True
            try:
                self.assertNotEqual(self.mod._device_ok("new-dev", "127.0.0.1"), "approved")
            finally:
                self.mod._REQUIRE_APPROVAL = False

    # -- roles ----------------------------------------------------------------
    def test_gm_secret_grants_gm_locally(self):
        r = self.client.post("/player-input/drain",
                             headers={"X-GM-Secret": "test-gm-secret"})
        self.assertNotEqual(r.status_code, 403)

    def test_local_without_secret_cannot_hit_gm_routes(self):
        for path in ("/chunk", "/stats", "/player-input/drain"):
            r = self.client.post(path, data="{}", content_type="application/json")
            self.assertEqual(r.status_code, 403, path)

    def test_wrong_gm_secret_403(self):
        r = self.client.post("/chunk", headers={"X-GM-Secret": "nope"},
                             data="{}", content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_player_cookie_allows_player_routes(self):
        t, _ = self._cookie_for("Kara")
        self.client.set_cookie("gm_session", t)
        try:
            # Werkzeug 3 responses are lazy: status is readable without
            # consuming the SSE generator (no buffered= kwarg — removed in 2.1)
            r = self.client.get("/stream", headers=TUNNEL)
            self.assertEqual(r.status_code, 200)
            r.close()
        finally:
            self.client.delete_cookie("gm_session")

    def test_player_cookie_cannot_hit_console_or_gm_routes(self):
        t, _ = self._cookie_for("Kara")
        self.client.set_cookie("gm_session", t)
        try:
            for path in ("/chunk", "/stats", "/clear", "/device/approve"):
                r = self.client.post(path, headers=TUNNEL, data="{}",
                                     content_type="application/json")
                self.assertEqual(r.status_code, 403, path)
        finally:
            self.client.delete_cookie("gm_session")

    def test_revoked_session_403(self):
        t, sid = self._cookie_for("Kara")
        self.mod._REVOCATION.revoke_sid(sid)
        self.client.set_cookie("gm_session", t)
        try:
            r = self.client.get("/stream", headers=TUNNEL)
            self.assertEqual(r.status_code, 403)
        finally:
            self.client.delete_cookie("gm_session")

    def test_expired_session_403(self):
        t = tokens.mint_session("kara", "Kara", "c", secret=self.secret, now=0, ttl_s=1)
        self.client.set_cookie("gm_session", t)
        try:
            r = self.client.get("/stream", headers=TUNNEL)
            self.assertEqual(r.status_code, 403)
        finally:
            self.client.delete_cookie("gm_session")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_auth_gate.py -q`
Expected: FAIL — tunnelled requests currently succeed (fail-open `_token_ok`), `_token_ok` still exists.

- [ ] **Step 3: Implement the gate**

In `gm-display-app.py`, below the Task-3 globals add (copy the three endpoint sets from the Trust model section verbatim):

```python
_PUBLIC_ENDPOINTS = {"join", "ping", "health", "static"}
_GM_ENDPOINTS = {"chunk", "stats", "drain_player_input", "dice_request"}
_PLAYER_ENDPOINTS = {
    "index", "stream", "srd_lookup", "player_input", "stage_input", "ready_input",
    "unstage_input", "skip_input", "player_dice", "narration_pref", "roll_pref",
    "tts_synthesize", "tts_voice", "audio_toggle", "audio_sfx", "effects_expire",
    "help_request", "dice_request_status", "get_character_sheet",
}


def _is_tunnelled() -> bool:
    """True when the request traversed a proxy hop (cloudflared or otherwise).

    Presence of these headers only ever DOWNGRADES trust — a tunnelled request
    can never be 'gm' or 'local'. Absence never upgrades a failed check.
    """
    return bool(request.headers.get("CF-Connecting-IP")
                or request.headers.get("X-Forwarded-For"))


def _is_local() -> bool:
    """Genuinely local: no proxy hop AND loopback peer. A --lan stranger or an
    ssh -R hop has a non-loopback remote_addr (or forwarding headers) → not local.
    Absence of tunnel headers never upgrades a non-loopback peer."""
    return (not _is_tunnelled()
            and request.remote_addr in ("127.0.0.1", "::1", None))


def _resolve_identity():
    cookie = request.cookies.get("gm_session")
    if cookie:
        payload = tokens.verify(cookie, secret=_INVITE_SECRET, kind="session")
        if payload and not _REVOCATION.is_sid_revoked(payload.get("sid", "")):
            return {"role": "player", "player_id": payload["player_id"],
                    "character": payload["character"]}
        # invalid/expired/revoked cookie: local console must not brick itself
        return {"role": "local"} if _is_local() else None
    header = request.headers.get("X-GM-Secret", "")
    if header and not _is_tunnelled() and hmac.compare_digest(header, _GM_SECRET):
        return {"role": "gm"}
    if _is_local():
        return {"role": "local"}
    return None


@app.before_request
def _gate():
    """Sole access authority (spec §3): fail-closed over reads and writes."""
    g.identity = _resolve_identity()
    endpoint = (request.endpoint or "").split(".")[-1]
    if endpoint in _PUBLIC_ENDPOINTS:
        return None
    if g.identity is None:
        return jsonify({"error": "forbidden"}), 403
    role = g.identity["role"]
    if role == "player" and endpoint not in _PLAYER_ENDPOINTS and _is_local():
        # GM opened a join link in their console browser: console keeps working
        g.identity = {"role": "local"}
        role = "local"
    if role == "gm":
        return None
    if endpoint in _GM_ENDPOINTS:
        return jsonify({"error": "forbidden"}), 403
    if role == "player" and endpoint not in _PLAYER_ENDPOINTS:
        return jsonify({"error": "forbidden"}), 403
    return None
```

Note: `request.remote_addr` is `127.0.0.1` under Flask's test client, so tests exercise `local` naturally; tunnelled tests add `CF-Connecting-IP` which downgrades regardless of peer address.

- [ ] **Step 4: Remove the legacy trust paths**

1. Delete `def _token_ok()` (grep `def _token_ok`). Delete every call site: grep `_token_ok()` — each is a guard like `if not _token_ok(): return jsonify(...), 403` at the top of a route; remove the whole guard (the gate replaces it). Also delete `_lan_token`/`_get_or_create_token` **only if** their sole remaining consumers were `_token_ok` and the `index()` template arg (check with grep `_lan_token`); `index()` must stop passing `lan_token` to the template only in Task 9 — until then pass `lan_token=""`.
2. In `_device_ok` (grep `def _device_ok`): delete the localhost auto-approve branch (the `ip in ("127.0.0.1", "::1")` check ~L287-290). Device state must never derive from `remote_addr`.
3. Bypass the device gate for authenticated players: at every `_device_ok(...)` call site (grep `_device_ok(` — `stage_input`, `ready_input`, `unstage_input`, `skip_input`), wrap the check:

```python
if (getattr(g, "identity", None) or {}).get("role") != "player":
    status = _device_ok(...)   # existing call + handling unchanged
```

A signed session cookie is strictly stronger identity than the device-id ritual; cookieless local console keeps the existing device flow. Note: `_device_ok` currently returns `"denied"` for an empty device id, so without this bypass every cookie'd player request would 403.
4. The exact write-route paths in the tests below are best-effort — verify each against the `@app.route` decorators (grep `@app.route`) and correct the test paths to the real ones before running.

- [ ] **Step 5: Migrate existing tests off the `_token_ok` monkeypatch**

Only `tests/test_milestone_counter.py` (L40) patches `_token_ok`; `test_display_robustness.py` does not touch it (verified). Replace `cls.mod._token_ok = lambda: True` with:

```python
cls.mod._GM_SECRET = "test-gm-secret"
```

and add the header to every POST helper in those files, e.g. in `_post`:

```python
return self.client.post("/stats", data=json.dumps(body),
                        content_type="application/json",
                        headers={"X-GM-Secret": "test-gm-secret"})
```

(Adapt per file — every request that hits a `_GM_ENDPOINTS` route needs the header; reads need nothing, they are `local`.)

- [ ] **Step 6: Run tests to verify pass**

Run: `python -m pytest tests -q`
Expected: all green (new gate tests + migrated legacy tests + everything else).

- [ ] **Step 7: Commit**

```bash
git add display/gm-display-app.py tests/test_auth_gate.py tests/test_milestone_counter.py tests/test_display_robustness.py
git commit -m "feat(remote): fail-closed before_request identity gate; remove _token_ok fail-open + localhost device trust"
```

---

### Task 5: Attribution — `/stream` and input routes bind character from `g.identity`

**Files:**
- Modify: `display/gm-display-app.py` — `stream()` (grep `def stream`), `stage_input()`, `ready_input()`, `unstage_input()`, `player_input()`, `player_dice()`, `roll_pref()`, `narration_pref()`
- Test: `tests/test_attribution.py`

**Interfaces:**
- Consumes: `g.identity` (Task 4).
- Produces: helper `_bound_character(fallback: str) -> str` used by all input routes; `/stream` registration uses it too.

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_attribution.py — character comes from identity, not request data (spec §3)."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402

TUNNEL = {"CF-Connecting-IP": "203.0.113.9"}


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_display_app", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AttributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(cls.tmp.name)
        cls.secret = tokens.ensure_secret(d / ".invite_secret")
        cls.mod._INVITE_SECRET = cls.secret
        cls.mod._GM_SECRET = "test-gm-secret"
        cls.mod._REVOCATION = tokens.RevocationStore(d / ".revoked.json")
        cls.client = cls.mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.mod._staged.clear()
        self.mod._current_stats = {"players": [{"name": "Kara"}, {"name": "Tom"}]}

    def _login(self, character):
        t = tokens.mint_session(character.lower(), character, "c", secret=self.secret)
        self.client.set_cookie("gm_session", t)

    def tearDown(self):
        self.client.delete_cookie("gm_session")

    def test_stage_ignores_body_character_for_players(self):
        self._login("Kara")
        r = self.client.post("/player-input/stage", headers=TUNNEL,
                             data=json.dumps({"character": "Tom", "text": "I attack"}),
                             content_type="application/json")
        self.assertLess(r.status_code, 300, r.get_data(as_text=True))
        self.assertIn("Kara", self.mod._staged)
        self.assertNotIn("Tom", self.mod._staged)

    def test_two_players_attributed_independently(self):
        for character, text in (("Kara", "kara acts"), ("Tom", "tom acts")):
            self._login(character)
            self.client.post("/player-input/stage", headers=TUNNEL,
                             data=json.dumps({"character": "Everybody", "text": text}),
                             content_type="application/json")
            self.client.delete_cookie("gm_session")
        self.assertEqual(self.mod._staged["Kara"]["text"], "kara acts")
        self.assertEqual(self.mod._staged["Tom"]["text"], "tom acts")

    def test_stream_ignores_query_character_for_players(self):
        self._login("Kara")
        r = self.client.get("/stream?character=Tom", headers=TUNNEL)
        self.assertEqual(r.status_code, 200)
        chars = list(self.mod._client_chars.values())
        self.assertIn("kara", chars)
        self.assertNotIn("tom", chars)
        r.close()

    def test_local_console_can_still_name_characters(self):
        # local role still goes through the device gate — present a device id
        # (with _REQUIRE_APPROVAL False, any non-empty id is approved)
        r = self.client.post("/player-input/stage",
                             headers={"X-DND-Device": "test-device"},
                             data=json.dumps({"character": "Tom", "text": "gm staged"}),
                             content_type="application/json")
        self.assertLess(r.status_code, 300, r.get_data(as_text=True))
        self.assertIn("Tom", self.mod._staged)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_attribution.py -q`
Expected: FAIL — body/query `character` currently wins.

- [ ] **Step 3: Implement**

Add near `_gate()`:

```python
def _bound_character(fallback: str = "") -> str:
    """Authenticated players act only as themselves; local/gm may name anyone."""
    ident = getattr(g, "identity", None) or {}
    if ident.get("role") == "player":
        return ident["character"]
    return fallback
```

Then in each modified route, wrap the existing character read. Example for `stage_input()` (grep `def stage_input`), where the current code reads the body character:

```python
character = _bound_character((data.get("character") or "").strip()[:50])
```

Apply the same one-line substitution in `ready_input`, `unstage_input`, `player_input`, `player_dice`, `roll_pref`, `narration_pref` — keep each route's existing local variable name and downstream validation unchanged. In `stream()` (grep `def stream`), the `?character=`/`?char=` extraction (~L2463) becomes:

```python
char = _bound_character((request.args.get("character") or request.args.get("char") or "").strip())
```

with the existing lowercase/truncate normalization still applied to the result after this line.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_attribution.py -q` then `python -m pytest tests -q` — all green.

- [ ] **Step 5: Commit**

```bash
git add display/gm-display-app.py tests/test_attribution.py
git commit -m "feat(remote): bind character from authenticated identity on stream + input routes"
```

---

### Task 6: `_broadcast_to` addressed SSE delivery + envelope helper

**Files:**
- Modify: `display/gm-display-app.py` (next to `_broadcast`, grep `def _broadcast`)
- Test: `tests/test_broadcast_to.py`

**Interfaces:**
- Consumes: `_clients`, `_client_chars`, `_clients_lock` (existing globals ~L819-825; verify the lock's exact name with grep — reader cites `_clients_lock`).
- Produces: `_broadcast_to(character: str, payload: dict) -> None`; `_envelope(event_type: str, identity: dict | None, payload: dict) -> dict` returning `{"v": 1, "type": ..., "identity": ..., "payload": ...}` (spec §3b schema, frozen for Spec 2).

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_broadcast_to.py — addressed delivery reaches only matching clients (spec §4)."""
import importlib.util
import pathlib
import queue
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_display_app", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BroadcastToTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()

    def setUp(self):
        self.mod._clients.clear()
        self.mod._client_chars.clear()
        self.kara_phone = queue.Queue(maxsize=8)
        self.kara_tablet = queue.Queue(maxsize=8)
        self.tom_phone = queue.Queue(maxsize=8)
        self.unbound = queue.Queue(maxsize=8)
        for q in (self.kara_phone, self.kara_tablet, self.tom_phone, self.unbound):
            self.mod._clients.append(q)
        self.mod._client_chars[self.kara_phone] = "kara"
        self.mod._client_chars[self.kara_tablet] = "kara"
        self.mod._client_chars[self.tom_phone] = "tom"

    def test_reaches_all_devices_of_target_only(self):
        self.mod._broadcast_to("Kara", {"x": 1})
        self.assertEqual(self.kara_phone.get_nowait(), {"x": 1})
        self.assertEqual(self.kara_tablet.get_nowait(), {"x": 1})
        self.assertTrue(self.tom_phone.empty())
        self.assertTrue(self.unbound.empty())

    def test_normalization_matches_registration(self):
        self.mod._broadcast_to("  KARA  ", {"x": 2})
        self.assertFalse(self.kara_phone.empty())

    def test_no_target_no_delivery(self):
        self.mod._broadcast_to("", {"x": 3})
        self.mod._broadcast_to("nobody", {"x": 3})
        for q in (self.kara_phone, self.kara_tablet, self.tom_phone, self.unbound):
            self.assertTrue(q.empty())

    def test_full_queue_does_not_raise(self):
        tiny = queue.Queue(maxsize=1)
        tiny.put_nowait("occupied")
        self.mod._clients.append(tiny)
        self.mod._client_chars[tiny] = "kara"
        self.mod._broadcast_to("Kara", {"x": 4})  # must not raise

    def test_envelope_schema(self):
        env = self.mod._envelope("feedback", {"player_id": "kara", "character": "Kara"},
                                 {"msg": "hi"})
        self.assertEqual(env, {"v": 1, "type": "feedback",
                               "identity": {"player_id": "kara", "character": "Kara"},
                               "payload": {"msg": "hi"}})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_broadcast_to.py -q`
Expected: FAIL — `AttributeError: _broadcast_to`

- [ ] **Step 3: Implement**

Directly below `_broadcast` (grep `def _broadcast`), matching its lock usage exactly (read `_broadcast`'s body first and reuse the same lock name):

```python
def _envelope(event_type, identity, payload):
    """Canonical message envelope (spec §3b). Schema frozen for Spec 2."""
    return {"v": 1, "type": event_type, "identity": identity, "payload": payload}


def _broadcast_to(character, payload):
    """Push payload only to SSE clients registered for this character.

    Normalizes the character exactly like /stream registration (strip,
    lowercase, cap 48) and delivers to every matching queue — a player may
    have several connected devices.
    """
    target = (character or "").strip().lower()[:48]
    if not target:
        return
    with _clients_lock:
        matches = [q for q, c in _client_chars.items() if c == target]
    for q in matches:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass
```

If `/stream` registration truncates differently than `[:48]`, match registration — registration is the source of truth; update the docstring accordingly.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_broadcast_to.py -q` then full suite.

- [ ] **Step 5: Commit**

```bash
git add display/gm-display-app.py tests/test_broadcast_to.py
git commit -m "feat(remote): _broadcast_to addressed SSE delivery + v1 message envelope"
```

---

### Task 7: CORS allow-list, CSRF origin check, tunnel-aware rate key, `/player-input` sanitize parity

**Files:**
- Modify: `display/gm-display-app.py` — `CORS(app)` L393, `_gate()` (Task 4), `_rate_ok` call sites (grep `_rate_ok(`), `player_input()` L1924-1958
- Test: `tests/test_csrf_rate.py`

**Interfaces:**
- Consumes: `_gate()` (Task 4), `_sanitize_input`, `_char_ok` (existing).
- Produces: `_ALLOWED_ORIGINS` (set), `_rate_key() -> str` used by every `_rate_ok` call site.

- [ ] **Step 1: Write the failing tests**

```python
"""tests/test_csrf_rate.py — origin allow-list on writes, per-CF-IP rate buckets, input parity."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_display_app", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CsrfRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(cls.tmp.name)
        cls.secret = tokens.ensure_secret(d / ".invite_secret")
        cls.mod._INVITE_SECRET = cls.secret
        cls.mod._GM_SECRET = "test-gm-secret"
        cls.mod._REVOCATION = tokens.RevocationStore(d / ".revoked.json")
        cls.mod._ALLOWED_ORIGINS = {"https://game.example.com", "http://localhost:5001"}
        cls.client = cls.mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.mod._current_stats = {"players": [{"name": "Kara"}]}
        self.mod._rate_buckets = {}

    def _player_headers(self, character="Kara", ip="203.0.113.9", origin="https://game.example.com"):
        t = tokens.mint_session(character.lower(), character, "c", secret=self.secret)
        self.client.set_cookie("gm_session", t)
        h = {"CF-Connecting-IP": ip}
        if origin:
            h["Origin"] = origin
        return h

    def tearDown(self):
        self.client.delete_cookie("gm_session")

    def _stage(self, headers, text="hi"):
        return self.client.post("/player-input/stage", headers=headers,
                                data=json.dumps({"text": text}),
                                content_type="application/json")

    def test_bad_origin_rejected_even_with_valid_cookie(self):
        r = self._stage(self._player_headers(origin="https://evil.example"))
        self.assertEqual(r.status_code, 403)

    def test_good_origin_accepted(self):
        r = self._stage(self._player_headers())
        self.assertLess(r.status_code, 300, r.get_data(as_text=True))

    def test_gm_writes_bypass_origin_check(self):
        r = self.client.post("/stats", headers={"X-GM-Secret": "test-gm-secret"},
                             data=json.dumps({"players": [{"name": "Kara"}]}),
                             content_type="application/json")
        self.assertLess(r.status_code, 300)

    def test_rate_buckets_keyed_on_cf_ip_not_shared(self):
        h1 = self._player_headers(ip="203.0.113.1")
        for _ in range(25):
            self._stage(h1, "spam")
        blocked = self._stage(h1, "spam")
        self.assertEqual(blocked.status_code, 429)
        self.client.delete_cookie("gm_session")
        h2 = self._player_headers(ip="203.0.113.2")
        ok = self._stage(h2, "fresh")
        self.assertNotEqual(ok.status_code, 429)

    def test_player_input_sanitizes_and_validates_char(self):
        h = self._player_headers()
        r = self.client.post("/player-input", headers=h,
                             data=json.dumps({"text": "attack; rm -rf $(x) `y`"}),
                             content_type="application/json")
        self.assertLess(r.status_code, 300, r.get_data(as_text=True))
        entry = self.mod._input_queue[-1]
        for bad in (";", "$", "`", "(", ")"):
            self.assertNotIn(bad, entry["text"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_csrf_rate.py -q`
Expected: FAIL — no origin check, shared bucket, weak `/player-input` sanitization.

- [ ] **Step 3: Implement**

1. Replace `CORS(app)` (L393) with:

```python
_PUBLIC_HOST = os.environ.get("GM_PUBLIC_HOST", "").strip()
_ALLOWED_ORIGINS = {"http://localhost:5001", "http://127.0.0.1:5001"}
if _PUBLIC_HOST:
    _ALLOWED_ORIGINS.add(f"https://{_PUBLIC_HOST}")
CORS(app, origins=sorted(_ALLOWED_ORIGINS))
```

2. Extend `_gate()` — after the existing role checks, before the final `return None`:

```python
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and role != "gm":
        origin = request.headers.get("Origin") or request.headers.get("Referer", "")
        if not any(origin == o or origin.startswith(o + "/") for o in _ALLOWED_ORIGINS):
            return jsonify({"error": "bad origin"}), 403
```

(SameSite=Lax alone does not stop top-level form POSTs — spec §5. GM CLI clients send no Origin, hence the `role != "gm"` carve-out.)

3. Add `_rate_key` next to `_rate_ok` and switch every call site (grep `_rate_ok(`) to `_rate_ok(_rate_key())`:

```python
def _rate_key() -> str:
    """Rate-limit key. Behind the tunnel remote_addr is always 127.0.0.1 —
    one shared bucket would let one player exhaust everyone's budget."""
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"
```

4. In `player_input()` (L1924-1958): replace the ad-hoc regex strip (L1941) with `text = _sanitize_input(raw_text)` and add the same `_char_ok` validation used by `stage_input()` (L2280-2283) — copy that block, returning 403 on failure, but additionally accept the route's legacy default `"Party"` (`if not (_char_ok(character, known) or character == "Party"): ...`) so characterless local console posts keep working. Ensure a 429 (not 403) is returned when `_rate_ok` fails, and that `/player-input/stage` also returns 429 on rate-limit (grep the existing status; align both).

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_csrf_rate.py -q` then full suite.

- [ ] **Step 5: Commit**

```bash
git add display/gm-display-app.py tests/test_csrf_rate.py
git commit -m "feat(remote): CORS allow-list, CSRF origin gate, CF-IP rate keys, player-input sanitize parity"
```

---

### Task 8: GM header reconciliation — `send.py` + `check_input.py` → `X-GM-Secret`

**Files:**
- Modify: `display/send.py` (`_read_token` L94-98, header L118)
- Modify: `display/check_input.py` (token read L88, header L91)
- Test: `tests/test_gm_header.py`

**Interfaces:**
- Consumes: `display/.gm_secret` (created by the server, Task 3; both scripts fall back to empty string if missing).
- Produces: both scripts send `X-GM-Secret: <secret>`; `X-DND-Token` and `X-Token` are gone.

- [ ] **Step 1: Write the failing test**

```python
"""tests/test_gm_header.py — CLI clients present X-GM-Secret, legacy headers gone."""
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent


class GmHeaderTests(unittest.TestCase):
    def test_send_py_uses_gm_secret_header(self):
        src = (REPO / "display" / "send.py").read_text()
        self.assertIn("X-GM-Secret", src)
        self.assertNotIn("X-DND-Token", src)
        self.assertIn(".gm_secret", src)

    def test_check_input_uses_gm_secret_header(self):
        src = (REPO / "display" / "check_input.py").read_text()
        self.assertIn("X-GM-Secret", src)
        self.assertNotRegex(src, r'"X-Token"')
        self.assertIn(".gm_secret", src)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_gm_header.py -q` → FAIL.

- [ ] **Step 3: Implement**

- `send.py`: `_read_token()` (L94-98) reads `_DIR / ".gm_secret"` instead of `.token`; L118 becomes `headers["X-GM-Secret"] = token`.
- `check_input.py`: token read (L88) points at `.gm_secret`; L91 header dict becomes `{"X-GM-Secret": token, "Content-Length": "0"}`. (This also fixes the pre-existing bug where `X-Token` never matched the server's `X-DND-Token` check.)

- [ ] **Step 4: Run tests + full suite; commit**

```bash
git add display/send.py display/check_input.py tests/test_gm_header.py
git commit -m "fix(remote): reconcile GM CLI auth on X-GM-Secret (.gm_secret bearer)"
```

---

### Task 9: Remove token-in-HTML from the console template

**Files:**
- Modify: `display/templates/index.html` (meta tag L8; JS null-safe already at L5456-5457, L5473-5479)
- Modify: `display/gm-display-app.py` `index()` L1141 (drop the `lan_token` template arg)
- Test: extend `tests/test_auth_gate.py`

**Interfaces:**
- Consumes: gate from Task 4 (local console no longer needs any header — `local` role covers console writes).

- [ ] **Step 1: Write the failing test** — append to `tests/test_auth_gate.py`:

```python
    def test_no_token_in_page_html(self):
        r = self.client.get("/")
        text = r.get_data(as_text=True)
        self.assertNotIn("dnd-token", text)
        self.assertNotIn("lan_token", text)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_auth_gate.py -q` → the new test FAILs (meta tag present).

- [ ] **Step 3: Implement**

- Delete line 8 of `index.html`: `<meta name="dnd-token" content="{{ lan_token }}">`. The consuming JS (L5456-5457) already null-checks and `_authHeaders()` (L5473-5479) omits the header when absent — no JS change needed.
- In `index()` (grep `def index()`), remove the `lan_token=` argument from `render_template`. Then grep `_lan_token` and `_get_or_create_token` — if now unreferenced, delete both and the `.token` bootstrap.

- [ ] **Step 4: Run full suite; commit**

```bash
git add display/templates/index.html display/gm-display-app.py tests/test_auth_gate.py
git commit -m "feat(remote): remove auth token from page HTML — identity is cookie-based"
```

---

### Task 10: Tunnel config, `start-tunnel.sh`, `docs/REMOTE-PLAY.md`, live SSE gate

**Files:**
- Create: `display/tunnel/config.yml.example`, `display/tunnel/start-tunnel.sh`
- Create: `docs/REMOTE-PLAY.md`
- Modify: `README.md` (one line pointing at the new doc, in the display/companion section)

**Interfaces:**
- Consumes: everything above; `gm_invite.py --host` / `GM_PUBLIC_HOST`.

- [ ] **Step 1: `display/tunnel/config.yml.example`**

```yaml
# cloudflared named-tunnel config for open-tabletop-gm remote play.
# Copy to ~/.cloudflared/config.yml after `cloudflared tunnel create gm-display`.
tunnel: gm-display
credentials-file: ~/.cloudflared/<TUNNEL-UUID>.json

ingress:
  - hostname: game.example.com     # <- your hostname
    service: http://localhost:5001
    originRequest:
      noTLSVerify: true
      # SSE: disable buffering so events stream in real time
      disableChunkedEncoding: false
  - service: http_status:404
```

- [ ] **Step 2: `display/tunnel/start-tunnel.sh`**

```bash
#!/usr/bin/env bash
# start-tunnel.sh — boot the cloudflared tunnel alongside the GM display.
# One-time setup: see docs/REMOTE-PLAY.md (cloudflared login + tunnel create).
set -euo pipefail

DISPLAY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TUNNEL_NAME="${GM_TUNNEL_NAME:-gm-display}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "error: cloudflared not installed (brew install cloudflared)" >&2
  exit 1
fi

# Display must be up first (localhost only — the tunnel is the sole way in).
if ! curl -sf "http://localhost:5001/ping" >/dev/null; then
  echo "display not running — starting it..."
  bash "$DISPLAY_DIR/start-display.sh"
  sleep 2
fi

echo "starting tunnel '$TUNNEL_NAME' → http://localhost:5001"
exec cloudflared tunnel run "$TUNNEL_NAME"
```

`chmod +x display/tunnel/start-tunnel.sh`.

- [ ] **Step 3: `docs/REMOTE-PLAY.md`** — write the guide with these sections (full prose, not stubs):
  1. **What you get** — internet play, per-player join links, no open ports; LAN `--lan`/`--tls` mode documented as legacy (spec §5).
  2. **One-time setup** — install cloudflared; `cloudflared login`; `cloudflared tunnel create gm-display`; DNS route `cloudflared tunnel route dns gm-display game.<domain>`; copy `config.yml.example`; `export GM_PUBLIC_HOST=game.<domain>` (used for invite links **and** the CORS/CSRF allow-list — required, writes 403 without it).
  3. **Each session** — `bash display/tunnel/start-tunnel.sh`; `python3 scripts/gm_invite.py -c <campaign> mint Kara Tom --host game.<domain>`; send each player their own link privately.
  4. **Verify SSE streams live (do this on first setup — spec gate)** — open a join link from a phone off-wifi; type in the GM console (`send.py`); the update must appear on the phone within ~2s. If events only arrive in bursts, Cloudflare is buffering: check `Content-Type: text/event-stream` reaches the client (`curl -N https://game.<domain>/stream -H "Cookie: ..."`) and that no `Cache-Control` stripping proxy sits in front.
  5. **Revoking / reissuing** — `gm_invite.py --revoke Kara`; reissuing a link auto-revokes the prior session on first use; links are single-use and expire after 72h.
  6. **Threat model & limits** — private-group posture, cookie identity assumes per-player browser profiles, secrets live in `display/.invite_secret` / `.gm_secret` (0600, never commit).

- [ ] **Step 4: Manual live gate (GM-run, blocks calling Slice 0 done — spec §4)**

Run the section-4 check end-to-end through a real tunnel from two devices on two networks: both players see live events; each staged input arrives attributed `[Kara]` / `[Tom]`. Record the result in the PR body. This requires the GM's Cloudflare account — it cannot be automated here.

- [ ] **Step 5: Full suite; commit**

```bash
git add display/tunnel docs/REMOTE-PLAY.md README.md
git commit -m "docs(remote): cloudflared tunnel config, start script, remote-play guide"
```

---

## Known deviations & mid-branch caveats (reviewed, accepted)

- **`local` trust class** is a plan addition over the spec's gm/player/None: required so the cookieless GM console browser keeps working. Constrained to loopback peer + no proxy headers; a `--lan` stranger gets nothing (LAN players now use join links). Residual risk — a header-stripping reverse proxy running on the host itself would look local; documented in `docs/REMOTE-PLAY.md`.
- **`gm_invite.py` takes explicit character names** rather than parsing "the active campaign's party" from campaign markdown — simpler and unambiguous; party parsing can come later.
- **Nothing emits through `_broadcast_to`/`_envelope` yet** — the producer ("GM issues feedback for Kara") is Spec 2's event spine; Slice 0 lands the tested primitives only. Intentional.
- **Between Task 4 and Task 8 the branch is self-inconsistent** (server wants `X-GM-Secret`, CLIs still send legacy headers). Do not run a live session mid-branch.
- **`_rate_key` trusts `CF-Connecting-IP` from any client** — a direct/LAN caller could rotate the header to dodge rate limits. Spec-mandated key choice; the gate (not the rate limiter) is the security boundary.

## Post-plan verification (before merge)

- `python -m pytest tests -q` — everything green.
- `/security-review`-grade pass: this branch is auth code — per operating floor, TWO blind reviews (both must pass) or `/code-review ultra` before merge.
- Manual live-tunnel SSE gate (Task 10 Step 4) done by the GM, result recorded in the PR.


