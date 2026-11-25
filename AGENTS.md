# HorarioGen Agent Instructions

## Session startup

1. Read this file, `docs/context/STATE.md`, and `docs/context/HANDOFF.md`.
2. Check `git status --short --branch` before editing.
3. Read `PROJECT.md`, `ARCHITECTURE.md`, `DECISIONS.md`, or `TASKS.md` only when relevant to the task.
4. Use `.agents/skills/context-manager/SKILL.md` to recover or save project context. Use `.agents/skills/token-efficiency/SKILL.md` to keep repository work focused.

## Project rules

- Preserve existing functionality and follow the documented architecture. Do not invent product requirements or institutional data.
- Keep the product UI in Spanish. Write source code, technical documentation, and Git commit messages in English.
- Keep changes scoped; do not modify business logic during repository/context configuration tasks unless explicitly requested.
- Check for existing project conventions before adding dependencies or abstractions.
- Never store credentials, tokens, or private user data in source control.
- Preserve existing documentation. Update relevant context files after substantial work; do not copy source code into context documents.
- `docs/context/HANDOFF.md` must remain under 500 words and `docs/context/STATE.md` under 1,000 words.

## Engineering workflow

- Prefer targeted searches (`rg`), focused diffs, and the smallest relevant verification. Exclude generated and dependency directories such as `node_modules`, `.next`, `.venv`, `__pycache__`, and `.git` from broad searches.
- For complex defects, use the `systematic-debugging` skill when available and identify the root cause before changing code.
- Use `verification-before-completion` when verification is needed; report only checks actually performed and their results.
- For frontend and design work, use the relevant installed Emil Kowalski skills, especially `emil-design-eng`; load animation-specific skills only when the task involves animation.
- Load skills only when relevant. Do not load the full skill catalog for routine changes.
- Do not use subagents unless task complexity materially benefits from delegation.

## Git

- Inspect status and preserve user changes. Do not commit or push unless the user authorizes that action for the current task.
- When authorized, use English Conventional Commit messages (for example, `feat: add teacher availability editor`).
- Keep commits focused and describe the behavior or maintenance change clearly.
