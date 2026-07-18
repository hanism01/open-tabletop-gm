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
