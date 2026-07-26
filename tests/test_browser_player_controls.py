"""Full-display player controls, asserted in a real browser.

Everything else that guards these controls reads the template as text. That
cannot see a container that ships collapsed, a rule that keeps an element at
`display: none`, or a button whose enabled state disagrees with its handler —
all three shipped green past the source-string suite. These tests execute the
page instead: real CSS cascade, real SSE, real server state.

Marked `browser`, so `python3 -m pytest tests -q -m "not browser"` runs the rest
of the suite without them. They need two things the repo does not declare
anywhere — it has no test-requirements file, and pytest itself is undeclared
too — so the setup is:

    pip install pytest-playwright
    playwright install chromium        # ~130-180MB, one time

Without them the module skips rather than fails.
"""
import json
import urllib.request

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="browser harness: pip install pytest-playwright && playwright install chromium")
from playwright.sync_api import expect  # noqa: E402

pytestmark = pytest.mark.browser


def _gm_dice_request(gm_display, character, label="Stealth"):
    """POST /dice-request as the GM. Returns the request_id.

    From the test process, not the browser: /dice-request is a GM endpoint and
    the GM secret never reaches the page.
    """
    req = urllib.request.Request(
        f"{gm_display.base_url}/dice-request",
        data=json.dumps({"character": character, "spec": "1d20",
                         "modifier": 2, "label": label, "dc": 15}).encode(),
        headers={"Content-Type": "application/json",
                 "X-GM-Secret": "test-gm-secret"},
        method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)["request_id"]


def test_unbound_display_offers_neither_control(gm_display, context):
    # Runtime state only. This does NOT cover the shipped attributes
    # (`disabled` on the button tag, `style="display:none"` on #pc-dice-btn),
    # and cannot: by the time the page has loaded, _syncPlayerControls() has
    # already re-derived `disabled = !ready`, and #input-panel is still
    # collapsed so nothing in #input-body is visible whatever its own style
    # says. Mutation-checked both ways — deleting either shipped attribute
    # leaves this test green.
    #
    # So test_sheet_button_ships_disabled in tests/test_full_display_controls.py
    # is not redundant with this one and must not be deleted as such: it is the
    # only cover for the window between HTML parse and the first sync, which is
    # also the permanent state if anything earlier in the inline script throws.
    # What this test does catch is the runtime regression — a sync that enables
    # the button with no identity, or a call site that inits the pad for an
    # unbound display (both mutation-checked red).
    page = gm_display.open(context)
    expect(page.locator("#pc-sheet-btn")).to_be_disabled()
    expect(page.locator("#pc-dice-btn")).not_to_be_visible()


def test_bound_player_opens_the_drawer_without_losing_the_narration(gm_display, context):
    # The whole point of putting the drawer on the full display: the phone view
    # hides the narration behind the drawer, and this view must not. (Opening
    # only — the roll itself is
    # test_rolling_from_the_badge_drains_the_pending_request.)
    page = gm_display.open(context, "Kara")
    page.click("#pc-dice-btn")
    expect(page.locator("#dice-drawer-panel")).to_be_visible()
    expect(page.locator("#text-scroll")).to_be_visible()


def test_gm_dice_request_reaches_a_bound_full_display(gm_display, context):
    # #input-panel ships collapsed and the badge lives inside #input-body, so
    # this is green only if the bound branch un-collapses the panel *and* the
    # badge's visible rule is not scoped to body.input-only. Both were broken
    # while the source-string suite stayed green.
    # Under the module's own lock: a live /stream thread reads this dict while
    # holding it. Atomic under the GIL today, but this is the repo's first
    # browser test and it sets the pattern for the next one.
    with gm_display.mod._dice_pending_lock:
        gm_display.mod._dice_pending.clear()
    page = gm_display.open(context, "Kara")
    _gm_dice_request(gm_display, "Kara")
    expect(page.locator("#dice-request-badge")).to_be_visible()


def test_rolling_from_the_badge_drains_the_pending_request(gm_display, context):
    # Server-side assertion in the shape test_remote_player_console.py already
    # uses, but reached through the UI: badge → Open → Roll.
    # Under the module's own lock: a live /stream thread reads this dict while
    # holding it. Atomic under the GIL today, but this is the repo's first
    # browser test and it sets the pattern for the next one.
    with gm_display.mod._dice_pending_lock:
        gm_display.mod._dice_pending.clear()
    page = gm_display.open(context, "Kara")
    request_id = _gm_dice_request(gm_display, "Kara")
    snapshot = gm_display.mod._dice_pending_snapshot()
    assert [e["pending"] for e in snapshot if e["request_id"] == request_id] == [["Kara"]]

    page.click("#dice-request-open")
    expect(page.locator("#dice-drawer-panel")).to_be_visible()
    page.click("#dp-roll")
    # The roll handler hides the badge only after /player-input/dice answered
    # 200, and the server drains the pending entry before answering — so this
    # is a real happens-before, not a sleep.
    expect(page.locator("#dice-request-badge")).to_be_hidden()
    assert gm_display.mod._dice_pending_snapshot() == []


def test_sheet_button_stays_disabled_with_an_identity_but_no_sheet_data(gm_display, context):
    # Override drift. The source-string suite pins that the readiness rule is
    # written once; it cannot stop a later line re-enabling the button after
    # the correct disable. Bound identity + empty _playerData is precisely the
    # state where `who` is truthy and `ready` is not, so an override keyed on
    # `who` alone shows up here and nowhere else.
    page = gm_display.open(context, "Kara")
    # Review F1: the binding is a *precondition* of this test, not scenery.
    # Unbound, the assertion below is still green — but it is then exercising
    # `who === ''`, and the `if (who) _pcSheetBtn.disabled = false;` mutation
    # this test exists to catch stops reddening it. So if the identity path
    # ever regresses, this must fail here rather than keep passing about
    # nothing.
    assert page.evaluate("() => GM_IDENTITY") == "Kara"
    assert page.evaluate("() => document.getElementById('pc-sheet-btn').disabled") is True


