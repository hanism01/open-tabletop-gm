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

    def test_mint_strips_character_whitespace(self):
        # character is the SSE address; surrounding whitespace must not survive minting
        # (Task 6 review: asymmetric strip caused cross-player leak / silent drop).
        t = tokens.mint_session("kara", "  Kara  ", "c", secret=SECRET, now=1000)
        p = tokens.verify(t, secret=SECRET, kind="session", now=1000)
        self.assertEqual(p["character"], "Kara")

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

    def test_non_ascii_sig_does_not_raise(self):
        # hmac.compare_digest raises TypeError on non-ASCII str args; verify()
        # must return None instead of propagating.
        self.assertIsNone(tokens.verify("aGk.日本", secret=SECRET, kind="join", now=0))

    def test_non_hex_sig_rejected(self):
        self.assertIsNone(tokens.verify("aGk.zz", secret=SECRET, kind="join", now=0))

    def test_oversized_token_rejected(self):
        huge = "a" * 5000 + "." + "0" * 64
        self.assertIsNone(tokens.verify(huge, secret=SECRET, kind="join", now=0))

    def test_nonpositive_ttl_rejected(self):
        t = tokens.mint_join("kara", "Kara", "camp1", secret=SECRET, now=1000, ttl_s=0)
        self.assertIsNone(tokens.verify(t, secret=SECRET, kind="join", now=1000))

    def test_bool_ttl_and_issued_rejected(self):
        # type(x) is int must reject bools (isinstance(True, int) is True in Python).
        body = tokens._b64(tokens.json.dumps(
            {"k": "join", "player_id": "kara", "character": "Kara", "campaign": "camp1",
             "jti": "x", "issued_at": True, "ttl_s": 100},
            separators=(",", ":")).encode())
        sig = tokens._sign(body, SECRET)
        self.assertIsNone(tokens.verify(body + "." + sig, secret=SECRET, kind="join", now=0))


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

    def test_set_active_same_sid_twice_does_not_self_revoke(self):
        self.store.set_active("kara", "s1")
        prior = self.store.set_active("kara", "s1")
        self.assertEqual(prior, "s1")
        self.assertFalse(self.store.is_sid_revoked("s1"))

    def test_corrupt_store_fails_closed(self):
        self.store.path.write_bytes(b"not json garbage {{{")
        with self.assertRaises(RuntimeError):
            self.store.consume_jti("j1")

    def test_missing_store_file_is_legitimate_empty(self):
        # Never-written file must not raise — only corruption should.
        self.assertFalse(self.store.is_jti_consumed("j1"))

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

    def test_ensure_secret_rejects_empty_preexisting_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / ".invite_secret"
            p.write_text("")
            with self.assertRaises(ValueError):
                tokens.ensure_secret(p)

    def test_ensure_secret_rejects_malformed_preexisting_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / ".invite_secret"
            p.write_text("not-hex-zz")
            with self.assertRaises(ValueError):
                tokens.ensure_secret(p)

    def test_ensure_secret_no_transient_permissive_window(self):
        # Simulate concurrent first-callers: the O_EXCL create must mean a
        # second caller reads back the already-secured file, never creates
        # a second 0644-then-chmod window.
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / ".invite_secret"
            results = []
            errors = []
            def worker():
                try:
                    results.append(tokens.ensure_secret(p))
                except Exception as e:  # noqa: BLE001
                    errors.append(e)
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads: t.start()
            for t in threads: t.join()
            self.assertEqual(errors, [])
            self.assertEqual(len(set(results)), 1)
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
