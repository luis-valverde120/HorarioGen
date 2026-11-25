"""Generate the downloadable Excel input template using the application data."""
import csv
import io
import json

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation


def template_workbook(data_folder):
    workbook = Workbook()
    workbook.remove(workbook.active)
    with (data_folder / "horario_semanal.csv").open(encoding="utf-8", newline="") as stream:
        sessions = list(csv.reader(stream, delimiter=";"))
    rules = json.loads((data_folder / "reglas_ejemplo.json").read_text(encoding="utf-8"))
    sheets = {
        "Sesiones": sessions,
        "Aulas": [["Aula", "Capacidad"]] + [[room, None] for room in rules["available_rooms"]],
        "Paralelos": [["Semestre", "Paralelo", "Aula", "Programa_Academico", "Carrera_Especialidad"]] + [
            [key[2], key[3], room, key[0], key[1]]
            for group, room in rules["group_rooms"].items() for key in [json.loads(group)]
        ],
        "Docentes": [["Docente", "Horas_Semanales"]] + [[teacher, minutes / 60] for teacher, minutes in rules["weekly_minutes"].items()],
        "Disponibilidad": [["Docente", "Dia", "Inicio", "Fin"]] + [
            [teacher, slot.split()[0], slot.split()[1], slot.split()[3]]
            for teacher, windows in rules["availability"].items() for slot in windows
        ],
        "Guia": [
            ["Campo", "Cómo completarlo"],
            ["Sesiones", "Una fila por clase o tutoría. Tipo admite Clase o Tutoria."],
            ["Formato sencillo CSV", "Materia, Docente, Grupo, Duracion_Horas y Tipo opcional. Se generan asignaciones iniciales."],
            ["Franja_Horaria", "Monday 08:00 - 10:00. Usa horas de 24 horas y nombres de días en inglés."],
            ["Jornadas", "Semestres impares: 07:00 a 13:00; pares: 14:00 a 20:00. Ambos paralelos respetan esa jornada. Ningún bloque puede atravesar el receso de 13:00 a 14:00."],
            ["Paralelos", "Semestres 1 a 9 con paralelo A o B. La hoja Paralelos asigna el aula que usa cada grupo."],
            ["Duración", "Usa bloques continuos de 1, 2, 3 o 4 horas para las clases."],
            ["Aulas", "Aulas disponibles entre 106 y 112. La capacidad es opcional y requiere datos institucionales."],
            ["Docentes", "Horas de clase y tutoría que debe cumplir por semana. Vacío significa sin meta."],
            ["Disponibilidad", "Registra cada día e intervalo permitido por docente. Las tutorías también deben caber."],
            ["Tutorías", "Las filas de tipo Tutoria reservan la franja y aula y permanecen fijas. Para vincularlas, usa la misma materia, semestre y paralelo de la clase; también reservan al grupo y respetan su jornada."],
            ["Ejemplo", "Los nombres, materias, cargas y disponibilidades de este archivo son ficticios."],
        ],
    }
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 28
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="35276B")
            cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.font = Font(name="Calibri", size=11, color="27334B")
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if cell.row % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor="F3F1FA")
        for column in sheet.columns:
            width = min(48, max(16, max(len(str(cell.value or "")) for cell in column) + 2))
            sheet.column_dimensions[column[0].column_letter].width = width
        if title == "Guia":
            sheet.column_dimensions["B"].width = 85
            for index in range(2, sheet.max_row + 1):
                sheet.row_dimensions[index].height = 34
    rooms = DataValidation(type="list", formula1='"106,107,108,109,110,111,112"')
    rooms.errorTitle = "Aula no disponible"
    rooms.error = "Selecciona un aula entre la 106 y la 112."
    rooms.showErrorMessage = True
    rooms.errorStyle = "stop"
    workbook["Aulas"].add_data_validation(rooms)
    rooms.add("A2:A100")
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()

