# Optimization working memory

Each run owns one `WorkingMemory` instance. The single worker holds the current population and best candidate in RAM. The API reads a synchronized snapshot of planning facts, evaluated constraints, current generation, current fitness, elapsed time, repair count, best candidate preview, and recorded conflicts. Each candidate evaluation builds its own occupancy index. Working memory retains the latest observed best candidate's index in RAM. The frontend receives summaries through polling.

A run starts queued, enters running, then finishes as completed, cancelled, or failed. Cancellation is cooperative. It is checked during candidate construction, the repair loop, and generation processing, and a terminal run rejects cancellation. A process restart marks interrupted runs failed.

The genetic algorithm records each observed generation and emits events when it finds an improved candidate, reaches feasibility, or applies a repair. A conflict event describes the currently observed best candidate. Events have a monotonic sequence, UTC timestamp, generation where available, and details from the operation. The API retains up to 250 events, 100 conflict records, and 20 preview sessions. The run record persists generation summaries, terminal memory, and final results. Complete populations are discarded after execution.

| Method and path | Purpose |
|---|---|
| `POST /api/planning/validate` | Preview feasibility diagnostics |
| `POST /api/optimizations` | Queue an optimization |
| `GET /api/optimizations/{id}` | Read run status and latest point |
| `GET /api/optimizations/{id}/memory` | Read synchronized state and recent events |
| `GET /api/optimizations/{id}/metrics` | Read generation history |
| `POST /api/optimizations/{id}/cancel` | Request cancellation |
| `GET /api/optimizations/{id}/result` | Read the completed timetable |

For a demonstration, load a dataset, select **Generar horario**, and open **Memoria de trabajo**. Review facts, events, conflicts, and the candidate preview. Open **Evolución del modelo** for the actual recorded history. An already feasible starting timetable may finish at generation zero. Runtime measurements depend on the machine and scenario.
