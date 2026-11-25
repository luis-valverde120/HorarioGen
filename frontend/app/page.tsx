"use client";

import { useEffect, useState, type FormEvent, type CSSProperties } from "react";
import { Activity, ArrowDown, ArrowRight, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Database, Download, FileUp, LayoutDashboard, Pause, Play, Search, Settings2, Users, DoorOpen, Layers3, WifiOff, Workflow } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button, Card } from "@/components/ui";
import { TeachingPlanner, type TeachingAssignment } from "@/components/teaching-planner";
import { RoomFlow } from "@/components/room-flow";

const API = process.env.NEXT_PUBLIC_HORARIOGEN_API ?? "";
const DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const API_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const TEACHER_COLORS = ["#593dc5", "#a82453", "#116fb4", "#007656", "#a14908", "#8c399a", "#007982", "#b33229", "#555e17", "#3454a0"];
const LABELS: Record<string, string> = {
  teacher: "Docentes", room: "Aulas", group: "Grupos", unassigned: "Sin asignar",
  duration: "Duración", capacity: "Aforo", availability: "Disponibilidad", workload: "Carga semanal", campus_hours: "Jornada académica", semester_shift: "Jornada del semestre", group_room: "Aula del paralelo", extra: "Asignaciones extra",
  rescheduled: "Cambios de franja", room_changes: "Cambios de aula", gaps: "Tiempos muertos", preferences: "Preferencias", teaching_days: "Días de la materia", course_distribution: "Concentración de materias",
};
const DEFAULTS = { population: 40, generations: 100, seconds: 10, mutation: 0.35, tournament: 3, elite: 2, seed: 42 };
const FIELDS = [
  ["population", "Población", 4, 200, 1], ["generations", "Generaciones", 0, 1000, 1],
  ["seconds", "Límite en segundos", 0.01, 120, 0.01], ["mutation", "Probabilidad de mutación", 0, 1, 0.01],
  ["tournament", "Tamaño de torneo", 2, 200, 1], ["elite", "Élite", 1, 199, 1],
  ["seed", "Semilla", 0, 2147483647, 1],
] as const;
const STOP: Record<string, string> = { optimal_score: "Puntuación mínima", generations: "Límite de generaciones", time: "Límite de tiempo" };

type Window = { day: number; start: string; end: string };
type Availability = Record<string, Window[]>;
type Tutoring = Window & { teacher: string; room: string; session_id?: number };
type Workload = Record<string, { scheduled: number; target: number | null }>;

function hours(minutes: number) {
  return new Intl.NumberFormat("es-EC", { maximumFractionDigits: 2 }).format(minutes / 60) + " h";
}

function apiSlot(window: Window) {
  return API_DAYS[window.day] + " " + window.start + " - " + window.end;
}

function teacherStyle(color: string): CSSProperties {
  return { "--teacher-color": color } as CSSProperties;
}

type Dataset = {
  id: string; name: string; count: number; rooms?: string[]; classes?: number; tutoring?: number;
  warnings?: string[]; rules?: { availability?: Record<string, string[]>; weekly_minutes?: Record<string, number>; group_rooms?: Record<string, string>; session_days?: Record<string, number[]> };
};
type Session = { kind?: "class" | "tutoring"; group_key?: string; id: number; course: string; teacher: string; program: string; major: string; level: string; section: string; room: string; day: number; start: number; end: number; slot: string };
type Point = { generation: number; hard: number; soft: number; elapsed: number };
type Run = { id: string; status: "queued" | "running" | "completed" | "failed"; progress: Point | null; error?: string };
type Evaluation = { hard: Record<string, number>; soft: Record<string, number>; coverage: Record<string, number>; score: [number, number]; feasible: boolean; conflicts: { type: string; teacher?: string; sessions: number[] }[]; workload?: Workload };
type Result = { original: Session[]; optimized: Session[]; baseline: Evaluation; evaluation: Evaluation };
type Metrics = { history: Point[]; best: Point | null; reason: string | null };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, { cache: "no-store", ...options });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(Array.isArray(detail) ? detail.map(e => e.msg).join(". ") : detail ?? "Error del servidor");
  }
  return data;
}

function clock(minutes: number) {
  return [Math.floor(minutes / 60), minutes % 60].map(n => String(n).padStart(2, "0")).join(":");
}

