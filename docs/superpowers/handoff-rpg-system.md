# Handoff: `rpg-system` Worktree

**Worktree:** `/Users/hani/projects/ttrpg_skill/.worktrees/rpg-system`

**Branch:** `rpg-system`

**Purpose:** Private GitHub-backed Pathfinder Second Edition and Starfinder Second Edition system modules, using the existing D&D system-module build/sync/lookup pattern.

## End goal

Deliver a complete, table-usable PF2e Remaster and SF2e system integration in
this project:

- Each system is selectable by a campaign and has an accurate, concise
  `system.md` GM rules layer.
- Each system can build a private local dataset from the pinned Foundry GitHub
  source without a running Foundry server.
- Each dataset supports source-aware lookup for actions, ancestries,
  backgrounds, classes, conditions, creatures, equipment, feats, hazards,
  items, rules, spells, vehicles, and the categories exposed by its source.
- PF2e and SF2e share safe importer/normalizer/lookup infrastructure but keep
  their rules and data isolated.
- The display companion renders each system's health, defenses, resources,
  attributes, conditions, effects, and combat fields correctly.
- Generated third-party data remains private and untracked; only importer
  code, module guidance, manifests, provenance rules, and synthetic fixtures
  are committed.
- Existing D&D behavior remains unchanged.
- The full test suite and focused system tests pass, and the worktree is ready
  for a reviewed integration/merge decision.

The immediate paused milestone is smaller: safely recover and verify PF2e in
this worktree, then leave SF2e and final integration for a later explicit
resume.

## Current Git state

The cherry-pick is **complete**. All five PF2e commits landed on `rpg-system`:

- `f91c17a` — PF2e module
- `05c91bc` — PF2e Remaster corrections
- `5784f0a` — recovery and condition styling (was conflicted; resolved)
- `bcdea69` — shared UI/manifest guidance (was conflicted; resolved)
- `659f806` — `stat_lines` suffix documentation

Three conflicts were resolved by taking the corrected incoming text: the dying
scope and Heroic Recovery exception in `systems/pf2e/system.md`, the
valued-condition renderer in `display/templates/index.html` (routed through
`className`, kept the `9a56f6c`-verbatim form so `d94aefa` applied its
longest-prefix rewrite cleanly), and the matching-rules row in
`systems/UI-MANIFEST.md`. An opus SME review approved both resolutions before
they were applied.

The worktree is clean. The shared `remote-play-slice0` checkout was never
touched.

## Completed work on this branch before the cherry-pick

Tasks 1–4 of the approved plan are present and reviewed:

- `82a819c` / `3a806ba` — shared GitHub source contract and hardened atomic writes.
- `aacd92f` / `b18c5e6` / `8cda1ae` / `51a252d` / `b8c5b78` — Foundry pack classification, YAML/JSON normalization, balanced token parsing, entity handling, traversal rejection, and regression tests.
- `43e0e00` / `5ca5bf3` / `ba966cf` / `68f36e7` / `da237e2` — PF2e/SF2e archive builders, source pinning, freshness identity checks, malformed/empty-data rejection, bounded archive reads, and source-path diagnostics.
- `9b36c9c` / `98f2441` — isolated PF2e/SF2e lookup commands, category aliases, dataset validation, and hermetic tests.

The builder uses the `foundryvtt/pf2e` `v14-dev` source archive with `packs/pf2e` and `packs/sf2e` roots. It does not require a running Foundry instance.

## PF2e work being recovered

The PF2e module commits were accidentally created on the shared `remote-play-slice0` checkout by a worker, not on this worktree. The user explicitly chose to cherry-pick them here and leave the shared checkout untouched.

Relevant source commits:

- `8f31829` — initial PF2e module and UI manifest.
- `fceffa5` — PF2e Remaster rules/data corrections.
- `9a56f6c` — recovery and condition styling corrections; currently conflicted.
- `d94aefa` — shared UI/documentation integration fixes.
- `b5f940f` — `stat_lines` suffix documentation.

The PF2e module has already passed source-accuracy review and code-quality review in its original sequence, but those changes must be integrated into this branch carefully because this branch has newer Task 4 display changes.

## Conflict resolution guidance

For `systems/pf2e/system.md`, preserve the incoming corrected dying scope and Heroic Recovery exception from `9a56f6c` while retaining the current branch's valid surrounding rules text.

For `display/templates/index.html`, preserve the current branch's existing renderer behavior and merge in the incoming valued-condition behavior. The final renderer must use exact matches first, then the longest matching base-condition prefix, and return the mapped severity value (`danger`, `warn`, `info`, or `buff`), not the map key.

After resolving:

```bash
git add systems/pf2e/system.md display/templates/index.html
git cherry-pick --continue
git status --short
```

Then verify that the shared checkout remains untouched except for its pre-existing unrelated work. Never reset or clean the shared checkout.

## Verification history

After resolving the cherry-pick (worktree clean):

- Full test suite: **207 passed**.
- Paizo source/pack/lookup focused tests: 43 passed.
- Display robustness tests (includes the node-run valued-condition test): 22 passed.
- `python3 -m json.tool systems/pf2e/ui.json` valid; `git diff --check` clean.

Re-run command for the full suite (venv with flask/pyyaml/pytest):

```bash
python3 -m unittest discover -s tests
```

## Plan status

- Tasks 1–4: complete and reviewed on `rpg-system`.
- Task 5 PF2e: complete — integrated and verified on this branch.
- Task 6 SF2e: **next.** Was intentionally paused; now unblocked.
- Task 7 integration/documentation/full verification: not started.

Plan and spec:

- `docs/superpowers/plans/2026-07-22-pf2e-sf2e-foundry-system-modules.md`
- `docs/superpowers/specs/2026-07-22-pf2e-sf2e-foundry-system-design.md`
