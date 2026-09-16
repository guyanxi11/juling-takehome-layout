# -*- coding: utf-8 -*-
"""
几何工具：多边形规范化、门禁区、贴墙候选矩形、碰撞与包含判定。

@author: wym
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from shapely.affinity import rotate as shp_rotate
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from .model import Item, Placement, Point as XY

# 坐标单位为毫米。相交面积超过该值才算重叠；边贴边（面积≈0）允许。
TOL = 1.0
# 仅用于吃掉浮点缝，不再把真实越界“扩”进房间（曾把 example1 制冰机 0.4mm 出界放过去）。
COVER_BUFFER = 0.05
# 贴墙时沿内法向微内收，边仍贴墙，但斜墙转角处不易穿出轮廓。
WALL_FLUSH_INSET = 0.5


def _as_xy(p: Sequence[float]) -> XY:
    return (float(p[0]), float(p[1]))


def dist(a: XY, b: XY) -> float:
    """两点欧氏距离。"""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize_ring(coords: Sequence[Sequence[float]]) -> List[XY]:
    """
    去掉重复顶点，保证首尾闭合。

    输入允许 last==first 或 last!=first（题目：线段首尾相连）。
    """
    pts = [_as_xy(p) for p in coords]
    cleaned: List[XY] = []
    for p in pts:
        if not cleaned or dist(cleaned[-1], p) > TOL:
            cleaned.append(p)
    if len(cleaned) >= 2 and dist(cleaned[0], cleaned[-1]) <= TOL:
        cleaned[-1] = cleaned[0]
    elif cleaned:
        cleaned.append(cleaned[0])
    return cleaned


def build_room(coords: Sequence[Sequence[float]]) -> Polygon:
    """
    构造房间多边形。

    若出现自交/重复描边（example4 这类），用 buffer(0) 修复为可用区域。
    """
    ring = normalize_ring(coords)
    poly = Polygon(ring)
    if not poly.is_valid or poly.area <= 0:
        poly = poly.buffer(0)
    if poly.is_empty:
        raise ValueError("轮廓无法构成有效多边形")
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return poly


def unit(vx: float, vy: float) -> XY:
    """向量单位化；零向量原样返回。"""
    n = math.hypot(vx, vy)
    if n < 1e-9:
        return (0.0, 0.0)
    return (vx / n, vy / n)


def inward_normal(a: XY, b: XY, room: Polygon) -> XY:
    """
    边 AB 指向房间内部的单位法向。

    在中点沿左右法向各探一步，落在多边形内的一侧即为内向。
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    left = unit(-dy, dx)
    mid = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
    probe = 8.0
    test = Point(mid[0] + left[0] * probe, mid[1] + left[1] * probe)
    if room.buffer(COVER_BUFFER).contains(test) or room.contains(test):
        return left
    return (-left[0], -left[1])


def _point_on_segment(p: XY, a: XY, b: XY, tol: float = TOL) -> bool:
    """点是否落在线段 AB 上（含端点）。"""
    if abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) > tol * max(dist(a, b), 1.0):
        return False
    return min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol and min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol


def _project_t(p: XY, a: XY, b: XY) -> float:
    """点 P 在 AB 上的参数 t，A=0，B=1。"""
    vx, vy = b[0] - a[0], b[1] - a[1]
    den = vx * vx + vy * vy
    if den < 1e-12:
        return 0.0
    return ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / den


@dataclass
class Wall:
    """一段可贴靠的墙（已扣除门洞）。"""

    wall_id: int
    a: XY
    b: XY
    inward: XY

    @property
    def length(self) -> float:
        return dist(self.a, self.b)

    @property
    def angle_deg(self) -> float:
        """墙方向角，范围 (-180, 180]。"""
        return math.degrees(math.atan2(self.b[1] - self.a[1], self.b[0] - self.a[0]))

    def point_at(self, s: float) -> XY:
        """沿墙从 A 走 s 毫米。"""
        t = unit(self.b[0] - self.a[0], self.b[1] - self.a[1])
        return (self.a[0] + t[0] * s, self.a[1] + t[1] * s)


