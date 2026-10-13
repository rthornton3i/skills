---
name: operating-rules
description: Owner's standing preferences, cross-project decisions and known traps for every repository: explaining cost, real vs sample data, mandatory critic review, small changes, token efficiency, approvals, branch rules, where notes live. Use at start of work, before reviewing/closing work, or when unsure how the owner wants something done.
---

# Operating rules (all projects)

Rules set once, expected everywhere. Live in this skill; projects keep no operating-rules file. Project notes (`.agent/state/`) add specifics, never contradict these without a recorded decision. Procedures live in other skills; this holds the cross-cutting rules.

## Capability check (do first)

Skills name abilities, not tools. At session start, check which exist in this environment; use the fallback if not. Never assume, never call a missing tool. Say once which fallbacks are active.

| Ability | If missing |
|---|---|
| Structured question prompts (cards) | Short option list in reply: 2-4 options, recommended first, "Get more info first" last; ask one question at a time |
| Subagents / separate agent contexts | One session plays each role in turn; each role starts from a written brief only, ignoring earlier reasoning; critic role re-reads diff fresh |
| Messaging a running agent | Re-brief a fresh agent with findings |
| Stopping agents | Skip; ignore stale output |
| Task list tool | Checklist in project notes (`.agent/state/next-steps.md`) |
| Worktree isolation | Sequential tasks on one branch at a time; never parallel on same files |
| Usage / context display | Estimate by conversation length; checkpoint at natural breaks instead of percentages |
| Context compaction | Write resume note, start fresh session |
| Session titles | Skip |
| Auto-loaded memory / skills | Read `MEMORY.md`, `project_state.md` and needed skill files explicitly at start |
| `gh` CLI | Plain git plus compare link (see `repo-management`) |
| Shell / file-edit tools | Ask user to run commands or paste output |

## Rules

- **Owner profile.** Fill in per user: platform/shell, experience level, how they like updates (length, where read). Match explanations to it.
- **Top rule: token efficiency without losing quality.** Pay for critics and reviews, not repeated context: scoped briefs, no re-reading unchanged files, one critic run per stage, capped reports. Conflict = keep the check, cut the re-reading.
- **Record first.** Set task status in the task list before working (`agent-workflow`).
- **Independent review mandatory.** Self-check is not review. Every behavior/data change passes a review critic before `done`; no skipped stages. Only no-behavior work (doc wording, bookkeeping) may take a logged waiver. Skip critics on mechanical work only with owner's word; ask again next time. No retrospective reviews of old work.
- **Classify complexity per task.** High = full pipeline; simple = lean path; unsure = high.
- **Small, conservative changes**; follow agreed process; narrow agent briefs.
- **Plain language about cost.** Analogy tied to owner's usage numbers; define each term once; short glossary; end with practical implication.
- **Real vs sample.** Never present invented content as real. Default real data; label samples visibly. Back claims about code by running it.
- **Approvals.** Owner approves only pushes to `dev`/`main` and PRs into them. Committing and pushing feature branches: no confirmation. Force-push, history rewrite, deleting unmerged work: explicit request (`repo-management`).
- **Feature branches only**; never commit on `dev`/`main`.
- **No planning words in skills/code.** Task ids, statuses, `.agent/state` paths stay in state notes.
- **Docs are part of the task.**
- **Lean notes.** Memory = index + resume note; rest in repo `.agent/state/`, one self-contained bullet per entry, superseded text deleted (`project-management`).
- **Cost by session length, not agent caps:** fresh sessions at natural breaks (after a task, ~35-50% context).
- **One thread per task.** Task concluded = resolve thread; new work gets a new, accurately named thread.
- **Sync checkout to `dev` after merges:** `git fetch`, checkout `dev`, `git pull --ff-only`, reinstall, test. Never discard uncommitted work: stash (uniquely tagged), tell owner.
- **Questions as structured prompts** (see Capability check), 2-4 options, recommended first, never numbered prose. Each has "Get more info first"; built-in "Other" covers other topics. "Get more info" chosen = research, re-ask same card; don't decide for owner.
- **User-level files may not be in git.** Before changing `~/.agent/`, copy to `~/.agent/retired/backups/<date>-<topic>/`; edit with file-edit tools (no scripts); read back.

## Read when needed

- Decisions with reasons and known traps (agents, git, worktrees, secrets, notes): `references/decisions-and-traps.md`. Read before changing workflow, roles, branch rules, note layout; before spawning agents, using worktrees, or merging stacked PRs.
- Setting up/auditing a project's `.agent/` folder: `project-management` skill, `references/templates.md`.

## Keeping this true

Add a rule only if owner states it as general or it held in more than one project; project-only facts go in that project's `.agent/state/`. Keep each reason; delete what a newer entry supersedes. No project names, task ids or repo paths here.
