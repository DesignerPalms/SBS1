from __future__ import annotations

import random
from collections import defaultdict
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
        g.add_edge(a, b, is_main=bool(e.get("is_main", False)))
    return g


def _weighted_entrance_choice(rng: random.Random, entrances: list[dict[str, Any]]) -> int:
    weights = [max(0.001, float(e.get("weight", 1.0))) for e in entrances]
    return rng.choices([e["node_id"] for e in entrances], weights=weights, k=1)[0]


def _pick_personality(rng: random.Random, cfg: dict[str, Any]) -> str:
    choices = ["wanderer", "mission", "explorer", "main"]
    w = [cfg["pct_wanderer"], cfg["pct_mission"], cfg["pct_explorer"], cfg["pct_main"]]
    return rng.choices(choices, weights=w, k=1)[0]


def _normalize_mix(cfg: dict[str, Any]) -> None:
    keys = ["pct_wanderer", "pct_mission", "pct_explorer", "pct_main"]
    vals = [max(0.0, float(cfg.get(k, 0.0))) for k in keys]
    s = sum(vals)
    if s <= 0:
        vals = [0.25, 0.25, 0.25, 0.25]
        s = 1
    for k, v in zip(keys, vals):
        cfg[k] = v / s


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _choose_next_neighbor(
    rng: random.Random,
    g: nx.Graph,
    current: int,
    prev: int | None,
    edge_flow: dict[tuple[int, int], float],
    cfg: dict[str, Any],
    personality: str,
    goal_node: int | None,
) -> int | None:
    neighbors = list(g.neighbors(current))
    if not neighbors:
        return None

    scores: list[float] = []
    for nb in neighbors:
        score = 1.0
        if prev is not None and nb == prev:
            score *= max(0.01, 1.0 - float(cfg["turnback_rate"]))

        e = g.edges[current, nb]
        if personality == "main" and e.get("is_main"):
            score *= float(cfg["main_loyal_multiplier"])

        flow = edge_flow[_edge_key(current, nb)]
        score *= 1.0 / (1.0 + float(cfg["congestion_alpha"]) * flow)

        if goal_node is not None:
            try:
                d_cur = nx.shortest_path_length(g, current, goal_node)
                d_nb = nx.shortest_path_length(g, nb, goal_node)
                if d_nb < d_cur:
                    score *= float(cfg["goal_bias"])
            except nx.NetworkXNoPath:
                pass

        scores.append(max(0.001, score))
    return rng.choices(neighbors, weights=scores, k=1)[0]




def _sample_wander_steps(rng: random.Random, avg_minutes: float, steps_per_min: int, deviation_minutes: float) -> int:
    dev = max(0.0, float(deviation_minutes))
    if dev <= 0.0:
        minutes = max(1.0, float(avg_minutes))
    else:
        # bell-curve variation: +/-dev bounds, with extremes unlikely
        sigma = max(0.1, dev / 3.0)
        delta = rng.gauss(0.0, sigma)
        delta = max(-dev, min(dev, delta))
        minutes = max(1.0, float(avg_minutes) + delta)
    return max(1, int(round(minutes * steps_per_min)))


def _closest_entrance(g: nx.Graph, current: int, entrances: list[dict[str, Any]]) -> int:
    entrance_nodes = [e["node_id"] for e in entrances]
    best = entrance_nodes[0]
    best_dist = float("inf")
    for n in entrance_nodes:
        try:
            d = nx.shortest_path_length(g, current, n)
            if d < best_dist:
                best_dist = d
                best = n
        except nx.NetworkXNoPath:
            continue
    return best

def _mission_target(rng: random.Random, attractors: list[dict[str, Any]], booths: list[dict[str, Any]]) -> int | None:
    if attractors:
        weights = [max(0.01, float(a.get("strength", 1.0))) for a in attractors]
        return rng.choices([a["node_id"] for a in attractors], weights=weights, k=1)[0]
    if booths:
        return rng.choice([b["node_id"] for b in booths])
    return None