def _collinear_overlap_params(a: XY, b: XY, d1: XY, d2: XY) -> Optional[Tuple[float, float]]:
    """
    若门线段落在墙 AB 上，返回门在 AB 参数轴上的 [t0, t1]（0~1）。
    否则返回 None。
    """
    if not (_point_on_segment(d1, a, b, tol=8.0) or _point_on_segment(d2, a, b, tol=8.0)):
        # 门端点可能略偏，再看是否共线且投影落在段内
        line_tol = 8.0
        def dist_to_line(p: XY) -> float:
            return abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / max(dist(a, b), 1.0)
        if dist_to_line(d1) > line_tol or dist_to_line(d2) > line_tol:
            return None
    t1 = _project_t(d1, a, b)
    t2 = _project_t(d2, a, b)
    lo, hi = min(t1, t2), max(t1, t2)
    # 与 [0,1] 无重叠则不是这段墙上的门
    if hi < -0.02 or lo > 1.02:
        return None
    return (max(0.0, lo), min(1.0, hi))


def extract_walls(room: Polygon, door: Tuple[XY, XY]) -> List[Wall]:
    """
    从轮廓提取可贴墙段：跳过过短边，把门洞从所在墙上挖掉。
    """
    coords = list(room.exterior.coords)
    d1, d2 = _as_xy(door[0]), _as_xy(door[1])
    raw: List[Tuple[XY, XY]] = []
    for i in range(len(coords) - 1):
        a, b = _as_xy(coords[i]), _as_xy(coords[i + 1])
        if dist(a, b) < 20.0:
            continue
        ov = _collinear_overlap_params(a, b, d1, d2)
        if ov is None:
            raw.append((a, b))
            continue
        t0, t1 = ov
        # 门前一段
        if t0 > 0.02:
            pa = a
            pb = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            if dist(pa, pb) >= 20.0:
                raw.append((pa, pb))
        # 门后一段
        if t1 < 0.98:
            pa = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            pb = b
            if dist(pa, pb) >= 20.0:
                raw.append((pa, pb))

    walls: List[Wall] = []
    for idx, (a, b) in enumerate(raw):
        walls.append(Wall(wall_id=idx, a=a, b=b, inward=inward_normal(a, b, room)))
    return _merge_collinear_walls(walls)


def _merge_collinear_walls(walls: List[Wall]) -> List[Wall]:
    """
    把首尾相接、方向相同的墙段合成更长的一段。

    轮廓常把共线点拆成多段（example2 顶边），合并后冰箱等长物体才贴得上。
    """
    if not walls:
        return []
    used = [False] * len(walls)
    merged: List[Wall] = []

    def try_extend(start: XY, end: XY, ang: float, inward: XY) -> Tuple[XY, XY]:
        changed = True
        while changed:
            changed = False
            for i, w in enumerate(walls):
                if used[i]:
                    continue
                if abs(((w.angle_deg - ang + 180) % 360) - 180) > 2.0:
                    continue
                if dist(w.inward, inward) > 0.2:
                    continue
                # 本段终点接下一段起点
                if dist(end, w.a) <= 8.0:
                    used[i] = True
                    end = w.b
                    changed = True
                elif dist(start, w.b) <= 8.0:
                    used[i] = True
                    start = w.a
                    changed = True
        return start, end

    for i, w in enumerate(walls):
        if used[i]:
            continue
        used[i] = True
        a, b = try_extend(w.a, w.b, w.angle_deg, w.inward)
        merged.append(Wall(wall_id=len(merged), a=a, b=b, inward=w.inward))
    return merged


def door_width(door: Tuple[XY, XY]) -> float:
    """门宽 N。"""
    return dist(_as_xy(door[0]), _as_xy(door[1]))


def build_door_zone(room: Polygon, door: Tuple[XY, XY], is_open_inward: bool) -> Polygon:
    """
    门禁区。

    - 任何门：门缝本身不可被遮挡（细长缓冲带）。
    - 内开门：再叠加 N×N 扇形占位（题目 note 的 1×1 即按门宽为单位）。
    """
    d1, d2 = _as_xy(door[0]), _as_xy(door[1])
    n = door_width(door)
    # 门缝缓冲：防止物体贴在门洞上把出入口堵死（外开门也要留缝）
    door_line = LineString([d1, d2]).buffer(max(n * 0.04, 20.0), cap_style=2)
    if not is_open_inward or n < 1.0:
        return door_line

    # 内开门：扇区是以门宽 N 为边长的正方形，落在房间内侧
    # 题目 note「占据 1x1」= 以门宽为 1 的单位，即 N×N
    inward = inward_normal(d1, d2, room)
    sq = Polygon([
        d1,
        d2,
        (d2[0] + inward[0] * n, d2[1] + inward[1] * n),  # 沿内法向推 N
        (d1[0] + inward[0] * n, d1[1] + inward[1] * n),
    ])
    return unary_union([door_line, sq])


