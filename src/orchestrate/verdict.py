import re
from pathlib import Path

from orchestrate.config import Review


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
    return "clean" if found.group(1) in clean else "hold"
