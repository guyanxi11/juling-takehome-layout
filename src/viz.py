# -*- coding: utf-8 -*-
"""
摆放结果可视化：轮廓、门禁区、地面层、离地架。

@author: wym
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from shapely.geometry import Polygon

from .geom import fridge_clearance_poly, placement_polygon
from .model import Solution

# 按类型上色；离地架用虚线区分类型（同样占 2D 面积，不得重叠）
_COLORS = {
    "fridge": "#3b82f6",
    "iceMaker": "#06b6d4",
    "shelf": "#f59e0b",
    "overShelf": "#8b5cf6",
    "generic": "#64748b",
}


def _poly_xy(poly: Polygon):
    x, y = poly.exterior.xy
    return list(x), list(y)


def render_solution(
    room: Polygon,
    door_zone: Polygon,
    solution: Solution,
    out_path: Path,
    title: str = "",
) -> None:
    """把房间 + 门禁区 + 各物体画到 PNG。"""
    fig, ax = plt.subplots(figsize=(10, 8))
    rx, ry = _poly_xy(room)
    ax.fill(rx, ry, color="#f8fafc", zorder=0)
    ax.plot(rx, ry, color="#0f172a", lw=1.8, zorder=1)

    if door_zone is not None and not door_zone.is_empty:
        # Polygon / MultiPolygon / GeometryCollection 都要能画
        if hasattr(door_zone, "geoms"):
            geoms = list(door_zone.geoms)
        else:
            geoms = [door_zone]
        labeled = False
        for g in geoms:
            if g.is_empty or g.geom_type not in ("Polygon", "MultiPolygon"):
                continue
            parts = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
            for part in parts:
                dx, dy = _poly_xy(part)
                ax.fill(dx, dy, color="#fecaca", alpha=0.7, zorder=2, label=("door zone" if not labeled else None))
                ax.plot(dx, dy, color="#dc2626", lw=1.2, zorder=3)
                labeled = True

    legend_done = set()
    for name, p in solution.placements.items():
        poly = placement_polygon(p)
        x, y = _poly_xy(poly)
        color = _COLORS.get(p.kind, _COLORS["generic"])
        ls = "--" if p.kind == "overShelf" else "-"
        alpha = 0.35 if p.kind == "overShelf" else 0.55
        label = p.kind if p.kind not in legend_done else None
        legend_done.add(p.kind)
        ax.fill(x, y, color=color, alpha=alpha, zorder=4)
        ax.plot(x, y, color=color, lw=1.6, ls=ls, zorder=5, label=label)
        ax.text(
            p.x,
            p.y,
            f"{name}\n{p.rotation:.1f}°",
            ha="center",
            va="center",
            fontsize=7,
            color="#111827",
            zorder=6,
        )
        if p.kind == "fridge":
            clr = fridge_clearance_poly(p, p.clr_depth)
            if clr is not None and not clr.is_empty:
                cx, cy = _poly_xy(clr)
                ax.plot(cx, cy, color="#2563eb", lw=1.0, ls=":", zorder=5)

    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title or ("feasible" if solution.feasible else "infeasible"))
    ax.legend(loc="best", fontsize=8)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
