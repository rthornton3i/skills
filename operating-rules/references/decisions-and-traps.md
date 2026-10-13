# Decisions and traps

Decisions hold in every project, with reasons. Procedures live in the named skill. Change a rule by editing its entry (or adding a newer one that states what it supersedes, then deleting old wording); never leave contradictions. A project overrides only via its own `.agent/state/decisions.md` (project file; layout in `project-management` `references/templates.md`).

## Workflow (`agent-workflow`)

- Difficulty and stakes scored separately: difficulty sets focus for planning/implementation, stakes sets review depth.
- Pipeline is for BEHAVIOR and DATA changes. Admin changes (doc wording, memory, skills, tooling, bookkeeping) use admin tier: orchestrator plans AND reviews diff; only implementer is an agent. Why: cost, clarity.
- Optional plan helper only for requests too large/tangled to plan directly (many packages, unclear scope, distinct pieces); breakdown only, once per request. Why: oversized requests start from a sketched architecture without paying on every task.
- Every behavior/data change gets a plan critic unless user waives it for that task (standing waiver: simple tasks on lean path). Why: orchestrator shouldn't skip it alone; cost worry = report and ask.
- Pipeline: optional helper; planner (extra focus on investigation) per task; plan critic (extra focus on challenging choices) once per plan; strict implementer for code, lighter pass for admin; review critic (multiple checks) once per task; orchestrator approval; escalation goes to a higher level. All but implementer run once per task. Why: strong plan challenged once, execution, independent check, without repeating context.
- Documentation is part of the task: planner names affected docs, implementer updates, review critic checks before `PASS`.
- Start every non-trivial request with a task list; use it to confirm all done.

## Token efficiency

- Each orchestrator request re-reads the whole session, so cache reads dominate. So: (1) fewer orchestrator round trips beat smaller files; prefer composite commands; (2) screenshots inflate every later request: render checks go to subagents, orchestrator reads DOM/text; (3) start fresh sessions at task boundaries; (4) delete dead notes, don't park them.
- Lean path: classify up front (`Complexity: simple|high, why`; unsure = high). HIGH (new types/architecture, result-changing logic, data formats/schemas, concurrency, user-flagged) = full pipeline. SIMPLE (renames, output naming, dead code, small hand-checkable fixes) skips planner and plan critic; short orchestrator plan; one implementer; tests + before/after parity; review critic only if a result could change. Merge related simple tasks into one branch/plan/run. Planners capped: plan only, ~300 words, read named files only, no prototypes. After rate-limit cutoff re-run only unfinished checks. Report fresh tokens per task at close.
- Quality first: slower is fine if effort goes to critics and reviews run efficiently (scoped brief, no re-reading unchanged files, no repeated checks, capped report). Report implementer-vs-critic split at task close.
- Audits: routine depth is the default; deeper only on request. One slice per run, three passes (`code-audit`), update `lessons.md` after EVERY run. Spot-verify top findings before filing.

## Git and PRs (`repo-management`)

- Branches reach integration only via user-approved PR; never merge/approve myself. PRs target `dev`, never `main`; promotion to `main` is user's.
- User approves only pushes to `dev`/`main` and PRs. Feature-branch commits/pushes: no confirmation. Force-push, history rewrite, branch deletion: explicit request. Permission layer still blocks a merge/delete = report, don't work around.
- Delete feature branches (local + remote) after PR merge once target contains the work (`git branch -r --merged`, `git cherry`). Delete by explicit name, not piped lists. At each merge and close-out.
- Work only on `feature/<slug>` off `dev`, including small `.agent` bookkeeping; PR after review critic passes. Why: `dev` stays releasable.
- Branch names: `main`, `dev`/named integration branch, `feature/<slug>`. Tool-assigned names get renamed before pushing.

## Memory and notes (`project-management`)

- Memory in the tool's per-project memory folder (e.g. `~/.agent/projects/<slug>/memory/`), outside repo. What must travel with git (manifest, state notes) lives in repo.
- Recompute what can be recomputed; remember what can't. Why: long conversations are main token cost; restart at nearly any point.
- Generic rules = global skills; project facts = project's own skill (`<project>-project`).
- Memory audit after every task, process change, before a fresh session; include cold-start test.
- Lean start-up: memory = `MEMORY.md` + resume note (≤1,800 B, ≤2,600 B, ≤4,400 B combined); rest in `.agent/state/`, found by grep. Skills = short `SKILL.md` + `references/` on demand. Why: start-up reading stays small.
- Cross-project preferences, decisions, traps live in `operating-rules`; project `.agent/state/` keeps only its own.

## Standards (`python-development`, `documentation`)

- Planning vocabulary (task ids, statuses, pipeline stages, `.agent/state` paths) stays in state notes/memory; never skills, code, tests, comments. Known defects in `watch-outs.md`, not code constants. Clean offenders when touched.
- Standards live in skills, not decision logs. Change by editing the skill and adding a line with reason to project decisions.
- Validation: one helper per function, called once near top; several only if checks unrelated, shared, or grouping would hide them.

## Traps

Agents
- Agent definition files, if the project has any, may load only at session start; check the roster before spawning; never swap a weaker check for a missing role without telling user.
- Usage limit can cut off background agents mid-run with no verdict: re-run only unfinished checks; cut-off ≠ finding.
- Never read an agent's `.output` (whole transcript); wait for notification or check size/timestamp.
- Browser tabs are shared with agents: `tabs_context`, use a tab you opened; don't navigate others' tabs while an agent runs.
- Brief every worktree agent on the venv trap below.

Worktrees and venvs
- Worktree agent gets fresh checkout without `.venv` (gitignored). Main `.venv` has package editable-installed pointing at MAIN source, so tests silently run unmodified code. In-file `sys.path.insert` is too late once `conftest.py` imports the package. Fix: set `PYTHONPATH` to worktree package root before python/pytest; confirm via `<package>.__file__`.
- Batch scripts with hard-coded relative `.venv` can't run in a worktree; run the underlying command with the real venv.

Git and PRs
- Stacked PRs strand work: later PR merged into already-merged base never reaches `dev`. Merge base first, retarget next (`gh pr edit N --base dev`), then verify target has the work (`git ls-tree`, `git log`).
- Local `dev` goes stale after GitHub merges: `git fetch origin dev:dev` (ff-only); compare to `origin/dev`.
- `git add -A .agent` can sweep half-finished edits into a bookkeeping commit; stage explicit paths.
- `.agent/project-manifest.json` often shows line-ending-only changes: confirm `git diff -w --stat` empty before discarding; never commit empty diff.

Secrets
- Never read, print, move or write `.env`. Test "no key" paths by removing variables and stubbing the dotenv loader in-process.
- Keys ever committed stay in history; rotation is user's task. Name risk once, don't nag.

Global files and notes
- User-level skills/agents/settings (`~/.agent/`) may not be in git: back up first (`~/.agent/retired/backups/<date>-<topic>/`), edit with file-edit tools, read back.
- Docs builds: clean output folder before any published build, or stale files get republished.
