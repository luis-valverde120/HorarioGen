# Scheduling model

The reference catalog is `data/upec_computacion.json`. It contains nine semesters and 50 subjects from the supplied three-page curriculum, with the document fingerprint and CES resolution. The source labels describe curriculum totals. The demonstration assigns two class hours and one tutorial hour per subject and group independently of those figures.

The curriculum places Titulación I in semester seven and Titulación II in semester eight. The timetable description in the supplied brief places Titulación I in semester eight. A course offering is specific to the active dataset, period, and group. The teaching planner can change those offerings without changing the reference catalog.

Select one or two groups per semester when creating a demonstration. The scenario uses 16 synthetic teachers and shares rooms 206–212 globally. The original 106–112 scenario remains available. Unknown capacity, enrollment, workload targets and teacher availability stay absent. Demo shifts and placements are synthetic. Optional campus and parallel windows replace parity-based shifts for explicitly configured plans, and gaps between windows reserve time.

The scheduler works with one continuous interval per session. Explicit class blocks sum exactly to configured weekly class hours. Tutorial blocks are configured separately. Imported or manually reserved tutorials remain fixed by default. Tutorials generated in the teaching plan can move while preserving their duration, teacher, and group. Existing plan data is preserved when creating a new dataset.

Teacher, room, and group occupancy use half-open intervals. The evaluator stores all intervals and checks overlaps for each shared resource across the entire dataset. The validation API checks fixed overlaps, durations, workload, continuous placement windows, and necessary resource time bounds. Configured calendars use strict preflight on run creation. Legacy clients can still run diagnostic searches that return unresolved conflicts.

The optimizer minimizes mandatory violations first, then weighted preference penalties. It retains session identity during uniform crossover, uses tournament selection and elitism, and attempts directed repair. With a custom calendar, it precomputes the available slots by session and prioritizes sessions with fewer options. It stops at the requested generation count, time limit, or the lowest defined score. Passing preflight does not imply a feasible schedule, and a feasible heuristic result does not establish global optimality.

Production use requires confirmed curriculum versions, course offerings, teacher availability and workloads, room capabilities, and enrollment. The room view shows scheduled occupancy.
