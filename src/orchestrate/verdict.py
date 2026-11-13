import re
from pathlib import Path

from orchestrate.config import Review

FINDINGS_HEADING = re.compile(r"^(?P<level>#+)\s*(?:\d+[.)]\s*)?findings\b", re.I)
FIXES_HEADING = re.compile(r"^(?:#+[ \t]*|\*\*|__)?[ \t]*fixes\b", re.I | re.M)
LIST_ITEM = re.compile(r"^(?:\d+[.)]|[-*])\s+")
NO_FINDINGS = re.compile(
    r"^(?:\d+[.)]|[-*])\s+[\W_]*(?:none|no findings|nothing(?: to report)?)[\W_]*$", re.I
)


def patterns(review: Review) -> tuple[re.Pattern[str], re.Pattern[str]]:
    words = sorted({*review.clean, *review.hold}, key=len, reverse=True)
    alternatives = "|".join(re.escape(w.lower()) for w in words)
    group = rf"({alternatives})"
    line = re.compile(
        rf"^[\W_]*(?:(?:one-line|overall|final)\s+)?verdict[\W_]*{group}\b"
        rf"(?!\s*[:,-]?\s*(?:no|not)\b)"
    )
    bare = re.compile(rf"^[\W_]*{group}[\W_]*$")
    return line, bare


def finding_items(text: str) -> list[str] | None:
    items: list[str] = []
    level = 0
    seen = sub = False
    for line in text.splitlines():
        if line.startswith("#"):
            depth = len(line) - len(line.lstrip("#"))
            if FINDINGS_HEADING.match(line):
                level, seen, sub = depth, True, False
            elif level and depth > level:
                items.append(line.strip())
                sub = True
            else:
                level = 0
            continue
        if level and not sub and LIST_ITEM.match(line) and not NO_FINDINGS.match(line.strip()):
            items.append(line.strip())
    return items if seen else None


def verdict(path: Path, review: Review) -> str | None:
    path = Path(path)
    if not path.exists() or not path.stat().st_size:
        return None
    line_re, bare_re = patterns(review)
    lines = [line.strip().lower() for line in path.read_text().splitlines() if line.strip()]
    preamble = []
    for index, line in enumerate(lines[: review.verdict_lines]):
        if index and line.startswith("#"):
            break
        preamble.append(line)
    found = next((m for m in map(bare_re.match, preamble) if m), None)
    if not found:
        found = next((m for m in map(line_re.match, lines) if m), None)
    if not found:
        return "unreadable"
    clean = {w.lower() for w in review.clean}
    if found.group(1) not in clean:
        return "hold"
    return "hold" if finding_items(path.read_text()) else "clean"
