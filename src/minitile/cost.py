"""Placement cost function (Section 6.1): full cost and incremental delta.

    cost = Σ_nets  w_net · manhattan(from, to)
         + λ_overlap · Σ_pairs overlap_area(a, b)
         + λ_halo    · Σ_pairs halo_violation(a, b)
         + λ_pipe    · Σ_nets  stages_est(net)

Duplicate nets (same unordered pair) are merged and their widths summed.
``halo_violation`` of an unordered pair is ``hv(a, b) + hv(b, a)`` (symmetric).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from minitile.geometry import Rect, halo_violation_pair, manhattan, overlap_area
from minitile.model import Design, Placement, Position


@dataclass(frozen=True, slots=True)
class CostWeights:
    lambda_overlap: float = 1000.0
    lambda_halo: float = 200.0
    lambda_pipe: float = 50.0


def stages_for(length: int, reach_per_cycle: int) -> int:
    """Pipeline stages needed for a wire of ``length``: max(0, ceil(length / reach) - 1)."""
    return max(0, -(-length // reach_per_cycle) - 1)


class CostModel:
    """Precomputed, index-based view of a design for fast cost evaluation."""

    def __init__(self, design: Design, weights: CostWeights | None = None) -> None:
        self.design = design
        self.weights = weights or CostWeights()
        self.names = [m.name for m in design.modules]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.sizes = [(m.w, m.h) for m in design.modules]
        self.halo = design.die.halo
        self.reach = design.reach_per_cycle

        merged: dict[tuple[int, int], int] = {}
        for net in design.nets:
            a, b = self.index[net.src], self.index[net.dst]
            key = (min(a, b), max(a, b))
            merged[key] = merged.get(key, 0) + net.width
        # (a, b, weight) with weight = summed width / 64
        self.nets: list[tuple[int, int, float]] = [
            (a, b, w / 64) for (a, b), w in sorted(merged.items())
        ]
        self.nets_of: list[list[int]] = [[] for _ in self.names]
        for k, (a, b, _) in enumerate(self.nets):
            self.nets_of[a].append(k)
            self.nets_of[b].append(k)
        self.connected_weight = [0.0] * len(self.names)
        for a, b, w in self.nets:
            self.connected_weight[a] += w
            self.connected_weight[b] += w

    # ------------------------------------------------------------ helpers
    def rect(self, i: int, pos: Position) -> Rect:
        w, h = self.sizes[i]
        return Rect(pos[0], pos[1], w, h)

    def positions(self, placement: Mapping[str, Position]) -> list[Position]:
        return [(placement[n][0], placement[n][1]) for n in self.names]

    def net_cost(self, ra: Rect, rb: Rect, weight: float) -> float:
        d = manhattan(ra, rb)
        return weight * d + self.weights.lambda_pipe * stages_for(d, self.reach)

    def pair_cost(self, ra: Rect, rb: Rect) -> float:
        ov = overlap_area(ra, rb)
        hv = halo_violation_pair(ra, rb, self.halo)
        return self.weights.lambda_overlap * ov + self.weights.lambda_halo * hv

    # ------------------------------------------------------------ full
    def full(self, pos: list[Position]) -> float:
        rects = [self.rect(i, p) for i, p in enumerate(pos)]
        total = 0.0
        for a, b, w in self.nets:
            total += self.net_cost(rects[a], rects[b], w)
        n = len(rects)
        for i in range(n):
            for j in range(i + 1, n):
                total += self.pair_cost(rects[i], rects[j])
        return total

    # ------------------------------------------------------------ delta
    def _local(self, rects: list[Rect], moved: list[int], net_ids: list[int]) -> float:
        total = 0.0
        for k in net_ids:
            a, b, w = self.nets[k]
            total += self.net_cost(rects[a], rects[b], w)
        moved_set = set(moved)
        for i in moved:
            ri = rects[i]
            for j, rj in enumerate(rects):
                if j == i or (j in moved_set and j < i):
                    continue  # skip self, and count each moved-moved pair once
                total += self.pair_cost(ri, rj)
        return total

    def delta(self, pos: list[Position], moves: Mapping[int, Position]) -> float:
        """Cost change if module ``i`` moved to ``moves[i]``; only affected terms recomputed."""
        moved = sorted(moves)
        net_ids = sorted({k for i in moved for k in self.nets_of[i]})
        before = [self.rect(i, p) for i, p in enumerate(pos)]
        after = list(before)
        for i, p in moves.items():
            after[i] = self.rect(i, p)
        return self._local(after, moved, net_ids) - self._local(before, moved, net_ids)

    # ------------------------------------------------------------ partial (greedy)
    def partial(
        self, i: int, p: Position, placed: Mapping[int, Position], penalties: bool
    ) -> float:
        """Cost of module ``i`` at ``p`` w.r.t. already placed modules only."""
        ri = self.rect(i, p)
        total = 0.0
        for k in self.nets_of[i]:
            a, b, w = self.nets[k]
            other = b if a == i else a
            if other in placed:
                total += self.net_cost(ri, self.rect(other, placed[other]), w)
        if penalties:
            for j, pj in placed.items():
                total += self.pair_cost(ri, self.rect(j, pj))
        return total


def full_cost(design: Design, placement: Placement, weights: CostWeights | None = None) -> float:
    """Full cost of a placement."""
    model = CostModel(design, weights)
    return model.full(model.positions(placement))


def delta_cost(
    design: Design,
    placement: Placement,
    moves: Mapping[str, Position],
    weights: CostWeights | None = None,
) -> float:
    """Cost change caused by moving/swapping the modules in ``moves`` (name -> new position)."""
    model = CostModel(design, weights)
    return model.delta(model.positions(placement), {model.index[n]: p for n, p in moves.items()})
