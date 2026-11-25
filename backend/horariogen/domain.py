import csv
import json
import io
import re
from dataclasses import dataclass, field

HEADERS = (
    "Franja_Horaria", "Nivel_Semestre", "Paralelo_Grupo", "Carrera_Especialidad",
    "Codigo_Asignatura", "Docente", "Aula", "Programa_Academico",
)
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
SPAN = re.compile(r"([A-Za-z]+)\s+(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})")


@dataclass(frozen=True, order=True)
class Slot:
    day: int
    start: int
    end: int

    def __post_init__(self):
        if not (0 <= self.day < 7 and 0 <= self.start < self.end <= 1440):
            raise ValueError("Intervalo semanal inválido")

    @property
    def label(self):
        start = f"{self.start // 60:02}:{self.start % 60:02}"
        end = f"{self.end // 60:02}:{self.end % 60:02}"
        return f"{DAYS[self.day]} {start} - {end}"

    @property
    def duration(self):
        return self.end - self.start


def parse_slot(value: str, legacy_hours=False):
    match = SPAN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Franja inválida: {value}")
    day, sh, sm, eh, em = match.groups()
    sh, sm, eh, em = map(int, (sh, sm, eh, em))
    if not (sm < 60 and em < 60 and sh < 24 and eh <= 24):
        raise ValueError(f"Hora inválida: {value}")
    if legacy_hours:
        sh = sh + 12 if 1 <= sh <= 7 else sh
        eh = eh + 12 if 1 <= eh <= 7 else eh
    return Slot(DAYS.index(day.title()), sh * 60 + sm, eh * 60 + em)


@dataclass(frozen=True)
class Gene:
    slot: Slot
    room: str


@dataclass(frozen=True)
class Session:
    id: int
    level: str
    section: str
    major: str
    course: str
    teacher: str
    program: str
    original: Gene
    tutoring: bool = False

    @property
    def group_key(self):
        return json.dumps(self.group, ensure_ascii=False, separators=(",", ":"))

    @property
    def group(self):
        return self.program, self.major, self.level, self.section


@dataclass(frozen=True)
class Rules:
    capacities: dict
    enrollments: dict
    availability: dict
    preferences: dict
    weekly_minutes: dict
    available_rooms: tuple = ()
    group_rooms: dict = field(default_factory=dict)
    enforce_hours: bool = True
    session_days: dict = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload):
        def windows(field):
            return {
                name: tuple(parse_slot(slot) for slot in slots)
                for name, slots in payload.get(field, {}).items()
            }
        return cls(payload.get("capacities", {}), payload.get("enrollments", {}),
                   windows("availability"), windows("preferences"), {teacher: value for teacher, value in payload.get("weekly_minutes", {}).items() if value is not None}, tuple(payload.get("available_rooms", ())), payload.get("group_rooms", {}), payload.get("enforce_hours", True), {int(k): tuple(v) for k, v in payload.get("session_days", {}).items()})


def load_csv(raw: bytes, legacy_hours=False):
    data = raw.decode("utf-8-sig")
    header = data.splitlines()[0] if data.splitlines() else ""
    delimiter = next((d for d in (";", ",", "\t") if d in header), ";")
    rows = csv.reader(io.StringIO(data, newline=""), delimiter=delimiter, strict=True)
    fields = tuple(next(rows, ()))
    expected = (*HEADERS, "Tipo") if "Tipo" in fields else HEADERS
    if len(fields) != len(expected) or set(fields) != set(expected):
        raise ValueError("El encabezado requiere las ocho columnas de HorarioGen y admite Tipo como opción")
    sessions = []
    for row in rows:
        if not row:
            continue
        if len(row) != len(fields) or any(not value.strip() for value in row):
            raise ValueError(f"Fila {rows.line_num}: faltan valores o hay columnas adicionales")
        franja, level, section, major, course, teacher, room, program = (
            row[fields.index(field)].strip() for field in HEADERS
        )
        try:
            slot = parse_slot(franja, legacy_hours)
        except ValueError as exc:
            raise ValueError(f"Fila {rows.line_num}: {exc}") from exc
        kind = row[fields.index("Tipo")].strip().lower() if "Tipo" in fields else "clase"
        if kind not in ("clase", "tutoria", "tutoría"):
            raise ValueError(f"Fila {rows.line_num}: Tipo debe ser Clase o Tutoría")
        sessions.append(Session(len(sessions) + 1, level, section, major, course,
                                teacher, program, Gene(slot, room), tutoring=kind != "clase"))
    if not sessions:
        raise ValueError("El archivo debe contener al menos una sesión")
    return tuple(sessions)


def session_payload(session, gene):
    return {
        "id": session.id, "level": session.level, "section": session.section,
        "major": session.major, "course": session.course, "teacher": session.teacher,
        "program": session.program, "room": gene.room, "day": gene.slot.day,
        "start": gene.slot.start, "end": gene.slot.end, "slot": gene.slot.label,
        "kind": "tutoring" if session.tutoring else "class", "group_key": session.group_key,
    }



def within_campus_hours(slot):
    return (420 <= slot.start < slot.end <= 780 or 840 <= slot.start < slot.end <= 1200)


def semester_number(session):
    match = re.fullmatch(r"Semestre ([1-9])", session.level)
    return int(match[1]) if match else None


def within_semester_shift(session, slot):
    number = semester_number(session)
    if number is None:
        return True
    beginning, closing = (420, 780) if number % 2 else (840, 1200)
    return beginning <= slot.start < slot.end <= closing


def occupies_group(session):
    return not session.tutoring or semester_number(session) is not None
