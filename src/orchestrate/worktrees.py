import re
import subprocess
from pathlib import Path

from orchestrate.config import Config


class WorktreeError(RuntimeError):
    pass


def git(cwd: Path, *args: str) -> None:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if done.returncode:
        raise WorktreeError(f"git {' '.join(args)}: {done.stderr.strip()}")


def link(target: Path, link_path: Path) -> bool:
    if link_path.is_symlink() or link_path.exists():
        return False
    link_path.symlink_to(target)
    return True


def record(config_path: Path, paths: list[Path]) -> None:
    text = config_path.read_text()
    value = "paths = [" + ", ".join(f'"{p}"' for p in paths) + "]"
    section = re.search(r"^\[worktrees\]\n(?:(?!^\[).*\n?)*", text, re.M)
    if section is None:
        text = text.rstrip("\n") + f"\n\n[worktrees]\n{value}\n"
    elif re.search(r"^paths\s*=.*$", section.group(0), re.M):
        body = re.sub(r"^paths\s*=.*$", value, section.group(0), count=1, flags=re.M)
        text = text[: section.start()] + body + text[section.end() :]
    else:
        body = section.group(0).replace("[worktrees]\n", f"[worktrees]\n{value}\n", 1)
        text = text[: section.start()] + body + text[section.end() :]
    config_path.write_text(text)


def create(config: Config, count: int) -> list[str]:
    repo = config.project.repo
    origin = f"origin/{config.project.destination}"
    git(repo, "fetch", "-q", "origin")
    report, paths = [], []
    for i in range(1, count + 1):
        path = repo.parent / f"{repo.name}-wt{i}"
        push = Path(f"{path}{config.land.push_suffix}")
        for target in (path, push):
            if target.exists():
                report.append(f"kept   {target}")
            else:
                git(repo, "worktree", "add", "-q", "--detach", str(target), origin)
                report.append(f"added  {target}")
        if link(config.workspace, path / ".orchestrate"):
            report.append(f"linked {path / '.orchestrate'}")
        for name in config.share:
            if (repo / name).exists() and link(repo / name, path / name):
                report.append(f"linked {path / name}")
        paths.append(path)
    known = list(config.worktrees)
    merged = known + [p for p in paths if p not in known]
    if merged != known:
        record(config.path, merged)
    return report
