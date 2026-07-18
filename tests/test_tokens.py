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
