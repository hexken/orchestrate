import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrate.registry import Workspace

STAGES = (
    ("building", "started on", "summary written"),
    ("reviewing", "reviews started", ("fixes sent", "reviews clean")),
    ("fixing", "fixes sent", ("light review started", "fixes in")),
    ("light", "light review started", ("reviews clean", "waiting: the light review holds")),
    ("landing", ("reviews clean", "fixes in"), "merged PR"),
)
EVENT_KINDS = (
    ("wedged", "wedged"),
    ("stalled", "stalled"),
    ("gone", "is gone"),
    ("blocked", "dialog"),
    ("land", "land:"),
    ("no verdict", "no verdict"),
    ("light hold", "light review holds"),
    ("review no output", "ended with no output"),
    ("job limit", "has run over"),
    ("moved", "moved past"),
    ("error", "error:"),
)
FINDING = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+.*?[\w./-]+\.\w+:\d+")
FIX_LINE = re.compile(r"(?P<file>[\w.-]+\.md)\s+#(?P<n>\d+):\s*(?P<what>fixed|declined)", re.I)
USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def stamp(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def stage_minutes(timeline: list[list[str]]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for name, begin, end in STAGES:
        begins = (begin,) if isinstance(begin, str) else begin
        ends = (end,) if isinstance(end, str) else end
        opened: datetime | None = None
        for when, what in timeline:
            if what.startswith(begins) and opened is None:
                opened = stamp(when)
            elif opened is not None and what.startswith(ends):
                result[name] += round((stamp(when) - opened).total_seconds() / 60, 1)
                opened = None
    return dict(result)


def event_kind(why: str) -> str:
    return next((kind for kind, needle in EVENT_KINDS if needle in why), "other")


def findings(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines() if FINDING.match(line))


def fixes(summary: Path) -> list[tuple[str, str]]:
    if not summary.exists():
        return []
    text = summary.read_text()
    part = re.split(r"^#+\s*fixes\b.*$", text, flags=re.M | re.I)
    if len(part) < 2:
        return []
    return [(m["file"], m["what"].lower()) for m in FIX_LINE.finditer(part[-1])]


def usage(transcript: Path) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(USAGE_KEYS, 0))
    for line in transcript.read_text().splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = record.get("message") if isinstance(record, dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
            continue
        model = str(message.get("model", "unknown"))
        for key in USAGE_KEYS:
            totals[model][key] += int(message["usage"].get(key) or 0)
    return dict(totals)


def role_of(unit: dict[str, Any], agent: str) -> str:
    if agent == unit["name"]:
        return str(unit.get("role", "builder"))
    return agent.removeprefix(f"{unit['name']}-").replace("-", "_")


def unit_report(folder: Path) -> dict[str, Any]:
    unit = json.loads((folder / "unit.json").read_text())
    timeline = unit.get("timeline", [])
    waits = [what.removeprefix("waiting: ") for _, what in timeline if what.startswith("waiting:")]
    reviews: dict[str, dict[str, Any]] = {}
    for review in sorted(folder.glob(f"{unit['unit']}-*.md")):
        role = review.stem.removeprefix(f"{unit['unit']}-")
        reviews[review.name] = {
            "role": role,
            "findings": findings(review),
            "fixed": 0,
            "declined": 0,
        }
    for name, what in fixes(folder / f"{unit['unit']}.md"):
        if name in reviews:
            reviews[name][what] += 1
    tokens: dict[str, dict[str, dict[str, int]]] = {}
    for transcript in folder.glob("*.jsonl"):
        tokens[role_of(unit, transcript.stem)] = usage(transcript)
    return {
        "unit": unit["unit"],
        "status": unit.get("status"),
        "harness": unit.get("harness"),
        "stages": stage_minutes(timeline),
        "fix_rounds": sum(1 for _, what in timeline if what.startswith("fixes sent")),
        "events": dict(Counter(event_kind(w) for w in waits)),
        "reviews": reviews,
        "tokens": tokens,
    }


def build(ws: Workspace, since: str | None = None) -> dict[str, Any]:
    units = []
    for folder in sorted(p for p in ws.archive.glob("*") if (p / "unit.json").exists()):
        report = unit_report(folder)
        first = json.loads((folder / "unit.json").read_text()).get("timeline", [["9999"]])[0][0]
        if since is None or first >= since:
            units.append(report)
    by_role: dict[str, dict[str, int]] = defaultdict(
        lambda: {"findings": 0, "fixed": 0, "declined": 0, "reviews": 0}
    )
    tokens: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(USAGE_KEYS, 0))
    for report in units:
        for review in report["reviews"].values():
            row = by_role[review["role"]]
            row["reviews"] += 1
            for key in ("findings", "fixed", "declined"):
                row[key] += review[key]
        for role, models in report["tokens"].items():
            for model, counts in models.items():
                for key, value in counts.items():
                    tokens[f"{role} / {model}"][key] += value
    return {"units": units, "reviewers": dict(by_role), "tokens": dict(tokens)}


def markdown(data: dict[str, Any]) -> str:
    out = [
        "# Orchestration report",
        "",
        "## Units",
        "",
        "| unit | harness | status | build | review | fix | light | land | fix rounds | events |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for u in data["units"]:
        s = u["stages"]
        cells = [
            f"{s.get(k, 0):g}" for k in ("building", "reviewing", "fixing", "light", "landing")
        ]
        events = ", ".join(f"{k} {v}" for k, v in sorted(u["events"].items())) or "-"
        out.append(
            f"| {u['unit']} | {u['harness']} | {u['status']} | {' | '.join(cells)} "
            f"| {u['fix_rounds']} | {events} |"
        )
    out += [
        "",
        "Stage times are minutes.",
        "",
        "## Reviewers",
        "",
        "| role | reviews | findings | fixed | declined |",
        "|---|---|---|---|---|",
    ]
    for role, r in sorted(data["reviewers"].items()):
        out.append(
            f"| {role} | {r['reviews']} | {r['findings']} | {r['fixed']} | {r['declined']} |"
        )
    out += [
        "",
        "## Tokens",
        "",
        "| role / model | input | output | cache read | cache write |",
        "|---|---|---|---|---|",
    ]
    for key, t in sorted(data["tokens"].items()):
        out.append(
            f"| {key} | {t['input_tokens']} | {t['output_tokens']} | "
            f"{t['cache_read_input_tokens']} | {t['cache_creation_input_tokens']} |"
        )
    return "\n".join(out) + "\n"
