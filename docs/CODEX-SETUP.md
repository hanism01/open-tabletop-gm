# Running open-tabletop-gm under the Codex CLI

`README.md` documents OpenCode, the only host with a first-class config slot. This
guide covers running the same framework under the **Codex CLI**, whose instruction
mechanism is `AGENTS.md` rather than an `instructions` array.

The repository root already ships an [`AGENTS.md`](../AGENTS.md). Codex loads it
automatically when you launch from the repo. The steps below cover the two things
`AGENTS.md` cannot configure on its own: the **sandbox** and **environment**.

## Why configuration is required

Codex's default permission preset is `sandbox_mode = "workspace-write"` with
`approval_policy = "on-request"`. Under it:

- **Writes are scoped to the workspace** (the git root and `TMPDIR`). Campaign data
  defaults to `~/open-tabletop-gm/`, which is **outside** the repo — so `/gm save`,
  `/gm new`, and every campaign write are blocked unless you fix the path or grant
  access.
- **Network is off.** `/gm update` (a `git pull`), the Pathfinder/Starfinder
  `build_foundry.py` dataset builds, and URL-based `/gm import` all need network.

Codex also caps the combined `AGENTS.md` instruction chain at `project_doc_max_bytes`
(**32 KiB** default). This is why `AGENTS.md` is a small pointer that tells the agent
to *read* `SKILL-commands.md` and `SKILL-branches.md` (≈39 KiB combined) rather than
inlining them — inlining would truncate the branch router and break the framework.

## 1. Campaign writes — pick one

**Option A (recommended): keep campaign data inside the workspace.** The repo already
git-ignores `campaigns/`, so point the data root there and no sandbox change is needed
for writes:

```bash
export GM_CAMPAIGN_ROOT="$(git -C /path/to/open-tabletop-gm rev-parse --show-toplevel)/campaigns"
```

**Option B: keep the default `~/open-tabletop-gm/` location** and grant the sandbox
write access to it, in `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
writable_roots = ["/Users/you/open-tabletop-gm"]
```

## 2. Network — for updates and dataset builds

Only needed if you use `/gm update`, the pf2e/sf2e Foundry builds, or URL imports. In
`~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
```

Or leave it off and approve those specific commands per-run when Codex prompts.

## 3. Display GM Help button (optional)

The display companion's **◈ GM Help** button shells out to a model CLI. Codex is not
auto-detected, so set the escape hatch in your shell before launching the display:

```bash
export OTGM_HINT_CMD='codex exec -'
```

The `-` makes Codex read the prompt from stdin, which is how `dm_help.py` passes it.
`codex exec` prints only the final message to stdout and streams progress to stderr,
which matches what the button expects. If hints hang, it is a known non-TTY-pipe
issue — fall back to `OTGM_HINT_CMD='claude -p'` or `'llm -m <model>'`.

## 4. Launch and verify

Launch Codex from the repository root so `AGENTS.md` loads and relative paths resolve:

```bash
cd /path/to/open-tabletop-gm
codex
```

Then confirm the port end to end:

1. `/gm new smoketest` — a campaign directory is written under `$GM_CAMPAIGN_ROOT`.
2. `/gm roll d20` — `scripts/dice.py` runs and returns a result.
3. `/gm load smoketest` — the seven-step load branch runs and opening narration prints.

If step 1 produces no files, the sandbox is still blocking writes — recheck section 1.
If a script errors with a path not found, you launched Codex outside the repo root —
`cd` in and relaunch.

## What is NOT needed

- **Raising `project_doc_max_bytes`.** Only required if you insist on inlining the
  instruction files into `AGENTS.md`, which the pointer approach deliberately avoids.
- **A custom slash command.** `/gm` is interpreted text, never registered with the host.
