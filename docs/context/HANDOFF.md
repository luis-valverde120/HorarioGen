# Handoff

## Current objective

Evolve the original HorarioGen application for the supplied UPEC Computing planning scenario.

## Implemented

- Added the 50-subject reference catalog and source fingerprint. Synthetic demonstrations cover one or two parallel groups per semester with 16 teachers and shared rooms 206–212.
- Added separate class and tutorial blocks, custom campus and group windows, preflight diagnostics, and locked assignments. The legacy dataset remains available.
- Integrated per-run working memory with the existing search and HTTP API. Added bounded events, observed conflicts, cancellation, and a preview of the best candidate.
- Added Spanish curriculum and working memory views, institutional design tokens, and adaptive timetable and room occupancy views. See `DESIGN.md`, `docs/SCHEDULING_MODEL.md`, and `docs/WORKING_MEMORY.md`.

## Verification and next action

- Backend suite and frontend production build passed during development. Browser verification loaded the two-parallel demo and showed a completed run with genuine events and zero hard violations. See STATE for the final verification record.
- Resolve the Titulación discrepancy with the applicable academic period and obtain verified institutional resources. Administrative curriculum version editing and individual group activation remain open.
- No release was declared. The feature changes are in the working tree.
