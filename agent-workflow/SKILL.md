---
name: agent-workflow
description: Runs tasks with multiple agents (planner, implementer, optional plan critic and review critic) under an orchestrator. Use when planning or running a multi-step task, delegating to subagents, setting up critic loops, or retiring agents.
---

# Agent workflow

Abilities used here (subagents, messaging, stopping, task list, worktrees, compaction) may not exist in this environment: check and use fallbacks in `operating-rules` capability table.

Orchestrator = main session talking to user. Owns plan, briefs, verification, merges. Subagents do bounded tasks, report back. Subagent starts cold, reports what it *intended*, not always what happened.

**Task** = unit of assignment, review, integration: one goal, one branch, one plan, one approval gate. Split big requests into tasks.

## Scope

Pipeline is for **behavior and data changes**: code changing what program does, results, data, secrets, hard-to-reverse state. Admin changes (doc wording, memory, skills, tooling, bookkeeping) use admin tier. Decide tier before planning; note `Tier: full` or `Tier: admin, <reason>`. Unsure = full.

**Docs are part of the task.** Behavior change that makes docs wrong (usage docs, docstrings, config refs, README) updates them in same task. Planner names affected docs, implementer updates, verification (or review critic, if run) checks.

## Record first

Keep one task list (session task tool or checklist in notes). Update it **before** acting, never after.

`planning` → `plan-review`* → `implementing` → `review`* → `approval` → `done`. Never skip to `done`. *Only when the user requested that critic.

| About to… | First record |
|---|---|
| Spawn planner | `planning` |
| Spawn plan critic (if requested) | `plan-review` |
| Spawn/message implementer | `implementing` |
| Spawn review critic (if requested) | `review`, loop `1 / 2` |
| Send findings back (critic or own verification) | `implementing`, loop `2 / 2`, findings |
| Escalate | `implementing`, new agent, `escalated A -> B`, why |
| Final check | `approval` |
| Passed (verified + approval; review `PASS` if run) | `done`, one-line outcome |

- Record verdicts the moment known, before next step (merge, next agent).
- Failed/abandoned action: fix list at once.
- Direct tasks without agents: mark `implementing` first.
- At safe restart points (task closed, commit, verdict) checkpoint memory (`project-management`).
- Tag agent descriptions `[task/role] text`.

## Pipeline

| Stage | Role | Emphasis | Job | Preset (optional) |
|---|---|---|---|---|
| 0 (optional) | plan helper | broad view | Request too large to plan directly: high-level breakdown only (pieces, order, watch-outs). No criteria, no file steps. | `plan-helper-opus-high` |
| 1 Plan | planner | extra focus on investigation, trade-offs | Investigate, choose approach, weigh one alternative. Plan: objective, acceptance criteria, files, ordered steps, out of scope, exact verification. One run. | `planner-opus-medium` |
| 2 Plan critic (optional, on request) | plan critic | extra focus on challenging choices | Devil's advocate: simpler/cheaper/safer path? What is missed? Attacks plan only, not code. **One attempt.** | `plan-critic-opus-high` |
| 3 Implement | implementer | strict execution | Executes plan. No redesign; plan wrong/impossible = stop and report. Admin: lighter pass. | code `implementer-opus-medium`; admin `implementer-sonnet-medium` |
| 4 Review (optional, on request) | review critic | multiple checks: run it, failure paths, before/after, docs | Work error-free and meets criteria. Does not re-litigate plan. | `review-critic-opus-medium` |
| 5 Approval | orchestrator | light evidence check | Approves. No separate agent. | none |
| 6 Audit (optional) | auditor | routine (3 passes) or deep (extra focus on risky slices) | After high-complexity task or several closed tasks. Read-only. Deep only on user request. | routine `code-auditor-opus-medium`; deep `code-auditor-opus-high` |

**Preset** = optional named agent (model tier + effort) for tools that define agents, e.g. Claude Code projects. Use it when the project defines that agent; otherwise follow Role/Emphasis/Job only. Escalation (`references/review-escalate-close.md`) moves the implementer to a stronger model than its preset. A project's own presets override this column.

