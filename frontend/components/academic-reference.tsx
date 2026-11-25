import { useState } from "react";
import { BookOpen } from "lucide-react";
import { Button, Card } from "./ui";

export type Curriculum = {
  program: string;
  rooms: string[];
  reference_teacher_count: number;
  source: { resolution: string; note: string };
  subjects: { id: string; semester: number; name: string; curriculum_hours: number }[];
};

type Offering = { level: string; section: string; course: string; teacher: string;
  start: number; end: number; kind?: "class" | "tutoring" };

export function AcademicReference({ curriculum, offerings, disabled, createDemo }: {
  curriculum: Curriculum | null; offerings: Offering[]; disabled: boolean;
  createDemo: (groups: string, period: string) => void;
}) {
  const [semester, setSemester] = useState(1);
  const [section, setSection] = useState("A");
  const [groups, setGroups] = useState("1");
  const [period, setPeriod] = useState("");
  const group = offerings.filter(row => row.level === "Semestre " + semester && row.section === section);
  return <Card id="malla" className="product-card institutional-panel">
    <h2><BookOpen size={20} /> Malla curricular</h2>
    {!curriculum ? <p className="muted">La malla aún no está disponible.</p> : <>
      <p className="muted">{curriculum.program} · {curriculum.source.resolution} · {curriculum.subjects.length} asignaturas</p>
      <div className="institutional-toolbar">
        <label className="label">Semestre<select className="field" value={semester} onChange={e => setSemester(Number(e.target.value))}>
          {[...new Set(curriculum.subjects.map(s => s.semester))].map(n => <option key={n} value={n}>{n}</option>)}
        </select></label>
        <label className="label">Paralelo<select className="field" value={section} onChange={e => setSection(e.target.value)}>
          <option>A</option><option>B</option>
        </select></label>
        <label className="label">Paralelos de demostración<select className="field" value={groups} onChange={e => setGroups(e.target.value)}>
          <option value="1">Uno por semestre</option><option value="2">Dos por semestre</option>
        </select></label>
        <label className="label">Periodo<input className="field" value={period} placeholder="Demostración" maxLength={80}
          onChange={e => setPeriod(e.target.value)} /></label>
        <Button type="button" disabled={disabled} onClick={() => createDemo(groups, period.trim() || "Demostración")}>Cargar demostración UPEC</Button>
      </div>
      <p className="muted">La demostración utiliza {curriculum.reference_teacher_count} docentes ficticios, cargas sintéticas y aulas {curriculum.rooms.join(", ")}.</p>
      <div className="overflow-auto">
        <table className="reference-table">
          <thead><tr><th>Asignatura</th><th>Horas curriculares</th><th>Clase / semana</th><th>Tutoría / semana</th><th>Docente</th></tr></thead>
          <tbody>{curriculum.subjects.filter(s => s.semester === semester).map(subject => {
            const matches = group.filter(row => row.course === subject.name);
            const total = (tutoring: boolean) => matches.filter(row => (row.kind === "tutoring") === tutoring)
              .reduce((sum, row) => sum + (row.end - row.start) / 60, 0);
            return <tr key={subject.id}><th scope="row">{subject.name}</th><td>{subject.curriculum_hours}</td>
              <td>{matches.length ? total(false) + " h" : "—"}</td>
              <td>{matches.length ? total(true) + " h" : "—"}</td>
              <td>{matches.length ? [...new Set(matches.map(row => row.teacher))].join(", ") : "Sin oferta"}</td></tr>;
          })}</tbody>
        </table>
      </div>
      <p className="muted">{curriculum.source.note}</p>
    </>}
  </Card>;
}
