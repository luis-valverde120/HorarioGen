from dataclasses import replace
from collections import defaultdict
import json
from pathlib import Path

import pytest

from horariogen.domain import Rules, Gene, load_csv, parse_slot, within_semester_shift
from horariogen.evaluation import evaluate
from horariogen.genetic import Config, optimize

DATA = Path(__file__).resolve().parents[2] / 'data'


@pytest.mark.parametrize('semester', range(1, 10))
def test_both_parallels_have_same_required_shift(semester):
    base = load_csv((DATA / 'horario_semanal.csv').read_bytes())[0]
    morning = parse_slot('Monday 07:00 - 09:00')
    afternoon = parse_slot('Monday 14:00 - 16:00')
    for parallel in ('A', 'B'):
        session = replace(base, level=f'Semestre {semester}', section=parallel)
        assert within_semester_shift(session, morning) == bool(semester % 2)
        assert within_semester_shift(session, afternoon) == (semester % 2 == 0)
        wrong = afternoon if semester % 2 else morning
        session = replace(session, original=Gene(wrong, '106'))
        result = evaluate([session], [session.original], Rules.from_payload({}))
        assert result.hard['semester_shift'] == 1


def test_example_subject_counts_and_optimized_shift():
    sessions = load_csv((DATA / 'horario_semanal.csv').read_bytes())
    subjects = defaultdict(set)
    for session in sessions:
        if not session.tutoring:
            subjects[session.group].add(session.course)
    assert len(subjects) == 18
    assert all(len(courses) == (5 if group[-1] == 'A' else 6) for group, courses in subjects.items())
    rules = Rules.from_payload(json.loads((DATA / 'reglas_ejemplo.json').read_text(encoding='utf-8')))
    genes, baseline, result, *_ = optimize(sessions, rules, Config(generations=5))
    assert baseline.hard['semester_shift'] == 1
    assert result.score[0] == 0
    assert all(within_semester_shift(s, g.slot) for s, g in zip(sessions, genes))


def test_linked_tutoring_reserves_students_and_respects_shift():
    base = load_csv((DATA / 'horario_semanal.csv').read_bytes())[0]
    first = replace(base, original=Gene(parse_slot('Monday 07:00 - 09:00'), '106'))
    tutor = replace(first, id=2, teacher='Otro docente', tutoring=True,
                    original=Gene(parse_slot('Monday 08:00 - 09:00'), '107'))
    result = evaluate([first, tutor], [first.original, tutor.original], Rules.from_payload({}))
    assert result.hard['group'] == 1
    assert result.hard['teacher'] == result.hard['room'] == 0
    tutor = replace(tutor, original=Gene(parse_slot('Monday 14:00 - 15:00'), '107'))
    result = evaluate([tutor], [tutor.original], Rules.from_payload({}))
    assert result.hard['semester_shift'] == 1
