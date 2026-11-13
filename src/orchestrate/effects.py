import os
import re
import subprocess
import sys
import time
from pathlib import Path

from orchestrate import herdr, jobs
from orchestrate.adapters import Harness, Land, adapter_path, role_env
from orchestrate.config import Config
from orchestrate.registry import Unit, Workspace

TRANSCRIPTS = Path("~/.claude/projects").expanduser()


class EffectError(RuntimeError):
    pass


def glob_regex(pattern: str) -> re.Pattern[str]:
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def matches(path: str, globs: tuple[str, ...]) -> bool:
    return any(glob_regex(g).match(path) for g in globs)


class Effects:
    def __init__(self, config: Config, ws: Workspace) -> None:
        self.config = config
        self.ws = ws

    def now(self) -> float:
        return time.time()

    def git(self, cwd: str, *args: str, check: bool = True) -> str:
        done = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=600, check=False
        )
        if check and done.returncode:
            raise EffectError(f"git {' '.join(args)} failed: {done.stderr.strip()[-400:]}")
        return done.stdout.strip()

    def head(self, unit: Unit) -> str:
        return self.git(unit["worktree"], "rev-parse", "--short", unit["branch"])

    def changed(self, unit: Unit) -> list[str]:
        out = self.git(unit["worktree"], "diff", "--name-only", unit["base"], unit["branch"])
        return out.splitlines()

    def fetch(self, unit: Unit) -> None:
        self.git(unit["worktree"], "fetch", "-q", "origin")

    def is_ancestor(self, unit: Unit, older: str, newer: str) -> bool:
        done = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            cwd=unit["worktree"],
            capture_output=True,
            check=False,
        )
        return done.returncode == 0

    def agent_state(self, name: str) -> str:
        return herdr.agent_state(name)

    def dialog(self, name: str) -> bool:
        return herdr.dialog(name)

    def prompt(self, name: str, message: str) -> None:
        herdr.agent_prompt(name, message)

    def split(self, pane: str, cwd: str) -> str:
        return herdr.split(pane, cwd)

    def tab_close(self, tab: str) -> None:
        herdr.tab_close(tab)

    def tab_create(self, cwd: str, label: str) -> tuple[str, str]:
        workspace = self.config.herdr.workspace or os.environ.get("HERDR_WORKSPACE_ID", "")
        return herdr.tab_create(workspace, cwd, label)

    def watch(self, unit: Unit) -> None:
        pane = herdr.split(unit["pane"], unit["worktree"], "down", 0.65)
        herdr.pane_run(pane, f"{self.ws.root / 'bin' / 'orch'} watch {unit['unit']}")

    def harness(self, role_name: str) -> Harness:
        role = self.config.roles[role_name]
        return Harness(adapter_path(self.ws.root, "harness", role.harness))

    def start_agent(self, role_name: str, name: str, pane: str, cwd: str, brief: str) -> str:
        role = self.config.roles[role_name]
        return self.harness(role_name).start(role, name, pane, cwd, brief, [str(self.ws.root)])

    def background(
        self,
        unit: Unit,
        label: str,
        cmd: list[str],
        role_name: str | None = None,
        cwd: str | None = None,
    ) -> str:
        env = role_env(self.config.roles[role_name]) if role_name else dict(os.environ)
        env["ORCH_CONFIG"] = str(self.config.path)
        env["ORCH_PYTHON"] = sys.executable
        env["ORCH_DESTINATION"] = self.config.project.destination
        env["ORCH_LOGS"] = str(self.ws.logs)
        env["ORCH_LAND_TRIES"] = str(self.config.land.timeout_minutes * 2)
        return jobs.background(unit, label, cmd, self.ws.logs, env=env, cwd=cwd)

    def job(self, unit: Unit, label: str) -> str | None:
        return jobs.job(unit, label)

    def too_old(self, unit: Unit) -> str | None:
        return jobs.too_old(unit, self.config.timeouts.job_hours * 3600, self.now())

    def land_adapter(self) -> Land:
        return Land(adapter_path(self.ws.root, "land", self.config.land.adapter))

    def merge(self, pr: str) -> tuple[bool, str]:
        return self.land_adapter().merge(pr)

    def transcript_age(self, session: str | None) -> float | None:
        if not session or not TRANSCRIPTS.exists():
            return None
        found = list(TRANSCRIPTS.glob(f"*/{session}.jsonl"))
        return self.now() - found[0].stat().st_mtime if found else None

    def transcripts(self, session: str) -> list[Path]:
        return list(TRANSCRIPTS.glob(f"*/{session}.jsonl")) if TRANSCRIPTS.exists() else []
