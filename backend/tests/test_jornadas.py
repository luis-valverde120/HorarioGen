from dataclasses import replace
from pathlib import Path
import json

import pytest

from horariogen.domain import Gene, Rules, load_csv, parse_slot, within_campus_hours
from horariogen.evaluation import evaluate
from horariogen.genetic import Config, optimize

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.mark.parametrize("label,allowed", [
    ("Monday 07:00 - 11:00", True),
    ("Tuesday 09:00 - 13:00", True),
    ("Tuesday 12:00 - 14:00", False),
    ("Wednesday 13:00 - 14:00", False),
    ("Thursday 14:00 - 18:00", True),
    ("Friday 16:00 - 20:00", True),
    ("Friday 19:00 - 21:00", False),
])
def test_jornada_boundaries(label, allowed):
    assert within_campus_hours(parse_slot(label)) is allowed


def test_parallel_room_rule_and_lunch_break():
    session = load_csv((DATA / "horario_semanal.csv").read_bytes())[0]
    rules = Rules.from_payload({"group_rooms": {session.group_key: "107"}})
    wrong = Gene(parse_slot("Monday 11:00 - 15:00"), "106")
    result = evaluate([session], [wrong], rules)
    assert result.hard["group_room"] == 1
    assert result.hard["campus_hours"] == 1


def test_all_semesters_parallel_rooms_and_fixed_tutoring():
    sessions = load_csv((DATA / "horario_semanal.csv").read_bytes())
    rules = Rules.from_payload(json.loads((DATA / "reglas_ejemplo.json").read_text(encoding="utf-8")))
    classes = [session for session in sessions if not session.tutoring]
    assert len(classes) == 101
    assert {session.level for session in classes} == {f"Semestre {level}" for level in range(1, 10)}
    assert all({session.section for session in classes if session.level == f"Semestre {level}"} == {"A", "B"} for level in range(1, 10))
    genes, baseline, result, history, reason = optimize(sessions, rules, Config(generations=20, seconds=10))
    assert result.score[0] == 0
    assert all(within_campus_hours(gene.slot) for gene in genes)
    for session, gene in zip(sessions, genes, strict=True):
        if session.tutoring:
            assert gene == session.original
        else:
            assert gene.room == rules.group_rooms[session.group_key]
            assert gene.slot.duration == session.original.slot.duration


def test_room_configuration_changes_actual_assignments():
    sessions = load_csv((DATA / "horario_semanal.csv").read_bytes())[:1]
    target = "112"
    rules = Rules.from_payload({
        "available_rooms": ["106", "112"],
        "group_rooms": {sessions[0].group_key: target},
    })
    genes, baseline, result, *_ = optimize(sessions, rules, Config(generations=5))
    assert genes[0].room == target
    assert result.hard["group_room"] == 0

