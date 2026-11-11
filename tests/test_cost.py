import random
from pathlib import Path

import pytest

from minitile.cost import CostModel, CostWeights, delta_cost, full_cost, stages_for
from minitile.model import Placement, Position
from minitile.parser import load_design, parse_design

TESTCASES = Path(__file__).parent.parent / "testcases"


def test_tiny_hand_computed() -> None:
    d = load_design(TESTCASES / "tiny_2modules.yaml")
    # manhattan 7, weight 64/64 = 1, stages 0, no overlap, gap 6 > halo
    assert full_cost(d, {"a": (1, 1), "b": (10, 1)}) == pytest.approx(7.0)


def test_hand_computed_penalties() -> None:
    d = parse_design(
        "die: { width: 40, height: 10, halo: 1 }\nreach_per_cycle: 4\n"
        "modules: [{name: a, w: 3, h: 3}, {name: b, w: 3, h: 3}]\n"
        "nets: [{from: a, to: b, width: 64}, {from: b, to: a, width: 64}]\n"
    )
    # far apart: manhattan 10, merged weight 2, stages ceil(10/4)-1 = 2
    assert full_cost(d, {"a": (0, 0), "b": (12, 0)}) == pytest.approx(2 * 10 + 50 * 2)
    # touching edge: manhattan 1, overlap 0, halo hv(a,b)=3 + hv(b,a)=3
    assert full_cost(d, {"a": (0, 0), "b": (3, 0)}) == pytest.approx(2 * 1 + 200 * 6)
    # overlap 2x3=6, halo: expand(a) covers x -1..3, b covers 2..4 -> 3*3=9 - 6 = 3, both ways
    w = CostWeights(lambda_overlap=10, lambda_halo=1, lambda_pipe=0)
    assert full_cost(d, {"a": (0, 0), "b": (1, 0)}, w) == pytest.approx(10 * 6 + 1 * 6)


def test_stages_for() -> None:
    assert [stages_for(n, 12) for n in (0, 12, 13, 24, 25)] == [0, 0, 1, 1, 2]


def test_delta_matches_full_difference_chain5() -> None:
    d = load_design(TESTCASES / "chain_5.yaml")
    model = CostModel(d)
    rng = random.Random(1234)
    W, H = d.die.width, d.die.height
    movable = [i for i, m in enumerate(d.modules) if m.fixed is None]
    pos: list[Position] = []
    for m in d.modules:
        pos.append(m.fixed if m.fixed else (rng.randrange(W - m.w + 1), rng.randrange(H - m.h + 1)))

    for _ in range(500):
        if rng.random() < 0.7:
            i = rng.choice(movable)
            w, h = model.sizes[i]
            moves = {i: (rng.randrange(W - w + 1), rng.randrange(H - h + 1))}
        else:
            i, j = rng.sample(movable, 2)
            moves = {i: pos[j], j: pos[i]}
        after = list(pos)
        for k, p in moves.items():
            after[k] = p
        expected = model.full(after) - model.full(pos)
        assert abs(model.delta(pos, moves) - expected) < 1e-9
        pos = after


def test_wrapper_functions_agree() -> None:
    d = load_design(TESTCASES / "chain_5.yaml")
    p: Placement = {"m1": (2, 2), "m2": (12, 2), "m3": (20, 2), "m4": (30, 2), "m5": (30, 12)}
    q = dict(p)
    q["m3"] = (11, 3)
    assert delta_cost(d, p, {"m3": (11, 3)}) == pytest.approx(full_cost(d, q) - full_cost(d, p))
