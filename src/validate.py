# -*- coding: utf-8 -*-
"""
对求解结果做硬约束复查，避免“搜到了但不合法”。

@author: wym
"""

from __future__ import annotations

from typing import List, Sequence

from shapely.geometry import Polygon

from .geom import (
    TOL,
    area_overlap,
    fridge_clearance_poly,
    placement_polygon,
    room_covers,
)
from .model import Item, Placement, Solution


def validate_solution(
    room: Polygon,
    door_zone: Polygon,
    items: Sequence[Item],
    solution: Solution,
) -> List[str]:
    """
    返回违规信息列表，空列表表示通过。

    检查：缺件、越界、挡门、任意两件 2D 重叠、冰箱开门边被占用。
    """
    errors: List[str] = []
    if not solution.feasible:
        return errors
    names = {it.name for it in items}
    if set(solution.placements) != names:
        errors.append(f"摆放集合与输入不一致: {set(solution.placements)} vs {names}")

    polys: List[tuple[str, Polygon, Placement]] = []
    for name, p in solution.placements.items():
        poly = placement_polygon(p)
        if not room_covers(room, poly):
            errors.append(f"{name} 超出轮廓")
        # 再报一刀无缓冲越界，方便发现“只靠容差才算在内”的姿态
        raw_out = poly.difference(room).area
        if raw_out > 1.0:
            errors.append(f"{name} 严格越界 {raw_out:.2f} mm^2")
        if area_overlap(poly, door_zone) > TOL:
            errors.append(f"{name} 遮挡门/内开扇区")
        polys.append((name, poly, p))

    # 任意两件不可有正面积重叠（离地架也不例外；边贴边允许）
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            n1, g1, _ = polys[i]
            n2, g2, _ = polys[j]
            if area_overlap(g1, g2) > TOL:
                errors.append(f"重叠: {n1} 与 {n2}")

    # 冰箱开门边：任何其他物体都不能进入禁放条带
    for name, _, p in polys:
        if p.kind != "fridge":
            continue
        strip = fridge_clearance_poly(p, p.clr_depth)
        if strip is None:
            continue
        for n2, g2, _ in polys:
            if n2 == name:
                continue
            if area_overlap(strip, g2) > TOL:
                errors.append(f"冰箱开门边被占用: {n2} 贴住 {name}")
    return errors
