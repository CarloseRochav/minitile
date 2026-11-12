"""Cross-process determinism: output must not depend on PYTHONHASHSEED (hash/set order)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTCASES = Path(__file__).parent.parent / "testcases"


def run_cli(design: Path, out: Path, hashseed: str) -> bytes:
    env = {**os.environ, "PYTHONHASHSEED": hashseed}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "minitile.cli",
            "run",
            str(design),
            "--seed",
            "42",
            "--out",
            str(out),
        ],
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout.decode(errors="replace") + proc.stderr.decode(
        errors="replace"
    )
    return out.read_bytes()


@pytest.mark.parametrize("name", ["star_noc", "chain_5", "soc_demo"])
def test_output_identical_across_hash_seeds(name: str, tmp_path: Path) -> None:
    design = TESTCASES / f"{name}.yaml"
    a = run_cli(design, tmp_path / "a.json", "1")
    b = run_cli(design, tmp_path / "b.json", "2")
    assert a == b
