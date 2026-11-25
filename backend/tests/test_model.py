from dataclasses import replace
from pathlib import Path
from random import Random

import pytest

from horariogen.demo import demo_csv
from horariogen.domain import Gene, Rules, load_csv, parse_slot
from horariogen.evaluation import evaluate
from horariogen.genetic import Config, crossover, exchange, optimize, reassign, tournament

DATA = Path(__file__).resolve().parents[2] / "data" / "dataset_horario.csv"
EMPTY = Rules.from_payload({"enforce_hours": False})


@pytest.fixture
def sample():
    return load_csv(DATA.read_bytes(), legacy_hours=True)[:10]


def test_load_full_dataset():
    sessions = load_csv(DATA.read_bytes(), legacy_hours=True)
    assert len(sessions) == 406
    assert len({s.id for s in sessions}) == 406
    assert len({s.course for s in sessions}) < 406
    assert sessions[1].original.slot.start == 13 * 60


@pytest.mark.parametrize("raw", [b"", b"\xff", b"a;b\n1;2", DATA.read_bytes().splitlines()[0] + b"\nbad"])
def test_invalid_csv(raw):
    with pytest.raises(ValueError):
        load_csv(raw)


@pytest.mark.parametrize("kind", ["teacher", "room", "group"])
def test_interval_collision(sample, kind):
    a, b = sample[:2]
    if kind == "teacher":
        b = replace(b, teacher=a.teacher)
    elif kind == "group":
        b = replace(b, program=a.program, major=a.major, level=a.level, section=a.section)
    room = a.original.room if kind == "room" else b.original.room
    a = replace(a, original=Gene(parse_slot("Monday 08:00 - 10:00"), a.original.room))
    b = replace(b, original=Gene(parse_slot("Monday 09:00 - 11:00"), room))
    evaluation = evaluate((a, b), (a.original, b.original), EMPTY, details=True)
    assert evaluation.score == (1, 0)
    assert evaluation.conflicts == [{"type": kind, "sessions": (1, 2)}]
    adjacent = Gene(parse_slot("Monday 10:00 - 12:00"), room)
    assert evaluate((a, b), (a.original, adjacent), EMPTY).score[0] == 0


def test_rules_and_lexicographic_fitness(sample):
    a, b = sample[:2]
    smaller_room = b.original.room
    rules = Rules.from_payload({
        "capacities": {smaller_room: 10, a.original.room: 30}, "enrollments": {a.id: 20},
        "availability": {a.teacher: ["Monday 08:00 - 10:00"]},
        "preferences": {a.teacher: ["Tuesday 08:00 - 10:00"]},
    })
    valid = evaluate((a,), (a.original,), rules)
    bad = evaluate((a,), (Gene(b.original.slot, smaller_room),), rules)
    assert valid.score == (0, 1)
    assert bad.hard["capacity"] == bad.hard["availability"] == 1
    assert valid.score < bad.score
    assert evaluate((a,), (), rules).hard["unassigned"] == 1
    assert evaluate((a,), (a.original,), EMPTY).coverage["capacity"] == 0


def test_gap_penalty(sample):
    a = sample[0]
    b = replace(a, id=2, original=Gene(parse_slot("Monday 10:30 - 11:30"), a.original.room))
    evaluation = evaluate((a, b), (a.original, b.original), EMPTY)
    assert evaluation.hard == dict.fromkeys(evaluation.hard, 0)
    assert evaluation.soft['gaps'] == 2
    assert evaluation.soft['course_distribution'] == 1


def test_tournament_and_uniform_crossover(sample):
    a, b = (s.original for s in sample[:2])
    first, second = (a,) * 12, (b,) * 12
    assert tournament([((1, 0), first), ((0, 100), second)], 2, Random(0)) == second
    child = crossover(first, second, Random(42))
    assert len(child) == 12
    assert set(child) == {a, b}


def test_mutations(sample):
    a, b = (s.original for s in sample[:2])
    genes = [a, b]
    exchange(genes, 0, {60: [1]}, Random(1))
    assert genes == [b, a]
    reassign(genes, 0, {60: [a.slot]}, [a.room], Random(1))
    assert genes[0] != b
    assert genes[0].slot.duration == 60


def test_demo_resolves_injected_conflicts_without_losing_sessions():
    raw = DATA.read_bytes()
    sample = load_csv(demo_csv(raw))
    genes, baseline, evaluation, history, reason = optimize(sample, EMPTY)
    assert baseline.hard["teacher"] == baseline.hard["room"] == 1
    assert baseline.score[0] == 2
    assert evaluation.score[0] == 0
    assert len(genes) == len(sample)
    assert all(g.slot.duration == s.original.slot.duration for s, g in zip(sample, genes, strict=True))
    scores = [(point["hard"], point["soft"]) for point in history]
    assert scores == sorted(scores, reverse=True)
    assert DATA.read_bytes() == raw


def test_stopping_conditions(sample, monkeypatch):
    demo = load_csv(demo_csv(DATA.read_bytes()))
    assert optimize(demo, EMPTY, Config(generations=0))[4] == "generations"
    assert optimize(sample[:1], EMPTY)[4] == "optimal_score"
    readings = iter((0, 1))
    monkeypatch.setattr("horariogen.genetic.time.monotonic", lambda: next(readings, 1))
    assert optimize(demo, EMPTY, Config(seconds=0.1))[4] == "time"

