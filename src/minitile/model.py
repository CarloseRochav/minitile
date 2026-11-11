"""Pydantic data models: input design and results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from minitile.geometry import Rect

PosInt = Annotated[StrictInt, Field(gt=0)]
NonNegInt = Annotated[StrictInt, Field(ge=0)]

Position = tuple[int, int]
Placement = dict[str, Position]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Die(_Base):
    width: PosInt
    height: PosInt
    halo: NonNegInt = 1


class Module(_Base):
    name: str
    w: PosInt
    h: PosInt
    fixed: tuple[StrictInt, StrictInt] | None = None
    rotatable: StrictBool = False

    def rect_at(self, pos: Position) -> Rect:
        return Rect(pos[0], pos[1], self.w, self.h)


class Net(_Base):
    src: str = Field(alias="from")
    dst: str = Field(alias="to")
    width: PosInt

    @property
    def weight(self) -> float:
        return self.width / 64


class Design(_Base):
    name: str = "design"
    die: Die
    reach_per_cycle: PosInt
    modules: list[Module]
    nets: list[Net]

    def module(self, name: str) -> Module:
        for m in self.modules:
            if m.name == name:
                return m
        raise KeyError(name)


# ---------------------------------------------------------------- results

NetStatus = Literal["ok", "detour_warning", "unroutable"]


class PlacementResult(_Base):
    placement: Placement
    legal: bool
    violations: list[str]
    cost_initial: float
    cost_final: float
    seed: int
    iterations: int


class RouteResult(_Base):
    src: str = Field(alias="from")
    dst: str = Field(alias="to")
    width: int
    length: int | None
    path: list[tuple[int, int]]


class NetMetrics(_Base):
    src: str = Field(alias="from")
    dst: str = Field(alias="to")
    width: int
    manhattan: int
    length: int | None
    detour: float | None
    pipeline_stages: int | None
    status: NetStatus
    path: list[tuple[int, int]]


class Summary(_Base):
    legal: bool
    violations: list[str]
    cost_initial: float
    cost_final: float
    total_weighted_length: float
    total_pipeline_stages: int
    max_detour: float | None
    unroutable_count: int
    seed: int
    iterations: int


class Params(_Base):
    seed: int
    iterations: int
    lambda_overlap: float
    lambda_halo: float
    lambda_pipe: float


def _round_floats(obj: Any) -> Any:
    if isinstance(obj, float):
        return round(obj, 3) + 0.0  # + 0.0 normalises -0.0
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_round_floats(v) for v in obj]
    return obj


class Result(_Base):
    design: str
    params: Params
    placement: Placement
    nets: list[NetMetrics]
    summary: Summary

    def to_dict(self) -> dict[str, Any]:
        rounded: dict[str, Any] = _round_floats(self.model_dump(mode="json", by_alias=True))
        return rounded

    def to_json_str(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2) + "\n"

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json_str(), encoding="utf-8", newline="\n")

    @classmethod
    def from_json(cls, path: str | Path) -> Result:
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