def make_rect(cx: float, cy: float, length: float, width: float, angle_deg: float) -> Polygon:
    """
    以中心点构造矩形。

    旋转 0°：length 沿 +x，width 沿 +y，与题目“初始角度为 0 度”一致。
    """
    geom = box(cx - length / 2.0, cy - width / 2.0, cx + length / 2.0, cy + width / 2.0)
    if abs(angle_deg) < 1e-9:
        return geom
    return shp_rotate(geom, angle_deg, origin=(cx, cy), use_radians=False)


def placement_polygon(p: Placement) -> Polygon:
    """Placement → 多边形。"""
    return make_rect(p.x, p.y, p.length, p.width, p.rotation)


def area_overlap(a: Polygon, b: Polygon) -> float:
    """相交面积；相切（面积≈0）视为不重叠。"""
    if a.is_empty or b.is_empty:
        return 0.0
    return a.intersection(b).area


def room_covers(room: Polygon, geom: Polygon) -> bool:
    """
    物体必须整体落在轮廓内（允许贴边，不允许穿出）。

    只向外扩 COVER_BUFFER 吃浮点，越界面积按绝对值限制（≤1 mm²）。
    """
    if geom.is_empty:
        return False
    outside = geom.difference(room.buffer(COVER_BUFFER))
    return outside.area <= 1.0


def fridge_clearance_poly(p: Placement, depth: float) -> Optional[Polygon]:
    """
    冰箱开门边前方的禁放条带。

    题目：开门边不能放任何东西（含离地架）。贴墙时开门朝内，条带宽为 length。
    """
    if p.kind != "fridge" or depth <= 0:
        return None
    nx, ny = p.inward
    if abs(nx) + abs(ny) < 1e-9:
        # 无墙信息时：开门边取旋转后 +width 方向
        rad = math.radians(p.rotation)
        nx, ny = -math.sin(rad), math.cos(rad)
    # 条带中心：冰箱前表面再向外 depth/2
    cx = p.x + nx * (p.depth / 2.0 + depth / 2.0)
    cy = p.y + ny * (p.depth / 2.0 + depth / 2.0)
    return make_rect(cx, cy, p.along, depth, p.rotation)


def sample_offsets(wall_len: float, item_along: float, step: float) -> List[float]:
    """
    沿墙滑动的起点偏移。

    核心策略：先按物体长度无重叠铺槽（0, along, 2*along...），
    保证多件相同货架不会全部挤在同一个墙角；再补两端和 step 抽样。
    """
    max_off = wall_len - item_along
    if max_off < -TOL:
        return []
    if max_off <= TOL:
        return [0.0]
    offs = {0.0, max_off}
    # 无重叠槽位：多件同尺寸物体可以各占一槽，回溯时不会互相抢同一个角
    slot = 0.0
    while slot <= max_off + 1e-6:
        offs.add(min(slot, max_off))
        slot += max(item_along, 1.0)
    if step <= 0 or step > 1e8:
        return sorted(offs)
    x = 0.0
    while x <= max_off + 1e-6:
        offs.add(min(max(x, 0.0), max_off))
        x += step
    for r in (0.25, 0.5, 0.75):
        offs.add(max_off * r)
    return sorted(offs)


def make_wall_placement(
    item: Item,
    wall: Wall,
    offset: float,
    along: float,
    depth: float,
    rotation: float,
) -> Placement:
    """根据贴墙参数生成 Placement（中心 = 墙点 + 内向 * 半深）。"""
    # 中心沿墙位置：offset 是物体起点，再加 along/2 才到矩形中心
    s = offset + along / 2.0
    foot = wall.point_at(s)
    # 沿内法向抬起 depth/2，再加 WALL_FLUSH_INSET，一条边贴墙且不穿出斜边
    cx = foot[0] + wall.inward[0] * (depth / 2.0 + WALL_FLUSH_INSET)
    cy = foot[1] + wall.inward[1] * (depth / 2.0 + WALL_FLUSH_INSET)
    # 归一化到 (-180, 180]，避免 360 与 0 重复
    rot = (rotation + 180.0) % 360.0 - 180.0
    return Placement(
        name=item.name,
        x=cx,
        y=cy,
        rotation=rot,
        length=item.length,
        width=item.width,
        kind=item.kind,
        wall_id=wall.wall_id,
        along=along,
        depth=depth,
        inward=wall.inward,
        offset=offset,
    )


def unique_wall_angles(walls: Sequence[Wall]) -> List[float]:
    """轮廓边方向（模 90°），用于非贴墙时仍保持与轮廓平行/垂直。"""
    angs = []
    for w in walls:
        a = w.angle_deg % 90.0
        if all(abs(a - b) > 1.0 for b in angs):
            angs.append(a)
    if not angs:
        angs = [0.0]
    return angs
