from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np


@dataclass
class SegmentConfig:
    attendance: int
    hours: float
    avg_minutes_on_floor: float


def _build_graph(layout: dict[str, Any]) -> nx.Graph:
    g = nx.Graph()
    for n in layout.get("nodes", []):
        g.add_node(n["id"], x=n["x"], y=n["y"])
    for e in layout.get("edges", []):
        a, b = e["source"], e["target"]
        n1 = next((n for n in layout.get("nodes", []) if n["id"] == a), None)
        n2 = next((n for n in layout.get("nodes", []) if n["id"] == b), None)
        length = 1.0
        if n1 and n2:
            length = max(1.0, math.hypot(float(n2["x"]) - float(n1["x"]), float(n2["y"]) - float(n1["y"])))
        g.add_edge(a, b, is_main=bool(e.get("is_main", False)), length=length)
    return g


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _weighted_entrance_choice(rng: random.Random, entrances: list[dict[str, Any]]) -> int:
    weights = [max(0.001, float(e.get("weight", 1.0))) for e in entrances]
    return rng.choices([e["node_id"] for e in entrances], weights=weights, k=1)[0]


def _closest_entrance(g: nx.Graph, current: int, entrances: list[dict[str, Any]]) -> int:
    entrance_nodes = [e["node_id"] for e in entrances]
    best = entrance_nodes[0]
    best_dist = float("inf")
    for n in entrance_nodes:
        try:
            d = nx.shortest_path_length(g, current, n, weight="length")
            if d < best_dist:
                best_dist = d
                best = n
        except nx.NetworkXNoPath:
            continue
    return best


def _normalize_mix(cfg: dict[str, Any]) -> None:
    keys = ["pct_wanderer", "pct_mission", "pct_explorer", "pct_main"]
    vals = [max(0.0, float(cfg.get(k, 0.0))) for k in keys]
    s = sum(vals)
    if s <= 0:
        vals = [0.25, 0.25, 0.25, 0.25]
        s = 1.0
    for k, v in zip(keys, vals):
        cfg[k] = v / s


def _normalize_group_mix(cfg: dict[str, Any]) -> list[float]:
    probs = [
        max(0.0, float(cfg.get("group_prob_solo", 0.7))),
        max(0.0, float(cfg.get("group_prob_couple", 0.2))),
        max(0.0, float(cfg.get("group_prob_triple", 0.08))),
        max(0.0, float(cfg.get("group_prob_quad", 0.02))),
    ]
    s = sum(probs)
    if s <= 0:
        probs = [1.0, 0.0, 0.0, 0.0]
        s = 1.0
    return [p / s for p in probs]


def _pick_group_size(rng: random.Random, cfg: dict[str, Any]) -> int:
    probs = _normalize_group_mix(cfg)
    return rng.choices([1, 2, 3, 4], weights=probs, k=1)[0]


def _pick_personality(rng: random.Random, cfg: dict[str, Any]) -> str:
    choices = ["wanderer", "mission", "explorer", "main"]
    w = [cfg["pct_wanderer"], cfg["pct_mission"], cfg["pct_explorer"], cfg["pct_main"]]
    return rng.choices(choices, weights=w, k=1)[0]


def _mission_target(rng: random.Random, attractors: list[dict[str, Any]], booths: list[dict[str, Any]]) -> int | None:
    if attractors:
        weights = [max(0.01, float(a.get("strength", 1.0))) for a in attractors]
        return rng.choices([a["node_id"] for a in attractors], weights=weights, k=1)[0]
    if booths:
        return rng.choice([b["node_id"] for b in booths])
    return None


def _sample_wander_minutes(rng: random.Random, avg_minutes: float, deviation_minutes: float) -> float:
    dev = max(0.0, float(deviation_minutes))
    if dev <= 0:
        return max(1.0, avg_minutes)
    sigma = max(0.1, dev / 3.0)
    delta = max(-dev, min(dev, rng.gauss(0.0, sigma)))
    return max(1.0, avg_minutes + delta)


