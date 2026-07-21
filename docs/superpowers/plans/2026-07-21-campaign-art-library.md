# Campaign Art Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the GM LLM a DeviantArt-first, campaign-scoped workflow to find, save, recall, and display credited reference art without using GenAI or copying third-party artwork.

**Architecture:** A stdlib-only `scripts/art.py` command manages one `art.json` per campaign and searches DuckDuckGo Lite, defaulting to a `site:deviantart.com` query. The display server holds only the current ephemeral art payload, broadcasts it through its existing SSE stream, and replays it on reconnect; the browser renders it in a dismissible, responsive panel. The command never downloads or rehosts artwork: it saves remote URLs and provenance only.

**Tech Stack:** Python 3.12 stdlib (`argparse`, `html.parser`, `urllib`, `json`, `ipaddress`), Flask/SSE, existing vanilla HTML/CSS/JavaScript display client, pytest/unittest.

**Spec:** `docs/superpowers/specs/2026-07-21-campaign-art-library-design.md` — the authority when this plan is ambiguous.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/art.py` | Validates public remote URLs, builds/parses capped DuckDuckGo Lite searches, and owns campaign `art.json` CRUD plus the GM-facing CLI. |
| `display/gm-display-app.py` | Authenticated `/art` state update, SSE broadcast, and reconnect replay for one active image. |
| `display/templates/index.html` | Safe DOM rendering, responsive styles, dismissal, alt/caption/source presentation, and broken-image fallback. |
| `tests/test_art.py` | Deterministic tests for query construction, parsing, validation, persistence, and CLI behavior. |
| `tests/test_art_display.py` | Flask auth/state/SSE tests for the display event. |
| `SKILL-commands.md`, `SKILL-scripts.md` | The LLM-facing command contract and usage examples. |

## Global Constraints

- No GenAI, upload, image generation, automatic download, proxy, cache, or rehosting.
- Default search source is DeviantArt. `--source web` is an explicit broad-search escape hatch.
- Search has a five-result cap, 8-second timeout, user-agent, and clear no-results/error output. Cache only the short-lived candidate list needed by the immediately following `save --candidate`; never cache image bytes.
- Accept only `https` public URLs for image/source fields: reject credentials, localhost, loopback, link-local, private, multicast, unspecified, and reserved IP literals. Reject redirect chains to unsafe URLs whenever the search metadata resolver follows a redirect.
- Preserve `source_url` and any discovered creator/attribution text. Render the source as a link, not hidden metadata.
- `art.json` uses atomic `*.tmp` + `os.replace` writes, the same durability pattern used elsewhere in the display.
- Keep active display art separate from campaign lore and from `art.json`; `hide` only clears display state.

### Task 1: Build the Art Data and Search Library

**Files:**
- Create: `scripts/art.py`
- Create: `tests/test_art.py`

- [ ] **Step 1: Write failing tests for the immutable data contract and search query construction.**

```python
def test_default_query_is_deviantart_restricted():
    assert art.build_search_query("blackwater keep") == (
        "blackwater keep site:deviantart.com"
    )

def test_web_source_does_not_add_domain_restriction():
    assert art.build_search_query("blackwater keep", source="web") == "blackwater keep"

def test_normalize_candidate_keeps_provenance_and_public_https_urls():
    result = art.normalize_candidate({
        "title": "Keep by Artist", "image_url": "https://images.example/keep.jpg",
        "thumbnail_url": "https://images.example/keep-small.jpg",
        "source_url": "https://www.deviantart.com/artist/art/keep",
        "creator": "Artist",
    })
    assert result["source_host"] == "www.deviantart.com"
    assert result["creator"] == "Artist"

def test_private_or_http_image_url_is_rejected():
    for url in ("http://example.com/a.jpg", "https://127.0.0.1/a.jpg",
                "https://localhost/a.jpg", "https://10.0.0.1/a.jpg"):
        with pytest.raises(art.ArtValidationError):
            art.validate_public_https_url(url)
