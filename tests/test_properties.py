"""Property tests (Section 11.9): small random designs."""

from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from minitile import Floorplan
from minitile.geometry import Rect, overlap_area, violates_halo
from minitile.model import Design
from minitile.parser import validate_data

ITERATIONS = 300


@st.composite
def designs(draw: st.DrawFn) -> Design:
    width = draw(st.integers(8, 30))
    height = draw(st.integers(8, 30))
    halo = draw(st.integers(0, 2))
    budget = (width * height * 2) // 5  # module area <= 40% of the die
    n = draw(st.integers(2, 8))

    modules: list[dict[str, Any]] = []
    fixed_rects: list[Rect] = []
    used = 0
    for i in range(n):
        w = draw(st.integers(1, max(1, width // 3)))
        h = draw(st.integers(1, max(1, height // 3)))
        if used + w * h > budget:
            break
        used += w * h
        mod: dict[str, Any] = {"name": f"m{i}", "w": w, "h": h}
        if draw(st.booleans()) and draw(st.booleans()):  # ~25% fixed
            r = Rect(draw(st.integers(0, width - w)), draw(st.integers(0, height - h)), w, h)
            if all(overlap_area(r, o) == 0 and not violates_halo(r, o, halo) for o in fixed_rects):
                fixed_rects.append(r)
                mod["fixed"] = [r.x, r.y]
        modules.append(mod)
    if len(modules) < 2:
        modules = [{"name": "m0", "w": 1, "h": 1}, {"name": "m1", "w": 1, "h": 1}]

    names = [m["name"] for m in modules]
    pairs = st.tuples(st.sampled_from(names), st.sampled_from(names)).filter(lambda p: p[0] != p[1])
    nets = [
        {"from": a, "to": b, "width": draw(st.sampled_from([8, 32, 64, 128, 256]))}
        for a, b in draw(st.lists(pairs, min_size=1, max_size=10))
    ]
    data = {
        "die": {"width": width, "height": height, "halo": halo},
        "reach_per_cycle": draw(st.integers(1, 20)),
        "modules": modules,
        "nets": nets,
    }
    return validate_data(data, name="prop")


SETTINGS = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@SETTINGS
@given(designs(), st.integers(0, 2**16))
def test_routed_nets_length_ge_manhattan(design: Design, seed: int) -> None:
    result = Floorplan(design).place(seed=seed, iterations=ITERATIONS).route().report()
    for n in result.nets:
        if n.length is not None:
            assert n.length >= n.manhattan
            assert n.detour is not None and n.detour >= 1


@SETTINGS
@given(designs(), st.integers(0, 2**16))
def test_fixed_modules_unchanged(design: Design, seed: int) -> None:
    pr = Floorplan(design).place(seed=seed, iterations=ITERATIONS).placement
    assert pr is not None
    for m in design.modules:
        if m.fixed is not None:
            assert pr.placement[m.name] == m.fixed


@SETTINGS
@given(designs(), st.integers(0, 2**16))
def test_deterministic(design: Design, seed: int) -> None:
    fp = Floorplan(design)
    a = fp.place(seed=seed, iterations=ITERATIONS).route().report().to_json_str()
    b = fp.place(seed=seed, iterations=ITERATIONS).route().report().to_json_str()
    assert a == b


@SETTINGS
@given(designs(), st.integers(0, 2**16))
def test_cost_final_le_initial(design: Design, seed: int) -> None:
    pr = Floorplan(design).place(seed=seed, iterations=ITERATIONS).placement
    assert pr is not None
    assert pr.cost_final <= pr.cost_initial