- **Optional critics**: plan critic and review critic run only when the user explicitly asks (per task, or as a standing project rule). The orchestrator may *recommend* them (one line, with why) when the planner designates the task `high` complexity; it never starts them unasked. Without critics: planner plans, implementer executes, orchestrator verifies (step 4) and approves.
- **Stage 0**: rare. Use when request spans many files/packages, unclear scope, or bundles distinct work. Output goes into planner brief. Once per request; never writes the plan.
- **Cadence**: planner and any critic run once per task.
- **Admin tier**: orchestrator writes plan, light implementer executes, orchestrator reviews diff itself (always) and notes `Orchestrator review: <result>`. Plan only; no prototypes.
- **Complexity**: planner (orchestrator, for simple tasks) classifies once before planning, notes `Complexity: simple|high, why`. HIGH (new types/architecture, result-changing logic, data formats/schemas, concurrency, user-flagged) = ask the user's approval for a planner plan (else a short orchestrator plan), and recommend both critics. SIMPLE (renames, dead code, small hand-checkable fixes, UI-only) = short orchestrator plan, one implementer, tests + before/after parity check. Unsure = high. Never split a high task to dodge the recommendation.
- **Plan critic verdict** (if run): `PLAN OK` or `BETTER PATH` + findings. Better path: revise plan once (edit it or send findings to planner), note why, implement. Never run twice. Fundamentally different approach: orchestrator picks, notes reason.
- **Implementer**: brief = final plan + constraints. Deviations reported, not made.
- **Review critic** (if run): runs things; returns `PASS` or `CHANGES`. Fixes go to implementer.
- **Approval is light.** Confirm chain intact: any requested critic ran once, implementer followed plan or reported deviations, verification (or review `PASS`) has evidence covering risky and failure paths, diff matches plan, no unintended result changes. Re-run code only if evidence has gaps. Gap = targeted re-check or ask user. User approves anything reaching a shared branch.
- **Waiver**: no behavior and no data change (doc wording, comments, formatting, memory bookkeeping) = orchestrator may do directly with noted waiver. Scripts count as behavior. Unsure = pipeline.
- **Roles are setups, not names.** Brief each stage with its emphasis and an independent context. No separate agent for a stage = fresh sub-session with same emphasis. Never swap in a weaker check; tell user.

## Guardrails

- No task starts or changes state before the list shows it.
- Never run plan critic twice on one plan; never start a critic the user didn't request.
- No `done` without verification evidence (admin: orchestrator diff review), recorded approval, and `PASS` from any requested review critic. Implementer's own report is not verification.
- Agents never push, merge, force anything, or write secrets. Say so in every brief.
- Don't spawn for what two tool calls do.
- Unclear brief: fix brief, don't escalate.
- Orchestrator doesn't write behavior-changing code; implementer does, from plan.
- Unverified agent output is never "done".
- **Cheap tests**: implementers run only touched files' tests with quiet runner, read last ~15 lines or failures. Slow set runs once per task, by review critic. No full test output in reports. Say so in briefs.
- Stuck/silent agent: stop, re-brief smaller.
- **Ping quiet agents** (~15 min admin, ~30 min implementer/critic, or user asks): check `git log` on its branch, then message it for three lines: done, doing, blocked. It may just await your reading. Relay in 1-2 lines. One ping per quiet period; no answer = stop, re-brief.

## Token efficiency

Cache reads dominate cost; orchestrator is the largest share.

- Compact/summarize context at natural breaks (task closed, long report absorbed, ~40%); never with a result pending.
- Agent reports ~100 words; findings as bullets with file:line. Fewer, larger launches. No status-only turns; don't paste reports to user.
- One implementer at a time by default; parallel only for disjoint files and docs, and user wants speed.
- Plans name exact files, functions, reusable helpers, fixtures, baselines, docs touched. Agent should not need to explore.
- Plan flags data/rule changes that move baseline results; asks user before implementation.
- Implementer: one full read per touched file, targeted edits and tests, one full fast-suite run and one docs build at end.
- Re-record baselines/regenerate artifacts with the project's script, never by hand.

## Bug reduction

- Failing test first for any reported defect.
- Implementer self-check before handing back: stale docs, reused random seed, edge cases (zero, empty, first/last), unit mismatch, double-counted value, changed results for inputs not using the feature, error state sticking across reruns, stale diagram/guide.
- Critics run before/after check: unchanged results for inputs not using new code.
- Add each new defect class to the self-check list.

## Read when needed

- Deciding agents, planning, briefing, assigning (steps 0-3): `references/setup-steps.md`.
- Verifying, review loop, approval, escalation, closing, retiring (steps 4-9): `references/review-escalate-close.md`.
- Writing a brief or escalation summary: `references/briefs.md`.
