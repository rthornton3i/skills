# Routines

Routine = named checklist. User says "run startup routine"; do steps in order, one short line per step. Ask only where a step says. Projects add steps in `.agent/state/routines.md` at "project additions". Every routine ends with the resume statement.

## Startup

1. **Context.** Read `project_state.md`; `git status -sb`, `git log -3 --oneline`. Disagreement = trust live state, fix note.
2. **Init check.** Manifest by hand: tools installed, env keys set (by name, never print values), skills and venv exist, memory location right. Manifest `agents.global` roles available; missing = say so, no weaker substitute. Fix only trivial and safe.
3. **Repo and review state.** Branch, uncommitted files, ahead/behind, `gh pr list`, unanswered PR comments (`gh pr view <n> --comments`).
4. **Next steps.** `.agent/state/next-steps.md` "Next step", loose ends in `watch-outs.md`. List open tasks and decisions waiting on user.
5. **Usage check.** usage display against thresholds in memory.
6. **Project additions** ("Startup additions").
7. **Name session.** `date '+%Y-%m-%d %H:%M'`; set session title `YYYY-MM-DD HH:MM - <topic>` if the tool supports titles. No task yet = project name.
8. **Resume statement.** Then wait for direction unless given.

## Close-out

1. Task list current; close finished tasks.
2. Verify: project checks (additions). Report failures as they are.
3. Commit and push task branches per `repo-management` (never `dev`/`main`). Say what stays uncommitted and why.
4. Update notes: `next-steps.md` (done, single next action, what waits on user), `decisions.md` entries with reason, `watch-outs.md`, `restart-kit.md` if tooling changed. Delete superseded text; no appended corrections.
5. Memory audit (`memory-and-audits.md`) incl. cold-start test. Record `Last memory audit: <date>`.
6. Refresh *Live state* in `project_state.md`.
7. Project additions ("Close-out additions").
8. Hand-off: resume statement; recommend fresh session if context long.

## Others

| Routine | Steps |
|---|---|
| Status | `git status -sb`, *Next step*; few lines |
| Checkpoint | Close-out 3, 4, 6 |
| Memory audit | Close-out 5 |
| PR feedback | List open PRs and unanswered comments; fix or reply; summarize changes and what needs user |
| Report bug | Add bug task; run through pipeline like any behavior change |
| Open PR | `repo-management` |
| Usage check | usage display vs thresholds; report, checkpoint if reached |

New routine: generic steps here, project-specific in `.agent/state/routines.md`. One screen; link skills for detail.
