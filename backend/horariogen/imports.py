"""Read scheduling inputs from CSV or an Excel workbook."""
import csv
import io
import re
import unicodedata
from zipfile import BadZipFile, ZipFile

from .domain import DAYS, HEADERS, load_csv, parse_slot

ROOMS = tuple(str(room) for room in range(106, 113))
SIMPLE_HEADERS = ("Materia", "Docente", "Grupo", "Duracion_Horas", "Tipo")
SPANISH_DAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


def plain(value):
    return "".join(c for c in unicodedata.normalize("NFD", str(value).strip()) if not unicodedata.combining(c)).lower()


def room_name(value):
    value = str(value).strip()
    if value.lower().startswith("aula "):
        value = value[5:].strip()
    if value.endswith(".0"):
        value = value[:-2]
    if value not in ROOMS:
        raise ValueError("Las aulas admitidas son 106, 107, 108, 109, 110, 111 y 112.")
    return value


def canonical_csv(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def table_rows(sheet):
    rows = iter(sheet.iter_rows(values_only=True))
    fields = tuple(str(value).strip() if value is not None else "" for value in next(rows, ()))
    if not fields or len(set(fields)) != len(fields):
        raise ValueError(f"Hoja {sheet.title}: encabezado vacío o duplicado.")
    if not all(fields):
        raise ValueError(f"Hoja {sheet.title}: hay columnas sin nombre.")
    result = []
    for index, values in enumerate(rows, 2):
        if all(value is None for value in values):
            continue
        if any(isinstance(value, str) and value.startswith("=") for value in values):
            raise ValueError(f"Hoja {sheet.title}, fila {index}: reemplaza las fórmulas por valores.")
        result.append(dict(zip(fields, ("" if value is None else str(value).strip() for value in values), strict=True)))
    return result, fields


def simple_sessions(rows):
    output = []
    for index, row in enumerate(rows):
        try:
            hours = float(row["Duracion_Horas"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Sesión {index + 1}: Duracion_Horas debe ser un número de 1 a 4.") from exc
        if hours not in (1, 2, 3, 4):
            raise ValueError(f"Sesión {index + 1}: usa bloques de 1, 2, 3 o 4 horas.")
        # Seed assignments are a starting point for optimization.
        day = index % 5
        start = (7, 9, 14)[(index // 5) % 3]
        output.append(dict(zip((*HEADERS, "Tipo"), (
            f"{DAYS[day]} {start:02}:00 - {start + int(hours):02}:00",
            row.get("Semestre") or row.get("Nivel_Semestre") or "Semestre 1", row.get("Grupo", ""),
            row.get("Carrera_Especialidad") or "General", row.get("Materia", ""),
            row.get("Docente", ""), ROOMS[index % len(ROOMS)],
            row.get("Programa_Academico") or "General", row.get("Tipo") or "Clase",
        ))))
    return output


def read_import(raw, filename, legacy=False):
    rules = {}
    warnings = []
    rooms = list(ROOMS)
    parallel_rows = []
    if filename.lower().endswith(".xlsx"):
        from openpyxl import load_workbook
        try:
            with ZipFile(io.BytesIO(raw)) as archive:
                if sum(part.file_size for part in archive.infolist()) > 30 * 1024 * 1024:
                    raise ValueError("El Excel descomprimido supera 30 MiB.")
            book = load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
            try:
                if "Sesiones" not in book.sheetnames:
                    raise ValueError("El Excel debe incluir una hoja llamada Sesiones.")
                rows, fields = table_rows(book["Sesiones"])
                if "Aulas" in book.sheetnames:
                    room_rows, room_fields = table_rows(book["Aulas"])
                    if "Aula" not in room_fields:
                        raise ValueError("La hoja Aulas requiere la columna Aula.")
                    rooms = [room_name(row["Aula"]) for row in room_rows]
                    if not rooms or len(set(rooms)) != len(rooms):
                        raise ValueError("Registra al menos un aula y evita duplicados.")
                    capacities = {room_name(row["Aula"]): int(row["Capacidad"]) for row in room_rows if row.get("Capacidad")}
                    rules["capacities"] = capacities
                if "Paralelos" in book.sheetnames:
                    parallel_rows, parallel_fields = table_rows(book["Paralelos"])
                    if not {"Semestre", "Paralelo", "Aula"} <= set(parallel_fields):
                        raise ValueError("La hoja Paralelos requiere Semestre, Paralelo y Aula.")
                if "Docentes" in book.sheetnames:
                    teacher_rows, teacher_fields = table_rows(book["Docentes"])
                    if not {"Docente", "Horas_Semanales"} <= set(teacher_fields):
                        raise ValueError("La hoja Docentes requiere Docente y Horas_Semanales.")
                    if len({row["Docente"] for row in teacher_rows}) != len(teacher_rows):
                        raise ValueError("La hoja Docentes contiene nombres duplicados.")
                    rules["weekly_minutes"] = {row["Docente"]: round(float(row["Horas_Semanales"]) * 60)
                                               for row in teacher_rows if row["Horas_Semanales"]}
                if "Disponibilidad" in book.sheetnames:
                    window_rows, window_fields = table_rows(book["Disponibilidad"])
                    if not {"Docente", "Dia", "Inicio", "Fin"} <= set(window_fields):
                        raise ValueError("La hoja Disponibilidad requiere Docente, Dia, Inicio y Fin.")
                    availability = {}
                    for row in window_rows:
                        key = plain(row["Dia"])
                        day = SPANISH_DAYS.index(key) if key in SPANISH_DAYS else DAYS.index(row["Dia"].title())
                        start, end = row["Inicio"][:5], row["Fin"][:5]
                        availability.setdefault(row["Docente"], []).append(f"{DAYS[day]} {start} - {end}")
                    rules["availability"] = availability
            finally:
                book.close()
        except (BadZipFile, KeyError, TypeError, OverflowError) as exc:
            raise ValueError("El archivo Excel es inválido o contiene valores incompatibles.") from exc
    elif filename.lower().endswith(".csv"):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Guarda el CSV con codificación UTF-8.") from exc
        delimiter = next((item for item in (";", ",", "\t") if item in text.splitlines()[0]), ";") if text.splitlines() else ";"
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError("El CSV contiene filas incompletas o columnas adicionales.")
    else:
        raise ValueError("Selecciona un archivo .csv o .xlsx.")
    if not rows:
        raise ValueError("Registra al menos una sesión.")
    if len(rows) > 3000:
        raise ValueError("Esta versión admite hasta 3000 sesiones por archivo.")
    if {"Materia", "Docente", "Grupo", "Duracion_Horas"} <= set(fields):
        rows = simple_sessions(rows)
        for index, row in enumerate(rows):
            row["Aula"] = rooms[index % len(rooms)]
        fields = (*HEADERS, "Tipo")
        legacy = False
        warnings.append("Se generaron asignaciones iniciales para las sesiones. Ejecuta la optimización para evaluar y reorganizar el horario.")
    elif not set(HEADERS) <= set(fields):
        raise ValueError("Usa la plantilla o las columnas Materia, Docente, Grupo y Duracion_Horas.")
    for row in rows:
        row["Aula"] = room_name(row["Aula"])
        if row["Aula"] not in rooms:
            raise ValueError(f"El aula {row['Aula']} de una sesión está ausente de la hoja Aulas.")
    for row in rows:
        if plain(row.get("Tipo", "Clase")) == "clase" or re.search(r"[1-9]", str(row["Nivel_Semestre"])):
            row["Nivel_Semestre"] = semester_name(row["Nivel_Semestre"])
            row["Paralelo_Grupo"] = parallel_name(row["Paralelo_Grupo"])
        row["Franja_Horaria"] = parse_slot(row["Franja_Horaria"], legacy).label
    fields = (*HEADERS, "Tipo") if "Tipo" in fields else HEADERS
    normalized = canonical_csv([{field: row.get(field, "") for field in fields} for row in rows], fields)
    sessions = load_csv(normalized)
    group_rooms = {}
    for session in sessions:
        if not session.tutoring:
            group_rooms.setdefault(session.group_key, session.original.room)
    seen = set()
    for row in parallel_rows:
        level, section, room = semester_name(row["Semestre"]), parallel_name(row["Paralelo"]), room_name(row["Aula"])
        if room not in rooms:
            raise ValueError(f"El aula {room} del paralelo está ausente de la hoja Aulas.")
        matches = [session for session in sessions if not session.tutoring and session.level == level and session.section == section
                   and (not row.get("Programa_Academico") or session.program == row["Programa_Academico"])
                   and (not row.get("Carrera_Especialidad") or session.major == row["Carrera_Especialidad"])]
        if not matches:
            raise ValueError(f"El paralelo {level} {section} no tiene sesiones.")
        for session in matches:
            if session.group_key in seen and group_rooms[session.group_key] != room:
                raise ValueError(f"El paralelo {level} {section} tiene asignaciones de aula contradictorias.")
            seen.add(session.group_key)
            group_rooms[session.group_key] = room
    rules["group_rooms"] = group_rooms
    rules["available_rooms"] = rooms
    if not rules.get("availability"):
        warnings.append("Falta disponibilidad docente. Regístrala antes de considerar el cumplimiento institucional.")
    return normalized, sessions, rules, warnings



def semester_name(value):
    match = re.search(r"\d+", str(value))
    if not match or not 1 <= int(match.group()) <= 9:
        raise ValueError("Las clases deben indicar un semestre del 1 al 9.")
    return f"Semestre {int(match.group())}"


def parallel_name(value):
    value = plain(value).replace("paralelo", "").replace("grupo", "").strip()
    if value in ("a", "1", "01"):
        return "A"
    if value in ("b", "2", "02"):
        return "B"
    raise ValueError("Usa paralelo A o B, equivalentes a 1 y 2.")
