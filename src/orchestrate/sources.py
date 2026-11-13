from pathlib import Path

from orchestrate.config import Config, Source


def root_of(config: Config, root: str) -> Path:
    if root == "planning" and config.project.planning_repo:
        return config.project.planning_repo
    if root == "workspace":
        return config.workspace
    return config.project.repo


def resolve(config: Config, pattern: str, root: str) -> list[Path]:
    path = Path(pattern).expanduser()
    if path.is_absolute():
        anchor = Path(path.anchor)
        found = list(anchor.glob(str(path.relative_to(anchor))))
    else:
        found = list(root_of(config, root).glob(pattern))
    return sorted(p for p in found if p.is_file())


def files(config: Config, kinds: tuple[str, ...] | None = None) -> list[tuple[Path, Source]]:
    seen: dict[Path, Source] = {}
    for entry in config.sources.entries:
        if kinds is not None and entry.kind not in kinds:
            continue
        for path in resolve(config, entry.path, entry.root):
            seen.setdefault(path.resolve(), entry)
    return sorted(seen.items())


def source_for(config: Config, path: Path) -> Source | None:
    target = path.resolve()
    return next((s for p, s in files(config) if p == target), None)
