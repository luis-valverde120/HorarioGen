import random
import time
from collections import defaultdict
from dataclasses import dataclass

from .domain import Gene, Slot, occupies_group, session_payload
from .evaluation import contained, evaluate
from .feasibility import planning_windows
from .working_memory import OptimizationCancelled


@dataclass(frozen=True)
class Config:
    population: int = 40
    generations: int = 100
    seconds: float = 10
    mutation: float = 0.35
    tournament: int = 3
    elite: int = 2
    seed: int = 42


def tournament(population, size, rng):
    return min(rng.sample(population, size), key=lambda candidate: candidate[0])[1]


def crossover(first, second, rng):
    return tuple(a if rng.getrandbits(1) else b for a, b in zip(first, second, strict=True))


def reassign(genes, index, slots, rooms, rng):
    gene = genes[index]
    if rng.getrandbits(1):
        genes[index] = Gene(rng.choice(slots[gene.slot.duration]), gene.room)
    else:
        genes[index] = Gene(gene.slot, rng.choice(rooms))


def exchange(genes, index, peers, rng):
    other = rng.choice(peers[genes[index].slot.duration])
    genes[index], genes[other] = genes[other], genes[index]


def repair_conflicts(sessions, initial, slots, rooms, rules, rng, deadline, memory=None):
    """Move conflict participants through feasible windows, including plateau moves."""
    genes = tuple(initial)
    best = evaluate(sessions, genes, rules).score, genes
    tabu = []
    by_id = {s.id: i for i, s in enumerate(sessions)}
    for _ in range(180):
        if memory and memory.cancelled.is_set():
            raise OptimizationCancelled
        if time.monotonic() >= deadline or best[0][0] == 0:
            break
        current = evaluate(sessions, genes, rules, details=True)
        targets = list({by_id[sid] for conflict in current.conflicts for sid in conflict['sessions']
                        if sid in by_id and not rules.fixed(sessions[by_id[sid]])})
        if not targets:
            break
        index = rng.choice(targets)
        session = sessions[index]
        windows = rules.availability.get(session.teacher)
        candidate_rooms = [rules.group_rooms[session.group_key]] if session.group_key in rules.group_rooms else rooms
        choices = []
        for slot in slots[session.original.slot.duration]:
            if not rules.group_allows(session, slot): continue
            if session.id in rules.session_days and slot.day not in rules.session_days[session.id]: continue
            if windows is not None and not contained(slot, windows): continue
            for room in candidate_rooms:
                candidate = Gene(slot, room)
                if candidate == genes[index] or (index, candidate) in tabu: continue
                moved = list(genes); moved[index] = candidate; moved = tuple(moved)
                choices.append((evaluate(sessions, moved, rules).score, moved))
            if time.monotonic() >= deadline: break
        if not choices: continue
        rng.shuffle(choices)
        chosen = min(choices, key=lambda item: item[0])
        if chosen[0][0] > current.score[0] + 1: continue
        tabu.append((index, genes[index])); tabu = tabu[-40:]
        genes = chosen[1]
        if memory:
            memory.repair(session.id, current.score, chosen[0])
        if chosen[0] < best[0]: best = chosen
    return best