def _apply_path(
    person_scale: int,
    path: list[int],
    node_visits: dict[int, float],
    edge_visits: dict[tuple[int, int], float],
    booth_nodes: set[int],
    booth_person_counts: dict[int, int],
) -> None:
    for n in path:
        node_visits[n] += person_scale
        if n in booth_nodes:
            seen = booth_person_counts[n]
            booth_person_counts[n] += 1
            booth_person_counts[n] += 0  # explicit, no-op for readability
    for a, b in zip(path, path[1:]):
        edge_visits[_edge_key(a, b)] += person_scale


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

    booth_nodes = {b["node_id"]: b.get("label", f"booth-{b['node_id']}") for b in booths}
    booth_scores_per_sim: dict[int, list[float]] = defaultdict(list)
    node_sums: dict[int, float] = defaultdict(float)
    edge_sums: dict[tuple[int, int], float] = defaultdict(float)

    for s in range(sims):
        rng = random.Random(int(cfg["seed"]) + s)
        node_visits: dict[int, float] = defaultdict(float)
        edge_visits: dict[tuple[int, int], float] = defaultdict(float)
        booth_score: dict[int, float] = defaultdict(float)

        people_done = 0
        while people_done < concurrent_people:
            group = 2 if rng.random() < min(1.0, max(0.0, float(cfg["couples_rate"]))) else 1
            people_done += group

            start = _weighted_entrance_choice(rng, entrances)
            personality = _pick_personality(rng, cfg)
            goal_node: int | None = None
            if personality == "mission":
                goal_node = _mission_target(rng, attractors, booths)

            path = [start]
            prev = None
            cur = start
            attractor_cooldown = 0
            booth_hits_for_person: dict[int, int] = defaultdict(int)

            if personality == "mission" and goal_node in g:
                try:
                    mission_path = nx.shortest_path(g, cur, goal_node)
                    for n in mission_path[1:]:
                        path.append(n)
                    cur = path[-1]
                    prev = path[-2] if len(path) > 1 else None
                except nx.NetworkXNoPath:
                    pass

            wander_steps = _sample_wander_steps(
                rng,
                segment.avg_minutes_on_floor,
                steps_per_min,
                float(cfg.get("minutes_deviation", 30.0)),
            )

            for _ in range(wander_steps):
                # dwell behavior
                hit_attractor = next((a for a in attractors if a["node_id"] == cur), None)
                if hit_attractor and attractor_cooldown <= 0:
                    dwell = max(1, int(hit_attractor.get("dwell_steps", 1)))
                    if len(path) > 1:
                        approach = _edge_key(path[-2], path[-1])
                    else:
                        approach = None
                    for _d in range(dwell):
                        path.append(cur)
                        if approach:
                            edge_visits[approach] += group
                    attractor_cooldown = int(cfg["attractor_cooldown_steps"])

                if attractor_cooldown > 0:
                    attractor_cooldown -= 1

                next_node = _choose_next_neighbor(rng, g, cur, prev, edge_visits, cfg, personality, goal_node)
                if next_node is None:
                    break
                prev, cur = cur, next_node
                path.append(cur)

            exit_target = _closest_entrance(g, cur, entrances)
            try:
                exit_path = nx.shortest_path(g, cur, exit_target)
                path.extend(exit_path[1:])
            except nx.NetworkXNoPath:
                pass

            # scoring and flow
            for n in path:
                node_visits[n] += group
                if n in booth_nodes:
                    seen = booth_hits_for_person[n]
                    booth_score[n] += (0.5**seen) * group
                    booth_hits_for_person[n] += 1
            for a, b in zip(path, path[1:]):
                edge_visits[_edge_key(a, b)] += group

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

    return {
        "booth_summary": booth_summary,
        "node_visit_mean": node_mean,
        "edge_visit_mean": edge_mean,
        "concurrent_people": concurrent_people,
    }
