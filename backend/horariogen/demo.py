import csv
import io
from dataclasses import replace

from .domain import HEADERS, load_csv


def demo_csv(raw):
    sessions = list(load_csv(raw, legacy_hours=True)[:10])
    first, second = sessions[:2]
    sessions[1] = replace(second, teacher=first.teacher, original=first.original)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(HEADERS)
    for s in sessions:
        writer.writerow((s.original.slot.label, s.level, s.section, s.major,
                         s.course, s.teacher, s.original.room, s.program))
    return output.getvalue().encode("utf-8")

