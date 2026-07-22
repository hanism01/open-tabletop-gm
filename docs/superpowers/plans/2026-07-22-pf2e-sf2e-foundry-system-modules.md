# PF2e and SF2e Foundry-Source System Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add private, GitHub-backed Pathfinder Second Edition Remaster and Starfinder Second Edition system modules that build local lookup datasets from Foundry source packs.

**Architecture:** Reuse the D&D module's direct-GitHub builder/sync/lookup lifecycle. A small `systems/paizo2e` helper package owns GitHub access, source provenance, pack-document loading, record normalization, and lookup primitives; `pf2e` and `sf2e` own their source specifications, rules guidance, UI manifests, generated datasets, and command wrappers. Both systems resolve from the `foundryvtt/pf2e` `v14-dev` source tree, using `packs/pf2e` and `packs/sf2e` respectively.

**Tech Stack:** Python 3 standard library, PyYAML for Foundry source YAML, GitHub REST/raw-content endpoints, JSON, `unittest`, existing display UI-manifest contract.

---

## File Structure

| Path | Responsibility |
|---|---|
| `systems/paizo2e/__init__.py` | Marks shared helper package. |
| `systems/paizo2e/source.py` | Source specifications, GitHub HTTP/tree access, commit resolution, atomic JSON writes. |
| `systems/paizo2e/packs.py` | YAML/JSON Foundry document parsing, category mapping, description cleanup, record normalization. |
| `systems/paizo2e/lookup.py` | Dataset loading, exact/substring lookup ranking, CLI formatting. |
| `systems/pf2e/build_foundry.py` | PF2e builder configuration and commands. |
| `systems/pf2e/sync_foundry.py` | PF2e stale-check/rebuild command. |
| `systems/pf2e/lookup.py` | PF2e lookup CLI wrapper. |
| `systems/pf2e/system.md` | PF2e Remaster GM procedure and command guidance. |
| `systems/pf2e/ui.json` | PF2e display manifest. |
| `systems/sf2e/...` | SF2e equivalents with `packs/sf2e` source root. |
| `tests/test_paizo2e_source.py` | Unit tests for source discovery, stale detection, and safe writes. |
| `tests/test_paizo2e_packs.py` | Unit tests for synthetic pack parsing and normalization. |
| `tests/test_paizo2e_lookup.py` | Unit tests for per-system lookup isolation and CLI output. |
| `.gitignore` | Ignores the two generated datasets. |

### Task 1: Establish the shared source contract and ignored dataset locations

**Files:**
- Create: `systems/paizo2e/__init__.py`
- Create: `systems/paizo2e/source.py`
- Create: `tests/test_paizo2e_source.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing tests for source specs, metadata, and atomic replacement.**

```python
from systems.paizo2e.source import SourceSpec, dataset_metadata, write_dataset

def test_source_spec_uses_the_split_v14_foundry_pack_roots():
    pf2e = SourceSpec("pf2e", "packs/pf2e")
    sf2e = SourceSpec("sf2e", "packs/sf2e")
    assert pf2e.repo == sf2e.repo == "foundryvtt/pf2e"
    assert pf2e.ref == sf2e.ref == "v14-dev"

def test_metadata_records_resolved_sha_and_record_provenance(tmp_path):
    meta = dataset_metadata(SourceSpec("pf2e", "packs/pf2e"), "abc123", {"actions": 2})
    assert meta["source"]["sha"] == "abc123"
    assert meta["system"] == "pf2e"
    out = tmp_path / "dataset.json"
    write_dataset(out, {"_meta": meta, "actions": []})
    assert out.exists()
```

- [ ] **Step 2: Run the new test to verify it fails.**

Run: `python3 -m unittest tests.test_paizo2e_source -v`

Expected: FAIL because `systems.paizo2e.source` does not exist.

- [ ] **Step 3: Implement the source helpers.**

```python
@dataclass(frozen=True)
class SourceSpec:
    system: str
    pack_root: str
    repo: str = "foundryvtt/pf2e"
    ref: str = "v14-dev"

def dataset_metadata(spec, sha, counts):
    return {"schema_version": 1, "system": spec.system,
            "source": {"repo": spec.repo, "ref": spec.ref, "sha": sha,
                       "pack_root": spec.pack_root}, "record_counts": counts}

