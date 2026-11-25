# Architecture and Product Decisions

Record durable decisions here. Keep entries concise; revise an existing decision when its rationale changes.

## D-001 — Preserve the v0.1.4 functional baseline

- **Decision:** Start this working repository from the last functional `v0.1.4` delivery.
- **Rationale:** It includes the requested teacher-subject weekly-load assignment and classroom-flow simulation.
- **Consequences:** Future product changes use this repository and preserve release versioning in the `v0.1.*` line.

## D-002 — Keep UI Spanish and engineering artifacts English

- **Decision:** User-facing product copy remains Spanish; source code, technical docs, and Git commits use English.
- **Rationale:** The application serves Spanish-speaking planners while the repository follows a consistent engineering language.

## D-003 — Treat optimizer rules as hard constraints before preferences

- **Decision:** Compare scores lexicographically as `(D, B)`, minimizing hard violations before soft costs.
- **Rationale:** Avoid improving convenience preferences at the cost of invalid teacher, room, group, availability, workload, shift, or section rules.
- **Consequence:** A heuristic run may still end with unresolved hard violations; results must show their measured score.

## D-004 — Keep local file persistence for the current baseline

- **Decision:** Store datasets and runs as local CSV/JSON with atomic file replacement and in-process locking.
- **Rationale:** The product is a local planning tool and does not currently require shared multi-user state.
- **Consequence:** Run one API process; authentication and shared database semantics are not provided.

## D-005 — Model room flow as scheduled occupancy only

- **Decision:** Simulate room occupancy from scheduled activity intervals, not student movement or traffic.
- **Rationale:** Enrollment and a verified building layout are not available in the example data.
