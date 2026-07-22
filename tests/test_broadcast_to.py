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