function Schedule({ rows, colors }: { rows: Session[]; colors: Map<string, string> }) {
  const [detail, setDetail] = useState<Session | null>(null);
  const levels = [...new Set(rows.map(row => row.level))];
  const semester = levels.length === 1 ? Number(levels[0]?.match(/^Semestre ([1-9])$/)?.[1]) : 0;
  const shiftStart = semester % 2 ? 420 : 840;
  const shiftEnd = semester % 2 ? 780 : 1200;
  const focused = semester > 0 && rows.every(row => row.start >= shiftStart && row.end <= shiftEnd);
  const begin = focused ? shiftStart : 420;
  const finish = focused ? shiftEnd : 1200;
  const general = new Set(rows.filter(row => row.kind !== "tutoring").map(row => row.group_key)).size > 1;
  const startHour = Math.floor(begin / 60);
  const endHour = Math.ceil(finish / 60);
  const visibleDays = Array.from({ length: Math.max(5, ...rows.map(row => row.day + 1)) }, (_, index) => index);
  const ticks = Array.from({ length: endHour - startHour }, (_, index) => startHour + index);

  function placements(day: number) {
    const sorted = rows.filter(row => row.day === day).sort((a, b) => a.start - b.start || b.end - a.end);
    const clusters: Session[][] = [];
    let end = -1;
    for (const row of sorted) {
      if (row.start >= end) { clusters.push([]); end = row.end; }
      clusters[clusters.length - 1].push(row);
      end = Math.max(end, row.end);
    }
    return clusters.flatMap(cluster => {
      const lanes: number[] = [];
      const assigned = cluster.map(row => {
        let lane = lanes.findIndex(until => until <= row.start);
        if (lane < 0) lane = lanes.length;
        lanes[lane] = row.end;
        return { row, lane };
      });
      return assigned.map(item => ({ ...item, count: lanes.length }));
    });
  }

  return <>
    {general || visibleDays.some(day => placements(day).some(item => item.count > 2)) ? <div className="agenda-scroll"><div className="agenda-grid">
      {visibleDays.map(day => <section className="agenda-day" key={day}><h3>{DAYS[day]}</h3>
        {rows.filter(row => row.day === day).sort((a,b) => a.start-b.start || a.level.localeCompare(b.level)).map(row =>
          <button type="button" key={row.id} className={"agenda-event " + (row.kind === "tutoring" ? "agenda-tutoring" : "")}
            style={teacherStyle(colors.get(row.teacher) ?? "#593dc5")} onClick={() => setDetail(row)}>
            <small>{clock(row.start)}–{clock(row.end)} · Aula {row.room}</small>
            <strong>{row.kind === "tutoring" ? "Tutoría · " + row.course : row.course}</strong>
            <span>{row.teacher}</span>{row.kind !== "tutoring" && <span>{row.level} · Paralelo {row.section}</span>}
          </button>)}
        {!rows.some(row => row.day === day) && <p className="muted">Sin actividades</p>}
      </section>)}
    </div></div> : <div className="week-scroll">
      <div className="week-calendar" style={{ gridTemplateColumns: "55px repeat(" + visibleDays.length + ", minmax(160px, 1fr))" }}>
        <div className="week-corner">Hora</div>
        {visibleDays.map(day => <div className="week-heading" key={day}><strong>{DAYS[day]}</strong><small>{rows.filter(row => row.day === day).length} {rows.filter(row => row.day === day).length === 1 ? "actividad" : "actividades"}</small></div>)}
        <div className="week-ruler" style={{ height: ticks.length * 90 }}>{ticks.map(hour => <span key={hour} style={{ top: (hour - startHour) * 90 }}>{clock(hour * 60)}</span>)}</div>
        {visibleDays.map(day => <div className="week-day" key={day} style={{ height: ticks.length * 90 }}>
          {ticks.map(hour => <div aria-hidden className="week-line" key={hour} style={{ top: (hour - startHour) * 90 }} />)}
          {begin <= 780 && finish >= 840 && <div className="lunch-break" style={{top:(13-startHour)*90,height:90}}>Receso</div>}
          {placements(day).map(({ row, lane, count }) => <button
            type="button" key={row.id} onClick={() => setDetail(row)}
            className={"week-event " + (row.kind === "tutoring" ? "tutoring-event" : "")}
            aria-label={[row.kind === "tutoring" ? "Tutoría · " + row.course : row.course, row.teacher, DAYS[day], clock(row.start), clock(row.end), "aula", row.room].join(" ")}
            style={{ ...teacherStyle(colors.get(row.teacher) ?? "#593dc5"),
              top: (row.start / 60 - startHour) * 90 + 3, height: (row.end - row.start) / 60 * 90 - 6,
              left: "calc(" + lane / count * 100 + "% + 3px)", width: "calc(" + 100 / count + "% - 6px)" }}>
              <small>{clock(row.start)}–{clock(row.end)}</small><strong>{row.kind === "tutoring" ? "Tutoría · " + row.course : row.course}</strong>
              <span>{row.teacher}</span><span>Aula {row.room} · {row.kind === "tutoring" ? "Tutoría" : "Paralelo " + row.section}</span>
          </button>)}
        </div>)}
      </div>
    </div>}
    {detail && <div className="session-detail" role="status">
      <div><strong>{detail.kind === "tutoring" ? "Tutoría · " + detail.course : detail.course}</strong><p>{detail.teacher} · {DAYS[detail.day]} {clock(detail.start)}–{clock(detail.end)} · {hours(detail.end - detail.start)} · Aula {detail.room}</p></div>
      <Button variant="outline" onClick={() => setDetail(null)}>Cerrar detalle</Button>
    </div>}
  </>;
}

function AvailabilityEditor({ teachers, colors, value, onChange, disabled }: {
  teachers: string[];
  colors: Map<string, string>;
  value: Availability;
  onChange: (next: Availability) => void;
  disabled: boolean;
}) {
  const [selected, setSelected] = useState("");
  const [day, setDay] = useState(0);
  const [start, setStart] = useState("08:00");
  const [end, setEnd] = useState("11:00");
  const [error, setError] = useState("");
  const teacher = teachers.includes(selected) ? selected : teachers[0] ?? "";
  const windows = value[teacher] ?? [];

  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!teacher || !start || !end || start >= end) {
      setError("La hora de fin debe ser posterior a la de inicio.");
      return;
    }
    if (windows.some(window => window.day === day && window.start === start && window.end === end)) {
      setError("Esta franja ya está registrada.");
      return;
    }
    setError("");
    onChange({ ...value, [teacher]: [...windows, { day, start, end }].sort(
      (a, b) => a.day - b.day || a.start.localeCompare(b.start),
    ) });
  }

  return <div className="availability-editor">
    <h3 className="font-bold">Disponibilidad docente</h3>
    <p className="muted">Agrega todas las franjas en las que el docente puede impartir clase. Cada sesión debe caber completa en una de ellas.</p>
    <form onSubmit={add} className="availability-form">
      <fieldset disabled={disabled || !teachers.length}>
        <label className="label">Docente<select className="field" value={teacher} onChange={event => { setSelected(event.target.value); setError(""); }}>
          {teachers.map(name => <option key={name}>{name}</option>)}
        </select></label>
        <label className="label">Día<select className="field" value={day} onChange={event => setDay(Number(event.target.value))}>
          {DAYS.map((name, index) => <option key={name} value={index}>{name}</option>)}
        </select></label>
        <label className="label">Desde<input className="field" type="time" value={start} required onChange={event => setStart(event.target.value)} /></label>
        <label className="label">Hasta<input className="field" type="time" value={end} required onChange={event => setEnd(event.target.value)} /></label>
        <Button type="submit">Agregar franja</Button>
      </fieldset>
    </form>
    {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
    <div className="mt-3 flex flex-wrap items-center gap-2" aria-live="polite">
      {teacher && <span className="teacher-label" style={teacherStyle(colors.get(teacher) ?? "#593dc5")}>{teacher}</span>}
      {windows.length === 0 && <p className="muted">Sin franjas permitidas registradas.</p>}
      {windows.map((window, index) => <div className="window-chip" key={DAYS[window.day] + window.start + window.end}>
        {DAYS[window.day]} {window.start}–{window.end}
        <button type="button" disabled={disabled} aria-label={"Quitar franja de " + DAYS[window.day] + " " + window.start}
          onClick={() => onChange({ ...value, [teacher]: windows.filter((_, item) => item !== index) })}>×</button>
      </div>)}
    </div>
    <p className="mt-2 muted">{Object.values(value).filter(items => items.length > 0).length} de {teachers.length} docentes con disponibilidad registrada en este formulario.</p>
  </div>;
}

