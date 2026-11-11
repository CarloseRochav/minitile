"""YAML -> Design, with schema and semantic validation (Section 5).

All errors are collected and raised together as a single ``DesignError``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from minitile.geometry import inside_die, overlap_area, violates_halo
from minitile.model import Design, Die, Module, Net, PosInt


class DesignError(Exception):
    """Raised when a design is invalid. ``errors`` holds every problem found."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("invalid design:\n" + "\n".join(f"  - {e}" for e in self.errors))


class _Reach(BaseModel):
    reach_per_cycle: PosInt


def _fmt_pydantic(prefix: str, exc: ValidationError) -> list[str]:
    out = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        where = f"{prefix}.{loc}" if loc else prefix
        out.append(f"{where}: {err['msg']}")
    return out


def _label(raw: Any, kind: str, index: int) -> str:
    if kind == "modules" and isinstance(raw, dict) and isinstance(raw.get("name"), str):
        return f"module '{raw['name']}'"
    if kind == "nets" and isinstance(raw, dict):
        return f"net #{index} ({raw.get('from')}->{raw.get('to')})"
    return f"{kind}[{index}]"


def validate_data(data: Any, name: str = "design") -> Design:
    """Validate a parsed YAML mapping and return a ``Design``, or raise ``DesignError``."""
    errors: list[str] = []
    if not isinstance(data, dict):
        raise DesignError(
            ["top level: expected a mapping with die, reach_per_cycle, modules, nets"]
        )

    allowed = {"die", "reach_per_cycle", "modules", "nets"}
    for key in sorted(set(data) - allowed, key=str):
        errors.append(f"top level: unknown field '{key}'")

    # -- 1. schema, piece by piece so that every error is collected
    die: Die | None = None
    if "die" not in data:
        errors.append("die: field required")
    else:
        try:
            die = Die.model_validate(data["die"])
        except ValidationError as e:
            errors.extend(_fmt_pydantic("die", e))

    reach: int | None = None
    if "reach_per_cycle" not in data:
        errors.append("reach_per_cycle: field required")
    else:
        try:
            reach = _Reach.model_validate(
                {"reach_per_cycle": data["reach_per_cycle"]}
            ).reach_per_cycle
        except ValidationError as e:
            errors.extend(_fmt_pydantic("top level", e))

    def items(kind: str) -> list[Any]:
        raw = data.get(kind)
        if raw is None:
            errors.append(f"{kind}: field required")
            return []
        if not isinstance(raw, list):
            errors.append(f"{kind}: expected a list")
            return []
        return raw

    modules: list[Module] = []
    for i, raw in enumerate(items("modules")):
        try:
            modules.append(Module.model_validate(raw))
        except ValidationError as e:
            errors.extend(_fmt_pydantic(_label(raw, "modules", i), e))

    nets: list[Net] = []
    for i, raw in enumerate(items("nets")):
        try:
            nets.append(Net.model_validate(raw))
        except ValidationError as e:
            errors.extend(_fmt_pydantic(_label(raw, "nets", i), e))

    # -- 2. duplicate module names
    seen: set[str] = set()
    for m in modules:
        if m.name in seen:
            errors.append(f"module '{m.name}': duplicate module name")
        seen.add(m.name)

    # -- 8. rotation
    for m in modules:
        if m.rotatable:
            errors.append(f"module '{m.name}': rotation not supported in Phase 1")

    if die is not None:
        # -- 3. module larger than die
        for m in modules:
            if m.w > die.width or m.h > die.height:
                errors.append(
                    f"module '{m.name}': size {m.w}x{m.h} larger than die {die.width}x{die.height}"
                )
        # -- 4. fixed module outside die
        fixed = [m for m in modules if m.fixed is not None]
        for m in fixed:
            assert m.fixed is not None
            if not inside_die(m.rect_at(m.fixed), die.width, die.height):
                errors.append(f"module '{m.name}': fixed position {list(m.fixed)} outside die")
        # -- 5. fixed modules overlapping or violating halo
        for i, a in enumerate(fixed):
            for b in fixed[i + 1 :]:
                assert a.fixed is not None and b.fixed is not None
                ra, rb = a.rect_at(a.fixed), b.rect_at(b.fixed)
                if overlap_area(ra, rb) > 0:
                    errors.append(f"fixed modules '{a.name}' and '{b.name}' overlap")
                elif violates_halo(ra, rb, die.halo):
                    errors.append(
                        f"fixed modules '{a.name}' and '{b.name}' violate halo {die.halo}"
                    )
        # -- 9. total area
        total = sum(m.w * m.h for m in modules)
        if total > die.width * die.height:
            errors.append(
                f"design cannot fit: total module area {total} > die area {die.width * die.height}"
            )

    # -- 6. unknown modules, 7. self loops (10. duplicate nets are allowed)
    for i, n in enumerate(nets):
        label = f"net #{i} ({n.src}->{n.dst})"
        for end in (n.src, n.dst):
            if end not in seen:
                errors.append(f"{label}: unknown module '{end}'")
        if n.src == n.dst:
            errors.append(f"{label}: self-loop net")

    if errors:
        raise DesignError(errors)
    assert die is not None and reach is not None
    return Design(name=name, die=die, reach_per_cycle=reach, modules=modules, nets=nets)


def parse_design(text: str, name: str = "design") -> Design:
    """Parse YAML text into a validated ``Design``."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise DesignError([f"YAML syntax error: {e}"]) from e
    return validate_data(data, name)


def load_design(path: str | Path) -> Design:
    """Load and validate a design file. The design name is the file stem."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise DesignError([f"cannot read {p}: {e}"]) from e
    return parse_design(text, name=p.stem)