def _sample_walk_speed(rng: random.Random, cfg: dict[str, Any]) -> float:
    # User calibrates image scale via pixels_per_10m; walking speed in m/min is modeled internally.
    px_per_10m = max(1.0, float(cfg.get("pixels_per_10m", 150.0)))
    px_per_m = px_per_10m / 10.0

    human_mean_m_per_min = max(20.0, float(cfg.get("human_walk_mean_m_per_min", 80.0)))
    human_std_m_per_min = max(1.0, float(cfg.get("human_walk_std_m_per_min", 12.0)))
    sampled_m_per_min = max(20.0, rng.gauss(human_mean_m_per_min, human_std_m_per_min))

    return sampled_m_per_min * px_per_m


def _arrival_weights(total_steps: int, cfg: dict[str, Any]) -> list[float]:
    weights = []
    wave_strength = max(0.0, float(cfg.get("arrival_wave_strength", 0.15)))
    wave_freq = max(0.1, float(cfg.get("arrival_wave_frequency", 2.0)))

    event_start = int(max(0, float(cfg.get("event_start_min", 120.0))))
    event_dur = int(max(0, float(cfg.get("event_duration_min", 30.0))))
    event_mult = max(1.0, float(cfg.get("event_multiplier", 1.2)))

    for step in range(total_steps):
        t = step / max(1, total_steps - 1)
        wave = 1.0 + wave_strength * math.sin(2.0 * math.pi * wave_freq * t)
        mult = wave
        if event_start <= step <= (event_start + event_dur):
            mult *= event_mult
        weights.append(max(0.01, mult))
    return weights


def _choose_next_neighbor(
    rng: random.Random,
    g: nx.Graph,
    current: int,
    prev: int | None,
    edge_flow: dict[tuple[int, int], float],
    cfg: dict[str, Any],
    personality: str,
    goal_node: int | None,
    recent_edges: deque[tuple[int, int]],
    seen_nodes: dict[int, int],
) -> int | None:
    neighbors = list(g.neighbors(current))
    if not neighbors:
        return None

    scores: list[float] = []
    repeat_penalty = max(0.01, float(cfg.get("repeat_edge_penalty", 0.75)))
    novelty_bonus_initial = max(0.0, float(cfg.get("novelty_bonus_initial", 0.4)))
    novelty_decay = max(0.0, float(cfg.get("novelty_decay_rate", 0.35)))

    for nb in neighbors:
        score = 1.0
        if prev is not None and nb == prev:
            score *= max(0.01, 1.0 - float(cfg["turnback_rate"]))

        edge = g.edges[current, nb]
        if personality == "main" and edge.get("is_main"):
            score *= float(cfg["main_loyal_multiplier"])

        flow = edge_flow[_edge_key(current, nb)]
        score *= 1.0 / (1.0 + float(cfg["congestion_alpha"]) * flow)

        ek = _edge_key(current, nb)
        if ek in recent_edges:
            score *= repeat_penalty

        visits = seen_nodes.get(nb, 0)
        score *= 1.0 + (novelty_bonus_initial * math.exp(-novelty_decay * visits))

        if goal_node is not None:
            try:
                d_cur = nx.shortest_path_length(g, current, goal_node, weight="length")
                d_nb = nx.shortest_path_length(g, nb, goal_node, weight="length")
                if d_nb < d_cur:
                    score *= float(cfg["goal_bias"])
            except nx.NetworkXNoPath:
                pass

        scores.append(max(0.001, score))
    return rng.choices(neighbors, weights=scores, k=1)[0]


def _service_node(
    node_id: int,
    now_step: int,
    service_state: dict[int, list[int]],
    capacity: int,
    service_time_steps: int,
    max_wait: int,
) -> tuple[int, int]:
    slots = service_state.setdefault(node_id, [])
    slots[:] = [t for t in slots if t > now_step]

    if len(slots) < capacity:
        end_step = now_step + service_time_steps
        slots.append(end_step)
        return now_step, 0

    soonest = min(slots)
    wait = max(0, soonest - now_step)
    if wait > max_wait:
        return now_step, wait

    slots.remove(soonest)
    start = soonest
    slots.append(start + service_time_steps)
    return start, wait


