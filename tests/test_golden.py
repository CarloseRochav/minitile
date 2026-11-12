"""Golden regression (Section 11.8). Regenerate with: ``uv run pytest --update-golden``."""

import json
from pathlib import Path

import pytest

from minitile import Floorplan

TESTCASES = Path(__file__).parent.parent / "testcases"
GOLDEN_SEED = 42
GOLDENS = ["chain_5", "star_noc"]


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
