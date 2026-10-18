---
name: windows-shell-gotchas
description: Traps when scripting on Windows with Git Bash and PowerShell: heredoc backslashes, CRLF line endings, runaway grep output, background servers, embedded browsers and private pages. Use before writing shell or Python edit scripts, editing files by script, or starting and stopping local servers.
---

# Windows shell gotchas

Known time-wasters; follow them.

## Scripts and quoting
- Python containing backslashes or backticks breaks inside a Bash heredoc (`'\\'` arrives mangled). Write the script to a scratch file with a file-write tool, then run it. In python use `Path(...).as_posix()` or raw strings for paths.
- Bash `$(...)` with `$'\r'` and process substitution can fail in Git Bash: do line-ending checks in python (`b'\r\n' in data`).
- Bash `kill %1` does not stop a server started by a tool; stop it by port from PowerShell: `Get-NetTCPConnection -LocalPort 8765 | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }`. A background command reports "completed" even when a server it launched keeps running.
- Windows PowerShell 5.1: no `&&`, no `?:`; use `;` and `if ($?)`.
- Backticks inside double-quoted Bash arguments are executed as commands (a `--desc "..."` once ran `git log --graph`); use single quotes.
- Git Bash rewrites `branch:path` arguments that look like paths (`git show origin/x:.agent/a.md` fails as "ambiguous argument"); run such git commands from PowerShell.
- Git Bash's `/tmp` and Python's `/tmp` are different folders on Windows; use a scratch folder under the project or home for files both must see.

## Line endings
- Working-tree files may be CRLF while git stores LF. When editing by script read bytes, note whether `\r\n` is present, edit on LF text, and write back with the original endings. Git prints "LF will be replaced by CRLF" warnings; they are noise.
- A file that shows as modified with an empty diff is a line-ending artifact: `git checkout -- <file>` clears it.

## Output size
- `grep -n -o`, `git grep` over generated files and SVG/JSON one-liners can flood the output. Start with `-c` or `-l`, exclude `*.svg` and generated folders, and pipe through `cut -c1-200 | head`.
- Pytest: `python -m pytest -q 2>&1 | tail -5`.

## Browsers and local servers
- An embedded browser is separate from the user's: not signed in, so private published pages show a sign-in page. Test locally (serve on localhost) and never sign in on the user's behalf.
- Screenshots can time out if the window is hidden; read page text or the DOM instead.
- Navigating to localhost may be denied by one tool but allowed by another (e.g. a preview/start tool); try the other.

## Editing many files
- Prefer one scripted pass over dozens of single edits, but dry-run first and print counts per file, then run the tests. Search every spelling of a name (PascalCase, camelCase, snake_case, UPPER_SNAKE) and non-code places (docs, JSON, SVG).
