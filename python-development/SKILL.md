---
name: python-development
description: General Python coding standards: naming, docstrings, grouped validation helpers, sparse comments, clean-break renames, tests, safe file editing. Use before writing, editing or reviewing Python, and when briefing an implementer or critic on style. Project skill adds specific paths and conventions.
---

# Python development standards

Match surrounding code: comment density, names, idiom. Project skill/notes win on conflict.

## Names
- Verbose, self-explaining (`strategyInputs`, not `stratIns`) for variables, attributes, params, functions.
- Test names = full sentences describing behavior.
- Follow project case convention (camelCase vs snake_case) consistently.

## Docstrings
- Major function (branching, loops, coordination, public API): short imperative summary, longer explanation if needed, `Args:` (every param except self/cls, type + meaning), `Returns:` (type + meaning, even None).
- Minor code gets none: one-line wrappers, tiny private helpers, trivial dunders, dataclass fields, `_check...` helpers.

## Validation
- Group a function's validation in ONE helper called once near top, `_check<WhatItChecks>`: nested if only it uses it, module-level if shared. Several helpers only for unrelated or differently-shared checks; keep calls together.
- Error messages start with dotted path of bad value (`scenario.barSize: ...`), say what to change.
- Reuse shared check helpers (finite, positive, at least N, one of). Add checks only where failure would be silent or hard to trace; let base Python/numpy/pandas errors surface.

## Comments
- What and why, sparingly. No task ids, planning-note paths, "later"/"planned" notes in code, tests, docstrings, skills. Known defects go in project notes.

## Changes and renames
- Public rename = clean break: no aliases or shims. Saved-file field rename bumps that file type's schema version; old files refused with hint, not migrated.
- After rename search every spelling (Pascal, camel, snake, UPPER_SNAKE) in docstrings, JSON, docs, figures; follow `documentation`. Prefer project rename script (dry run, then apply).

## Tests
- Behavior change needs a test failing without it. Re-record baselines only with the project's recorder script.
- Add/rename/remove test = update generated test catalog (`documentation`).
- Cheap runs: implementer runs touched files' tests plus baseline tests, quiet runner, reads last ~15 lines or failures. `slow` tests run once per task by review critic. Never paste full test output.

## Editing hygiene
- Read file before editing. Files may be CRLF: scripted edits read bytes, keep original line endings.
- Python with backslashes or backticks breaks in shell heredocs: write the script to a file with a file-write tool, then run it.
- Agent in git worktree may import main repo's package: set `PYTHONPATH` to worktree source before starting Python; confirm with package `__file__`.
- Never read, print or write `.env`.
