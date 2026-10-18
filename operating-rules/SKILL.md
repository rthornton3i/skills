---
name: operating-rules
description: User's standing preferences, cross-project decisions and known traps for every repository: explaining cost, real vs sample data, mandatory critic review, small changes, token efficiency, approvals, branch rules, where notes live. Use at start of work, before reviewing/closing work, or when unsure how the user wants something done.
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

- **Agent folder** = `.agent/`, or `.claude/` when the project already uses it. Skills write `.agent/`; read it as the project's actual folder.
- **Project specifics stay in the project**: lessons, decisions, traps, rules for one project go in its agent folder (`state/decisions.md` incl. "Standing project rules", `watch-outs.md`, `audit-lessons.md`, `next-steps.md`), never in a skill. No project `operating-rules.md` files.
- **User profile**: fill per user (platform/shell, experience, update style); match explanations to it.
- **Token efficiency without losing quality** (top rule): pay for critics and reviews, not repeated context: scoped briefs, no re-reading unchanged files, one critic run per stage, capped reports. Conflict = keep the check, cut the re-reading. Fresh sessions at natural breaks (after a task, ~35-50% context), not agent caps.
- **Record first**: set task status before working (`agent-workflow`). Classify complexity per task; unsure = high.
- **Independent review mandatory**: every behavior/data change passes a review critic before `done`; self-check is not review. Only no-behavior work may take a logged waiver. Skip critics on mechanical work only with the user's word, asked each time. No retrospective reviews of old work.
- **Small, conservative changes**; agreed process; narrow briefs. Docs are part of the task.
- **Plain language about cost**: analogy tied to the user's numbers; define each term once; end with the practical implication.
- **Real vs sample**: never present invented content as real; default real data, label samples; back claims about code by running it.
- **Git** (`repo-management`): feature branches only, never commit on `dev`/`main`; user approves only pushes to `dev`/`main` and PRs into them; feature-branch commits/pushes need no confirmation; force-push, history rewrite, deleting unmerged work need an explicit request. After merges sync `dev` (`git fetch`, checkout, `pull --ff-only`, reinstall, test); never discard uncommitted work: stash (uniquely tagged), tell user.
- **No planning words in skills/code** (task ids, statuses, state paths): they stay in state notes.
- **Lean notes**: memory = index + resume note; rest in `.agent/state/`, one self-contained bullet each, superseded text deleted (`project-management`).
- **One thread per task**: concluded = resolve; new work gets a new, accurately named thread.
- **Questions**: structured prompts (see Capability check), 2-4 options, recommended first, plus "Get more info first" (= research, re-ask same question; don't decide for user). Never numbered prose.
- **User-level files may not be in git**: back up before changing `~/.agent/`; edit with file-edit tools; read back.

## Read when needed

- Decisions with reasons and known traps (agents, git, worktrees, secrets, notes): `references/decisions-and-traps.md`. Read before changing workflow, roles, branch rules, note layout; before spawning agents, using worktrees, or merging stacked PRs.
- Setting up/auditing a project's `.agent/` folder: `project-management` skill, `references/templates.md`.

## Keeping this true

Add a rule only if user states it as general or it held in more than one project; project-only facts go in that project's `.agent/state/`. Keep each reason; delete what a newer entry supersedes. No project names, task ids or repo paths here.
