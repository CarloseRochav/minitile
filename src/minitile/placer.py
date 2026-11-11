"""Placement: greedy initial placement, simulated annealing and legality check (Section 6)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from minitile.cost import CostModel, CostWeights
from minitile.geometry import Rect, inside_die, overlap_area, violates_halo
from minitile.model import Design, Placement, PlacementResult, Position


@dataclass(frozen=True, slots=True)
class AnnealParams:
    iterations: int = 20_000
    seed: int = 0
    p_translate: float = 0.7  # probability of a translate move; the rest are swaps
    t0_samples: int = 200
    final_temp_ratio: float = 1e-4


# ---------------------------------------------------------------- greedy


def _legal_against(model: CostModel, i: int, p: Position, placed: dict[int, Position]) -> bool:
    ri = model.rect(i, p)
    halo = model.halo
    for j, pj in placed.items():
        rj = model.rect(j, pj)
        if overlap_area(ri, rj) > 0 or violates_halo(ri, rj, halo):
            return False
    return True


def greedy_placement(model: CostModel) -> list[Position]:
    """Section 6.2: fixed modules first, then movable ones by connectivity, area, name."""
    design = model.design
    W, H = design.die.width, design.die.height
    placed: dict[int, Position] = {}
    for i, m in enumerate(design.modules):
        if m.fixed is not None:
            placed[i] = m.fixed

    movable = [i for i, m in enumerate(design.modules) if m.fixed is None]
    movable.sort(
        key=lambda i: (
            -model.connected_weight[i],
            -(model.sizes[i][0] * model.sizes[i][1]),
            model.names[i],
        )
    )
    for i in movable:
        w, h = model.sizes[i]
        stride = max(1, min(w, h) // 2)
        candidates = [
            (x, y) for y in range(0, H - h + 1, stride) for x in range(0, W - w + 1, stride)
        ]
        best: Position | None = None
        best_cost = math.inf
        for p in candidates:
            if not _legal_against(model, i, p, placed):
                continue
            c = model.partial(i, p, placed, penalties=False)
            if c < best_cost:
                best, best_cost = p, c
        if best is None:  # no legal spot: minimise cost including overlap/halo penalties
            for p in candidates:
                c = model.partial(i, p, placed, penalties=True)
                if c < best_cost:
                    best, best_cost = p, c
        assert best is not None
        placed[i] = best
    return [placed[i] for i in range(len(design.modules))]


# ---------------------------------------------------------------- annealing


def _clamp(p: Position, size: tuple[int, int], W: int, H: int) -> Position:
    return (min(max(p[0], 0), W - size[0]), min(max(p[1], 0), H - size[1]))


def _propose(
    model: CostModel,
    rng: random.Random,
    pos: list[Position],
    movable: list[int],
    radius: int,
    p_translate: float,
) -> dict[int, Position]:
    W, H = model.design.die.width, model.design.die.height
    if len(movable) >= 2 and rng.random() >= p_translate:
        i, j = rng.sample(movable, 2)
        return {
            i: _clamp(pos[j], model.sizes[i], W, H),
            j: _clamp(pos[i], model.sizes[j], W, H),
        }
    i = rng.choice(movable)
    dx = rng.randint(-radius, radius)
    dy = rng.randint(-radius, radius)
    return {i: _clamp((pos[i][0] + dx, pos[i][1] + dy), model.sizes[i], W, H)}


def anneal(
    model: CostModel, start: list[Position], params: AnnealParams
) -> tuple[list[Position], float]:
    """Section 6.3. Returns the best placement seen and its (full) cost."""
    design = model.design
    start_cost = model.full(start)
    movable = [i for i, m in enumerate(design.modules) if m.fixed is None]
    n_iter = params.iterations
    if not movable or n_iter <= 0:
        return list(start), start_cost

    rng = random.Random(params.seed)
    r0 = max(1, max(design.die.width, design.die.height) // 2)

    def rects_of(pos: list[Position]) -> list[Rect]:
        return [model.rect(i, p) for i, p in enumerate(pos)]

    # initial temperature from sampled moves around the greedy placement
    start_rects = rects_of(start)
    positive: list[float] = []
    for _ in range(params.t0_samples):
        moves = _propose(model, rng, start, movable, r0, params.p_translate)
        d = model.delta_rects(start_rects, {i: model.rect(i, p) for i, p in moves.items()})
        if d > 0:
            positive.append(d)
    t0 = -(sum(positive) / len(positive)) / math.log(0.8) if positive else 1.0
    alpha = params.final_temp_ratio ** (1 / (n_iter - 1)) if n_iter > 1 else 1.0

    pos = list(start)
    rects = list(start_rects)
    cur = start_cost
    best, best_cost = list(pos), cur
    span = max(1, n_iter - 1)
    for k in range(n_iter):
        temp = t0 * alpha**k
        radius = max(1, r0 - ((r0 - 1) * k) // span)
        moves = _propose(model, rng, pos, movable, radius, params.p_translate)
        new_rects = {i: model.rect(i, p) for i, p in moves.items()}
        d = model.delta_rects(rects, new_rects)
        if d <= 0 or rng.random() < math.exp(-d / temp):
            for i, p in moves.items():
                pos[i] = p
                rects[i] = new_rects[i]
            cur += d
            if cur < best_cost - 1e-9:
                best, best_cost = list(pos), cur

    final_cost = model.full(best)  # recompute exactly; avoids accumulated float drift
    if final_cost > start_cost:
        return list(start), start_cost
    return best, final_cost


# ---------------------------------------------------------------- legality


def check_legality(design: Design, placement: Placement) -> list[str]:
    """Section 6.4: inside die, no overlap, no halo violation. Returns violation messages."""
    W, H, halo = design.die.width, design.die.height, design.die.halo
    rects = [(m.name, m.rect_at(placement[m.name])) for m in design.modules]
    out: list[str] = []
    for name, r in rects:
        if not inside_die(r, W, H):
            out.append(f"{name} outside die")
    for i, (na, ra) in enumerate(rects):
        for nb, rb in rects[i + 1 :]:
            ov = overlap_area(ra, rb)
            if ov > 0:
                out.append(f"{na} overlaps {nb} (area {ov})")
            elif violates_halo(ra, rb, halo):
                out.append(f"{na} violates halo {halo} with {nb}")
    return out


# ---------------------------------------------------------------- entry point


def place(
    design: Design,
    seed: int = 0,
    iterations: int = 20_000,
    weights: CostWeights | None = None,
    p_translate: float = 0.7,
) -> PlacementResult:
    """Greedy + simulated annealing + legality check."""
    model = CostModel(design, weights)
    start = greedy_placement(model)
    cost_initial = model.full(start)
    params = AnnealParams(iterations=iterations, seed=seed, p_translate=p_translate)
    best, cost_final = anneal(model, start, params)
    placement = {n: best[i] for i, n in enumerate(model.names)}
    violations = check_legality(design, placement)
    return PlacementResult(
        placement=placement,
        legal=not violations,
        violations=violations,
        cost_initial=cost_initial,
        cost_final=cost_final,
        seed=seed,
        iterations=iterations,
    )
