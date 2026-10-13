# Memory location, manifest, context length, audits

## Where memory lives

Tool's per-project memory folder, **outside repo**, e.g. `~/.agent/projects/<slug>/memory/` (slug = project path, non-alphanumerics replaced by dashes). Local to machine; loaded at session start if the tool supports it, else read it explicitly.

- Doesn't travel with repo. Anything surviving a new machine or clone (manifest, state notes, skills) belongs in repo. Decisions that matter everywhere: put in project docs too.
- No git noise or exposure: no commits, no conflicts, not readable by repo collaborators.
- Opt-in only if user asks: keep notes in `<repo>/.agent/memory/` instead; notes then sit in git (conflicts, visible to collaborators). Not standard.

## Manifest

`.agent/project-manifest.json` lists all that restarting tooling needs: global/project skills, `agents.global` (optional), environment (venv, setup command, env-file key *names*), tools, branch model. Authoritative restart kit; memory just points to it. Schema: `templates.md`. Update in same change as any skill/env var/tool change.

## Context length

Check context fill with the tool's usage/context display, if any. Adjustable thresholds:
- ~35%: note it; keep checkpoints tight.
- ~50%: at next safe point tell user fresh session is cheaper and safe; give resume statement.
- ~70%: no new tasks; checkpoint; recommend fresh session.

## Memory audit

Checkpoint records what changed; audit checks everything recorded is still true. Run after each task merge, milestone, or process/direction change; before recommending/starting a fresh session; at least every 5 closed tasks.

1. Read all memory files, `MEMORY.md`, `.agent/state/` (via `INDEX.md`).
2. Compare claims to live state: `git status -sb`, manifest, `git branch`/`git log`, `gh pr list`, available agent roles, cited skills/config. Verify every name, path, URL, commit id, command a fresh session would use.
3. Fix/delete stale lines in place (no appended corrections). Merge duplicates. Delete superseded notes, folding lasting reasons into survivor. Keep decisions with reasons. ~One screen per file.
4. Cross-check: *Next step* vs task list, decisions vs skills, every `MEMORY.md` path real, one accurate line per file.
5. Update manifest/restart kit if tools, skills, roles, URLs, commands changed.
6. **Cold-start test**: from `MEMORY.md` + state note alone, can a fresh session say what is done, next, allowed without asking, needs user? Add what's missing.
7. Record `Last memory audit: <date>`; tell user in one line what changed. 
