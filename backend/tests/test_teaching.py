from dataclasses import replace
from collections import Counter
from pathlib import Path
import json

import pytest
from fastapi.testclient import TestClient

from horariogen.api import TeachingAssignment, create_app
from horariogen.domain import Gene, Rules, Session, parse_slot
from horariogen.domain import load_csv
from horariogen.teaching import build_plan
from horariogen.evaluation import evaluate
from horariogen.genetic import Config, optimize
from horariogen.storage import FileRepository

BASE=Session(1,'Semestre 1','A','Software','Programación','Ana Paz','Computación',Gene(parse_slot('Monday 07:00 - 09:00'),'106'))

def test_ten_hours_in_full_demo_can_resolve_resource_conflicts():
    data=Path(__file__).resolve().parents[2]/'data'
    sessions=load_csv((data/'horario_semanal.csv').read_bytes())
    payload=json.loads((data/'reglas_ejemplo.json').read_text(encoding='utf-8'))
    entries={}
    for s in sessions:
        if s.tutoring:continue
        key=s.group_key,s.course
        if key not in entries:
            entries[key]=dict(source_id=s.id,course=s.course,teacher=s.teacher,weekly_hours=0,block_hours=2,days=[0,1,2,3,4])
        entries[key]['weekly_hours']+=s.original.slot.duration//60
        if s.original.slot.duration>120:entries[key]['block_hours']=4
        if s.level=='Semestre 7' and s.section=='A' and s.course=='Aplicaciones móviles':target=key
    entries[target]['weekly_hours']=10
    planned,days,_=build_plan(sessions,[TeachingAssignment(**v) for v in entries.values()],Rules.from_payload(payload))
    payload['session_days']=days
    payload['weekly_minutes']={teacher:sum(s.original.slot.duration for s in planned if s.teacher==teacher) for teacher in {s.teacher for s in planned}}
    genes,_,result,*_=optimize(planned,Rules.from_payload(payload),Config(generations=20,seconds=10))
    assert result.score[0]==0,result.hard
    selected=[g for s,g in zip(planned,genes) if (s.group_key,s.course)==target and not s.tutoring]
    assert sum(g.slot.duration for g in selected)==600
    assert len({g.slot.day for g in selected})>=2

@pytest.mark.parametrize('hours,block',[(10,2),(20,4),(7,2),(1,1)])
def test_weekly_hours_are_expanded_and_spread(hours,block):
    item=TeachingAssignment(source_id=1,course=BASE.course,teacher=BASE.teacher,weekly_hours=hours,block_hours=block,days=[0,1,2,3,4])
    planned,days,_=build_plan([BASE],[item],Rules.from_payload({}))
    assert sum(s.original.slot.duration for s in planned)==hours*60
    assert all(s.original.slot.duration<=block*60 for s in planned)
    assert len({s.original.slot.day for s in planned})==min(5,len(planned))
    rules=Rules.from_payload({'session_days':days})
    assert evaluate(planned,[s.original for s in planned],rules).score[0]==0
    assert len({s.id for s in planned})==len(planned)

def test_selected_days_remain_mandatory_during_optimization():
    item=TeachingAssignment(source_id=1,course=BASE.course,teacher=BASE.teacher,weekly_hours=4,block_hours=2,days=[0,2])
    planned,days,_=build_plan([BASE],[item],Rules.from_payload({}))
    assert {s.original.slot.day for s in planned}=={0,2}
    rules=Rules.from_payload({'session_days':days})
    wrong=Gene(parse_slot('Tuesday 07:00 - 09:00'),'106')
    assert evaluate(planned,[wrong,planned[1].original],rules).hard['teaching_days']==1
    genes,_,result,*_=optimize(planned,rules,Config(generations=3))
    assert result.score[0]==0 and all(g.slot.day in [0,2] for g in genes)

def test_parallel_cannot_exceed_weekly_capacity():
    item=TeachingAssignment(source_id=1,course=BASE.course,teacher=BASE.teacher,weekly_hours=30,block_hours=2,days=[0,1,2,3,4])
    tutor=replace(BASE,id=2,tutoring=True,original=Gene(parse_slot('Monday 11:00 - 12:00'),'106'))
    with pytest.raises(ValueError,match='30 horas'):build_plan([BASE,tutor],[item],Rules.from_payload({}))
    with pytest.raises(ValueError,match='superan la jornada'):build_plan([BASE],[item.model_copy(update={'days':[0,2]})],Rules.from_payload({}))

def test_plan_api_persists_hours_teacher_link_and_previous_dataset(tmp_path):
    with TestClient(create_app(FileRepository(tmp_path))) as client:
        raw=('Franja_Horaria;Nivel_Semestre;Paralelo_Grupo;Carrera_Especialidad;Codigo_Asignatura;Docente;Aula;Programa_Academico;Tipo\n'
             'Monday 07:00 - 09:00;Semestre 1;A;Software;Programación;Ana Paz;106;Computación;Clase\n'
             'Monday 10:00 - 12:00;Semestre 1;A;Software;Álgebra;Luis Sol;106;Computación;Clase\n'
             'Friday 12:00 - 13:00;Semestre 1;A;Software;Programación;Ana Paz;106;Computación;Tutoria\n').encode()
        dataset=client.post('/api/datasets/import',files={'file':('sample.csv',raw)}).json()
        items=[dict(source_id=1,course='Programación',teacher='Luis Sol',weekly_hours=10,block_hours=2,days=[0,1,2,3,4]),
               dict(source_id=2,course='Álgebra',teacher='Ana Paz',weekly_hours=2,block_hours=2,days=[0,2])]
        response=client.post(f"/api/datasets/{dataset['id']}/teaching-plan",json={'assignments':items})
        assert response.status_code==201,response.text
        new=response.json();assert new['id']!=dataset['id']
        rows=client.get(f"/api/datasets/{new['id']}/sessions").json()
        classes=[s for s in rows if s['course']=='Programación' and s['kind']=='class']
        assert len(classes)==5 and sum(s['end']-s['start'] for s in classes)==600
        assert len({s['day'] for s in classes})==5
        assert all(s['teacher']=='Luis Sol' for s in rows if s['course']=='Programación')
        assert new['rules']['weekly_minutes']['Luis Sol']==660
        assert new['rules']['session_days']
        assert len(client.get(f"/api/datasets/{dataset['id']}/sessions").json())==3
        duplicate=client.post(f"/api/datasets/{dataset['id']}/teaching-plan",json={'assignments':[items[0],items[0]]})
        assert duplicate.status_code==422
        invalid=client.post(f"/api/datasets/{dataset['id']}/teaching-plan",json={'assignments':[{**items[0],'teacher':'Unknown'}]})
        assert invalid.status_code==422
