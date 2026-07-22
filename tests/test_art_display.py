"""Tests for GM-controlled active campaign-art SSE state."""
import importlib.util
import json
import pathlib
import queue
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402

TUNNEL = {"CF-Connecting-IP": "203.0.113.9"}
GM = {"X-GM-Secret": "test-gm-secret"}
VALID_ART = {
    "title": "Blackwater Keep",
    "category": "place",
    "kind": "place",
    "image_url": "https://images.example.com/keep.jpg",
    "source_url": "https://artist.example.com/keep",
    "creator": "A. Artist",
    "alt": "A weathered stone keep",
}


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_art_display_app", str(REPO / "display" / "gm-display-app.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gm_art_display_app"] = mod
    spec.loader.exec_module(mod)
    return mod


def _event(response):
    return json.loads(next(response.response).decode().removeprefix("data: "))


class ArtDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.tmp = tempfile.TemporaryDirectory()
        directory = pathlib.Path(cls.tmp.name)
        cls.secret = tokens.ensure_secret(directory / ".invite_secret")
        cls.mod._INVITE_SECRET = cls.secret
        cls.mod._GM_SECRET = "test-gm-secret"
        cls.mod._REVOCATION = tokens.RevocationStore(directory / ".revoked.json")
        cls.client = cls.mod.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        with self.mod._active_art_lock:
            self.mod._active_art = None
        with self.mod._stats_lock:
            self.mod._current_stats = {"players": [{"name": "Kara"}]}

    def test_art_requires_gm_authentication(self):
        response = self.client.post(
            "/art", headers=TUNNEL, data=json.dumps({"action": "show", **VALID_ART}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_player_cannot_control_art(self):
        session = tokens.mint_session("kara", "Kara", "c", secret=self.secret)
        self.client.set_cookie("gm_session", session)
        try:
            response = self.client.post(
                "/art", headers=TUNNEL, data=json.dumps({"action": "show", **VALID_ART}),
                content_type="application/json",
            )
        finally:
            self.client.delete_cookie("gm_session")
        self.assertEqual(response.status_code, 403)

    def test_gm_show_stores_and_replays_active_art(self):
        response = self.client.post(
            "/art", headers=GM, data=json.dumps({"action": "show", **VALID_ART}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json(), {"art": VALID_ART})
        with self.mod._active_art_lock:
            self.assertEqual(self.mod._active_art, VALID_ART)

        stream = self.client.get("/stream", buffered=False)
        events = [_event(stream) for _ in range(3)]
        stream.close()
        self.assertEqual(events[1], {"stats": {"players": [{"name": "Kara"}]}})
        self.assertEqual(events[2], {"art": VALID_ART})

    def test_gm_hide_broadcasts_null_and_clears_active_art(self):
        self.client.post(
            "/art", headers=GM, data=json.dumps({"action": "show", **VALID_ART}),
            content_type="application/json",
        )
        stream = self.client.get("/stream", buffered=False)
        client_queue = self.mod._clients[-1]
        while True:
            try:
                client_queue.get_nowait()
            except queue.Empty:
                break

        response = self.client.post(
            "/art", headers=GM, data=json.dumps({"action": "hide"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(client_queue.get_nowait(), {"art": None})
        stream.close()
        with self.mod._active_art_lock:
            self.assertIsNone(self.mod._active_art)

    def test_show_rejects_private_or_malicious_urls(self):
        for field, value in (
            ("image_url", "https://127.0.0.1/art.jpg"),
            ("source_url", "https://user:pass@example.com/art"),
            ("image_url", "http://images.example.com/art.jpg"),
        ):
            with self.subTest(field=field, value=value):
                payload = {"action": "show", **VALID_ART, field: value}
                response = self.client.post(
                    "/art", headers=GM, data=json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400, response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
