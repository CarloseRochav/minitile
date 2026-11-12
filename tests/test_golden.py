"""Golden regression (Section 11.8). Regenerate with: ``uv run pytest --update-golden``."""

import json
from pathlib import Path

import pytest

from minitile import Floorplan

TESTCASES = Path(__file__).parent.parent / "testcases"
GOLDEN_SEED = 42
GOLDENS = ["chain_5", "star_noc", "soc_demo"]


@pytest.mark.parametrize("name", GOLDENS)
def test_golden(name: str, update_golden: bool) -> None:
    result = Floorplan.load(TESTCASES / f"{name}.yaml").place(seed=GOLDEN_SEED).route().report()
    golden = TESTCASES / f"{name}.golden.json"
    if update_golden:
        golden.write_text(result.to_json_str(), encoding="utf-8", newline="\n")
        pytest.skip(f"updated {golden.name}")
    assert golden.exists(), f"missing {golden.name}; run `uv run pytest --update-golden`"
    # Compare parsed objects so the check doesn't depend on whitespace or line endings.
    assert result.to_dict() == json.loads(golden.read_text(encoding="utf-8"))
    assert result.summary.legal


@pytest.mark.parametrize("name", GOLDENS)
def test_golden_file_format(name: str) -> None:
    raw = (TESTCASES / f"{name}.golden.json").read_bytes()
    assert b"\r" not in raw, "golden files must use LF line endings"
    assert raw.endswith(b"}\n") and not raw.endswith(b"\n\n"), "must end with exactly one \\n"


def test_soc_demo_showcase_criteria() -> None:
    """soc_demo must keep showing real trade-offs with --seed 42 and default parameters."""
    r = Floorplan.load(TESTCASES / "soc_demo.yaml").place(seed=GOLDEN_SEED).route().report()
    s = r.summary
    assert s.legal and s.unroutable_count == 0
    assert (s.cost_initial - s.cost_final) / s.cost_initial >= 0.20
    assert sum(1 for n in r.nets if (n.pipeline_stages or 0) >= 1) >= 2
    assert any(n.status == "detour_warning" for n in r.nets)
    assert 12 <= len(r.placement) <= 15
