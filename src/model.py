# -*- coding: utf-8 -*-
"""
输入 / 输出数据结构。

@author: wym
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


Point = Tuple[float, float]


def item_kind(name: str) -> str:
    """
    根据输入字典的 key 解析物品类型。

    规则：前缀匹配 fridge / iceMaker / overShelf / shelf。
    """
    if name.startswith("overShelf"):
        return "overShelf"
    if name.startswith("shelf"):
        return "shelf"
    if name.startswith("fridge"):
        return "fridge"
    if name.startswith("iceMaker"):
        return "iceMaker"
    return "generic"


@dataclass
class Item:
    """待摆放矩形。length/width 对应旋转角 0° 时的 x 向 / y 向尺寸。"""

    name: str
    length: float
    width: float

    @property
    def kind(self) -> str:
        return item_kind(self.name)

    @property
    def is_elevated(self) -> bool:
        """离地架标识。题目要求不与其他物体重叠，因此 2D 上仍占独立区域。"""
        return self.kind == "overShelf"


@dataclass
class Placement:
    """单个物体的摆放结果：中心点 + 逆时针旋转角（度）。"""

    name: str
    x: float
    y: float
    rotation: float
    length: float
    width: float
    kind: str
    wall_id: int = -1
    along: float = 0.0
    depth: float = 0.0
    inward: Point = (0.0, 0.0)
    offset: float = 0.0  # 沿墙起点偏移，仅贴墙姿态有意义
    clr_depth: float = 80.0  # 冰箱门前禁放条带深度


@dataclass
class Problem:
    """一道输入题。"""

    boundary: List[Point]
    door: Tuple[Point, Point]
    is_open_inward: bool
    items: List[Item]
    source: str = ""


@dataclass
class Solution:
    """求解输出。"""

    feasible: bool
    placements: Dict[str, Placement] = field(default_factory=dict)
    message: str = ""
    door_zone_wkt: Optional[str] = None

    def to_dict(self) -> dict:
        """转成题目要求的 JSON 结构。"""
        out = {
            "feasible": self.feasible,
            "message": self.message,
            "placements": {},
        }
        for name, p in self.placements.items():
            out["placements"][name] = {
                "center": [round(p.x, 4), round(p.y, 4)],
                "rotation": round(p.rotation, 4),
            }
        return out
