# Steps 4-9: verify, review, escalate, close, retire

## 4. Verify before trusting

Agent summary = claim. Read the diff, run criteria commands, check: edits outside scope, "passing" that never ran code, weakened tests, leftover debug. Then move to `review`. Your verification precedes critic, never replaces it.

## 5. Review

Spawn review critic **once per task** after step 4. Fresh agent. Give acceptance criteria and where change lives (branch/diff), *not* implementer's reasoning. Narrow scope: run things, check error-free and criteria met. No plan re-litigation, no rewrites, no praise. If plan named docs affected, critic checks they were updated and match; stale doc = `CHANGES`. Require:

- `PASS` or `CHANGES`
- numbered findings: severity, `file:line`, concrete failure scenario, criterion violated

No scenario = noise; drop. Record review and loop number (`1 / max`).

## 6. Loop

1. **Triage** yourself. Critics err. Accept/reject each with reason; never forward blindly.
2. Send accepted findings to same implementer (message it; keeps context) or fresh one if off track. Bump loop, note findings.
3. Re-verify, re-review changed files only. Delta check: message same critic; clean second opinion: new one. Plan critic never re-runs.
4. **Exit**: `PASS` + green verification = done. `minLoops` hit and still wrong = escalate (7). Same finding twice = brief/approach wrong, re-plan. Budget or ladder exhausted = give user remaining findings.

State goal (criteria met, tests green, no high findings) at loop start.

## Final approval

Light check, not second review. After review `PASS`, before `done`/merge: confirm evidence chain, record `Orchestrator final approval: <why>`. Quick read of plan, plan critic verdict, diff summary, critic's "Checked" list. Gap (failure path never exercised, diff beyond plan) = targeted re-check, not approval.

## 7. Escalate

Set when planning, put in brief:
- `minLoops`: critique rounds before escalation considered (default 2).
- **Ladder**, light to strong: standard strict → extra focus (re-read plan, findings, nearby code; run each criterion) → more capable setup if available.
- Total loop budget (default 6).

**Escalate when** after `minLoops` the review still returns `CHANGES` with high/medium findings showing the task is *incorrect* and findings are not converging (same count/severity, or new defects). Shrinking clearly = one more loop.

**Don't escalate** for: low-severity polish; ambiguous/wrong plan, criteria or brief (re-plan with planner, no new plan critic run); environment blockers; recurring finding caused by unclear relayed feedback. Obvious high-stakes difficulty: start higher.

**How**: running agent can't change setup, so swap.
1. Stop current implementer.
2. Spawn **fresh** implementer at next level with original brief + deduplicated findings (fixed/unfixed) + short note on what was tried and why it fell short. Existing diff is reference to build on or discard. No failed agent reasoning. Template in `briefs.md`.
3. Reset loop counter; record in list: new agent, `escalated A -> B`, why.
4. Review critic stays same emphasis, always fresh.
5. Top level spent or budget gone = escalation summary to user (`briefs.md`).

Later review finds what earlier passed = add checks to review brief for similar tasks.

## 8. Close

`done` needs: criteria met, evidence, review `PASS` (or noted waiver), recorded approval. Skipped a stage? Move back to `review`, say so, run critic. Note outcome in one line. Merge branch per repo rules, then memory audit and checkpoint (`project-management`). **Shared branches are user's call**: never merge a PR into protected branch; confirm other pushes.

## 9. Retire agents

- Stop anything still running, esp. after loop cap or scrapped approach.
- Don't reuse an implementer for an unrelated task; reuse is for a task's own loop. Applies to escalation replacements too.
- Discard worktrees once branch merged or abandoned.
- Mark done in list. Follow-up work = new task, not reopen.
