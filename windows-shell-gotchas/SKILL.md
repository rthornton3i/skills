---
name: windows-shell-gotchas
description: Lists traps when scripting on Windows with Git Bash and PowerShell in an AI coding agent: heredoc backslashes, CRLF line endings, runaway grep output, background servers, the built-in browser and private pages. Use before writing shell or Python edit scripts, editing files by script, or starting and stopping local servers.
---

# Windows shell gotchas

Each item cost time before. Follow them and skip the rediscovery.

## Scripts and quoting
- Python containing backslashes or backticks breaks inside a Bash heredoc (`'\\'` arrives mangled). Write the script with the Write tool (a scratchpad file), then run it. For paths inside python use `Path(...).as_posix()` or raw strings, not escaped backslashes. An invalid escape such as `'\S'` in a normal string only warns, but use a raw string.
- Bash `$(...)` with `$'\r'` and process substitution can fail in Git Bash: do line-ending checks in python (`b'\r\n' in data`).
- Bash `kill %1` does not stop a server started by a tool; stop it by port from the PowerShell tool: `Get-NetTCPConnection -LocalPort 8765 | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }`. A background command reports "completed" even when a server it launched keeps running.
- The PowerShell tool is Windows PowerShell 5.1: no `&&`, no `?:`, use `;` and `if ($?)`.
- Backticks inside double-quoted Bash arguments are executed as commands (a `--desc "..."` once ran `git log --graph`); use single quotes.
- Git Bash rewrites `branch:path` arguments that look like paths (`git show origin/x:.agent/a.md` fails as "ambiguous argument"); run such git commands from the PowerShell tool.
- Git Bash's `/tmp` and Python's `/tmp` are different folders on Windows; use the session scratchpad for anything both must see.

## Line endings
- Working-tree files may be CRLF while git stores LF. When editing by script read bytes, note whether `\r\n` is present, edit on LF text, and write back with the original endings. Git prints "LF will be replaced by CRLF" warnings; they are noise.
- A file that shows as modified with an empty diff is a line-ending artifact: `git checkout -- <file>` clears it.

## Output size
- `grep -n -o`, `git grep` over generated files and SVG/JSON one-liners can flood the output. Start with `-c` or `-l`, exclude `*.svg` and generated folders, and pipe through `cut -c1-200 | head`.
- Pytest: `python -m pytest -q 2>&1 | tail -5`.

## Browsers and local servers
- The built-in browser pane is a separate browser: it is not signed in to the user's accounts, so private published pages show a sign-in page. Test a page locally instead (serve it on localhost and open that URL with the preview or navigate tool) and never sign in on the user's behalf.
- Screenshots can time out if the window is hidden; use page text or DOM reads (`get_page_text`, `javascript_tool`) instead.
- A `navigate` to localhost can be denied while `preview_start` with a `url` works.

## Editing many files
- Prefer one scripted pass over dozens of single edits, but dry-run first and print counts per file, then run the tests. Search every spelling of a name (PascalCase, camelCase, snake_case, UPPER_SNAKE) and non-code places (docs, JSON, SVG).
