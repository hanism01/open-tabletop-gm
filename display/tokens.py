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


def _valid_secret(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def ensure_secret(path: pathlib.Path) -> str:
    path = pathlib.Path(path)
    # Write to a private tmp file first, then atomically publish via os.link
    # (fails EEXIST if the target already exists) so no reader can ever see
    # the target file before it holds its full, final content.
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    value = secrets.token_hex(32)
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(value)
        try:
            os.link(str(tmp), str(path))
        except FileExistsError:
            pass
    finally:
        tmp.unlink(missing_ok=True)
    existing = path.read_text().strip()
    if not _valid_secret(existing):
        raise ValueError(f"secret file {path} does not contain 64 hex chars")
    return existing


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str, secret: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def _mint(kind: str, id_key: str, player_id: str, character: str, campaign: str,
          *, secret: str, ttl_s: int, now=None) -> str:
    payload = {
        "k": kind, "player_id": player_id, "character": character.strip(),
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


MAX_TOKEN_LEN = 4096


def verify(token, *, secret, kind, now=None):
    """Return the payload dict, or None. Checks signature, kind, TTL — not revocation."""
    if not isinstance(token, str) or len(token) > MAX_TOKEN_LEN or token.count(".") != 1:
        return None
    body, sig = token.rsplit(".", 1)
    if not body:
        return None
    expected = _sign(body, secret)
    try:
        sig_bytes = bytes.fromhex(sig)
        expected_bytes = bytes.fromhex(expected)
    except ValueError:
        return None
    if not hmac.compare_digest(expected_bytes, sig_bytes):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("k") != kind:
        return None
    issued = payload.get("issued_at")
    ttl = payload.get("ttl_s")
    if type(issued) is not int or type(ttl) is not int:
        return None
    if ttl <= 0:
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
            text = self.path.read_text()
        except FileNotFoundError:
            data = {}
        except OSError as e:
            raise RuntimeError(f"revocation store {self.path} unreadable: {e}") from e
        else:
            try:
                data = json.loads(text)
            except ValueError as e:
                raise RuntimeError(f"revocation store {self.path} corrupt: {e}") from e
            if not isinstance(data, dict):
                raise RuntimeError(f"revocation store {self.path} corrupt: not an object")
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
            if prior and prior != sid and prior not in data["sid"]:
                data["sid"].append(prior)
            data["active"][player_id] = sid
            self._save(data)
            return prior

    def active(self) -> dict:
        with self._lock:
            return self._load()["active"]
