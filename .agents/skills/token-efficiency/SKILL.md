---
name: token-efficiency
description: Reduce unnecessary repository reads, output, and repeated analysis while preserving correctness and verification.
---

# Token Efficiency

## Retrieve context selectively

- At session start, read only `AGENTS.md`, `docs/context/STATE.md`, and `docs/context/HANDOFF.md`.
- Consult other context documents only when the task depends on them.
- Use targeted `rg` searches and narrow line ranges before reading large files.
- Reuse verified context; do not redo unchanged analysis.

## Search and edit narrowly

- Exclude `node_modules`, `.next`, `.venv`, `__pycache__`, `.git`, build, coverage, and other generated/vendor directories from broad searches.
- Inspect Git status and focused diffs before and after edits.
- Make incremental changes; do not regenerate whole files for a small fix.
- Preserve architecture and avoid unrelated refactors or unnecessary dependencies.
- Do not use subagents for routine tasks; delegate only when task complexity justifies it.

## Verify proportionally

- Run the smallest relevant check first, then broaden only when warranted.
- Do not claim a check was run based on historical context.
- Report concrete results and known limitations without dumping full logs.

## Communicate concisely

- Communicate with the user in Spanish.
- Keep documentation and code in English and the HorarioGen UI in Spanish.
- Summarize changes, verification, and blockers; do not repeat the request or print entire files in chat.
- For simple tasks, act directly without elaborate planning. For complex work, use a short plan and progress updates.

Efficiency must not reduce correctness, security, accessibility, or necessary verification.
