from pathlib import Path

import pytest

from minitile.geometry import Cell, Rect, cells, distance_to_rect, manhattan
from minitile.model import Design, Placement, RouteResult
from minitile.parser import load_design, parse_design
from minitile.router import Grid, route_all, route_between

TESTCASES = Path(__file__).parent.parent / "testcases"


def fixed_placement(d: Design) -> Placement:
    return {m.name: m.fixed for m in d.modules if m.fixed is not None}


def route_case(name: str) -> tuple[Design, Placement, list[RouteResult]]:
    d = load_design(TESTCASES / f"{name}.yaml")
    p = fixed_placement(d)
    return d, p, route_all(d, p)


def assert_valid_path(d: Design, p: Placement, a: Rect, b: Rect, r: RouteResult) -> None:
    blocked: set[Cell] = set()
    for m in d.modules:
        blocked |= cells(m.rect_at(p[m.name]))
    assert r.length is not None
    if r.length <= 1:
        assert r.path == []
        return
    assert len(r.path) == r.length - 1
    assert distance_to_rect(r.path[0], a) == 1
    assert distance_to_rect(r.path[-1], b) == 1
    for c in r.path:
        assert c not in blocked
        assert 0 <= c[0] < d.die.width and 0 <= c[1] < d.die.height
    for c1, c2 in zip(r.path, r.path[1:], strict=False):
        assert abs(c1[0] - c2[0]) + abs(c1[1] - c2[1]) == 1


def test_tiny_2modules() -> None:
    d, p, routes = route_case("tiny_2modules")
    (r,) = routes
    a, b = d.module("a").rect_at(p["a"]), d.module("b").rect_at(p["b"])
    assert manhattan(a, b) == 7
    assert r.length == 7
    assert_valid_path(d, p, a, b, r)


def test_blocked_route() -> None:
    d, p, routes = route_case("blocked_route")
    (r,) = routes
    a, b = d.module("a").rect_at(p["a"]), d.module("b").rect_at(p["b"])
    assert manhattan(a, b) == 19
    assert r.length == 33
    assert_valid_path(d, p, a, b, r)
    assert all(y >= 18 or y <= 1 for x, y in r.path if 14 <= x <= 15)


def test_unroutable() -> None:
    _, _, routes = route_case("unroutable")
    (r,) = routes
    assert r.length is None and r.path == []


def test_adjacent_halo0() -> None:
    d = parse_design(
        "die: { width: 10, height: 10, halo: 0 }\nreach_per_cycle: 12\n"
        "modules: [{name: a, w: 2, h: 2, fixed: [0, 0]}, {name: b, w: 2, h: 2, fixed: [2, 1]}]\n"
        "nets: [{from: a, to: b, width: 64}]\n"
    )
    (r,) = route_all(d, fixed_placement(d))
    assert r.length == 1 and r.path == []


def test_one_cell_gap() -> None:
    d = parse_design(
        "die: { width: 10, height: 10, halo: 1 }\nreach_per_cycle: 12\n"
        "modules: [{name: a, w: 2, h: 2, fixed: [0, 0]}, {name: b, w: 2, h: 2, fixed: [3, 0]}]\n"
        "nets: [{from: a, to: b, width: 64}]\n"
    )
    (r,) = route_all(d, fixed_placement(d))
    assert r.length == 2 and r.path == [(2, 0)]


def test_overlapping_footprints_length_zero() -> None:
    d = parse_design(
        "die: { width: 10, height: 10, halo: 0 }\nreach_per_cycle: 12\n"
        "modules: [{name: a, w: 3, h: 3}, {name: b, w: 3, h: 3}]\nnets: []\n"
    )
    grid = Grid(d, {"a": (0, 0), "b": (1, 1)})
    assert route_between(grid, Rect(0, 0, 3, 3), Rect(1, 1, 3, 3)) == (0, [])


def test_route_order_width_desc_then_names() -> None:
    d = load_design(TESTCASES / "star_noc.yaml")
    p = {"cpu": (2, 2), "gpu": (14, 2), "dsp": (2, 14), "modem": (14, 14), "noc": (28, 28)}
    routes = route_all(d, p)
    assert [(r.src, r.dst) for r in routes] == [
        ("gpu", "noc"),
        ("cpu", "noc"),
        ("dsp", "modem"),
        ("noc", "modem"),
    ]


@pytest.mark.parametrize("name", ["tiny_2modules", "blocked_route"])
def test_paths_are_valid(name: str) -> None:
    d, p, routes = route_case(name)
    for r in routes:
        assert_valid_path(
            d, p, d.module(r.src).rect_at(p[r.src]), d.module(r.dst).rect_at(p[r.dst]), r
        )