```

- [ ] **Step 2: Run the focused test file to prove the library does not exist.**

Run: `python -m pytest tests/test_art.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'art'` or missing symbols.

- [ ] **Step 3: Implement the minimal pure helpers in `scripts/art.py`.**

```python
ART_KINDS = {"place", "npc", "creature"}
SEARCH_SOURCES = {"deviantart", "web"}
MAX_RESULTS = 5

def build_search_query(query: str, source: str = "deviantart") -> str:
    clean = " ".join(query.split())
    if not clean or source not in SEARCH_SOURCES:
        raise ArtValidationError("query and source are required")
    return clean + " site:deviantart.com" if source == "deviantart" else clean

def validate_public_https_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ArtValidationError("URL must be public HTTPS")
    host = parsed.hostname or ""
    if host.lower() == "localhost":
        raise ArtValidationError("URL host is not public")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ArtValidationError("URL host is not public")
    except ValueError:
        pass
    return urllib.parse.urlunsplit(parsed)
```

Implement a small `HTMLParser` that extracts result anchors and `<img>` fields from the Lite response, normalizes at most `MAX_RESULTS`, and uses canonical result links as `source_url`. If the Lite markup lacks an image URL, return the result with `thumbnail_url: ""` and `image_url: ""`; do not fetch the artwork or source page in this task.

- [ ] **Step 4: Run the focused tests.**

Run: `python -m pytest tests/test_art.py -q`

Expected: PASS for query, validation, and parser-normalization cases.

- [ ] **Step 5: Commit the isolated helper layer.**

```bash
git add scripts/art.py tests/test_art.py
git commit -m "feat: add campaign art search helpers"
```

### Task 2: Add Campaign-Owned Art Persistence and CRUD

**Files:**
- Modify: `scripts/art.py`
- Modify: `tests/test_art.py`

- [ ] **Step 1: Add failing persistence tests using a temporary campaign root.**

```python
def test_save_and_find_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("GM_CAMPAIGN_ROOT", str(tmp_path))
    record = art.save_record("ashfall", {
        "id": "blackwater-keep", "title": "Blackwater Keep", "aliases": ["keep"],
        "kind": "place", "tags": ["ruin"],
        "image_url": "https://images.example/keep.jpg", "thumbnail_url": "",
        "source_url": "https://www.deviantart.com/a/art/keep", "creator": "A",
    })
    assert record["id"] == "blackwater-keep"
    assert art.find_records("ashfall", "keep")[0]["id"] == "blackwater-keep"
    assert (tmp_path / "campaigns" / "ashfall" / "art.json").exists()

def test_save_rejects_duplicate_id_and_invalid_kind(monkeypatch, tmp_path):
    monkeypatch.setenv("GM_CAMPAIGN_ROOT", str(tmp_path))
    with pytest.raises(art.ArtValidationError):
        art.save_record("ashfall", {"id": "x", "kind": "pc"})
```

- [ ] **Step 2: Run the persistence cases to verify failure.**

Run: `python -m pytest tests/test_art.py -q -k 'save or find'`

Expected: FAIL because `save_record` and `find_records` are undefined.

- [ ] **Step 3: Implement an atomic `art.json` store and record schema.**

```python
def art_path(campaign: str) -> pathlib.Path:
    return paths.find_campaign(campaign) / "art.json"

