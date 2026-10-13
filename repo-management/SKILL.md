---
name: repo-management
description: Defines git operating rules for any project: main/dev/feature branch model, PRs that always target dev, user-approved PRs, push and merge limits, and secrets handling. Use for branching, merging, pushing, pull requests, new-machine setup, API keys, secrets, or what is committed.
---

# Repo management

Generic git rules. `gh` CLI optional: missing or unauthenticated = plain git plus compare link. Project README, instruction file (e.g. `AGENTS.md`) and project skill hold specifics (setup, key names, layout).

## Branch model

main / dev / feature; user approves work before it reaches `dev`.

- **`main`**: stable, last known-good milestone. No direct commits. Advances only when `dev` is promoted.
- **`dev`**: integration, cut from `main`. Receives work only via approved PR.
- **`feature/<name>`**: one per task, cut from `dev`. After gate (criteria met, verified, critic pass where required) open PR into `dev`. Pushing feature branches needs no confirmation, even with open PR (push updates it).
- **Promotion** `dev` → `main`: deliberate milestones, done by the user. Never open a PR against `main` or merge into it.

**Every PR targets `dev`** (`--base dev`) unless user names another base for that PR. No `dev` yet = propose creating from `main`.

## Pushing and merging

`dev` and `main` are shared state. Never push to them; never merge into them except via user-approved PR into `dev`. User approves only pushes to `dev`/`main` (when they merge a PR) and PRs. No confirmation needed for: creating, committing on, pushing feature branches; opening PRs into `dev`; deleting a feature branch I created on `origin` after its PR merged (`feature/*` only). Force-push, history rewrite, deleting any other branch (not mine, or unmerged) need explicit request.

## Branch cleanup

After every merge and at close-out; no confirmation.

- **Delete**: local and remote `feature/*` (and worktree) whose tip is ancestor of `dev` (`git merge-base --is-ancestor <branch> dev`), and branches with closed PRs. Local `git branch -d` (never `-D`); remote `git push origin --delete <name>`; `git fetch --prune`; your own stashes.
- **Keep**: `main`, `dev`/integration branch, checked-out branch, branches with commits `dev` lacks. Unmerged = list for user, never delete.
- Remote refuses (e.g. HTTP 403): don't work around; list merged remote branches in next steps for owner; clean local.
- Report deleted and remaining branches in one line.

## Secrets

- **Never write a real key, token or password into any file**, including `.env`. Hard rule. Ask user to paste it themselves (`notepad .env`); verify presence/format without echoing (non-empty, length, at most first few characters).
- Real values only in gitignored `.env` or platform secret store. `.env.example` = names only. Code reads env.
- User saved real keys in a tracked template: `mv` it to `.env` (never display), recreate template with empty placeholders, confirm `git status` shows template unchanged before commit.
- Ever committed or pushed = compromised: tell user to rotate. History rewrite + force-push is a separate explicit user decision; matters more for public repos.

## Read when needed

- Opening a PR, setup of fresh environment, repo hygiene, commit/amend/reset/discard habits: `references/pr-and-hygiene.md`.
