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

    def test_corrupt_revocation_store_denies_403_not_500(self):
        t, _ = self._cookie_for("Kara")
        self.mod._REVOCATION.path.write_text("{ not valid json")
        self.client.set_cookie("gm_session", t)
        try:
            r = self.client.get("/stream", headers=TUNNEL)
            self.assertEqual(r.status_code, 403)
        finally:
            self.client.delete_cookie("gm_session")
            self.mod._REVOCATION.path.write_text('{"jti": [], "sid": [], "active": {}}')


if __name__ == "__main__":
    unittest.main()
