"""SVG rendering (SPEC Section 14)."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from typer.testing import CliRunner

from minitile import Floorplan, Result
from minitile.cli import app
from minitile.render import CHAR_W, label_font, render_svg, stroke_width, svg_y

TESTCASES = Path(__file__).parent.parent / "testcases"
NS = "{http://www.w3.org/2000/svg}"
runner = CliRunner()


def result_for(name: str) -> Result:
    return Floorplan.load(TESTCASES / f"{name}.yaml").place(seed=42).route().report()


def classes(root: ET.Element, prefix: str) -> list[ET.Element]:
    return [e for e in root.iter() if (e.get("class") or "").split(" ")[0] == prefix]


def test_y_flip() -> None:
    # grid origin bottom-left, SVG origin top-left: svg_y = (H - y - h) * cell
    assert svg_y(0, 1, 10, 10) == 90  # bottom row -> bottom of the SVG die
    assert svg_y(9, 1, 10, 10) == 0  # top row -> SVG y 0
    assert svg_y(2, 3, 20, 10) == 150
    assert svg_y(0, 20, 20, 7) == 0  # full-height block


@pytest.mark.parametrize("name", ["blocked_route", "soc_demo", "unroutable", "star_noc"])
def test_svg_structure(name: str) -> None:
    r = result_for(name)
    assert r.layout is not None
    root = ET.fromstring(r.to_svg_str())
    assert root.tag == f"{NS}svg"
    assert len(classes(root, "background")) == 1
    modules = classes(root, "module")
    assert len(modules) == len(r.layout.modules)
    assert sorted(e.get("class", "") for e in modules).count("module fixed") == sum(
        m.fixed for m in r.layout.modules.values()
    )
    routes = classes(root, "route")
    assert len(routes) == len(r.nets)
    assert len(classes(root, "stage-marker")) == sum(n.pipeline_stages or 0 for n in r.nets)


def test_marker_counts() -> None:
    blocked = ET.fromstring(result_for("blocked_route").to_svg_str())
    assert len(classes(blocked, "stage-marker")) == 2
    soc = result_for("soc_demo")
    root = ET.fromstring(soc.to_svg_str())
    assert len(classes(root, "stage-marker")) == soc.summary.total_pipeline_stages == 26


def test_status_not_by_color_alone() -> None:
    root = ET.fromstring(result_for("blocked_route").to_svg_str())
    (route,) = classes(root, "route")
    assert route.get("class") == "route detour_warning"
    assert route.get("stroke-dasharray")  # dashed, not only orange
    unr = ET.fromstring(result_for("unroutable").to_svg_str())
    (line,) = classes(unr, "route")
    assert line.tag == f"{NS}line" and line.get("stroke-dasharray")


def test_route_starts_and_ends_on_footprint_edges() -> None:
    r = result_for("tiny_2modules")  # a cells x 1..3, b cells x 10..12, route along y
    root = ET.fromstring(r.to_svg_str())
    (route,) = classes(root, "route")
    pts = [tuple(float(v) for v in p.split(",")) for p in route.get("points", "").split()]
    xs = [p[0] for p in pts]
    assert xs[0] == 40.0  # right edge of a: x = 4 cells * 10 px
    assert xs[-1] == 100.0  # left edge of b: x = 10 cells * 10 px
    assert len(pts) == len(r.nets[0].path) + 2


def test_labels_never_overflow() -> None:
    for name, w, h in [("cpu_cluster", 140, 120), ("usb_phy", 40, 120), ("x" * 40, 30, 30)]:
        fit = label_font(name, w, h)
        if fit is None:
            continue
        size, rotated = fit
        along, across = (h, w) if rotated else (w, h)
        assert CHAR_W * size * len(name) <= along - 4 + 1e-9
        assert size <= across - 4
    assert label_font("a_very_long_module_name", 10, 10) is None  # too small: no label


def test_stroke_width_bounds() -> None:
    assert stroke_width(8) == 1.0
    assert stroke_width(64) == 1.75
    assert stroke_width(512) == 4.0
    assert stroke_width(4096) == 4.0


def test_deterministic_and_json_roundtrip(tmp_path: Path) -> None:
    r = result_for("soc_demo")
    out = tmp_path / "r.json"
    r.to_json(out)
    from_json = Result.from_json(out).to_svg_str()
    assert from_json == r.to_svg_str() == Result.from_json(out).to_svg_str()


def test_no_layout_raises() -> None:
    r = result_for("tiny_2modules").model_copy(update={"layout": None})
    with pytest.raises(ValueError, match="no layout"):
        render_svg(r)
    with pytest.raises(ValueError, match="cell"):
        render_svg(result_for("tiny_2modules"), cell=0)


@pytest.mark.parametrize("name", ["blocked_route", "soc_demo"])
def test_golden_svg(name: str, update_golden: bool) -> None:
    svg = result_for(name).to_svg_str()
    golden = TESTCASES / f"{name}.golden.svg"
    if update_golden:
        golden.write_text(svg, encoding="utf-8", newline="\n")
        pytest.skip(f"updated {golden.name}")
    assert golden.exists(), f"missing {golden.name}; run `uv run pytest --update-golden`"
    assert svg == golden.read_text(encoding="utf-8")


def test_cli_render_and_run_svg(tmp_path: Path) -> None:
    js, svg_run, svg_render = tmp_path / "r.json", tmp_path / "a.svg", tmp_path / "b.svg"
    design = str(TESTCASES / "star_noc.yaml")
    r = runner.invoke(
        app,
        [
            "run",
            design,
            "--seed",
            "42",
            "--iterations",
            "300",
            "--out",
            str(js),
            "--svg",
            str(svg_run),
        ],
    )
    assert r.exit_code == 0, r.stdout
    r = runner.invoke(app, ["render", str(js), "--out", str(svg_render)])
    assert r.exit_code == 0, r.stdout
    assert svg_run.read_bytes() == svg_render.read_bytes()
    ET.fromstring(svg_render.read_text(encoding="utf-8"))
    r = runner.invoke(app, ["render", str(js), "--out", str(tmp_path / "c.svg"), "--cell", "4"])
    assert r.exit_code == 0
    assert 'width="160"' in (tmp_path / "c.svg").read_text(encoding="utf-8")  # 40 cells * 4 px


def test_cli_render_bad_input(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    r = runner.invoke(app, ["render", str(bad), "--out", str(tmp_path / "x.svg")])
    assert r.exit_code == 1


def test_docs_image_up_to_date(update_golden: bool) -> None:
    """README embeds docs/img/soc_demo.svg; it must match the current renderer output."""
    image = Path(__file__).parent.parent / "docs" / "img" / "soc_demo.svg"
    svg = result_for("soc_demo").to_svg_str()
    if update_golden:
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_text(svg, encoding="utf-8", newline="\n")
        pytest.skip("updated docs/img/soc_demo.svg")
    assert image.exists(), "missing docs/img/soc_demo.svg; run `uv run pytest --update-golden`"
    assert image.read_text(encoding="utf-8") == svg, (
        "docs/img/soc_demo.svg is out of date; run `uv run pytest --update-golden`"
    )
