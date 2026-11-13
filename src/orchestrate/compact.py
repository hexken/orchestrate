import re
from collections import Counter
from dataclasses import dataclass

PROTECTED = re.compile(
    r"^(#{1,6})\s+(?:\S+\s+)?(changelog|change log|history|decisions|rulings)\b", re.I
)
HEADING = re.compile(r"^(#{1,6})\s")
FENCE = re.compile(r"^\s*```")
NARRATION = (
    (r"\bnow\b", "'now' narrates a change"),
    (r"\bno longer\b", "'no longer' narrates a change"),
    (
        r"\b(?:changed|renamed|moved|replaced|switched|updated|reduced|raised|increased)\s+"
        r"(?:from|to)\b",
        "says what it changed from or to",
    ),
    (r"\b(?:previously|formerly|used to|originally)\b", "refers to an earlier version"),
    (
        r"\b(?:has|have|was|were) been (?:changed|updated|renamed|removed|added|moved|replaced)\b",
        "narrates an edit",
    ),
    (
        r"\b(?:was|were) (?:changed|updated|renamed|removed|added|moved|replaced)\b",
        "narrates an edit",
    ),
    (
        r"\b(?:per|at|on) the (?:owner|user|client)'?s? (?:request|instruction|decision|ask)\b",
        "credits a request",
    ),
    (r"\bas (?:requested|discussed|decided|agreed|asked)\b", "credits a request"),
    (r"\binstead of\b", "contrasts with an alternative that may be history"),
    (r"\((?:updated|changed|added|revised|fixed|new)\b[^)]*\)", "inline update note"),
    (r"\b(?:updated|revised|changed|added) (?:on )?\d{4}-\d{2}-\d{2}\b", "dated update note"),
    (r"^\s*(?:\*\*)?(?:new|update|updated|note)(?:\*\*)?:", "update marker"),
)
COMPILED = [(re.compile(p, re.I), why) for p, why in NARRATION]
ID = re.compile(r"\b[A-Z]{1,5}-?\d+[a-z]?\b")
LINK = re.compile(r"\]\(([^)\s]+)\)|(https?://[^\s)>\]]+)")
NORMATIVE = re.compile(r"\b(must|never|always|shall|required|at most|at least|only)\b", re.I)
QUANTITY = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:%|ms|s|sec|seconds?|min|minutes?|h|hours?|days?|weeks?|kb|mb|gb|tb|"
    r"tokens?|characters?|chars|lines?|bytes?|requests?|calls?|items?|rows?|usd|dollars?)\b",
    re.I,
)


@dataclass(frozen=True)
class Candidate:
    line: int
    text: str
    why: str


def unprotected_lines(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    fenced, protected_level = False, 0
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            if protected_level and level <= protected_level:
                protected_level = 0
            if PROTECTED.match(line):
                protected_level = level
            continue
        if not protected_level:
            out.append((number, line))
    return out


def scan(text: str) -> list[Candidate]:
    found = []
    for number, line in unprotected_lines(text):
        for pattern, why in COMPILED:
            match = pattern.search(line)
            if match:
                found.append(Candidate(number, line.strip(), why))
                break
    return found


def blocks(text: str) -> list[str]:
    out: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if FENCE.match(line):
            if current is None:
                current = []
            else:
                out.append("\n".join(current))
                current = None
        elif current is not None:
            current.append(line)
    return out


def elements(text: str) -> dict[str, Counter[str]]:
    lines = text.splitlines()
    return {
        "ID": Counter(ID.findall(text)),
        "heading": Counter(line.strip() for line in lines if HEADING.match(line)),
        "code block": Counter(blocks(text)),
        "link": Counter(a or b for a, b in LINK.findall(text)),
        "table row": Counter(
            line.strip().strip("|").split("|")[0].strip()
            for line in lines
            if line.lstrip().startswith("|") and not set(line.strip()) <= set("|-: ")
        ),
        "normative word": Counter(w.lower() for w in NORMATIVE.findall(text)),
        "quantity": Counter(q.lower().replace(" ", "") for q in QUANTITY.findall(text)),
    }


def verify(before: str, after: str) -> list[str]:
    old, new = elements(before), elements(after)
    dropped = []
    for kind, counts in old.items():
        for item, count in counts.items():
            if new[kind][item] < count:
                shown = item if len(item) < 80 else item[:77] + "..."
                dropped.append(f"dropped {kind}: {shown}")
    return dropped
