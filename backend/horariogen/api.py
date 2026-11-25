import csv
from dataclasses import replace
import io
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt, model_validator

from .domain import HEADERS, Gene, Rules, Session, Slot, load_csv, parse_slot, session_payload
from .genetic import Config, optimize
from .imports import ROOMS, read_import
from .workbook import template_workbook
from .storage import FileRepository, Repository
from .teaching import build_plan

PROJECT = Path(__file__).resolve().parents[2]
BUNDLED = PROJECT / "data" / "horario_semanal.csv"
WEEKLY_ID = "00000000-0000-4000-8000-000000000014"
PREVIOUS_BUNDLES = {"00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"}
LOGGER = logging.getLogger(__name__)
MAX_BYTES = 5 * 1024 * 1024


class Parameters(BaseModel):
    population: int = Field(40, ge=4, le=200)
    generations: int = Field(100, ge=0, le=1000)
    seconds: float = Field(10, ge=0.01, le=120)
    mutation: float = Field(0.35, ge=0, le=1)
    tournament: int = Field(3, ge=2, le=200)
    elite: int = Field(2, ge=1, le=199)
    seed: int = Field(42, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def validate_population(self):
        if self.tournament > self.population or self.elite >= self.population:
            raise ValueError("El torneo debe caber en la población y la élite debe ser menor")
        return self


class TutoringInput(BaseModel):
    session_id: int | None = Field(default=None, ge=1)
    teacher: str
    room: str
    slot: str


class RuleInput(BaseModel):
    capacities: dict[str, PositiveInt] = Field(default_factory=dict)
    enrollments: dict[PositiveInt, NonNegativeInt] = Field(default_factory=dict)
    availability: dict[str, list[str]] = Field(default_factory=dict)
    preferences: dict[str, list[str]] = Field(default_factory=dict)
    weekly_minutes: dict[str, NonNegativeInt | None] = Field(default_factory=dict)
    class_minutes: dict[PositiveInt, int] = Field(default_factory=dict)
    session_days: dict[PositiveInt, list[Literal[0, 1, 2, 3, 4]]] = Field(default_factory=dict)
    tutoring: list[TutoringInput] = Field(default_factory=list)
    group_rooms: dict[str, str] = Field(default_factory=dict)
    available_rooms: list[str] = Field(default_factory=lambda: list(ROOMS))


class OptimizationInput(BaseModel):
    dataset_id: UUID
    parameters: Parameters = Field(default_factory=Parameters)
    rules: RuleInput = Field(default_factory=RuleInput)


class TeachingAssignment(BaseModel):
    source_id: PositiveInt
    course: str = Field(min_length=1, max_length=180)
    teacher: str = Field(min_length=1, max_length=180)
    weekly_hours: int = Field(ge=1, le=30)
    block_hours: int = Field(ge=1, le=4)
    days: list[Literal[0, 1, 2, 3, 4]] = Field(min_length=1, max_length=5)


class TeachingPlanInput(BaseModel):
    assignments: list[TeachingAssignment] = Field(min_length=1, max_length=250)
    use_assigned_load: bool = True


def create_app(repository: Repository | None = None):
    def register(repo, name, raw, legacy, identifier=None, preset=None):
        normalized, sessions, imported, warnings = read_import(raw, name, legacy)
        rules = {**imported, **(preset or {})}
        # Apply the same validation to workbook metadata and API-supplied rules.
        validated = RuleInput.model_validate(rules)
        Rules.from_payload(validated.model_dump())
        teachers = {s.teacher for s in sessions}
        if (validated.availability.keys() | validated.weekly_minutes.keys()) - teachers:
            raise ValueError("Hay reglas de docentes que no aparecen en Sesiones.")
        record = dict(id=identifier or str(uuid4()), name=name, count=len(sessions),
                      legacy_hours=False,
                      rules=validated.model_dump(), warnings=warnings if not preset else [],
                      rooms=validated.available_rooms, teachers=len(teachers),
                      classes=sum(not s.tutoring for s in sessions), tutoring=sum(s.tutoring for s in sessions))
        repo.save_original(record["id"], normalized)
        repo.save_source(record["id"], raw)
        repo.put("datasets", record)
        return record

    @asynccontextmanager
    async def lifespan(app):
        repo = repository or FileRepository(Path(os.environ.get("HORARIOGEN_DATA", PROJECT / "storage")))
        app.state.repo = repo
        for run in repo.all("runs"):
            if run["status"] in {"queued", "running"}:
                repo.put("runs", {**run, "status": "failed", "error": "La ejecución fue interrumpida"})
        if BUNDLED.is_file():
            try:
                repo.get("datasets", WEEKLY_ID)
            except FileNotFoundError:
                register(repo, "Escenario académico v0.1.4.csv", BUNDLED.read_bytes(), False, WEEKLY_ID,
                         json.loads((PROJECT / "data" / "reglas_ejemplo.json").read_text(encoding="utf-8")))
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="horariogen") as executor:
            app.state.executor = executor
            yield

    app = FastAPI(title="HorarioGen", version="0.1.4", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("HORARIOGEN_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )

    def repo():
        return app.state.repo

    def get(collection, identifier):
        try:
            return repo().get(collection, str(identifier))
        except FileNotFoundError as exc:
            raise HTTPException(404, "Identificador no encontrado") from exc

    def sessions_for(dataset):
        return load_csv(repo().original(dataset["id"]), dataset["legacy_hours"])

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/datasets/import", status_code=201)
    def import_dataset(file: UploadFile = File(...), legacy_hours: bool = Form(False)):
        raw = file.file.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "El CSV supera 5 MiB")
        try:
            return register(repo(), file.filename or "dataset.csv", raw, legacy_hours)
        except (ValueError, csv.Error) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/datasets")
    def datasets():
        return [item for item in repo().all("datasets") if item["id"] not in PREVIOUS_BUNDLES]

    @app.get("/api/templates/{format}")
    def template(format: str):
        if format == "csv":
            return Response((PROJECT / "data" / "plantilla_sesiones.csv").read_bytes(), media_type="text/csv",
                            headers={"Content-Disposition": 'attachment; filename="HorarioGen-v0.1.4.csv"'})
        if format == "xlsx":
            return Response(template_workbook(PROJECT / "data"), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": 'attachment; filename="HorarioGen-v0.1.4.xlsx"'})
        raise HTTPException(404, "Plantilla no encontrada")

    @app.get("/api/datasets/{identifier}/sessions")
    def dataset_sessions(identifier: UUID):
        sessions = sessions_for(get("datasets", identifier))
        return [session_payload(s, s.original) for s in sessions]

    @app.post('/api/datasets/{identifier}/teaching-plan', status_code=201)
    def teaching_plan(identifier: UUID, request: TeachingPlanInput):
        dataset = get('datasets', identifier)
        payload = dict(dataset.get('rules', {}))
        try:
            planned, days, source_ids = build_plan(sessions_for(dataset), request.assignments, Rules.from_payload(payload))
            payload['session_days'] = days
            payload['class_minutes'] = {}
            payload['tutoring'] = []
            payload['enrollments'] = {new: payload.get('enrollments', {}).get(str(old), payload.get('enrollments', {}).get(old))
                                     for new, old in source_ids.items()
                                     if str(old) in payload.get('enrollments', {}) or old in payload.get('enrollments', {})}
            teachers = {s.teacher for s in planned}
            groups = {s.group_key for s in planned if not s.tutoring}
            payload['group_rooms'] = {key: room for key, room in payload.get('group_rooms', {}).items() if key in groups}
            for field in ('availability', 'preferences', 'weekly_minutes'):
                payload[field] = {teacher: value for teacher, value in payload.get(field, {}).items() if teacher in teachers}
            if request.use_assigned_load:
                payload['weekly_minutes'] = {teacher: sum(s.original.slot.duration for s in planned if s.teacher == teacher) for teacher in teachers}
            output = io.StringIO(newline='')
            writer = csv.writer(output, delimiter=';')
            writer.writerow((*HEADERS, 'Tipo'))
            for s in planned:
                writer.writerow([s.original.slot.label, s.level, s.section, s.major, s.course,
                                 s.teacher, s.original.room, s.program, 'Tutoria' if s.tutoring else 'Clase'])
            raw = output.getvalue().encode('utf-8-sig')
            record = register(repo(), 'Plan docente v0.1.4.csv', raw, False, preset=payload)
            record['warnings'] = ['Plan guardado como un conjunto nuevo. Genera el horario para comprobar los cruces, la disponibilidad y la carga.']
            repo().put('datasets', record)
            return record
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def execute(run, sessions, rules, config):
        def save(**fields):
            run.update(fields)
            repo().put("runs", run)

        progress_history = []

        def publish(point):
            progress_history.append(point)
            save(progress=point, history=progress_history)

        try:
            save(status="running")
            genes, baseline, result, history, reason = optimize(
                sessions, rules, config, progress=publish,
            )
            rows = [session_payload(s, g) for s, g in zip(sessions, genes, strict=True)]
            save(status="completed", reason=reason, history=history, result={
                "original": [session_payload(s, s.original) for s in sessions],
                "optimized": rows, "baseline": baseline.payload(), "evaluation": result.payload(),
            })
        except Exception:
            LOGGER.exception("Falló la optimización %s", run["id"])
            save(status="failed", error="Falló la optimización. Consulte el registro del servidor.")

    @app.post("/api/optimizations", status_code=202)
    def submit(request: OptimizationInput):
        dataset = get("datasets", request.dataset_id)
        sessions = sessions_for(dataset)
        provided = request.rules.model_dump(exclude_unset=True)
        merged = dict(dataset.get("rules", {}))
        for key, value in provided.items():
            merged[key] = {**merged.get(key, {}), **value} if isinstance(value, dict) else value
        inputs = RuleInput.model_validate(merged)
        valid_groups = {s.group_key for s in sessions if not s.tutoring}
        if inputs.group_rooms.keys() - valid_groups or set(inputs.group_rooms.values()) - set(inputs.available_rooms):
            raise HTTPException(422, "Revisa los paralelos y sus aulas asignadas.")
        valid_teachers = {s.teacher for s in sessions}
        valid_rooms = set(inputs.available_rooms)
        if not valid_rooms or valid_rooms - set(ROOMS) or len(valid_rooms) != len(inputs.available_rooms):
            raise HTTPException(422, "Selecciona aulas únicas entre la 106 y la 112.")
        if {s.original.room for s in sessions} - valid_rooms:
            raise HTTPException(422, "Las asignaciones iniciales contienen aulas fuera de la lista disponible.")
        valid_classes = {s.id for s in sessions if not s.tutoring}
        if (inputs.enrollments.keys() - {s.id for s in sessions}
                or inputs.session_days.keys() - valid_classes
                or inputs.class_minutes.keys() - valid_classes
                or inputs.capacities.keys() - valid_rooms
                or (inputs.availability.keys() | inputs.preferences.keys() | inputs.weekly_minutes.keys()) - valid_teachers):
            raise HTTPException(422, "Las reglas hacen referencia a sesiones, docentes o aulas desconocidos")
        try:
            rules = Rules.from_payload(inputs.model_dump())
            adjusted = []
            for session in sessions:
                minutes = inputs.class_minutes.get(session.id)
                if minutes is not None:
                    if minutes not in (60, 120, 180, 240):
                        raise ValueError("La duración de clase debe ser de 1 a 4 horas completas.")
                    slot = session.original.slot
                    session = replace(session, original=replace(session.original, slot=Slot(slot.day, slot.start, slot.start + minutes)))
                adjusted.append(session)
            tutoring_keys = {(s.teacher, s.original.slot) for s in adjusted if s.tutoring}
            for item in inputs.tutoring:
                if item.teacher not in valid_teachers or item.room not in valid_rooms:
                    raise ValueError("Selecciona un docente y un aula del horario para la tutoría.")
                slot = parse_slot(item.slot)
                key = item.teacher, slot
                if key in tutoring_keys:
                    raise ValueError("Esta tutoría ya está registrada para el docente.")
                tutoring_keys.add(key)
                if item.session_id is not None:
                    source = next((s for s in sessions if s.id == item.session_id and not s.tutoring), None)
                    if source is None or source.teacher != item.teacher:
                        raise ValueError("Selecciona una materia impartida por el docente de tutoría.")
                    adjusted.append(replace(source, id=len(adjusted) + 1, original=Gene(slot, item.room), tutoring=True))
                else:
                    adjusted.append(Session(len(adjusted) + 1, "—", "—", "—", "Tutoría", item.teacher, "—",
                                            Gene(slot, item.room), tutoring=True))
            sessions = tuple(adjusted)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        run = dict(id=str(uuid4()), dataset_id=dataset["id"], status="queued",
                   created_at=datetime.now(timezone.utc).isoformat(), progress=None,
                   parameters=request.parameters.model_dump(), rules=inputs.model_dump())
        repo().put("runs", run)
        app.state.executor.submit(execute, run.copy(), sessions, rules, Config(**run["parameters"]))
        return run

    @app.get("/api/optimizations/{identifier}")
    def status(identifier: UUID):
        return {k: v for k, v in get("runs", identifier).items() if k not in {"history", "result"}}

    def completed(identifier):
        run = get("runs", identifier)
        if run["status"] != "completed":
            raise HTTPException(409, "El resultado todavía no está disponible")
        return run

    @app.get("/api/optimizations/{identifier}/result")
    def result(identifier: UUID):
        return completed(identifier)["result"]

    @app.get("/api/optimizations/{identifier}/metrics")
    def metrics(identifier: UUID):
        run = get("runs", identifier)
        return {"history": run.get("history", []), "best": run.get("progress"), "reason": run.get("reason")}

    @app.get("/api/optimizations/{identifier}/export")
    def export(identifier: UUID):
        rows = completed(identifier)["result"]["optimized"]
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        has_tutoring = any(row.get("kind") == "tutoring" for row in rows)
        writer.writerow((*HEADERS, "Tipo") if has_tutoring else HEADERS)
        for row in rows:
            values = [row[key] for key in ("slot", "level", "section", "major", "course", "teacher", "room", "program")]
            if has_tutoring:
                values.append("Tutoria" if row.get("kind") == "tutoring" else "Clase")
            writer.writerow(values)
        return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="horariogen-optimizado.csv"'})

    return app


app = create_app()

