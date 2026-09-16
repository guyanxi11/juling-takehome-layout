# -*- coding: utf-8 -*-
"""
贴墙优先的矩形摆放搜索。

约束按题目原文：
- 全部物体在轮廓内，2D 互不重叠（离地架也不例外）
- 旋转与轮廓边平行或垂直
- 空间足够则全部贴墙
- 不挡门；内开门占 N×N
- 冰箱 length 边为开门边，该侧不能放任何东西

@author: wym
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Sequence, Tuple

from shapely.geometry import Polygon

from .geom import (
    COVER_BUFFER,
    TOL,
    Wall,
    area_overlap,
    fridge_clearance_poly,
    make_rect,
    make_wall_placement,
    placement_polygon,
    room_covers,
    sample_offsets,
    unique_wall_angles,
)
from .model import Item, Placement, Problem, Solution

# 冰箱门前禁放深度（毫米）：禁止任何物体贴在开门边上
FRIDGE_STRIP = 80.0
MAX_NODES = 40000
TIME_LIMIT_SEC = 12.0


def _sort_items(items: Sequence[Item]) -> List[Item]:
    """放置顺序：约束紧、占地大的先放；离地架同样占 2D 面积，放在货架之后。"""
    rank = {"fridge": 0, "iceMaker": 1, "generic": 2, "shelf": 3, "overShelf": 4}

    def key(it: Item) -> Tuple[int, float]:
        return (rank.get(it.kind, 2), -(it.length * it.width))

    return sorted(items, key=key)


def _orientations(item: Item, allow_deep: bool) -> List[Tuple[float, float, str]]:
    """
    贴墙朝向。

    货架/离地架默认 length 沿墙（1000×400 则 400 为进深）。
    冰箱只能 length 沿墙，才能让开门边朝向室内。
    """
    if item.kind == "fridge":
        return [(item.length, item.width, "length_along")]
    shallow = (item.length, item.width, "length_along")
    deep = (item.width, item.length, "width_along")
    if not allow_deep:
        return [shallow]
    return [shallow, deep]


def _rotation_for(wall: Wall, mode: str) -> float:
    """0° 时 length 沿 +x。length 沿墙 ⇒ 旋转=墙角；width 沿墙 ⇒ +90°。"""
    if mode == "length_along":
        return wall.angle_deg
    return wall.angle_deg + 90.0


def _fridge_strip_ok(p: Placement, room: Polygon) -> bool:
    """
    冰箱开门边必须朝室内：80mm 条带与房间相交足够大，说明前面不是墙。
    """
    strip = fridge_clearance_poly(p, FRIDGE_STRIP)
    if strip is None or strip.is_empty:
        return False
    inside = strip.intersection(room.buffer(COVER_BUFFER))
    return inside.area >= p.along * FRIDGE_STRIP * 0.35


def generate_wall_candidates(
    item: Item,
    walls: Sequence[Wall],
    room: Polygon,
    door_zone: Polygon,
    step: float,
    allow_deep: bool,
) -> List[Placement]:
    """沿每段墙生成候选，过滤越界 / 挡门 / 冰箱门对着墙的姿态。"""
    cands: List[Placement] = []
    for wall in walls:
        if wall.length < 30.0:
            continue
        for along, depth, mode in _orientations(item, allow_deep):
            if along > wall.length + TOL:
                continue
            rot = _rotation_for(wall, mode)
            for off in sample_offsets(wall.length, along, step):
                # 中心落在墙内法向一侧，保证有一条边贴在这段墙上
                p = make_wall_placement(item, wall, off, along, depth, rot)
                p.clr_depth = FRIDGE_STRIP
                poly = placement_polygon(p)
                if not room_covers(room, poly):
                    continue
                if area_overlap(poly, door_zone) > TOL:
                    continue
                if item.kind == "fridge" and not _fridge_strip_ok(p, room):
                    continue
                cands.append(p)
    return cands


def _cand_score(p: Placement, door_zone: Polygon) -> float:
    """浅进深、贴墙角、远离门洞优先。"""
    score = 0.0
    score -= p.depth * 0.08
    if p.offset <= TOL:
        score += 40.0
    score += min(placement_polygon(p).centroid.distance(door_zone), 4000.0) / 80.0
    if p.kind == "fridge":
        score += 20.0
    return score


def _collides(poly: Polygon, occupied: List[Polygon], clearances: List[Polygon]) -> bool:
    """
    与已放物体或冰箱开门条带是否有正面积重叠。

    离地架也走这里：题目要求不与其他物体重叠，2D 一律禁叠。
    """
    for other in occupied:
        if area_overlap(poly, other) > TOL:
            return True
    for clr in clearances:
        if area_overlap(poly, clr) > TOL:
            return True
    return False


class _SearchState:
    def __init__(self) -> None:
        self.nodes = 0
        self.deadline = 0.0
        self.best: Optional[Dict[str, Placement]] = None


def _dfs(
    idx: int,
    order: List[Item],
    cand_map: Dict[str, List[Placement]],
    occupied: List[Polygon],
    clearances: List[Polygon],
    placed: Dict[str, Placement],
    st: _SearchState,
) -> bool:
    """回溯。每个物体只尝试已预生成的候选。"""
    st.nodes += 1
    if st.nodes > MAX_NODES or time.time() > st.deadline:
        return False
    if idx >= len(order):
        st.best = dict(placed)
        return True

    item = order[idx]
    for p in cand_map[item.name]:
        poly = placement_polygon(p)
        if _collides(poly, occupied, clearances):
            continue
        occupied.append(poly)
        placed[item.name] = p
        extra = False
        if item.kind == "fridge":
            # 开门边不能放任何东西：后续所有物体都不得进入条带
            clr = fridge_clearance_poly(p, FRIDGE_STRIP)
            if clr is not None:
                clearances.append(clr)
                extra = True
        if _dfs(idx + 1, order, cand_map, occupied, clearances, placed, st):
            return True
        if extra:
            clearances.pop()
        placed.pop(item.name)
        occupied.pop()
    return False


def generate_interior_candidates(
    item: Item,
    walls: Sequence[Wall],
    room: Polygon,
    door_zone: Polygon,
    step: float,
) -> List[Placement]:
    """
    非贴墙候选：网格 + 与轮廓平行/垂直的旋转。

    仅当贴墙方案失败时启用；旋转仍必须与某条轮廓边平行或垂直。
    """
    minx, miny, maxx, maxy = room.bounds
    angles = unique_wall_angles(walls)
    rots: List[float] = []
    for a in angles:
        for extra in (0.0, 90.0):
            r = a + extra
            if all(abs(((r - x + 180) % 360) - 180) > 1.0 for x in rots):
                rots.append(r)
    cands: List[Placement] = []
    x = minx + min(item.length, item.width) * 0.5
    while x <= maxx:
        y = miny + min(item.length, item.width) * 0.5
        while y <= maxy:
            for rot in rots:
                poly = make_rect(x, y, item.length, item.width, rot)
                if not room_covers(room, poly):
                    continue
                if area_overlap(poly, door_zone) > TOL:
                    continue
                p = Placement(
                    name=item.name,
                    x=x,
                    y=y,
                    rotation=(rot + 180.0) % 360.0 - 180.0,
                    length=item.length,
                    width=item.width,
                    kind=item.kind,
                    wall_id=-1,
                    along=item.length,
                    depth=item.width,
                    clr_depth=FRIDGE_STRIP,
                )
                if item.kind == "fridge" and not _fridge_strip_ok(p, room):
                    continue
                cands.append(p)
            y += step
        x += step
    return cands


def _cap_candidates(cands: List[Placement], door_zone: Polygon, limit: int) -> List[Placement]:
    """按墙分组保留，避免全局 Top-N 把候选都收成同一个墙角。"""
    if not cands:
        return []
    by_wall: Dict[int, List[Placement]] = {}
    for p in cands:
        by_wall.setdefault(p.wall_id, []).append(p)
    per_wall = max(10, limit // max(len(by_wall), 1))
    picked: List[Placement] = []

    def keep(p: Placement, acc: List[Placement]) -> bool:
        for q in acc:
            if abs(p.x - q.x) < 12.0 and abs(p.y - q.y) < 12.0 and abs(p.rotation - q.rotation) < 1.0:
                return False
        return True

    for group in by_wall.values():
        group = sorted(group, key=lambda p: -_cand_score(p, door_zone))
        n = 0
        for p in group:
            if keep(p, picked):
                picked.append(p)
                n += 1
            if n >= per_wall:
                break
    for p in sorted(cands, key=lambda x: -_cand_score(x, door_zone)):
        if len(picked) >= limit:
            break
        if keep(p, picked):
            picked.append(p)
    return picked


def _run_search(
    order: List[Item],
    cand_map: Dict[str, List[Placement]],
) -> Tuple[bool, Optional[Dict[str, Placement]], int]:
    st = _SearchState()
    st.deadline = time.time() + TIME_LIMIT_SEC
    ok = _dfs(0, order, cand_map, [], [], {}, st)
    return ok, st.best, st.nodes


def solve_layout(
    room: Polygon,
    walls: Sequence[Wall],
    door_zone: Polygon,
    items: Sequence[Item],
) -> Solution:
    """主求解：先贴墙浅深度，再逐步放宽。"""
    order = _sort_items(items)
    phases = [
        (1e9, False, False, 80),
        (1e9, True, False, 96),
        (100.0, True, False, 120),
        (40.0, True, False, 140),
        (140.0, True, True, 80),
    ]

    last_msg = "未找到可行摆放"
    for step, allow_deep, allow_interior, limit in phases:
        cand_map: Dict[str, List[Placement]] = {}
        empty = False
        for it in order:
            wall_cands = generate_wall_candidates(it, walls, room, door_zone, step, allow_deep)
            interior: List[Placement] = []
            if allow_interior:
                interior = generate_interior_candidates(it, walls, room, door_zone, max(step, 160.0))
            merged = _cap_candidates(wall_cands + interior, door_zone, limit)
            if not merged:
                empty = True
                last_msg = f"{it.name} 在当前阶段没有任何合法姿态"
                break
            cand_map[it.name] = merged
        if empty:
            continue

        ok, best, nodes = _run_search(order, cand_map)
        if ok and best is not None:
            return Solution(
                feasible=True,
                placements=best,
                message=(
                    f"可行（step={step}, deep={allow_deep}, "
                    f"interior={allow_interior}, nodes={nodes}）"
                ),
            )
        last_msg = f"阶段 step={step} 搜索失败（nodes={nodes}）"

    return Solution(feasible=False, placements={}, message=last_msg)


def solve_problem(problem: Problem, room: Polygon, walls: Sequence[Wall], door_zone: Polygon) -> Solution:
    """Problem → Solution 的薄封装。"""
    return solve_layout(room, walls, door_zone, problem.items)
