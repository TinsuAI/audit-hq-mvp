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
    max_nodes: int = 15,
    min_thickness: float = 1.5,
) -> dict:
    """Sankey 2 cấp, đọc được khi có nhiều mã.

    - Sort theo qty giảm dần.
    - Cap ở max_nodes; phần đuôi gộp thành 1 node "+N khác" với tổng qty.
    - Ribbon origin được stack theo tỷ lệ qty trên thanh center (không cùng 1 điểm).
    - Thickness có floor để mã nhỏ vẫn nhìn thấy.
    """
    if not nodes:
        return {"nodes": [], "width": width, "height": pad * 2}

    # Sort by qty desc; lift None to 0.
    sorted_nodes = sorted(nodes, key=lambda t: -max(0.0, float(t[1] or 0)))

    # Cap + lump tail.
    if len(sorted_nodes) > max_nodes:
        visible = sorted_nodes[: max_nodes - 1]
        hidden = sorted_nodes[max_nodes - 1 :]
        hidden_qty = sum(max(0.0, float(q or 0)) for _, q, _ in hidden)
        visible.append((f"+{len(hidden)} mã khác", hidden_qty, "đã gộp"))
        sorted_nodes = visible

    n = len(sorted_nodes)
    height = n * height_per_node + pad * 2
    qtys = [max(0.0, float(q or 0)) for _, q, _ in sorted_nodes]
    total = sum(qtys) or 1e-9

    cx_center = pad + 16 if direction == "out" else width - pad - 16
    cx_side = width - pad - 220 if direction == "out" else pad + 220

    # Center bar spans the chart vertical area; ribbons attach at cumulative
    # Y proportional to each node's qty (real sankey stacking).
    center_top = pad
    center_bot = height - pad
    center_span = center_bot - center_top

    rendered = []
    cum = 0.0
    for i, ((code, qty_raw, name), qty) in enumerate(zip(sorted_nodes, qtys, strict=False)):
        cy_side = pad + (i + 0.5) * height_per_node + 4
        # Ribbon origin Y on center bar = midpoint of this node's allocated slice.
        slice_top = center_top + (cum / total) * center_span
        slice_h = (qty / total) * center_span
        cy_origin = slice_top + slice_h / 2
        cum += qty

        thickness = max(min_thickness, (qty / total) * 28)
        mid_x = (cx_center + cx_side) / 2

        if direction == "out":
            path = (
                f"M{cx_center + 8},{round(cy_origin, 1)} "
                f"C{mid_x},{round(cy_origin, 1)} {mid_x},{round(cy_side, 1)} {cx_side},{round(cy_side, 1)}"
            )
            label_x = cx_side + 8
            text_anchor = "start"
        else:
            path = (
                f"M{cx_side},{round(cy_side, 1)} "
                f"C{mid_x},{round(cy_side, 1)} {mid_x},{round(cy_origin, 1)} "
                f"{cx_center - 8},{round(cy_origin, 1)}"
            )
            label_x = cx_side - 8
            text_anchor = "end"

        is_other = code.startswith("+") and "khác" in code
        share_pct = (qty / total * 100) if total > 0 else 0.0
        rendered.append({
            "code": code,
            "name": name,
            "qty": qty_raw if not is_other else qty,
            "share_pct": round(share_pct, 1),
            "path": path,
            "thickness": round(thickness, 1),
            "label_x": round(label_x, 1),
            "label_y": round(cy_side, 1),
            "text_anchor": text_anchor,
            "is_other": is_other,
        })

    return {
        "nodes": rendered,
        "width": width,
        "height": height,
        "pad": pad,
        "cx_center": cx_center,
        "cy_center": height / 2,
        "center_label": center_label,
        "direction": direction,
        "total_qty": total,
    }
