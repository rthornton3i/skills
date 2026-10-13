# Templates and project `.agent/` layout

Copy, fill, keep short, update in place. Everything below describes a **project's own** files (not skill files).

## New-project checklist

- `.agent/project-manifest.json` (below).
- `.agent/skills/<project>-project/SKILL.md`: setup, layout, repo conventions, short "Documentation specifics" and "Python specifics" (naming/docstring style, config and helper locations, test and docs commands, worktree `PYTHONPATH`). Detail in `references/`.
- Tool permission settings (local, untracked): allow deleting/remote-deleting `feature/*`; deny same for `main`, `dev`; new worktrees branch from current HEAD.
- Local preview commands (app, static docs server): list in the project skill or `restart-kit.md`.
- `.agent/state/` files (below).
- Memory: `MEMORY.md` + `project_state.md` in `~/.agent/projects/<slug>/memory/`.

## `.agent/project-manifest.json`

Everything needed to restart tooling. Names and paths only, no secrets. Check by hand at start-up. Update in same change when a skill, env var or tool is added/removed.

```json
{
  "project": "<repo name>",
  "skills": { "global": ["repo-management", "project-management"], "project": ["<project skill>"] },
  "agents": { "global": ["<role>"] },
  "environment": { "venv": ".venv", "setup": "<setup command>", "env_file": ".env", "env_keys": ["<KEY_NAME>"] },
  "tools": ["git", "python", "gh"],
  "branches": { "stable": "main", "integration": "dev", "current": "<branch>" }
}
```

`agents.global` lists every role the pipeline uses, incl. any critic it needs (e.g. diagram critic).

## `memory/project_state.md` (resume note, ≤2,600 B)

```markdown
---
name: project-state
description: RESUME HERE - current work, next step and open loose ends
metadata:
  type: project
---

## Live state
(branch, ahead/behind, tree state, last commit; refresh by hand with git)

## In flight
Task t12 (export feature) in review, loop 1 of 2. Implementer idle, waiting on review critic.

## Next step
When review critic returns, triage findings; PASS = mark t12 done, start t13.

## Loose ends needing the user
- Rotate old API keys. Run `gh auth login` before first PR.

## Rules in one line
## Where details live
```

Rules: one screen; *Next step* = one concrete action; absolute dates; delete items when done; lasting decisions go to the project's `.agent/state/decisions.md`.

## `MEMORY.md` (index)

No front matter; ≤12 lines, ≤200 chars each, ≤1,800 B. Line 1 = resume note, line 2 = `.agent/state/` + `INDEX.md`, then one line per state file (repo paths in backticks, never right before a closing parenthesis).

```markdown
- [Project state](project_state.md) - RESUME HERE: work in flight, next step, loose ends
- State notes: `.agent/state/INDEX.md` says when to open each file
- [User profile](user_profile.md) - who the user is, background to assume
```

## `.agent/state/` files

| File | Holds | Open when |
|---|---|---|
| `INDEX.md` (~1.4 KB) | one line per file (when to open); grep tip; editing rules | any lookup |
| `decisions.md` | project decisions: bullets; past a few screens, a catalog (heading per subject, one line per entry) with entries in `decisions/<subject>.md` (what, why, how to apply) | changing scope, layout, public names, workflow |
| `next-steps.md` | single next action, queued work, "Pending from the last close-out audit" | starting work, startup |
| `watch-outs.md` | project traps; "Loose ends needing the user" | before touching risky areas |
| `restart-kit.md` | docs URLs, environment, roles, "Gotchas that cost time before" | tool trouble, before publishing |
| `routines.md` | "Startup additions", "Close-out additions", "Project commands worth knowing" | running a routine |
| plan/design files (`plan-<task>.md`, `<task>-design.md`, audit findings) | approved plans/designs until work merges | working that task |

Editing rules: one self-contained bullet per entry (grep hit shows it whole); absolute dates; no secrets; delete superseded text (git keeps history); no project facts copied from a skill. User preferences aren't copied per project (`operating-rules`); a project-only preference file has front matter (`name`, `description`, `metadata.type: feedback|user`) + **Why:** / **How to apply:**.

## Routine additions worth copying

Startup: run tests, report failures before work; `git worktree list` for leftovers; read "Pending from the last close-out audit", tell user what's outstanding.

Close-out, in order; every failure/gap goes to `next-steps.md` ("Pending...") and `watch-outs.md` with exact failing command, never silently fixed:
- Tests; regenerate generated docs (test catalogs, diagrams), run their `--check`.
- Changed diagrams get critic pass or a recorded pending item.
- Clean docs build, warnings as errors; republish docs if guides/diagrams changed.
- Audit, one line each, OK or gap: `git status` clean; branch vs `origin/<branch>` and `origin/dev` (fetch first); `gh pr list --state all --limit 5` vs PRs in notes; no leftover worktrees; open tasks match reality; manifest matches reality; docs URLs resolve; process deviations this session (behavior change without pipeline or review critic) named openly.

## Resume statement

> Resuming <project> at <where>. Last checkpoint <age>. Next step: <one action>. Needs you: <loose ends, or "nothing">.

Fresh session reads only `MEMORY.md` + `project_state.md` (~4 KB), then `git status -sb` and `git log -3 --oneline`.
