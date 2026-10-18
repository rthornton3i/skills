# Decisions and traps

Rules live in the skill that owns them; this holds the reasons and known traps. Change a rule by editing its entry and deleting old wording; no contradictions. A project overrides only via its own `.agent/state/decisions.md`.

## Reasons (rule -> why)

- **Tiered pipeline** (`agent-workflow`): behavior/data changes get planner + implementer + verification; admin changes skip the planner. Difficulty sets planning focus, stakes set review depth. Why: spend on checks where errors cost.
- **Plan helper** only for oversized requests: a sketched architecture beats paying for exploration on every task.
- **Critics optional, once each**: extra agents cost tokens, so the user opts in; when run, a plan is challenged once and work reviewed once, no repeated context. Orchestrator recommends them for high-complexity/high-stakes tasks, never starts them alone.
- **Cost model**: every orchestrator request re-reads the whole session, so cache reads dominate. So: fewer round trips beat smaller files (prefer composite commands); images inflate every later request (delegate render checks, read DOM/text); fresh sessions at task boundaries; delete dead notes.
- **Feature branches off `dev`, PRs into `dev`**: `dev` stays releasable; user alone promotes to `main`.
- **Delete merged branches** at each merge/close-out: stale branches hide unmerged work. Delete by explicit name, never piped lists.
- **Recompute what can be recomputed, remember what can't**: long conversations are the main token cost; restart at nearly any point.
- **Memory audit** after each task, process change, before a fresh session (include cold-start test): stale notes mislead more than none.
- **Lean start-up** (`MEMORY.md` + resume note small, rest grep-found; short `SKILL.md` + on-demand `references/`): start-up reading stays small.
- **Planning vocabulary** (task ids, statuses, `.agent/state` paths) stays out of skills, code, tests, comments; known defects go in `watch-outs.md`, not code constants.
- **Validation helpers**: one per function, called once near top; several only if checks are unrelated or shared.
- **Audits**: routine depth default, deeper on request; one slice per run; update lessons after every run; spot-verify top findings before filing.

## Traps

Agents
- Agent definition files may load only at session start; check the roster before spawning; never swap a weaker check for a missing role without telling the user.
- Usage limit can cut off background agents with no verdict: re-run only unfinished checks; cut-off is not a finding.
- Never read an agent's raw output transcript; wait for its report or check size/timestamp.
- Browser tabs are shared with agents: use a tab you opened; don't navigate others' tabs while an agent runs.
- Brief every worktree agent on the venv trap below.

Worktrees and venvs
- Worktree has no `.venv` (gitignored). Main `.venv` has the package editable-installed pointing at MAIN source, so tests silently run unmodified code; in-file `sys.path.insert` is too late once `conftest.py` imports the package. Fix: set `PYTHONPATH` to the worktree package root before python/pytest; confirm via `<package>.__file__`.
- Scripts with hard-coded relative `.venv` can't run in a worktree; run the underlying command with the real venv.

Git and PRs
- Stacked PRs strand work: a later PR merged into an already-merged base never reaches `dev`. Merge base first, retarget next (`gh pr edit N --base dev`), then verify the target has the work (`git ls-tree`, `git log`).
- Local `dev` goes stale after remote merges: `git fetch origin dev:dev` (ff-only); compare to `origin/dev`.
- `git add -A .agent` sweeps half-finished edits into bookkeeping commits; stage explicit paths.
- Manifest/files showing line-ending-only changes: confirm `git diff -w --stat` is empty before discarding; never commit an empty diff.
- Permission layer blocks a merge/delete = report, don't work around.

Secrets
- Never read, print, move or write `.env`. Test "no key" paths by removing variables and stubbing the dotenv loader in-process.
- Committed keys stay in history; rotation is the user's task. Name the risk once, don't nag.

Notes and files
- User-level skills/agents/settings may not be in git: back up first (`~/.agent/retired/backups/<topic>/`), edit with file-edit tools, read back.
- Docs builds: clean the output folder before a published build, or stale files get republished.
