---
name: context-manager
description: Restore concise HorarioGen context at session start and persist verified project state after substantial work.
---

# Context Manager

## Session start

1. Read `AGENTS.md`, `docs/context/STATE.md`, and `docs/context/HANDOFF.md`.
2. Check `git status --short --branch` and preserve all user changes.
3. Read `PROJECT.md`, `ARCHITECTURE.md`, `DECISIONS.md`, or `TASKS.md` only when relevant. Do not reread unchanged files or repeat completed analysis.

## During work

- Track durable decisions, unresolved blockers, and verification evidence.
- Keep source code as the source of truth for implementation details; context documents summarize and link to it.
- Do not save credentials, secrets, or real personal data.
- Avoid duplicating project or README documentation.

## Save context

After a substantial task or when asked:

1. Update `STATE.md` with the verified current baseline and actual checks performed.
2. Update `TASKS.md` only when task status changes.
3. Add or revise `DECISIONS.md` only for durable decisions.
4. Update `ARCHITECTURE.md` only when architecture changed.
5. Replace `HANDOFF.md` with current objective, completed work/files, decisions, verification, blockers, and an exact next action.

Keep `HANDOFF.md` below 500 words and `STATE.md` below 1,000 words. Never report historical tests as newly run. Do not create commits or push unless authorized for the current task; use English Conventional Commits when authorized.
