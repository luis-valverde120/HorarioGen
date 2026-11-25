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
from threading import Lock
from uuid import UUID, uuid4
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt, model_validator

from .domain import HEADERS, Gene, Rules, Session, Slot, load_csv, occupies_group, parse_slot, session_payload
from .genetic import Config, optimize
from .imports import ROOMS, UPEC_ROOMS, read_import
from .reference import demonstration
from .feasibility import validate_feasibility
from .workbook import template_workbook
from .storage import FileRepository, Repository
from .teaching import build_plan
from .working_memory import OptimizationCancelled, WorkingMemory
from .evaluation import evaluate

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
    session_days: dict[PositiveInt, list[Literal[0, 1, 2, 3, 4, 5]]] = Field(default_factory=dict)
    tutoring: list[TutoringInput] = Field(default_factory=list)
    group_rooms: dict[str, str] = Field(default_factory=dict)
    available_rooms: list[str] = Field(default_factory=lambda: list(ROOMS))
    campus_windows: list[str] | None = None
    group_windows: dict[str, list[str]] = Field(default_factory=dict)
    locked_sessions: list[PositiveInt] = Field(default_factory=list)
    movable_tutoring: list[PositiveInt] = Field(default_factory=list)
    soft_weights: dict[Literal["rescheduled", "room_changes", "gaps", "teacher_gaps",
                               "preferences", "course_distribution"], NonNegativeInt] = Field(default_factory=dict)


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
    days: list[Literal[0, 1, 2, 3, 4, 5]] = Field(min_length=1, max_length=6)
    class_blocks: list[Literal[1, 2, 3, 4]] | None = Field(default=None, max_length=30)
    tutorial_blocks: list[Literal[1, 2, 3, 4]] | None = Field(default=None, max_length=30)


class TeachingPlanInput(BaseModel):
    assignments: list[TeachingAssignment] = Field(min_length=1, max_length=250)
    use_assigned_load: bool = True


class MemorySnapshot(BaseModel):
    run_id: str
    scenario_id: str
    status: str
    generation: int | None = None
    maximum_generations: int = 0
    seed: int | None = None
    population_size: int = 0
    best: dict | None = None
    facts: dict = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    conflict_total: int = 0
    repairs: int = 0
    preview: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)


