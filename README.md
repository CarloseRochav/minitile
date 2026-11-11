# minitile

A small learning project inspired by **physical-aware floorplanning**, for example Qualcomm's
Physical Aware Tiling. Given a die, a set of rectangular chip modules and the data paths (nets)
between them, minitile:

1. validates the design,
2. **places** the movable modules legally (inside the die, no overlaps, spacing respected),
   minimizing weighted wirelength and pipeline stages,
3. **routes** every net on a grid with A\*, going around modules,
4. reports per-net **length, Manhattan lower bound, detour ratio and pipeline stages**.

It is a simplified model and **not a real EDA tool**. See [SPEC.md](SPEC.md) for the exact
definitions.

## How it relates to physical-aware floorplanning

In a real SoC, where blocks sit on the die decides how long the wires between them are. Long
wires need pipeline registers (extra clock cycles of latency), and wires that have to detour
around other blocks are longer than the straight-line estimate suggests. Physical-aware
floorplanning brings these physical effects into early architecture decisions instead of
discovering them late in implementation.

minitile models a few of these effects:

| Real-world concept | minitile model |
|---|---|
| Block placement | Rectangles on an integer grid; simulated annealing over a Manhattan-based cost |
| Keep-out / channel spacing | `halo`: empty cells required between modules (used as routing space) |
| Wire length | Grid A\* route length between module footprints |
| Detours around blocks | `detour = length / manhattan`; anything above 1.3 is flagged as `detour_warning` |
| Timing closure / pipelining | `reach_per_cycle`: stages = `max(0, ceil(length / reach) - 1)` |
| Bus width | Net `width` (bits) scales the wirelength cost (`width / 64`) |

## Install and run

Requires [uv](https://docs.astral.sh/uv/). uv downloads Python 3.12 if needed.

```bash
uv sync
uv run minitile validate testcases/star_noc.yaml
uv run minitile run testcases/star_noc.yaml --seed 42 --out result.json
uv run minitile report result.json
```

`run` exit codes: `0` ok, `1` invalid design, `2` illegal placement, `3` one or more unroutable nets.

Python API (every step returns a new, immutable `Floorplan`):

```python
from minitile import Floorplan

fp = Floorplan.load("testcases/chain_5.yaml")
result = fp.place(seed=42, iterations=20_000).route().report()
result.to_json("out.json")
print(result.summary.max_detour)
```

### Example

`testcases/blocked_route.yaml` puts a wall between two modules, so the route has to go over it:

```
$ uv run minitile run testcases/blocked_route.yaml --seed 42
Placement cost: 69 → 69 (+0%)  legal: yes  seed: 42  iterations: 20,000

 Net   Width   Length   Manhattan   Detour   Stages   Status
 ───────────────────────────────────────────────────────────────────
 a→b      64       33          19    1.737        2   detour_warning

Total weighted length: 33.000  pipeline stages: 2  max detour: 1.737  unroutable: 0
```

On consoles that can't show `→` and `−` (e.g. Windows cp1252), the table falls back to `->`
and `-`.

## Input format

```yaml
die: { width: 40, height: 40, halo: 1 }
reach_per_cycle: 12
modules:
  - { name: cpu, w: 8,  h: 8, fixed: [2, 2] }   # fixed lower-left position
  - { name: gpu, w: 10, h: 8 }                  # movable
  - { name: noc, w: 4,  h: 4 }
nets:
  - { from: cpu, to: noc, width: 128 }
  - { from: gpu, to: noc, width: 256 }
```

Every validation error is reported at once (duplicate names, unknown modules, self-loops,
fixed modules overlapping, total area too large, ...).

## Development

```bash
uv run pytest                     # all tests (unit, golden, hypothesis property tests)
uv run pytest --update-golden     # regenerate testcases/*.golden.json (explicit only)
uv run ruff check && uv run ruff format --check
uv run mypy --strict
uv run python scripts/benchmark.py   # 30 modules / 60 nets / 100x100, target < 10 s
```

Layout: `src/minitile/` holds `model`, `geometry`, `parser`, `cost`, `placer`, `router`,
`metrics`, `api` and `cli`. Tests are in `tests/` and example designs in `testcases/`.

### Implementation notes

- **Halo penalty is symmetric.** The spec's `halo_violation(a, b)` (expand `a`, intersect with
  `b`) depends on argument order when the modules differ in size. minitile uses
  `hv(a, b) + hv(b, a)` for each unordered pair.
- **Duplicate nets** (same unordered pair) are merged for the cost by summing widths. Each one
  is still routed and reported separately.
- **Overlapping footprints** (only possible in an illegal placement) get route length `0`.
  4-adjacent footprints get length `1`.
- **Determinism:** all randomness goes through one seeded `random.Random`, and JSON keys are
  sorted with floats rounded to 3 decimals. The same design, parameters and seed give
  byte-identical JSON.
- If annealing never improves on the greedy placement, the greedy placement is returned, so
  `cost_final <= cost_initial` always holds.

## Limitations

- **No congestion:** routes do not compete for space, so real detours would be larger.
- **No real timing:** timing is a single "reach per cycle" number. Real timing depends on wire
  RC, buffering, process corners and so on.
- **No power grid**, no pins on specific module edges, no multi-pin nets, no module rotation.
- **Grid abstraction:** units are abstract grid cells, not microns.
- Illegal placements are reported, not repaired (CLI exit code `2`).