def write_dataset(path, dataset):
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(dataset, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
```

Add GitHub request helpers with a fixed user agent, 30-second timeout, URL-encoded paths, and explicit `RuntimeError` messages. Add `resolve_ref(spec)` using GitHub's commits endpoint and `tree_at_sha(spec, sha)` using the recursive tree endpoint.

- [ ] **Step 4: Ignore generated data only.**

Append exactly:

```gitignore
# Generated Foundry-source datasets (private local table data)
systems/pf2e/data/pf2e_foundry.json
systems/sf2e/data/sf2e_foundry.json
```

- [ ] **Step 5: Run the test and whitespace validation.**

Run: `python3 -m unittest tests.test_paizo2e_source -v && git diff --check`

Expected: PASS; the two dataset paths are ignored.

- [ ] **Step 6: Commit.**

```bash
git add systems/paizo2e/__init__.py systems/paizo2e/source.py tests/test_paizo2e_source.py .gitignore
git commit -m "feat: add shared Foundry source contract"
```

### Task 2: Parse and normalize Foundry pack documents

**Files:**
- Create: `systems/paizo2e/packs.py`
- Create: `tests/test_paizo2e_packs.py`

- [ ] **Step 1: Write failing normalization tests using only synthetic YAML.**

```python
from systems.paizo2e.packs import normalize_document, pack_category

def test_normalizes_a_foundry_action_with_source_provenance():
    raw = """name: Stride\ntype: action\nsystem:\n  description:\n    value: '<p>Move up to your Speed.</p>'\n  traits:\n    value: [move]\n"""
    record = normalize_document(raw, "packs/pf2e/actions/stride.yaml", "actions")
    assert record["name"] == "Stride"
    assert record["category"] == "actions"
    assert record["description"] == "Move up to your Speed."
    assert record["source_path"].endswith("stride.yaml")

def test_pack_category_maps_bestiaries_to_creatures_and_excludes_media():
    assert pack_category("packs/sf2e/alien-core/alien.yaml") == "creatures"
    assert pack_category("packs/pf2e/spells/fireball.yaml") == "spells"
    assert pack_category("packs/pf2e/assets/logo.webp") is None
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `python3 -m unittest tests.test_paizo2e_packs -v`

Expected: FAIL because `systems.paizo2e.packs` does not exist.

- [ ] **Step 3: Implement deterministic pack selection and normalization.**

Implement `pack_category(path)` with these return categories: `actions`, `ancestries`, `backgrounds`, `classes`, `conditions`, `creatures`, `equipment`, `feats`, `hazards`, `items`, `rules`, `spells`, and `vehicles`. Match directory names and `*-bestiary` paths; return `None` for `.webp`, `.png`, `.jpg`, `.mp3`, `.ogg`, and unknown paths.

Implement `normalize_document(raw_text, source_path, category)` to parse YAML with `yaml.safe_load`, reject non-mapping documents and documents with no name, and return:

```python
{
  "name": name,
  "index": slugify(name),
  "category": category,
  "type": document.get("type", ""),
  "description": strip_foundry_markup(description),
  "traits": system.get("traits", {}).get("value", []),
  "level": system.get("level", {}).get("value"),
  "source_path": source_path,
}
```

`strip_foundry_markup` must replace `@UUID[...] {label}` and `@Check[...] {label}` with labels, remove remaining `@Token[...]` and HTML tags, then collapse blank lines. Keep unknown `system` fields out of the v1 normalized record rather than guessing their meaning.

- [ ] **Step 4: Run unit tests.**

Run: `python3 -m unittest tests.test_paizo2e_packs -v`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add systems/paizo2e/packs.py tests/test_paizo2e_packs.py
git commit -m "feat: normalize Foundry source pack documents"
```

### Task 3: Build, retain, and synchronize per-system datasets

**Files:**
- Modify: `systems/paizo2e/source.py`
- Create: `systems/pf2e/build_foundry.py`
- Create: `systems/pf2e/sync_foundry.py`
- Create: `systems/sf2e/build_foundry.py`
- Create: `systems/sf2e/sync_foundry.py`
- Create: `systems/pf2e/data/.gitkeep`
- Create: `systems/sf2e/data/.gitkeep`
- Modify: `tests/test_paizo2e_source.py`

- [ ] **Step 1: Add failing tests for changed-source rebuild decisions and last-good-data preservation.**

```python
from systems.paizo2e.source import needs_rebuild

def test_needs_rebuild_only_when_sha_changes_or_dataset_is_missing(tmp_path):
    path = tmp_path / "pf2e_foundry.json"
    assert needs_rebuild(path, "new") is True
    path.write_text('{"_meta":{"source":{"sha":"old"}}}')
    assert needs_rebuild(path, "old") is False
    assert needs_rebuild(path, "new") is True
```

- [ ] **Step 2: Run the failing test.**

Run: `python3 -m unittest tests.test_paizo2e_source -v`

Expected: FAIL because `needs_rebuild` does not exist.

- [ ] **Step 3: Implement a generic build function and thin system wrappers.**

Add `build_dataset(spec, output_path, force=False)` to `source.py`. It must: resolve the SHA; return `False` with an up-to-date message when `needs_rebuild` is false; select source-tree blobs under `spec.pack_root`; fetch only `.yaml`, `.yml`, and `.json` documents; normalize supported documents; count records by category; call `write_dataset` only after all selected downloads complete; and return `True` after replacement.

Each wrapper is intentionally small:

```python
# systems/pf2e/build_foundry.py
SPEC = SourceSpec("pf2e", "packs/pf2e")
OUT_FILE = Path(__file__).parent / "data" / "pf2e_foundry.json"
if __name__ == "__main__":
    build_dataset(SPEC, OUT_FILE, force="--force" in sys.argv)
```

Use the analogous `sf2e` / `packs/sf2e` / `sf2e_foundry.json` values for SF2e. `sync_foundry.py --check` prints `Up to date.`, `Stale.`, or `Unverifiable.`; without `--check` it calls the builder only when stale. A failed run must raise before `write_dataset`, preserving the prior file.

- [ ] **Step 4: Run focused tests.**

Run: `python3 -m unittest tests.test_paizo2e_source tests.test_paizo2e_packs -v`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add systems/paizo2e/source.py systems/pf2e systems/sf2e tests/test_paizo2e_source.py
git commit -m "feat: add PF2e and SF2e dataset builders"
```

### Task 4: Add isolated category lookup commands

**Files:**
- Create: `systems/paizo2e/lookup.py`
- Create: `systems/pf2e/lookup.py`
- Create: `systems/sf2e/lookup.py`
- Create: `tests/test_paizo2e_lookup.py`

- [ ] **Step 1: Write failing lookup and isolation tests.**

```python
from systems.paizo2e.lookup import find_records

def test_lookup_prefers_exact_name_and_never_crosses_system_dataset():
    pf = {"actions": [{"name": "Stride", "index": "stride"}]}
    sf = {"actions": [{"name": "Boost", "index": "boost"}]}
    assert find_records(pf, "actions", "stride")[0]["name"] == "Stride"
    assert find_records(sf, "actions", "stride") == []
```

- [ ] **Step 2: Run the failing test.**

Run: `python3 -m unittest tests.test_paizo2e_lookup -v`

Expected: FAIL because the shared lookup helper does not exist.

- [ ] **Step 3: Implement ranking, output, and wrappers.**

Implement `find_records(dataset, category, query, limit=1)` with exact normalized-name matches first, then case-insensitive substring matches sorted by `(name.casefold(), source_path)`. Implement `format_record(record, source_sha)` to include category, traits, level, description, source path, and the first 12 SHA characters. The wrappers load only their own output file and support:

```text
python3 systems/pf2e/lookup.py spell "fireball"
python3 systems/sf2e/lookup.py creature "akreni"
python3 systems/pf2e/lookup.py any "stride" --all
```

If the dataset is absent, print the exact matching builder command and exit 1. If no record matches, print a no-match message and exit 0.

- [ ] **Step 4: Run the lookup tests.**

Run: `python3 -m unittest tests.test_paizo2e_lookup -v`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add systems/paizo2e/lookup.py systems/pf2e/lookup.py systems/sf2e/lookup.py tests/test_paizo2e_lookup.py
git commit -m "feat: add PF2e and SF2e lookup commands"
```

### Task 5: Add the PF2e module contract and display manifest

**Files:**
- Create: `systems/pf2e/system.md`
- Create: `systems/pf2e/ui.json`
- Modify: `SYSTEM-PORTING.md`
- Test: `python3 -m json.tool systems/pf2e/ui.json`

- [ ] **Step 1: Write the PF2e `system.md` from `systems/TEMPLATE.md`, replacing every scaffold field.**

Define the remastered d20 check against a DC, four degrees of success, natural-20/natural-1 degree adjustment, proficiency ranks, three actions plus reaction, hero points, dying/wounded, conditions, encounter mode, and recovery. Include exact command examples:

```text
python3 systems/pf2e/lookup.py action "aid"
python3 systems/pf2e/sync_foundry.py --check
```

- [ ] **Step 2: Add `ui.json` for PF2e fields.**

Use a Health bar, a Hero Points bar, stat lines for AC/Speed/Perception/Class DC, a conditions tag list, an effects list, and an ability-score grid for STR/DEX/CON/INT/WIS/CHA. The combat strip contains HP, AC, Speed, and Class DC.

- [ ] **Step 3: Document the new module's data lifecycle.**

Add a short `SYSTEM-PORTING.md` subsection that states system datasets may be generated locally, must record source metadata, and must be ignored when derived from third-party GitHub content. Reference the PF2e build/sync/lookup commands.

- [ ] **Step 4: Validate the manifest and inspect all required template headings.**

Run: `python3 -m json.tool systems/pf2e/ui.json >/dev/null && rg -n '^## ' systems/pf2e/system.md`

Expected: valid JSON and all template sections present.

- [ ] **Step 5: Commit.**

```bash
git add systems/pf2e/system.md systems/pf2e/ui.json SYSTEM-PORTING.md
git commit -m "feat: add Pathfinder Second Edition module"
```

### Task 6: Add the SF2e module contract and display manifest

**Files:**
- Create: `systems/sf2e/system.md`
- Create: `systems/sf2e/ui.json`
- Test: `python3 -m json.tool systems/sf2e/ui.json`

- [ ] **Step 1: Write the SF2e `system.md` from `systems/TEMPLATE.md`, replacing every scaffold field.**

Document the shared d20/degrees/proficiency/three-action engine and SF2e-specific table procedures for ranged and area attacks, item levels, technology, spellcasting, and SF2e conditions. Keep ancestry, class, item, spell, creature, and setting lookup in the SF2e dataset only. Include:

```text
python3 systems/sf2e/lookup.py item "azimuth laser pistol"
python3 systems/sf2e/sync_foundry.py --check
```

- [ ] **Step 2: Add `ui.json` for SF2e fields.**

Use a Health bar, a Resolve Points bar, stat lines for AC/Speed/Perception/Class DC, a condition tag list, an effects list, and the standard six-ability grid. The combat strip contains HP, AC, Speed, and Class DC.

- [ ] **Step 3: Validate the module.**

Run: `python3 -m json.tool systems/sf2e/ui.json >/dev/null && rg -n '^## ' systems/sf2e/system.md`

Expected: valid JSON and all template headings present.

- [ ] **Step 4: Commit.**

```bash
git add systems/sf2e/system.md systems/sf2e/ui.json
git commit -m "feat: add Starfinder Second Edition module"
```

### Task 7: Verify integration, source behavior, and documentation

**Files:**
- Modify: `README.md`
- Modify: `tests/test_paizo2e_source.py`
- Modify: `tests/test_paizo2e_lookup.py`

- [ ] **Step 1: Add integration tests for separate generated dataset paths and wrapper error messages.**

```python
def test_pf2e_and_sf2e_wrappers_use_distinct_generated_files():
    assert "pf2e_foundry.json" in PF2E_LOOKUP_SOURCE
    assert "sf2e_foundry.json" in SF2E_LOOKUP_SOURCE
```

Also test that a simulated fetch failure leaves a pre-existing output file byte-for-byte unchanged.

- [ ] **Step 2: Run the new tests before changing documentation.**

Run: `python3 -m unittest tests.test_paizo2e_source tests.test_paizo2e_packs tests.test_paizo2e_lookup -v`

Expected: PASS.

- [ ] **Step 3: Update the README system table and setup instructions.**

Add PF2e Remaster and SF2e rows, state that generated source datasets are local and not bundled, and show one build and lookup command for each module. Do not describe the data as an official rules distribution or a Foundry replacement.

- [ ] **Step 4: Run repository checks.**

Run:

```bash
python3 -m unittest tests.test_paizo2e_source tests.test_paizo2e_packs tests.test_paizo2e_lookup -v
python3 -m json.tool systems/pf2e/ui.json >/dev/null
python3 -m json.tool systems/sf2e/ui.json >/dev/null
git diff --check
git status --short
```

Expected: all focused tests pass, both manifests parse, no whitespace errors, and no generated dataset appears in status.

- [ ] **Step 5: Run the full suite after installing its existing PyYAML prerequisite.**

Run: `pip3 install pyyaml && pytest -q`

Expected: collection succeeds; investigate any failures before claiming completion. The baseline currently fails at collection because PyYAML is absent.

- [ ] **Step 6: Commit.**

```bash
git add README.md tests/test_paizo2e_source.py tests/test_paizo2e_lookup.py
git commit -m "docs: document Foundry-source system modules"
```

## Plan Self-Review

- Spec coverage: Tasks 1–4 implement GitHub source pinning, pack normalization, local generated data, synchronization, provenance, error retention, and isolated lookup. Tasks 5–6 implement both system modules and UI manifests. Task 7 verifies integration, documents operation, and confirms generated data is not tracked.
- Placeholder scan: no TBD/TODO or deferred implementation steps are present; all paths, commands, data shapes, and expected results are specified.
- Type consistency: both wrappers use `SourceSpec(system, pack_root)`, generated datasets have `_meta.source.sha`, and all lookup paths use the matching system-local output filename.
