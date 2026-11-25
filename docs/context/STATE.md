# Current Project State

## Baseline

- Release baseline: HorarioGen `v0.1.4`. The working tree contains the UPEC scheduling evolution. The version marker is unchanged.
- The app is a Spanish-language local scheduler with a FastAPI backend, a Next.js frontend, a genetic optimization engine, CSV/Excel import, teacher/subject weekly-load planning, classroom occupancy simulation, and CSV export.
- The source migration intentionally omitted generated frontend dependencies/build output and runtime `storage/`; the launcher creates runtime storage as needed. Example source datasets remain under `data/`.
- The checkout tracks `origin/main`. This change is uncommitted.

## Baseline capabilities and constraints

- The example uses ten fictional teachers, semesters 1–9, sections A/B, classrooms 106–112, and 101 class blocks plus 18 linked tutoring activities.
- Odd semesters use 07:00–13:00; even semesters use 14:00–20:00. Lunch from 13:00–14:00 is reserved.
- Teachers have weekly load targets and availability windows. Subject assignments can be split into repeated one-to-four-hour blocks on selected weekdays.
- Hard violations are minimized before soft costs. The optimizer is heuristic; zero observed violations do not prove global optimality or validate missing institutional data.
- Runs use local CSV/JSON persistence and one optimization worker in a single API process.

## Verification record

- The current backend suite passed 58 tests. The two reference scenarios completed with zero hard violations using 16 synthetic teachers and rooms 206–212.
- The Next.js production build passed with type checking.
- Browser smoke verification loaded the 18-group UPEC scenario, observed a completed run and six engine events, and rendered the weekly schedule and seven rooms. At a 390 px viewport the document fit the page and the week grid scrolled inside its panel. An impossible Saturday window produced visible diagnostics through keyboard activation.
- A three-run legacy scenario engine spot check used seed 42, population 20, six generations, and a two-second cap. Both the previous search and the current search with memory returned `(0, 31)` every time. Median elapsed time was 0.450 s and 0.518 s respectively. This measures one scenario and excludes API persistence.

## UPEC working tree

- Curriculum source, period label, synthetic demonstration, and fixed versus configurable calendar rules are described in [Scheduling model](../SCHEDULING_MODEL.md).
- Live working memory, events, candidate preview, and cancellation are described in [Optimization working memory](../WORKING_MEMORY.md).
- The application retains its legacy demonstration. Institutional teacher identities, availability, room capabilities, and verified offerings remain pending. One reference curriculum version is bundled.

## Environment and startup

- Windows launcher: `Iniciar-HorarioGen.cmd`.
- Manual startup and API routes: repository `README.md`.
- Python requirements: `backend/requirements.txt` and `backend/requirements-dev.txt`.
- Frontend package manifest and lockfile: `frontend/package.json` and `frontend/package-lock.json`.
- Runtime data defaults to `storage/`, which is ignored by Git. `HORARIOGEN_DATA` can select another location.

## Known gaps

- Example teacher, availability, workload, and room data are fictional.
- Verified room capacities and per-session enrollment are not included.
- Physical campus traffic needs enrollment data and a building plan; current room flow shows scheduled occupancy only.
- Authentication and shared multi-user database persistence are out of scope for this local baseline.
- Re-run relevant checks after code changes; do not treat historical results as validation of new changes.
