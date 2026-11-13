import re
from dataclasses import dataclass
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"
TOKEN = re.compile(r"\{\{(\w+)\}\}")
WORKSPACE_FILES = (
    "orchestrate.toml",
    "ORCHESTRATION.md",
    "INBOX.md",
    "RESUME.md",
    "AGENT-SETUP.md",
    "setup-permissions.py",
    "briefs/builder.md",
    "briefs/review.md",
    "briefs/second_reviewer.md",
    "briefs/light.md",
    "briefs/refresh.md",
)
FOLDERS = ("adapters", "plans", "rulings", "logs", "bin")
EXCLUDES = ("/.orchestrate", "/scratch/")
WRAPPER = """#!/usr/bin/env bash
exec uv run --quiet --project "${{ORCHESTRATE_HOME:-$HOME/Dev/personal/orchestrate}}" \\
  orch --config "{config}" "$@"
"""


class ScaffoldError(ValueError):
    pass


@dataclass(frozen=True)
class Answers:
    repo: Path
    name: str
    destination: str = "main"
    planning_repo: str = ""
    land: str = ""
    work_plan: str = "(not written yet: run the orchestrate-plan skill)"


def render(text: str, values: dict[str, str]) -> str:
    def swap(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise ScaffoldError(f"template token {{{{{key}}}}} has no value")
        return values[key]

    return TOKEN.sub(swap, text)


def git_dir(repo: Path) -> Path:
    dot = repo / ".git"
    if dot.is_dir():
        return dot
    if dot.is_file():
        text = dot.read_text().strip()
        if text.startswith("gitdir:"):
            path = (repo / text.split(":", 1)[1].strip()).resolve()
            common = path / "commondir"
            return (path / common.read_text().strip()).resolve() if common.exists() else path
    raise ScaffoldError(f"{repo} is not a git repository")


def exclude(repo: Path) -> bool:
    path = git_dir(repo) / "info" / "exclude"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    missing = [line for line in EXCLUDES if line not in lines]
    if missing:
        path.write_text("\n".join([*lines, *missing]) + "\n")
    return bool(missing)


def scaffold(answers: Answers) -> list[tuple[str, str]]:
    repo = answers.repo.expanduser().resolve()
    ws = repo / ".orchestrate"
    values = {
        "name": answers.name,
        "repo": str(repo),
        "destination": answers.destination,
        "planning_repo": answers.planning_repo,
        "land": answers.land,
        "workspace": str(ws),
        "work_plan": answers.work_plan,
    }
    report = []
    for name in WORKSPACE_FILES:
        target = ws / name
        if target.exists():
            report.append((name, "kept"))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render((TEMPLATES / name).read_text(), values))
        report.append((name, "wrote"))
    for folder in FOLDERS:
        (ws / folder).mkdir(parents=True, exist_ok=True)
    wrapper = ws / "bin" / "orch"
    if wrapper.exists():
        report.append(("bin/orch", "kept"))
    else:
        wrapper.write_text(WRAPPER.format(config=ws / "orchestrate.toml"))
        wrapper.chmod(0o755)
        report.append(("bin/orch", "wrote"))
    report.append((".git/info/exclude", "wrote" if exclude(repo) else "kept"))
    return report
