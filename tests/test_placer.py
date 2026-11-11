from pathlib import Path

import pytest

from minitile.cost import CostModel
from minitile.model import Design
from minitile.parser import load_design, parse_design
from minitile.placer import check_legality, greedy_placement, place

TESTCASES = Path(__file__).parent.parent / "testcases"


def design(name: str) -> Design:
    return load_design(TESTCASES / f"{name}.yaml")


@pytest.mark.parametrize("name", ["chain_5", "star_noc", "blocked_route", "tiny_2modules"])
def test_fixed_modules_never_move(name: str) -> None:
    d = design(name)
    res = place(d, seed=3, iterations=2_000)
    for m in d.modules:
        if m.fixed is not None:
            assert res.placement[m.name] == m.fixed


@pytest.mark.parametrize("seed", [0, 1, 7])
def test_cost_final_not_worse(seed: int) -> None:
    res = place(design("chain_5"), seed=seed, iterations=3_000)
    assert res.cost_final <= res.cost_initial


def test_same_seed_same_placement() -> None:
    d = design("star_noc")
    a = place(d, seed=42, iterations=3_000)
    b = place(d, seed=42, iterations=3_000)
    assert a == b


def test_different_seeds_run() -> None:
    d = design("star_noc")
    a = place(d, seed=1, iterations=3_000)
    b = place(d, seed=2, iterations=3_000)
    assert a.legal and b.legal  # placements may or may not differ


@pytest.mark.parametrize("name", ["chain_5", "star_noc"])
def test_default_params_legal(name: str) -> None:
    res = place(design(name))
    assert res.legal, res.violations
    assert res.violations == []


def test_greedy_is_legal_on_star() -> None:
    d = design("star_noc")
    model = CostModel(d)
    pos = greedy_placement(model)
    assert check_legality(d, {n: pos[i] for i, n in enumerate(model.names)}) == []


def test_legality_reports_violations() -> None:
    d = parse_design(
        "die: { width: 10, height: 10, halo: 1 }\nreach_per_cycle: 5\n"
        "modules: [{name: a, w: 3, h: 3}, {name: b, w: 3, h: 3}, {name: c, w: 3, h: 3}]\n"
        "nets: []\n"
    )
    v = check_legality(d, {"a": (0, 0), "b": (1, 1), "c": (8, 0)})
    assert "a overlaps b (area 4)" in v
    assert "c outside die" in v
    v = check_legality(d, {"a": (0, 0), "b": (3, 0), "c": (0, 6)})
    assert v == ["a violates halo 1 with b"]


def test_zero_iterations() -> None:
    res = place(design("chain_5"), iterations=0)
    assert res.cost_final == res.cost_initial
