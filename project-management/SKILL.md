---
name: project-management
description: Keeps project context saved so a fresh session can resume without long conversations: memory index, resume note, repo manifest, checkpoints and start-up protocol. Use when the user mentions saving context, memory, handoffs, resuming, fresh sessions, or asks for the startup, close-out or any named routine.
---

# Project management: continuity across sessions

Usage display, session titles, auto-loaded memory, task list: use only if present; fallbacks in `operating-rules` capability table.

**Agent folder** = `.agent/`, or `.claude/` when the project already uses it (script autodetects). **Script** `scripts/checkpoint.py` (Python 3, stdlib only), run as `python <this-skill>/scripts/checkpoint.py --project . <cmd>`: `brief`, `snapshot [--write-memory]`, `lookup <keyword>`, `restart-check`, `memory-status`. No Python = use the git/grep equivalents noted below.

Conversation is disposable; project state is not. Long conversations cost most tokens (every step re-sends history). State lives in two places:

| Home | Holds | Travels with |
|---|---|---|
| **Repo** | code, skills, `.agent/state/` notes, restart manifest | repository |
| **Memory** (`~/.agent/projects/<slug>/memory/`, outside repo) | what can't be recomputed: decision reasons, user preferences, resume note | this machine only |

**Recompute what can be recomputed, remember what can't.** Git state comes from git commands. Memory holds reasons, preferences, next step, loose ends. Memory is a claim about the past; verify against live state before trusting.

## Lean layout

Outline: `references/templates.md`.

- `MEMORY.md`: index only, ~12 lines, ≤1,800 B, one pointer per topic with repo path in backticks.
- `project_state.md`: resume note, ≤2,600 B: *Live state* (branch, last commit), *In flight*, *Next step*, *Rules in one line*, *Where details live*.
- Everything else: Markdown in `.agent/state/` (`INDEX.md` says when to open each): decisions, restart kit, next steps, watch-outs, log. One entry per bullet.
- Find detail with `checkpoint.py lookup <keyword>` (or grep `.agent/state/`); never open the whole folder.

Keep out of memory: anything code, git history or a skill already says; secrets; long logs. Use absolute dates, never "yesterday".

## Checkpoint at safe restart points

Safe point = nothing half-done: between tasks, after a commit, after a recorded verdict. Not on a timer.

| Trigger | Action |
|---|---|
| Task changes state | update *In flight*, *Next step*, *Live state* |
| Decision made/agreed | add line to `.agent/state/decisions.md` with reason |
| Commit, merge, PR, branch cut, push | refresh *Live state* |
| Preference or correction | write/update note in `.agent/state/` + `MEMORY.md` pointer now |
| Agent batch starts / finishes | checkpoint before and after |
| Task completes and merges | full checkpoint + memory audit |
| Milestone completes | full checkpoint + audit; tell user it is a natural fresh-session point |
| Process, rules or tooling change | memory audit |
| User stops, switches or starts fresh | full checkpoint first |
| Context passes thresholds | full checkpoint; say so |

Thresholds and audit steps: `references/memory-and-audits.md`.

## Checkpoint procedure

1. Task list current: statuses match reality.
2. Edit *In flight*, *Next step*: concrete, one next action, note ≤2,600 B.
3. `checkpoint.py snapshot --write-memory` refreshes the auto *Live state* block (branch, ahead/behind, tree, last commit). No script: edit it by hand from `git status -sb`, `git log -1 --oneline`.
4. Decisions and preferences: one bullet each in `.agent/state/`; keep `MEMORY.md` pointers in sync (every file listed, every pointer resolves).
5. Uncommitted work: say so; commit only when asked.
6. Resume statement: *"Resuming <project> at <where>. Last checkpoint <age>. Next step: <action>. Needs you: <loose ends>."* Also the session handoff.

## Starting a fresh session

1. New machine: memory empty; rebuild from repo (manifest, `git log`, `.agent/state/`).
2. Read only `MEMORY.md` (auto-loads) and `project_state.md`.
3. `checkpoint.py brief` (no script: `git status -sb`, `git log -3 --oneline`, read *Next step*). **Disagreement = trust live state**, fix note.
4. Give resume statement; continue with *Next step*.
5. More detail only if needed: `checkpoint.py lookup <keyword>` or the one file `MEMORY.md` names. `checkpoint.py restart-check` on tool trouble or new machine (no script: check manifest by hand).
6. Before spawning agents, confirm manifest's `agents.global` roles exist in session; missing = tell user, no weaker substitute.

## Guardrails

- Never write secret values into memory, manifest or snapshot; env keys by name only.
- Don't invent state; every *In flight* claim comes from something just done or verified.
- Keep memory small: replace stale lines, ~one screen per file, tight index. Stale note is worse than none.
- Don't duplicate skills; link.

## Read when needed

- Named routine (startup, close-out, status, checkpoint, memory audit, PR feedback, bug report): `references/routines.md` (projects add steps in `.agent/state/routines.md`).
- Where memory lives, manifest, context length, memory audit (after task/milestone or every 5 closed tasks): `references/memory-and-audits.md`.
- Manifest schema, resume note, state files, new-project checklist, close-out audit: `references/templates.md`.
