import re
from dataclasses import dataclass
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


SEVERITY = re.compile(r"(?<![\w-])(high|medium|low|nit|critical|blocking)(?![\w-])", re.I)
NONE_TITLE = re.compile(r"^[\W_]*(?:no findings|findings[\W_]*none|none)[\W_]*$", re.I)


@dataclass(frozen=True)
class Finding:
    text: str
    severity: str | None


def severity_of(text: str | None) -> str | None:
    found = SEVERITY.search(text or "")
    return found.group(1).lower() if found else None


class Section:
    def __init__(self) -> None:
        self.items: list[Finding] = []
        self.paragraphs: list[Finding] = []
        self.sub: str | None = None
        self.sub_items = 0
        self.sub_none = False
        self.indent: int | None = None
        self.last = "blank"

    def add(self, text: str) -> None:
        self.items.append(Finding(text, severity_of(text) or severity_of(self.sub)))
        self.sub_items += 1

    def open_sub(self, text: str | None) -> None:
        self.close_sub()
        self.sub, self.sub_items, self.sub_none = text, 0, False
        self.indent, self.last = None, "blank"

    def close_sub(self) -> None:
        if self.sub and not self.sub_items and not self.sub_none:
            self.items.append(Finding(self.sub, severity_of(self.sub)))
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
                if NONE_ONLY.match(item["text"]):
                    self.sub_none = True
                else:
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
        if NONE_ONLY.match(stripped):
            self.sub_none = True
        elif self.sub is None:
            self.paragraphs.append(Finding(stripped, severity_of(stripped)))

    def result(self) -> list[Finding]:
        self.close_sub()
        return self.items or self.paragraphs


def findings(text: str) -> list[Finding] | None:
    lines = text.splitlines()
    section: Section | None = None
    level = 0
    result: list[Finding] = []
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
                result += section.result()
            section = None
            if FINDINGS_WORD.search(title):
                seen = True
                if not NONE_TITLE.match(title):
                    section, level = Section(), depth
            continue
        if section is not None:
            following = lines[index + 1] if index + 1 < len(lines) else ""
            section.line(line, following)
    if section is not None:
        result += section.result()
    return result if seen else None


def finding_items(text: str) -> list[str] | None:
    found = findings(text)
    return None if found is None else [f.text for f in found]


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
