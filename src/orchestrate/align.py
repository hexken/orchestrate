import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from orchestrate import sources, specgate
from orchestrate.config import Config

PROSE = ("spec", "plan", "bookkeeping", "memory", "docs", "log")
TICKED = re.compile(r"`([^`\n]+)`")
PATHLIKE = re.compile(
    r"^(?P<path>[\w.~/-]*[\w-]\.[A-Za-z0-9]{1,8}|[\w.-]+(?:/[\w.-]+)+/?)"
    r"(?::(?P<line>\d+)(?:-\d+)?)?$"
)
IDENT = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)(?:\(\))?$")
BOLD_DEF = re.compile(r"^\s*(?:[-*]\s+)?\*\*(?P<term>[^*]{2,60})\*\*\s*(?:is\b|are\b|:|—|-|–)")
HEADING = re.compile(r"^#{1,6}\s+(?P<title>.*)$")
CODE_FENCE = re.compile(r"^\s*```")


@dataclass
class Finding:
    kind: str
    where: str
    what: str


@dataclass
class Worklist:
    findings: list[Finding] = field(default_factory=list)

    def add(self, kind: str, where: str, what: str) -> None:
        self.findings.append(Finding(kind, where, what))


def tracked(repo: Path) -> list[Path]:
    done = subprocess.run(
        ["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=False
    )
    return [repo / name for name in done.stdout.splitlines()] if done.returncode == 0 else []


def corpus(repo: Path) -> str:
    parts = []
    for path in tracked(repo):
        try:
            parts.append(path.read_text())
        except (UnicodeDecodeError, OSError):
            continue
    return "\n".join(parts)


def looks_like_code(name: str) -> bool:
    bare = name.split(".")[-1]
    return len(bare) >= 4 and ("_" in bare or "." in name or bool(re.search(r"[a-z][A-Z]", bare)))


def prose_lines(text: str) -> list[tuple[int, str]]:
    out, fenced = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if CODE_FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            out.append((number, line))
    return out


def references(config: Config, path: Path, text: str, code: str, work: Worklist) -> None:
    bases = [config.project.repo, path.parent]
    if config.project.planning_repo:
        bases.append(config.project.planning_repo)
    for number, line in prose_lines(text):
        for token in TICKED.findall(line):
            token = token.strip()
            where = f"{path}:{number}"
            match = PATHLIKE.match(token)
            if match and not token.startswith(("http", "-")) and " " not in token:
                ref = Path(match.group("path")).expanduser()
                hits = [ref] if ref.is_absolute() else [b / ref for b in bases]
                found = next((h for h in hits if h.exists()), None)
                if found is None:
                    if "/" in token or match.group("line"):
                        work.add("dead reference", where, f"`{token}` does not exist")
                    continue
                if match.group("line") and found.is_file():
                    count = len(found.read_text(errors="replace").splitlines())
                    if int(match.group("line")) > count:
                        work.add(
                            "dead reference",
                            where,
                            f"`{token}` is past the end of the file ({count} lines)",
                        )
                continue
            ident = IDENT.match(token)
            if ident and looks_like_code(ident.group("name")):
                name = ident.group("name").split(".")[-1]
                if name not in code:
                    work.add("dead reference", where, f"`{token}` is not in the implementation")


def definitions(text: str) -> list[tuple[str, int]]:
    found, glossary, table_seen = [], False, False
    for number, line in prose_lines(text):
        heading = HEADING.match(line)
        if heading:
            glossary = "glossary" in heading.group("title").lower()
            table_seen = False
            continue
        bold = BOLD_DEF.match(line)
        if bold:
            found.append((bold.group("term").strip().lower(), number))
        elif glossary and line.startswith("|"):
            cells = [c.strip().strip("*`") for c in line.strip().strip("|").split("|")]
            if not table_seen:
                table_seen = True
                continue
            if cells and cells[0] and not set(cells[0]) <= set("-: "):
                found.append((cells[0].lower(), number))
    return found


def run(config: Config) -> Worklist:
    work = Worklist()
    code = corpus(config.project.repo)
    defined: dict[str, list[str]] = defaultdict(list)
    for path, _ in sources.files(config, PROSE):
        text = path.read_text(errors="replace")
        references(config, path, text, code, work)
        for term, number in definitions(text):
            defined[term].append(f"{path}:{number}")
    for term, places in sorted(defined.items()):
        if len({p.rsplit(":", 1)[0] for p in places}) > 1:
            work.add(
                "defined twice", places[0], f"'{term}' is also defined at {', '.join(places[1:])}"
            )
    if not config.homes:
        work.add(
            "no home", str(config.path), "no [[homes]] table: each kind of fact needs one home"
        )
    for home in config.homes:
        target = sources.root_of(config, home.root) / home.path
        if not target.exists():
            work.add("no home", str(config.path), f"'{home.question}' points to missing {target}")
    if config.project.planning_repo and config.project.planning_repo.exists():
        known = {p for p, _ in sources.files(config)}
        for path in sorted(config.project.planning_repo.rglob("*.md")):
            if ".git" in path.parts or path.resolve() in known:
                continue
            work.add("unclassified", str(path), "matches no [sources] entry")
    if config.spec_gate.enabled:
        result = specgate.scan(config.spec_gate, config.project.repo)
        for line in result.errors + result.failures:
            work.add("scan", str(config.spec_gate.spec), line)
    return work


def markdown(work: Worklist) -> str:
    out = [f"# Alignment worklist {date.today().isoformat()}", ""]
    if not work.findings:
        return "\n".join([*out, "Nothing to align.", ""])
    groups: dict[str, list[Finding]] = defaultdict(list)
    for finding in work.findings:
        groups[finding.kind].append(finding)
    for kind, items in groups.items():
        out += [f"## {kind} ({len(items)})", ""]
        out += [f"- [ ] {f.where}: {f.what}" for f in items]
        out.append("")
    return "\n".join(out)