function TutoringEditor({ teachers, rooms, sessions, items, onChange, disabled }: {
  teachers: string[]; rooms: string[]; sessions: Session[]; items: Tutoring[];
  onChange: (items: Tutoring[]) => void; disabled: boolean;
}) {
  const [error, setError] = useState("");
  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const source = sessions.find(row => row.id === Number(data.get("session_id")));
    const item = {
      session_id: source?.id,
      teacher: source?.teacher ?? String(data.get("teacher")), room: String(data.get("room")),
      day: Number(data.get("day")), start: String(data.get("start")), end: String(data.get("end")),
    };
    if (item.start >= item.end) {
      setError("La hora de fin debe ser posterior a la de inicio.");
      return;
    }
    if (items.some(other => other.teacher === item.teacher && apiSlot(other) === apiSlot(item))) {
      setError("Esta tutoría ya está registrada para el docente.");
      return;
    }
    setError("");
    onChange([...items, item]);
  }
  return <div className="availability-editor mt-4">
    <h3 className="font-bold">Tutorías</h3>
    <p className="muted">Vincula la tutoría con una materia y paralelo; se usará su docente. La reserva cuenta en su carga semanal y ocupa al grupo y al aula durante todo el bloque. Para tutorías generales se usa el docente seleccionado.</p>
    <form onSubmit={add} className="availability-form">
      <fieldset disabled={disabled || !teachers.length || !rooms.length} className="tutoring-fields">
        <label className="label">Materia y paralelo<select className="field" name="session_id"><option value="">Tutoría general</option>{sessions.filter(row => row.kind !== "tutoring").map(row => <option key={row.id} value={row.id}>{row.level} {row.section} · {row.course} · {row.teacher}</option>)}</select></label>
        <label className="label">Docente de tutoría<select className="field" name="teacher">{teachers.map(teacher => <option key={teacher}>{teacher}</option>)}</select></label>
        <label className="label">Día de tutoría<select className="field" name="day">{DAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label>
        <label className="label">Inicio de tutoría<input className="field" name="start" type="time" defaultValue="11:00" required /></label>
        <label className="label">Fin de tutoría<input className="field" name="end" type="time" defaultValue="12:00" required /></label>
        <label className="label">Aula de tutoría<select className="field" name="room">{rooms.map(room => <option key={room}>{room}</option>)}</select></label>
        <Button type="submit">Reservar tutoría</Button>
      </fieldset>
    </form>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {items.length > 0 && <ul className="mt-3 flex flex-wrap gap-2">{items.map((item, index) => <li className="window-chip" key={item.teacher + apiSlot(item)}>
      {item.teacher} · {DAYS[item.day]} {item.start}–{item.end} · {item.room}
      <button type="button" disabled={disabled} aria-label={"Quitar tutoría de " + item.teacher + " " + DAYS[item.day] + " " + item.start}
        onClick={() => onChange(items.filter((_, position) => position !== index))}>×</button>
    </li>)}</ul>}
  </div>;
}

