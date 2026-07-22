# Project: open-tabletop-gm (ttrpg_skill)

TTRPG game-master tool: an LLM runs the game. Python 3.12 / Flask + SSE backend
(`display/`), vanilla JS/CSS/HTML front end (no React, no build step), pytest.
System modules live in `systems/` (dnd5e, pf2e, sf2e, paizo2e, brp). Version in
`VERSION`.

## Source control: GitHub, NOT Gitea

This repo is hosted on **GitHub**. Use the **`gh`** CLI for all forge operations
(issues, PRs, releases). Do **NOT** use `tea` here — the global/workspace rule
about `tea` (Gitea CLI) does not apply to this project.

### Remotes
- `origin` → `https://github.com/hanism01/open-tabletop-gm.git` — **your fork** (push here).
- `upstream` → `https://github.com/Bobby-Gray/open-tabletop-gm` — the original you forked from. Do **not** push to it.

### Push safety
- `main` tracks `origin/main`. A bare `git push` from `main` goes to your fork. Never push `main` to `upstream`.
- **`gh`'s default repo is set to your fork** (`hanism01/open-tabletop-gm`) via `gh repo set-default` — separate from git branch tracking. But **your fork has issues disabled**, so the project's issues and PRs live on **upstream**. To view/triage them: `gh issue list -R Bobby-Gray/open-tabletop-gm` / `gh pr list -R Bobby-Gray/open-tabletop-gm`.

## Workflow

- Feature work uses git worktrees under `.worktrees/` (one dir per branch, shared `.git`).
- Commit without asking; never push to remote without explicit instruction.
- TDD is mandatory. Verify after edits: `python3 -m pytest tests -q`.