def run_simulation(
    layout: dict[str, Any],
    cfg: dict[str, Any],
    segment: SegmentConfig,
    progress_cb=None,
    progress_offset: float = 0.0,
    progress_span: float = 1.0,
) -> dict[str, Any]:
    g = _build_graph(layout)
    entrances = layout.get("entrances", [])
    booths = layout.get("booths", [])
    attractors = layout.get("attractors", [])
    if g.number_of_nodes() == 0 or not entrances:
        return {"booth_summary": {}, "node_visit_mean": {}, "edge_visit_mean": {}, "concurrent_people": 0}

    _normalize_mix(cfg)
    sims = int(cfg["sims"])
    steps_per_min = int(cfg["steps_per_minute"])
    seg_hours = max(0.01, float(segment.hours))
    arrivals_per_hour = segment.attendance / seg_hours
    avg_hours_on_floor = max(0.01, segment.avg_minutes_on_floor / 60.0)
    concurrent_people = max(1, round(arrivals_per_hour * avg_hours_on_floor))

    total_steps = max(60, int(seg_hours * 60.0 * steps_per_min))
    booth_nodes = {b["node_id"]: b.get("label", f"booth-{b['node_id']}") for b in booths}
    attractor_map = {a["node_id"]: a for a in attractors}

    booth_scores_per_sim: dict[int, list[float]] = defaultdict(list)
    node_sums: dict[int, float] = defaultdict(float)
    edge_sums: dict[tuple[int, int], float] = defaultdict(float)

    queue_wait_totals: dict[int, float] = defaultdict(float)
    queue_wait_counts: dict[int, int] = defaultdict(int)

    for s in range(sims):
        rng = random.Random(int(cfg["seed"]) + s)
        node_visits: dict[int, float] = defaultdict(float)
        edge_visits: dict[tuple[int, int], float] = defaultdict(float)
        booth_score: dict[int, float] = defaultdict(float)

        service_state: dict[int, list[int]] = {}
        arrival_w = _arrival_weights(total_steps, cfg)

        people_done = 0
        groups: list[tuple[int, int]] = []
        while people_done < concurrent_people:
            gsize = _pick_group_size(rng, cfg)
            people_done += gsize
            spawn_step = rng.choices(range(total_steps), weights=arrival_w, k=1)[0]
            groups.append((spawn_step, gsize))
        groups.sort(key=lambda x: x[0])

        for spawn_step, group in groups:
            start = _weighted_entrance_choice(rng, entrances)
            personality = _pick_personality(rng, cfg)
            goal_node: int | None = _mission_target(rng, attractors, booths) if personality == "mission" else None

            wander_minutes = _sample_wander_minutes(rng, segment.avg_minutes_on_floor, float(cfg.get("minutes_deviation", 30.0)))
            walk_speed = _sample_walk_speed(rng, cfg)
            distance_budget = wander_minutes * walk_speed
            if personality in ("mission", "main"):
                distance_budget *= max(0.5, float(cfg.get("group_cohesion", 0.9)))

            path = [start]
            prev = None
            cur = start
            traveled = 0.0
            now = spawn_step
            booth_hits_for_person: dict[int, int] = defaultdict(int)
            recent_edges: deque[tuple[int, int]] = deque(maxlen=max(1, int(cfg.get("memory_window_steps", 8))))
            seen_nodes: dict[int, int] = defaultdict(int)
            seen_nodes[cur] += 1

            if personality == "mission" and goal_node in g:
                try:
                    mission_path = nx.shortest_path(g, cur, goal_node, weight="length")
                    for n in mission_path[1:]:
                        e_len = float(g.edges[cur, n].get("length", 1.0))
                        traveled += e_len
                        now += 1
                        edge_visits[_edge_key(cur, n)] += group
                        recent_edges.append(_edge_key(cur, n))
                        cur = n
                        path.append(cur)
                        seen_nodes[cur] += 1
                    prev = path[-2] if len(path) > 1 else None
                except nx.NetworkXNoPath:
                    pass

            while traveled < distance_budget:
                # queue/service at booth/attractor nodes
                if cur in attractor_map:
                    attr = attractor_map[cur]
                    cap = max(1, int(attr.get("capacity", 2)))
                    svc = max(1, int(attr.get("dwell_steps", 3)))
                    max_wait = max(0, int(attr.get("max_wait_steps", 20)))
                    service_start, wait = _service_node(cur, now, service_state, cap, svc, max_wait)
                    if wait > 0:
                        queue_wait_totals[cur] += wait * group
                        queue_wait_counts[cur] += group
                        for _ in range(wait):
                            path.append(cur)
                            node_visits[cur] += group
                        now = service_start
                    for _ in range(svc):
                        path.append(cur)
                        node_visits[cur] += group
                        now += 1
                        if len(path) > 2:
                            approach = _edge_key(path[-3], path[-2])
                            edge_visits[approach] += group

                if cur in booth_nodes:
                    cap = max(1, int(cfg.get("booth_capacity", 2)))
                    svc = max(1, int(cfg.get("booth_service_steps", 1)))
                    max_wait = max(0, int(cfg.get("booth_max_queue_wait_steps", 20)))
                    service_start, wait = _service_node(cur, now, service_state, cap, svc, max_wait)
                    if wait > 0:
                        queue_wait_totals[cur] += wait * group
                        queue_wait_counts[cur] += group
                        now = service_start

                nxt = _choose_next_neighbor(rng, g, cur, prev, edge_visits, cfg, personality, goal_node, recent_edges, seen_nodes)
                if nxt is None:
                    break
                edge_len = float(g.edges[cur, nxt].get("length", 1.0))
                if traveled + edge_len > distance_budget:
                    break
                traveled += edge_len
                now += 1
                prev, cur = cur, nxt
                path.append(cur)
                ek = _edge_key(path[-2], path[-1])
                edge_visits[ek] += group
                recent_edges.append(ek)
                seen_nodes[cur] += 1

            # after budget, exit directly to nearest entrance
            exit_target = _closest_entrance(g, cur, entrances)
            try:
                exit_path = nx.shortest_path(g, cur, exit_target, weight="length")
                for n in exit_path[1:]:
                    now += 1
                    edge_visits[_edge_key(cur, n)] += group
                    cur = n
                    path.append(cur)
            except nx.NetworkXNoPath:
                pass

            for n in path:
                node_visits[n] += group
                if n in booth_nodes:
                    seen = booth_hits_for_person[n]
                    booth_score[n] += (0.5**seen) * group
                    booth_hits_for_person[n] += 1

        for n, v in node_visits.items():
            node_sums[n] += v
        for e, v in edge_visits.items():
            edge_sums[e] += v
        for booth_id in booth_nodes.keys():
            booth_scores_per_sim[booth_id].append(booth_score.get(booth_id, 0.0))

        if progress_cb:
            pct = progress_offset + progress_span * ((s + 1) / sims)
            progress_cb(min(1.0, pct), f"Simulation {s + 1}/{sims}")

    booth_summary = {}
    for booth_id, label in booth_nodes.items():
        arr = np.array(booth_scores_per_sim.get(booth_id, [0.0]), dtype=float)
        booth_summary[str(booth_id)] = {
            "label": label,
            "mean_score": float(arr.mean()),
            "std_score": float(arr.std(ddof=0)),
        }

    node_mean = {str(k): v / sims for k, v in node_sums.items()}
    edge_mean = {f"{a}-{b}": v / sims for (a, b), v in edge_sums.items()}
    queue_wait_mean = {str(k): (queue_wait_totals[k] / max(1, queue_wait_counts[k])) / sims for k in queue_wait_totals.keys()}

    return {
        "booth_summary": booth_summary,
        "node_visit_mean": node_mean,
        "edge_visit_mean": edge_mean,
        "queue_wait_mean": queue_wait_mean,
        "concurrent_people": concurrent_people,
    }
