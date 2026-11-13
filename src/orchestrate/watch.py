import re
import shutil
import sys
import time
from pathlib import Path

from orchestrate.config import Review
from orchestrate.registry import Unit, Workspace
from orchestrate.verdict import verdict

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
STEP = re.compile(r"=== \d\d:\d\d:\d\d |RESULT")


def tail(path: Path, limit: int = 20000) -> list[str]:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - limit))
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return []
    return [s for s in (ANSI.sub("", p).strip() for p in re.split(r"[\r\n]+", text)) if s]


def minutes(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def render(unit: Unit, ws: Workspace, review: Review, now: float) -> list[str]:
    stamp = time.strftime("%H:%M:%S", time.localtime(now))
    out = [
        f"{unit['unit']}   {unit['status'].upper()}   {unit['branch']}   "
        f"pr {unit.get('pr') or '-'}   {stamp}"
    ]
    if unit.get("event"):
        out.append(f"EVENT: {unit['event']}")
    out += [f"{when[11:16]} {what}" for when, what in unit.get("timeline", [])[-5:]]
    for item in unit.get("required", []):
        path = Path(item["path"])
        state = (verdict(path, review) or "writing") if path.exists() else "pending"
        out.append(f"{item['role']} {item['kind']}: {state}")
    for label, info in unit.get("jobs", {}).items():
        rc = Path(info["log"] + ".rc")
        if rc.exists():
            code = rc.read_text().strip()
            if code == "0":
                continue
            state = f"done, exit {code}"
        else:
            state = f"running {minutes(now - info['started'])}"
        last = (tail(Path(info["log"])) or ["(no output yet)"])[-1]
        out.append(f"{label} {state}: {last}")
    pattern = f"push-{unit['branch'].replace('/', '-')}-*.log"
    logs = sorted(ws.logs.glob(pattern), key=lambda p: p.stat().st_mtime)
    if logs:
        lines = tail(logs[-1])
        steps = [line for line in lines if STEP.match(line)]
        out += [f"push {line.lstrip('= ')}" for line in steps[-2:]]
    return out


def loop(ws: Workspace, review: Review, name: str) -> int:
    while True:
        unit = ws.load().get(name)
        lines = render(unit, ws, review, time.time()) if unit else [f"no unit {name}"]
        size = shutil.get_terminal_size()
        lines = [line[: size.columns] for line in lines][: size.lines - 1]
        sys.stdout.write("\x1b[H\x1b[2J" + "\n".join(lines) + "\n")
        sys.stdout.flush()
        if not unit or unit["status"] in ("merged", "closed"):
            return 0
        time.sleep(5)
