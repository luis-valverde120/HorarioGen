# Current Project State

## Baseline

- Active baseline: HorarioGen `v0.1.4`, copied from the last functional delivery into this working repository.
- The app is a Spanish-language local scheduler with a FastAPI backend, a Next.js frontend, a genetic optimization engine, CSV/Excel import, teacher/subject weekly-load planning, classroom occupancy simulation, and CSV export.
- The source migration intentionally omitted generated frontend dependencies/build output and runtime `storage/`; the launcher creates runtime storage as needed. Example source datasets remain under `data/`.
- A local Git repository is initialized on branch `main`, with `origin` configured to the user-provided GitHub URL. No commits or pushes have been made.

## Baseline capabilities and constraints

- The example uses ten fictional teachers, semesters 1–9, sections A/B, classrooms 106–112, and 101 class blocks plus 18 linked tutoring activities.
- Odd semesters use 07:00–13:00; even semesters use 14:00–20:00. Lunch from 13:00–14:00 is reserved.
- Teachers have weekly load targets and availability windows. Subject assignments can be split into repeated one-to-four-hour blocks on selected weekdays.
- Hard violations are minimized before soft costs. The optimizer is heuristic; zero observed violations do not prove global optimality or validate missing institutional data.
- Runs use local CSV/JSON persistence and one optimization worker in a single API process.

## Verification record

The prior v0.1.4 delivery reports 53 passing automated tests, a successful frontend production build and type checks, DOM-level component checks, and a successful API integration scenario for a ten-hour subject. These are historical results from the source delivery; this repository migration has not rerun that suite. A desktop browser visual check was not completed in that environment.

The migration was verified by SHA-256 comparison of 38 functional source files, with no mismatches. Generated dependencies, build output, and runtime storage are absent from the new checkout. No product tests were run because this task changed repository setup and documentation only.

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
