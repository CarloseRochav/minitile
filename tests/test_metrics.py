from pathlib import Path

import pytest

from minitile import Floorplan
from minitile.api import FloorplanStateError
from minitile.cost import stages_for
from minitile.metrics import detour_ratio

TESTCASES = Path(__file__).parent.parent / "testcases"


def test_detour_zero_manhattan() -> None:
    assert detour_ratio(0, 0) == 1.0
    assert detour_ratio(5, 0) == 1.0
    assert detour_ratio(33, 19) == 1.737


@pytest.mark.parametrize("length, stages", [(12, 0), (13, 1), (24, 1), (25, 2)])
def test_pipeline_stages(length: int, stages: int) -> None:
    assert stages_for(length, 12) == stages


def test_tiny_net_metrics() -> None:
    r = Floorplan.load(TESTCASES / "tiny_2modules.yaml").place(iterations=100).route().report()
    (n,) = r.nets
    assert (n.manhattan, n.length, n.detour, n.pipeline_stages, n.status) == (7, 7, 1.0, 0, "ok")


def test_blocked_route_summary() -> None:
    r = Floorplan.load(TESTCASES / "blocked_route.yaml").place(iterations=100).route().report()
    (n,) = r.nets
    assert n.manhattan == 19
    assert n.length == 33
    assert n.detour == 1.737
    assert n.pipeline_stages == 2
    assert n.status == "detour_warning"
    s = r.summary
    assert s.legal and s.violations == []
    assert s.total_weighted_length == 33.0  # width 64 -> weight 1
    assert s.total_pipeline_stages == 2
    assert s.max_detour == 1.737
    assert s.unroutable_count == 0
    assert s.cost_initial == s.cost_final  # everything fixed


def test_unroutable_metrics() -> None:
    r = Floorplan.load(TESTCASES / "unroutable.yaml").place(iterations=100).route().report()
    (n,) = r.nets
    assert n.status == "unroutable"
    assert n.length is None and n.detour is None and n.pipeline_stages is None
    assert r.summary.unroutable_count == 1
    assert r.summary.max_detour is None
    assert r.summary.total_weighted_length == 0.0


def test_api_is_immutable_and_ordered() -> None:
    fp = Floorplan.load(TESTCASES / "chain_5.yaml")
    with pytest.raises(FloorplanStateError, match="before place"):
        fp.route()
    placed = fp.place(seed=1, iterations=500)
    assert fp.placement is None and placed.placement is not None
    with pytest.raises(FloorplanStateError, match="before route"):
        placed.report()
    result = placed.route().report()
    assert result.design == "chain_5"
    assert result.params.seed == 1 and result.params.iterations == 500


def test_json_roundtrip(tmp_path: Path) -> None:
    r = Floorplan.load(TESTCASES / "star_noc.yaml").place(seed=42, iterations=500).route().report()
    out = tmp_path / "out.json"
    r.to_json(out)
    data = r.to_dict()
    assert set(data) == {"design", "params", "placement", "nets", "summary", "layout"}
    assert set(data["nets"][0]) == {
        "from",
        "to",
        "width",
        "manhattan",
        "length",
        "detour",
        "pipeline_stages",
        "status",
        "path",
    }
    assert type(r).from_json(out).to_json_str() == out.read_text()


def test_layout_section() -> None:
    r = Floorplan.load(TESTCASES / "blocked_route.yaml").place(iterations=0).route().report()
    assert r.layout is not None
    assert (r.layout.die.width, r.layout.die.height, r.layout.die.halo) == (30, 20, 1)
    assert r.layout.reach_per_cycle == 12
    assert r.layout.modules["wall"].w == 2 and r.layout.modules["wall"].h == 16
    assert all(m.fixed for m in r.layout.modules.values())