def test_the_disabled_sheet_button_can_still_be_hovered(gm_display, context):
    # #stage-btn:disabled and #dm-help-btn:disabled both take pointer-events:
    # none, which kills hit-testing and with it the tooltip that explains why
    # the button is disabled. Whether some broader rule hands this button the
    # same thing is a question about the computed style, which the deleted
    # selector scan tried to answer by reading CSS text and got wrong in both
    # directions. getComputedStyle answers it outright.
    page = gm_display.open(context, "Kara")
    assert page.evaluate("() => GM_IDENTITY") == "Kara"          # review F1
    button = page.locator("#pc-sheet-btn")
    # Review F2: the visibility assertion is what makes the rest of this test
    # mean what its name says. getComputedStyle resolves pointer-events through
    # the cascade whether or not the element is rendered, and to_be_disabled()
    # does not require a box — so on an unbound page, where #input-panel is
    # still collapsed and the button has no box at all, both of the assertions
    # below pass while saying nothing about hit-testing. A computed `auto` on
    # an element that is not laid out is not a hoverable button.
    expect(button).to_be_visible()
    expect(button).to_be_disabled()
    pointer_events = page.evaluate(
        "() => getComputedStyle(document.getElementById('pc-sheet-btn')).pointerEvents")
    assert pointer_events != "none", (
        "a rule in the cascade suppresses hit-testing on the disabled Sheet "
        "button, so its explanatory tooltip is unreachable")


KARA_SHEET = "# Kara\n\n**Class** Rogue\n\n- Thieves' tools\n"


def _seed_sheet_data(page, name):
    """Put one character into the page's own _playerData.

    openSheet renders its live header from _playerData, which normally arrives
    over SSE. The module fixture ships an empty roster on purpose — that is the
    state the Sheet button's readiness rule is about — and it is module-scoped,
    so pushing a roster into the server would leak into every other test here.
    Seeding the page's copy keeps this test's state inside this test.
    """
    page.evaluate(
        """(name) => {
            _playerData[name] = { name, class: 'Rogue', hp: 12, max_hp: 18, ac: 15 };
        }""", name)


def _await_intercept(page, held):
    """Block until a routed request has been captured, or fail saying so."""
    for _ in range(100):
        if held:
            return held[0]
        page.wait_for_timeout(50)
    raise AssertionError("openSheet never fetched the authored sheet")


def test_open_sheet_shows_the_authored_markdown_under_the_live_header(gm_display, context):
    # The live SSE header and the GM's authored .md are two different sources,
    # and a player asking for "my character sheet" means both. Source-string
    # tests cannot see whether the second one actually lands in the DOM, or
    # where — this can.
    page = gm_display.open(context, "Kara")
    page.route("**/character/Kara", lambda route: route.fulfill(
        status=200, content_type="text/markdown; charset=utf-8", body=KARA_SHEET))
    _seed_sheet_data(page, "Kara")
    page.evaluate("() => openSheet('Kara')")

    expect(page.locator("#sheet-modal")).to_be_visible()
    expect(page.locator("#sheet-content .sm-authored h1")).to_have_text("Kara")
    # Order matters, not just presence: a player opening the sheet mid-combat
    # is looking for current HP, and must not have to scroll past the whole
    # authored document to reach it.
    following = page.evaluate(
        """() => document.querySelector('#sheet-content .sm-name')
                 .compareDocumentPosition(
                     document.querySelector('#sheet-content .sm-authored'))
                 & Node.DOCUMENT_POSITION_FOLLOWING""")
    assert following != 0, "the authored body renders above the live header"


def test_a_character_with_no_sheet_file_is_a_quiet_note_not_an_error(gm_display, context):
    # No .md on disk is the normal state for an NPC or a freshly imported PC.
    # No route override here: the fixture's roster is empty, so the real
    # endpoint answers a real 404 and the client's degrade path runs for real.
    page = gm_display.open(context, "Kara")
    _seed_sheet_data(page, "Brann")
    page.evaluate("() => openSheet('Brann')")

    expect(page.locator("#sheet-content .sm-authored-missing")).to_be_visible()
    # The live header is the part that must survive the 404.
    expect(page.locator("#sheet-content .sm-name")).to_have_text("Brann")


def test_closing_the_phone_overlay_does_not_discard_an_open_sheet_fetch(gm_display, context):
    # openSheet must own its stale counter. _playerSheetRequest belongs to the
    # phone overlay and closePlayerSheet() bumps it, so an openSheet fetch that
    # borrowed it would be silently dropped by any overlay close in flight —
    # leaving the modal showing the live header and no authored body, with no
    # error anywhere.
    held = []
    page = gm_display.open(context, "Kara")
    page.route("**/character/Kara", lambda route: held.append(route))
    _seed_sheet_data(page, "Kara")
    page.evaluate("() => openSheet('Kara')")
    route = _await_intercept(page, held)

    page.evaluate("() => closePlayerSheet()")
    route.fulfill(status=200, content_type="text/markdown; charset=utf-8",
                  body=KARA_SHEET)

    expect(page.locator("#sheet-content .sm-authored h1")).to_have_text("Kara")
