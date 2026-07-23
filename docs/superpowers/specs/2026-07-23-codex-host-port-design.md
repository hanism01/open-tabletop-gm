# Design: Codex CLI host port

**Date:** 2026-07-23
**Status:** Approved, implemented
**Scope:** Let the framework run under the Codex CLI, whose instruction mechanism is
`AGENTS.md`, without touching the OpenCode-facing files.

## Problem

`README.md` documents only OpenCode, which loads instruction files via an
`instructions` array in `opencode.json`. Codex has no such array — it reads `AGENTS.md`.
Porting is not "copy the config"; Codex's loading model and sandbox impose constraints
the OpenCode path never surfaced.

## Findings that shaped the design (verified against Codex docs, 2026-07)

1. **32 KiB instruction cap.** Codex concatenates the global `~/.codex/AGENTS.md` plus
   every `AGENTS.md` from git root to cwd, root-first, and hard-stops at
   `project_doc_max_bytes` (default 32768 B). `SKILL-commands.md` (23,680 B) +
   `SKILL-branches.md` (15,382 B) = 39,062 B. Inlining both into one `AGENTS.md`
   overflows the cap and truncates the second file, silently gutting the branch router.
   → **Decision: pointer `AGENTS.md`, not inlined.** The files are read on demand.
   Context drift (the usual reason to prefer inlining) is a non-issue on Codex's
   GPT-5-class models.

2. **`<skill-base>` has no runtime resolution.** The definition lived in the now-legacy
   `SKILL-scripts.md`. The standing files use `<skill-base>/…` with no rule for
   resolving it. → **Decision: `AGENTS.md` resolves it via `git rev-parse
   --show-toplevel` at session start.**

3. **`SKILL.md` is never explicitly loaded.** The router and command reference cite
   "SKILL.md → …" but no branch reads it; under OpenCode it is read "on first session
   load" by convention. → **Decision: `AGENTS.md` explicitly instructs reading `SKILL.md`
   on the first `/gm new` or `/gm load` of a session.**

4. **Mixed path bases.** Some commands use `<skill-base>/scripts/…`, others bare
   `scripts/`, `display/`, `systems/`. → **Decision: `AGENTS.md` mandates launching from
   the repo root.**

5. **Sandbox blocks campaign writes.** Default `workspace-write` scopes writes to the
   workspace. Campaign data defaults to `~/open-tabletop-gm/`, outside the repo. →
   **Decision: document two fixes** — set `GM_CAMPAIGN_ROOT` to `<repo>/campaigns`
   (already git-ignored) or add the campaign root to `sandbox_workspace_write.writable_roots`.

6. **Network off by default.** `/gm update`, `build_foundry.py`, and URL imports need
   network. → **Decision: document `network_access = true` as opt-in.**

7. **GM Help hint CLI.** `dm_help.py` auto-detects `claude, opencode, gemini, llm` — not
   Codex. It passes the prompt on stdin. → **Decision: document
   `OTGM_HINT_CMD='codex exec -'`**, where `-` routes stdin to the prompt. Note the known
   non-TTY-pipe hang and a fallback.

8. **`python3`, not `python3.12`.** Every script call uses `python3`. → Documented as a
   PATH requirement.

## Deliverables

- `AGENTS.md` (repo root) — pointer: load order, `<skill-base>` resolution, `SKILL.md`
  first-load, repo-root cwd rule, `/gm`-is-text rule, path to setup doc.
- `docs/CODEX-SETUP.md` — sandbox, path, network, GM Help config, launch/verify steps.
- This spec.

## Out of scope

- Raising `project_doc_max_bytes` (only needed for the rejected inline approach).
- Codex-specific changes to any `SKILL*.md` or Python — the core stays host-neutral.
- Registering a native `/gm` command (impossible and unnecessary — it is interpreted text).
