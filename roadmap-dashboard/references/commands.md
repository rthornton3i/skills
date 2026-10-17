# roadmap.py commands

`RM` = `python <skills-dir>/roadmap-dashboard/scripts/roadmap.py --project .` (`--project DIR` defaults to `.`). Every write prints ONE line `ok <what> [files]`; errors go to stderr with exit 1. Every write revalidates the plan and recomputes `counts`. `RM <command> --help` shows the arguments.

## Read
- `status [--short]`: about 25 lines. Active phases with done/total, open stories with status and agent, the first not-started story per active feature, publish state, token total, git.json age. The publish line is either `unpublished: N status events since <ISO time> (changed files: ...)` or `published <ISO time>, up to date`. `--short`: exactly 3 lines — the header line, one line of open stories as `id status agent name(40)` joined by `; ` (or `open: none`), and a publish line (`publish: up to date` / `publish: changed a, b` / `publish: never published`). Prefer `--short` for routine checks: every orchestrator round trip is expensive.
- `show <story>`: one story with its details.
- `next-ids`: next free s/f/m ids.
- `validate`: unique ids, references, status values, archived phases hold whole phases only, JSON parses, shell files present. Exit 1 on a problem.

## Write (statuses: not-started, planning, plan-review, progress, review, approval, done)
- `start <story> [--agent ID] [--note TXT]` (preferred for the most frequent status change — shorthand for `set-status <story> progress --agent ID --note TXT`; every orchestrator round trip is expensive): same validation and output as `set-status`.
- `set-status <story> <status> [--agent ID] [--critic ID] [--loop "1 / 2"] [--escalated TXT] [--note TXT]`: refuses `done`; appends an event to `ledger/events.jsonl` (the record token attribution uses). The event carries `agent`: `--critic` when the status is plan-review or review, otherwise `--agent` (none if not given; old events are not rewritten). A hint is printed when planning or progress is set without an agent.
- `set-story <story> [--name --agent --critic --loop --escalated --desc --notes]`
- `set-feature <feature> [--points N] [--estTokens N]`: `--points` must be one of the Fibonacci scale 1,2,3,5,8,13,21; `--estTokens` a non-negative integer; an empty string clears a field.
- `add-phase --name N [--id]`; `add-feature --phase P --name N [--id]`; `add-story --feature F --name N [--id] [--desc D] [--criteria "a|b|c"] [--type story|bug]` (`bug` marks a defect fix and shows a BUG chip; `set-story S --type bug|story` changes it later) (refuses features of an archived phase; use `add-feature` or `reopen-phase` first). `add-feature` reopens an archived phase first and prints `(reopened phase P)`; `add-phase` refuses a name starting "Side track" when a Side track phase already exists.
- `reopen-phase <phase>`: move an archived phase, its features and stories back into `plan.json`.
- `rename phase|feature|story <id> <name>`
- `log <story> <text> [--when "Sep 21"]`: default when is today ("Mon D"). For an archived story it appends a row to `archive/story-logs.jsonl`.
- `criterion <story> add <text>` or `criterion <story> done <index>` (index is 1-based).
- `agent-chip <id> --name N --initials II --model a|b|c --label TXT [--role R]`: the chip shown on story cards; there is no roster.
- `event <story> <state> [--note TXT] [--agent ID]`: append an event without changing the story; `--agent` is stored on the event.
- `close-story <story> --outcome TXT [--obe] [--date YYYY-MM-DD]`: status done, `completed` date, the detail record moves to `archive/story-logs.jsonl`, then `sweep`. `--obe` marks it closed without being built (counts as done, shows an OBE chip; say why in the outcome).
- `done <story> --outcome TXT [--agent ID] [--critic ID] [--obe] [--date YYYY-MM-DD] [--log TXT] [--publish]` (preferred for closing a story — replaces the usual `set-story` + `close-story` (+ `refresh` + `publish-args`) sequence in one call; every orchestrator round trip is expensive): sets `--agent`/`--critic` first if given (same validation as `set-story`), appends `--log` before closing, then closes exactly as `close-story`. With `--publish`, also does the work of `refresh` (tokens, git, activity, map, validate) and prints the `publish-args` JSON. Without `--publish`, prints one extra line after the `ok close-story ...` line: `next: <id> <status> <name(48)>` — the next open story, else the first not-started story of the same feature, else `next: none`. Refuses an already-done story.
- `set-outcome <story> TXT`
- `sweep`: each active phase whose stories are all done moves, with its features and stories, to `plan-archive.json`; features never move alone. Prints what moved.

