# Steps 0-3: decide, plan, brief, assign

## 0. Use agents at all?

Each spawn re-derives context you hold. Behavior tasks always use full pipeline. Small no-behavior tasks with known target: do directly, noted waiver. Extra agents only for independent parallel work or large searches that would flood context. Track task in list either way.

## 1. Plan

1. Split big requests into tasks, each one coherent capability. Plan may have ordered steps.
2. **Acceptance criteria before anyone starts**: concrete, checkable ("`app.py` exits 0 on sample data", not "works"). Same criteria brief implementer, drive critic, define done. Keep with task.
3. Mark dependencies. Independent tasks may run parallel; tasks touching same files run sequentially or in isolated worktrees.
4. Cut task branch from integration branch. Agents never push or merge.
5. **Every task gets one independent review before `done`.** Review critic = fresh agent, once per task, after orchestrator verifies (step 4). Applies even if orchestrator did the work. High-stakes (money, security, data correctness, irreversible) also gets your own independent verification. Only exception: waiver for no-behavior, no-data tasks; note `Review waived: <reason>`. Unsure = review.

## 2. Create and brief

Extra roles: read-only explorer (light, fast) for lookups; light helper for mechanical checks (lint, leftover grep, format). Others per pipeline table.

Agent files, if project defines them, load only at session start; an unquoted `: ` in a description can make one silently fail to load. Quote descriptions; after editing start fresh session and confirm role is listed. Missing = tell user, no weaker substitute.

Name agents by role and number (planner 1, implementer 1...); note holder per task in list.

Brief is self-contained: goal and why, what you learned or ruled out, exact files/lines, criteria, constraints (branch, no push/merge, no secrets, no destructive commands), report shape. Never "based on your findings, fix it": understand first, hand over specific task. Templates: `briefs.md`.

Background runs by default; don't poll or sleep. Foreground only if next step needs result.

## 3. Assign and track

- One task per agent. Same implementer for several tasks only serially, same files.
- Record `implementing` + agent first, then spawn.
- Launch independent tasks in one message.
- **Parallel tasks use isolated worktrees**, one branch each. Worktree may lack untracked tooling (virtualenv): put interpreter path and path variables in brief; implementer confirms imports resolve to its own worktree. Merge one at a time. Before second task's review, its implementer merges integration branch and resolves conflicts (regenerate generated files, don't hand-merge). After merge remove worktree, delete branch.
