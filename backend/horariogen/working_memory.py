from collections import deque
from datetime import datetime, timezone
from threading import Event, RLock


class WorkingMemory:
    """One run's published snapshot, separate from its worker-owned population."""

    def __init__(self, run_id, dataset_id, config):
        self.cancelled = Event()
        self.lock = RLock()
        self.events = deque(maxlen=250)
        self.sequence = 0
        self.population = ()
        self.best = None
        self.best_occupancy = {}
        self.summary = {
            "run_id": run_id, "scenario_id": dataset_id, "status": "queued",
            "generation": None, "maximum_generations": config.generations,
            "seed": config.seed, "population_size": 0, "best": None,
            "facts": {}, "constraints": [], "conflicts": [], "conflict_total": 0,
            "repairs": 0,
        }

    def emit(self, kind, **fields):
        with self.lock:
            self.sequence += 1
            self.events.append({
                "sequence": self.sequence, "type": kind,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "generation": self.summary["generation"], **fields,
            })

    def update(self, **fields):
        with self.lock:
            self.summary.update(fields)

    def record(self, population, best, evaluation, point, preview):
        with self.lock:
            previous = self.best
            self.population, self.best = tuple(population), best
            self.best_occupancy = evaluation.occupancy
            conflicts = evaluation.conflicts
            self.update(generation=point["generation"], population_size=len(population),
                        best=point, conflicts=conflicts[:100], conflict_total=len(conflicts),
                        preview=preview)
            if conflicts:
                self.emit("CONFLICT_DETECTED", conflict=conflicts[0], count=len(conflicts))
            if previous is None or best[0] < previous[0]:
                self.emit("BEST_CANDIDATE_UPDATED", fitness=best[0])
                if best[0][0] == 0 and (previous is None or previous[0][0]):
                    self.emit("FEASIBLE_SCHEDULE_FOUND", fitness=best[0])
            self.emit("GENERATION_COMPLETED", fitness=best[0])

    def repair(self, session_id, before, after):
        with self.lock:
            self.summary["repairs"] += 1
            self.emit("REPAIR_APPLIED", sessions=[session_id], before=before, after=after)

    def snapshot(self):
        with self.lock:
            return {**self.summary, "events": list(self.events)}


class OptimizationCancelled(Exception):
    pass
