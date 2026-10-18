# Skills

Tool-neutral skills for software and project work. Each folder has a short `SKILL.md` (load first) and optional `references/` (open when the skill says).

## Which skill?

| Need | Skill |
|---|---|
| Start of work in any project; standing rules, capability fallbacks, known traps | `operating-rules` |
| Plan or run a task with planner, plan critic, implementer, review critic | `agent-workflow` |
| Save context, resume, checkpoint, startup/close-out routines, `.agent/` layout | `project-management` |
| Branches, PRs, pushing, secrets, repo hygiene | `repo-management` |
| Python style, validation, tests | `python-development` |
| Guides, generated catalogs, diagrams, docs build | `documentation` |
| Read-only code audit | `code-audit` |
| Reply style, summaries, questions | `response-format` |
| Windows Git Bash / PowerShell scripting traps | `windows-shell-gotchas` |
| Project roadmap dashboard (only if the project has one) | `roadmap-dashboard` |

Default load order: `operating-rules`, then the skill for the task.

## Wiring a project

Tools that auto-load skills by description need nothing. Others: add this to the project's instruction file (`AGENTS.md`, `CLAUDE.md`, etc.):

```
Skills: <skills-dir>. At start read operating-rules/SKILL.md; load others by the table in README.md.
Project notes: .agent/state/ (see project-management/references/templates.md).
```

Project-specific lessons, decisions and rules live in the project's `.agent/` folder, never here.
