"""Integer-grid rectangle operations (Section 4 of the spec).

A ``Rect`` at ``(x, y)`` with size ``(w, h)`` occupies cells ``x .. x+w-1`` and ``y .. y+h-1``.
"""

from __future__ import annotations

from dataclasses import dataclass

Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        """Last occupied column (inclusive)."""
        return self.x + self.w - 1

    @property
    def y2(self) -> int:
        """Last occupied row (inclusive)."""
        return self.y + self.h - 1

    @property
    def area(self) -> int:
        return self.w * self.h


def cells(r: Rect) -> set[Cell]:
    """All cells occupied by ``r``."""
    return {(x, y) for x in range(r.x, r.x + r.w) for y in range(r.y, r.y + r.h)}


def inside_die(r: Rect, width: int, height: int) -> bool:
    return r.x >= 0 and r.y >= 0 and r.x + r.w <= width and r.y + r.h <= height


def overlap_area(a: Rect, b: Rect) -> int:
    """Area of the intersection of two footprints (0 if disjoint)."""
    ox = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    if ox <= 0:
        return 0
    oy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    if oy <= 0:
        return 0
    return ox * oy


def manhattan(a: Rect, b: Rect) -> int:
    """Gap distance between the nearest cells of ``a`` and ``b`` (0 if they overlap)."""
    dx = max(0, b.x - a.x2, a.x - b.x2)
    dy = max(0, b.y - a.y2, a.y - b.y2)
    return dx + dy


def expand(r: Rect, halo: int) -> Rect:
    """``r`` grown by ``halo`` cells on every side."""
    return Rect(r.x - halo, r.y - halo, r.w + 2 * halo, r.h + 2 * halo)


def halo_violation(a: Rect, b: Rect, halo: int) -> int:
    """Directional halo violation: area(expand(a) ∩ b) - overlap_area(a, b)."""
    if halo <= 0:
        return 0
    return overlap_area(expand(a, halo), b) - overlap_area(a, b)


def halo_violation_pair(a: Rect, b: Rect, halo: int) -> int:
    """Symmetric halo violation of an unordered pair: hv(a, b) + hv(b, a)."""
    return halo_violation(a, b, halo) + halo_violation(b, a, halo)


def violates_halo(a: Rect, b: Rect, halo: int) -> bool:
    """True if the footprints don't overlap but the empty gap between them is < ``halo``."""
    return halo > 0 and overlap_area(a, b) == 0 and overlap_area(expand(a, halo), b) > 0


def adjacent(a: Rect, b: Rect) -> bool:
    """True if the footprints do not overlap and some cell of ``a`` is 4-adjacent to ``b``."""
    return overlap_area(a, b) == 0 and manhattan(a, b) == 1


def distance_to_rect(c: Cell, r: Rect) -> int:
    """Manhattan distance (in steps) from cell ``c`` to the nearest cell of ``r``."""
    x, y = c
    dx = max(0, r.x - x, x - r.x2)
    dy = max(0, r.y - y, y - r.y2)
    return dx + dy


def neighbors_of_rect(r: Rect, width: int, height: int) -> list[Cell]:
    """Cells inside the die that are 4-adjacent to ``r`` (sorted, deterministic)."""
    out: set[Cell] = set()
    for x in range(r.x, r.x + r.w):
        out.add((x, r.y - 1))
        out.add((x, r.y + r.h))
    for y in range(r.y, r.y + r.h):
        out.add((r.x - 1, y))
        out.add((r.x + r.w, y))
    return sorted((x, y) for x, y in out if 0 <= x < width and 0 <= y < height)
