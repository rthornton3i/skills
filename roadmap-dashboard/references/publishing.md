# Publishing the dashboard

Published files (flat names, nothing else): `index.html` (small stub) plus `styles.css app.js tabs.json tab-plan.js tab-flow.js tab-map.js tab-git.js plan.json tokens.json plan-archive.json map.json git.json flow.json` (plus the script, data and lazy files of every tab in `tabs.json`, which `publish-args` adds by itself).

## Page features
The header shows `Updated <time>` (the newest data `generated` value), a `Reload` button (refetches every data file with no-cache and re-mounts the active tab; free, no publish) and an `Ask Claude to update` button. That button uses the `comments` capability (`sendToClaude`); it is enabled only when `canSendToClaude()` is `available`, meaning a Claude session is watching the artifact, and is otherwise disabled with the reason shown. The publish call declares `capabilities: {"comments": {}}`; consent is asked once at first use, and the artifact is then organization-internal, not publicly shareable.

## Publish policy
`plan.json` is updated locally at EVERY status change (`RM set-status`, about 100 tokens). The published page is republished only (i) when the owner asks, in chat or through the "Ask Claude to update" button, and (ii) at a wrap-up: a feature finished, a checkpoint (commit or push), or before a session ends. Not on every stage transition.

## First publish
1. `RM refresh`, then `RM publish-args --all`.
2. ONE Artifact call: `file_path` = the printed `file_path`, `icon: "roadmap"`, a one-sentence `description`, `capabilities` as printed, no `url`, `files` = the printed map.
3. Open the result, check it renders, then `RM mark-published --url URL`.

## Later publish
1. `RM refresh`, then `RM publish-args` (changed files only).
2. `Artifact read url` (the small stub; satisfies read-before-publish) and `Artifact list scope:files url` (listed files may be replaced).
3. ONE Artifact publish with `url`, `file_path`, `files` and `capabilities` exactly as printed.
   A publish to an existing URL is refused until the live version was read in this session (step 2's `Artifact read`); if it is refused with that reason, read it and publish again unchanged. That is not a reason to pass `overwrite_unread`: changed data files you published earlier in the session, or listed in step 2, are replaceable without it. A `null` file value removes a stale published file.
4. `RM mark-published --url URL`.

## Comment request ("Ask Claude to update")
The request arrives as an artifact comment sent to Claude. Run `RM refresh`, `RM publish-args`, ONE Artifact publish with exactly the printed arguments, `RM mark-published --url URL`, then answer in the comment thread with one line.

## If the tool refuses a data file
If the tool refuses to replace a listed-only data file, stop and report. Never pass `overwrite_unread` without the owner's word.

## Cache
JSON is fetched no-cache. If old JS or CSS shows after a republish, reload the page; if it persists, report it.
