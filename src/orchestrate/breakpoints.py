import json
import re
import time
from pathlib import Path
from typing import Any

from orchestrate.registry import Unit, Workspace

FINISHED = ("merged", "closed")
Breakpoint = dict[str, Any]


def path(ws: Workspace) -> Path:
    return ws.root / "breakpoints.json"


def load(ws: Workspace) -> dict[str, Breakpoint]:
    file = path(ws)
    data = json.loads(file.read_text()) if file.exists() else {}
    return data if isinstance(data, dict) else {}


def save(ws: Workspace, points: dict[str, Breakpoint]) -> None:
    ws.root.mkdir(parents=True, exist_ok=True)
    path(ws).write_text(json.dumps(points, indent=2) + "\n")


def plan_rows(work_plan: Path | None) -> list[dict[str, str]]:
    if work_plan is None or not work_plan.exists():
        return []
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in work_plan.read_text().splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        if "id" in header and len(cells) == len(header):
            rows.append(dict(zip(header, cells, strict=True)))
    return rows


def plan_units(work_plan: Path | None) -> dict[str, str]:
    return {r["id"]: r["milestone"] for r in plan_rows(work_plan) if "milestone" in r}


def plan_sizes(work_plan: Path | None) -> dict[str, str]:
    return {r["id"]: r["size"] for r in plan_rows(work_plan) if r.get("size")}


def add(
    ws: Workspace, name: str, after: list[str], kind: str = "user", milestone: str = ""
) -> Breakpoint:
    points = load(ws)
    if name in points and points[name]["status"] != "passed":
        raise RuntimeError(f"breakpoint {name} already exists ({points[name]['status']})")
    point = {
        "after": sorted(set(after)),
        "status": "pending",
        "kind": kind,
        "milestone": milestone,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    points[name] = point
    save(ws, points)
    ws.note("-", f"breakpoint {name} added after {', '.join(point['after']) or 'nothing'}")
    return point


def milestone(ws: Workspace, work_plan: Path | None, number: str) -> str:
    units = [uid for uid, m in plan_units(work_plan).items() if m == number]
    if not units:
        raise RuntimeError(f"no unit of milestone {number} in the work plan")
    name = f"milestone-{number}"
    add(ws, name, units, "milestone", number)
    return name


def auto_milestone(ws: Workspace, work_plan: Path | None, unit_id: str) -> None:
    number = plan_units(work_plan).get(unit_id)
    if not number or not number.isdigit():
        return
    if f"milestone-{number}" not in load(ws):
        milestone(ws, work_plan, number)


def blocks(point: Breakpoint, unit_id: str, plan: dict[str, str]) -> bool:
    if point["status"] == "passed" or unit_id in point["after"]:
        return False
    if point["kind"] != "milestone":
        return True
    own = plan.get(unit_id, "")
    return own.isdigit() and int(own) > int(point["milestone"])


def blocking(ws: Workspace, unit_id: str, plan: dict[str, str]) -> str | None:
    return next((n for n, p in load(ws).items() if blocks(p, unit_id, plan)), None)


def reached(ws: Workspace, units: dict[str, Unit]) -> list[str]:
    points = load(ws)
    newly = []
    for name, point in points.items():
        if point["status"] != "pending":
            continue
        if all(units.get(u, {}).get("status") in FINISHED for u in point["after"]):
            point["status"] = "reached"
            point["reached"] = time.strftime("%Y-%m-%d %H:%M:%S")
            newly.append(name)
    if newly:
        save(ws, points)
        for name in newly:
            ws.note("-", f"breakpoint {name} reached")
    return newly


def pass_(ws: Workspace, name: str) -> None:
    points = load(ws)
    if name not in points:
        raise RuntimeError(f"no breakpoint {name}")
    points[name]["status"] = "passed"
    points[name]["passed"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save(ws, points)
    ws.note("-", f"owner input: breakpoint {name} passed")


def active(units: dict[str, Unit]) -> list[str]:
    return [k for k, u in units.items() if u["status"] not in ("merged", "closed", "error")]


def valid_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", name))
