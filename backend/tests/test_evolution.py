import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from horariogen.api import create_app
from horariogen.domain import Gene, Rules, Session, Slot
from horariogen.evaluation import evaluate
from horariogen.feasibility import validate_feasibility
from horariogen.genetic import Config, optimize
from horariogen.storage import FileRepository
from horariogen.working_memory import OptimizationCancelled, WorkingMemory


@pytest.mark.parametrize("parallel_count", [1, 2])
def test_reference_scenario_and_run_memory(tmp_path, parallel_count):
    with TestClient(create_app(FileRepository(tmp_path))) as client:
        curriculum = client.get("/api/curriculum").json()
        assert len(curriculum["subjects"]) == 50
        assert {subject["semester"] for subject in curriculum["subjects"]} == set(range(1, 10))
        assert "sha256" in curriculum["source"]
        dataset = client.post(f"/api/curriculum/demonstration?groups={parallel_count}")
        assert dataset.status_code == 201, dataset.text
        dataset = dataset.json()
        assert dataset["rooms"] == [str(room) for room in range(206, 213)]
        assert dataset["teachers"] == 16
        identifier = dataset["id"]
        sessions = client.get(f"/api/datasets/{identifier}/sessions").json()
        assert len({row["group_key"] for row in sessions}) == 9 * parallel_count
        assert dataset["classes"] == dataset["tutoring"] == 50 * parallel_count
        assert {row["end"] - row["start"] for row in sessions if row["kind"] == "class"} == {120}
        request = {"dataset_id": identifier}
        diagnostics = client.post("/api/planning/validate", json=request).json()
        assert diagnostics["can_optimize"], diagnostics
        run = client.post("/api/optimizations", json=request)
        assert run.status_code == 202, run.text
        path = "/api/optimizations/" + run.json()["id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and client.get(path).json()["status"] in {"queued", "running"}:
            time.sleep(0.01)
        snapshot = client.get(path + "/memory").json()
        assert snapshot["status"] == "completed"
        assert snapshot["best"]["hard"] == 0
        assert snapshot["facts"]["sessions"] == len(sessions)
        assert {item["type"] for item in snapshot["events"]} >= {
            "FACTS_LOADED", "GENERATION_COMPLETED", "FEASIBLE_SCHEDULE_FOUND", "RUN_COMPLETED",
        }
        assert client.get(path + "/result").json()["evaluation"]["feasible"]
        assert client.post(path + "/cancel").status_code == 409


def test_custom_saturday_shifts_and_continuous_resource_conflicts():
    session = Session(1, "Semestre 2", "A", "Computación", "Programación", "Docente", "UPEC",
                      Gene(Slot(5, 420, 660), "206"))
    second = replace(session, id=2, level="Semestre 3", teacher="Otra docente",
                     original=Gene(Slot(5, 600, 720), "206"))
    rules = Rules.from_payload({
        "campus_windows": ["Saturday 07:00 - 13:00", "Saturday 14:00 - 20:00"],
        "group_windows": {session.group_key: ["Saturday 07:00 - 13:00"]},
        "available_rooms": ["206"],
    })
    evaluation = evaluate([session, second], [session.original, second.original], rules,
                          details=True, include_resources=True)
    assert evaluation.hard["room"] == 1
    assert evaluation.conflicts[0]["resource"] == "206"
    assert evaluation.hard["semester_shift"] == 0
    assert validate_feasibility([session], rules)["can_optimize"]
    impossible = replace(rules, availability={"Docente": [Slot(5, 540, 720)]})
    assert not validate_feasibility([session], impossible)["can_optimize"]


def test_memory_event_bound_and_cooperative_cancellation():
    config = Config()
    memory = WorkingMemory("run", "dataset", config)
    for _ in range(300):
        memory.emit("GENERATION_COMPLETED")
    snapshot = memory.snapshot()
    assert len(snapshot["events"]) == 250
    assert snapshot["events"][0]["sequence"] == 51
    memory.cancelled.set()
    with pytest.raises(OptimizationCancelled):
        optimize([], Rules.from_payload({}), config, memory=memory)


def test_save_explicit_class_and_tutorial_distributions(tmp_path):
    with TestClient(create_app(FileRepository(tmp_path))) as client:
        dataset = client.post("/api/curriculum/demonstration").json()
        path = f"/api/datasets/{dataset['id']}"
        source = next(row for row in client.get(path + "/sessions").json() if row["kind"] == "class")
        entry = {"source_id": source["id"], "course": source["course"], "teacher": source["teacher"],
                 "weekly_hours": 6, "block_hours": 4, "class_blocks": [3, 3], "tutorial_blocks": [1, 2],
                 "days": [0, 1, 2, 3, 4]}
        saved = client.post(path + "/teaching-plan", json={"assignments": [entry]})
        assert saved.status_code == 201, saved.text
        record = saved.json()
        sessions = client.get(f"/api/datasets/{record['id']}/sessions").json()
        assert sorted(row["end"] - row["start"] for row in sessions if row["kind"] == "class") == [180, 180]
        assert sorted(row["end"] - row["start"] for row in sessions if row["kind"] == "tutoring") == [60, 120]
        assert record["rules"]["movable_tutoring"] == [row["id"] for row in sessions if row["kind"] == "tutoring"]
        assert record["rules"]["weekly_minutes"] == {source["teacher"]: 540}
        assert client.post("/api/planning/validate", json={"dataset_id": record["id"]}).json()["can_optimize"]
        entry["class_blocks"] = [4, 3]
        assert client.post(path + "/teaching-plan", json={"assignments": [entry]}).status_code == 422
