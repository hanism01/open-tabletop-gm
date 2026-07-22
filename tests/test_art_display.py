"""Tests for GM-controlled active campaign-art SSE state."""
import importlib.util
import json
import pathlib
import queue
import sys
import tempfile
import threading
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


class BrowserArtDisplayContractTests(unittest.TestCase):
    """Static contracts for the safe, inline browser scene-art renderer."""

    @classmethod
    def setUpClass(cls):
        cls.template = (REPO / "display" / "templates" / "index.html").read_text()

    def assert_in_order(self, source, *needles):
        """Require lifecycle calls to surround a mutation in one source scope."""
        position = -1
        for needle in needles:
            position = source.find(needle, position + 1)
            self.assertNotEqual(position, -1, f"missing {needle!r} in scoped source")

    def test_scene_art_is_an_inline_semantic_figure_not_an_overlay(self):
        self.assertIn("scene-art-panel", self.template)
        self.assertIn("document.createElement('figure')", self.template)
        self.assertIn("document.createElement('figcaption')", self.template)
        self.assertIn("textContent.appendChild(panel)", self.template)
        self.assertIn("max-width: min(62vw, 900px)", self.template)
        self.assertNotIn("#scene-art-panel { position: fixed", self.template)

    def test_scene_art_renderer_uses_safe_dom_and_source_link_safety(self):
        start = self.template.index("function renderSceneArt(")
        end = self.template.index("let charQueue", start)
        renderer = self.template[start:end]
        self.assertNotIn("innerHTML", renderer)
        self.assertIn("sourceLink.rel = 'noopener noreferrer'", renderer)
        self.assertIn("sourceLink.textContent", renderer)
        self.assertIn("image.addEventListener('error'", renderer)
        self.assertIn("failure.hidden = false", renderer)
        self.assertIn("_flushForBlock()", renderer)
        self.assertIn("_reanchorCursor()", renderer)
        self.assertNotIn("aria-expanded", renderer)
        self.assertIn("aria-label", renderer)
        self.assertIn("document.createElement('button')", renderer)

    def test_sse_art_open_replace_and_clear_are_handled(self):
        self.assertIn("if (payload.art !== undefined)", self.template)
        self.assertIn("renderSceneArt(payload.art)", self.template)
        self.assertIn("clearSceneArt()", self.template)
        self.assertIn("scene-art-toggle", self.template)
        self.assertIn("aria-live", self.template)
        start = self.template.index("function renderSceneArt(")
        end = self.template.index("let charQueue", start)
        renderer = self.template[start:end]
        self.assertIn("if (!art) { clearSceneArt(); return; }", renderer)
        self.assertIn("if (key === _sceneArtKey && _sceneArtHost) return;", renderer)
        self.assertIn("if (changed) _sceneArtCollapsedKey = null;", renderer)
        self.assertIn("if (_sceneArtCollapsedKey === key)", renderer)
        clear_start = self.template.index("function clearSceneArt()")
        clear_end = self.template.index("function renderSceneArt(", clear_start)
        clear_renderer = self.template[clear_start:clear_end]
        self.assertIn("_flushForBlock()", clear_renderer)
        self.assertIn("_reanchorCursor()", clear_renderer)

    def test_scene_art_mutations_flush_then_reanchor_in_their_own_scopes(self):
        clear_start = self.template.index("function clearSceneArt()")
        clear_end = self.template.index("function renderSceneArt(", clear_start)
        clear_renderer = self.template[clear_start:clear_end]
        self.assert_in_order(
            clear_renderer,
            "_flushForBlock()",
            "_sceneArtHost.remove()",
            "_reanchorCursor()",
        )

        start = self.template.index("function renderSceneArt(")
        end = self.template.index("let charQueue", start)
        renderer = self.template[start:end]
        show_start = renderer.index("  const show = () => {")
        hide_start = renderer.index("    hide.addEventListener('click'", show_start)
        show_end = renderer.index("  if (_sceneArtCollapsedKey === key)", show_start)
        show_renderer = renderer[show_start:show_end]
        host_replace = "if (_sceneArtHost) _sceneArtHost.replaceWith(panel);"
        host_append = "else textContent.appendChild(panel);"
        self.assertIn(host_replace, show_renderer)
        self.assertIn(host_append, show_renderer)

        # Both initial append and replacement are bracketed inside show().
        self.assert_in_order(
            show_renderer, "_flushForBlock()", host_replace, "_reanchorCursor()"
        )
        self.assert_in_order(
            show_renderer, "_flushForBlock()", host_append, "_reanchorCursor()"
        )

        # Collapsing replaces the figure only after flushing and reanchors after.
        hide_end = renderer.index("    if (_sceneArtHost) _sceneArtHost.replaceWith(panel);", hide_start)
        hide_renderer = renderer[hide_start:hide_end]
        self.assert_in_order(
            hide_renderer,
            "_flushForBlock()",
            "panel.replaceWith(chip)",
            "_reanchorCursor()",
        )

        # Both show-chip handlers restore through show() between flush/reanchor.
        first_chip = hide_renderer[hide_renderer.index("chip.addEventListener('click'"):]
        self.assertIn("_sceneArtCollapsedKey = null;\n        show();", first_chip)
        collapsed_start = renderer.index("  if (_sceneArtCollapsedKey === key)")
        collapsed_end = renderer.index("  } else {", collapsed_start)
        collapsed_renderer = renderer[collapsed_start:collapsed_end]
        self.assert_in_order(
            collapsed_renderer,
            "_flushForBlock()",
            "if (_sceneArtHost) _sceneArtHost.replaceWith(chip);",
            "_reanchorCursor()",
        )
        self.assert_in_order(
            collapsed_renderer,
            "_flushForBlock()",
            "else textContent.appendChild(chip);",
            "_reanchorCursor()",
        )


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
        self.assertEqual(response.status_code, 204, response.get_data(as_text=True))
        with self.mod._active_art_lock:
            self.assertEqual(self.mod._active_art, VALID_ART)

        stream = self.client.get("/stream", buffered=False)
        events = [_event(stream) for _ in range(3)]
        stream.close()
        self.assertEqual(events[1], {"stats": {"players": [{"name": "Kara"}]}})
        self.assertEqual(events[2], {"art": VALID_ART})

    def test_interleaved_art_mutations_finish_with_a_matching_broadcast(self):
        broadcasts = []
        show_entered = threading.Event()
        release_show = threading.Event()
        hide_broadcasted = threading.Event()
        original_broadcast = self.mod._broadcast

        def controlled_broadcast(payload):
            if payload == {"art": VALID_ART}:
                show_entered.set()
                release_show.wait(timeout=1)
            broadcasts.append(payload)
            if payload == {"art": None}:
                hide_broadcasted.set()

        def post(payload):
            client = self.mod.app.test_client()
            client.post("/art", headers=GM, data=json.dumps(payload),
                        content_type="application/json")

        self.mod._broadcast = controlled_broadcast
        show = threading.Thread(target=post, args=({"action": "show", **VALID_ART},))
        hide = threading.Thread(target=post, args=({"action": "hide"},))
        try:
            show.start()
            self.assertTrue(show_entered.wait(timeout=1))
            hide.start()
            hide_broadcasted.wait(timeout=0.2)
            release_show.set()
            show.join(timeout=1)
            hide.join(timeout=1)
        finally:
            release_show.set()
            self.mod._broadcast = original_broadcast

        self.assertFalse(show.is_alive())
        self.assertFalse(hide.is_alive())
        with self.mod._active_art_lock:
            active_art = self.mod._active_art
        self.assertEqual(broadcasts[-1], {"art": active_art})

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
            ("image_url", "https://127.0.0.1.sslip.io/art.jpg"),
            ("source_url", "https://10.0.0.1.sslip.io/art"),
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
