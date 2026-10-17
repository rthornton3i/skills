---
name: code-audit
description: How to brief and run a read-only code audit in three ordered passes (lint and hygiene, architecture and scalability, corner cases and bugs), with report format and learned lessons. Use when starting an audit, briefing an auditor, or reviewing an audit report.
---

# Code audit: three passes, in order

User-triggered, after a large task or several closed tasks (not per task; review critic covers that). Read-only: auditor never edits. One slice per call. Orchestrator writes the report to the project's audit-findings file and turns confirmed defects into bug tasks.

## Brief

- Slice (files + tests); passes to run (default all three).
- Known issues not to report (audit plan, `watch-outs.md`).
- Cap: read slice once, run its tests once, ≤~10 throwaway probes.
- Report in the reply, not a file.
- Project's `audit-lessons.md` (in its agent folder `state/`): read first; highest-yield checks first, skip ones marked not paying off. Unique probe filename prefix per auditor.

## Pass 1: lint and hygiene (cheap, first)

Run project linter/type checker if any; else read for:
- Duplicated helpers/constants, copy-pasted blocks.
- Dead code: unused functions, params, imports, unreachable branches.
- Indexing/type pitfalls: positional vs label indexing, negative/wrapped indexes, off-by-one, chained assignment, float equality, integer division.
- Redundant recomputation (fetch inside loop).
- Names/comments/docstrings not matching code; drift from coding skill.

One line each; no deep digging.

## Pass 2: architecture and scalability

Still suited to planned growth (users, data, features, integrations)?
- One fact, several sources (setting in two objects, default in two layers).
- Boundaries: wrong-way imports, cycles, god functions/classes, logic in wrong layer.
- Hidden growth blockers: single user/tenant, one data size, globals, state overwritten per run.
- Extension cost: files changed to add a feature/option/config field (give count).
- Performance shape: bad growth with input size/combinations, repeated I/O, parallel vs shared.
- Docs/diagrams vs real structure.

Report top few risks: growth scenario that breaks each + smallest fix. No rewrites.

## Pass 3: corner cases and bugs (costly, last, use pass 1-2 leads)

Verify by running. Throwaway probes outside repo; run real data if available. Checklist:
- High-stakes paths (money, security, data loss): zero/minimum amounts, rounding, limits crossed in one step, fees/totals, first/last item.
- Sentinels (`inf`, NaN, None, 0) from empty inputs later sorted/averaged as real.
- Boundaries: window shorter than warm-up, 0/1 item, first/last element, empty/single-row input, duplicate/unsorted keys.
- Time-ordered data: truncation check (cut-short input result equals full run up to cut) so nothing uses future data.
- Config/serialization: round-trip every type, two sources for one value, override silently dropping a field, error messages naming wrong thing.
- State: input mutation, sharing between runs/workers, order dependence, pickling.
- Float comparison on amounts (`100*1.1 != 110.0`).
- Tests that can't fail, assertions missing the claim, missing failure-path tests.
- Never write "X is correct" without running the edge case that would break X.

For each bug state materiality: run affected case on real data; unchanged results = cleanup, not bug.

## Report (≤~1,500 words)

`VERDICT: CLEAN | FINDINGS`; findings grouped by pass, ranked by impact. Each: `[bug|risk|cleanup] file:line - what`, evidence (command or traced code), effect on results, fix, confidence (`confirmed` reproduced, `read` traced only, `suspicion`). End: covered, not covered, rough tool calls.

## Lessons (project-local, update every run)

Lessons are project-specific: keep them in the project's `<agent folder>/state/audit-lessons.md`, never in this skill. If missing, create it from the template below. After EVERY audit (mandatory): update it from reports; add bug locations, drop checks that found nothing, record cost. Merge duplicates, delete entries proven wrong. Refine this skill only when a lesson applies to all projects. Keep both short.

```
# Audit lessons
Each entry: what was learned + evidence. Merge duplicates; delete entries proven wrong.
## Where bugs hid
## Checks that paid off
## Checks that did not pay off (skip or shrink)
## Architecture notes (what fits, weak seams)
## Calibration (cost per slice in tokens/time; tips for parallel auditors)
## Review of the implementations (reviews that pay, recurring nits)
```

## Afterwards

- Spot-verify top findings before filing; mark unverified.
- Confirmed result-changing defects → bug tasks first; rest grouped into one risk task and one cleanup task.
- Routine depth (3 passes, standard focus) by default; deep (extra focus, real-data checks) at milestones/before release on high-stakes, config, serialization slices.
