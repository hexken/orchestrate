import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NAME = re.compile(r"[a-z][a-z0-9-]{0,31}")
KINDS = ("spec", "plan", "bookkeeping", "memory", "log", "code", "docs")
OWNERS = ("owner", "agent")
STRENGTHS = ("conservative", "full", "none")
MODES = ("interactive", "print")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Project:
    name: str
    repo: Path
    destination: str = "main"
    branch_prefix: str = "agent/"
    planning_repo: Path | None = None
    scratch: str = "scratch"


@dataclass(frozen=True)
class Herdr:
    workspace: str = ""
    orchestrator_pane: str = ""


@dataclass(frozen=True)
class Land:
    adapter: str = ""
    checks: tuple[str, ...] = ()
    heavy_lock: Path | None = None
    push_suffix: str = "-push"
    timeout_minutes: int = 60
    theirs_on_conflict: tuple[str, ...] = ()
    commit_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class Timeouts:
    stall_minutes: int = 20
    wedged_minutes: int = 45
    job_hours: int = 4
    poll_seconds: int = 30


@dataclass(frozen=True)
class Review:
    clean: tuple[str, ...] = ("clean", "meets its outcome")
    hold: tuple[str, ...] = ("not clean", "changes needed", "hold")
    docs_only: tuple[str, ...] = ("docs/**", "*.md")
    verdict_lines: int = 60
    context: tuple[str, ...] = ()


@dataclass(frozen=True)
class Role:
    harness: str
    model: str
    effort: str = "medium"
    mode: str = "interactive"


@dataclass(frozen=True)
class Pipeline:
    reviews: tuple[str, ...]
    light: str


@dataclass(frozen=True)
class Source:
    path: str
    kind: str
    owner: str = "agent"
    compact: str = "none"


@dataclass(frozen=True)
class Sources:
    impl_docs: str = "deferred"
    entries: tuple[Source, ...] = ()


@dataclass(frozen=True)
class Home:
    question: str
    path: str


@dataclass(frozen=True)
class Breakpoints:
    steps: tuple[str, ...] = ("freeze", "align", "compact", "digest")
    conditional_go: str = ""


@dataclass(frozen=True)
class SpecGate:
    enabled: bool = False
    spec: Path | None = None
    acceptance_dir: str = "tests/acceptance"
    drafts_dir: str = "scratch/acceptance"
    install_checks: tuple[str, ...] = ()
    title_section: str = r"^###\s+\d+\.(?P<milestone>\d+)\b"
    test_marker: str = r"@pytest\.mark\.guarantee\(\s*\"(?P<id>[GC]\d+)\"\s*\)"
    property_dir: str = "properties"
    title_pattern: str = (
        r"^-\s+(?P<title>[A-Z][^(\n]*?)(?:\s+\((?P<refs>[GC]\d+(?:,\s*[GC]\d+)*)\))?\s*$"
    )
    guarantee_pattern: str = r"\*\*(?P<id>[GC]\d+)\b"
    milestone: int = 1


DEFAULT_ROLES = {
    "orchestrator": Role("claude", "claude-opus-5-5", "medium"),
    "builder": Role("claude", "claude-opus-5-5", "medium"),
    "reviewer": Role("claude", "claude-opus-5-5", "high"),
    "second_reviewer": Role("agy", "gemini-4-hydrogen-medium", "medium", "print"),
    "light_reviewer": Role("agy", "gemini-4-hydrogen-medium", "medium", "print"),
    "light_reviewer_claude": Role("claude", "claude-opus-5-5", "high"),
    "proxy": Role("claude", "claude-opus-5-5", "high"),
    "proxy_second": Role("agy", "gemini-4-hydrogen-medium", "medium", "print"),
    "mechanical": Role("claude", "claude-sonnet-5-5", "medium"),
}

DEFAULT_PIPELINE = {
    "claude": Pipeline(("reviewer", "second_reviewer"), "light_reviewer"),
    "agy": Pipeline(("reviewer",), "light_reviewer_claude"),
}


@dataclass(frozen=True)
class Config:
    path: Path
    project: Project
    workspace: Path
    herdr: Herdr = field(default_factory=Herdr)
    worktrees: tuple[Path, ...] = ()
    share: tuple[str, ...] = ()
    land: Land = field(default_factory=Land)
    timeouts: Timeouts = field(default_factory=Timeouts)
    review: Review = field(default_factory=Review)
    roles: dict[str, Role] = field(default_factory=lambda: dict(DEFAULT_ROLES))
    pipeline: dict[str, Pipeline] = field(default_factory=lambda: dict(DEFAULT_PIPELINE))
    sources: Sources = field(default_factory=Sources)
    homes: tuple[Home, ...] = ()
    breakpoints: Breakpoints = field(default_factory=Breakpoints)
    spec_gate: SpecGate = field(default_factory=SpecGate)


