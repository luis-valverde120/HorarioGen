from collections import Counter, defaultdict

from .domain import Slot, occupies_group, semester_number
from .evaluation import evaluate


def intersect(left, right):
    return sorted({Slot(a.day, max(a.start, b.start), min(a.end, b.end))
                   for a in left for b in right
                   if a.day == b.day and max(a.start, b.start) < min(a.end, b.end)})


def planning_windows(session, rules):
    if rules.campus_windows is not None:
        windows = rules.campus_windows
    else:
        bands = ((420, 780), (840, 1200)) if rules.enforce_hours else ((0, 1440),)
        windows = [Slot(day, start, end) for day in range(7) for start, end in bands]
        number = semester_number(session)
        if rules.enforce_hours and number and session.group_key not in rules.group_windows:
            windows = [slot for slot in windows if (slot.start == 420) == bool(number % 2)]
    if session.group_key in rules.group_windows:
        windows = intersect(windows, rules.group_windows[session.group_key])
    if session.teacher in rules.availability:
        windows = intersect(windows, rules.availability[session.teacher])
    days = rules.session_days.get(session.id, range(7))
    return [slot for slot in windows if slot.day in days and slot.duration >= session.original.slot.duration]


def total_minutes(windows):
    end_by_day = {}
    minutes = 0
    for slot in sorted(windows):
        end = end_by_day.get(slot.day, 0)
        minutes += max(0, slot.end - max(end, slot.start))
        end_by_day[slot.day] = max(end, slot.end)
    return minutes


def validate_feasibility(sessions, rules):
    errors, warnings = [], []

    def error(code, message, **context):
        errors.append({"code": code, "message": message, **context})

    minutes = Counter()
    demand = Counter()
    windows_by_resource = defaultdict(set)
    ids = Counter(s.id for s in sessions)
    for session in sessions:
        if ids[session.id] > 1:
            error("duplicate_id", "Hay identificadores de sesión duplicados.", session_id=session.id)
        duration = session.original.slot.duration
        if duration not in (60, 120, 180, 240):
            error("duration", "Las sesiones deben durar de una a cuatro horas completas.", session_id=session.id)
        windows = planning_windows(session, rules)
        room = rules.group_rooms.get(session.group_key) if occupies_group(session) else None
        if rules.fixed(session):
            fixed = session.original.slot
            windows = [fixed] if any(w.day == fixed.day and w.start <= fixed.start and fixed.end <= w.end
                                     for w in windows) else []
            if room and room != session.original.room:
                windows = []
            room = session.original.room
        if not windows:
            error("no_interval", f"{session.course} · {session.teacher}: no hay una franja continua disponible.",
                  session_id=session.id)
        rooms = (room,) if room else rules.available_rooms
        enrollment = rules.enrollments.get(session.id)
        if enrollment is not None and rooms and all(
            name in rules.capacities and rules.capacities[name] < enrollment for name in rooms
        ):
            error("capacity", f"{session.course}: las aulas permitidas no tienen aforo suficiente.",
                  session_id=session.id)
        resources = [("docente", session.teacher)]
        if occupies_group(session):
            resources.append(("paralelo", session.group_key))
        if room or len(rooms) == 1:
            resources.append(("aula", room or rooms[0]))
        for resource in resources:
            demand[resource] += duration
            windows_by_resource[resource].update(windows)
        minutes[session.teacher] += duration

    for (kind, name), required in demand.items():
        if required > total_minutes(windows_by_resource[kind, name]):
            error("resource_minutes", f"Las sesiones del recurso {kind} {name} exceden el tiempo disponible.",
                  resource=name)
    if rules.campus_windows is not None and rules.available_rooms:
        required = sum(minutes.values())
        supply = total_minutes(rules.campus_windows) * len(rules.available_rooms)
        if required > supply:
            error("shared_room_minutes", "Las sesiones superan el tiempo total disponible de las aulas.")
    for teacher, target in rules.weekly_minutes.items():
        if target != minutes[teacher]:
            error("workload", f"La carga de {teacher} no coincide con las horas de sus sesiones.", resource=teacher)
    fixed = [s for s in sessions if rules.fixed(s)]
    evaluation = evaluate(fixed, [s.original for s in fixed], rules, details=True)
    for conflict in evaluation.conflicts:
        if conflict["type"] in ("teacher", "room", "group"):
            error("locked_overlap", "Dos sesiones reservadas coinciden en un recurso.",
                  sessions=conflict["sessions"])
    missing = sorted({s.teacher for s in sessions} - rules.availability.keys())
    if missing:
        warnings.append({"code": "unknown_availability",
                         "message": f"No hay disponibilidad registrada para {len(missing)} docentes."})
    return {"can_optimize": not errors, "errors": errors, "warnings": warnings}
