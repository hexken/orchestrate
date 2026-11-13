import fcntl
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Unit = dict[str, Any]
ACTIVE = ("starting", "building", "reviewing", "fixing", "light", "landing")
DONE = ("merged", "closed", "error")


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def registry(self) -> Path:
        return self.root / "units.json"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def events(self) -> Path:
        return self.logs / "events.jsonl"

    @property
    def archive(self) -> Path:
        return self.logs / "units"

    @property
    def briefs(self) -> Path:
        return self.root / "briefs"

    @property
    def supervisor(self) -> Path:
        return self.root / "units.json.supervisor"

    def load(self) -> dict[str, Unit]:
        if not self.registry.exists():
            return {}
        data = json.loads(self.registry.read_text())
        return data if isinstance(data, dict) else {}

    def save(self, units: dict[str, Unit]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.registry.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(units, indent=2) + "\n")
        os.replace(tmp, self.registry)

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / "units.json.lock", "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def event(self, unit: str, status: str | None, what: str) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        record = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "epoch": round(time.time(), 1),
            "unit": unit,
            "status": status,
            "what": what,
        }
        with open(self.events, "a") as handle:
            handle.write(json.dumps(record) + "\n")

    def mark(self, unit: Unit, what: str) -> None:
        unit.setdefault("timeline", []).append([time.strftime("%Y-%m-%d %H:%M:%S"), what])
        self.event(unit.get("unit", "-"), unit.get("status"), what)

    def wait(self, unit: Unit, why: str) -> str:
        unit["status"], unit["event"] = "waiting", why
        self.mark(unit, f"waiting: {why}")
        return why

    def note(self, unit: str, text: str) -> None:
        self.event(unit, None, text)
