# -*- coding: utf-8 -*-
"""
居灵 TakeHome 入口。

用法：
    python main.py example1.json
    python main.py --all
    python main.py example1.json --no-viz

@author: wym
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from src.geom import build_door_zone, build_room, extract_walls
from src.model import Item, Problem, Solution
from src.placer import solve_problem
from src.validate import validate_solution
from src.viz import render_solution

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"


def load_problem(path: Path) -> Problem:
    """读取题目 JSON。algoToPlace 的 value 为 [length, width]。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    items: List[Item] = []
    for name, size in raw["algoToPlace"].items():
        # 题目约定：value = [length, width]，0° 时 length→x、width→y
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise ValueError(f"{name} 尺寸必须是 [length, width]")
        items.append(Item(name=name, length=float(size[0]), width=float(size[1])))
    door = raw["door"]
    return Problem(
        boundary=[(float(p[0]), float(p[1])) for p in raw["boundary"]],
        door=((float(door[0][0]), float(door[0][1])), (float(door[1][0]), float(door[1][1]))),
        is_open_inward=bool(raw.get("isOpenInward", False)),
        items=items,
        source=str(path),
    )


def run_one(json_path: Path, do_viz: bool = True) -> Solution:
    """求解单个 example，写出 JSON / PNG 到 output/。"""
    problem = load_problem(json_path)
    room = build_room(problem.boundary)
    walls = extract_walls(room, problem.door)
    door_zone = build_door_zone(room, problem.door, problem.is_open_inward)
    sol = solve_problem(problem, room, walls, door_zone)
    errs = validate_solution(room, door_zone, problem.items, sol)
    if errs:
        sol.feasible = False
        sol.message = (sol.message or "") + " | 校验失败: " + "; ".join(errs)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = json_path.stem
    out_json = OUT_DIR / f"{stem}.result.json"
    out_json.write_text(json.dumps(sol.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== {json_path.name} ===")
    print(f"  room area = {room.area:.1f} mm^2, walls = {len(walls)}, valid = {room.is_valid}")
    print(f"  feasible  = {sol.feasible}")
    print(f"  message   = {sol.message}")
    if errs:
        print(f"  VALIDATE FAIL: {errs}")
    else:
        print("  validate  = OK")
    for name, p in sol.placements.items():
        print(f"  {name:16s}  center=({p.x:.2f}, {p.y:.2f})  rot={p.rotation:.2f}°  wall={p.wall_id}")
    print(f"  wrote {out_json}")

    if do_viz:
        out_png = OUT_DIR / f"{stem}.png"
        title = f"{stem}  feasible={sol.feasible}"
        render_solution(room, door_zone, sol, out_png, title=title)
        print(f"  wrote {out_png}")
    return sol


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="居灵轮廓内矩形摆放")
    parser.add_argument("input", nargs="?", help="输入 JSON 路径")
    parser.add_argument("--all", action="store_true", help="跑目录下全部 example*.json")
    parser.add_argument("--no-viz", action="store_true", help="不导出 PNG")
    args = parser.parse_args(argv)

    if args.all:
        files = sorted(ROOT.glob("example*.json"))
        if not files:
            print("未找到 example*.json", file=sys.stderr)
            return 2
        ok = True
        for f in files:
            sol = run_one(f, do_viz=not args.no_viz)
            ok = ok and sol.feasible
        return 0 if ok else 1

    if not args.input:
        parser.print_help()
        return 2
    path = Path(args.input)
    if not path.is_file():
        path = ROOT / args.input
    if not path.is_file():
        print(f"找不到文件: {args.input}", file=sys.stderr)
        return 2
    sol = run_one(path, do_viz=not args.no_viz)
    return 0 if sol.feasible else 1


if __name__ == "__main__":
    raise SystemExit(main())
