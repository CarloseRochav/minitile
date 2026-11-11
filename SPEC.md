# minitile — Phase 1 Spec

> A learning project inspired by physical-aware floorplanning (e.g. Qualcomm's Physical Aware Tiling).
> It places rectangular chip modules on a grid, routes data paths between them, and reports
> wirelength, detours and pipeline stages. It is a simplified model, not a real EDA tool.

---

## 0. How to use this spec (instructions for Claude Code)

- Implement **Phase 1 only**. Sections marked *Out of scope* must not be built.
- Work in the order of **Section 10 (Implementation steps)**. Each step ends with passing tests,
  `ruff check`, `ruff format --check` and `mypy --strict` clean, and one commit.
- Formulas and definitions in this spec are the source of truth. If something is ambiguous or seems
  wrong, **stop and ask** instead of guessing or silently changing the definition.
- Prefer small, pure functions. No global state. All randomness goes through a seeded `random.Random`.
- Do not add dependencies beyond Section 2 without asking.

---

## 1. Goal

Given a YAML description of a die (chip area), modules (rectangles) and nets (data paths):

1. Validate the input.
2. Place movable modules legally (no overlaps, inside the die, spacing respected),
   minimizing weighted wirelength and pipeline stages.
3. Route each net on the grid with A\*, avoiding modules.
4. Compute per-net metrics (length, Manhattan lower bound, detour ratio, pipeline stages) and a summary.
5. Output a JSON result and a readable table.

### Out of scope for Phase 1
- SVG/HTML rendering, web GUI, FastAPI, MCP server, testcase extraction (Phases 2–4).
- Net-to-net congestion (routes do not block each other).
- Module rotation (field exists in the model, but must be rejected by validation if `true`).
- Timing models beyond the simple `reach_per_cycle` rule.

---

## 2. Tech stack

| Purpose | Tool |
|---|---|
| Language | Python 3.12 |
| Project / env | `uv` |
| Data model + validation | `pydantic` v2 |
| YAML | `pyyaml` (`safe_load` only) |
| CLI | `typer` |
| Tables | `rich` |
| Tests | `pytest`, `hypothesis` |
| Lint / format | `ruff` |
| Types | `mypy --strict` |
| A\* priority queue | stdlib `heapq` |

---

## 3. Project structure

```
minitile/
├── pyproject.toml
├── README.md
├── SPEC.md                    # this file
├── src/minitile/
│   ├── __init__.py
│   ├── model.py               # Die, Module, Net, Design, Placement, results (pydantic)
│   ├── geometry.py            # Rect ops: cells, overlap, gap distance, adjacency
│   ├── parser.py              # YAML -> Design, semantic validation
│   ├── cost.py                # cost function (fast, Manhattan-based)
│   ├── placer.py              # greedy initial placement + simulated annealing + legality check
│   ├── router.py              # grid A*
│   ├── metrics.py             # per-net + summary metrics
│   ├── api.py                 # high-level Floorplan API
│   └── cli.py                 # typer app
├── testcases/                 # example designs (YAML) + golden results
│   ├── tiny_2modules.yaml
│   ├── blocked_route.yaml
│   ├── unroutable.yaml
│   ├── chain_5.yaml
│   └── star_noc.yaml
├── tests/
│   ├── test_geometry.py
│   ├── test_parser.py
│   ├── test_cost.py
│   ├── test_placer.py
│   ├── test_router.py
│   ├── test_metrics.py
│   ├── test_cli.py
│   └── test_properties.py     # hypothesis
└── .github/workflows/ci.yml
```

---

## 4. Coordinate system and geometry

- Integer grid. Origin `(0, 0)` is the **bottom-left** cell. `x` grows right, `y` grows up.
- The die has cells `x ∈ [0, width-1]`, `y ∈ [0, height-1]`.
- A module placed at `(x, y)` with size `(w, h)` occupies cells
  `x .. x+w-1` and `y .. y+h-1` (its `(x, y)` is the lower-left cell).
- **Inside die:** `x >= 0`, `y >= 0`, `x + w <= die.width`, `y + h <= die.height`.
- **Overlap area** of two modules: area of the intersection of their footprints (0 if disjoint).
- **Gap distance** between modules A and B, measured between their nearest cells:

  ```
  dx = max(0, B.x - (A.x + A.w - 1), A.x - (B.x + B.w - 1))
  dy = max(0, B.y - (A.y + A.h - 1), A.y - (B.y + B.h - 1))
  manhattan(A, B) = dx + dy
  ```
  Examples: A cells x 1..3, B cells x 10..12, y ranges overlap → `manhattan = 7`.
  Overlapping footprints → `0`.

- **Halo (spacing):** `die.halo` (default `1`) is the number of empty cells required between any
  two modules. Two modules violate halo if the empty gap between them is smaller than `halo`
  on the axis where they are separated. Equivalent rule: expand each footprint by `halo` cells on every
  side and check for overlap with the *other unexpanded* footprint.
  Halo applies only between modules, not between modules and the die edge.

---

## 5. Input format (YAML)

```yaml
die:
  width: 40           # int > 0
  height: 40          # int > 0
  halo: 1             # int >= 0, default 1
reach_per_cycle: 12   # int > 0: max route length a signal travels in one clock cycle

modules:
  - { name: cpu,   w: 8,  h: 8, fixed: [2, 2] }   # fixed position (lower-left), never moved
  - { name: gpu,   w: 10, h: 8 }                    # movable
  - { name: dsp,   w: 6,  h: 6 }
  - { name: modem, w: 8,  h: 6 }
  - { name: noc,   w: 4,  h: 4 }
  # optional field: rotatable: false  (must be false in Phase 1)

nets:
  - { from: cpu, to: noc,   width: 128 }   # width = bus width in bits, int > 0
  - { from: gpu, to: noc,   width: 256 }
  - { from: dsp, to: modem, width: 64 }
  - { from: noc, to: modem, width: 64 }
```

### Validation rules (`parser.py`)
Each failure raises `DesignError` with a clear message naming the offending item.
Collect **all** errors and report them together (do not stop at the first).

1. Schema/type errors (pydantic): missing fields, non-int values, non-positive sizes/widths/reach, `halo < 0`.
2. Duplicate module names.
3. A module larger than the die (`w > width` or `h > height`).
4. A fixed module outside the die.
5. Two fixed modules overlapping or violating halo.
6. A net referencing an unknown module.
7. A self-loop net (`from == to`).
8. `rotatable: true` → "rotation not supported in Phase 1".
9. Total module area > die area → "design cannot fit".
10. Duplicate nets (same unordered pair) are **allowed**; their widths are summed for cost purposes.

---

## 6. Placement (`cost.py`, `placer.py`)

### 6.1 Cost function (fast, used during annealing)

```
cost = Σ_nets  w_net · manhattan(from, to)
     + λ_overlap · Σ_pairs overlap_area(a, b)
     + λ_halo    · Σ_pairs halo_violation(a, b)
     + λ_pipe    · Σ_nets  stages_est(net)

w_net         = net.width / 64
stages_est    = max(0, ceil(manhattan(from, to) / reach_per_cycle) - 1)
halo_violation(a, b) = overlap area between a expanded by halo and b, minus overlap_area(a, b)
```

Default weights: `λ_overlap = 1000`, `λ_halo = 200`, `λ_pipe = 50`. Exposed as parameters.

Requirements:
- `cost.py` must provide a function for the **full** cost and a function for the **delta** caused by
  moving or swapping modules, recomputing only the affected nets and pairs. A test must verify that
  `full(after) - full(before) == delta` for random moves.

### 6.2 Greedy initial placement
1. Place fixed modules at their given positions.
2. Sort movable modules by total connected net weight (desc), break ties by area (desc), then name.
3. For each module, scan candidate positions on a stride of `max(1, min(w, h) // 2)` over the die,
   and choose the **legal** position (inside die, no overlap, no halo violation with already placed
   modules) with the lowest partial cost (nets to already placed modules only).
4. If no legal position exists, choose the position with minimal partial cost including overlap penalties.

### 6.3 Simulated annealing
- Moves (chosen at random, probabilities configurable):
  - **translate** (70%): move one movable module by a random offset in `[-r, r]` on each axis,
    clamped to the die. `r` starts at `max(die.width, die.height) // 2` and shrinks linearly with
    temperature progress down to `1`.
  - **swap** (30%): swap the lower-left positions of two movable modules, clamped to the die.
- Initial temperature: sample 200 random moves from the greedy placement, take the mean of the
  positive deltas `d̄`, set `T0 = -d̄ / ln(0.8)` (≈80% initial acceptance of worsening moves).
  If no positive deltas, `T0 = 1`.
- Cooling: geometric, `T_k = T0 · α^k` with `α` chosen so that `T` reaches `T0 · 1e-4`
  at the final iteration.
- Accept if `delta <= 0`, else with probability `exp(-delta / T)`.
- Keep track of the **best** placement seen. Return the best one.
- Parameters: `iterations` (default 20 000), `seed` (default 0).
- **Determinism:** same design + same parameters + same seed → byte-identical JSON output.

### 6.4 Legality
After annealing, check the final placement: inside die, no overlap, no halo violation.
`PlacementResult.legal` is `false` if any check fails, with a list of violations.
Do **not** auto-fix in Phase 1. The CLI exits with code `2` if the placement is illegal.

---

## 7. Routing (`router.py`)

- Grid = die cells. A cell is **blocked** if it belongs to any module footprint.
  Halo cells are free (halo exists to leave routing space).
- A net from A to B is a path of 4-connected steps from a cell of A's footprint to a cell of B's
  footprint, where all intermediate cells are free.
- **Route length** = number of steps in that path.
  - Implementation: multi-source A\*. Start set = free cells 4-adjacent to A, each with `g = 1`.
    Goal = any free cell 4-adjacent to B; final length = `g + 1`.
  - Special case: if A and B footprints are 4-adjacent (only possible with `halo = 0`), length = `1`.
  - Heuristic: Manhattan distance from the cell to B's footprint (admissible).
  - Tie-breaking must be deterministic (e.g. heap key `(f, h, x, y)`).
- Nets are routed independently (no congestion). Route nets in order of width desc, then name pair,
  so output order is stable.
- If no path exists: status `unroutable`, length `null`.
- Return the path as a list of `[x, y]` cells (excluding module cells) for later rendering.

---

## 8. Metrics (`metrics.py`)

Per net:

| Field | Definition |
|---|---|
| `from`, `to`, `width` | from input |
| `manhattan` | gap distance (Section 4) at final placement |
| `length` | route length (Section 7), or `null` if unroutable |
| `detour` | `length / manhattan`, rounded to 3 decimals. If `manhattan == 0` → `1.0`. `null` if unroutable |
| `pipeline_stages` | `max(0, ceil(length / reach_per_cycle) - 1)`, `null` if unroutable |
| `status` | `ok`, `detour_warning` (detour > 1.3), or `unroutable` |
| `path` | list of cells |

Summary:

| Field | Definition |
|---|---|
| `legal` | from placement |
| `violations` | list of strings |
| `cost_initial`, `cost_final` | greedy vs best annealed cost |
| `total_weighted_length` | Σ `w_net · length` over routed nets |
| `total_pipeline_stages` | Σ over routed nets |
| `max_detour` | max over routed nets |
| `unroutable_count` | count |
| `seed`, `iterations` | run parameters |

---

## 9. Interfaces

### 9.1 Python API (`api.py`)
```python
from minitile import Floorplan

fp = Floorplan.load("testcases/chain_5.yaml")
result = fp.place(seed=42, iterations=20_000).route().report()
result.to_json("out.json")
print(result.summary.max_detour)
```
`place()` and `route()` return a new object or `self` (choose one and be consistent). `route()` before
`place()` raises a clear error.

### 9.2 CLI (`cli.py`)
```
minitile validate DESIGN.yaml
minitile run DESIGN.yaml [--seed 0] [--iterations 20000] [--out result.json]
minitile report result.json
```
- `validate`: prints `OK` or all errors; exit code `0` / `1`.
- `run`: validate → place → route → metrics; writes JSON if `--out`, prints a rich table always.
  Exit codes: `0` ok, `1` invalid design, `2` illegal placement, `3` one or more unroutable nets.
- `report`: prints the table from a saved JSON.

Table example:
```
Placement cost: 1,842 → 1,107 (−40%)  legal: yes  seed: 42  iterations: 20,000
Net          Width  Length  Manhattan  Detour  Stages  Status
gpu→noc        256       9          9   1.000       0  ok
cpu→noc        128      14         12   1.167       1  ok
dsp→modem       64      22         16   1.375       1  detour_warning
noc→modem       64      11         11   1.000       0  ok
```

### 9.3 JSON output
```json
{
  "design": "chain_5",
  "params": { "seed": 42, "iterations": 20000, "lambda_overlap": 1000, "lambda_halo": 200, "lambda_pipe": 50 },
  "placement": { "cpu": [2, 2], "gpu": [14, 3] },
  "nets": [ { "from": "gpu", "to": "noc", "width": 256, "manhattan": 9, "length": 9,
              "detour": 1.0, "pipeline_stages": 0, "status": "ok", "path": [[12, 5], [13, 5]] } ],
  "summary": { "legal": true, "violations": [], "cost_initial": 1842.0, "cost_final": 1107.0,
               "total_weighted_length": 0.0, "total_pipeline_stages": 0, "max_detour": 1.0,
               "unroutable_count": 0 }
}
```
Keys sorted, floats rounded to 3 decimals, so golden files are stable.

---

## 10. Implementation steps

| # | Step | Done when |
|---|---|---|
| 1 | Scaffold: `uv` project, ruff, mypy strict, pytest, CI workflow (lint + types + tests on push) | CI green on an empty test |
| 2 | `model.py` + `geometry.py` | geometry tests pass (Section 11.1) |
| 3 | `parser.py` + validation | parser tests pass (11.2) |
| 4 | `cost.py` full + delta | cost tests pass, including delta == full difference (11.3) |
| 5 | `placer.py` greedy + annealing + legality | placer tests pass (11.4) |
| 6 | `router.py` | router tests pass with the exact expected values (11.5) |
| 7 | `metrics.py` + `api.py` | metrics tests pass (11.6) |
| 8 | `cli.py` | CLI tests pass (11.7) |
| 9 | Testcases + golden results + property tests | 11.8, 11.9 pass |
| 10 | README: what it is, limitations, how to run, one example table | reviewed by me |

---

## 11. Tests

### 11.1 Geometry
- Cells of a 3×2 module at (1,1) are exactly `{(1,1),(2,1),(3,1),(1,2),(2,2),(3,2)}`.
- `manhattan`: A at (1,1) 3×3, B at (10,1) 3×3 → `7`. Diagonal case: A (0,0) 2×2, B (5,5) 2×2 → `4 + 4 = 8`. Overlapping → `0`.
- `overlap_area`: identical modules → `w·h`; touching edges → `0`.
- Halo: modules with gap 0 and halo 1 → violation; gap 1 and halo 1 → no violation.

### 11.2 Parser — one test per rule in Section 5, plus:
- An input with three different errors reports all three.
- The example YAML in Section 5 parses with no errors.

### 11.3 Cost
- Hand-computed cost for `tiny_2modules` matches.
- For 500 random moves on `chain_5` (seeded), `delta` equals `full(after) - full(before)` within `1e-9`.

### 11.4 Placer
- Fixed modules never move.
- `cost_final <= cost_initial`.
- Same seed → identical placement; different seeds may differ.
- `chain_5` and `star_noc` produce `legal: true` with default parameters.

### 11.5 Router — exact expected values

**`tiny_2modules.yaml`**
```yaml
die: { width: 20, height: 10, halo: 1 }
reach_per_cycle: 12
modules:
  - { name: a, w: 3, h: 3, fixed: [1, 1] }
  - { name: b, w: 3, h: 3, fixed: [10, 1] }
nets:
  - { from: a, to: b, width: 64 }
```
Expected: `manhattan = 7`, `length = 7`, `detour = 1.0`, `pipeline_stages = 0`, `status = ok`.

**`blocked_route.yaml`** (a wall forces a detour)
```yaml
die: { width: 30, height: 20, halo: 1 }
reach_per_cycle: 12
modules:
  - { name: a,    w: 4, h: 4,  fixed: [2, 8] }
  - { name: b,    w: 4, h: 4,  fixed: [24, 8] }
  - { name: wall, w: 2, h: 16, fixed: [14, 2] }
nets:
  - { from: a, to: b, width: 64 }
```
The wall occupies y 2..17, so the route must pass at y ≥ 18 (shortest) or y ≤ 1.
Expected: `manhattan = 19`, `length = 33` (19 horizontal + 7 up + 7 down), `detour = 1.737`,
`pipeline_stages = 2`, `status = detour_warning`.

**`unroutable.yaml`** (b is fully enclosed; needs `halo: 0`)
```yaml
die: { width: 20, height: 20, halo: 0 }
reach_per_cycle: 12
modules:
  - { name: a,      w: 2, h: 2, fixed: [1, 1] }
  - { name: b,      w: 2, h: 2, fixed: [10, 10] }
  - { name: bottom, w: 4, h: 1, fixed: [9, 9] }
  - { name: top,    w: 4, h: 1, fixed: [9, 12] }
  - { name: left,   w: 1, h: 2, fixed: [9, 10] }
  - { name: right,  w: 1, h: 2, fixed: [12, 10] }
nets:
  - { from: a, to: b, width: 64 }
```
Expected: `status = unroutable`, `length = null`; CLI `run` exits with code `3`.

- Adjacent modules with `halo: 0` → `length = 1`.
- Every returned path is 4-connected and contains no module cells.

### 11.6 Metrics
- `manhattan == 0` → `detour = 1.0`.
- Pipeline stages: reach 12 → lengths 12 → 0, 13 → 1, 24 → 1, 25 → 2.
- Summary totals match hand-computed values on `blocked_route`.

### 11.7 CLI (via `typer.testing.CliRunner`)
- `validate` on a valid / invalid file → exit codes 0 / 1.
- `run` exit codes 0, 1, 2, 3 (build a small illegal case for 2 using a tiny `iterations` value
  or an over-packed design that still passes the area check).
- `run --out` writes JSON matching Section 9.3 keys; `report` reads it back.

### 11.8 Golden regression
- `chain_5.yaml`: 5 modules in a chain (`m1→m2→m3→m4→m5`), die 40×40, one fixed module.
- `star_noc.yaml`: the Section 5 example.
- Generate `testcases/<name>.golden.json` with `--seed 42`, commit it. A test reruns and compares
  the JSON exactly. Regenerating goldens requires an explicit command (`pytest --update-golden`
  or a script), never automatic.

### 11.9 Property tests (hypothesis, small designs: ≤ 8 modules, die ≤ 30×30, module area ≤ 40% of die)
- For every routed net: `length >= manhattan` and `detour >= 1`.
- Fixed modules are unchanged after placement.
- Output is deterministic for a given seed.
- `cost_final <= cost_initial`.

---

## 12. Acceptance criteria for Phase 1

- [ ] All tests pass in CI; ruff and `mypy --strict` clean.
- [ ] Exact router values in 11.5 match.
- [ ] `minitile run testcases/star_noc.yaml --seed 42` prints the table and finishes in < 2 s.
- [ ] A generated design with 30 modules and 60 nets on a 100×100 die finishes 20 000 iterations
      plus routing in < 10 s on a laptop (add a benchmark script, not a CI test).
- [ ] README explains the model, its limitations (no congestion, no real timing, no power grid,
      grid abstraction), and how it relates to physical-aware floorplanning.

## 13. Known limitations (state these in the README)
- Routes do not compete for space (no congestion), so real detours would be larger.
- Timing is a single "reach per cycle" number; real timing depends on wire RC, buffers and corners.
- No power grid, no pins on specific module edges, no multi-pin nets.
- Grid units are abstract, not microns.
