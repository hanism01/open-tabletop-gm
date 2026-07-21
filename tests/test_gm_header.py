"""tests/test_gm_header.py — CLI clients present X-GM-Secret, legacy headers gone."""
import pathlib
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
        self.assertNotIn("X-DND-Token", src)
        self.assertIn(".gm_secret", src)

    def test_push_stats_uses_gm_secret_header(self):
        src = (REPO / "display" / "push_stats.py").read_text()
        self.assertIn("X-GM-Secret", src)
        self.assertNotIn("X-DND-Token", src)
        self.assertIn(".gm_secret", src)

    def test_autorun_wait_uses_gm_secret_header(self):
        src = (REPO / "display" / "autorun_wait.py").read_text()
        self.assertIn("X-GM-Secret", src)
        self.assertNotIn("X-DND-Token", src)
        self.assertIn(".gm_secret", src)


if __name__ == "__main__":
    unittest.main()
