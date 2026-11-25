from collections import Counter, defaultdict
from dataclasses import dataclass

from .domain import occupies_group


@dataclass
class Evaluation:
    hard: dict
    soft: dict
    coverage: dict
    conflicts: list
    workload: dict
    occupancy: dict | None = None

    @property
    def score(self):
        return sum(self.hard.values()), sum(self.soft.values())

    def payload(self):
        return dict(hard=self.hard, soft=self.soft, coverage=self.coverage,
                    score=self.score, feasible=self.score[0] == 0, conflicts=self.conflicts, workload=self.workload)


def contained(slot, windows):
    return any(w.day == slot.day and w.start <= slot.start and slot.end <= w.end
               for w in windows)


def evaluate(sessions, genes, rules, details=False, *, include_resources=False):
    hard = Counter(dict.fromkeys(
        ("teacher", "room", "group", "unassigned", "extra", "duration", "capacity", "availability", "workload", "campus_hours", "semester_shift", "group_room", "teaching_days"), 0))
    soft = Counter(dict.fromkeys(("rescheduled", "room_changes", "gaps", "preferences", "course_distribution"), 0))
    coverage = Counter(dict.fromkeys(("capacity", "availability", "preferences"), 0))
    conflicts = []
    buckets = defaultdict(list)
    minutes = Counter()
    course_days = Counter()

    def violation(kind, *ids):
        hard[kind] += 1
        if details:
            conflicts.append({"type": kind, "sessions": ids})

    hard["extra"] = max(0, len(genes) - len(sessions))
    for index, session in enumerate(sessions):
        gene = genes[index] if index < len(genes) else None
        if gene is None or not gene.room:
            violation("unassigned", session.id)
            continue
        slot = gene.slot
        if session.id in rules.session_days and slot.day not in rules.session_days[session.id]:
            violation("teaching_days", session.id)
        if not session.tutoring:
            key = session.group, session.course, slot.day
            soft['course_distribution'] += course_days[key]
            course_days[key] += 1
        if slot.duration != session.original.slot.duration:
            violation("duration", session.id)
        if not rules.campus_allows(slot):
            violation("campus_hours", session.id)
        if not rules.group_allows(session, slot):
            violation("semester_shift", session.id)
        assigned_room = (rules.group_rooms or {}).get(session.group_key)
        if occupies_group(session) and assigned_room and gene.room != assigned_room:
            violation("group_room", session.id)
        minutes[session.teacher] += slot.duration
        resources = [("teacher", session.teacher), ("room", gene.room)]
        if occupies_group(session):
            resources.append(("group", session.group))
        if session.tutoring and rules.fixed(session) and gene != session.original:
            violation("availability", session.id)
        if session.id in rules.locked_sessions and gene != session.original:
            violation("locked_assignment", session.id)
        for kind, resource in resources:
            buckets[kind, resource, slot.day].append((slot.start, slot.end, session.id))
        size = rules.enrollments.get(session.id)
        capacity = rules.capacities.get(gene.room)
        if size is not None and capacity is not None:
            coverage["capacity"] += 1
            if size > capacity:
                violation("capacity", session.id)
        if session.teacher in rules.availability:
            coverage["availability"] += 1
            if not contained(slot, rules.availability[session.teacher]):
                violation("availability", session.id)
        if session.teacher in rules.preferences:
            coverage["preferences"] += 1
            soft["preferences"] += not contained(slot, rules.preferences[session.teacher])
        soft["rescheduled"] += 3 * (slot != session.original.slot)
        soft["room_changes"] += gene.room != session.original.room

    for (kind, resource, day), intervals in buckets.items():
        if len(intervals) < 2:
            continue
        active = []
        latest_end = 0
        for start, end, session_id in sorted(intervals):
            active = [(until, previous) for until, previous in active if until > start]
            for _, previous in active:
                violation(kind, previous, session_id)
                if details and include_resources:
                    conflicts[-1].update(resource=resource, day=day)
            if latest_end and start > latest_end:
                if kind == "group":
                    soft["gaps"] += (start - latest_end + 59) // 60
                elif kind == "teacher" and rules.soft_weights.get("teacher_gaps"):
                    soft["teacher_gaps"] += (start - latest_end + 59) // 60
            latest_end = max(latest_end, end)
            active.append((end, session_id))
    for teacher, target in rules.weekly_minutes.items():
        if minutes[teacher] != target:
            hard["workload"] += 1
            if details:
                conflicts.append({"type": "workload", "teacher": teacher, "sessions": []})
    workload = {teacher: {"scheduled": minutes[teacher], "target": rules.weekly_minutes.get(teacher)}
                for teacher in sorted({session.teacher for session in sessions})} if details else {}
    if rules.soft_weights:
        for name, weight in rules.soft_weights.items():
            measured = soft[name] // 3 if name == "rescheduled" else soft[name]
            soft[name] = measured * weight
    return Evaluation(dict(hard), dict(soft), dict(coverage), conflicts, workload,
                      dict(buckets) if include_resources else None)

