"""Benchmark (Section 12): 30 modules, 60 nets, 100x100 die, 20 000 iterations + routing.

Usage: ``uv run python scripts/benchmark.py [--seed 0] [--iterations 20000]``
Target: < 10 s on a laptop. Not run in CI.
"""

from __future__ import annotations

import argparse
import random
import time
from typing import Any

from minitile import Floorplan
from minitile.parser import validate_data


def generate(seed: int, n_modules: int = 30, n_nets: int = 60, size: int = 100) -> dict[str, Any]:
    rng = random.Random(seed)
    modules: list[dict[str, Any]] = []
    for i in range(n_modules):
        modules.append({"name": f"m{i:02d}", "w": rng.randint(4, 12), "h": rng.randint(4, 12)})
    modules[0]["fixed"] = [2, 2]
    nets = []
    for _ in range(n_nets):
        a, b = rng.sample(range(n_modules), 2)
        nets.append(
            {
                "from": modules[a]["name"],
                "to": modules[b]["name"],
                "width": rng.choice([32, 64, 128, 256]),
            }
        )
    return {
        "die": {"width": size, "height": size, "halo": 1},
        "reach_per_cycle": 20,
        "modules": modules,
        "nets": nets,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--iterations", type=int, default=20_000)
    args = ap.parse_args()

    design = validate_data(generate(args.seed), name="bench_30x60")
    t0 = time.perf_counter()
    placed = Floorplan(design).place(seed=args.seed, iterations=args.iterations)
    t1 = time.perf_counter()
    result = placed.route().report()
    t2 = time.perf_counter()

    s = result.summary
    print(f"placement: {t1 - t0:.2f} s   routing+metrics: {t2 - t1:.2f} s   total: {t2 - t0:.2f} s")
    print(
        f"legal: {s.legal}  cost: {s.cost_initial:,.0f} -> {s.cost_final:,.0f}  "
        f"unroutable: {s.unroutable_count}  max detour: {s.max_detour}"
    )
    print("PASS" if t2 - t0 < 10 else "FAIL", "(target < 10 s)")


if __name__ == "__main__":
    main()
