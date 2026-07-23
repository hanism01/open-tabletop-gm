# open-tabletop-gm — host instructions (Codex / AGENTS.md-based agents)

This repository is an LLM-agnostic tabletop RPG Game Master framework. Under a host
that reads `AGENTS.md` (e.g. the Codex CLI), this file replaces the OpenCode
`instructions` array documented in `README.md`. It is a **pointer**, not the whole
skill: Codex concatenates the `AGENTS.md` chain and caps it at ~32 KiB, so the large
instruction files are read on demand rather than inlined here.

## Load order — do this at the start of every session, before any `/gm` action

1. **Read `SKILL-commands.md` and `SKILL-branches.md`** from the repository root and
   treat them as always-authoritative for the rest of the session. `SKILL-commands.md`
   is the command reference; `SKILL-branches.md` is the branch router that defines
   every procedure. When any `/gm` command or state transition occurs, follow the
   matching branch in `SKILL-branches.md` exactly.
2. **On the first `/gm new` or `/gm load` of a session, also read `SKILL.md`** from the
   repository root — the GM persona and craft. The router and command reference cite
   "SKILL.md → …" throughout and assume it is in context, but nothing loads it for you.
   Read it once per session.
3. **Do NOT read `SKILL-scripts.md`.** It is legacy and superseded. Focused script
   references load on demand from `scripts/*.md` exactly when the router directs.

## Path and runtime contract

- **`<skill-base>`** in the instruction files means the absolute path to THIS
  repository. Resolve it once at session start with `git rev-parse --show-toplevel`
  and substitute it wherever `<skill-base>/…` appears.
- **Run every command from the repository root** so bare relative paths such as
  `scripts/…`, `display/…`, and `systems/…` resolve.
- Scripts invoke **`python3`** (not `python3.12`); ensure `python3` is on `PATH`.
- Campaign data lives under **`$GM_CAMPAIGN_ROOT`** (default `~/open-tabletop-gm`),
  which is **outside** this repository. Codex's default `workspace-write` sandbox
  blocks writes there and blocks network access. See
  [`docs/CODEX-SETUP.md`](docs/CODEX-SETUP.md) for the required sandbox, path, and
  network configuration — campaign saves will silently fail without it.

## `/gm` is not a shell command

`/gm …` is plain text for you to interpret via the router — never run it in a shell,
never treat it as a native slash command. Once a campaign is loaded, all player input
is in-game action and needs no prefix.
