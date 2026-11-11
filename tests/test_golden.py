"""Golden regression (Section 11.8). Regenerate with: ``uv run pytest --update-golden``."""

from pathlib import Path

import pytest

from minitile import Floorplan

TESTCASES = Path(__file__).parent.parent / "testcases"
GOLDEN_SEED = 42


@pytest.mark.parametrize("name", ["chain_5", "star_noc"])
def test_golden(name: str, update_golden: bool) -> None:
    result = Floorplan.load(TESTCASES / f"{name}.yaml").place(seed=GOLDEN_SEED).route().report()
    actual = result.to_json_str()
    golden = TESTCASES / f"{name}.golden.json"
    if update_golden:
        golden.write_text(actual, encoding="utf-8", newline="\n")
        pytest.skip(f"updated {golden.name}")
    assert golden.exists(), f"missing {golden.name}; run `uv run pytest --update-golden`"
    assert actual == golden.read_text(encoding="utf-8")
    assert result.summary.legal