export default function Home() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [parameters, setParameters] = useState(DEFAULTS);
  const [ruleText, setRuleText] = useState("");
  const [availability, setAvailability] = useState<Availability>({});
  const [groupRooms, setGroupRooms] = useState<Record<string, string>>({});
  const [levelFilter, setLevelFilter] = useState("Semestre 1");
  const [parallelFilter, setParallelFilter] = useState("A");
  const [showTutoring, setShowTutoring] = useState(true);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [durations, setDurations] = useState<Record<number, number>>({});
  const [tutoring, setTutoring] = useState<Tutoring[]>([]);
  const [planDirty, setPlanDirty] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [frame, setFrame] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [view, setView] = useState<"original" | "optimized" | "list">("original");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [connection, setConnection] = useState<"loading" | "online" | "offline">("loading");
  const [page, setPage] = useState(1);
  const [dayFilter, setDayFilter] = useState("");
  const [teacherFilter, setTeacherFilter] = useState("");
  const [roomFilter, setRoomFilter] = useState("");
  const [importNotice, setImportNotice] = useState("");

  function report(issue: unknown) {
    setError(issue instanceof Error && issue.message !== "Failed to fetch" ? issue.message : "No se pudo conectar con la API. Comprueba que el backend esté iniciado.");
  }

  async function connect() {
    setConnection("loading");
    setError("");
    try {
      const items = await request<Dataset[]>("/api/datasets");
      setDatasets(items);
      setSelected(previous => previous || items[0]?.id || "");
      setConnection("online");
    } catch {
      setConnection("offline");
    }
  }

  useEffect(() => { void connect(); }, []);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    request<Session[]>("/api/datasets/" + selected + "/sessions", { signal: controller.signal })
      .then(rows => {
        setSessions(rows);
        const meta = datasets.find(item => item.id === selected);
        const configured: Availability = {};
        for (const [teacher, windows] of Object.entries(meta?.rules?.availability ?? {})) {
          configured[teacher] = windows.map(slot => {
            const parts = slot.split(" ");
            return { day: API_DAYS.indexOf(parts[0]), start: parts[1], end: parts[3] };
          });
        }
        setAvailability(configured);
        setGroupRooms(meta?.rules?.group_rooms ?? {});
        const firstClass = rows.find(row => row.kind !== "tutoring");
        setLevelFilter(firstClass?.level ?? "");
        setParallelFilter(firstClass?.section ?? "");
        setTargets(Object.fromEntries(Object.entries(meta?.rules?.weekly_minutes ?? {}).map(([teacher, minutes]) => [teacher, String(minutes / 60)])));
      }).catch(issue => { if (!controller.signal.aborted) report(issue); });
    return () => controller.abort();
  }, [selected, datasets]);

  const activeId = run && (run.status === "queued" || run.status === "running") ? run.id : null;
  useEffect(() => {
    if (!activeId) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const path = "/api/optimizations/" + activeId;
    async function poll() {
      try {
        const [state, points] = await Promise.all([request<Run>(path), request<Metrics>(path + "/metrics")]);
        if (!live) return;
        setMetrics(points);
        if (state.status === "completed") {
          const [output, finalPoints] = await Promise.all([
            request<Result>(path + "/result"), request<Metrics>(path + "/metrics"),
          ]);
          if (!live) return;
          setMetrics(finalPoints);
          setResult(output);
          setView("optimized");
        }
        setRun(state);
        if (state.status === "completed") setError("");
        if (state.status === "queued" || state.status === "running") timer = setTimeout(poll, 300);
        if (state.status === "failed") setError(state.error ?? "Falló la ejecución.");
      } catch (issue) {
        if (live) {
          report(issue);
          timer = setTimeout(poll, 1500);
        }
      }
    }
    void poll();
    return () => { live = false; clearTimeout(timer); };
  }, [activeId]);

  function choose(id: string) {
    setPlanDirty(false);
    if (id === selected) return;
    setSelected(id);
    setSessions([]);
    setAvailability({});
    setTargets({});
    setGroupRooms({});
    setDurations({});
    setTutoring([]);
    setRuleText("");
    setRun(null);
    setResult(null);
    setMetrics(null);
    setFrame(null);
    setPlaying(false);
    setView("original");
    setQuery("");
    setDayFilter("");
    setTeacherFilter("");
    setRoomFilter("");
    setPage(1);
    setError("");
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setImportNotice("");
    setPending(true);
    setError("");
    try {
      const dataset = await request<Dataset>("/api/datasets/import", { method: "POST", body: new FormData(form) });
      setDatasets(items => [...items, dataset]);
      choose(dataset.id);
      setImportNotice("Archivo importado. Revisa las aulas y la carga docente antes de generar el horario.");
      form.reset();
    } catch (issue) { report(issue); }
    finally { setPending(false); }
  }

  async function saveTeachingPlan(assignments: TeachingAssignment[], useLoad: boolean) {
    setPending(true);
    try {
      const dataset = await request<Dataset>("/api/datasets/" + selected + "/teaching-plan", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assignments, use_assigned_load: useLoad }),
      });
      choose(dataset.id);
      setDatasets(items => [...items, dataset]);
      setImportNotice("Plan docente guardado. Genera el horario para validar todas las asignaciones.");
    } finally { setPending(false); }
  }

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (planDirty) { setError("Guarda las asignaciones de docentes y materias antes de generar el horario."); return; }
    setPending(true);
    setError("");
    try {
      const rules = ruleText.trim() ? JSON.parse(ruleText) : {};
      const configured = Object.fromEntries(
        Object.entries(availability).map(([teacher, windows]) =>
          [teacher, windows.map(window => API_DAYS[window.day] + " " + window.start + " - " + window.end)]),
      );
      rules.group_rooms = groupRooms;
      rules.availability = { ...rules.availability, ...configured };
      const weeklyMinutes = Object.entries(targets).map(([teacher, value]) => {
        if (value === "") return [teacher, null];
        const minutes = Number(value) * 60;
        if (!Number.isFinite(minutes) || minutes < 0 || minutes > 7 * 1440) {
          throw new Error("Revisa las horas semanales de " + teacher + ".");
        }
        return [teacher, Math.round(minutes)];
      });
      rules.weekly_minutes = { ...rules.weekly_minutes, ...Object.fromEntries(weeklyMinutes) };
      rules.class_minutes = { ...rules.class_minutes, ...durations };
      rules.tutoring = [...(rules.tutoring ?? []), ...tutoring.map(item => ({ session_id: item.session_id, teacher: item.teacher, room: item.room, slot: apiSlot(item) }))];
      const state = await request<Run>("/api/optimizations", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: selected, parameters, rules }),
      });
      setResult(null);
      setMetrics(null);
      setFrame(null);
      setPlaying(false);
      setView("list");
      setRun(state);
    } catch (issue) { report(issue); }
    finally { setPending(false); }
  }

  useEffect(() => {
    if (activeId) document.getElementById("modelo")?.scrollIntoView({ block: "start" });
  }, [activeId]);

  const points = metrics?.history ?? [];
  const series = [
    ...(result ? [{ label: "Original", hard: result.baseline.score[0], soft: result.baseline.score[1], elapsed: 0 }] : []),
    ...points.map(point => ({ ...point, label: String(point.generation) })),
  ];
  const lastFrame = Math.max(0, series.length - 1);
  const shownFrame = Math.min(frame ?? lastFrame, lastFrame);
  const shownPoint = series[shownFrame];

  useEffect(() => {
    if (!playing) return;
    if (shownFrame >= lastFrame) {
      setPlaying(false);
      return;
    }
    const timer = setTimeout(() => setFrame(Math.min(lastFrame, shownFrame + Math.max(1, Math.ceil(lastFrame / 75)))), 65);
    return () => clearTimeout(timer);
  }, [playing, shownFrame, lastFrame]);

  const teachers = [...new Set(sessions.map(row => row.teacher))].sort();
  const colors = new Map(teachers.map((teacher, index) => [
    teacher, TEACHER_COLORS[index] ?? "hsl(" + Math.round(index * 137.508 % 360) + " 66% 36%)",
  ]));
  const busy = pending || Boolean(activeId);
  const rooms = datasets.find(item => item.id === selected)?.rooms ?? [...new Set(sessions.map(row => row.room))].sort();
  const current = view === "optimized" ? result?.optimized ?? [] : view === "original" ? result?.original ?? sessions : sessions;
  const plannedMinutes = new Map<string, number>();
  for (const row of sessions) {
    plannedMinutes.set(row.teacher, (plannedMinutes.get(row.teacher) ?? 0) + (durations[row.id] ?? row.end - row.start));
  }
  for (const item of tutoring) {
    const minutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3));
    plannedMinutes.set(item.teacher, (plannedMinutes.get(item.teacher) ?? 0) + minutes(item.end) - minutes(item.start));
  }
  const groupKey = (row: Session) => row.group_key ?? JSON.stringify([row.program,row.major,row.level,row.section]);
  const classGroups = [...new Map(sessions.filter(row => row.kind !== "tutoring").map(row => [groupKey(row),row])).values()]
    .sort((a,b) => a.level.localeCompare(b.level, "es", {numeric:true}) || a.section.localeCompare(b.section));
  const groupTeachers = new Set(current.filter(row => row.kind !== "tutoring" && (!levelFilter || row.level === levelFilter) && (!parallelFilter || row.section === parallelFilter)).map(row => row.teacher));
  const filtered = current.filter(row => {
    const academic = row.kind === "tutoring"
      ? showTutoring && (/^Semestre [1-9]$/.test(row.level) ? (!levelFilter || row.level === levelFilter) && (!parallelFilter || row.section === parallelFilter) : (!levelFilter && !parallelFilter || groupTeachers.has(row.teacher)))
      : (!levelFilter || row.level === levelFilter) && (!parallelFilter || row.section === parallelFilter);
    return academic && (dayFilter === "" || row.day === Number(dayFilter)) &&
      (!teacherFilter || row.teacher === teacherFilter) && (!roomFilter || row.room === roomFilter) &&
      [row.course,row.teacher,row.room,row.program,row.major,row.level,row.section,String(row.id)]
        .some(value => value.toLowerCase().includes(query.trim().toLowerCase()));
  });
  const visibleTeachers = [...new Set(filtered.map(row => row.teacher))].sort();
  const originalById = new Map(result?.original.map(row => [row.id, row]));
  const changes = (result?.optimized ?? []).flatMap(after => {
    const before = originalById.get(after.id);
    return before && (before.slot !== after.slot || before.room !== after.room) ? [{ before, after }] : [];
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / 8));
  const currentPage = Math.min(page, totalPages);
  const selectedDataset = datasets.find(dataset => dataset.id === selected);
  const cards = [
    { name: "Clases semanales", value: sessions.filter(row => row.kind !== "tutoring").length, icon: Layers3, color: "indigo" },
    { name: "Docentes", value: new Set(sessions.map(s => s.teacher)).size, icon: Users, color: "violet" },
    { name: "Aulas", value: new Set(sessions.map(s => s.room)).size, icon: DoorOpen, color: "mint" },
    { name: "Tutorías", value: sessions.filter(row => row.kind === "tutoring").length + tutoring.length, icon: CalendarDays, color: "peach" },
  ];

  return <div className="workspace">
    <aside className="sidebar">
      <a href="#inicio" className="brand"><span className="brand-icon"><CalendarDays size={22} /></span><span>HorarioGen<small>Planificación · v0.1.4</small></span></a>
      <nav aria-label="Navegación principal">
        <a href="#inicio"><LayoutDashboard size={18} /> Mi planificación</a>
        <a href="#sesiones"><CalendarDays size={18} /> Horarios</a>
        <a href="#datos"><Database size={18} /> Datos académicos</a>
        <a href="#asignaciones"><Users size={18} /> Docentes y materias</a>
        <a href="#flujo-aulas"><DoorOpen size={18} /> Flujo de aulas</a>
        <a href="#reglas"><Settings2 size={18} /> Modelo y reglas</a>
        <a href="#optimizar"><Workflow size={18} /> Optimización</a>
        {run && <a href="#modelo"><Activity size={18} /> Modelo visual</a>}
      </nav>
      <div className="sidebar-status"><span data-online={connection === "online"} />{connection === "online" ? "Sistema conectado" : connection === "loading" ? "Conectando…" : "Servicio sin conexión"}</div>
    </aside>
    <div id="inicio" className="workspace-body">
      <header className="topbar"><span>Planificación académica <ChevronRight size={14} /> <strong>Panel de trabajo</strong></span><a href="#datos"><FileUp size={16} /> Importar archivo</a></header>
      <main className="dashboard">
        <section className="hero">
          <div className="hero-copy">
            <p className="hero-kicker"><CalendarDays size={15} /> PLANIFICACIÓN ACADÉMICA</p>
            <h1>Una semana bien planificada.</h1>
            <p>Clases, carga docente y tutorías en un solo horario. Planifica con las aulas 106 a 112 y verifica la disponibilidad de tu equipo.</p>
            <div className="hero-actions"><Button form="optimization-form" type="submit" disabled={busy || !sessions.length}><Play size={16} /> {busy ? "Procesando…" : "Generar horario"}</Button><a href="#sesiones">Ver sesiones <ArrowDown size={15} /></a></div>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="mini-calendar">
              <div className="mini-title"><CalendarDays size={18} /><span></span><i></i><i></i></div>
              <div className="mini-days"><span>LUN</span><span>MAR</span><span>MIÉ</span><span>JUE</span><span>VIE</span></div>
              <div className="mini-grid">{Array.from({length:15}, (_, i) => <i key={i} data-cell={i} />)}</div>
            </div>
            <span className="art-check"><CheckCircle2 size={23} /></span>
          </div>
        </section>
        <nav className="workflow-nav" aria-label="Pasos de planificación">
          <a href="#datos"><FileUp size={18} /><span><strong>Carga tus datos</strong><small>Excel o CSV</small></span></a>
          <a href="#reglas"><Users size={18} /><span><strong>Revisa disponibilidad</strong><small>Carga y tutorías</small></span></a>
          <a href="#sesiones"><CalendarDays size={18} /><span><strong>Genera y compara</strong><small>Calendario semanal</small></span></a>
        </nav>
        {importNotice && <div className="import-success" role="status"><CheckCircle2 size={18} /><p>{importNotice}</p><button aria-label="Cerrar aviso" onClick={() => setImportNotice("")}>×</button></div>}
        {selectedDataset?.warnings?.map(warning => <p key={warning} className="notice">{warning}</p>)}
        {connection === "offline" && <div className="notice" role="alert"><WifiOff size={20} /><div><strong>No se pudo conectar con el servicio</strong><p>Inicia HorarioGen con Iniciar-HorarioGen.cmd y vuelve a intentar.</p></div><Button variant="outline" onClick={() => void connect()}>Reintentar</Button></div>}
        {error && <p role="alert" className="notice">{error}</p>}
        <section className="stat-grid" aria-label="Resumen del dataset">
          {cards.map(({name, value, icon: Icon, color}) => <div className="stat-card" key={name}><span className={"stat-icon " + color}><Icon size={20} /></span><div><p>{name}</p><strong>{sessions.length ? value : "—"}</strong></div></div>)}
        </section>
        <Card id="datos" className="product-card">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-bold"><FileUp size={19} /> Importa tu planificación</h2>
          <p className="muted mb-4">Excel reúne sesiones, aulas, carga y disponibilidad. Con CSV puedes cargar sesiones y completar las reglas aquí.</p>
          <div className="template-links"><a href={API + "/api/templates/xlsx"}><Download size={15} /> Plantilla Excel</a><a href={API + "/api/templates/csv"}><Download size={15} /> Plantilla CSV</a></div>
          <label className="label">Conjunto de datos<select className="field" value={selected} onChange={e => choose(e.target.value)} disabled={busy}>
            {!datasets.length && <option value="">Selecciona o importa un CSV</option>}
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name} · {d.count} sesiones</option>)}
          </select></label>
          <form onSubmit={upload} className="mt-5 grid gap-3 border-t border-slate-200 pt-4">
            <label className="upload-zone"><FileUp size={25} /><strong>Selecciona tu archivo de planificación</strong><span>Excel .xlsx o CSV UTF-8 · Hasta 5 MiB</span><input aria-label="Archivo de planificación" name="file" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required disabled={busy} /></label>
            <label className="flex items-center gap-2 muted"><input name="legacy_hours" value="true" type="checkbox" disabled={busy} /> Interpretar 01:00–07:59 como horas de la tarde</label>
            <Button type="submit" variant="outline" disabled={busy} className="justify-self-start"><FileUp size={16} /> Importar</Button>
          </form>
        </Card>
      {run && <Card id="modelo" className="product-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-xl font-bold"><Activity size={22} /> Modelo en acción</h2>
          <span className="model-badge">{{queued:"En cola", running:"En vivo", completed:"Completado", failed:"Interrumpido"}[run.status]}</span>
        </div>
        <p className="mt-2 muted">El algoritmo prioriza reducir los conflictos. Entre horarios con los mismos conflictos, busca la menor penalización.</p>
        {shownPoint ? <>
          <div className="model-stats">
            <div><small>Etapa</small><strong>{shownPoint.label === "Original" ? "Horario original" : "Generación " + shownPoint.label}</strong></div>
            <div><small>Conflictos</small><strong>{shownPoint.hard}</strong></div>
            <div><small>Penalización</small><strong>{shownPoint.soft}</strong></div>
            <div><small>Tiempo registrado</small><strong>{shownPoint.elapsed.toFixed(2)} s</strong></div>
          </div>
          <div className="model-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series.slice(0, shownFrame + 1)} margin={{ right: 12 }}>
                <CartesianGrid stroke="#e7e8f2" strokeDasharray="3 4" />
                <XAxis dataKey="label" minTickGap={24} />
                <YAxis yAxisId="hard" allowDecimals={false} width={30} />
                <YAxis yAxisId="soft" orientation="right" allowDecimals={false} width={30} />
                <Tooltip labelFormatter={label => label === "Original" ? "Horario original" : "Generación " + label} />
                <Legend />
                <Line yAxisId="hard" type="stepAfter" dataKey="hard" name="Conflictos (izq.)" stroke="#5141cf" strokeWidth={3} dot={shownFrame < 2} isAnimationActive={false} />
                <Line yAxisId="soft" type="stepAfter" dataKey="soft" name="Penalización (der.)" stroke="#0c8365" strokeWidth={2} dot={shownFrame < 2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {result && lastFrame > 0 && <div className="model-controls">
            <Button type="button" variant="outline" onClick={() => {
              if (playing) setPlaying(false);
              else { if (shownFrame >= lastFrame) setFrame(0); setPlaying(true); }
            }}>{playing ? <Pause size={16} /> : <Play size={16} />}{playing ? "Pausar" : "Reproducir ejecución"}</Button>
            <input type="range" aria-label="Etapa del modelo" aria-valuetext={shownPoint.label === "Original" ? "Horario original" : "Generación " + shownPoint.label}
              min={0} max={lastFrame} value={shownFrame} onChange={e => { setPlaying(false); setFrame(e.target.valueAsNumber); }} />
            <Button type="button" variant="outline" onClick={() => { setPlaying(false); setFrame(null); }}>Ir al final</Button>
          </div>}
        </> : <p className="empty-state mt-4" role="status">{run.status === "failed" ? "La ejecución se interrumpió antes de registrar una generación." : "Esperando la primera generación…"}</p>}
      </Card>}
      {result && metrics && <Card id="resultado" className="product-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-bold">Resultado de la optimización</h2>
          <a href={API + "/api/optimizations/" + run?.id + "/export"} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-teal-900"><Download size={16} /> Exportar CSV</a>
        </div>
        <p className="mt-3 muted">{metrics.reason && STOP[metrics.reason]} · {changes.length} {changes.length === 1 ? "sesión reasignada" : "sesiones reasignadas"}</p>
        <div className="result-summary"><div><small>Conflictos evaluables</small><strong>{result.baseline.score[0]} → {result.evaluation.score[0]}</strong></div><div><small>Sesiones conservadas</small><strong>{result.optimized.length} / {result.original.length}</strong></div><a href="#sesiones">Abrir horario <ArrowDown size={15} /></a></div>
        <p className={"chip mt-3 " + (result.evaluation.feasible ? "bg-teal-100 text-teal-900" : "bg-amber-100 text-amber-900")}>
          {result.evaluation.feasible ? "Factible según las restricciones evaluadas" : "La ejecución terminó con conflictos pendientes"}
        </p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div>
            <table className="w-full text-sm"><thead><tr>
              <th className="table-cell">Conflictos</th><th className="table-cell">Original</th><th className="table-cell">Optimizado</th>
            </tr></thead><tbody>
              {Object.entries(result.evaluation.hard).map(([kind, count]) => <tr key={kind} className="border-t">
                <th scope="row" className="table-cell font-medium">{LABELS[kind]}</th><td className="table-cell">{result.baseline.hard[kind]}</td><td className="table-cell">{count}</td>
              </tr>)}
              <tr className="border-t font-semibold"><th className="table-cell">Penalización blanda</th><td className="table-cell">{result.baseline.score[1]}</td><td className="table-cell">{result.evaluation.score[1]}</td></tr>
            </tbody></table>
            <p className="mt-3 muted">Cobertura en el horario optimizado · Aforo {result.evaluation.coverage.capacity}/{result.optimized.length} · Disponibilidad docente {result.evaluation.coverage.availability}/{result.optimized.length} · Preferencias {result.evaluation.coverage.preferences}/{result.optimized.length}.</p>
            {([["original", result.baseline], ["optimizado", result.evaluation]] as const).map(([name, evaluation]) =>
              evaluation.conflicts.length > 0 && <details key={name} className="mt-3 text-sm">
                <summary className="cursor-pointer font-semibold">Sesiones con conflictos en el horario {name}</summary>
                <ul className="mt-2 max-h-48 overflow-auto">{evaluation.conflicts.map((item, i) =>
                  <li key={i}>{LABELS[item.type]} · {item.teacher ?? item.sessions.map(id => "#" + id).join(", ")}</li>
                )}</ul>
              </details>
            )}
          </div>
          <div>
            <h3 className="mb-3 font-bold">Cambios de horario</h3>
            {Object.entries(result.evaluation.workload ?? {}).some(([, row]) => row.target !== null) && <ul className="mb-4 text-sm">
              {Object.entries(result.evaluation.workload ?? {}).filter(([, row]) => row.target !== null).map(([teacher, row]) =>
                <li key={teacher}>{teacher} · {hours(row.scheduled)} de {hours(row.target!)} · {row.scheduled === row.target ? "Cumple" : "No cumple"}</li>)}
            </ul>}
            {changes.length ? <ul className="model-changes">{changes.map(({before, after}) => <li key={after.id}>
              <strong>#{after.id} · {after.course}</strong><p className="muted">{after.teacher}</p>
              <div className="model-diff">
                <div><small>Original</small><strong>{DAYS[before.day]} · {clock(before.start)}–{clock(before.end)}</strong><span>{before.room}</span></div>
                <ArrowRight size={17} aria-hidden />
                <div><small>Optimizado</small><strong>{DAYS[after.day]} · {clock(after.start)}–{clock(after.end)}</strong><span>{after.room}</span></div>
              </div>
            </li>)}</ul> : <p className="muted">El modelo conservó las franjas y aulas originales.</p>}
          </div>
        </div>
      </Card>}
      <TeachingPlanner sessions={sessions} sessionDays={datasets.find(item => item.id === selected)?.rules?.session_days} disabled={busy} onSave={saveTeachingPlan} onDirtyChange={setPlanDirty} />
      <Card id="sesiones" className="product-card schedule-panel">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div><h2 className="text-xl font-bold">Tu semana académica</h2><p className="mt-1 muted">{selectedDataset?.name === "Escenario académico v0.1.4.csv" ? "Escenario de ejemplo · Docentes y disponibilidad ficticios" : selectedDataset?.name ?? "Selecciona un conjunto de datos"}</p></div>
          <div className="segments" aria-label="Vista del horario">
            {([["list", "Sesiones"], ["original", "Inicial"], ["optimized", "Generado"]] as const).map(([key, name]) =>
              <Button key={key} variant={view === key ? "primary" : "outline"} aria-pressed={view === key} disabled={key === "optimized" && !result} onClick={() => { setView(key); setPage(1); }}>{name}</Button>)}
          </div>
        </div>
        {visibleTeachers.length > 0 && <ul className="teacher-legend" aria-label="Colores de los docentes">
          {visibleTeachers.map(teacher => <li key={teacher} className="teacher-label" style={teacherStyle(colors.get(teacher)!)}>{teacher}</li>)}
        </ul>}
        {view !== "list" && <p className="muted mb-3"><span className="tutor-key">Tutoría</span> Los bloques con borde discontinuo son tutorías reservadas.</p>}
        <div className="academic-filters">
          <label>Semestre<select className="field" aria-label="Semestre del horario" value={levelFilter} onChange={event => { setLevelFilter(event.target.value); setParallelFilter(event.target.value ? sessions.find(row => row.kind !== "tutoring" && row.level === event.target.value)?.section ?? "" : ""); setPage(1); }}>
            <option value="">Todos los semestres</option>{Array.from({length:9},(_,index) => "Semestre " + (index+1)).map(level => <option key={level}>{level}</option>)}
          </select></label>
          <label>Paralelo<select className="field" aria-label="Paralelo del horario" value={parallelFilter} onChange={event => { setParallelFilter(event.target.value); setPage(1); }}>
            <option value="">Todos los paralelos</option><option value="A">Paralelo A</option><option value="B">Paralelo B</option>
          </select></label>
          <label className="tutorial-toggle"><input type="checkbox" checked={showTutoring} onChange={event => setShowTutoring(event.target.checked)} /> Incluir tutorías del paralelo</label>
          <div className="shift-label"><strong>{levelFilter ? levelFilter + (Number(levelFilter.match(/\d+/)?.[0]) % 2 ? " · Mañana" : " · Tarde") : "Jornadas por semestre"}</strong><span>{levelFilter ? Number(levelFilter.match(/\d+/)?.[0]) % 2 ? "07:00–13:00" : "14:00–20:00" : "Impares: mañana · Pares: tarde"}</span></div>
        </div>
        {levelFilter && <p className="muted mb-3">{new Set(current.filter(row => row.kind !== "tutoring" && row.level === levelFilter && (!parallelFilter || row.section === parallelFilter)).map(row => row.course)).size} materias en la selección · Ambos paralelos comparten la jornada de su semestre. Receso: 13:00–14:00.</p>}
        {!levelFilter && <p className="muted mb-3">Vista general en agenda. Selecciona un semestre y paralelo para consultar su cuadrícula semanal.</p>}
        <div className="table-tools">
          <label className="search-box"><Search size={18} /><input aria-label="Buscar sesiones" placeholder="Buscar asignatura, docente, aula o grupo…" value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} /></label>
          <select aria-label="Filtrar por docente" className="field" value={teacherFilter} onChange={event => { setTeacherFilter(event.target.value); setPage(1); }}>
            <option value="">Todos los docentes</option>{teachers.map(teacher => <option key={teacher}>{teacher}</option>)}
          </select>
          <select aria-label="Filtrar por aula" className="field" value={roomFilter} onChange={event => { setRoomFilter(event.target.value); setPage(1); }}>
            <option value="">Todas las aulas</option>{rooms.map(room => <option value={room} key={room}>Aula {room}</option>)}
          </select>
          <select aria-label="Filtrar por día" className="field" value={dayFilter} onChange={e => { setDayFilter(e.target.value); setPage(1); }}>
            <option value="">Todos los días</option>{DAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}
          </select>
        </div>
        {filtered.length === 0 ? <div className="empty-state"><CalendarDays size={26} /><strong>{connection === "loading" ? "Cargando sesiones…" : sessions.length ? "Sin coincidencias" : "Aún no hay sesiones"}</strong><p>{sessions.length ? "Prueba otra búsqueda o cambia el filtro de día." : "Selecciona un conjunto de datos o importa un CSV."}</p></div> : view !== "list" ? <Schedule rows={filtered} colors={colors} /> :
          <div className="table-frame">
            <div className="overflow-auto"><table className="w-full min-w-[740px] text-sm">
              <thead><tr>{["Asignatura", "Docente", "Grupo", "Día y hora", "Aula", "Duración"].map(label => <th scope="col" className="table-cell" key={label}>{label}</th>)}</tr></thead>
              <tbody>{filtered.slice((currentPage - 1) * 8, currentPage * 8).map(s => <tr key={s.id}>
                <td className="table-cell"><strong>{s.course}</strong><small>Sesión #{s.id}</small></td>
                <td className="table-cell"><span className="teacher-label" style={teacherStyle(colors.get(s.teacher) ?? "#593dc5")}>{s.teacher}</span></td>
                <td className="table-cell">{s.program} · {s.section}<small>{s.level} · {s.major}</small></td>
                <td className="table-cell"><strong>{DAYS[s.day]}</strong><small>{clock(s.start)} – {clock(s.end)}</small></td>
                <td className="table-cell"><span className="room-tag">{s.room}</span></td>
                <td className="table-cell">{s.kind === "tutoring" || view !== "list" ? hours(s.end - s.start) : <select
                  className="field duration-field" aria-label={"Duración de sesión " + s.id} disabled={busy}
                  value={durations[s.id] ?? s.end - s.start} onChange={event => setDurations(previous => {
                    const next = { ...previous };
                    const minutes = Number(event.target.value);
                    if (minutes === s.end - s.start) delete next[s.id];
                    else next[s.id] = minutes;
                    return next;
                  })}>
                  {[...new Set([60, 120, 180, 240, s.end - s.start])].sort((a, b) => a - b).map(minutes => <option value={minutes} key={minutes}>{hours(minutes)}</option>)}
                </select>}</td>
              </tr>)}</tbody>
            </table></div>
            <div className="pagination"><span>{(currentPage - 1) * 8 + 1}–{Math.min(currentPage * 8, filtered.length)} de {filtered.length} sesiones</span><div>
              <Button variant="outline" aria-label="Página anterior" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={16} /></Button>
              <span>{currentPage} / {totalPages}</span>
              <Button variant="outline" aria-label="Página siguiente" disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}><ChevronRight size={16} /></Button>
            </div></div>
          </div>}
      </Card>
      <RoomFlow rows={result?.optimized ?? sessions} rooms={rooms} colors={colors} generated={Boolean(result)} />
      <Card id="reglas" className="product-card">
        <h2 className="text-xl font-bold">Modelo y reglas</h2>
        <p className="mt-2 muted">El modelo representa cada sesión con una franja y un aula. Conserva su materia, docente, grupo y duración.</p>
        <div className="room-inventory"><div><h3>Aulas disponibles</h3><p>El generador utiliza las aulas registradas en el archivo.</p></div><ul>{rooms.map(room => <li key={room}><DoorOpen size={17} /><strong>{room}</strong></li>)}</ul></div>
        <details className="parallel-assignments"><summary>Aulas por semestre y paralelo</summary>
          <p className="muted mt-2">Cada paralelo usa el aula asignada a todas sus clases. Los grupos pueden compartir aula en franjas diferentes.</p>
          <div className="overflow-auto mt-3"><table className="w-full text-sm">
            <thead><tr><th className="table-cell">Semestre</th><th className="table-cell">Paralelo</th><th className="table-cell">Aula asignada</th></tr></thead>
            <tbody>{classGroups.map(row => <tr key={groupKey(row)} className="border-t">
              <td className="table-cell">{row.level}<small className="block text-slate-500">{row.program}</small></td><td className="table-cell">{row.section}</td>
              <td className="table-cell"><select className="field" aria-label={"Aula de " + row.level + " paralelo " + row.section} disabled={busy}
                value={groupRooms[groupKey(row)] ?? row.room} onChange={event => setGroupRooms({...groupRooms,[groupKey(row)]:event.target.value})}>
                  {rooms.map(room => <option value={room} key={room}>Aula {room}</option>)}
              </select></td></tr>)}</tbody>
          </table></div>
        </details>
        <div className="rule-grid">
          <div><h3>Reglas obligatorias</h3><ul>
            <li>Semestres 1, 3, 5, 7 y 9: mañana (07:00–13:00). Semestres 2, 4, 6 y 8: tarde (14:00–20:00), en ambos paralelos. Las tutorías de materia respetan esta jornada y reservan también al paralelo.</li>
            <li>Las clases se imparten en el aula asignada al semestre y paralelo.</li>
            <li>Una sesión debe estar dentro de la disponibilidad registrada del docente.</li>
            <li>Un docente, aula o grupo no puede estar en dos sesiones simultáneas.</li>
            <li>Todas las sesiones deben quedar asignadas y mantener su duración.</li>
            <li>La carga lectiva semanal debe coincidir con las horas configuradas, incluidas las tutorías.</li>
            <li>El aula debe tener capacidad suficiente cuando se conocen el aforo y la matrícula.</li>
          </ul></div>
          <div><h3>Preferencias del modelo</h3><ul>
            <li>Reducir los cambios de franja y de aula respecto al horario original.</li>
            <li>Reducir tiempos muertos de los grupos.</li>
            <li>Respetar las preferencias horarias registradas.</li>
          </ul><p className="mt-3 muted">El algoritmo minimiza primero los incumplimientos obligatorios y después la penalización de las preferencias.</p></div>
        </div>
        <AvailabilityEditor teachers={teachers} colors={colors} value={availability} onChange={setAvailability} disabled={busy} />
        <div className="availability-editor mt-4">
          <h3 className="font-bold">Carga lectiva semanal</h3>
          <p className="muted">Indica las horas de clase y tutoría que debe cumplir cada docente. Deja la meta vacía si careces de ese dato. Ajusta los bloques de 1 a 4 horas en la columna Duración de la lista de sesiones.</p>
          <div className="mt-3 overflow-auto"><table className="w-full text-sm">
            <thead><tr><th className="table-cell">Docente</th><th className="table-cell">Meta semanal</th><th className="table-cell">Horas previstas</th><th className="table-cell">Diferencia</th></tr></thead>
            <tbody>{teachers.map(teacher => {
              const target = targets[teacher] ?? "";
              const scheduled = plannedMinutes.get(teacher) ?? 0;
              const difference = target === "" ? null : scheduled - Math.round(Number(target) * 60);
              return <tr className="border-t" key={teacher}>
                <td className="table-cell"><span className="teacher-label" style={teacherStyle(colors.get(teacher)!)}>{teacher}</span></td>
                <td className="table-cell"><input className="field duration-field" type="number" min="0" max="168" step="any" placeholder="Horas" aria-label={"Meta semanal de " + teacher} disabled={busy} value={target} onChange={event => setTargets({ ...targets, [teacher]: event.target.value })} /></td>
                <td className="table-cell">{hours(scheduled)}</td>
                <td className="table-cell">{difference === null ? "—" : difference === 0 ? "Cumple" : difference < 0 ? "Faltan " + hours(-difference) : "Exceso de " + hours(difference)}</td>
              </tr>;
            })}</tbody>
          </table></div>
          <p className="muted">Mover una sesión de día o aula no cambia la carga. Para corregir un desfase, revisa las duraciones, las sesiones asignadas o las tutorías.</p>
        </div>
        <TutoringEditor teachers={teachers} rooms={rooms} sessions={sessions} items={tutoring} onChange={setTutoring} disabled={busy} />
      </Card>
      <div>
        <Card id="optimizar" className="product-card">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-bold"><Settings2 size={19} /> Optimización</h2>
          <form id="optimization-form" onSubmit={start} className="space-y-4">
            <p className="muted">El algoritmo evoluciona horarios candidatos y conserva el mejor. Puedes aumentar las generaciones para ampliar la búsqueda.</p>
            <fieldset disabled={busy} className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
              {FIELDS.slice(0, 3).map(([key, title, min, max, step]) => <label className="label" key={key}>{title}
                <input className="field" type="number" required min={min} max={max} step={step}
                  value={Number.isNaN(parameters[key]) ? "" : parameters[key]}
                  onChange={e => setParameters(p => ({ ...p, [key]: e.target.valueAsNumber }))} />
              </label>)}
            </fieldset>
            <details className="advanced">
              <summary>Parámetros avanzados</summary>
              <fieldset disabled={busy} className="mt-3 grid grid-cols-2 gap-3">
                {FIELDS.slice(3).map(([key, title, min, max, step]) => <label className="label" key={key}>{title}
                  <input className="field" type="number" required min={min} max={max} step={step}
                    value={Number.isNaN(parameters[key]) ? "" : parameters[key]}
                    onChange={e => setParameters(p => ({ ...p, [key]: e.target.valueAsNumber }))} />
                </label>)}
              </fieldset>
            </details>
            <details className="advanced">
              <summary>Aforos, matrículas y preferencias</summary>
              <label className="label mt-3">Reglas adicionales en JSON
                <textarea className="field font-mono" rows={4} value={ruleText} disabled={busy} onChange={e => setRuleText(e.target.value)} placeholder='{"capacities": {}, "enrollments": {}, "preferences": {}}' />
              </label>
              <p className="mt-2 muted">Usa el nombre exacto del aula o docente y el ID numérico de sesión para matrículas. Escribe intervalos como Monday 08:00 - 10:00.</p>
            </details>
            <Button disabled={busy || !selected || !sessions.length} type="submit"><Play size={16} /> {busy ? "Buscando un horario…" : "Generar horario"}</Button>
            {run && <p aria-live="polite" className="run-status">
              {{ queued: "En cola", running: "En ejecución", completed: "Completada", failed: "Fallida" }[run.status]}
              {run.progress && ["running", "completed"].includes(run.status) && " · Generación " + run.progress.generation + " · " + run.progress.elapsed + " s"}
            </p>}
          </form>
        </Card>
      </div>
      </main>
    </div>
  </div>;
}