def greedy_seed(sessions, slots, rooms, rules, deadline, placements=None):
    """Keep existing assignments when possible and relocate conflicting sessions."""
    teachers, groups, occupancy = defaultdict(list), defaultdict(list), defaultdict(list)
    genes = []

    def overlaps(slot, assignments):
        return sum(other.start < slot.end and slot.start < other.end for other in assignments)

    def priority(item):
        return (not rules.fixed(item), len(placements.get(item.id, ())) if placements is not None else
                int(not rules.group_allows(item, item.original.slot)), -item.original.slot.duration, item.id)

    for session in sorted(sessions, key=priority):
        if time.monotonic() >= deadline:
            return None
        original = session.original
        enrollment = rules.enrollments.get(session.id)
        availability = rules.availability.get(session.teacher)
        preference = rules.preferences.get(session.teacher)

        def slot_cost(slot):
            hard = int(not rules.campus_allows(slot))
            hard += int(session.id in rules.session_days and slot.day not in rules.session_days[session.id])
            hard += int(not rules.group_allows(session, slot))
            hard += overlaps(slot, teachers[session.teacher, slot.day])
            if occupies_group(session):
                hard += overlaps(slot, groups[session.group, slot.day])
            hard += availability is not None and not contained(slot, availability)
            soft = 3 * (slot != original.slot)
            soft += preference is not None and not contained(slot, preference)
            return hard, soft

        def room_cost(slot, room):
            capacity = rules.capacities.get(room)
            hard = overlaps(slot, occupancy[room, slot.day])
            hard += capacity is not None and enrollment is not None and enrollment > capacity
            hard += occupies_group(session) and (rules.group_rooms or {}).get(session.group_key, room) != room
            return hard, int(room != original.room)

        def candidates():
            choices = placements.get(session.id) if placements else None
            for slot in choices or slots[original.slot.duration]:
                slot_hard, slot_soft = slot_cost(slot)
                for room in [(rules.group_rooms or {})[session.group_key]] if session.group_key in (rules.group_rooms or {}) else rooms:
                    room_hard, room_soft = room_cost(slot, room)
                    yield (slot_hard + room_hard, slot_soft + room_soft), Gene(slot, room)

        if rules.fixed(session) or slot_cost(original.slot) == room_cost(original.slot, original.room) == (0, 0):
            gene = original
        else:
            _, gene = min(candidates(), key=lambda candidate: candidate[0])
        genes.append((session.id, gene))
        slot = gene.slot
        teachers[session.teacher, slot.day].append(slot)
        if occupies_group(session):
            groups[session.group, slot.day].append(slot)
        occupancy[gene.room, slot.day].append(slot)
    by_id = dict(genes)
    return tuple(by_id[session.id] for session in sessions)


