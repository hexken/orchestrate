import os
import shlex
import subprocess
import time
from pathlib import Path

from orchestrate.registry import Unit


def background(
    unit: Unit,
    label: str,
    cmd: list[str],
    logs: Path,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> str:
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{unit['name']}-{label}-{int(time.time() * 1000)}.out"
    quoted = " ".join(shlex.quote(c) for c in cmd)
    wrapped = f"{quoted} >{shlex.quote(str(log))} 2>&1; echo $? >{shlex.quote(str(log))}.rc"
    proc = subprocess.Popen(
        ["bash", "-c", wrapped],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
        cwd=cwd,
    )
    unit.setdefault("jobs", {})[label] = {"log": str(log), "started": time.time(), "pid": proc.pid}
    return str(log)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return True
    return waited == 0


def job(unit: Unit, label: str) -> str | None:
    info = unit.get("jobs", {}).get(label)
    if not info:
        return None
    log, rc = Path(info["log"]), Path(info["log"] + ".rc")
    if not rc.exists() and info.get("pid") and not alive(info["pid"]):
        with open(log, "a") as handle:
            handle.write("\nFAILED job died without an exit code\n")
        rc.write_text("255\n")
    if not rc.exists():
        return None
    lines = log.read_text().strip().splitlines() if log.exists() else []
    return lines[-1] if lines else ""


def exit_code(unit: Unit, label: str) -> int | None:
    info = unit.get("jobs", {}).get(label)
    rc = Path(info["log"] + ".rc") if info else None
    return int(rc.read_text().strip() or 255) if rc and rc.exists() else None


def too_old(unit: Unit, limit_seconds: float, now: float | None = None) -> str | None:
    now = time.time() if now is None else now
    for label, info in unit.get("jobs", {}).items():
        if job(unit, label) is None and now - info["started"] > limit_seconds:
            return str(label)
    return None
