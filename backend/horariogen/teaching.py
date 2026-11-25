"""Expand a course's weekly teaching assignment into individual class blocks."""
from collections import Counter
from dataclasses import replace

from .domain import Gene, Slot, semester_number, occupies_group
from .evaluation import contained


def build_plan(sessions, entries, rules):
    sources = {s.id: s for s in sessions if not s.tutoring}
    known_teachers = {s.teacher for s in sessions}
    planned = {}
    for entry in entries:
        source = sources.get(entry.source_id)
        if source is None or entry.teacher not in known_teachers:
            raise ValueError('Selecciona un grupo y un docente registrados.')
        course = entry.course.strip()
        if not course:
            raise ValueError('La materia necesita un nombre.')
        key = source.group_key, course.casefold()
        if key in planned:
            raise ValueError('Una materia solo puede tener una asignación por paralelo.')
        days = sorted(set(entry.days))
        if not days or len(days) != len(entry.days):
            raise ValueError('Selecciona días únicos de lunes a viernes.')
        if entry.weekly_hours > len(days) * 6:
            raise ValueError(f'{course}: las horas superan la jornada de los días elegidos.')
        planned[key] = (source, entry, days)
    if sum((e.weekly_hours + e.block_hours - 1) // e.block_hours for _, e, _ in planned.values()) + sum(s.tutoring for s in sessions) > 3000:
        raise ValueError('El plan supera el límite de 3000 actividades.')
    totals = Counter()
    for source, entry, _ in planned.values(): totals[source.group_key] += entry.weekly_hours * 60
    for tutor in sessions:
        if tutor.tutoring and (tutor.group_key, tutor.course.casefold()) in planned:
            totals[tutor.group_key] += tutor.original.slot.duration
    if any(minutes > 1800 for minutes in totals.values()):
        raise ValueError('Las clases y tutorías de un paralelo superan sus 30 horas disponibles por semana.')
    # A teacher change also updates that course's existing fixed tutoring reservations.
    links = {(s.group_key, s.course.casefold()): entry for s, entry, _ in planned.values()}
    originals = {(s.group_key, s.course.casefold()): [] for s in sources.values()}
    for source in sources.values(): originals[source.group_key, source.course.casefold()].append(source)
    output = []
    for tutor in sessions:
        if not tutor.tutoring: continue
        if occupies_group(tutor):
            entry = links.get((tutor.group_key, tutor.course.casefold()))
            if entry is None: continue
            tutor = replace(tutor, teacher=entry.teacher, course=entry.course.strip())
        output.append(tutor)

    def conflicts(session, slot, room):
        return sum(slot.day == other.original.slot.day and slot.start < other.original.slot.end
                   and other.original.slot.start < slot.end
                   and (session.teacher == other.teacher or room == other.original.room
                        or occupies_group(other) and session.group == other.group)
                   for other in output)

    allowed = {}
    # Keep feasible existing blocks first so editing one course does not rebuild all others.
    pending = []
    for key, (source, entry, days) in planned.items():
        remaining = entry.weekly_hours * 60
        room = rules.group_rooms.get(source.group_key, source.original.room)
        number = semester_number(source)
        beginning, closing = (420, 780) if number % 2 else (840, 1200)
        for previous in originals.get(key, []):
            duration = previous.original.slot.duration
            slot = previous.original.slot
            windows = rules.availability.get(entry.teacher)
            candidate = replace(previous, teacher=entry.teacher, course=entry.course.strip(), original=Gene(slot, room))
            if (duration <= remaining and duration <= entry.block_hours * 60
                    and slot.day in days and beginning <= slot.start < slot.end <= closing
                    and (windows is None or contained(slot, windows))
                    and not conflicts(candidate, slot, room)):
                output.append(candidate); allowed[id(candidate)] = days; remaining -= duration
        while remaining:
            duration = min(remaining, entry.block_hours * 60)
            pending.append((source, entry, days, room, beginning, closing, duration))
            remaining -= duration
    for source, entry, days, room, beginning, closing, duration in sorted(pending, key=lambda item: (-item[-1], item[0].id)):
        candidate = replace(source, teacher=entry.teacher, course=entry.course.strip())
        windows = rules.availability.get(entry.teacher)
        daily = Counter()
        for other in output:
            if not other.tutoring and other.group == source.group and other.course == candidate.course:
                daily[other.original.slot.day] += other.original.slot.duration
        options = [Slot(day, start, start + duration) for day in days
                   for start in range(beginning, closing - duration + 1, 60)]
        def cost(slot):
            hard = conflicts(candidate, slot, room) + int(windows is not None and not contained(slot, windows))
            return hard, daily[slot.day], slot.day, slot.start
        slot = min(options, key=cost)
        candidate = replace(candidate, original=Gene(slot, room))
        output.append(candidate); allowed[id(candidate)] = days
    # Stable, unique sequential IDs are shared by CSV, rules and optimization output.
    normalized = tuple(replace(s, id=i+1) for i, s in enumerate(output))
    session_days = {i+1: allowed[id(s)] for i, s in enumerate(output) if not s.tutoring}
    return normalized, session_days, {i+1: s.id for i, s in enumerate(output)}
