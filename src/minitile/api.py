"""High-level, immutable Floorplan API (Section 9.1).

Every step returns a **new** ``Floorplan``; the original is never modified::

    fp = Floorplan.load("testcases/chain_5.yaml")
    result = fp.place(seed=42, iterations=20_000).route().report()
    result.to_json("out.json")
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from minitile.cost import CostWeights
from minitile.metrics import build_result
from minitile.model import Design, PlacementResult, Result, RouteResult
from minitile.parser import load_design
from minitile.placer import place
from minitile.router import route_all


class FloorplanStateError(RuntimeError):
    """Raised when steps are called out of order (e.g. ``route()`` before ``place()``)."""


@dataclass(frozen=True)
class Floorplan:
    design: Design
    weights: CostWeights = field(default_factory=CostWeights)
    placement: PlacementResult | None = None
    routes: tuple[RouteResult, ...] | None = None

    @classmethod
    def load(cls, path: str | Path, weights: CostWeights | None = None) -> Floorplan:
        return cls(design=load_design(path), weights=weights or CostWeights())

    def place(self, seed: int = 0, iterations: int = 20_000) -> Floorplan:
        pr = place(self.design, seed=seed, iterations=iterations, weights=self.weights)
        return replace(self, placement=pr, routes=None)

    def route(self) -> Floorplan:
        if self.placement is None:
            raise FloorplanStateError("route() called before place(): place the design first")
        routes = route_all(self.design, self.placement.placement)
        return replace(self, routes=tuple(routes))

    def report(self) -> Result:
        if self.placement is None:
            raise FloorplanStateError("report() called before place()")
        if self.routes is None:
            raise FloorplanStateError("report() called before route()")
        return build_result(self.design, self.placement, list(self.routes), self.weights)