def save_records(path: pathlib.Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": 1, "records": records}, indent=2) + "\n")
    os.replace(tmp, path)
```

Validate IDs as lower-case slugs, cap title/alias/tag/note lengths, require a valid kind and valid public HTTPS `image_url`/`source_url` when supplied, then add `saved_at` and `source_host`. Implement `save_record`, `find_records`, `list_records`, `update_record`, and `delete_record`; query across ID, title, aliases, kind, and tags case-insensitively. Never delete image bytes because none are stored.

- [ ] **Step 4: Expand and run CRUD/atomic-write tests.**

Run: `python -m pytest tests/test_art.py -q`

Expected: PASS, including duplicate rejection, update/delete, alias recall, and no remaining `.tmp` file.

- [ ] **Step 5: Commit persistence.**

```bash
git add scripts/art.py tests/test_art.py
git commit -m "feat: persist campaign art records"
```

### Task 3: Expose the GM LLM Command Workflow

**Files:**
- Modify: `scripts/art.py`
- Modify: `tests/test_art.py`

- [ ] **Step 1: Write CLI contract tests.**

```python
def test_search_defaults_to_deviantart(monkeypatch, capsys):
    monkeypatch.setattr(art, "fetch_lite_html", lambda query: FIXTURE_HTML)
    assert art.main(["search", "--query", "blackwater keep"]) == 0
    assert "site:deviantart.com" in capsys.readouterr().out

def test_save_candidate_requires_a_search_cache(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GM_CAMPAIGN_ROOT", str(tmp_path))
    assert art.main(["save", "--campaign", "ashfall", "--candidate", "1",
                     "--as", "keep", "--kind", "place"]) == 2
    assert "run art search first" in capsys.readouterr().err
```

- [ ] **Step 2: Run the CLI tests to verify failure.**

Run: `python -m pytest tests/test_art.py -q -k 'defaults or candidate'`

Expected: FAIL because `main(argv)` and the candidate cache contract are absent.

- [ ] **Step 3: Implement argparse subcommands and a bounded candidate cache.**

```text
python3 scripts/art.py search --campaign ashfall --query "Blackwater Keep" [--source deviantart|web]
python3 scripts/art.py save --campaign ashfall --candidate 1 --as blackwater-keep --kind place [--tags ruin,coast]
python3 scripts/art.py find --campaign ashfall --query keep
python3 scripts/art.py list --campaign ashfall [--kind npc]
python3 scripts/art.py update --campaign ashfall --id blackwater-keep --title "Blackwater Keep"
python3 scripts/art.py delete --campaign ashfall --id blackwater-keep
python3 scripts/art.py show --campaign ashfall --id blackwater-keep
python3 scripts/art.py show --url https://... --source-url https://... --title "Storm Coast"
python3 scripts/art.py hide
```

Persist normalized candidates in `campaign/.art_search_cache.json` with `created_at`; accept them for ten minutes only, and delete the cache after a successful `save --candidate`. Output candidate lists as compact JSON so the LLM can select an ordinal deterministically. `show` and `hide` will call the authenticated display endpoint introduced in Task 4; until then, isolate that POST behind `post_display_art(payload)` so it can be mocked.

- [ ] **Step 4: Run the complete art CLI suite.**

Run: `python -m pytest tests/test_art.py -q`

Expected: PASS; malformed commands return exit code 2 and never create an art record.

- [ ] **Step 5: Commit the CLI.**

```bash
git add scripts/art.py tests/test_art.py
git commit -m "feat: add LLM campaign art commands"
```

### Task 4: Add Authenticated Active-Art SSE State

**Files:**
- Modify: `display/gm-display-app.py`
- Create: `tests/test_art_display.py`

- [ ] **Step 1: Write failing Flask tests for GM-only art changes and reconnect replay.**

```python
def test_art_update_requires_gm_secret(app_module):
    response = app_module.app.test_client().post("/art", json={"action": "show"})
    assert response.status_code == 403

def test_show_then_stream_replays_active_art(app_module):
    client = app_module.app.test_client()
    response = client.post("/art", headers={"X-GM-Secret": "test-gm-secret"}, json={
        "action": "show", "title": "Blackwater Keep",
        "image_url": "https://images.example/keep.jpg",
        "source_url": "https://www.deviantart.com/a/art/keep", "alt": "Stone keep",
    })
    assert response.status_code == 204
    stream = client.get("/stream", buffered=False)
    assert b'"art"' in next(stream.response)
```

- [ ] **Step 2: Run the display tests to verify failure.**

Run: `python -m pytest tests/test_art_display.py -q`

Expected: FAIL with `404` for `/art` or no `art` replay payload.

- [ ] **Step 3: Implement current-art state, validation, and the `/art` endpoint.**

```python
_active_art: dict | None = None
_active_art_lock = threading.Lock()

@app.route("/art", methods=["POST"])
def art():
    data = request.get_json(silent=True) or {}
    if data.get("action") == "hide":
        with _active_art_lock:
            global _active_art
            _active_art = None
        _broadcast({"art": None})
        return "", 204
    payload = _validate_art_payload(data)
    with _active_art_lock:
        _active_art = payload
    _broadcast({"art": payload})
    return "", 204
```

Add `art` to `_GM_ENDPOINTS`, validate the same public-HTTPS policy server-side (duplicate the small validator locally rather than importing a CLI module), cap all strings, and avoid rendering HTML from payload values. During `/stream`, enqueue `{"art": dict(_active_art)}` when active after the stats replay. The endpoint retains no image bytes and is only reachable to existing GM-secret callers.

- [ ] **Step 4: Run focused and existing auth/broadcast tests.**

Run: `python -m pytest tests/test_art_display.py tests/test_auth_gate.py tests/test_broadcast_to.py -q`

Expected: PASS; player and unauthenticated requests remain 403, GM requests show/hide, reconnect gets the latest state.

- [ ] **Step 5: Commit display state.**

```bash
git add display/gm-display-app.py tests/test_art_display.py
git commit -m "feat: broadcast active campaign art"
```

### Task 5: Render Art Safely and Responsively in the Display Client

**Files:**
- Modify: `display/templates/index.html`
- Modify: `tests/test_art_display.py`

- [ ] **Step 1: Add static-contract tests before editing the page.**

```python
def test_client_has_safe_art_renderer_and_no_innerhtml_url_sink():
    html = (REPO / "display" / "templates" / "index.html").read_text()
    assert "function renderArt(payload)" in html
    assert "artImage.src = payload.image_url" in html
    assert "#art-panel" in html
    assert "art-panel" not in re.findall(r"innerHTML\\s*=.*", html)
```

- [ ] **Step 2: Run the static test to verify failure.**

Run: `python -m pytest tests/test_art_display.py -q -k renderer`

Expected: FAIL because `renderArt` and `#art-panel` do not yet exist.

- [ ] **Step 3: Add an accessible panel and DOM-only renderer.**

```html
<aside id="art-panel" aria-live="polite" hidden>
  <button id="art-close" type="button" aria-label="Hide artwork">×</button>
  <img id="art-image" alt="">
  <p id="art-caption"></p>
  <a id="art-source" target="_blank" rel="noopener noreferrer">View source</a>
  <p id="art-error" hidden>Artwork could not be loaded.</p>
</aside>
```

```javascript
function renderArt(payload) {
  artPanel.hidden = !payload;
  if (!payload) return;
  artImage.alt = payload.alt || payload.title;
  artImage.src = payload.image_url;
  artCaption.textContent = payload.title;
  artSource.href = payload.source_url;
  artSource.hidden = !payload.source_url;
  artError.hidden = true;
}
```

In the existing `evtSource.onmessage` handler, invoke `renderArt(payload.art)` whenever the `art` key is present (including `null`). Use CSS so desktop art occupies a bounded panel above existing controls and phone art becomes a compact drawer; it must not be `position: fixed` over the action textarea. Set an image `error` listener that hides the image and reveals `#art-error`; the close button locally hides the panel without altering server state.

- [ ] **Step 4: Run the static/client tests.**

Run: `python -m pytest tests/test_art_display.py -q`

Expected: PASS; the renderer uses `textContent` and property assignment, not untrusted HTML interpolation.

- [ ] **Step 5: Commit the client.**

```bash
git add display/templates/index.html tests/test_art_display.py
git commit -m "feat: render campaign art in display"
```

### Task 6: Document the LLM Contract and End-to-End Behavior

**Files:**
- Modify: `SKILL-commands.md`
- Modify: `SKILL-scripts.md`
- Modify: `display/README.md`

- [ ] **Step 1: Add the exact GM-facing command examples and policy.**

```markdown
When a recurring place, NPC, or creature would benefit from a visual reference:

python3 scripts/art.py search --campaign <campaign> --query "<subject>"
# DeviantArt-first; add --source web only for broader results.
python3 scripts/art.py save --campaign <campaign> --candidate <n> --as <id> --kind place|npc|creature
python3 scripts/art.py show --campaign <campaign> --id <id>

Never generate art, download it, rehost it, or omit its source URL. Use `art hide` when
the image no longer serves the scene.
```

- [ ] **Step 2: Document operational behavior in the display README.**

Describe the one-active-image model, reconnect replay, source-caption link, broken-image fallback, campaign-local `art.json`, and no-GenAI/no-copying policy.

- [ ] **Step 3: Verify documentation references.**

Run: `rg -n "art search|source deviantart|GenAI|art.json" SKILL-commands.md SKILL-scripts.md display/README.md`

Expected: each policy and command is discoverable; no document says that a human uses a search console.

- [ ] **Step 4: Commit documentation.**

```bash
git add SKILL-commands.md SKILL-scripts.md display/README.md
git commit -m "docs: describe campaign art workflow"
```

### Task 7: Run the Full Regression Suite and Review the Security Boundaries

**Files:**
- Modify: `tests/test_art.py` only if an uncovered branch is discovered
- Modify: `tests/test_art_display.py` only if an uncovered branch is discovered

- [ ] **Step 1: Run all art and display tests.**

Run: `python -m pytest tests/test_art.py tests/test_art_display.py tests/test_display_robustness.py tests/test_auth_gate.py tests/test_broadcast_to.py -q`

Expected: PASS.

- [ ] **Step 2: Run the complete repository test suite.**

Run: `python -m pytest tests -q`

Expected: PASS with no collection errors.

- [ ] **Step 3: Manually verify no prohibited scope leaked in.**

Run:

```bash
rg -n "openai|imagegen|generate image|requests\.get|urlretrieve|shutil\.copyfile" scripts/art.py display/gm-display-app.py
git diff HEAD~7..HEAD -- scripts/art.py display/gm-display-app.py display/templates/index.html
```

Expected: no GenAI client, no artwork download/rehosting path, no unsafe server-side image fetch, and no new dependency.

- [ ] **Step 4: Commit any final test-only corrections.**

```bash
git add tests/test_art.py tests/test_art_display.py
git commit -m "test: cover campaign art edge cases"
```

Only create this commit when Step 1 or Step 2 added a necessary test correction; otherwise leave the worktree clean.

## Plan Self-Review

- **Spec coverage:** Tasks 1 and 3 implement DeviantArt-first DuckDuckGo Lite discovery; Task 2 implements campaign-local place/NPC/creature records; Tasks 4–5 implement authenticated active-art SSE, reconnect replay, source caption, responsive display, and failure state; Task 6 documents the LLM workflow; Task 7 covers regression and the no-GenAI/no-rehosting boundaries.
- **Placeholder scan:** No TBD/TODO items, implicit validation steps, or undefined interface names remain. `post_display_art`, `save_record`, `find_records`, and `_validate_art_payload` are introduced in the tasks where they are first needed.
- **Type consistency:** `art.json` records use `image_url`, `thumbnail_url`, `source_url`, `creator`, `source_host`, and `kind` consistently; SSE uses the `art` payload key and `null` for hide across server and client.
