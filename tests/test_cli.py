import json
from pathlib import Path

from typer.testing import CliRunner

from minitile.cli import app

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
    assert "Placement cost:" in r.stdout
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
    assert set(data) == {"design", "params", "placement", "nets", "summary"}
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
