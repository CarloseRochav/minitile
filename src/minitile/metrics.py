"""Per-net and summary metrics (Section 8)."""

from __future__ import annotations

from minitile.cost import CostWeights, stages_for
from minitile.geometry import manhattan
from minitile.model import (
    Design,
    NetMetrics,
    NetStatus,
    Params,
    PlacementResult,
    Result,
    RouteResult,
    Summary,
)

DETOUR_WARNING = 1.3


def detour_ratio(length: int, manhattan_dist: int) -> float:
    """length / manhattan rounded to 3 decimals; 1.0 when manhattan == 0."""
    if manhattan_dist == 0:
        return 1.0
    return round(length / manhattan_dist, 3)


def net_metrics(design: Design, pr: PlacementResult, route: RouteResult) -> NetMetrics:
    a = design.module(route.src).rect_at(pr.placement[route.src])
    b = design.module(route.dst).rect_at(pr.placement[route.dst])
    dist = manhattan(a, b)
    detour: float | None = None
    stages: int | None = None
    status: NetStatus = "unroutable"
    if route.length is not None:
        detour = detour_ratio(route.length, dist)
        stages = stages_for(route.length, design.reach_per_cycle)
        status = "detour_warning" if detour > DETOUR_WARNING else "ok"
    return NetMetrics(
        src=route.src,
        dst=route.dst,
        width=route.width,
        manhattan=dist,
        length=route.length,
        detour=detour,
        pipeline_stages=stages,
        status=status,
        path=route.path,
    )


def summarize(pr: PlacementResult, nets: list[NetMetrics]) -> Summary:
    routed = [n for n in nets if n.length is not None]
    detours = [n.detour for n in routed if n.detour is not None]
    return Summary(
        legal=pr.legal,
        violations=pr.violations,
        cost_initial=pr.cost_initial,
        cost_final=pr.cost_final,
        total_weighted_length=sum(n.width / 64 * n.length for n in routed if n.length is not None),
        total_pipeline_stages=sum(n.pipeline_stages or 0 for n in routed),
        max_detour=max(detours) if detours else None,
        unroutable_count=len(nets) - len(routed),
        seed=pr.seed,
        iterations=pr.iterations,
    )


def build_result(
    design: Design,
    pr: PlacementResult,
    routes: list[RouteResult],
    weights: CostWeights,
) -> Result:
    nets = [net_metrics(design, pr, r) for r in routes]
    return Result(
        design=design.name,
        params=Params(
            seed=pr.seed,
            iterations=pr.iterations,
            lambda_overlap=weights.lambda_overlap,
            lambda_halo=weights.lambda_halo,
            lambda_pipe=weights.lambda_pipe,
        ),
        placement={m.name: pr.placement[m.name] for m in design.modules},
        nets=nets,
        summary=summarize(pr, nets),
    )
