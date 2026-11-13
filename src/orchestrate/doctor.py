import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from orchestrate import ci
from orchestrate.adapters import AdapterError, Harness, Land, adapter_path
from orchestrate.config import Config

SETUP = "write it with the orchestrate-setup skill"


@dataclass(frozen=True)
class Line:
    state: str
    what: str
    fix: str = ""

    def __str__(self) -> str:
        return f"{self.state:8} {self.what}" + (f"  ({self.fix})" if self.fix else "")


def tool(name: str, fix: str) -> Line:
    return Line("ok", name) if shutil.which(name) else Line("missing", name, fix)


def basics() -> list[Line]:
    lines = [
        Line("ok", "inside Herdr")
        if os.environ.get("HERDR_ENV") == "1"
        else Line("fail", "inside Herdr", "run this from a Herdr pane"),
        tool("herdr", "install Herdr: see its official install page"),
        tool("herdr-name", "a helper that names a Herdr agent so the name survives restarts"),
        tool("git", "install git"),
        tool("uv", "install uv: see astral.sh/uv"),
    ]
    ok = sys.version_info >= (3, 11)
    lines.append(
        Line(
            "ok" if ok else "fail",
            f"python {sys.version.split()[0]}",
            "" if ok else "Python 3.11 or later",
        )
    )
    return lines


def git_out(cwd: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def repository(config: Config) -> list[Line]:
    repo = config.project.repo
    if git_out(repo, "rev-parse", "--git-dir") is None:
        return [Line("fail", f"git repository {repo}", "clone or create it first")]
    lines = [Line("ok", f"git repository {repo}")]
    remote = git_out(repo, "remote", "get-url", "origin")
    lines.append(
        Line("ok", f"origin {remote}")
        if remote
        else Line("fail", "origin remote", "add one: git remote add origin <url>")
    )
    for worktree in config.worktrees:
        status = git_out(worktree, "status", "--porcelain", "--untracked-files=no")
        if status is None:
            lines.append(Line("missing", f"worktree {worktree}", "run orch worktrees"))
        elif status:
            lines.append(Line("fail", f"worktree {worktree}", "it has uncommitted changes"))
        else:
            lines.append(Line("ok", f"worktree {worktree}"))
    if config.project.planning_repo and not config.project.planning_repo.exists():
        lines.append(Line("missing", f"planning repo {config.project.planning_repo}"))
    if config.spec_gate.enabled and not (config.spec_gate.spec and config.spec_gate.spec.exists()):
        lines.append(Line("missing", f"spec {config.spec_gate.spec}", "set spec_gate.spec"))
    return lines


def adapters(config: Config) -> list[Line]:
    lines = []
    for name in sorted({role.harness for role in config.roles.values()}):
        path = adapter_path(config.workspace, "harness", name)
        if not os.access(path, os.X_OK):
            lines.append(Line("missing", f"harness adapter {name} ({path})", SETUP))
            continue
        try:
            reply = Harness(path).describe()
        except AdapterError as err:
            lines.append(Line("fail", f"harness adapter {name}", str(err)))
            continue
        lines.append(Line("ok", f"harness adapter {name}"))
        lines.append(tool(str(reply.get("cli") or reply.get("kind")), f"install the {name} CLI"))
    if not config.land.adapter:
        return [*lines, Line("missing", "land adapter", "set land.adapter, then " + SETUP)]
    path = adapter_path(config.workspace, "land", config.land.adapter)
    if not os.access(path, os.X_OK):
        return [*lines, Line("missing", f"land adapter {config.land.adapter} ({path})", SETUP)]
    land = Land(path)
    try:
        reply = land.describe()
    except AdapterError as err:
        return [*lines, Line("fail", f"land adapter {config.land.adapter}", str(err))]
    lines.append(Line("ok", f"land adapter {config.land.adapter}"))
    if reply.get("cli"):
        lines.append(tool(str(reply["cli"]), f"install the {reply['cli']} CLI"))
    lines.append(
        Line("ok", "forge login")
        if land.auth()
        else Line("fail", "forge login", "log in with the forge's CLI yourself")
    )
    return lines


def ci_steps(config: Config) -> list[Line]:
    if not config.land.ci_config:
        return []
    ignore = config.land.ci_ignore
    lines: list[Line] = []
    commands: list[str] = []
    for path in config.land.ci_config:
        if not path.exists():
            lines.append(Line("missing", f"CI config {path}", "fix land.ci_config"))
            continue
        found = ci.steps(path.read_text())
        lines += [
            Line("fail", f"{path.name} line {number} not parsed ({why}): {text}", "check by hand")
            for number, text, why in found.unparsed
            if not ci.ignored(text, ignore)
        ]
        if not found.commands:
            lines.append(
                Line("fail", f"CI config {path.name}: no steps found", "compare it by hand")
            )
        commands += found.commands
    for command in ci.uncovered(commands, config.land.checks, ignore):
        lines.append(
            Line(
                "missing",
                f"CI step with no local check: {command}",
                "add it to land.checks, or to land.ci_ignore if it only belongs in CI",
            )
        )
    names = ", ".join(p.name for p in config.land.ci_config)
    return lines or [Line("ok", f"CI steps of {names} covered by land.checks")]


def run(config: Config | None) -> tuple[list[Line], int]:
    lines = basics()
    if config is None:
        lines.append(Line("missing", "orchestrate.toml", "run the orchestrate-setup skill"))
    else:
        lines += repository(config) + adapters(config) + ci_steps(config)
    return lines, 0 if all(line.state == "ok" for line in lines) else 1