def create_app(repository: Repository | None = None):
    active_memory: dict[str, WorkingMemory] = {}
    memory_lock = Lock()
    def register(repo, name, raw, legacy, identifier=None, preset=None, academic_context=None):
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
        if academic_context is not None:
            record["academic_context"] = academic_context
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

    @app.get("/api/curriculum")
    def curriculum():
        return json.loads((PROJECT / "data" / "upec_computacion.json").read_text(encoding="utf-8"))

    @app.post("/api/curriculum/demonstration", status_code=201)
    def curriculum_demo(groups: Literal["1", "2"] = "1",
                        period: str = Query("Demostración", min_length=1, max_length=80)):
        count = int(groups)
        catalog = curriculum()
        raw, preset = demonstration(catalog, count)
        return register(repo(), f"Demostración UPEC · {period} · {count} por semestre.csv", raw, False, preset=preset,
                        academic_context={"period": period, "curriculum_id": catalog["id"], "synthetic": True})

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
            previous = sessions_for(dataset)
            planned, days, source_ids = build_plan(previous, request.assignments, Rules.from_payload(payload))
            previous_tutoring = {s.id for s in previous if s.tutoring}
            old_movable = set(payload.get("movable_tutoring", ()))
            payload["movable_tutoring"] = [s.id for s in planned if s.tutoring and
                                           (source_ids[s.id] not in previous_tutoring or source_ids[s.id] in old_movable)]
            payload['session_days'] = days
            payload['class_minutes'] = {}
            payload["locked_sessions"] = []
            payload['tutoring'] = []
            payload['enrollments'] = {new: payload.get('enrollments', {}).get(str(old), payload.get('enrollments', {}).get(old))
                                     for new, old in source_ids.items()
                                     if str(old) in payload.get('enrollments', {}) or old in payload.get('enrollments', {})}
            teachers = {s.teacher for s in planned}
            groups = {s.group_key for s in planned if not s.tutoring}
            for field in ("group_rooms", "group_windows"):
                payload[field] = {key: value for key, value in payload.get(field, {}).items() if key in groups}
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
            record = register(repo(), 'Plan docente v0.1.4.csv', raw, False, preset=payload,
                              academic_context=dataset.get("academic_context"))
            record['warnings'] = ['Plan guardado como un conjunto nuevo. Genera el horario para comprobar los cruces, la disponibilidad y la carga.']
            repo().put('datasets', record)
            return record
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def execute(run, sessions, rules, config, memory):
        def save(**fields):
            run.update(fields)
            repo().put("runs", run)

        progress_history = []

        def publish(point):
            progress_history.append(point)
            save(progress=point, history=progress_history)

        try:
            if memory.cancelled.is_set():
                raise OptimizationCancelled
            memory.update(status="running")
            memory.emit("RUN_STARTED")
            assessment = evaluate(sessions, [s.original for s in sessions], rules)
            memory.update(
                facts={"sessions": len(sessions), "teachers": sorted({s.teacher for s in sessions}),
                       "rooms": list(rules.available_rooms),
                       "groups": sorted({s.group_key for s in sessions if not s.tutoring}),
                       "tutorials": sum(s.tutoring for s in sessions)},
                constraints=list(assessment.hard),
            )
            memory.emit("FACTS_LOADED")
            save(status="running")
            genes, baseline, result, history, reason = optimize(
                sessions, rules, config, progress=publish, memory=memory,
            )
            rows = [session_payload(s, g) for s, g in zip(sessions, genes, strict=True)]
            with memory_lock:
                if memory.cancelled.is_set():
                    raise OptimizationCancelled
                memory.update(status="completed")
                memory.emit("RUN_COMPLETED", reason=reason)
                save(status="completed", reason=reason, history=history, memory=memory.snapshot(), result={
                    "original": [session_payload(s, s.original) for s in sessions],
                    "optimized": rows, "baseline": baseline.payload(), "evaluation": result.payload(),
                })
        except OptimizationCancelled:
            memory.update(status="cancelled")
            memory.emit("RUN_CANCELLED")
            save(status="cancelled", memory=memory.snapshot())
        except Exception:
            LOGGER.exception("Falló la optimización %s", run["id"])
            memory.update(status="failed")
            memory.emit("RUN_FAILED")
            save(status="failed", memory=memory.snapshot(),
                 error="Falló la optimización. Consulte el registro del servidor.")
        finally:
            with memory_lock:
                active_memory.pop(run["id"], None)

    def prepare(request: OptimizationInput):
        dataset = get("datasets", request.dataset_id)
        sessions = sessions_for(dataset)
        provided = request.rules.model_dump(exclude_unset=True)
        merged = dict(dataset.get("rules", {}))
        for key, value in provided.items():
            merged[key] = {**merged.get(key, {}), **value} if isinstance(value, dict) else value
        inputs = RuleInput.model_validate(merged)
        valid_groups = {s.group_key for s in sessions if not s.tutoring}
        if ((inputs.group_rooms.keys() | inputs.group_windows.keys()) - valid_groups
                or set(inputs.group_rooms.values()) - set(inputs.available_rooms)):
            raise HTTPException(422, "Revisa los paralelos y sus aulas asignadas.")
        valid_teachers = {s.teacher for s in sessions}
        valid_rooms = set(inputs.available_rooms)
        if (not valid_rooms or len(valid_rooms) != len(inputs.available_rooms)
                or not (valid_rooms <= set(ROOMS) or valid_rooms <= set(UPEC_ROOMS))):
            raise HTTPException(422, "Selecciona aulas únicas de un solo catálogo.")
        if {s.original.room for s in sessions} - valid_rooms:
            raise HTTPException(422, "Las asignaciones iniciales contienen aulas fuera de la lista disponible.")
        valid_classes = {s.id for s in sessions if not s.tutoring}
        if (inputs.enrollments.keys() - {s.id for s in sessions}
                or set(inputs.locked_sessions) - {s.id for s in sessions}
                or inputs.session_days.keys() - {s.id for s in sessions}
                or set(inputs.movable_tutoring) - {s.id for s in sessions if s.tutoring and occupies_group(s)}
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
        return dataset, sessions, rules, inputs

    @app.post("/api/planning/validate")
    def validate_plan(request: OptimizationInput):
        _, sessions, rules, _ = prepare(request)
        return validate_feasibility(sessions, rules)

    @app.post("/api/optimizations", status_code=202)
    def submit(request: OptimizationInput):
        dataset, sessions, rules, inputs = prepare(request)
        if rules.campus_windows is not None:
            diagnostics = validate_feasibility(sessions, rules)
            if diagnostics["errors"]:
                raise HTTPException(422, diagnostics["errors"][0]["message"])
        run = dict(id=str(uuid4()), dataset_id=dataset["id"], status="queued",
                   created_at=datetime.now(timezone.utc).isoformat(), progress=None,
                   parameters=request.parameters.model_dump(), rules=inputs.model_dump())
        repo().put("runs", run)
        config = Config(**run["parameters"])
        memory = WorkingMemory(run["id"], dataset["id"], config)
        with memory_lock:
            active_memory[run["id"]] = memory
        app.state.executor.submit(execute, run.copy(), sessions, rules, config, memory)
        return run

    @app.get("/api/optimizations/{identifier}")
    def status(identifier: UUID):
        return {k: v for k, v in get("runs", identifier).items() if k not in {"history", "result", "memory"}}

    @app.get("/api/optimizations/{identifier}/memory", response_model=MemorySnapshot)
    def run_memory(identifier: UUID):
        with memory_lock:
            memory = active_memory.get(str(identifier))
            if memory:
                return memory.snapshot()
        run = get("runs", identifier)
        return run.get("memory") or {
            "run_id": run["id"], "scenario_id": run["dataset_id"], "status": run["status"],
            "best": run.get("progress"), "seed": run["parameters"]["seed"],
            "maximum_generations": run["parameters"]["generations"],
        }

    @app.post("/api/optimizations/{identifier}/cancel", status_code=202)
    def cancel_run(identifier: UUID):
        with memory_lock:
            run = get("runs", identifier)
            memory = active_memory.get(str(identifier))
            if not memory or run["status"] not in {"queued", "running"}:
                raise HTTPException(409, "La ejecución ya terminó.")
            memory.cancelled.set()
        return {"accepted": True}

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