## Tasks (the orchestrator's own list, not the plan; never touched by refresh)
- `tasks-show`: prints the current list, or `no current task list`.
- `tasks-set --file items.json [--title T]`: replaces the current list wholesale. `items.json`: `{"title": optional str, "items": [{"text": str, "status": "pending"|"active"|"done"}, ...]}`.
- `tasks-archive [--title T]`: moves the current list to `tasks-archive-<UTC timestamp>.json`, adds a row to `tasks-index.json`, clears the current list. Refuses an empty current list.

## Derived data
- `tokens`: reads the session transcripts, writes `ledger/runs.jsonl` and `tokens.json` (totals per story, feature, phase; prints totals and a reconcile line). Retention: rows in the old `runs.jsonl` whose `session` has no transcript any more (the desktop app deletes old ones) are kept as they are, so a refresh never drops spend; rows of sessions that still have a transcript are rebuilt from it. `--compare-legacy` compares with the old stamped values.
- `git [--days N] [--max N]`: writes `git.json` schema 2 with branch-graph lanes and the active-branch list with its story and feature links (default window `git_days` in `ledger/config.json`, else 14; commit cap `git_max_commits`, else 150; `git_prs: false` skips the `gh pr list` call); older rows are appended to `archive/git-events.jsonl`.
- `activity [--days N] [--max-recent N]`: writes `activity.json` (default window `activity_days` in `ledger/config.json`, else 30; recent-row cap `activity_max_recent`, else 100).
- `flow [--days N] [--max-events N]`: writes `flow.json` from `ledger/events.jsonl` (and `ledger/runs.jsonl` to name the agent and total its tokens per step) for the Execution flow tab (default window `flow_days` in `ledger/config.json`, else 14; event cap `flow_max_events`, else 250). The `flow` tab in `tabs.json` lists it under `lazy` (new projects get that from the shell copy).
- `map`: scans skills, agents, memory, dashboard and git into `map.json`.
- `refresh`: tokens, git, activity, flow, map, then validate.

## Shell and publish
- `sync-shell [--force]`: copy the shell from the skill into `.claude/roadmap` (`tabs.json` is never overwritten; a locally changed shell file is kept unless `--force`).
- `init`: empty project setup: config, empty plan, `tabs.json`, shell.
- `add-tab --id X --title T --script tab-x.js [--data key=file.json] [--lazy key=file.json] [--lazy-glob "prefix-*.json"]` (the tab's script, data and lazy files are included by `publish-args` and `mark-published`; `--lazy-glob` also includes every matching file already on disk each time, for a data set that grows without editing `tabs.json` — the Tasks tab's archived lists use it)
- `publish-args [--all]`: prints the JSON for the Artifact call: `url`, `file_path`, `files` (changed only; all with `--all` or on a first publish), `changed`, `missing`, and `capabilities` (pass it to the Artifact tool as printed).
- `mark-published [--url URL]`: writes `ledger/published.json` (`{"url","at","files":{name:sha256}}`) and the manifest `artifact_url`. `--url` is optional: omitted, it reuses the url already stored in `ledger/published.json` (error `no stored url: pass --url` if none stored).
- `serve [--port 8765]`: local server that wraps `index.html` like the publisher; open `http://localhost:8765/`.

## Other
- `selftest`: runs every module's selftest in a temp project; prints `selftest ok`.
- `migrate-legacy --html FILE [--force]`, `migrate-legacy --verify`: the one-time migration from the old single-page roadmap (verify prints `verify ok`). `--verify` compares the old page with the plan as it was at migration, so it is only meaningful right after migrating; it reports differences once the plan has moved on.
