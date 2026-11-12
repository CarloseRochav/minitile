import json
import re
from pathlib import Path

from typer.testing import CliRunner

from minitile.cli import app, percent_change

TESTCASES = Path(__file__).parent.parent / "testcases"
runner = CliRunner()

INVALID = """
die: { width: 10, height: 10 }
reach_per_cycle: 12
modules:
  - { name: a, w: 2, h: 2 }
  - { name: a, w: 2, h: 2 }
nets:
  - { from: a, to: ghost, width: 64 }
"""

# Passes the area check (18 <= 25) but two 3x3 modules plus halo 1 need 7 cells on some axis.
OVERPACKED = """
die: { width: 5, height: 5, halo: 1 }
reach_per_cycle: 12
modules:
  - { name: a, w: 3, h: 3 }
  - { name: b, w: 3, h: 3 }
nets:
  - { from: a, to: b, width: 64 }
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_validate_ok() -> None:
    r = runner.invoke(app, ["validate", str(TESTCASES / "star_noc.yaml")])
    assert r.exit_code == 0
    assert r.stdout.strip() == "OK"


def test_validate_invalid(tmp_path: Path) -> None:
    r = runner.invoke(app, ["validate", str(write(tmp_path, "bad.yaml", INVALID))])
    assert r.exit_code == 1
    assert "duplicate module name" in r.stdout
    assert "unknown module 'ghost'" in r.stdout


def test_run_ok() -> None:
    r = runner.invoke(app, ["run", str(TESTCASES / "tiny_2modules.yaml"), "--iterations", "100"])
    assert r.exit_code == 0, r.stdout
    assert r.stdout.startswith("placement: skipped (all modules fixed)")  # tiny is all fixed
    assert "a→b" in r.stdout or "a->b" in r.stdout


def test_run_invalid(tmp_path: Path) -> None:
    r = runner.invoke(app, ["run", str(write(tmp_path, "bad.yaml", INVALID))])
    assert r.exit_code == 1


def test_run_illegal(tmp_path: Path) -> None:
    r = runner.invoke(
        app, ["run", str(write(tmp_path, "packed.yaml", OVERPACKED)), "--iterations", "200"]
    )
    assert r.exit_code == 2, r.stdout
    assert "legal: no" in r.stdout


def test_run_unroutable() -> None:
    r = runner.invoke(app, ["run", str(TESTCASES / "unroutable.yaml"), "--iterations", "100"])
    assert r.exit_code == 3, r.stdout
    assert "unroutable" in r.stdout


def test_run_out_and_report(tmp_path: Path) -> None:
    out = tmp_path / "result.json"
    r = runner.invoke(
        app,
        [
            "run",
            str(TESTCASES / "star_noc.yaml"),
            "--seed",
            "42",
            "--iterations",
            "500",
            "--out",
            str(out),
        ],
    )
    assert r.exit_code == 0, r.stdout
    data = json.loads(out.read_text())
    assert set(data) == {"design", "params", "placement", "nets", "summary", "layout"}
    assert set(data["params"]) == {
        "seed",
        "iterations",
        "lambda_overlap",
        "lambda_halo",
        "lambda_pipe",
    }
    assert set(data["summary"]) >= {
        "legal",
        "violations",
        "cost_initial",
        "cost_final",
        "total_weighted_length",
        "total_pipeline_stages",
        "max_detour",
        "unroutable_count",
    }
    assert data["design"] == "star_noc"
    assert data["params"]["seed"] == 42
    assert list(data) == sorted(data)  # keys sorted

    rep = runner.invoke(app, ["report", str(out)])
    assert rep.exit_code == 0
    assert rep.stdout == r.stdout  # same table from the saved JSON


def test_report_bad_file(tmp_path: Path) -> None:
    r = runner.invoke(app, ["report", str(write(tmp_path, "x.json", "{not json"))])
    assert r.exit_code == 1


def test_percent_change_signs() -> None:
    assert percent_change(100, 100) == "0%"
    assert percent_change(1000, 999) == "0%"  # -0.1% rounds to 0: no sign
    assert percent_change(1000, 1001) == "0%"
    assert percent_change(1842, 1107) == "\N{MINUS SIGN}40%"
    assert percent_change(100, 150) == "+50%"
    assert percent_change(100, 60, minus="-") == "-40%"
    assert percent_change(0, 0) == "0%"


def test_run_all_fixed_header_and_json(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    r = runner.invoke(app, ["run", str(TESTCASES / "blocked_route.yaml"), "--out", str(out)])
    assert r.exit_code == 0, r.stdout
    first = r.stdout.splitlines()[0]
    assert first.startswith("placement: skipped (all modules fixed)")
    assert "Placement cost" not in r.stdout and "iterations" not in first
    s = json.loads(out.read_text())["summary"]
    assert s["placement_skipped"] is True
    assert s["cost_initial"] == s["cost_final"] == 69.0  # 19 + 50 * stages_est(19) = 19 + 50


def test_run_movable_json_not_skipped(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    r = runner.invoke(
        app, ["run", str(TESTCASES / "chain_5.yaml"), "--iterations", "200", "--out", str(out)]
    )
    assert r.exit_code == 0, r.stdout
    assert json.loads(out.read_text())["summary"]["placement_skipped"] is False
    assert r.stdout.startswith("Placement cost:")
    assert "(+0%)" not in r.stdout


HEADER_RE = re.compile(
    r"^Placement cost: (?P<x>[\d,]+) (?:→|->) (?P<y>[\d,]+) "
    r"\((?P<pct>0%|[\N{MINUS SIGN}-]\d+%|\+\d+%)\)  legal: yes  seed: 42  iterations: 20,000$"
)


def test_run_real_placement_header() -> None:
    """star_noc has movable modules: the header must show `Placement cost: X → Y (...)`."""
    r = runner.invoke(app, ["run", str(TESTCASES / "star_noc.yaml"), "--seed", "42"])
    assert r.exit_code == 0, r.stdout
    m = HEADER_RE.match(r.stdout.splitlines()[0])
    assert m, r.stdout.splitlines()[0]
    x, y = int(m["x"].replace(",", "")), int(m["y"].replace(",", ""))
    assert y < x  # annealing improved on greedy
    assert m["pct"] != "0%" and not m["pct"].startswith("+")


def test_long_net_names_not_truncated() -> None:
    r = runner.invoke(app, ["run", str(TESTCASES / "soc_demo.yaml"), "--iterations", "200"])
    assert "…" not in r.stdout
    assert "cpu_cluster→l3_cache" in r.stdout or "cpu_cluster->l3_cache" in r.stdout
