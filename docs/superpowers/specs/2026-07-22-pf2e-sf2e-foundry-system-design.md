# PF2e and SF2e Foundry-Source System Modules

## Purpose

Add comprehensive private-table support for Pathfinder Second Edition Remaster
and Starfinder Second Edition. The modules use Foundry VTT's public GitHub
system sources as their updateable reference data, while preserving this
project's existing system-module architecture.

The result must work without a running Foundry installation. Foundry-specific
or locally owned content can be considered separately after the public-source
workflow is proven.

## Scope

Version one provides two system modules:

- `systems/pf2e/` for Pathfinder Second Edition Remaster.
- `systems/sf2e/` for Starfinder Second Edition.

Each module supplies rules guidance, a character-display manifest, a
GitHub-backed dataset builder, a source synchronizer, and a command-line
lookup tool. The modules import all relevant pack categories available in
their configured public Foundry source, including actions, feats, equipment,
spells, creatures, conditions, and other rules documents supported by that
source.

Version one does not read a running Foundry instance, premium modules, local
world content, media assets, or installed third-party add-ons.

## Source Strategy

The source is GitHub, not a Foundry runtime bridge or a manually managed clone.
This follows the existing `systems/dnd5e/build_srd.py` pattern:

1. A module declares an upstream repository, ref, and supported pack roots.
2. Its builder resolves the ref to an exact commit SHA.
3. The builder downloads only the configured pack files from that commit.
4. The builder writes a normalized local dataset with source provenance.
5. Its synchronizer compares the recorded SHA with upstream and rebuilds only
   when the source changes, unless forced.

The pinned commit is the authoritative source revision for a generated
dataset. This makes lookup results reproducible and makes source updates
explicit.

The public Foundry repository may expose PF2e and SF2e through different
branches, manifests, or pack roots. The source configuration keeps these
values per module instead of assuming a shared location.

## Module Layout

```text
systems/
  paizo2e/
    source.py              shared GitHub fetch, SHA, pack-discovery, metadata helpers
    normalize.py           shared Foundry-document normalization primitives
  pf2e/
    system.md              PF2e Remaster rules and GM procedure
    build_foundry.py       build PF2e's generated dataset
    sync_foundry.py        check/rebuild PF2e source data
    lookup.py              query PF2e data during play
    ui.json                PF2e display manifest
    data/                  generated local data
  sf2e/
    system.md              SF2e rules and GM procedure
    build_foundry.py
    sync_foundry.py
    lookup.py
    ui.json
    data/
```

`paizo2e` contains only reusable implementation helpers. It does not merge
the games' rules data or make one system's options visible to the other.

## Generated Data and Provenance

The builder produces one per-system dataset containing normalized records and
metadata:

- source repository, ref, resolved commit SHA, and build timestamp;
- source pack and document identifier for every record;
- record category, name, system fields needed by lookup, and text needed for
  the table's GM lookup;
- builder schema version.

Source checkouts, raw pack files, generated datasets, and any future indexes
are local private data and are excluded from Git. The repository commits only
the code, module rules, source configuration, licensing/provenance guidance,
and synthetic test fixtures.

## Lookup Experience

Each module's `lookup.py` accepts a category and query, following the D&D
module convention. It searches only its own dataset and reports the source
revision used. Typical categories include actions, feats, items, spells,
creatures, conditions, and rules.

If no dataset is present, the command explains which module builder to run.
If a sync/build fails, the last successful dataset remains intact. The command
does not silently return partial data as a complete source.

## Rules and UI

`system.md` remains the primary GM rules layer. It will describe the relevant
d20 checks, degrees of success, proficiency, three-action turns, reactions,
conditions, recovery, incapacitation, advancement, and table-facing reward
mechanics.

Each system owns a `ui.json` using the existing generic display-manifest
format. The shared code does not alter the display renderer. System modules
push their own health, defenses, resources, conditions, actions, and attribute
fields through the existing stat payload shape.

## Errors and Updates

- Network, GitHub API, malformed-pack, and unsupported-document errors identify
  the source file and preserve the previous dataset.
- Synchronization reports up-to-date, stale, or unverifiable source state.
- Builders reject unknown schema versions instead of guessing how to parse
  them.
- A source update requires an explicit `sync_foundry.py` run or `--force`; it
  never changes data during a game lookup.

## Testing

Tests use compact, synthetic Foundry pack fixtures that cover pack discovery,
normalization, provenance, lookups, stale-source detection, error recovery,
and system isolation. They do not download or commit an upstream corpus.

An integration check may fetch source metadata only. Full dataset builds remain
an opt-in local operation because they depend on network availability and
external source state.

## Acceptance Criteria

1. A PF2e and SF2e module exist and can be selected by a campaign.
2. Each module can build and query its own GitHub-derived data without Foundry
   running.
3. Every generated record identifies the exact source revision and pack.
4. Synchronization detects upstream changes without rebuilding an unchanged
   dataset.
5. One module's lookup cannot return records from the other module.
6. Generated data and raw source content are not tracked by Git.
7. Existing D&D system workflows and display behavior remain unchanged.
