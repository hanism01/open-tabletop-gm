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


if __name__ == "__main__":
    unittest.main()
