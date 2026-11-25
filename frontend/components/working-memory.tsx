import { Activity } from "lucide-react";
import { Button, Card } from "./ui";

export type Memory = {
  status: string; generation: number | null; maximum_generations: number; seed: number;
  population_size: number; repairs: number; best: { hard: number; soft: number; elapsed: number } | null;
  facts: { sessions?: number; tutorials?: number; teachers?: string[]; rooms?: string[]; groups?: string[] };
  constraints: string[]; conflict_total: number;
  conflicts: { type: string; sessions: number[]; resource?: string | string[] }[];
  events: { sequence: number; type: string; generation: number | null; timestamp: string }[];
  preview: { id: number; course: string; slot: string; room: string }[];
};

const events: Record<string, string> = {
  RUN_STARTED: "Ejecución iniciada", FACTS_LOADED: "Datos de planificación cargados",
  CONFLICT_DETECTED: "Conflicto detectado", REPAIR_APPLIED: "Reparación aplicada",
  GENERATION_COMPLETED: "Generación registrada", BEST_CANDIDATE_UPDATED: "Mejor candidato actualizado",
  FEASIBLE_SCHEDULE_FOUND: "Horario sin infracciones obligatorias encontrado",
  RUN_COMPLETED: "Ejecución completada", RUN_CANCELLED: "Ejecución cancelada", RUN_FAILED: "Ejecución fallida",
};
const statusLabels: Record<string, string> = {
  queued: "En cola", running: "En ejecución", completed: "Completada", cancelled: "Cancelada", failed: "Fallida",
};

export function WorkingMemoryPanel({ memory, status, labels, cancelling, cancel }: {
  memory: Memory | null; status?: string; labels: Record<string, string>; cancelling: boolean; cancel: () => void;
}) {
  const phase = memory?.status ?? status;
  return <Card id="memoria" className="product-card institutional-panel">
    <div className="institutional-heading"><h2><Activity size={20} /> Memoria de trabajo</h2>
      {(phase === "queued" || phase === "running") && <Button type="button" variant="outline" disabled={cancelling} onClick={cancel}>
        {cancelling ? "Cancelación solicitada" : "Cancelar ejecución"}
      </Button>}</div>
    {!memory ? <p className="muted">{status ? statusLabels[status] + " · Esperando la primera lectura." : "Genera un horario para observar la ejecución."}</p> : <>
      <p role="status">{statusLabels[memory.status]}</p>
      <dl className="memory-metrics">
        <div><dt>Generación</dt><dd>{memory.generation ?? "—"} / {memory.maximum_generations}</dd></div>
        <div><dt>Población</dt><dd>{memory.population_size}</dd></div>
        <div><dt>Mejor puntuación (D, B)</dt><dd>{memory.best ? memory.best.hard + ", " + memory.best.soft : "—"}</dd></div>
        <div><dt>Reparaciones</dt><dd>{memory.repairs}</dd></div>
        <div><dt>Tiempo registrado</dt><dd>{memory.best ? memory.best.elapsed.toFixed(2) + " s" : "—"}</dd></div>
        <div><dt>Semilla</dt><dd>{memory.seed}</dd></div>
      </dl>
      <p className="muted">La generación mide el avance de la búsqueda hasta su condición de parada.</p>
      <details><summary>Hechos y restricciones</summary>
        <p>{memory.facts.sessions ?? 0} sesiones · {memory.facts.tutorials ?? 0} tutorías · {memory.facts.groups?.length ?? 0} paralelos</p>
        <p>{memory.facts.teachers?.length ?? 0} docentes · Aulas {memory.facts.rooms?.join(", ") || "—"}</p>
        <ul>{memory.constraints.map(code => <li key={code}>{labels[code] ?? code}</li>)}</ul>
      </details>
      <details><summary>Conflictos del mejor candidato ({memory.conflict_total})</summary>
        {memory.conflicts.length ? <ul>{memory.conflicts.map((item, i) => <li key={i}>
          {labels[item.type] ?? item.type} · Sesiones {item.sessions.join(", ")}{item.resource ? " · " + String(item.resource) : ""}
        </li>)}</ul> : <p className="muted">{memory.best ? "Sin conflictos registrados." : "Evaluación pendiente."}</p>}
      </details>
      <details><summary>Eventos recientes ({memory.events.length})</summary>
        <ol className="memory-events">{[...memory.events].reverse().map(event => <li key={event.sequence}>
          <time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleTimeString("es-EC")}</time>
          {" · "}{events[event.type] ?? event.type}{event.generation === null ? "" : " · Generación " + event.generation}
        </li>)}</ol>
      </details>
      <details><summary>Vista previa del candidato ({memory.preview.length} sesiones)</summary>
        <ul>{memory.preview.map(item => <li key={item.id}>{item.course} · {item.slot} · Aula {item.room}</li>)}</ul>
      </details>
    </>}
  </Card>;
}
