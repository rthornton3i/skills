---
name: documentation
description: Keep a project's documentation true to its code: guides, API reference, generated catalogs, diagrams with an independent critic pass, hand-drawn figures, docs builds and publishing. Use when code, tests, names or diagrams change, before close-out, and when briefing documentation work. Project paths and commands live in the project's own skill or notes.
---

# Documentation

Docs describe code as it is now, plain language, examples that run. Doc root (usually `docs/`), build command, generators: from project skill, README or notes.

## When code changes

1. Update every guide sentence, example, module-table row, API entry naming what changed (classes, modules, fields, columns, signatures, config keys). Search all spellings of old names.
2. Hand-drawn figures (no generator) go stale silently. List them in project notes; edit by hand when a module/class they name changes.
3. Docstrings feed the API reference; keep right (`python-development`).

## Generated catalogs (e.g. test catalog)

- One curated source (JSON/YAML) + generator writing the committed page. Generator cross-checks source against reality (e.g. pytest collection), fails on mismatch.
- Add/rename/remove catalogued things = edit source, rerun generator.
- Generator has a `--check` mode: writes nothing, exits non-zero if committed page stale/missing (ignore line endings). Run at every close-out.

## Diagrams (SysML or similar)

- Model as data: all diagrams in one model file; draw images from it with the project's tool. Never hand-edit generated images.
- Check verifies: code references resolve, listed parameters match signatures, text fits boxes, images current.
- Kinds: block definition, internal block (connections, typed flows), activity. Custom drawing fine if it follows notation.
- Conventions: every block/item has code reference; attribute types as specific as code (`list[Item]`, not `list`); relationship kind matches code (composition = ownership, association = reference, generalization = subclassing); reuse existing stereotypes, multiplicities, operation style.
- Text overflow: widen block, then blocks to its right, then diagram width.
- Any diagram change: edit model, run generator, run `--check`, then ONE independent read-only critic pass on changed diagram ids (relationship kinds, type accuracy, completeness, convention drift). Fix real findings, regenerate, commit. No budget for the pass = record ids as pending in project notes; never skip silently.
- At close-out run every `--check`; list diagrams changed this session.

## Build and publish

- Delete previous build output first (incremental builds leave stale pages); build with warnings as errors (Sphinx `-W`). Known warnings listed in project notes.
- Publish only when asked or at close-out. Run project's prepare step if any (rename unservable folders, rewrite links); read existing published copy first; publish changed pages only; remove stale pages explicitly.
- Commit generated pages and images; not the build output directory.
