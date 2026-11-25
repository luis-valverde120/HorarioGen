# HorarioGen v0.1.4

HorarioGen is a local academic timetable planner. It imports Excel or CSV data, configures classrooms and teacher availability, assigns weekly teaching loads, and searches for a timetable with a genetic algorithm. The interface is in Spanish; technical documentation and source code are in English.

## Requirements and launch

- Python 3.11 or later
- Node.js 22 or later, including npm
- Internet access on first launch to install dependencies and build the frontend

On Windows, run `Iniciar-HorarioGen.cmd`. Keep its terminal open while using the app; press Ctrl+C to stop both services. On macOS or Linux, run `python3 iniciar.py`. The launcher accepts `--port`, `--api-port`, and `--sin-navegador`. Defaults are frontend port 3000 and API port 8000. Set `HORARIOGEN_DATA` to choose a persistence directory.

For manual development, install `backend/requirements-dev.txt` in a Python virtual environment and run `python -m uvicorn horariogen.api:app --host 127.0.0.1 --port 8000` from `backend`. In `frontend`, run `npm ci` and `npm run dev`. Set `HORARIOGEN_BACKEND` to change the Next.js API proxy target. The browser uses same-origin `/api` routes.

## Demonstration scenario

Open **Malla curricular** to load the UPEC reference demonstration for an academic period with one or two groups per semester. The demonstration uses classrooms 206–212 and 16 synthetic teachers. Curriculum hours are source totals and appear separately from planned weekly hours. Use **Memoria de trabajo** to see the optimizer's recorded state and events.

See the [scheduling model](docs/SCHEDULING_MODEL.md), [working memory guide](docs/WORKING_MEMORY.md), and [design system](DESIGN.md) for implementation details.

The bundled example has ten fictional teachers, 101 class blocks, and 18 linked tutoring activities. It covers semesters 1–9 with sections A and B: five distinct subjects in each A section and six in each B section. Blocks range from one to four hours, with two-hour blocks most common. Example classrooms are 106–112. Example weekly teacher loads, including tutoring, range from 18 to 26 hours.

Odd semesters (1, 3, 5, 7, 9) use the morning shift, 07:00–13:00. Even semesters (2, 4, 6, 8) use the afternoon shift, 14:00–20:00. Both sections follow their semester's shift. Five or six subjects is a property of the example, not an import restriction.

The initial timetable intentionally places one class in the wrong shift to demonstrate optimization. Generate a timetable to evaluate and export a candidate. The subjects, loads, availability, and room assignments are illustrative, not an official institutional curriculum. Replace them with verified institutional data before operational use.

The calendar opens on semester 1, section A. When all displayed activities fit that semester's shift, it focuses on that six-hour window. The 13:00–14:00 lunch interval is reserved and shown in full-day views. A class block must fit wholly within one academic shift. Multiple sections use a daily agenda where a grid would be too narrow. Each section can be assigned a classroom in **Model and rules**; its classes and linked tutoring must use that room. Different sections can share a room at different times.

## Assign teachers and weekly subject hours

**Teachers and subjects** groups class activities by semester, section, and subject. For each subject, choose a registered teacher, edit the subject name, set weekly hours, choose a maximum block length of one to four hours, and select allowed weekdays. A ten-hour subject with two-hour blocks becomes five sessions distributed over the selected weekdays. A twenty-hour load is split into blocks as well; feasibility depends on teacher availability, classroom occupancy, and the section's shift and weekly capacity.

Saving assignments creates a new dataset and preserves the previous one. All sections are saved, including sections hidden by the current filter. Generate a timetable after saving to check and optimize the complete plan. The optimizer preserves each subject's weekly hours, penalizes placing its sessions on the same day, and treats selected weekdays as a hard constraint. A section can have at most 30 scheduled hours per week, including linked tutoring.

When **Use assigned hours as current teaching targets** is enabled, teacher targets are set to the sum of class and tutoring hours in the plan. When disabled, existing targets remain and mismatches are reported. Changing a subject's teacher also changes its linked tutoring activities. Removing a subject removes its classes and linked tutoring from the newly saved dataset. Assignments use the currently selected dataset's classrooms and availability; save the plan before changing those rules on screen.

The example distributes seventh-section-A Mobile Applications and eighth-section-A Machine Learning across multiple days. A subject may have multiple weekly sessions while the section retains five or six distinct subjects.

## Simulate classroom occupancy

**Classroom flow** displays all seven classrooms and shows the activity, teacher, section, and time remaining, together with the next scheduled activity. Choose a weekday and time, play or pause the week, reset, or change playback speed. The simulation advances in 30-minute steps from 07:00 through 19:30 and then moves to the next day. Intervals are half-open: an activity ending at the next activity's start time frees the classroom for that activity.

Before optimization, the view uses the initial assignments; afterward, it uses the optimized result. It includes all sections and is independent of calendar filters. Simultaneous classroom conflicts are highlighted. This is an academic occupancy simulation; it does not estimate student counts or physical movement through a building without enrollment data and a floor plan.

## Excel import

Use `.xlsx` files with values in cells. Formulas are rejected to avoid relying on cached results from another application. Each sheet's headers must be in its first row.