def optimize(sessions, rules, config=Config(), progress=lambda point: None, *, memory=None):
    started = time.monotonic()
    deadline = started + config.seconds
    rng = random.Random(config.seed)

    def check_cancelled():
        if memory and memory.cancelled.is_set():
            raise OptimizationCancelled

    check_cancelled()
    original = tuple(s.original for s in sessions)
    rooms = rules.available_rooms or tuple(sorted({gene.room for gene in original}))
    slots, peers = {}, {}
    for index, gene in enumerate(original):
        slots.setdefault(gene.slot.duration, set()).add(gene.slot)
        if not rules.fixed(sessions[index]):
            peers.setdefault(gene.slot.duration, []).append(index)
    for duration, options in slots.items():
        if rules.campus_windows is not None:
            for window in rules.campus_windows:
                for start in range(window.start, window.end - duration + 1, 60):
                    options.add(Slot(window.day, start, start + duration))
        elif rules.enforce_hours:
            for day in range(5):
                for beginning, closing in ((420, 780), (840, 1200)):
                    for start in range(beginning, closing - duration + 1, 60):
                        options.add(Slot(day, start, start + duration))
        for windows in (*rules.availability.values(), *rules.group_windows.values()):
            for window in windows:
                for start in range(window.start, window.end - duration + 1, 60):
                    options.add(Slot(window.day, start, start + duration))
        valid = {slot for slot in options if rules.campus_allows(slot)}
        # Keep the original as fallback if no valid block fits the duration.
        slots[duration] = tuple(sorted(valid or options))
    mutable = [index for indices in peers.values() for index in indices]
    placements = None
    if rules.campus_windows is not None or rules.group_windows:
        placements = {}
        for index in mutable:
            check_cancelled()
            session = sessions[index]
            duration = session.original.slot.duration
            windows = planning_windows(session, rules)
            from_windows = {Slot(w.day, start, start + duration) for w in windows
                            for start in range(w.start, w.end - duration + 1, 60)}
            from_windows.update(slot for slot in slots[duration] if contained(slot, windows))
            placements[session.id] = tuple(sorted(from_windows))
            slots[duration] = tuple(sorted(set(slots[duration]) | from_windows))

    def rank(genes):
        genes = tuple(Gene(gene.slot, (rules.group_rooms or {}).get(session.group_key, gene.room))
                      if not rules.fixed(session) else session.original for session, gene in zip(sessions, genes, strict=True))
        return evaluate(sessions, genes, rules).score, genes

    def mutate(genes, index):
        if placements is not None:
            session = sessions[index]
            options = placements[session.id]
            if options:
                fixed_room = rules.group_rooms.get(session.group_key)
                genes[index] = Gene(rng.choice(options), fixed_room or rng.choice(rooms))
            return
        if rng.getrandbits(1):
            reassign(genes, index, slots, rooms, rng)
        else:
            exchange(genes, index, peers, rng)

    baseline = evaluate(sessions, original, rules, details=True)
    best = baseline.score, original
    history = []

    def record(generation):
        check_cancelled()
        point = {"generation": generation, "hard": best[0][0], "soft": best[0][1],
                 "elapsed": round(time.monotonic() - started, 4)}
        history.append(point)
        if memory:
            assessment = evaluate(sessions, best[1], rules, details=True, include_resources=True)
            preview = [session_payload(s, g) for s, g in zip(sessions[:20], best[1][:20])]
            memory.record(population, best, assessment, point, preview)
        progress(point)

    population = [best]
    targets = [index for index in mutable if sessions[index].id in {
        sid for conflict in baseline.conflicts for sid in conflict["sessions"]
    }]
    if not mutable:
        record(0)
        return original, baseline, baseline, history, "optimal_score" if best[0] == (0, 0) else "generations"
    if best[0][0]:
        seed = greedy_seed(sessions, slots, rooms, rules, deadline, placements)
        if seed is not None:
            candidate = rank(seed)
            population.append(candidate)
            if candidate[0] < best[0]:
                best = candidate
        if best[0][0] and time.monotonic() < deadline:
            repaired = repair_conflicts(sessions, best[1], slots, rooms, rules, rng,
                                        min(deadline, time.monotonic() + config.seconds * 0.45), memory)
            if repaired[0] < best[0]:
                best = repaired
                population.append(repaired)
    for index in range(config.population - len(population)):
        check_cancelled()
        if best[0] == (0, 0) or time.monotonic() >= deadline:
            break
        genes = list(original)
        for _ in range(1 + index % max(1, min(12, len(original)))):
            target = rng.choice(targets) if targets and rng.random() < 0.8 else rng.choice(mutable)
            mutate(genes, target)
        candidate = rank(tuple(genes))
        population.append(candidate)
        if candidate[0] < best[0]:
            best = candidate
    record(0)
    reason = "generations"
    for generation in range(1, config.generations + 1):
        if best[0] == (0, 0) or time.monotonic() >= deadline or len(population) < config.tournament:
            break
        population.sort(key=lambda candidate: candidate[0])
        next_population = population[:config.elite]
        while len(next_population) < config.population and time.monotonic() < deadline:
            check_cancelled()
            first = tournament(population, config.tournament, rng)
            second = tournament(population, config.tournament, rng)
            genes = list(crossover(first, second, rng))
            if rng.random() < config.mutation:
                target = rng.choice(targets) if targets and rng.random() < 0.7 else rng.choice(mutable)
                mutate(genes, target)
            candidate = rank(tuple(genes))
            next_population.append(candidate)
            if candidate[0] < best[0]:
                best = candidate
            if best[0] == (0, 0):
                break
        population = next_population
        record(generation)
    if best[0] == (0, 0):
        reason = "optimal_score"
    elif time.monotonic() >= deadline:
        reason = "time"
    return best[1], baseline, evaluate(sessions, best[1], rules, details=True), history, reason

