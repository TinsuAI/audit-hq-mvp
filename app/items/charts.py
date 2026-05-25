"""Pure functions that compute chart geometry. Templates just render coords.

Keeping charts deterministic + unit-testable, no Jinja state hacks.
"""

from __future__ import annotations

from typing import Literal

StepKind = Literal["opening", "in", "out", "closing"]


def sparkline_points(
    values: list[float],
    *,
    width: int = 480,
    height: int = 80,
    pad: int = 8,
) -> dict:
    n = len(values)
    if n == 0:
        return {"points": [], "width": width, "height": height}
    mx = max(values)
    mn = min(values)
    rng = (mx - mn) or 1
    step = (width - pad * 2) / (n - 1) if n > 1 else 0
    pts = []
    for i, v in enumerate(values):
        x = pad + i * step
        y = height - pad - ((v - mn) / rng) * (height - pad * 2)
        pts.append((round(x, 1), round(y, 1)))
    return {"points": pts, "width": width, "height": height, "min": mn, "max": mx}


def waterfall_layout(
    steps: list[tuple[str, float, StepKind]],
    *,
    width: int = 720,
    height: int = 240,
    pad_x: int = 16,
    pad_top: int = 24,
    pad_bottom: int = 48,
) -> dict:
    """Return list of bar geometries + axis info for SVG rendering."""
    if not steps:
        return {"bars": [], "width": width, "height": height, "zero_y": height / 2}

    running = 0.0
    tops: list[float] = []
    bots: list[float] = []
    for _, v, kind in steps:
        if kind in ("opening", "closing"):
            bot, top = 0.0, float(v)
            running = float(v)
        else:
            if v >= 0:
                bot, top = running, running + v
            else:
                bot, top = running + v, running
            running = running + v
        tops.append(top)
        bots.append(bot)

    mx = max(tops + [0.0])
    mn = min(bots + [0.0])
    rng = (mx - mn) or 1
    n = len(steps)
    bw_gap = (width - pad_x * 2) / n
    bw = bw_gap * 0.7
    plot_h = height - pad_top - pad_bottom

    bars = []
    for i, (label, v, kind) in enumerate(steps):
        top = tops[i]
        bot = bots[i]
        y_top = pad_top + plot_h * (mx - top) / rng
        y_bot = pad_top + plot_h * (mx - bot) / rng
        x = pad_x + i * bw_gap + (bw_gap - bw) / 2
        bars.append({
            "label": label,
            "value": v,
            "kind": kind,
            "x": round(x, 1),
            "y": round(min(y_top, y_bot), 1),
            "w": round(bw, 1),
            "h": round(abs(y_bot - y_top), 1),
            "label_y": height - pad_bottom + 16,
            "value_y": round(min(y_top, y_bot) - 4, 1),
            "cx": round(x + bw / 2, 1),
            # Endpoint of running total after this step (for connector lines).
            "end_x": round(x + bw, 1),
            "end_y": round(
                pad_top
                + plot_h
                * (mx - (top if v >= 0 or kind in ("opening", "closing") else bot))
                / rng,
                1,
            ),
        })

    zero_y = pad_top + plot_h * (mx - 0) / rng
    return {
        "bars": bars,
        "width": width,
        "height": height,
        "pad_x": pad_x,
        "pad_bottom": pad_bottom,
        "zero_y": round(zero_y, 1),
    }


def sankey_layout(
    center_label: str,
    nodes: list[tuple[str, float, str]],
    *,
    direction: Literal["in", "out"] = "out",
    width: int = 720,
    height_per_node: int = 28,
    pad: int = 16,
) -> dict:
    if not nodes:
        return {"nodes": [], "width": width, "height": pad * 2}
    n = len(nodes)
    height = n * height_per_node + pad * 2
    total = sum(max(0.0, q) for _, q, _ in nodes) or 1e-9

    cx_center = pad + 16 if direction == "out" else width - pad - 16
    cx_side = width - pad - 220 if direction == "out" else pad + 220
    cy_center = height / 2

    rendered = []
    for i, (code, qty, name) in enumerate(nodes):
        cy = pad + (i + 0.5) * height_per_node + 4
        thickness = 4 + (max(qty, 0.0) / total) * 24
        mid_x = (cx_center + cx_side) / 2
        if direction == "out":
            path = (
                f"M{cx_center + 8},{cy_center} "
                f"C{mid_x},{cy_center} {mid_x},{cy} {cx_side},{cy}"
            )
            label_x = cx_side + 8
            text_anchor = "start"
        else:
            path = (
                f"M{cx_side},{cy} C{mid_x},{cy} {mid_x},{cy_center} {cx_center - 8},{cy_center}"
            )
            label_x = cx_side - 8
            text_anchor = "end"
        rendered.append({
            "code": code,
            "name": name,
            "qty": qty,
            "path": path,
            "thickness": round(thickness, 1),
            "label_x": round(label_x, 1),
            "label_y": round(cy, 1),
            "text_anchor": text_anchor,
        })

    return {
        "nodes": rendered,
        "width": width,
        "height": height,
        "pad": pad,
        "cx_center": cx_center,
        "cy_center": cy_center,
        "center_label": center_label,
        "direction": direction,
    }