| Sheet | Columns | Purpose |
|---|---|---|
| `Sesiones` (required) | `Franja_Horaria`, `Nivel_Semestre`, `Paralelo_Grupo`, `Carrera_Especialidad`, `Codigo_Asignatura`, `Docente`, `Aula`, `Programa_Academico`, optional `Tipo` | Classes and tutoring |
| `Aulas` | `Aula`, optional `Capacidad` | Classroom catalog; only rooms 106–112 are allowed |
| `Paralelos` | `Semestre`, `Paralelo`, `Aula`, optional `Programa_Academico`, `Carrera_Especialidad` | Classroom assigned to each section |
| `Docentes` | `Docente`, `Horas_Semanales` | Weekly teaching target including tutoring |
| `Disponibilidad` | `Docente`, `Dia`, `Inicio`, `Fin` | Allowed teacher time windows |
| `Guia` | `Campo`, `Cómo completarlo` | Downloadable template instructions |

If `Aulas` is omitted, all seven rooms are available. If supplied, only listed rooms may be assigned, and every initial assignment must belong to that list. Capacity is checked only when enrollment is also provided for a session. Use 24-hour ranges such as `Monday 08:00 - 10:00`. Availability accepts weekday names in Spanish or English and times such as `08:00`. Consecutive activities may meet exactly at the previous activity's end.

## CSV import

For class rows, semester must be 1–9 and section must be A or B (equivalent to 1 or 2). Original-format rows use `Nivel_Semestre` and `Paralelo_Grupo`. In CSV, the first class's classroom for each section is its initial room; it can be corrected in the app. UTF-8 files may use comma, semicolon, or tab separators.

Use either the original eight session columns, with optional `Tipo`, or the simpler `Materia`, `Docente`, `Grupo`, `Duracion_Horas` format with optional `Semestre`. If omitted, semester defaults to 1. Optional `Tipo` accepts `Clase` or `Tutoria`. The simple format creates initial assignments for the search and displays a notice to run the optimizer. Imported source files are stored with a `.source` extension and normalized CSV files use the same dataset ID. Limits: 5 MiB per upload, 30 MiB decompressed Excel workbook, and 3,000 sessions. Import validation errors are returned as messages with HTTP 422.

## Model and constraints

A chromosome contains a time-slot and room assignment for each activity. Each activity retains its teacher, subject, section, and duration. Tutoring activities reserve their slot and room. Overlaps are evaluated using actual time intervals.

The objective is lexicographic `(D, B)`: hard-constraint violations `D` are minimized before soft penalties `B`. Hard constraints include teacher, room, and section overlaps; unassigned or invalid-duration activities; workload targets; availability and capacity when supplied; academic shifts; assigned section rooms; allowed subject weekdays; and section weekly-hour limits. Soft penalties cover rescheduling, room changes, gaps in a section's day, recorded teacher preferences, and repeated subject blocks on the same day.

Teaching workload includes classes and tutoring. Rescheduling does not change total hours; users must adjust activities or durations when a target is under- or over-subscribed. Administrative, research, and other work counts only when represented in the plan.

Each optimization run creates a population from the original schedule, a greedy candidate, and variants. If conflicts remain, it tries to move affected activities within allowed windows and retains the best candidate found. The genetic search uses tournament selection, uniform crossover, reassignment or equal-duration swap mutations, and elitism. It stops at the configured generation/time limit or score `(0, 0)`. This is a heuristic search, not a learned model or proof of global optimality. Runs and their history are persisted locally.

## Architecture and API

The application is a modular local monolith. A FastAPI backend validates data, invokes a separate scheduling engine, and stores datasets and runs as CSV/JSON. A single worker runs optimizations outside request handling. The Next.js frontend uses TypeScript, Tailwind, UI components, and Recharts. Run one Uvicorn process with the local file repository.

The API includes `POST /api/datasets/import`, `GET /api/datasets`, `GET /api/datasets/{id}/sessions`, `POST /api/datasets/{id}/teaching-plan`, `POST /api/optimizations`, `GET /api/optimizations/{id}` and its `result`, `metrics`, and `export` subroutes, and `GET /api/health`. `GET /api/templates/xlsx` and `/csv` download import templates. Interactive API documentation is available at `/docs`.

## Verification record

The v0.1.4 development record reports 53 automated tests passing, covering CSV/Excel import, persistence, availability, shifts, rooms, workload, tutoring, one-to-four-hour blocks, ten- and twenty-hour subject loads, allowed weekdays, and non-destructive teaching-plan creation. It also reports a successful production build and type checks. Component behavior was checked with a DOM test for room occupancy, day selection, playback, pause, weekly subject totals, editing a ten-hour load, and saving. An API integration run distributed a seventh-section-A subject's ten hours into five sessions, preserved the prior dataset, and reached zero hard violations after optimization. A desktop-browser visual check could not be completed in that environment. These are prior v0.1.4 results; rerun verification after making changes.

## Versioning and known limits

The current release is `v0.1.4`, recorded in `VERSION`, the interface, and API. Subsequent changes belong to the `v0.1.*` series and should be isolated in their versioned delivery folders when packaging is requested.

The heuristic may finish with unresolved conflicts. Demonstration rules and availability are fictional. Classroom capacity needs verified capacity and enrollment data. Physical student traffic needs enrollment data and a building floor plan. Screen-edited rules apply to subsequent runs; re-import the source file to restore its original rules. Runs interrupted by a process restart are marked failed. Authentication and multi-user database storage are not included.
