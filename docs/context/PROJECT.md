# Project Overview

HorarioGen is a local academic timetable planner for configuring teachers, subject assignments, weekly teaching hours, availability, sections, and classrooms, then generating and reviewing a weekly schedule. The current application is version `0.1.4`.

## Product scope

- Import academic sessions and related constraints from CSV or Excel.
- Assign teachers and weekly hours to subjects; split hours into repeated one-to-four-hour blocks across selected weekdays.
- Optimize hard scheduling constraints and soft preferences with a genetic algorithm.
- Review schedules by session, teacher, room, day, and initial/optimized state; simulate classroom occupancy.
- Export a generated timetable.

The bundled scenario is fictional: ten teachers, semesters 1–9, sections A/B, and rooms 106–112. Odd semesters use 07:00–13:00 and even semesters 14:00–20:00, with lunch 13:00–14:00 reserved. These values are example rules and must not be presented as verified institutional policy.

## Product and engineering conventions

- The user interface is Spanish. Source code and technical documentation are English.
- Preserve existing behavior and use the architecture described in `ARCHITECTURE.md`.
- The scheduler is heuristic and run-based; it is not a trained model and does not guarantee a globally optimal schedule.
- Classroom occupancy does not model student headcount or physical movement without enrollment and building-layout data.
- Do not store credentials or real institutional personal data in source control.

For setup, import formats, and operating instructions, see the repository `README.md`.