def expand(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a table")
    return value


def strings(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key} must be a list of strings")
    return tuple(value)


def choice(value: str, options: tuple[str, ...], key: str) -> str:
    if value not in options:
        raise ConfigError(f"{key} must be one of {', '.join(options)}, not {value!r}")
    return value


def build(cls: Any, data: dict[str, Any], key: str, **override: Any) -> Any:
    known = set(cls.__dataclass_fields__)
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"{key}.{sorted(unknown)[0]} is not a known key")
    values = {k: tuple(v) if isinstance(v, list) else v for k, v in data.items()}
    values.update(override)
    try:
        return cls(**values)
    except TypeError as err:
        raise ConfigError(f"{key}: {err}") from err


def roles(data: dict[str, Any]) -> dict[str, Role]:
    result = dict(DEFAULT_ROLES)
    for name, raw in data.items():
        key = f"roles.{name}"
        merged = {**result[name].__dict__, **raw} if name in result else dict(raw)
        if not merged.get("model"):
            raise ConfigError(f"{key}.model is required")
        if not NAME.fullmatch(str(merged.get("harness", ""))):
            raise ConfigError(f"{key}.harness must be an adapter name like 'claude'")
        choice(merged.get("mode", "interactive"), MODES, f"{key}.mode")
        result[name] = build(Role, merged, key)
    return result


def pipelines(data: dict[str, Any], known: dict[str, Role]) -> dict[str, Pipeline]:
    result = dict(DEFAULT_PIPELINE)
    for harness, raw in data.items():
        key = f"pipeline.{harness}"
        reviews = strings(raw.get("reviews", []), f"{key}.reviews")
        for role in reviews:
            if role not in known:
                raise ConfigError(f"{key}.reviews names undefined role {role!r}")
        light = raw.get("light", "")
        if light not in known:
            raise ConfigError(f"{key}.light names undefined role {light!r}")
        result[harness] = Pipeline(reviews, light)
    return result


def sources(data: dict[str, Any]) -> Sources:
    entries = []
    for i, raw in enumerate(data.get("entries", [])):
        key = f"sources.entries[{i}]"
        entry = build(Source, raw, key)
        choice(entry.kind, KINDS, f"{key}.kind")
        choice(entry.owner, OWNERS, f"{key}.owner")
        choice(entry.compact, STRENGTHS, f"{key}.compact")
        entries.append(entry)
    impl_docs = choice(data.get("impl_docs", "deferred"), ("deferred", "maintained"), "sources")
    return Sources(impl_docs, tuple(entries))


def load(path: Path) -> Config:
    path = Path(path).expanduser().resolve()
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"{path}: {err}") from err
    base = path.parent
    raw_project = table(data, "project")
    if not raw_project.get("repo"):
        raise ConfigError("project.repo is required")
    repo = expand(raw_project["repo"], base)
    planning = raw_project.get("planning_repo")
    project = build(
        Project,
        {k: v for k, v in raw_project.items() if k != "workspace"},
        "project",
        repo=repo,
        planning_repo=expand(planning, base) if planning else None,
    )
    workspace = expand(raw_project.get("workspace", ".orchestrate"), repo)
    raw_land = table(data, "land")
    lock = raw_land.get("heavy_lock")
    land = build(Land, raw_land, "land", heavy_lock=expand(lock, base) if lock else None)
    gate = table(data, "spec_gate")
    spec = gate.get("spec")
    spec_gate = build(SpecGate, gate, "spec_gate", spec=expand(spec, base) if spec else None)
    known = roles(table(data, "roles"))
    homes = tuple(build(Home, h, f"homes[{i}]") for i, h in enumerate(data.get("homes", [])))
    return Config(
        path=path,
        project=project,
        workspace=workspace,
        herdr=build(Herdr, table(data, "herdr"), "herdr"),
        worktrees=tuple(
            expand(p, base)
            for p in strings(table(data, "worktrees").get("paths", []), "worktrees.paths")
        ),
        share=strings(table(data, "worktrees").get("share", []), "worktrees.share"),
        land=land,
        timeouts=build(Timeouts, table(data, "timeouts"), "timeouts"),
        review=build(
            Review,
            table(data, "review"),
            "review",
            context=tuple(
                str(expand(c, base))
                for c in strings(table(data, "review").get("context", []), "review.context")
            ),
        ),
        roles=known,
        pipeline=pipelines(table(data, "pipeline"), known),
        sources=sources(table(data, "sources")),
        homes=homes,
        breakpoints=build(Breakpoints, table(data, "breakpoints"), "breakpoints"),
        spec_gate=spec_gate,
    )
