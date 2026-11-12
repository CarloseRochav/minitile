"""SVG rendering of a placed-and-routed result (SPEC Section 14). Stdlib only.

Output is deterministic: same Result -> byte-identical SVG (no timestamps, no random ids,
all coordinates rounded to at most 2 decimals).
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from minitile.geometry import Cell, Rect, neighbors_of_rect
from minitile.metrics import percent_change
from minitile.model import Layout, NetMetrics, Result

# Okabe-Ito colorblind-safe palette (status is also encoded by dash pattern, not color alone).
COLOR_OK = "#0072B2"  # blue
COLOR_WARNING = "#E69F00"  # orange
COLOR_UNROUTABLE = "#D55E00"  # vermillion
COLOR_MOVABLE_FILL = "#D6ECF8"  # light tint of sky blue #56B4E9
COLOR_MOVABLE_STROKE = "#0072B2"
COLOR_FIXED_FILL = "#C8C8C8"
COLOR_FIXED_HATCH = "#6E6E6E"
COLOR_FIXED_STROKE = "#3C3C3C"
COLOR_TEXT = "#111111"
COLOR_GRID = "#E4E4E4"
COLOR_DIE = "#333333"

DASH = {"ok": None, "detour_warning": "8 4", "unroutable": "2 5"}
COLOR = {"ok": COLOR_OK, "detour_warning": COLOR_WARNING, "unroutable": COLOR_UNROUTABLE}

PAD = 16
TITLE_H = 80
LEGEND_GAP = 14
LEGEND_ITEM_W = 170
LEGEND_ROW_H = 22
LEGEND_COLS = 3
CHAR_W = 0.62  # average glyph width as a fraction of the font size (sans-serif)
MAX_FONT = 12.0
MIN_FONT = 5.0


def fmt(x: float) -> str:
    """Number with at most 2 decimals and no trailing zeros (deterministic text)."""
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def svg_y(y: int, h: int, die_height: int, cell: int) -> int:
    """SVG top edge (origin top-left) of a grid rect at ``y``, height ``h`` (origin bottom-left)."""
    return (die_height - y - h) * cell


def stroke_width(bus_width: int) -> float:
    """1..4 px by log2(bus width): 32 -> 1, 64 -> 1.75, 128 -> 2.5, 256 -> 3.25, 512 -> 4."""
    return round(min(4.0, max(1.0, 1.0 + (math.log2(bus_width) - 5) * 0.75)), 2)


def label_font(name: str, w_px: float, h_px: float) -> tuple[float, bool] | None:
    """Font size and rotation for a centered label that fits inside the block, or None."""
    n = max(1, len(name))
    aw, ah = w_px - 4, h_px - 4
    horizontal = min(MAX_FONT, aw / (CHAR_W * n), ah)
    vertical = min(MAX_FONT, ah / (CHAR_W * n), aw)
    size, rotated = (vertical, True) if vertical > horizontal * 1.15 else (horizontal, False)
    if size < MIN_FONT:
        return None
    return round(math.floor(size * 100) / 100, 2), rotated


def stage_marker_cells(net: NetMetrics, reach: int) -> list[Cell]:
    """Cells reached after k*reach steps from the source footprint, k = 1..stages."""
    stages = net.pipeline_stages or 0
    cells: list[Cell] = []
    for k in range(1, stages + 1):
        i = k * reach - 1  # step 1 lands on path[0]
        if 0 <= i < len(net.path):
            cells.append((net.path[i][0], net.path[i][1]))
    return cells


class _Canvas:
    def __init__(self, layout: Layout, placement: dict[str, tuple[int, int]], cell: int) -> None:
        self.layout = layout
        self.cell = cell
        self.H = layout.die.height
        self.rects = {
            name: Rect(placement[name][0], placement[name][1], m.w, m.h)
            for name, m in layout.modules.items()
        }

    def point(self, gx: float, gy: float) -> tuple[float, float]:
        """Grid coordinates (float, origin bottom-left) -> SVG pixels inside the die group."""
        return gx * self.cell, (self.H - gy) * self.cell

    def center_of_cell(self, c: Cell) -> tuple[float, float]:
        return self.point(c[0] + 0.5, c[1] + 0.5)

    def center_of_rect(self, r: Rect) -> tuple[float, float]:
        return self.point(r.x + r.w / 2, r.y + r.h / 2)

    def edge_point(self, c: Cell, r: Rect) -> tuple[float, float]:
        """Midpoint of the edge between free cell ``c`` and its neighbouring cell in ``r``."""
        nx = min(max(c[0], r.x), r.x2)
        ny = min(max(c[1], r.y), r.y2)
        return self.point((c[0] + nx) / 2 + 0.5, (c[1] + ny) / 2 + 0.5)

    def route_points(self, net: NetMetrics) -> list[tuple[float, float]]:
        a, b = self.rects[net.src], self.rects[net.dst]
        if net.path:
            pts = [self.edge_point(net.path[0], a)]
            pts += [self.center_of_cell((c[0], c[1])) for c in net.path]
            pts.append(self.edge_point(net.path[-1], b))
            return pts
        # adjacent footprints (length 1): connect the middle pair of touching cells
        touching = [c for c in neighbors_of_rect(a, 10**9, 10**9) if _inside(c, b)]
        if touching:
            cb = touching[len(touching) // 2]
            ca = (min(max(cb[0], a.x), a.x2), min(max(cb[1], a.y), a.y2))
            return [self.center_of_cell(ca), self.center_of_cell(cb)]
        # overlapping footprints (illegal placement) or unroutable: straight center-to-center
        return [self.center_of_rect(a), self.center_of_rect(b)]


def _inside(c: Cell, r: Rect) -> bool:
    return r.x <= c[0] <= r.x2 and r.y <= c[1] <= r.y2


def _pts(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{fmt(x)},{fmt(y)}" for x, y in points)


def _diamond(cx: float, cy: float, r: float, cls: str) -> str:
    d = (
        f"M{fmt(cx)},{fmt(cy - r)} L{fmt(cx + r)},{fmt(cy)} "
        f"L{fmt(cx)},{fmt(cy + r)} L{fmt(cx - r)},{fmt(cy)} Z"
    )
    return f'<path class="{cls}" d="{d}" fill="#000000" stroke="#FFFFFF" stroke-width="1"/>'


def _route_style(status: str, width: int) -> str:
    dash = DASH[status]
    style = (
        f'fill="none" stroke="{COLOR[status]}" stroke-width="{fmt(stroke_width(width))}" '
        'stroke-linejoin="round" stroke-linecap="round"'
    )
    return style + (f' stroke-dasharray="{dash}"' if dash else "")


def render_svg(result: Result, cell: int = 10) -> str:
    """Render a Result to an SVG document string."""
    if cell < 1:
        raise ValueError("cell must be >= 1")
    layout = result.layout
    if layout is None:
        raise ValueError(
            "result has no layout section (written by an older minitile); re-run `minitile run`"
        )
    cv = _Canvas(layout, result.placement, cell)
    W, H = layout.die.width, layout.die.height
    die_w, die_h = W * cell, H * cell
    legend_rows = math.ceil(6 / LEGEND_COLS)
    content_w = max(die_w, LEGEND_COLS * LEGEND_ITEM_W)
    svg_w = content_w + 2 * PAD
    svg_h = PAD + TITLE_H + die_h + LEGEND_GAP + legend_rows * LEGEND_ROW_H + PAD
    ox, oy = PAD, PAD + TITLE_H
    s = result.summary

    out: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" '
        f'viewBox="0 0 {svg_w} {svg_h}" font-family="Helvetica, Arial, sans-serif">',
        f"<title>minitile: {escape(result.design)}</title>",
        "<defs>",
        '<pattern id="hatch-fixed" patternUnits="userSpaceOnUse" width="6" height="6" '
        'patternTransform="rotate(45)">',
        f'<rect width="6" height="6" fill="{COLOR_FIXED_FILL}"/>',
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{COLOR_FIXED_HATCH}" stroke-width="2"/>',
        "</pattern>",
        "</defs>",
        f'<rect class="background" x="0" y="0" width="{svg_w}" height="{svg_h}" fill="#FFFFFF"/>',
    ]

    # -- title block
    if s.placement_skipped:
        cost = "placement skipped (all modules fixed)"
    else:
        change = percent_change(s.cost_initial, s.cost_final)
        cost = f"cost {s.cost_initial:,.0f} → {s.cost_final:,.0f} ({change})"
    max_detour = "-" if s.max_detour is None else f"{s.max_detour:.3f}"
    lines = [
        (18, "bold", f"{result.design}"),
        (13, "normal", f"seed {s.seed}  ·  {cost}"),
        (13, "normal", f"pipeline stages: {s.total_pipeline_stages}  ·  max detour: {max_detour}"),
    ]
    y = PAD + 16
    for size, weight, text in lines:
        out.append(
            f'<text class="title" x="{PAD}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{COLOR_TEXT}">{escape(text)}</text>'
        )
        y += size + 8

    # -- die, grid, modules, routes, markers
    out.append(f'<g class="die" transform="translate({ox},{oy})">')
    out.append(
        f'<rect class="die-outline" x="0" y="0" width="{die_w}" height="{die_h}" '
        f'fill="#FCFCFC" stroke="{COLOR_DIE}" stroke-width="1.5"/>'
    )
    for gx in range(10, W, 10):
        out.append(
            f'<line class="grid" x1="{gx * cell}" y1="0" x2="{gx * cell}" y2="{die_h}" '
            f'stroke="{COLOR_GRID}" stroke-width="1"/>'
        )
    for gy in range(10, H, 10):
        yy = (H - gy) * cell
        out.append(
            f'<line class="grid" x1="0" y1="{yy}" x2="{die_w}" y2="{yy}" '
            f'stroke="{COLOR_GRID}" stroke-width="1"/>'
        )

    for name in sorted(layout.modules):  # canonical order: JSON keys are written sorted
        m = layout.modules[name]
        r = cv.rects[name]
        x, top = r.x * cell, svg_y(r.y, r.h, H, cell)
        w_px, h_px = r.w * cell, r.h * cell
        kind = "fixed" if m.fixed else "movable"
        fill = "url(#hatch-fixed)" if m.fixed else COLOR_MOVABLE_FILL
        stroke = COLOR_FIXED_STROKE if m.fixed else COLOR_MOVABLE_STROKE
        tip = f"{name} ({m.w}x{m.h}) at [{r.x}, {r.y}]{' fixed' if m.fixed else ''}"
        out.append('<g class="module-group">')
        out.append(f"<title>{escape(tip)}</title>")
        out.append(
            f'<rect class="module {kind}" x="{x}" y="{top}" width="{w_px}" height="{h_px}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )
        label = label_font(name, w_px, h_px)
        if label is not None:
            font_size, rotated = label
            cx, cy = x + w_px / 2, top + h_px / 2
            rot = f' transform="rotate(-90 {fmt(cx)} {fmt(cy)})"' if rotated else ""
            bg = ' paint-order="stroke" stroke="#FFFFFF" stroke-width="2.5"' if m.fixed else ""
            out.append(
                f'<text class="label" x="{fmt(cx)}" y="{fmt(cy)}" font-size="{fmt(font_size)}" '
                f'text-anchor="middle" dominant-baseline="central" fill="{COLOR_TEXT}"'
                f"{bg}{rot}>{escape(name)}</text>"
            )
        out.append("</g>")

    for net in result.nets:
        cls = f"route {net.status}"
        style = _route_style(net.status, net.width)
        tip = escape(f"{net.src} -> {net.dst}: {net.status}")
        if net.status == "unroutable":
            (x1, y1), (x2, y2) = (
                cv.center_of_rect(cv.rects[net.src]),
                cv.center_of_rect(cv.rects[net.dst]),
            )
            out.append(
                f'<line class="{cls}" x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" '
                f"{style}><title>{tip}</title></line>"
            )
        else:
            out.append(
                f'<polyline class="{cls}" points="{_pts(cv.route_points(net))}" {style}>'
                f"<title>{tip}</title></polyline>"
            )

    r_marker = max(3.0, cell * 0.45)
    for net in result.nets:
        for c in stage_marker_cells(net, layout.reach_per_cycle):
            cx, cy = cv.center_of_cell(c)
            out.append(_diamond(cx, cy, r_marker, "stage-marker"))
    out.append("</g>")

    # -- legend
    ly0 = oy + die_h + LEGEND_GAP
    items: list[tuple[str, str]] = [
        (
            "movable module",
            f'<rect x="0" y="-7" width="24" height="14" fill="{COLOR_MOVABLE_FILL}" '
            f'stroke="{COLOR_MOVABLE_STROKE}" stroke-width="1.5"/>',
        ),
        (
            "fixed module",
            f'<rect x="0" y="-7" width="24" height="14" fill="url(#hatch-fixed)" '
            f'stroke="{COLOR_FIXED_STROKE}" stroke-width="1.5"/>',
        ),
        ("route ok (solid)", f'<line x1="0" y1="0" x2="24" y2="0" {_route_style("ok", 128)}/>'),
        (
            "detour > 1.3 (dashed)",
            f'<line x1="0" y1="0" x2="24" y2="0" {_route_style("detour_warning", 128)}/>',
        ),
        (
            "unroutable (dotted)",
            f'<line x1="0" y1="0" x2="24" y2="0" {_route_style("unroutable", 128)}/>',
        ),
        ("pipeline stage", _diamond(12, 0, 5, "legend-marker")),
    ]
    out.append('<g class="legend">')
    for i, (text, swatch) in enumerate(items):
        lx = PAD + (i % LEGEND_COLS) * LEGEND_ITEM_W
        ly = ly0 + (i // LEGEND_COLS) * LEGEND_ROW_H + LEGEND_ROW_H / 2
        out.append(f'<g transform="translate({lx},{fmt(ly)})">{swatch}')
        out.append(
            f'<text x="32" y="0" font-size="12" dominant-baseline="central" '
            f'fill="{COLOR_TEXT}">{escape(text)}</text></g>'
        )
    out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"
