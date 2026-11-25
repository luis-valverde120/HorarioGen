import json
from collections import defaultdict

from .domain import DAYS, HEADERS
from .imports import canonical_csv


def demonstration(curriculum, sections=1):
    """Build a clearly synthetic schedule independently of curriculum hours."""
    rooms = curriculum["rooms"]
    campus = [f"{day} {start} - {end}" for day in DAYS[:5]
              for start, end in (("07:00", "13:00"), ("14:00", "20:00"))]
    rows = []
    group_windows = {}
    teacher_count = curriculum["reference_teacher_count"]
    occupied_teachers = defaultdict(set)
    next_teacher = 0
    semesters = (1, 2, 3, 5, 4, 6, 7, 8, 9)
    for group_index in range(9 * sections):
        semester_index, section = divmod(group_index, sections)
        semester = semesters[semester_index]
        subjects = [s for s in curriculum["subjects"] if s["semester"] == semester]
        # Sharing four rooms between the first eight five-subject groups leaves
        # ten distinct room/shift combinations for the remaining groups.
        packed = sections == 2 and group_index < 8
        lane = group_index // 2 if packed else group_index - (4 if sections == 2 else 0)
        room = rooms[lane % len(rooms)]
        start_hour = 7 if lane < len(rooms) else 14
        group = (curriculum["program"], "Computación", f"Semestre {semester}", "AB"[section])
        group_windows[json.dumps(group, ensure_ascii=False, separators=(",", ":"))] = [
            f"{day} {start_hour:02}:00 - {start_hour + 6:02}:00" for day in DAYS[:5]
        ]
        for index, subject in enumerate(subjects):
            offset = (group_index % 2 if packed else index // 5) * 3
            start = start_hour + offset
            day = DAYS[index % 5]
            taken = occupied_teachers[day, start]
            while next_teacher % teacher_count in taken:
                next_teacher += 1
            taken.add(next_teacher % teacher_count)
            teacher = f"Docente demo {next_teacher % teacher_count + 1:02}"
            next_teacher += 1
            for beginning, end, kind in ((start, start + 2, "Clase"), (start + 2, start + 3, "Tutoria")):
                values = (f"{day} {beginning:02}:00 - {end:02}:00", group[2], group[3],
                          group[1], subject["name"], teacher, room, group[0], kind)
                rows.append(dict(zip((*HEADERS, "Tipo"), values, strict=True)))
    return canonical_csv(rows, (*HEADERS, "Tipo")), {
        "campus_windows": campus, "group_windows": group_windows,
    }
