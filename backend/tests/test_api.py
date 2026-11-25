import csv
import io
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from horariogen.api import create_app
from horariogen.domain import load_csv
from horariogen.imports import ROOMS
from horariogen.storage import FileRepository

DATA = Path(__file__).resolve().parents[2] / "data"


def wait_for_result(client, path):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        status = client.get(path).json()
        if status["status"] in {"completed", "failed"}:
            assert status["status"] == "completed", status
            return client.get(path + "/result").json()
        time.sleep(0.03)
    raise AssertionError("La optimización no terminó")


def test_tutoring_can_be_linked_to_course_and_parallel(tmp_path):
    with TestClient(create_app(FileRepository(tmp_path))) as client:
        dataset = client.get('/api/datasets').json()[0]
        source = client.get(f"/api/datasets/{dataset['id']}/sessions").json()[0]
        tutor = {'session_id': source['id'], 'teacher': source['teacher'],
                 'room': source['room'], 'slot': 'Monday 07:00 - 08:00'}
        payload = {'dataset_id': dataset['id'], 'parameters': {'generations': 0},
                   'rules': {'tutoring': [tutor]}}
        response = client.post('/api/optimizations', json=payload)
        assert response.status_code == 202, response.text
        result = wait_for_result(client, '/api/optimizations/' + response.json()['id'])
        linked = result['original'][-1]
        assert linked['kind'] == 'tutoring'
        assert all(linked[key] == source[key] for key in ('course', 'level', 'section', 'teacher', 'group_key'))
        tutor['teacher'] = next(row['teacher'] for row in result['original'] if row['teacher'] != source['teacher'])
        assert client.post('/api/optimizations', json=payload).status_code == 422


def test_complete_excel_workflow(tmp_path):
    repo = FileRepository(tmp_path)
    with TestClient(create_app(repo)) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        bundled, = client.get("/api/datasets").json()
        assert bundled["classes"] == 101 and bundled["tutoring"] == 18
        assert bundled["teachers"] == 10 and bundled["rooms"] == list(ROOMS)
        workbook = client.get("/api/templates/xlsx")
        assert workbook.status_code == 200
        imported = client.post("/api/datasets/import", files={"file": ("plan.xlsx", workbook.content)})
        assert imported.status_code == 201, imported.text
        dataset = imported.json()
        assert dataset["count"] == 119
        assert dataset["rules"]["availability"] == bundled["rules"]["availability"]
        assert dataset["rules"]["weekly_minutes"] == bundled["rules"]["weekly_minutes"]
        assert (tmp_path / "datasets" / f"{dataset['id']}.source").read_bytes() == workbook.content
        response = client.post("/api/optimizations", json={"dataset_id": dataset["id"]})
        assert response.status_code == 202, response.text
        path = "/api/optimizations/" + response.json()["id"]
        result = wait_for_result(client, path)
        assert result["baseline"]["score"][0] > 0
        assert result["evaluation"]["score"][0] == 0
        assert result["evaluation"]["coverage"]["availability"] == 119
        assert {row["room"] for row in result["optimized"]} <= set(ROOMS)
        assert [row["id"] for row in result["original"]] == [row["id"] for row in result["optimized"]]
        for original, optimized in zip(result["original"], result["optimized"], strict=True):
            assert original["end"] - original["start"] == optimized["end"] - optimized["start"]
            if original["kind"] == "tutoring":
                assert original == optimized
        assert all(row["scheduled"] == row["target"] for row in result["evaluation"]["workload"].values())
        exported = client.get(path + "/export")
        sessions = load_csv(exported.content)
        assert len(sessions) == 119 and sum(s.tutoring for s in sessions) == 18
        metrics = client.get(path + "/metrics").json()
        assert metrics["best"] == metrics["history"][-1]
    with TestClient(create_app(repo)) as client:
        assert client.get(path).json()["status"] == "completed"


def test_simple_csv_creates_initial_assignments(tmp_path):
    with TestClient(create_app(FileRepository(tmp_path))) as client:
        raw = "Materia;Docente;Grupo;Duracion_Horas\nÁlgebra;Laura Paz;A;4\nFísica;Mario Sol;B;2\n"
        response = client.post("/api/datasets/import", files={"file": ("sesiones.csv", raw.encode())})
        assert response.status_code == 201, response.text
        dataset = response.json()
        rows = client.get(f"/api/datasets/{dataset['id']}/sessions").json()
        assert [row["end"] - row["start"] for row in rows] == [240, 120]
        assert dataset["rooms"] == list(ROOMS) and dataset["warnings"]
        assert all(row["level"] == "Semestre 1" for row in rows)
        assert {row["teacher"] for row in rows} == {"Laura Paz", "Mario Sol"}


@pytest.mark.parametrize("filename,raw", [
    ("bad.xlsx", b"invalid"),
    ("bad.csv", b"bad"),
    ("bad.xls", b"not supported"),
    ("bad.csv", b"Materia;Docente;Grupo;Duracion_Horas\nAlgo;Laura;A;nan"),
    ("bad.csv", b"Materia;Docente;Grupo;Duracion_Horas\nAlgo;;A;2"),
])
def test_invalid_imports_are_rejected(filename, raw, tmp_path):
    with TestClient(create_app(FileRepository(tmp_path))) as client:
        response = client.post("/api/datasets/import", files={"file": (filename, raw)})
        assert response.status_code == 422, response.text


def test_room_catalog_and_unknown_teacher_validation(tmp_path):
    with TestClient(create_app(FileRepository(tmp_path))) as client:
        dataset = client.get("/api/datasets").json()[0]
        raw = (DATA / "horario_semanal.csv").read_bytes().replace(b";106;", b";200;")
        assert client.post("/api/datasets/import", files={"file": ("bad.csv", raw)}).status_code == 422
        for rules in [
            {"available_rooms": ["200"]},
            {"availability": {"Desconocido": ["Monday 08:00 - 12:00"]}},
            {"class_minutes": {"102": 120}},
        ]:
            response = client.post("/api/optimizations", json={"dataset_id": dataset["id"], "rules": rules})
            assert response.status_code == 422, response.text


def test_clear_target_and_block_day(tmp_path):
    with TestClient(create_app(FileRepository(tmp_path))) as client:
        dataset = client.get("/api/datasets").json()[0]
        teacher = next(iter(dataset["rules"]["weekly_minutes"]))
        response = client.post("/api/optimizations", json={
            "dataset_id": dataset["id"], "parameters": {"generations": 0},
            "rules": {"weekly_minutes": {teacher: None}, "availability": {teacher: []}},
        })
        assert response.status_code == 202
        path = "/api/optimizations/" + response.json()["id"]
        result = wait_for_result(client, path)
        assert result["evaluation"]["workload"][teacher]["target"] is None
        assert result["evaluation"]["hard"]["availability"] >= 6

