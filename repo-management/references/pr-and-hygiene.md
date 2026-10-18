# Pull requests, setup, hygiene

## Pull request

Task done (criteria met, verified, critic pass where requested): open PR from feature branch into `dev`, then stop. User reviews and approves. Never approve, merge or auto-merge.

1. Branch clean, up to date with `dev`, project checks pass (tests, docs build, smoke run).
2. Push (pre-authorized), open PR against `dev`.
3. Title short, imperative. Body: what changed; verification evidence (commands, results); critic verdicts and escalations (if any); follow-ups/deferred; what reviewer should scrutinize.
4. `gh pr create --base dev --head feature/<name>`. Always pass `--base dev` (`gh` defaults to repo default, usually `main`); confirm base after. Run `gh auth status` first. Not authenticated = tell user, give compare link instead: `git remote get-url origin`, drop `.git`, append `/compare/dev...feature/<name>`.
5. Wait for review. Changes = new commits on branch. After merge, cut next branch from updated `dev`. Starting next task before approval stacks on unmerged base; get user's explicit okay.

## Fresh environment

Follow README/setup script, then verify:
1. Isolated environment; install project (editable for packages in development).
2. `.env` from `.env.example`; user fills values.
3. Build docs if any; read warnings.
4. Run smoke check or example end to end.

After dependency changes (`pyproject.toml`, `requirements.txt`, `package.json`) reinstall and run project before calling done.

## Hygiene

- Untracked: `.env`, virtual envs, build output, caches (`__pycache__/`), package metadata (`*.egg-info`), machine-specific files, personal editor settings (`.vscode/`).
- Tracked file holding one person's preference: untrack, gitignore, keep local copy.
- Branch model, setup steps or credential handling change = update README/project skill same change.
- Commit on feature branches as work passes gates; never on `dev`/`main`. Prefer new commits over amend. Never skip hooks. No force-push, hard reset or branch deletion without explicit request.
- Before anything discarding uncommitted work (`checkout -- <file>`, `restore`, `reset`, `clean`): `git status`, read `git diff <file>` for exact paths; stash/commit real content. "Line-ending noise" must be confirmed with `git diff -w --stat <file>` (empty) first. After broad `git add`, read `git status` for surprises.
