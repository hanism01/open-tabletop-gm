"""Shared pytest configuration and the live-server fixture for the browser harness.

Everything else under tests/ drives Flask's test client or reads the template as
text, and needs nothing from this file. Only tests/test_browser_player_controls.py
uses `gm_display`.
"""
import importlib.util
import pathlib
import sys
import tempfile
import threading

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))
import tokens  # noqa: E402

# The browser has to look like a remote player, not like the GM's own console.
# index() hands a loopback caller an empty identity on purpose (a GM opening a
# join link in their own browser must not bind their display for 30 days), and a
# Playwright page hitting 127.0.0.1 *is* loopback. The single thing that makes
# _is_local() false is a proxy-hop header, which is exactly what the existing
# unit tests use (TUNNEL in test_full_display_controls.py) and exactly what a
# real cloudflared player request carries. Set on the browser context, so the
# page document, the EventSource and every fetch carry it.
#
# Budget note for whoever adds more bound page loads here: _rate_key() returns
# this header when it is present, so *every* bound page in this module shares
# one rate-limit bucket, and _rate_ok allows 20 writes per 60s (_RATE_MAX /
# _RATE_WINDOW in gm-display-app.py). Each bound load POSTs /narration-pref on
# its own, and a roll POSTs /player-input/dice. Today that is 6 writes across
# the module. Past 20 within a minute the excess starts coming back 429 — and
# /narration-pref failing is silent in the page, so the symptom would be a
# confusing assertion failure somewhere else, not a visible error. Give each
# bound page its own CF-Connecting-IP if this module ever grows that far.
TUNNEL_HEADERS = {"CF-Connecting-IP": "203.0.113.9"}


def pytest_configure(config):
    # Registered here rather than in a pytest.ini/pyproject.toml because this
    # repo has neither, and inventing one to hold a single marker line would be
    # a new project-wide config surface for no other gain. `-m "not browser"`
    # works off this registration; an unmarked run is unchanged.
    config.addinivalue_line(
        "markers",
        "browser: drives a real Chromium via Playwright against a live server "
        "(needs pytest-playwright and `playwright install chromium`)")


def _import_app():
    # Same mechanism as tests/test_full_display_controls.py — the module's file
    # name contains a hyphen, so it cannot be imported by name.
    spec = importlib.util.spec_from_file_location(
        "gm_display_app_browser", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class GmDisplay:
    """A live gm-display-app on an ephemeral port, isolated from real state."""

    def __init__(self, mod, base_url, secret):
        self.mod = mod
        self.base_url = base_url
        self.secret = secret

    def session_cookie(self, character):
        """A gm_session cookie for `character`, in Playwright's cookie shape."""
        return {
            "name": "gm_session",
            "value": tokens.mint_session(character.lower(), character, "camp",
                                         secret=self.secret),
            "url": self.base_url,
        }

    def open(self, context, character=""):
        """A loaded page at "/", bound to `character` when one is given."""
        if character:
            context.set_extra_http_headers(TUNNEL_HEADERS)
            context.add_cookies([self.session_cookie(character)])
        page = context.new_page()
        page.goto(self.base_url, wait_until="load")
        return page


@pytest.fixture(scope="module")
def gm_display():
    from werkzeug.serving import make_server

    mod = _import_app()
    # ignore_cleanup_errors: an SSE handler thread can still be unwinding when
    # the server goes down, and a stray _persist_log() into a directory being
    # removed must not fail the run.
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    directory = pathlib.Path(tmp.name)

    secret = tokens.ensure_secret(directory / ".invite_secret")
    mod._INVITE_SECRET = secret
    mod._REVOCATION = tokens.RevocationStore(directory / ".revoked.json")
    mod._GM_SECRET = "test-gm-secret"
    # Same isolation as test_remote_player_console.setUpClass, for the same
    # reason: /player-input/dice persists the text log, and left alone
    # _get_log_file() resolves into display/.campaign or falls back to the
    # repo's gitignored display/text_log.json — real developer state, and the
    # cross-run pollution ba048a4 had to work around in test_art_display.py.
    # CAMP_FILE points at a path that does not exist so _get_tail_file() stays
    # None and the tail lives in memory; _text_log is cleared because module
    # import already ran _load_log() against the real file.
    mod.CAMP_FILE = str(directory / "no-such-campaign-file")
    mod._LOG_FALLBACK = str(directory / "text_log.json")
    with mod._text_log_lock:
        mod._text_log.clear()
    # No roster: _playerData stays empty, which is the state the Sheet button's
    # readiness rule is about. Tests that need sheet data can set it themselves.
    mod._current_stats = {}

    server = make_server("127.0.0.1", 0, mod.app, threaded=True)
    base_url = f"http://127.0.0.1:{server.port}"
    # _gate's CSRF check allow-lists Origin against this set, which is built at
    # import time around port 5001. The page posts from an ephemeral port.
    mod._ALLOWED_ORIGINS = {base_url}

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield GmDisplay(mod, base_url, secret)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        # shutdown() only stops the accept loop; without this the listening
        # socket stays open for the life of the pytest process.
        server.server_close()
        tmp.cleanup()
