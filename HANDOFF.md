# Handoff: Remote Player One-Screen Console

**Worktree:** `.worktrees/remote-player-console`  
**Branch:** `remote-player-console`  
**Paused:** 2026-07-22, at the user’s request  
**Working tree:** implementation commits are clean; this uncommitted handoff is the only expected change

## Goal

Replace the remote phone Move/Roll/Sheet tabs with one persistent player screen:

- a party roster that opens any party member’s character sheet in a phone slide-over;
- an always-visible message dock containing the draft input and whole-party staged queue;
- one bottom dice drawer used for both free rolls and GM-requested rolls, without hijacking the player’s current context.

The GM is an LLM. Do **not** add human GM-console controls. GM-requested rolls continue to use `scripts/dice_player.py` / `display/send.py --dice-request`.

## Current state

Tasks 1 and 2 are complete and approved. Task 3’s implementation and its quality fixes are committed and tested, but must be re-reviewed before being marked approved. Tasks 4 and 5 have not started.

| Task | Status | Relevant commits |
|---|---|---|
| 1. Server/client contracts | Complete, approved | `6b0d118`, `8374dd1`, `d881514` |
| 2. Persistent phone base | Complete, approved | `f254124`, `1e53e7c`, `25674c8` |
| 3. Roster and sheet slide-over | Implemented; reviews need re-run | `84a74d6`, `b7168ff` |
| 4. Single dice drawer | Pending | — |
| 5. Responsive proof and release docs | Pending | — |

## Task 3: exact review checkpoint

`b7168ff fix: harden player sheet overlay state` resolved the prior quality findings:

- a sequence token prevents a slow response for a previously selected character from replacing the currently requested sheet;
- prior sheet content is cleared while loading;
- Tab and Shift+Tab are trapped within the `aria-modal` overlay;
- background scroll is locked while open and scroll/focus are restored for close button, Escape, and backdrop close paths.

Worker verification reported:

```text
python3 -m pytest tests/test_remote_player_console.py -q  # 8 passed
python3 -m pytest tests -q                                # 207 passed
```

Before beginning Task 4, run a fresh Task 3 spec review and code-quality review against `84a74d6..b7168ff`. Do not amend or revert the commits unless a reviewer finds a specific issue.

## Next implementation task: dice drawer (Task 4)

Use TDD. Start with focused failing tests in `tests/test_remote_player_console.py`, then implement only after they are red.

Required behavior:

1. Remove the tab navigation side effect from `_applyDiceRequest`; it must **not** call `_setActiveTab('roll')` or auto-open the dice UI.
2. GM requests show a dismissible badge/FAB state. Tapping it opens the same `#dice-drawer` used by free rolls.
3. The ordinary dice FAB opens an editable free-roll pad.
4. GM-requested rolls retain the existing prefill, DC label, request ID, and locked controls; completion still posts to `/player-input/dice`.
5. Cancelling/clearing the matching request hides the badge, clears the active request ID, and unlocks the controls.
6. Preserve the player’s message draft and whole-party staged queue. Do not restore the old phone tabs.

The planned focused checks are:

```bash
python3 -m pytest tests/test_remote_player_console.py -q -k dice
python3 -m pytest tests/test_remote_player_console.py tests/test_attribution.py -q
```

## Task 5 (after Task 4 approval)

At 375px and 430px, prove in the browser that roster, message dock, staged queue, and FAB are usable without tabs; opening/closing a sheet retains a message draft; free and requested dice flows use the one drawer; and remote staged-input attribution remains bound to the signed-in character.

Then update `docs/REMOTE-PLAY.md` and `display/README.md`, run the full suite, and request final spec and quality review.

## Key files

- `display/templates/index.html` — phone console markup, CSS, roster/sheet/dice JavaScript.
- `display/gm-display-app.py` — authenticated party-sheet access and staged-input/dice endpoints.
- `tests/test_remote_player_console.py` — focused behavioral/markup contracts.
- `tests/test_attribution.py` — signed-in player attribution contract.
- `docs/superpowers/specs/2026-07-21-remote-player-console-design.md` — agreed design.

The fuller step-by-step plan currently exists in the primary checkout at `docs/superpowers/plans/2026-07-22-remote-player-one-screen-console.md`; copy or commit it into this branch if the continuation needs that checklist to travel with the worktree.

## Continuation protocol

1. Confirm `git status --short` shows only `?? HANDOFF.md` (unless this document has subsequently been committed).
2. Re-run the two Task 3 review gates and record their results.
3. Only if both approve, assign a fresh worker to Task 4; keep the scope limited to dice drawer behavior.
4. After each task: run focused tests, full tests, spec review, then code-quality review.
5. Do not merge this branch until Tasks 4 and 5 are approved and browser proof is recorded.
