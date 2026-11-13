import re
from pathlib import Path

from orchestrate.config import Review

FIXES_HEADING = re.compile(
    r"^(?:#+[ \t]*fixes\b[^\n]*|(?:\*\*|__)[ \t]*fixes\b[^*_\n]*(?:\*\*|__):?[ \t]*"
    r"|fixes[ \t]*:?[ \t]*)$",
    re.I | re.M,
)
HEADING = re.compile(r"^(#+)\s*(.*)$")
BOLD = re.compile(r"^(?:\*\*|__)(?P<text>[^*_]+?)(?:\*\*|__):?$")
FENCE = re.compile(r"^\s*(?:```|~~~)")
ITEM = re.compile(r"^(?P<indent>\s*)(?:\d+[.)]|[-*+])\s+(?P<text>.*)$")
TABLE_RULE = re.compile(r"^\|?[\s:|-]*-[\s:|-]*\|?$")
NONE_ONLY = re.compile(r"^[\W_]*(?:none|no findings|nothing(?: to report)?)[\W_]*$", re.I)
FINDINGS_WORD = re.compile(r"\bfindings\b", re.I)


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


def heading_of(line: str) -> tuple[int, str] | None:
    found = HEADING.match(line)
    if found:
        return len(found.group(1)), found.group(2)
    bold = BOLD.match(line.strip())
    return (7, bold["text"]) if bold else None


def is_rule(line: str) -> bool:
    return line.startswith("|") and bool(TABLE_RULE.match(line))


class Section:
    def __init__(self) -> None:
        self.items: list[str] = []
        self.sub: str | None = None
        self.sub_count = 0
        self.indent: int | None = None
        self.last = "blank"

    def add(self, text: str) -> None:
        self.items.append(text)
        self.sub_count += 1

    def open_sub(self, text: str | None) -> None:
        self.close_sub()
        self.sub, self.sub_count, self.indent, self.last = text, 0, None, "blank"

    def close_sub(self) -> None:
        if self.sub and not self.sub_count:
            self.items.append(self.sub)
        self.sub = None

    def line(self, line: str, following: str) -> None:
        stripped = line.strip()
        if not stripped:
            self.last = "blank"
            return
        item = ITEM.match(line)
        if item:
            indent = len(item["indent"])
            if self.indent is None or indent <= self.indent:
                self.indent = indent
                if not NONE_ONLY.match(item["text"]):
                    self.add(stripped)
            self.last = "item"
            return
        if stripped.startswith("|"):
            if not is_rule(stripped) and not is_rule(following.strip()):
                self.add(stripped)
            return
        if self.last != "blank":
            return
        self.last = "para"
        if not NONE_ONLY.match(stripped):
            self.add(stripped)


def finding_items(text: str) -> list[str] | None:
    lines = text.splitlines()
    section: Section | None = None
    level = 0
    found = Section()
    seen = fence = False
    for index, line in enumerate(lines):
        if FENCE.match(line):
            fence = not fence
            continue
        if fence:
            continue
        heading = heading_of(line)
        if heading:
            depth, title = heading
            if section is not None and depth > level:
                section.open_sub(None if NONE_ONLY.match(title) else line.strip())
                continue
            if section is not None:
                section.close_sub()
            section = None
            if FINDINGS_WORD.search(title):
                section, level, seen = found, depth, True
                section.open_sub(None)
            continue
        if section is not None:
            following = lines[index + 1] if index + 1 < len(lines) else ""
            section.line(line, following)
    found.close_sub()
    return found.items if seen else None


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
