"""Grid A* routing between module footprints (Section 7).

Cells inside any module footprint are blocked; halo cells are free. Route length counts the
4-connected steps from a cell of A to a cell of B. Nets are routed independently (no congestion).
"""

from __future__ import annotations

import heapq

from minitile.geometry import Cell, Rect, distance_to_rect, neighbors_of_rect, overlap_area
from minitile.model import Design, Net, Placement, RouteResult


class Grid:
    """Blocked-cell map of the die for a given placement."""

    def __init__(self, design: Design, placement: Placement) -> None:
        self.width = design.die.width
        self.height = design.die.height
        self.blocked = bytearray(self.width * self.height)
        for m in design.modules:
            r = m.rect_at(placement[m.name])
            for x in range(max(0, r.x), min(self.width, r.x + r.w)):
                for y in range(max(0, r.y), min(self.height, r.y + r.h)):
                    self.blocked[y * self.width + x] = 1

    def free(self, c: Cell) -> bool:
        x, y = c
        return 0 <= x < self.width and 0 <= y < self.height and not self.blocked[y * self.width + x]


def route_between(grid: Grid, a: Rect, b: Rect) -> tuple[int | None, list[Cell]]:
    """Shortest route length from footprint ``a`` to footprint ``b`` and its free-cell path.

    Returns ``(None, [])`` if unroutable. Overlapping footprints give length 0, 4-adjacent
    footprints give length 1; both have an empty path.
    """
    if overlap_area(a, b) > 0:
        return 0, []
    starts = [c for c in neighbors_of_rect(a, grid.width, grid.height) if grid.free(c)]
    if any(distance_to_rect(c, b) == 0 for c in neighbors_of_rect(a, grid.width, grid.height)):
        return 1, []  # A and B are 4-adjacent

    g_best: dict[Cell, int] = {}
    parent: dict[Cell, Cell | None] = {}
    heap: list[tuple[int, int, int, int]] = []
    for c in starts:
        h = distance_to_rect(c, b)
        g_best[c] = 1
        parent[c] = None
        heapq.heappush(heap, (1 + h, h, c[0], c[1]))

    while heap:
        f, h, x, y = heapq.heappop(heap)
        c = (x, y)
        g = f - h
        if g > g_best[c]:
            continue  # stale entry
        if h == 1:  # free cell 4-adjacent to B: one more step enters B
            path: list[Cell] = []
            cur: Cell | None = c
            while cur is not None:
                path.append(cur)
                cur = parent[cur]
            path.reverse()
            return g + 1, path
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not grid.free(n):
                continue
            ng = g + 1
            if ng < g_best.get(n, 1 << 60):
                g_best[n] = ng
                parent[n] = c
                nh = distance_to_rect(n, b)
                heapq.heappush(heap, (ng + nh, nh, n[0], n[1]))
    return None, []


def net_order(nets: list[Net]) -> list[Net]:
    """Routing/output order: width desc, then (from, to) name pair."""
    return sorted(nets, key=lambda n: (-n.width, n.src, n.dst))


def route_all(design: Design, placement: Placement) -> list[RouteResult]:
    grid = Grid(design, placement)
    rects = {m.name: m.rect_at(placement[m.name]) for m in design.modules}
    out: list[RouteResult] = []
    for net in net_order(design.nets):
        length, path = route_between(grid, rects[net.src], rects[net.dst])
        out.append(RouteResult(src=net.src, dst=net.dst, width=net.width, length=length, path=path))
    return out
